from typing import Any, Dict

from qblparser.utils.helpers import SafeExtractor, TableResolver
from qblparser.utils.property_extractor import PropertyExtractor
from qblparser.utils.role_defaults import collect_role_default_references


ROLE_FORM_ASSIGNMENT_KEYS = ("ViewForm", "EditForm", "AddForm")

_REPORTED_FORM_PROPERTIES = frozenset({
    "Name", "Description", "DisplayPagesAs", "ShouldAutoAddFields",
    "ShouldShowBuiltInFieldsFooter", "AlwaysTabsForViewRecord",
    "AllowedSaveActions",
})


def _unreported_properties(form_value: Dict[str, Any]) -> Dict[str, Any]:
    properties = form_value.get("Properties") if isinstance(form_value, dict) else None
    if not isinstance(properties, dict):
        return {}
    return {
        name: value for name, value in properties.items()
        if name not in _REPORTED_FORM_PROPERTIES
    }


def collect_role_assigned_form_ids(forms_node: Dict[str, Any]) -> set[str]:
    if not isinstance(forms_node, dict):
        return set()

    forms_properties = SafeExtractor.get_dict(forms_node, "Properties")
    role_defaults = forms_properties.get("RoleDefaults", {})
    return collect_role_default_references(
        role_defaults,
        ("$Form_", "$FormV2_"),
        setting_keys=ROLE_FORM_ASSIGNMENT_KEYS,
    )


def parse_form(table_name: str, form_key: str, form_value: Dict[str, Any], table_key: str, table_schema,
               identifier_index=None, app_key="", forms_node=None):
    table_info = TableResolver.resolve_from_logical_id(table_key, identifier_index, table_schema, app_key)
    table_id = table_info.get("table_id", "")
    assigned_form_ids = collect_role_assigned_form_ids(forms_node or {})
    
    props = PropertyExtractor(form_value)
    properties = SafeExtractor.get_dict(form_value, "Properties")
    allowed_save_actions = properties.get("AllowedSaveActions", [])
    if isinstance(allowed_save_actions, list):
        allowed_save_actions_str = ", ".join(str(action) for action in allowed_save_actions)
    else:
        allowed_save_actions_str = str(allowed_save_actions) if allowed_save_actions else ""

    return {
        "App Logical ID": app_key or "",
        "Table Logical ID": table_key or "",
        "Table ID": table_id,
        "Table Name": table_name,
        "Form Logical ID": form_key or "",
        "Form ID": props.id(),
        "Form Name": props.name("Unnamed Form"),
        "Assigned to Role (View/Edit/Add)": "Yes" if form_key in assigned_form_ids else "No",
        "Description": props.description(),
        "Display Pages As": properties.get("DisplayPagesAs", ""),
        "Auto Add Fields": properties.get("ShouldAutoAddFields", ""),
        "Show Built-in Fields Footer": properties.get("ShouldShowBuiltInFieldsFooter", ""),
        "Always Tabs For View Record": properties.get("AlwaysTabsForViewRecord", ""),
        "Allowed Save Actions": allowed_save_actions_str,
        "Other Properties": _unreported_properties(form_value),
    }


def _rule_members(rule_value: Dict[str, Any], container: str, type_column: str):
    members = rule_value.get(container, [])
    if not isinstance(members, list):
        return []

    parsed = []
    for member in members:
        if not isinstance(member, dict):
            continue
        parsed.append({
            type_column: PropertyExtractor(member).type(),
            "Properties": member.get("Properties", {}),
        })
    return parsed


def parse_rule(table_name: str, form_name: str, rule_key: str, rule_value: Dict[str, Any], form_key: str, table_key: str, table_schema, form_value, identifier_index=None, app_key=""):
    table_info = TableResolver.resolve_from_logical_id(table_key, identifier_index, table_schema, app_key)
    table_id = table_info.get("table_id", "")
    
    rule_props = PropertyExtractor(rule_value)
    form_props = PropertyExtractor(form_value)

    return {
        "App Logical ID": app_key or "",
        "Table Name": table_name,
        "Table Logical ID": table_key or "",
        "Table ID": table_id,
        "Form Name": form_name,
        "Form Logical ID": form_key or "",
        "Form ID": form_props.id(),
        "Rule ID": rule_key,
        "Enabled": not rule_props.get("Disable", False),
        "When Conditions": _rule_members(rule_value, "When", "Condition Type"),
        "If Conditions": _rule_members(rule_value, "If", "Condition Type"),
        "Actions": _rule_members(rule_value, "Actions", "Action Type"),
    }
