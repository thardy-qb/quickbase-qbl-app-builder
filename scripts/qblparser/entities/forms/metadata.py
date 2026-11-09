from typing import Any, Dict

from qblparser.utils.helpers import FieldExtractor, SafeExtractor, TableResolver
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


RULE_CONDITION_CHILD_KEYS = ("When", "If")

RULE_FIELD_KEYS = ("Field", "Target", "FieldTarget")


def iter_rule_conditions(nodes):
    if not isinstance(nodes, list):
        return
    for node in nodes:
        if not isinstance(node, dict):
            continue
        yield node
        for key in RULE_CONDITION_CHILD_KEYS:
            yield from iter_rule_conditions(node.get(key))


def rule_field_references(rule_value):
    if not isinstance(rule_value, dict):
        return []
    found = []

    def collect(node, role):
        properties = node.get("Properties", {})
        if not isinstance(properties, dict):
            return
        for key in RULE_FIELD_KEYS:
            field = FieldExtractor.from_reference(properties.get(key))
            if field and (field, role) not in found:
                found.append((field, role))
        value = properties.get("Value")
        if isinstance(value, dict):
            field = FieldExtractor.from_reference(value)
            if field and (field, role) not in found:
                found.append((field, role))

    conditions = list(rule_value.get("When") or []) + list(rule_value.get("If") or [])
    for condition in iter_rule_conditions(conditions):
        collect(condition, "condition")
    for action in rule_value.get("Actions") or []:
        if isinstance(action, dict):
            collect(action, "action")
    return found


def _rule_members(rule_value: Dict[str, Any], container: str, type_column: str):
    return _parse_members(rule_value.get(container, []), type_column)


def _parse_members(members, type_column: str):
    if not isinstance(members, list):
        return []

    parsed = []
    for member in members:
        if not isinstance(member, dict):
            continue
        entry = {
            type_column: PropertyExtractor(member).type(),
            "Properties": member.get("Properties", {}),
        }
        nested = []
        for key in RULE_CONDITION_CHILD_KEYS:
            nested.extend(_parse_members(member.get(key), type_column))
        if nested:
            entry["Conditions"] = nested
        parsed.append(entry)
    return parsed


def _type_tail(node) -> str:
    text = PropertyExtractor(node).type("") if isinstance(node, dict) else ""
    return text.rsplit("::", 1)[-1] if text else ""


def _reference_label(reference, field_labels) -> str:
    field = FieldExtractor.from_reference(reference)
    if field:
        return field_labels.get(field, field)
    if isinstance(reference, dict):
        for key, value in reference.items():
            if isinstance(value, str) and value.startswith("$"):
                return value
    return "" if reference in (None, "", {}) else str(reference)


def _scalar_text(value, field_labels) -> str:
    if isinstance(value, dict):
        label = _reference_label(value, field_labels)
        return f"[{label}]" if label else ""
    if isinstance(value, list):
        return ", ".join(_scalar_text(item, field_labels) for item in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return f'"{" ".join(str(value).split())}"'


def _render_condition(node, field_labels) -> str:
    properties = node.get("Properties", {}) if isinstance(node.get("Properties"), dict) else {}
    children = []
    for key in RULE_CONDITION_CHILD_KEYS:
        children.extend(c for c in (node.get(key) or []) if isinstance(c, dict))
    if children:
        joiner = " OR " if str(properties.get("TrueWhen", "")).casefold() == "any" else " AND "
        inner = joiner.join(_render_condition(child, field_labels) for child in children)
        return f"({inner})" if len(children) > 1 else inner

    kind = _type_tail(node)
    subject = ""
    for key in ("Field", "Role"):
        if key in properties:
            subject = _reference_label(properties.get(key), field_labels)
            break
    if not subject and properties.get("Formula"):
        subject = f"formula {' '.join(str(properties['Formula']).split())}"
    comparison = properties.get("Comparison", "")
    parts = [subject or kind]
    if comparison:
        parts.append(str(comparison))
    for key in ("Value", "Value2", "Days", "RelativeTo", "TimeFrame"):
        value = properties.get(key)
        if key in properties and value is not None and (value != "" or key == "Value"):
            parts.append(_scalar_text(value, field_labels))
    if kind and subject and kind not in ("Field", "FormulaIsTrue", "Role"):
        parts.insert(0, kind)
    return " ".join(part for part in parts if part)


def _render_action(node, field_labels) -> str:
    properties = node.get("Properties", {}) if isinstance(node.get("Properties"), dict) else {}
    parts = [_type_tail(node) or "Action"]
    for key in RULE_FIELD_KEYS:
        if key in properties:
            label = _reference_label(properties.get(key), field_labels)
            if label:
                parts.append(label)
    for key in ("Value", "Label", "Color", "Message"):
        if key in properties and properties.get(key) not in (None, ""):
            parts.append(("to " if key in ("Value", "Label", "Color") else "") +
                         _scalar_text(properties.get(key), field_labels))
    return " ".join(parts)


def render_rule_summary(rule_value, field_labels=None) -> str:
    field_labels = field_labels or {}
    clauses = []
    for container, word in (("When", "When"), ("If", "If")):
        members = [m for m in (rule_value.get(container) or []) if isinstance(m, dict)]
        if members:
            clauses.append(f"{word} " + " AND ".join(_render_condition(m, field_labels) for m in members))
    actions = [a for a in (rule_value.get("Actions") or []) if isinstance(a, dict)]
    text = " ".join(clauses) or "Always"
    if actions:
        text += " -> " + "; ".join(_render_action(a, field_labels) for a in actions)
    return text


def _field_labels(table_fields) -> Dict[str, str]:
    labels = {}
    if isinstance(table_fields, dict):
        for key, value in table_fields.items():
            if isinstance(value, dict):
                label = PropertyExtractor(value).label("")
                if label:
                    labels[key] = label
    return labels


def parse_rule(table_name: str, form_name: str, rule_key: str, rule_value: Dict[str, Any], form_key: str, table_key: str, table_schema, form_value, identifier_index=None, app_key="", table_fields=None):
    table_info = TableResolver.resolve_from_logical_id(table_key, identifier_index, table_schema, app_key)
    table_id = table_info.get("table_id", "")
    
    rule_props = PropertyExtractor(rule_value)
    form_props = PropertyExtractor(form_value)
    labels = _field_labels(table_fields)
    references = rule_field_references(rule_value)

    def named(role):
        return ", ".join(labels.get(field, field) for field, r in references if r == role)

    disabled = rule_props.get("Disabled", rule_props.get("Disable", False))

    return {
        "App Logical ID": app_key or "",
        "Table Name": table_name,
        "Table Logical ID": table_key or "",
        "Table ID": table_id,
        "Form Name": form_name,
        "Form Logical ID": form_key or "",
        "Form ID": form_props.id(),
        "Rule ID": rule_key,
        "Rule Name": rule_props.get("Name", "") or "",
        "Enabled": not bool(disabled),
        "Run On": rule_props.get("RunOn", "") or "",
        "Rule Summary": render_rule_summary(rule_value, labels),
        "Condition Fields": named("condition"),
        "Action Fields": named("action"),
        "When Conditions": _rule_members(rule_value, "When", "Condition Type"),
        "If Conditions": _rule_members(rule_value, "If", "Condition Type"),
        "Actions": _rule_members(rule_value, "Actions", "Action Type"),
    }
