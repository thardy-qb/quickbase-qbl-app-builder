from __future__ import annotations

import re
from typing import Any, Dict, Iterator, List, Mapping, Set, Tuple

from qblparser.contracts import QBLIssue

TOKEN = re.compile(r"\[([^\]\[]*)\]")

FORMULA_PROPERTIES = ("Formula", "ColorFormula", "CustomAccessCriteria", "Query")

TABLE_ALIAS_PREFIX = "_DBID_"
FIELD_ID_PREFIX = "_fid_"

BUILTIN_TOKENS = frozenset({"_APP_ID_"})

AGGREGATE_CONTAINERS = ("SummaryVariables", "Columns")

LABELLED_CONTAINERS = ("SummaryFormulas", "ReportFormulas")

SUMMARIZE_SUFFIXES = {
    "Total": "tot",
    "Average": "avg",
    "Maximum": "max",
    "Minimum": "min",
}

AGGREGATE_SHAPE = re.compile(r"^(?P<label>.+?) \((?P<suffix>[^()\[\]]+)\)$")


def _issue(code: str, logical_id: str, path: str, qbl_type: str, problem: str) -> QBLIssue:
    return {
        "LogicalID": logical_id,
        "Path": path,
        "Type": qbl_type,
        "Problem": problem,
        "Code": code,
        "Severity": "warning",
    }


def _field_labels(table: Mapping[str, Any]) -> Set[str]:
    labels = set()
    fields = table.get("Fields")
    if not isinstance(fields, Mapping):
        return labels
    for field in fields.values():
        if not isinstance(field, Mapping):
            continue
        properties = field.get("Properties")
        if not isinstance(properties, Mapping):
            continue
        label = properties.get("Label")
        if isinstance(label, str) and label.strip():
            labels.add(label.strip())
    return labels


def _field_labels_by_id(table: Mapping[str, Any]) -> Dict[str, str]:
    by_id: Dict[str, str] = {}
    fields = table.get("Fields")
    if not isinstance(fields, Mapping):
        return by_id
    for key, field in fields.items():
        if not isinstance(field, Mapping):
            continue
        properties = field.get("Properties")
        if not isinstance(properties, Mapping):
            continue
        label = properties.get("Label")
        if isinstance(label, str) and label.strip():
            by_id[str(key)] = label.strip()
    return by_id


def _source_field_label(properties: Mapping[str, Any], by_id: Mapping[str, str]) -> str:
    source = properties.get("Source")
    if not isinstance(source, Mapping):
        return ""
    target = source.get("Field")
    if not isinstance(target, str):
        return ""
    return by_id.get(target.strip(), "")


def _derived_labels(node: Mapping[str, Any], by_id: Mapping[str, str]) -> Tuple[Set[str], Set[str]]:
    exact: Set[str] = set()
    unmapped: Set[str] = set()

    for container in AGGREGATE_CONTAINERS:
        members = node.get(container)
        if not isinstance(members, Mapping):
            continue
        for member in members.values():
            if not isinstance(member, Mapping):
                continue
            properties = member.get("Properties")
            if not isinstance(properties, Mapping):
                continue
            label = _source_field_label(properties, by_id)
            if not label:
                continue
            summarize_by = properties.get("SummarizeBy")
            if not isinstance(summarize_by, str):
                continue
            suffix = SUMMARIZE_SUFFIXES.get(summarize_by.strip())
            if suffix:
                exact.add(f"{label} ({suffix})")
            else:
                unmapped.add(label)

    for container in LABELLED_CONTAINERS:
        members = node.get(container)
        if not isinstance(members, Mapping):
            continue
        for member in members.values():
            if not isinstance(member, Mapping):
                continue
            properties = member.get("Properties")
            if not isinstance(properties, Mapping):
                continue
            label = properties.get("Label")
            if isinstance(label, str) and label.strip():
                exact.add(label.strip())

    return exact, unmapped


def _is_unmapped_aggregate(token: str, unmapped: Set[str]) -> bool:
    if not unmapped:
        return False
    match = AGGREGATE_SHAPE.match(token)
    return bool(match) and match.group("label") in unmapped


def _table_aliases(app: Mapping[str, Any]) -> Set[str]:
    aliases = set()
    tables = app.get("Tables")
    if not isinstance(tables, Mapping):
        return aliases
    for table in tables.values():
        if not isinstance(table, Mapping):
            continue
        properties = table.get("Properties")
        if not isinstance(properties, Mapping):
            continue
        alias = properties.get("AliasHint")
        if isinstance(alias, str) and alias.strip():
            aliases.add(alias.strip())
    return aliases


def _formula_holders(
    node: Any,
    path: str,
    logical_id: str,
    by_id: Mapping[str, str],
    exact: Set[str],
    unmapped: Set[str],
) -> Iterator[Tuple[str, str, str, str, str, Set[str], Set[str]]]:
    if isinstance(node, Mapping):
        qbl_type = str(node.get("Type", ""))
        node_exact, node_unmapped = _derived_labels(node, by_id)
        if node_exact or node_unmapped:
            exact = exact | node_exact
            unmapped = unmapped | node_unmapped

        properties = node.get("Properties")
        if isinstance(properties, Mapping):
            for prop in FORMULA_PROPERTIES:
                value = properties.get(prop)
                if isinstance(value, str) and value.strip():
                    yield (
                        logical_id,
                        f"{path} > Properties > {prop}",
                        qbl_type,
                        prop,
                        value,
                        exact,
                        unmapped,
                    )
        for key, child in node.items():
            if key == "Properties":
                continue
            child_id = key if isinstance(key, str) and key.startswith("$") else logical_id
            yield from _formula_holders(
                child, f"{path} > {key}", child_id, by_id, exact, unmapped
            )
    elif isinstance(node, list):
        for index, child in enumerate(node):
            yield from _formula_holders(
                child, f"{path}[{index}]", logical_id, by_id, exact, unmapped
            )


def validate_qbl_formulas(qbl_data: Any) -> List[QBLIssue]:
    if not isinstance(qbl_data, Mapping):
        return []

    resources = qbl_data.get("Resources")
    if not isinstance(resources, Mapping):
        return []

    issues: List[QBLIssue] = []

    for app_key, app in resources.items():
        if not isinstance(app, Mapping):
            continue
        aliases = _table_aliases(app)
        tables = app.get("Tables")
        if not isinstance(tables, Mapping):
            continue

        for table_key, table in tables.items():
            if not isinstance(table, Mapping):
                continue
            labels = _field_labels(table)
            by_id = _field_labels_by_id(table)
            base = f"{app_key} > Tables > {table_key}"

            for (logical_id, path, qbl_type, prop, formula,
                 derived, unmapped) in _formula_holders(
                table, base, table_key, by_id, frozenset(), frozenset()
            ):
                seen: Dict[str, bool] = {}
                for raw in TOKEN.findall(formula):
                    token = raw.strip()
                    if not token or token in seen:
                        continue
                    seen[token] = True

                    if token in BUILTIN_TOKENS or token.startswith(FIELD_ID_PREFIX):
                        continue

                    if token.startswith(TABLE_ALIAS_PREFIX):
                        if token not in aliases:
                            issues.append(_issue(
                                "FML002", logical_id, path, qbl_type,
                                f"'{prop}' names the table alias [{token}], which no "
                                f"table in this application declares as an AliasHint",
                            ))
                        continue

                    if (token not in labels
                            and token not in derived
                            and not _is_unmapped_aggregate(token, unmapped)):
                        issues.append(_issue(
                            "FML001", logical_id, path, qbl_type,
                            f"'{prop}' names the field [{token}], which '{table_key}' "
                            f"does not declare. A formula addresses fields by label, so "
                            f"nothing else in this document connects the two and the "
                            f"platform does not read formula bodies at all",
                        ))

    return issues
