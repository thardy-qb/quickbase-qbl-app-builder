from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence, Tuple

CROSS_REFERENCE_SOURCES: Tuple[Tuple[str, str, str], ...] = (
    ("field_pipeline_matrix", "Field Logical ID", "Used in Pipelines"),
    ("custom_email_field_matrix", "Field Logical ID", "Used in Custom Emails"),
    ("connected_table_fields", "Table Field Logical ID", "Used in Connected Tables"),
)

CROSS_REFERENCE_CATEGORIES: Tuple[str, ...] = tuple(
    category for _, _, category in CROSS_REFERENCE_SOURCES
)

ANALYZER_CATEGORIES: Tuple[str, ...] = (
    "Used in Reports",
    "Used in Report Dynamic Filters",
    "Used in Forms",
    "Used in Form Rules",
    "Used in Custom Data Rules",
    "Referenced in Formulas",
    "Used in Relationships",
    "Used in Dashboards",
    "Used in Charts",
    "Used in Field Properties",
    "Used in Permissions",
    "Cross-App References",
)

ALL_USAGE_CATEGORIES: Tuple[str, ...] = ANALYZER_CATEGORIES + CROSS_REFERENCE_CATEGORIES


def _rows(parsed_data: Mapping[str, Any], name: str) -> List[Dict[str, Any]]:
    value = parsed_data.get(name)
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _is_yes(value: Any) -> bool:
    return _text(value).casefold() in ("yes", "true")


def collect_cross_references(parsed_data: Mapping[str, Any]) -> Dict[str, Dict[str, int]]:
    counts: Dict[str, Dict[str, int]] = {}
    for collection, column, category in CROSS_REFERENCE_SOURCES:
        for row in _rows(parsed_data, collection):
            logical_id = _text(row.get(column))
            if not logical_id:
                continue
            counts.setdefault(logical_id, {})
            counts[logical_id][category] = counts[logical_id].get(category, 0) + 1
    return counts


def apply_cross_reference_usage(parsed_data: Dict[str, Any]) -> Dict[str, Any]:
    field_rows = _rows(parsed_data, "fields")
    if not field_rows:
        return parsed_data

    reference_counts = collect_cross_references(parsed_data)

    for row in field_rows:
        logical_id = _text(row.get("Field Logical ID"))
        found = reference_counts.get(logical_id, {})

        extra_references = 0
        for category in CROSS_REFERENCE_CATEGORIES:
            hits = int(found.get(category, 0))
            row[category] = "Yes" if (hits or _is_yes(row.get(category))) else "No"
            extra_references += hits

        try:
            previous_total = int(_text(row.get("Total Usage Count")) or 0)
        except ValueError:
            previous_total = 0
        total_references = previous_total + extra_references
        row["Total Usage Count"] = total_references

        row["Total Usage Categories"] = sum(
            1 for category in ALL_USAGE_CATEGORIES if _is_yes(row.get(category))
        )

        try:
            field_id = int(_text(row.get("Field ID")) or 0)
        except ValueError:
            field_id = 0
        is_builtin = 1 <= field_id <= 5
        row["Potentially Unused"] = "No" if (total_references or is_builtin) else "Yes"

    return parsed_data
