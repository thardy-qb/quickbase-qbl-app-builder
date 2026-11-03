from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from qblparser.validators import validate_qbl_references

Path = Tuple[str, ...]

ADDED = "added"
REMOVED = "removed"
MODIFIED = "modified"


@dataclass(frozen=True)
class ResourceChange:

    path: Path
    kind: str
    qbl_type: str

    @property
    def logical_id(self) -> str:
        return self.path[-1] if self.path else ""

    def __str__(self) -> str:
        return f"{self.kind} {self.qbl_type} at {' > '.join(self.path)}"


def iter_resources(document: Any, path: Path = ()) -> Iterator[Tuple[Path, Mapping[str, Any]]]:
    if isinstance(document, Mapping):
        if "Type" in document and path:
            yield path, document
        for key, value in document.items():
            if key == "Properties":
                continue
            yield from iter_resources(value, path + (str(key),))
    elif isinstance(document, list):
        for index, value in enumerate(document):
            yield from iter_resources(value, path + (str(index),))


def _without_children(node: Mapping[str, Any]) -> Dict[str, Any]:
    own: Dict[str, Any] = {}
    for key, value in node.items():
        if isinstance(value, Mapping) and any(
            isinstance(child, Mapping) and "Type" in child for child in value.values()
        ):
            continue
        if isinstance(value, list) and any(
            isinstance(child, Mapping) and "Type" in child for child in value
        ):
            continue
        if isinstance(value, Mapping) and isinstance(value.get("Resources"), Mapping):
            own[key] = {k: v for k, v in value.items() if k != "Resources"}
            continue
        own[key] = value
    return own


def diff_solutions(source: Mapping[str, Any],
                   destination: Mapping[str, Any]) -> List[ResourceChange]:
    source_nodes = dict(iter_resources(source))
    destination_nodes = dict(iter_resources(destination))

    changes: List[ResourceChange] = []
    for path, node in source_nodes.items():
        qbl_type = str(node.get("Type", ""))
        if path not in destination_nodes:
            changes.append(ResourceChange(path, ADDED, qbl_type))
        elif _without_children(node) != _without_children(destination_nodes[path]):
            changes.append(ResourceChange(path, MODIFIED, qbl_type))
    for path, node in destination_nodes.items():
        if path not in source_nodes:
            changes.append(ResourceChange(path, REMOVED, str(node.get("Type", ""))))

    return sorted(changes, key=lambda change: change.path)


def _read(document: Any, path: Sequence[str]) -> Optional[Any]:
    node: Any = document
    for step in path:
        if isinstance(node, Mapping) and step in node:
            node = node[step]
        elif isinstance(node, list) and step.isdigit() and int(step) < len(node):
            node = node[int(step)]
        else:
            return None
    return node


def _write(document: Any, path: Sequence[str], value: Any) -> None:
    node = document
    for step in path[:-1]:
        if not isinstance(node, Mapping):
            raise MergeError(f"cannot place a resource under {' > '.join(path)}")
        node = node.setdefault(step, {})
    node[path[-1]] = value


class MergeError(ValueError):
    pass


def apply_selection(destination: Mapping[str, Any], source: Mapping[str, Any],
                    selection: Sequence[Path]) -> Dict[str, Any]:
    merged = deepcopy(dict(destination))
    for path in selection:
        node = _read(source, path)
        if node is None:
            raise MergeError(f"source has no resource at {' > '.join(path)}")
        _write(merged, path, deepcopy(node))
    return merged


def unresolved_after_merge(merged: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [issue for issue in validate_qbl_references(merged)
            if issue["Code"] == "REF001"]


def required_additions(source: Mapping[str, Any],
                       merged: Mapping[str, Any]) -> Dict[str, List[Path]]:
    declared: Dict[str, List[Path]] = {}
    for path, _node in iter_resources(source):
        declared.setdefault(path[-1], []).append(path)

    missing: Dict[str, List[Path]] = {}
    for issue in unresolved_after_merge(merged):
        problem = issue["Problem"]
        start = problem.find("'")
        end = problem.find("'", start + 1)
        if start == -1 or end == -1:
            continue
        logical_id = problem[start + 1:end]
        missing[logical_id] = declared.get(logical_id, [])
    return missing


def complete_selection(source: Mapping[str, Any], destination: Mapping[str, Any],
                       selection: Sequence[Path],
                       *, max_rounds: int = 20) -> Tuple[List[Path], Dict[str, List[Path]]]:
    chosen: List[Path] = list(dict.fromkeys(selection))

    for _round in range(max_rounds):
        merged = apply_selection(destination, source, chosen)
        missing = required_additions(source, merged)
        if not missing:
            return chosen, {}

        added = False
        unsatisfiable: Dict[str, List[Path]] = {}
        for logical_id, paths in missing.items():
            if not paths:
                unsatisfiable[logical_id] = []
                continue
            for path in paths:
                if path not in chosen:
                    chosen.append(path)
                    added = True
        if not added:
            return chosen, unsatisfiable

    raise MergeError(
        f"selection did not settle after {max_rounds} rounds; this suggests a "
        f"reference cycle the source cannot satisfy"
    )


__all__ = [
    "ADDED",
    "MODIFIED",
    "MergeError",
    "Path",
    "REMOVED",
    "ResourceChange",
    "apply_selection",
    "complete_selection",
    "diff_solutions",
    "iter_resources",
    "required_additions",
    "unresolved_after_merge",
]
