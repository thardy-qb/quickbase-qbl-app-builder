from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from qblparser.utils.qbl_tags import REF_MARKER

from .code_pages import reresolve_field_ids
from .tokens import resolve_field_tokens
from .merge import Path, iter_resources

_SHARED_CONTAINERS = {"Charts": "Reports"}

_ID_FLOORS = {"Forms": 10, "Pages": 2}

_MATCHED_BY_ID = ("Forms", "Relationships", "Steps")

_REPLACED_WHOLESALE = ("MainSection", "Sidebar")

_DATA_BEARING = ("QB::Field::", "QB::Table")

_COMPUTED = ("QB::Field::Lookup", "QB::Field::Summary", "QB::Field::RecordID",
             "QB::Field::DateCreated", "QB::Field::DateModified",
             "QB::Field::LastModifiedBy", "QB::Field::ReportLink")


def _holds_data(qbl_type: str) -> bool:
    return (qbl_type.startswith(_DATA_BEARING)
            and not qbl_type.startswith(_COMPUTED)
            and not qbl_type.endswith("::Formula"))

UPDATE_REMOVES_DATA = "UPD001"
UPDATE_REMOVES_RESOURCE = "UPD002"
UPDATE_CHANGES_FIELD_TYPE = "UPD003"


@dataclass
class UpdatePlan:

    document: Dict[str, Any]
    removed: List[Tuple[Path, str]] = field(default_factory=list)
    pinned: List[Tuple[Path, int, int]] = field(default_factory=list)
    reassigned: List[Tuple[Path, int, int]] = field(default_factory=list)
    possible_renames: List[Tuple[Path, Path]] = field(default_factory=list)
    retyped: List[Tuple[Path, str, str]] = field(default_factory=list)
    code_page_fields: List[Tuple[str, str, int, int]] = field(default_factory=list)
    field_tokens: int = 0

    def findings(self) -> List[Dict[str, Any]]:
        out = []
        renamed_from = {old for old, _new in self.possible_renames}
        for path, qbl_type in self.removed:
            data = _holds_data(qbl_type)
            hint = ""
            if path in renamed_from:
                new = next(n for o, n in self.possible_renames if o == path)
                hint = (f" If '{new[-1]}' is this field renamed, pass "
                        f"renames={{('{path[-3]}', '{new[-1]}'): '{path[-1]}'}} "
                        f"and its data is kept.")
            out.append({
                "Code": UPDATE_REMOVES_DATA if data else UPDATE_REMOVES_RESOURCE,
                "Severity": "Error" if data else "Warning",
                "Problem": (f"The PUT deletes {qbl_type} {path[-1]}, which the "
                            f"deployed solution has and this document does not"
                            + (", and every value stored in it." if data else ".")
                            + hint),
                "Path": " > ".join(path),
                "Type": qbl_type,
            })
        for path, deployed, sent in self.retyped:
            out.append({
                "Code": UPDATE_CHANGES_FIELD_TYPE,
                "Severity": "Warning",
                "Problem": (f"{path[-1]} changes type from {deployed} to {sent}. "
                            f"The platform converts the stored values, and a "
                            f"conversion that cannot hold one loses it."),
                "Path": " > ".join(path),
                "Type": sent,
            })
        return out

    @property
    def safe(self) -> bool:
        return not any(f["Severity"] == "Error" for f in self.findings())


def _id_space(path: Path) -> Path:
    container = path[-2]
    return path[:-2] + (_SHARED_CONTAINERS.get(container, container),)


def _reconcilable(document: Any) -> Dict[Path, Mapping[str, Any]]:
    return {path: node for path, node in iter_resources(document)
            if path[0] in ("Resources", "ExternalResources")
            and not any(step in _MATCHED_BY_ID or step in _REPLACED_WHOLESALE
                        for step in path)}


def _platform_added(path: Path, node: Mapping[str, Any]) -> bool:
    return (path[-1] == "$Report_List_Changes"
            and (node.get("Properties") or {}).get("DisplayOnlyNewOrChangedRecords") is True)


def _numbered(document: Any) -> Dict[Path, Mapping[str, Any]]:
    return {path: node for path, node in _reconcilable(document).items()
            if isinstance(node.get("Id"), int) and not isinstance(node.get("Id"), bool)
            and len(path) >= 2}


def _rewrite_references(node: Any, table_key: str, old: str, new: str,
                        inside: bool) -> None:
    if isinstance(node, Mapping):
        if isinstance(node, dict) and node.get("Field") == new:
            table = node.get("Table")
            if table == table_key or (table is None and inside):
                node["Field"] = old
        if (isinstance(node, dict) and node.get(REF_MARKER)
                and node.get("value") == new and inside):
            node["value"] = old
        for key, value in node.items():
            _rewrite_references(value, table_key, old, new,
                                inside or key == table_key)
    elif isinstance(node, list):
        for value in node:
            _rewrite_references(value, table_key, old, new, inside)


def _apply_renames(document: Dict[str, Any],
                   renames: Mapping[Tuple[str, str], str]) -> None:
    for (table_key, new), old in renames.items():
        found = False
        for path, node in list(iter_resources(document)):
            if len(path) >= 2 and path[-2] == "Fields" and path[-1] == new \
                    and path[-3] == table_key:
                parent = document
                for step in path[:-1]:
                    parent = parent[int(step)] if isinstance(parent, list) else parent[step]
                if old in parent:
                    raise ValueError(
                        f"rename {new} -> {old} in {table_key}: the document "
                        f"already has a field {old}")
                items = list(parent.items())
                parent.clear()
                for key, value in items:
                    parent[old if key == new else key] = value
                found = True
        if not found:
            raise ValueError(
                f"rename {new} -> {old}: the document has no field {new} in "
                f"{table_key}")
        _rewrite_references(document, table_key, old, new, inside=False)


def plan_update(document: Mapping[str, Any], deployed: Mapping[str, Any], *,
                renames: Optional[Mapping[Tuple[str, str], str]] = None,
                ) -> UpdatePlan:
    working: Dict[str, Any] = copy.deepcopy(dict(document))
    if renames:
        _apply_renames(working, renames)

    plan = UpdatePlan(document=working)
    deployed_numbered = _numbered(deployed)
    deployed_all = _reconcilable(deployed)
    working_all = _reconcilable(working)

    for path, node in deployed_all.items():
        if path not in working_all:
            if _platform_added(path, node):
                continue
            plan.removed.append((path, str(node.get("Type", ""))))
        elif str(node.get("Type", "")).startswith("QB::Field::"):
            sent = str(working_all[path].get("Type", ""))
            if sent != node.get("Type"):
                plan.retyped.append((path, str(node.get("Type")), sent))

    used: Dict[Path, set] = {}
    for path, node in deployed_numbered.items():
        used.setdefault(_id_space(path), set()).add(node["Id"])

    new_nodes: List[Tuple[Path, Dict[str, Any]]] = []
    for path, node in _numbered(working).items():
        if path in deployed_numbered:
            deployed_id = deployed_numbered[path]["Id"]
            if node["Id"] != deployed_id:
                plan.pinned.append((path, node["Id"], deployed_id))
                node["Id"] = deployed_id
        else:
            new_nodes.append((path, node))

    by_space: Dict[Path, List[Tuple[Path, Dict[str, Any]]]] = {}
    for path, node in new_nodes:
        by_space.setdefault(_id_space(path), []).append((path, node))
    for space, members in by_space.items():
        taken = used.get(space, set())
        if not any(node["Id"] in taken for _path, node in members):
            continue
        floor = _ID_FLOORS.get(space[-1], 1)
        next_id = max(max(taken, default=0) + 1, floor)
        for path, node in sorted(members, key=lambda item: item[1]["Id"]):
            plan.reassigned.append((path, node["Id"], next_id))
            node["Id"] = next_id
            next_id += 1

    removed_fields = [(p, t) for p, t in plan.removed if p[-2:-1] == ("Fields",)]
    added_fields = [(p, str(n.get("Type", ""))) for p, n in working_all.items()
                    if len(p) >= 2 and p[-2] == "Fields" and p not in deployed_all]
    for old_path, old_type in removed_fields:
        for new_path, new_type in added_fields:
            if new_path[:-1] == old_path[:-1] and new_type == old_type:
                plan.possible_renames.append((old_path, new_path))

    plan.code_page_fields = reresolve_field_ids(working)
    plan.field_tokens = resolve_field_tokens(working)
    return plan


__all__ = [
    "UPDATE_CHANGES_FIELD_TYPE",
    "UPDATE_REMOVES_DATA",
    "UPDATE_REMOVES_RESOURCE",
    "UpdatePlan",
    "plan_update",
]
