from qblparser.utils.helpers import TableResolver, FieldExtractor
from qblparser.utils.property_extractor import PropertyExtractor
from typing import List, Dict, Any, Set, Tuple
import re

FORMULA_QUERY_FUNCTIONS = [
    "GetRecord",
    "GetRecordByUniqueField",
    "GetRecords",
    "GetFieldValues",
    "SumValues",
    "Size"
]
FORMULA_QUERY_PATTERN = re.compile(
    r"\b(?:GetRecord|GetRecordByUniqueField|GetRecords|GetFieldValues|SumValues|Size)\s*\(",
    re.IGNORECASE
)
CURRENT_DATE_FUNCTION_PATTERN = re.compile(
    r"\b(?:Today|Now|CurrentDate|CurrentTimestamp)\s*\(",
    re.IGNORECASE
)
RECORD_ID_REFERENCE_PATTERN = re.compile(r"\[\s*Record ID#?\s*\]", re.IGNORECASE)
SUMMARY_QUERY_FIELD_ID_PATTERN = re.compile(r"\{\s*'?(?P<field_id>\d+)'?\s*\.")
LIMITED_VIEW_PERMISSION_KEYS = ("CanView", "CanViewTable", "CanViewRecords")

_REPORTED_FIELD_PROPERTIES = frozenset({
    "Label", "HelpText", "Comments", "Formula", "AllowedInReports",
    "AllowCreateChoices", "ChoiceOrder", "IsSearchable", "IsRequired",
    "IsUnique", "IsAuditable", "RolePermissions", "Lookup", "Summary",
    "Reference", "ListChoices",
})


def _unreported_properties(field_value):
    properties = field_value.get("Properties") if isinstance(field_value, dict) else None
    if not isinstance(properties, dict):
        return {}
    return {
        name: value for name, value in properties.items()
        if name not in _REPORTED_FIELD_PROPERTIES
    }


def parse_field_metadata(table_name, fields, table_key, table_schema, app_key, app_value, identifier_index=None, qbl_resources=None):
    table_info = TableResolver.resolve_from_logical_id(table_key, identifier_index, table_schema, app_key)
    table_id = table_info.get("table_id", "")

    field_entries = []
    label_lookup = {}
    for field_key, field_value in fields.items():
        props = PropertyExtractor(field_value)
        label = props.label(field_key)
        norm_label = _normalize_label(label)
        label_lookup.setdefault(norm_label, []).append(field_key)
        field_entries.append((field_key, field_value, props))

    field_caching_context = {
        "current_app_key": app_key or "",
        "current_table_key": table_key or "",
        "current_app_value": app_value if isinstance(app_value, dict) else {},
        "qbl_resources": qbl_resources if isinstance(qbl_resources, dict) else {},
        "identifier_index": identifier_index,
        "table_schema": table_schema,
        "table_cache": {},
        "constraint_cache": {},
    }

    field_metadata = []
    metadata_by_field = {}
    fields_used_in_queries = set()

    for field_key, field_value, props in field_entries:
        field_id_raw = props.id()
        field_type = props.type()
        formula = props.formula() or ""
        is_formula_query = _is_formula_query_field(field_type, formula)
        referenced_fields = set()
        if is_formula_query:
            referenced_fields = _extract_formula_query_references(formula, label_lookup)
            fields_used_in_queries.update(referenced_fields)
        
        allow_create_choices, choice_order = _extract_choice_properties(props, field_type)

        base_metadata = {
            "App Logical ID": app_key or "",
            "Table Logical ID": table_key or "",
            "Table ID": table_id,
            "Table Name": table_name,
            "Field Logical ID": field_key,
            "Field ID": field_id_raw,
            "Field Label": props.label(),
            "Field Type": field_type.split("::")[-1] if field_type else "",
            "Field Help": props.help_text(),
            "Comments": props.comments(),
            "Formula": props.formula(),
            "Allowed in Reports": props.allowed_in_reports(),
            "AllowCreateChoices": allow_create_choices,
            "ChoiceOrder": choice_order,
            "Is Searchable": props.is_searchable(),
            "Is Required": props.is_required(),
            "Is Unique": props.is_unique(),
            "Is Auditable": props.is_auditable(),
            "Is Formula Query": "Yes" if is_formula_query else "No",
            "Other Properties": _unreported_properties(field_value),
        }
        
        lookup_metadata = _extract_lookup_metadata(
            props,
            field_type,
            identifier_index=identifier_index,
            table_schema=table_schema,
            app_key=app_key,
            table_key=table_key,
            app_value=app_value,
            qbl_resources=qbl_resources,
        )
        base_metadata.update(lookup_metadata)
        
        summary_metadata = _extract_summary_metadata(
            props,
            field_type,
            identifier_index=identifier_index,
            table_schema=table_schema,
            app_key=app_key,
            table_key=table_key,
            app_value=app_value,
            qbl_resources=qbl_resources,
        )
        base_metadata.update(summary_metadata)
        base_metadata["Field Caching Eligible"] = _field_caching_eligibility_label(field_key, field_caching_context)
        
        field_metadata.append(base_metadata)
        metadata_by_field[field_key] = base_metadata

    for field_key, metadata in metadata_by_field.items():
        metadata["Is Used In Formula Query"] = "Yes" if field_key in fields_used_in_queries else "No"
    
    return field_metadata


def _extract_choice_properties(props, field_type):
    input_options = props.get("InputOptions", {})
    if not isinstance(input_options, dict):
        return "", ""

    if "AllowCreateChoices" not in input_options:
        return "", ""

    return input_options.get("AllowCreateChoices", ""), input_options.get("ChoiceOrder", "")


def _extract_lookup_metadata(props, field_type, identifier_index=None, table_schema=None, app_key="",
                             table_key="", app_value=None, qbl_resources=None):
    lookup_data = {
        "Lookup Relationship": "",
        "Lookup Target Table": "",
        "Lookup Target Table ID": "",
        "Lookup Target Field": "",
        "Lookup Target Field ID": "",
        "Lookup Display As Link": "",
        "Lookup Display Type": "",
    }
    
    if field_type == "QB::Field::Lookup":
        lookup_config = props.safe_get("Lookup", default={})
        
        if isinstance(lookup_config, dict):
            relationship_ref = lookup_config.get("Relationship", {})
            if isinstance(relationship_ref, dict):
                lookup_data["Lookup Relationship"] = relationship_ref.get("Relationship", "")
            
            target_field_ref = lookup_config.get("TargetField", {})
            if isinstance(target_field_ref, dict):
                target_table_logical = target_field_ref.get("Table", "")
                target_field_logical = target_field_ref.get("Field", "")
                relationship_logical = ""
                if isinstance(relationship_ref, dict):
                    relationship_logical = relationship_ref.get("Relationship", "")
                
                lookup_data["Lookup Target Table"] = target_table_logical
                lookup_data["Lookup Target Field"] = target_field_logical
                target_app_logical = _resolve_target_app_logical_id(
                    relationship_logical=relationship_logical,
                    target_table_logical=target_table_logical,
                    app_key=app_key,
                    table_key=table_key,
                    app_value=app_value,
                    identifier_index=identifier_index,
                    qbl_resources=qbl_resources,
                )
                
                if target_table_logical and identifier_index and table_schema:
                    target_table_info = TableResolver.resolve_from_logical_id(
                        target_table_logical, identifier_index, table_schema, target_app_logical
                    )
                    lookup_data["Lookup Target Table ID"] = target_table_info.get("table_id", "")
                
                if target_field_logical and target_table_logical and identifier_index:
                    target_field_id = TableResolver.resolve_field_id(
                        target_table_logical, target_field_logical, identifier_index, target_app_logical
                    )
                    lookup_data["Lookup Target Field ID"] = target_field_id or ""
            
            lookup_data["Lookup Display As Link"] = lookup_config.get("DisplayAsLinkToParent", "")
            lookup_data["Lookup Display Type"] = lookup_config.get("DisplayType", "")
    
    return lookup_data


def _relationship_of_reference_field(table_logical, field_logical, app_key,
                                    app_value=None, qbl_resources=None):
    if not table_logical or not field_logical:
        return ""

    tables = {}
    if isinstance(app_value, dict):
        tables = app_value.get("Tables", {}) or {}
    if table_logical not in tables and isinstance(qbl_resources, dict):
        for candidate_app in (qbl_resources.get("Resources", {}) or {}).values():
            if not isinstance(candidate_app, dict):
                continue
            candidate_tables = candidate_app.get("Tables", {}) or {}
            if table_logical in candidate_tables:
                tables = candidate_tables
                break

    field_node = (tables.get(table_logical) or {}).get("Fields", {}).get(field_logical, {})
    if not isinstance(field_node, dict):
        return ""

    reference = PropertyExtractor(field_node).safe_get("Reference", default={})
    if not isinstance(reference, dict):
        return ""
    relationship_ref = reference.get("Relationship", {})
    if isinstance(relationship_ref, dict):
        return relationship_ref.get("Relationship", "") or ""
    if isinstance(relationship_ref, str):
        return relationship_ref
    return ""


def _extract_summary_metadata(props, field_type, identifier_index=None, table_schema=None, app_key="",
                              table_key="", app_value=None, qbl_resources=None):
    summary_data = {
        "Summary Relationship": "",
        "Summary Target Table": "",
        "Summary Target Table ID": "",
        "Summary Target Field": "",
        "Summary Target Field ID": "",
        "Summary Accumulation Type": "",
        "Summary Formula": "",
        "Field Caching Enabled": "",
    }

    if field_type == "QB::Field::Summary":
        summary_config = props.safe_get("Summary", default={})

        if isinstance(summary_config, dict):
            reference_ref = summary_config.get("ReferenceField", {})
            child_table_logical = ""
            reference_field_logical = ""
            if isinstance(reference_ref, dict):
                child_table_logical = reference_ref.get("Table", "") or ""
                reference_field_logical = reference_ref.get("Field", "") or ""

            relationship_ref = summary_config.get("Relationship", {})
            relationship_logical = ""
            if isinstance(relationship_ref, dict):
                relationship_logical = relationship_ref.get("Relationship", "") or ""
            if not relationship_logical:
                relationship_logical = _relationship_of_reference_field(
                    child_table_logical, reference_field_logical, app_key,
                    app_value=app_value, qbl_resources=qbl_resources,
                )

            summarize_ref = summary_config.get("FieldToSummarize", {})
            if not isinstance(summarize_ref, dict):
                summarize_ref = {}
            legacy_target = summary_config.get("TargetField", {})
            if not isinstance(legacy_target, dict):
                legacy_target = {}

            target_field_logical = (
                summarize_ref.get("Field", "") or legacy_target.get("Field", "") or ""
            )
            target_table_logical = (
                summarize_ref.get("Table", "")
                or legacy_target.get("Table", "")
                or child_table_logical
            )

            summary_data["Summary Relationship"] = relationship_logical
            summary_data["Summary Target Table"] = target_table_logical
            summary_data["Summary Target Field"] = target_field_logical

            target_app_logical = _resolve_target_app_logical_id(
                relationship_logical=relationship_logical,
                target_table_logical=target_table_logical,
                app_key=app_key,
                table_key=table_key,
                app_value=app_value,
                identifier_index=identifier_index,
                qbl_resources=qbl_resources,
            )

            if target_table_logical and identifier_index and table_schema:
                target_table_info = TableResolver.resolve_from_logical_id(
                    target_table_logical, identifier_index, table_schema, target_app_logical
                )
                summary_data["Summary Target Table ID"] = target_table_info.get("table_id", "")

            if target_field_logical and target_table_logical and identifier_index:
                target_field_id = TableResolver.resolve_field_id(
                    target_table_logical, target_field_logical, identifier_index, target_app_logical
                )
                summary_data["Summary Target Field ID"] = target_field_id or ""

            summary_data["Summary Accumulation Type"] = (
                summary_config.get("Function", "")
                or summary_config.get("AccumulationType", "")
                or ""
            )
            summary_data["Summary Formula"] = (
                summary_config.get("Formula", "") or summary_config.get("Query", "") or ""
            )

        cache_value = ""
        if isinstance(summary_config, dict) and "EvaluateOnlyOnChange" in summary_config:
            cache_value = summary_config.get("EvaluateOnlyOnChange", "")
        elif props.get("EvaluateOnlyOnChange", "") != "":
            cache_value = props.get("EvaluateOnlyOnChange", "")
        if isinstance(cache_value, bool):
            summary_data["Field Caching Enabled"] = "Yes" if cache_value else "No"
        elif cache_value != "":
            summary_data["Field Caching Enabled"] = cache_value
        else:
            summary_data["Field Caching Enabled"] = "No"

    return summary_data


def _normalize_label(label: str) -> str:
    if isinstance(label, str):
        return label.strip().lower()
    return ""


def _field_caching_eligibility_label(field_key: str, context: Dict[str, Any]) -> str:
    eligible = _is_field_caching_eligible(
        (
            context.get("current_app_key", ""),
            context.get("current_table_key", ""),
            field_key or "",
        ),
        context,
    )
    return "Yes" if eligible else "No"


def _is_field_caching_eligible(field_ref: Tuple[str, str, str], context: Dict[str, Any]) -> bool:
    app_logical, table_logical, field_logical = field_ref
    table_context = _get_table_field_context(context, app_logical, table_logical)
    field_info = table_context.get("fields", {}).get(field_logical)
    if not field_info:
        return False

    field_type = field_info.get("field_type", "")
    if field_type == "QB::Field::Summary":
        constraints = _analyze_field_caching_constraints(field_ref, context)
        return not constraints["has_custom_permissions"] and not constraints["table_has_limited_view"]

    if "::Formula" not in field_type:
        return False

    constraints = _analyze_field_caching_constraints(field_ref, context)
    return (
        not constraints["has_custom_permissions"]
        and not constraints["table_has_limited_view"]
        and not constraints["references_current_date"]
        and not constraints["references_record_id"]
        and not constraints["references_formula_query"]
    )


def _analyze_field_caching_constraints(field_ref: Tuple[str, str, str], context: Dict[str, Any]) -> Dict[str, bool]:
    constraint_cache = context.setdefault("constraint_cache", {})
    if field_ref in constraint_cache:
        return constraint_cache[field_ref]

    visiting = context.setdefault("constraint_visiting", set())
    if field_ref in visiting:
        return _empty_field_caching_constraints()

    visiting.add(field_ref)

    app_logical, table_logical, field_logical = field_ref
    table_context = _get_table_field_context(context, app_logical, table_logical)
    field_info = table_context.get("fields", {}).get(field_logical)
    if not field_info:
        visiting.discard(field_ref)
        return _empty_field_caching_constraints()

    constraints = {
        "has_custom_permissions": bool(field_info.get("has_custom_permissions")) or bool(table_context.get("has_custom_permissions")),
        "table_has_limited_view": bool(table_context.get("has_limited_view")),
        "references_current_date": _field_references_current_date(field_info),
        "references_record_id": _field_references_record_id(field_info),
        "references_formula_query": bool(field_info.get("is_formula_query")),
    }

    for dependency in _get_field_caching_dependencies(field_ref, field_info, table_context, context):
        dep_constraints = _analyze_field_caching_constraints(dependency, context)
        for key in constraints:
            constraints[key] = constraints[key] or dep_constraints[key]

    visiting.discard(field_ref)
    constraint_cache[field_ref] = constraints
    return constraints


def _empty_field_caching_constraints() -> Dict[str, bool]:
    return {
        "has_custom_permissions": False,
        "table_has_limited_view": False,
        "references_current_date": False,
        "references_record_id": False,
        "references_formula_query": False,
    }


def _get_table_field_context(context: Dict[str, Any], app_logical: str, table_logical: str) -> Dict[str, Any]:
    cache_key = (app_logical or "", table_logical or "")
    table_cache = context.setdefault("table_cache", {})
    if cache_key in table_cache:
        return table_cache[cache_key]

    app_value = _get_app_value_for_logical(context, app_logical)
    table_value = {}
    if isinstance(app_value, dict):
        table_value = app_value.get("Tables", {}).get(table_logical, {})

    field_context = _build_table_field_context(app_logical, table_logical, table_value)
    table_cache[cache_key] = field_context
    return field_context


def _get_app_value_for_logical(context: Dict[str, Any], app_logical: str) -> Dict[str, Any]:
    current_app_key = context.get("current_app_key", "")
    if app_logical == current_app_key:
        return context.get("current_app_value", {})
    return (
        context.get("qbl_resources", {})
        .get("Resources", {})
        .get(app_logical, {})
    )


def _build_table_field_context(app_logical: str, table_logical: str, table_value: Dict[str, Any]) -> Dict[str, Any]:
    label_lookup = {}
    field_key_by_id = {}
    fields_by_key = {}
    fields = table_value.get("Fields", {}) if isinstance(table_value, dict) else {}

    for field_key, field_value in fields.items():
        if not isinstance(field_value, dict):
            continue

        props = PropertyExtractor(field_value)
        label = props.label()
        norm_label = _normalize_label(label)
        if norm_label:
            label_lookup.setdefault(norm_label, []).append(field_key)

        field_type = props.type()
        field_id = str(props.id(default="") or "").strip()
        if field_id:
            field_key_by_id[field_id] = field_key
        fields_by_key[field_key] = {
            "field_key": field_key,
            "field_type": field_type,
            "formula": props.formula() or "",
            "summary_formula": _extract_summary_formula(props),
            "summary_query": _extract_summary_query(props),
            "lookup_config": props.safe_get("Lookup", default={}),
            "summary_config": props.safe_get("Summary", default={}),
            "has_custom_permissions": _field_has_custom_permissions(props),
            "is_formula_query": _is_formula_query_field(field_type, props.formula() or ""),
            "is_record_id": field_type == "QB::Field::RecordId",
        }

    return {
        "app_logical": app_logical or "",
        "table_logical": table_logical or "",
        "label_lookup": label_lookup,
        "field_key_by_id": field_key_by_id,
        "fields": fields_by_key,
        "has_limited_view": _table_has_limited_view_permissions(table_value),
        "has_custom_permissions": False,
    }


def _extract_summary_formula(props: PropertyExtractor) -> str:
    summary_config = props.safe_get("Summary", default={})
    if not isinstance(summary_config, dict):
        return ""
    return str(summary_config.get("Formula", "") or "")


def _extract_summary_query(props: PropertyExtractor) -> str:
    summary_config = props.safe_get("Summary", default={})
    if not isinstance(summary_config, dict):
        return ""
    return str(summary_config.get("Query", "") or "")


def _field_has_custom_permissions(props: PropertyExtractor) -> bool:
    role_permissions = props.get("RolePermissions", {})
    if isinstance(role_permissions, dict):
        return bool(role_permissions)
    return bool(role_permissions)


def _table_has_limited_view_permissions(table_value: Dict[str, Any]) -> bool:
    if not isinstance(table_value, dict):
        return False

    table_props = PropertyExtractor(table_value)
    role_permissions = table_props.get("RolePermissions", {})
    if not isinstance(role_permissions, dict):
        return False

    for permissions in role_permissions.values():
        if not isinstance(permissions, dict):
            continue
        for permission_key in LIMITED_VIEW_PERMISSION_KEYS:
            permission_value = permissions.get(permission_key)
            if _permission_has_limited_view(permission_value):
                return True
    return False


def _permission_has_limited_view(permission_value: Any) -> bool:
    if not isinstance(permission_value, dict):
        return False

    when_value = str(permission_value.get("When", "") or "").strip().lower()
    criteria_value = str(permission_value.get("CustomAccessCriteria", "") or "").strip()
    if criteria_value:
        return True
    if when_value and when_value not in ("", "always", "everyone", "all"):
        return True
    return False


def _field_references_current_date(field_info: Dict[str, Any]) -> bool:
    for formula in (field_info.get("formula", ""), field_info.get("summary_formula", "")):
        if isinstance(formula, str) and CURRENT_DATE_FUNCTION_PATTERN.search(formula):
            return True
    return False


def _field_references_record_id(field_info: Dict[str, Any]) -> bool:
    if field_info.get("is_record_id"):
        return True

    for formula in (field_info.get("formula", ""), field_info.get("summary_formula", "")):
        if isinstance(formula, str) and RECORD_ID_REFERENCE_PATTERN.search(formula):
            return True
    return False


def _get_field_caching_dependencies(field_ref: Tuple[str, str, str], field_info: Dict[str, Any],
                                    table_context: Dict[str, Any], context: Dict[str, Any]) -> Set[Tuple[str, str, str]]:
    dependencies = set()
    app_logical, table_logical, _ = field_ref
    field_type = field_info.get("field_type", "")

    if "::Formula" in field_type:
        dependencies.update(_extract_scoped_formula_dependencies(
            field_info.get("formula", ""),
            table_context,
        ))

    if field_type == "QB::Field::Lookup":
        lookup_ref = _extract_lookup_target_field_reference(
            lookup_config=field_info.get("lookup_config", {}),
            app_logical=app_logical,
            table_logical=table_logical,
            current_app_value=_get_app_value_for_logical(context, app_logical),
            current_app_key=context.get("current_app_key", ""),
            identifier_index=context.get("identifier_index"),
            table_schema=context.get("table_schema"),
            qbl_resources=context.get("qbl_resources"),
        )
        if lookup_ref:
            dependencies.add(lookup_ref)

    if field_type == "QB::Field::Summary":
        summary_ref = _extract_summary_target_field_reference(
            summary_config=field_info.get("summary_config", {}),
            app_logical=app_logical,
            table_logical=table_logical,
            current_app_value=_get_app_value_for_logical(context, app_logical),
            current_app_key=context.get("current_app_key", ""),
            identifier_index=context.get("identifier_index"),
            table_schema=context.get("table_schema"),
            qbl_resources=context.get("qbl_resources"),
        )
        if summary_ref:
            dependencies.add(summary_ref)
            target_table_context = _get_table_field_context(context, summary_ref[0], summary_ref[1])
        else:
            target_table_context = table_context

        dependencies.update(_extract_scoped_summary_query_dependencies(
            field_info.get("summary_query", ""),
            target_table_context,
        ))

        dependencies.update(_extract_scoped_formula_dependencies(
            field_info.get("summary_formula", ""),
            target_table_context,
        ))

    return dependencies


def _extract_scoped_formula_dependencies(formula: str, table_context: Dict[str, Any]) -> Set[Tuple[str, str, str]]:
    dependencies = set()
    if not isinstance(formula, str) or not formula.strip():
        return dependencies

    label_lookup = table_context.get("label_lookup", {})
    app_logical = table_context.get("app_logical", "")
    table_logical = table_context.get("table_logical", "")
    fields = table_context.get("fields", {})

    for field_ref in FieldExtractor.from_formula(formula):
        if not isinstance(field_ref, str):
            continue
        if field_ref.startswith("$Field_"):
            if field_ref in fields:
                dependencies.add((app_logical, table_logical, field_ref))
            continue

        norm_label = _normalize_label(field_ref)
        for logical_id in label_lookup.get(norm_label, []):
            dependencies.add((app_logical, table_logical, logical_id))

    return dependencies


def _extract_scoped_summary_query_dependencies(query: str, table_context: Dict[str, Any]) -> Set[Tuple[str, str, str]]:
    dependencies = set()
    if not isinstance(query, str) or not query.strip():
        return dependencies

    field_key_by_id = table_context.get("field_key_by_id", {})
    fields = table_context.get("fields", {})
    app_logical = table_context.get("app_logical", "")
    table_logical = table_context.get("table_logical", "")

    for match in SUMMARY_QUERY_FIELD_ID_PATTERN.finditer(query):
        field_id = match.group("field_id")
        field_logical = field_key_by_id.get(field_id)
        if field_logical and field_logical in fields:
            dependencies.add((app_logical, table_logical, field_logical))

    return dependencies


def _extract_lookup_target_field_reference(lookup_config: Dict[str, Any], app_logical: str, table_logical: str,
                                           current_app_value: Dict[str, Any], current_app_key: str,
                                           identifier_index=None, table_schema=None, qbl_resources=None):
    if not isinstance(lookup_config, dict):
        return None

    target_field_ref = lookup_config.get("TargetField", {})
    if not isinstance(target_field_ref, dict):
        return None

    target_table_logical = str(target_field_ref.get("Table", "") or "")
    target_field_logical = str(target_field_ref.get("Field", "") or "")
    if not target_table_logical or not target_field_logical:
        return None

    relationship_logical = _extract_relationship_logical_id(lookup_config.get("Relationship", {}))
    target_app_logical = _resolve_target_app_logical_id(
        relationship_logical=relationship_logical,
        target_table_logical=target_table_logical,
        app_key=app_logical or current_app_key,
        table_key=table_logical,
        app_value=current_app_value,
        identifier_index=identifier_index,
        qbl_resources=qbl_resources,
    )
    return (target_app_logical or app_logical, target_table_logical, target_field_logical)


def _extract_summary_target_field_reference(summary_config: Dict[str, Any], app_logical: str, table_logical: str,
                                            current_app_value: Dict[str, Any], current_app_key: str,
                                            identifier_index=None, table_schema=None, qbl_resources=None):
    if not isinstance(summary_config, dict):
        return None

    relationship_logical = _extract_relationship_logical_id(summary_config.get("Relationship", {}))
    target_table_logical = ""
    target_field_logical = ""

    for ref_key in ("TargetField", "FieldToSummarize", "ReferenceField"):
        ref_value = summary_config.get(ref_key, {})
        if not isinstance(ref_value, dict):
            continue
        target_table_logical = str(ref_value.get("Table", "") or target_table_logical)
        target_field_logical = str(
            ref_value.get("Field", "") or ref_value.get("ReferenceField", "") or target_field_logical
        )
        if not relationship_logical:
            relationship_logical = _extract_relationship_logical_id(ref_value.get("Relationship", {}))
        if target_table_logical and target_field_logical:
            break

    if not target_table_logical or not target_field_logical:
        return None

    target_app_logical = _resolve_target_app_logical_id(
        relationship_logical=relationship_logical,
        target_table_logical=target_table_logical,
        app_key=app_logical or current_app_key,
        table_key=table_logical,
        app_value=current_app_value,
        identifier_index=identifier_index,
        qbl_resources=qbl_resources,
    )
    return (target_app_logical or app_logical, target_table_logical, target_field_logical)


def _extract_relationship_logical_id(relationship_ref: Any) -> str:
    if isinstance(relationship_ref, str):
        return relationship_ref
    if isinstance(relationship_ref, dict):
        return str(
            relationship_ref.get("Relationship", "")
            or relationship_ref.get("ReferenceField", "")
            or relationship_ref.get("Field", "")
            or ""
        )
    return ""


def _is_formula_query_field(field_type: str, formula) -> bool:
    if not isinstance(field_type, str):
        return False
    if "::Formula" not in field_type:
        return False

    if not isinstance(formula, str):
        return False
    formula = formula.strip()
    if not formula:
        return False

    return bool(FORMULA_QUERY_PATTERN.search(formula))


def _extract_formula_query_references(formula: str, label_lookup: Dict[str, List[str]]) -> set:
    references = set()
    if not formula:
        return references

    formula_refs = FieldExtractor.from_formula(formula)
    for ref in formula_refs:
        if not isinstance(ref, str):
            continue
        if ref.startswith("$Field_"):
            references.add(ref)
        else:
            norm = _normalize_label(ref)
            for field_key in label_lookup.get(norm, []):
                references.add(field_key)
    return references


def _resolve_target_app_logical_id(relationship_logical: str, target_table_logical: str, app_key: str,
                                   table_key: str, app_value: Dict[str, Any], identifier_index=None,
                                   qbl_resources: Dict[str, Any] = None) -> str:
    if not target_table_logical:
        return app_key or ""

    normalized_rel = str(relationship_logical or "")

    relationships = {}
    if isinstance(app_value, dict):
        relationships = (
            app_value.get("Tables", {})
            .get(table_key, {})
            .get("Relationships", {})
        )

    matched_rel_key = ""
    matched_rel_val = {}
    if normalized_rel:
        for rel_key, rel_val in relationships.items():
            if not isinstance(rel_val, dict):
                continue
            rel_key_str = str(rel_key)
            if rel_key_str == normalized_rel:
                matched_rel_key = rel_key_str
                matched_rel_val = rel_val
                break
        if not matched_rel_key:
            prefix_candidates = []
            for rel_key, rel_val in relationships.items():
                if not isinstance(rel_val, dict):
                    continue
                rel_key_str = str(rel_key)
                if (
                    normalized_rel.startswith(rel_key_str + "_")
                    or rel_key_str.startswith(normalized_rel + "_")
                ):
                    prefix_candidates.append((len(rel_key_str), rel_key_str, rel_val))
            if prefix_candidates:
                _, matched_rel_key, matched_rel_val = max(prefix_candidates, key=lambda item: item[0])

    rel_type = str(matched_rel_val.get("Type", ""))
    rel_parent = matched_rel_val.get("Properties", {}).get("Parent", {})
    if "CrossAppChild" in rel_type and isinstance(rel_parent, dict):
        parent_app = str(rel_parent.get("App", "") or "")
        if parent_app:
            return parent_app
    if matched_rel_key and "CrossAppParent" in rel_type:
        child_app = _find_cross_app_child_app(
            parent_app_key=app_key,
            parent_table_key=table_key,
            parent_relationship_key=matched_rel_key,
            target_table_logical=target_table_logical,
            qbl_resources=qbl_resources,
        )
        if child_app:
            return child_app

    if isinstance(identifier_index, dict) and target_table_logical:
        owning_apps = []
        for candidate_app_key, app_data in identifier_index.items():
            if not isinstance(app_data, dict):
                continue
            tables = app_data.get("tables", {})
            if target_table_logical in tables:
                owning_apps.append(candidate_app_key)
        if len(owning_apps) == 1:
            return owning_apps[0]
        if app_key in owning_apps:
            return app_key

    return app_key or ""


def _find_cross_app_child_app(parent_app_key: str, parent_table_key: str, parent_relationship_key: str,
                              target_table_logical: str, qbl_resources: Dict[str, Any] = None) -> str:
    if not isinstance(qbl_resources, dict):
        return ""
    resources = qbl_resources.get("Resources", {})
    if not isinstance(resources, dict):
        return ""

    for child_app_key, child_app_value in resources.items():
        if not isinstance(child_app_value, dict):
            continue
        for child_table_key, child_table_value in child_app_value.get("Tables", {}).items():
            if target_table_logical and child_table_key != target_table_logical:
                continue
            relationships = child_table_value.get("Relationships", {})
            for _, child_relationship_value in relationships.items():
                if not isinstance(child_relationship_value, dict):
                    continue
                rel_type = str(child_relationship_value.get("Type", ""))
                if "CrossAppChild" not in rel_type:
                    continue
                parent_ref = child_relationship_value.get("Properties", {}).get("Parent", {})
                if not isinstance(parent_ref, dict):
                    continue
                if (
                    parent_ref.get("App") == parent_app_key
                    and parent_ref.get("Table") == parent_table_key
                    and parent_ref.get("Relationship") == parent_relationship_key
                ):
                    return child_app_key
    return ""


def enhance_field_metadata_with_usage(field_metadata, field_usage):
    enhanced_metadata = []
    
    for field_data in field_metadata:
        field_key = field_data["Field Logical ID"]
        table_key = field_data.get("Table Logical ID", "")
        usage = field_usage.get((table_key, field_key))
        if usage is None:
            usage = field_usage.get(field_key, {})
        
        usage_categories = [
            "Used in Reports", "Used in Report Dynamic Filters", "Used in Forms", "Used in Form Rules", 
            "Used in Custom Data Rules", "Referenced in Formulas", 
            "Used in Relationships", "Used in Dashboards", "Used in Charts",
            "Used in Field Properties", "Used in Permissions", "Cross-App References"
        ]
        usage_count = sum(1 for category in usage_categories if usage.get(category, False))
        usage_counts = usage.get("__counts__", {})
        usage_reference_count = sum(
            int(usage_counts.get(category, 0))
            for category in usage_categories
        ) if isinstance(usage_counts, dict) else usage_count
        
        try:
            field_id_num = int(field_data["Field ID"]) if field_data["Field ID"] != "N/A" else 0
        except (ValueError, TypeError):
            field_id_num = 0
        
        is_builtin_field = 1 <= field_id_num <= 5
        is_unused = usage_reference_count == 0 and not is_builtin_field
        
        enhanced_field = field_data.copy()
        enhanced_metadata.append(enhanced_field)
        enhanced_field.update({
            "Used in Reports": "Yes" if usage.get("Used in Reports") else "No",
            "Used in Report Dynamic Filters": "Yes" if usage.get("Used in Report Dynamic Filters") else "No",
            "Used in Forms": "Yes" if usage.get("Used in Forms") else "No", 
            "Used in Form Rules": "Yes" if usage.get("Used in Form Rules") else "No",
            "Used in Custom Data Rules": "Yes" if usage.get("Used in Custom Data Rules") else "No",
            "Referenced in Formulas": "Yes" if usage.get("Referenced in Formulas") else "No",
            "Used in Relationships": "Yes" if usage.get("Used in Relationships") else "No",
            "Used in Dashboards": "Yes" if usage.get("Used in Dashboards") else "No",
            "Used in Charts": "Yes" if usage.get("Used in Charts") else "No",
            "Used in Field Properties": "Yes" if usage.get("Used in Field Properties") else "No",
            "Used in Permissions": "Yes" if usage.get("Used in Permissions") else "No",
            "Cross-App References": "Yes" if usage.get("Cross-App References") else "No",
            
            "Total Usage Count": usage_reference_count,
            "Total Usage Categories": usage_count,
            "Potentially Unused": "Yes" if is_unused else "No",
        })
    
    return enhanced_metadata


