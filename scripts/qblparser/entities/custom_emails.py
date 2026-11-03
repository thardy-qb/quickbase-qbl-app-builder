from qblparser.utils.property_extractor import PropertyExtractor
from qblparser.utils.helpers import FieldExtractor, SafeExtractor, TableResolver
from qblparser.utils.qbl_tags import scalar_ref_value


RECIPIENT_KEYS = ("Users", "ExternalUsers", "UserEntities", "Groups", "Roles", "Fields")
RECIPIENT_SECTIONS = ("To", "CC", "BCC")


def _resolve_var(value, param_defs):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        if set(value.keys()) == {"Name"}:
            param = param_defs.get(value.get("Name"), {})
            resolved = param.get("Value", []) if isinstance(param, dict) else []
            if resolved is None or resolved == "":
                return []
            return resolved if isinstance(resolved, list) else [resolved]
        return [value]
    return []


def _count_recipients(section, param_defs):
    if not isinstance(section, dict):
        return 0
    total = 0
    for key in RECIPIENT_KEYS:
        total += len(_resolve_var(section.get(key), param_defs))
    return total


def _collect_recipient_roles(email_settings, param_defs):
    roles = []
    for section_name in RECIPIENT_SECTIONS:
        section = SafeExtractor.get_dict(email_settings, section_name)
        for entry in _resolve_var(section.get("Roles"), param_defs):
            if isinstance(entry, dict) and entry.get("Role"):
                roles.append(entry["Role"])
            elif isinstance(entry, str):
                roles.append(entry)
    return roles


def _get_param_defs(qbl_resources):
    if isinstance(qbl_resources, dict):
        defs = qbl_resources.get("ParameterDefinitions", {})
        if isinstance(defs, dict):
            return defs
    return {}


def _iter_condition_fields(conditions):
    if not isinstance(conditions, list):
        return
    for condition in conditions:
        if not isinstance(condition, dict):
            continue
        nested = condition.get("When")
        if isinstance(nested, list):
            yield from _iter_condition_fields(nested)
        field_ref = SafeExtractor.get_dict(condition, "Properties").get("Field")
        logical_id = FieldExtractor.from_reference(field_ref)
        if logical_id:
            yield logical_id


CONDITION_TYPE_PREFIX = "QB::CustomEmail::Condition::"

GROUP_CONDITION_TYPE = CONDITION_TYPE_PREFIX + "Group"


def _is_group_condition(condition):
    return (
        condition.get("Type") == GROUP_CONDITION_TYPE
        or isinstance(condition.get("When"), list)
    )


def _count_conditions(conditions):
    if not isinstance(conditions, list):
        return 0
    count = 0
    for condition in conditions:
        if not isinstance(condition, dict):
            continue
        if _is_group_condition(condition):
            count += _count_conditions(condition.get("When"))
            continue
        if str(condition.get("Type", "")).startswith(CONDITION_TYPE_PREFIX):
            count += 1
    return count


def _stringify(value, default=""):
    scalar = scalar_ref_value(value)
    if scalar:
        return scalar
    if isinstance(value, dict):
        for key in ("Name", "Field", "Role"):
            if key in value:
                return str(value[key])
        return default
    if value is None:
        return default
    return str(value)


def _document_template_id(entry):
    scalar = scalar_ref_value(entry)
    if scalar:
        return scalar
    if isinstance(entry, dict):
        template_id = entry.get("DocumentTemplate", "")
        return template_id if isinstance(template_id, str) else ""
    if isinstance(entry, str):
        return entry
    return ""


def parse_custom_email(
    email_key,
    email_value,
    identifier_index=None,
    table_schema=None,
    app_key="",
    table_key="",
    table_value=None,
    qbl_resources=None,
    **kwargs,
):
    props = PropertyExtractor(email_value)
    send_options = SafeExtractor.get_dict(email_value, "Properties", "SendOptions")
    email_settings = SafeExtractor.get_dict(email_value, "Properties", "EmailSettings")
    conditions = email_value.get("Conditions", [])
    param_defs = _get_param_defs(qbl_resources)

    table_props = PropertyExtractor(table_value or {})
    table_name = table_props.name("") if table_value else ""

    trigger_fields = SafeExtractor.get_list(send_options, "Fields")
    record_events = SafeExtractor.get_list(send_options, "RecordEventTrigger")
    documents = SafeExtractor.get_list(email_settings, "Documents")
    attachments = SafeExtractor.get_list(email_settings, "FileAttachments")
    content = email_settings.get("Content", "")
    if not isinstance(content, str):
        content = ""
    condition_count = _count_conditions(conditions)

    return {
        "App Logical ID": app_key or "",
        "Table Logical ID": table_key or "",
        "Table Name": table_name,
        "Custom Email Logical ID": email_key,
        "Custom Email ID": props.id(""),
        "Custom Email Name": props.name(""),
        "Description": props.description("") or "",
        "Owner": props.get("Owner", ""),
        "Trigger Type": send_options.get("TriggerType", ""),
        "Record Event Triggers": ", ".join(str(e) for e in record_events) or "None",
        "Schedule": send_options.get("Schedule", ""),
        "Trigger Field Count": len(trigger_fields),
        "From": _stringify(email_settings.get("From"), ""),
        "Bulk Change": email_settings.get("BulkChange", ""),
        "Check Recipient Permissions": "Yes" if email_settings.get("CheckRecipientPermissions") else "No",
        "Send Scheduled Even When Empty": "Yes" if email_settings.get("SendScheduledEmailEvenWhenEmpty") else "No",
        "Subject": _stringify(email_settings.get("Subject"), "").strip(),
        "To Recipient Count": _count_recipients(email_settings.get("To"), param_defs),
        "CC Recipient Count": _count_recipients(email_settings.get("CC"), param_defs),
        "BCC Recipient Count": _count_recipients(email_settings.get("BCC"), param_defs),
        "Referenced Roles": ", ".join(_collect_recipient_roles(email_settings, param_defs)) or "None",
        "Has Content": "Yes" if content.strip() else "No",
        "Content Length": len(content),
        "File Attachment Count": len(attachments),
        "Document Template Count": len(documents),
        "Condition Count": condition_count,
        "Has Conditions": "Yes" if condition_count else "No",
    }


def parse_custom_email_field_matrix(
    email_key,
    email_value,
    identifier_index=None,
    table_schema=None,
    app_key="",
    table_key="",
    table_value=None,
    qbl_resources=None,
    **kwargs,
):
    props = PropertyExtractor(email_value)
    email_name = props.name("")
    send_options = SafeExtractor.get_dict(email_value, "Properties", "SendOptions")
    email_settings = SafeExtractor.get_dict(email_value, "Properties", "EmailSettings")
    param_defs = _get_param_defs(qbl_resources)

    references = []

    for ref in SafeExtractor.get_list(send_options, "Fields"):
        logical_id = FieldExtractor.from_reference(ref)
        if logical_id:
            references.append((logical_id, "Trigger Field"))

    for ref in SafeExtractor.get_list(email_settings, "FileAttachments"):
        logical_id = FieldExtractor.from_reference(ref)
        if logical_id:
            references.append((logical_id, "File Attachment"))

    for section_name in RECIPIENT_SECTIONS:
        section = SafeExtractor.get_dict(email_settings, section_name)
        for entry in _resolve_var(section.get("Fields"), param_defs):
            logical_id = FieldExtractor.from_reference(entry)
            if logical_id:
                references.append((logical_id, f"{section_name} Recipient Field"))

    for logical_id in _iter_condition_fields(email_value.get("Conditions", [])):
        references.append((logical_id, "Condition"))

    rows = []
    for field_logical_id, usage in references:
        rows.append({
            "App Logical ID": app_key or "",
            "Table Logical ID": table_key or "",
            "Custom Email Logical ID": email_key,
            "Custom Email Name": email_name,
            "Field Logical ID": field_logical_id,
            "Field ID": TableResolver.resolve_field_id(table_key, field_logical_id, identifier_index, app_key),
            "Usage Context": usage,
        })
    return rows


def parse_custom_email_document_matrix(
    email_key,
    email_value,
    identifier_index=None,
    table_schema=None,
    app_key="",
    table_key="",
    table_value=None,
    qbl_resources=None,
    **kwargs,
):
    props = PropertyExtractor(email_value)
    email_name = props.name("")
    email_settings = SafeExtractor.get_dict(email_value, "Properties", "EmailSettings")

    document_templates = SafeExtractor.get_dict(table_value or {}, "DocumentTemplates")

    rows = []
    for entry in SafeExtractor.get_list(email_settings, "Documents"):
        template_logical_id = _document_template_id(entry)
        if not template_logical_id:
            continue

        template_node = document_templates.get(template_logical_id, {})
        template_name = PropertyExtractor(template_node).name("") if template_node else ""

        rows.append({
            "App Logical ID": app_key or "",
            "Table Logical ID": table_key or "",
            "Custom Email Logical ID": email_key,
            "Custom Email Name": email_name,
            "Document Template Logical ID": template_logical_id,
            "Document Template Name": template_name,
        })
    return rows


