from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from qblparser.contracts import QBLIssue
from qblparser.utils.qbl_tags import is_bad_ref, tag_of


REFERENCE_KEYS: Dict[str, Tuple[int, Tuple[str, ...]]] = {
    "App": (0, ("QB::Application",)),
    "Table": (1, ("QB::Table",)),
    "Pipeline": (1, ("QB::Pipeline",)),
    "DataSource": (1, ("QB::ConnectedDataSource",)),
    "Role": (1, ("QB::Application::Role",)),
    "Dashboard": (1, ("QB::Dashboard", "QB::HomePage")),
    "Page": (1, ("QB::HomePage", "QB::CodePage", "QB::RichTextPage")),
    "Field": (2, ("QB::Field::",)),
    "Report": (2, ("QB::Report",)),
    "Chart": (2, ("QB::Chart",)),
    "Relationship": (2, ("QB::Relationship",)),
    "Form": (2, ("QB::Form",)),
    "FormV2": (2, ("QB::FormV2",)),
    "CustomEmail": (2, ("QB::CustomEmail",)),
    "DocumentTemplate": (2, ("QB::DocumentTemplate",)),
    "ReportGroup": (2, ("QB::ReportGroup",)),
    "RecordSet": (2, ("QB::ConnectedRecordSet", "QB::PlaceholderRecordSet")),
    "PipelineChannelAccount": (2, ("QB::PipelineChannelAccount",)),
    "PipelineStep_DataSource": (2, ("QB::PipelineStep::DataSource",)),
    "FormElement": (3, ("QB::Form::Element::", "QB::FormElement")),
    "FormV2Page": (3, ("QB::FormV2::Page",)),
    "ReportFormula": (3, ("QB::Report::Formula::",)),
    "SummaryFormula": (3, ("QB::Report::SummaryFormula::", "QB::Report::SummaryVariable")),
    "ConnectedColumn": (3, ("QB::ConnectedColumn::",)),
    "FormV2Section": (4, ("QB::FormV2::Section",)),
    "FormV2Column": (5, ("QB::FormV2::Column",)),
    "FormV2Element": (6, ("QB::FormV2::Element",)),
}

REFERENCE_CONTAINER_KINDS: Dict[str, Tuple[str, ...]] = {
    "Field": ("QB::Table",),
    "Report": ("QB::Table",),
    "Chart": ("QB::Table",),
    "Relationship": ("QB::Table",),
    "Form": ("QB::Table",),
    "FormV2": ("QB::Table",),
    "CustomEmail": ("QB::Table",),
    "DocumentTemplate": ("QB::Table",),
    "ReportGroup": ("QB::Table",),
    "FormElement": ("QB::Form", "QB::FormV2"),
    "FormV2Page": ("QB::FormV2",),
    "FormV2Section": ("QB::FormV2",),
    "FormV2Column": ("QB::FormV2",),
    "FormV2Element": ("QB::FormV2",),
    "ReportFormula": ("QB::Report", "QB::Report::"),
    "SummaryFormula": ("QB::Report", "QB::Report::"),
    "RecordSet": ("QB::ConnectedDataSource", "QB::ConnectedDataSource::"),
    "ConnectedColumn": ("QB::ConnectedDataSource", "QB::ConnectedDataSource::"),
    "Table": ("QB::Application",),
    "Role": ("QB::Application",),
    "Dashboard": ("QB::Application",),
    "Page": ("QB::Application",),
}


REFERENCE_KEY_TYPES: Dict[str, Tuple[str, ...]] = {
    key: types for key, (_rank, types) in REFERENCE_KEYS.items()
}


@dataclass(frozen=True)
class Declaration:

    logical_id: str
    qbl_type: str
    path: Tuple[str, ...]

    @property
    def full_path(self) -> Tuple[str, ...]:
        return self.path + (self.logical_id,)


@dataclass
class SymbolTable:

    by_id: Dict[str, List[Declaration]] = dataclass_field(default_factory=dict)
    by_full_path: Dict[Tuple[str, ...], Declaration] = dataclass_field(default_factory=dict)
    duplicates: List[Tuple[Tuple[str, ...], str, str]] = dataclass_field(default_factory=list)
    parameters: set = dataclass_field(default_factory=set)

    def add(self, declaration: Declaration) -> None:
        self.by_id.setdefault(declaration.logical_id, []).append(declaration)
        self.by_full_path.setdefault(declaration.full_path, declaration)

    def candidates(self, logical_id: str) -> List[Declaration]:
        return self.by_id.get(logical_id, [])


def _is_declaration(value: Any) -> bool:
    return isinstance(value, dict) and str(value.get("Type", "")).startswith("QB::")


def build_symbol_table(qbl_data: Any) -> SymbolTable:
    table = SymbolTable()

    parameters = qbl_data.get("ParameterDefinitions") if isinstance(qbl_data, dict) else None
    if isinstance(parameters, dict):
        table.parameters.update(str(name) for name in parameters)

    seen: Dict[Tuple[Tuple[str, ...], str], str] = {}

    def walk(node: Any, path: Tuple[str, ...]) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(key, str) and key.startswith("$") and _is_declaration(value):
                    declaration = Declaration(key, str(value.get("Type", "")), path)
                    scope_key = (path, key)
                    if scope_key in seen:
                        table.duplicates.append((path, key, declaration.qbl_type))
                    else:
                        seen[scope_key] = declaration.qbl_type
                    table.add(declaration)
                    walk(value, path + (key,))
                else:
                    walk(value, path)
        elif isinstance(node, list):
            for item in node:
                walk(item, path)

    walk(qbl_data, ())
    return table


@dataclass(frozen=True)
class ReferenceSite:

    tag: str
    value: Any
    path: Tuple[str, ...]

    location: str


def iter_references(qbl_data: Any) -> Iterator[ReferenceSite]:

    def walk(node: Any, path: Tuple[str, ...], location: str) -> Iterator[ReferenceSite]:
        tag = tag_of(node)
        if tag:
            yield ReferenceSite(tag, node, path, location)
            return

        if isinstance(node, dict):
            for key, value in node.items():
                next_path = path
                if isinstance(key, str) and key.startswith("$") and _is_declaration(value):
                    next_path = path + (key,)
                yield from walk(value, next_path, f"{location} > {key}")
        elif isinstance(node, list):
            for index, item in enumerate(node):
                yield from walk(item, path, f"{location}[{index}]")

    yield from walk(qbl_data, (), "$")


def _issue(code: str, severity: str, logical_id: str, path: str, qbl_type: str, problem: str) -> QBLIssue:
    return {
        "LogicalID": logical_id,
        "Path": path,
        "Type": qbl_type,
        "Problem": problem,
        "Code": code,
        "Severity": severity,
    }


def _type_matches(qbl_type: str, expected: Sequence[str]) -> bool:
    return any(qbl_type == prefix or qbl_type.startswith(prefix) for prefix in expected)


def _is_container_kind(qbl_type: str, kinds: Sequence[str]) -> bool:
    for kind in kinds:
        if kind.endswith("::"):
            if qbl_type.startswith(kind):
                return True
        elif qbl_type == kind:
            return True
    return False


def _shared_prefix_length(left: Sequence[str], right: Sequence[str]) -> int:
    length = 0
    for a, b in zip(left, right):
        if a != b:
            break
        length += 1
    return length


def _anchor_path(
    table: SymbolTable, named: Dict[str, str], scope: Sequence[str], container_types: Sequence[str]
) -> Optional[Tuple[str, ...]]:
    if not container_types:
        return None

    best: Optional[Tuple[int, Tuple[str, ...]]] = None
    for value in named.values():
        for candidate in table.candidates(value):
            if not _is_container_kind(candidate.qbl_type, container_types):
                continue
            score = _shared_prefix_length(candidate.path, scope)
            if best is None or score > best[0]:
                best = (score, candidate.full_path)
    if best is not None:
        return best[1]

    for depth in range(len(scope), 0, -1):
        declaration = table.by_full_path.get(tuple(scope[:depth]))
        if declaration and _is_container_kind(declaration.qbl_type, container_types):
            return declaration.full_path

    return None


def _resolve(
    table: SymbolTable,
    target_key: str,
    target_id: str,
    named: Dict[str, str],
    scope: Sequence[str],
) -> Optional[Declaration]:
    candidates = table.candidates(target_id)
    if not candidates:
        return None

    expected = REFERENCE_KEY_TYPES.get(target_key)
    if expected:
        by_kind = [c for c in candidates if _type_matches(c.qbl_type, expected)]
        candidates = by_kind or candidates

    anchor = _anchor_path(table, named, scope, REFERENCE_CONTAINER_KINDS.get(target_key, ()))
    if anchor is not None:
        scoped = [c for c in candidates if c.full_path[:len(anchor)] == anchor]
        if not scoped:
            return None
        candidates = scoped

    return max(candidates, key=lambda c: _shared_prefix_length(c.path, scope))


def _ordered_ids(entries: Any, key: str) -> set:
    found = set()
    if not isinstance(entries, list):
        return found
    for entry in entries:
        if isinstance(entry, dict):
            value = entry.get(key)
            if isinstance(value, str):
                found.add(value)
        elif isinstance(entry, str):
            found.add(entry)
    return found


def _check_ordering_completeness(qbl_data: Any, table: SymbolTable) -> List[QBLIssue]:
    issues: List[QBLIssue] = []
    resources = qbl_data.get("Resources") if isinstance(qbl_data, dict) else None
    if not isinstance(resources, dict):
        return issues

    for app_id, app in resources.items():
        if not (isinstance(app_id, str) and app_id.startswith("$App_") and isinstance(app, dict)):
            continue
        properties = app.get("Properties") if isinstance(app.get("Properties"), dict) else {}

        for container, order_key, ref_key, label in (
            ("Tables", "TableOrder", "Table", "table"),
            ("Roles", "RoleOrder", "Role", "role"),
        ):
            declared = app.get(container)
            if not isinstance(declared, dict):
                continue
            declared_ids = {k for k, v in declared.items() if isinstance(k, str) and _is_declaration(v)}
            if not declared_ids:
                continue

            if order_key not in properties:
                continue

            ordered = _ordered_ids(properties.get(order_key), ref_key)
            for missing in sorted(declared_ids - ordered):
                issues.append(_issue(
                    "REF005", "error", missing, f"{app_id} > Properties > {order_key}", "QB::Application",
                    f"Declared {label} '{missing}' is missing from {order_key}",
                ))

    return issues


def validate_qbl_references(qbl_data: Any) -> List[QBLIssue]:
    if not isinstance(qbl_data, dict):
        return []

    table = build_symbol_table(qbl_data)
    issues: List[QBLIssue] = []

    for scope, logical_id, qbl_type in table.duplicates:
        issues.append(_issue(
            "REF004", "error", logical_id, " > ".join(scope) or "$", qbl_type,
            f"Duplicate logical ID '{logical_id}' declared twice in the same scope",
        ))

    issues.extend(_check_ordering_completeness(qbl_data, table))

    for site in iter_references(qbl_data):
        owner = site.path[-1] if site.path else "$"

        if site.tag == "Var":
            name = site.value.get("Name") if isinstance(site.value, dict) else None
            if name is not None and str(name) not in table.parameters:
                issues.append(_issue(
                    "REF003", "error", owner, site.location, "!Var",
                    f"Parameter '{name}' is not declared in ParameterDefinitions",
                ))
            continue

        if site.tag == "BadRef" or is_bad_ref(site.value):
            message = site.value.get("message") if isinstance(site.value, dict) else ""
            issues.append(_issue(
                "REF000", "warning", owner, site.location, "!BadRef",
                f"Reference could not be resolved when the solution was exported: {message}",
            ))
            continue

        if site.tag != "Ref" or not isinstance(site.value, dict):
            continue

        named = {k: v for k, v in site.value.items() if isinstance(v, str) and v.startswith("$")}
        if not named:
            continue

        target_key = max(named, key=lambda k: REFERENCE_KEYS.get(k, (99, ()))[0])
        target_id = named[target_key]

        declaration = _resolve(table, target_key, target_id, named, site.path)

        if declaration is None:
            issues.append(_issue(
                "REF001", "error", owner, site.location, "!Ref",
                f"Reference to '{target_id}' does not resolve to a declared resource",
            ))
            continue

        expected = REFERENCE_KEY_TYPES.get(target_key)
        if expected and not _type_matches(declaration.qbl_type, expected):
            issues.append(_issue(
                "REF002", "error", owner, site.location, "!Ref",
                f"Reference key '{target_key}' points at '{target_id}', "
                f"which is declared as {declaration.qbl_type}",
            ))

    return issues
