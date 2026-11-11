from __future__ import annotations

from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from qblparser.contracts import QBLIssue
from qblparser.qbl_schema import NESTED_DOCUMENTED_PROPERTIES, get_resource_spec
from qblparser.qbl_schema.schema_types import SCHEMA_ENUMS
from qblparser.utils.qbl_tags import tag_of


DOCUMENTED_ENUMS: Dict[Tuple[str, str], Tuple[str, ...]] = {
    ("QB::ConnectedRecordSet", "SetType"): ("Table", "Query"),
    ("QB::PlaceholderRecordSet", "SetType"): ("Table", "Query"),
}

KNOWN_VALUES: Dict[Tuple[str, str], Tuple[str, ...]] = {
    ("QB::Report::Table", "DefaultRowHeight"): (
        "Default", "ExtraTall", "Medium", "Short", "Tall"),
    ("QB::Report::Table", "ColumnHeaderText"): ("Default", "Truncate", "Wrap"),
    ("QB::Report::Table", "GroupDisplay"): ("Collapsed", "Default", "Expanded"),
    ("QB::Report::Table", "InlineEditing"): ("Default", "No", "Yes"),
    ("QB::FormV2::Element::Field", "LabelMode"): ("Custom", "Default", "Hidden"),
    ("QB::Field::URL::Formula", "Target"): ("NewWindow", "Popup", "SamePage"),
    ("QB::Report::Table", "RowNumberVisibility"): ("Default", "Hidden", "Visible"),
    ("QB::Table", "DefaultReportSettings.DefaultRowNumberVisibility"): ("Hidden", "Visible"),
}

VALUE_PATTERNS: Dict[Tuple[str, str], Tuple[Tuple[str, ...], Tuple[str, ...], str]] = {
    ("QB::FormV2::Element::Field", "Width"): (
        ("px", "%"), ("Default",), "must end with 'px' or '%', or be Default"),
}


DOCUMENTED_NESTED_ENUMS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "QB::Field::Summary": {
        "Summary.Function": (
            "Count", "Total", "Average", "Maximum", "Minimum", "StdDeviation",
            "CombinedText", "DistinctCount", "AnyRelatedRecords", "CombinedUser",
        ),
    },
}

NESTED_KINDS: Dict[str, Dict[str, str]] = {
    "QB::Chart::Bar": {"DataDetails.DataAxis.Data": "list"},
    "QB::Chart::HorizontalBar": {"DataDetails.DataAxis.Data": "list"},
    "QB::Chart::StackedBar": {"DataDetails.DataAxis.Data": "list"},
    "QB::Chart::HorizontalStackedBar": {"DataDetails.DataAxis.Data": "list"},
    "QB::Chart::Area": {"DataDetails.DataAxis.Data": "list"},
    "QB::Chart::Gauge": {"Data": "mapping"},
    "QB::Chart::ProgressBar": {"Data": "mapping"},
}


UNSUPPORTED_TYPES = {
    "QB::Field::Unsupported": (
        "vCard and iCalendar fields export as QB::Field::Unsupported and cannot "
        "be created or updated through QBL; a table holding one is likely to "
        "have mismatched field IDs between this document and the real app"
    ),
}

UNSUPPORTED_PROPERTIES = {
    "QB::Report::Table": {
        "Format": (
            "the Format property on a table report is not supported by QBL and "
            "is ignored on import"
        ),
    },
}


def classify(value: Any) -> str:
    if tag_of(value):
        return "reference"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "mapping"
    return "unknown"


def _issue(code: str, severity: str, logical_id: str, path: str, qbl_type: str, problem: str) -> QBLIssue:
    return {
        "LogicalID": logical_id,
        "Path": path,
        "Type": qbl_type,
        "Problem": problem,
        "Code": code,
        "Severity": severity,
    }


def iter_resources(qbl_data: Any) -> Iterator[Tuple[str, str, Mapping[str, Any], str]]:

    def walk(node: Any, logical_id: str, path: str) -> Iterator[Tuple[str, str, Mapping[str, Any], str]]:
        if isinstance(node, dict):
            qbl_type = node.get("Type")
            if isinstance(qbl_type, str) and qbl_type.startswith("QB::"):
                properties = node.get("Properties")
                if isinstance(properties, dict):
                    yield logical_id, qbl_type, properties, path
            for key, value in node.items():
                next_id = key if isinstance(key, str) and key.startswith("$") else logical_id
                yield from walk(value, next_id, f"{path} > {key}")
        elif isinstance(node, list):
            for index, item in enumerate(node):
                yield from walk(item, logical_id, f"{path}[{index}]")

    yield from walk(qbl_data, "$", "$")


def _reference_only_property(spec, prop: str) -> bool:
    property_spec = spec.properties.get(prop) if spec and spec.properties else None
    if not property_spec or not property_spec.kinds:
        return False

    non_null = {kind for kind in property_spec.kinds if kind != "null"}
    if non_null != {"reference"}:
        return False

    return property_spec.kind_checkable


def validate_qbl_values(qbl_data: Any) -> List[QBLIssue]:
    if not isinstance(qbl_data, dict):
        return []

    issues: List[QBLIssue] = []
    issues.extend(_check_document_version(qbl_data))
    issues.extend(_check_platform_version_support(qbl_data))

    inert_properties: Dict[Tuple[str, str], List[str]] = {}

    for logical_id, qbl_type, properties, path in iter_resources(qbl_data):
        spec = get_resource_spec(qbl_type)
        issues.extend(_check_nested_kinds(logical_id, qbl_type, properties, path))
        issues.extend(_check_nested_property_names(logical_id, qbl_type, properties, path))
        issues.extend(_check_unsupported_type(logical_id, qbl_type, path))
        issues.extend(_check_nested_enums(logical_id, qbl_type, properties, path))
        issues.extend(_check_schema_enums(logical_id, qbl_type, properties, path))
        issues.extend(_check_known_values(logical_id, qbl_type, properties, path))

        for key_type, prop, found_on in _unsupported_properties_present(
            logical_id, qbl_type, properties
        ):
            inert_properties.setdefault((key_type, prop), []).append(found_on)

        for prop, value in properties.items():
            prop_name = str(prop)

            domain = DOCUMENTED_ENUMS.get((qbl_type, prop_name))
            if domain and isinstance(value, str) and value not in domain:
                issues.append(_issue(
                    "VAL002", "error", logical_id, f"{path} > Properties > {prop_name}", qbl_type,
                    f"'{prop_name}' is '{value}', which is not one of {', '.join(domain)}",
                ))


            pattern = VALUE_PATTERNS.get((qbl_type, prop_name))
            if pattern and value is not None:
                suffixes, literals, rule = pattern
                text = value if isinstance(value, str) else str(value)
                if text.strip() not in literals and not text.rstrip().endswith(suffixes):
                    issues.append(_issue(
                        "VAL008", "error", logical_id,
                        f"{path} > Properties > {prop_name}", qbl_type,
                        f"'{prop_name}' is '{value}'; the platform requires that it {rule}",
                    ))

            if (
                isinstance(value, str)
                and value.startswith("$")
                and not tag_of(value)
                and _reference_only_property(spec, prop_name)
            ):
                issues.append(_issue(
                    "VAL001", "error", logical_id, f"{path} > Properties > {prop_name}", qbl_type,
                    f"'{prop_name}' is the bare logical ID '{value}'; this property takes a "
                    f"reference, so it needs a !Ref naming the resource",
                ))

    issues.extend(_summarize_unsupported_properties(inert_properties))
    return issues


def _check_document_version(qbl_data: Mapping[str, Any]) -> List[QBLIssue]:
    solution = qbl_data.get("Solution")
    if isinstance(solution, Mapping) and "Version" in solution:
        holder, version = "Solution.Version", solution["Version"]
    elif "Version" in qbl_data:
        holder, version = "Version", qbl_data["Version"]
    else:
        return []

    if not isinstance(version, str):
        return []

    return [_issue(
        "VAL003", "error", "", holder, "",
        f"`{holder}` is the string '{version}'; the platform requires a number here "
        f"and rejects the quoted form as a syntax error naming nothing",
    )]


PLATFORM_ACCEPTED_VERSIONS = ("0.7", "0.12", "0.14", "0.15")

PLATFORM_REJECTED_VERSIONS = ("0.1", "0.8", "0.9", "0.11", "0.13", "0.16")


def _normalized_version_text(version: Any) -> str:
    if isinstance(version, bool):
        return ""
    if isinstance(version, (int, float)):
        return f"{version:g}"
    return str(version).strip()


def _check_platform_version_support(qbl_data: Mapping[str, Any]) -> List[QBLIssue]:
    solution = qbl_data.get("Solution")
    if isinstance(solution, Mapping) and "Version" in solution:
        holder, version = "Solution.Version", solution["Version"]
    elif "Version" in qbl_data:
        holder, version = "Version", qbl_data["Version"]
    else:
        return []

    text = _normalized_version_text(version)
    if not text or text in PLATFORM_ACCEPTED_VERSIONS:
        return []

    if text in PLATFORM_REJECTED_VERSIONS:
        return [_issue(
            "VAL009", "error", "", holder, "",
            f"`{holder}` is {text}, which the platform refuses outright: "
            f"`Unparsed: Version {text} is not supported`. That costs the whole "
            f"document and names nothing to work back from. The accepted "
            f"versions are "
            f"{', '.join(PLATFORM_ACCEPTED_VERSIONS)}",
        )]

    return [_issue(
        "VAL009", "warning", "", holder, "",
        f"`{holder}` is {text}, which is not known to be accepted. Accepted "
        f"versions are {', '.join(PLATFORM_ACCEPTED_VERSIONS)}",
    )]


_CONFIRMED_VALUES_BY_TYPE: Dict[str, Dict[str, Tuple[str, ...]]] = {}
for (_confirmed_type, _confirmed_path), _confirmed in KNOWN_VALUES.items():
    _CONFIRMED_VALUES_BY_TYPE.setdefault(_confirmed_type, {})[_confirmed_path] = _confirmed


def _check_known_values(
    logical_id: str, qbl_type: str, properties: Mapping[str, Any], path: str
) -> List[QBLIssue]:
    issues: List[QBLIssue] = []
    for dotted, confirmed in (_CONFIRMED_VALUES_BY_TYPE.get(qbl_type) or {}).items():
        found, value = _walk_path(properties, dotted)
        if not found or not isinstance(value, str) or value in confirmed:
            continue
        issues.append(_issue(
            "VAL007", "warning", logical_id,
            f"{path} > Properties > {dotted}", qbl_type,
            f"'{dotted}' is '{value}'. The platform enforces a closed domain "
            f"here, and the known accepted values are {', '.join(confirmed)}; "
            f"this value is not among them",
        ))
    return issues


def _walk_path(properties: Mapping[str, Any], dotted: str) -> Tuple[bool, Any]:
    node: Any = properties
    for part in dotted.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return False, None
        node = node[part]
    return True, node


def _check_nested_enums(
    logical_id: str, qbl_type: str, properties: Mapping[str, Any], path: str
) -> List[QBLIssue]:
    domains = DOCUMENTED_NESTED_ENUMS.get(qbl_type)
    if not domains:
        return []

    issues: List[QBLIssue] = []
    for dotted, permitted in domains.items():
        found, value = _walk_path(properties, dotted)
        if not found or not isinstance(value, str) or value in permitted:
            continue
        issues.append(_issue(
            "VAL002", "error", logical_id, f"{path} > Properties > {dotted}", qbl_type,
            f"'{dotted}' is '{value}', which is not one of {', '.join(permitted)}",
        ))
    return issues


_SCHEMA_ENUMS_BY_TYPE: Dict[str, Dict[str, Tuple[str, ...]]] = {}
for (_enum_type, _enum_path), _enum_values in SCHEMA_ENUMS.items():
    _SCHEMA_ENUMS_BY_TYPE.setdefault(_enum_type, {})[_enum_path] = _enum_values


def _check_schema_enums(
    logical_id: str, qbl_type: str, properties: Mapping[str, Any], path: str
) -> List[QBLIssue]:
    domains = _SCHEMA_ENUMS_BY_TYPE.get(qbl_type)
    if not domains:
        return []

    issues: List[QBLIssue] = []
    for dotted, permitted in domains.items():
        if (qbl_type, dotted) in DOCUMENTED_ENUMS:
            continue
        if dotted in (DOCUMENTED_NESTED_ENUMS.get(qbl_type) or {}):
            continue
        found, value = _walk_path(properties, dotted)
        if not found or not isinstance(value, str) or value in permitted:
            continue
        shown = ", ".join(permitted[:8]) + (", ..." if len(permitted) > 8 else "")
        issues.append(_issue(
            "VAL010", "error", logical_id, f"{path} > Properties > {dotted}", qbl_type,
            f"'{dotted}' is '{value}', which is not one of {shown}",
        ))
    return issues


def _check_unsupported_type(logical_id: str, qbl_type: str, path: str) -> List[QBLIssue]:
    reason = UNSUPPORTED_TYPES.get(qbl_type)
    if not reason:
        return []
    return [_issue(
        "VAL006", "warning", logical_id, path, qbl_type,
        f"'{qbl_type}' is not supported by QBL: {reason}",
    )]


def _unsupported_properties_present(
    logical_id: str, qbl_type: str, properties: Mapping[str, Any]
) -> Iterator[Tuple[str, str, str]]:
    for prop in UNSUPPORTED_PROPERTIES.get(qbl_type, {}):
        if prop in properties:
            yield qbl_type, prop, logical_id


def _summarize_unsupported_properties(
    found: Mapping[Tuple[str, str], List[str]]
) -> List[QBLIssue]:
    issues: List[QBLIssue] = []
    for (qbl_type, prop), logical_ids in sorted(found.items()):
        reason = UNSUPPORTED_PROPERTIES[qbl_type][prop]
        count = len(logical_ids)
        nodes = f"{count} {qbl_type} node{'s' if count != 1 else ''}"
        issues.append(_issue(
            "VAL006", "warning", "", f"{qbl_type} > Properties > {prop}", qbl_type,
            f"'{prop}' is not supported by QBL: {reason}; carried by {nodes}, "
            f"starting with {logical_ids[0]}",
        ))
    return issues


def _check_nested_property_names(
    logical_id: str, qbl_type: str, properties: Mapping[str, Any], path: str
) -> List[QBLIssue]:
    documented_by_path = NESTED_DOCUMENTED_PROPERTIES.get(qbl_type)
    if not documented_by_path:
        return []

    issues: List[QBLIssue] = []
    for dotted, permitted in documented_by_path.items():
        found, value = _walk_path(properties, dotted)
        if not found or not isinstance(value, Mapping):
            continue
        for name in value:
            if str(name) in permitted:
                continue
            issues.append(_issue(
                "VAL005", "warning", logical_id,
                f"{path} > Properties > {dotted} > {name}", qbl_type,
                f"'{name}' is not a documented property of '{dotted}'; "
                f"the documented ones are {', '.join(permitted)}",
            ))
    return issues


def _check_nested_kinds(
    logical_id: str, qbl_type: str, properties: Mapping[str, Any], path: str
) -> List[QBLIssue]:
    expected_by_path = NESTED_KINDS.get(qbl_type)
    if not expected_by_path:
        return []

    issues: List[QBLIssue] = []
    for dotted, expected in expected_by_path.items():
        found, value = _walk_path(properties, dotted)
        if not found or value is None:
            continue
        actual = classify(value)
        if actual != expected:
            issues.append(_issue(
                "VAL004", "error", logical_id, f"{path} > Properties > {dotted}", qbl_type,
                f"'{dotted}' is a {actual}; the platform requires a {expected} here",
            ))
    return issues
