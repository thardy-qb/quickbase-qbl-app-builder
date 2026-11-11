from qblparser.utils.helpers import TableResolver, report_field_uses
from qblparser.utils.property_extractor import PropertyExtractor
from qblparser.utils.qbl_tags import scalar_ref_value
from typing import List, Dict, Any


def _reference_logical_id(value):
    scalar = scalar_ref_value(value)
    if scalar:
        return scalar
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for candidate in value.values():
            resolved = _reference_logical_id(candidate)
            if resolved:
                return resolved
    return ""


def _format_sorting(sort_and_group):
    if isinstance(sort_and_group, str):
        return sort_and_group
    if isinstance(sort_and_group, dict):
        sort_and_group = [sort_and_group]
    if not isinstance(sort_and_group, list) or not sort_and_group:
        return "Default"

    parts = []
    for entry in sort_and_group:
        if not isinstance(entry, dict):
            resolved = _reference_logical_id(entry)
            if resolved:
                parts.append(resolved)
            continue
        target = _reference_logical_id(entry.get("Field")) or "Unresolved"
        order = entry.get("SortOrder")
        group_by = entry.get("GroupBy")
        rendered = f"{target} {order}" if isinstance(order, str) and order else target
        if isinstance(group_by, str) and group_by and group_by != "Default":
            rendered = f"{rendered} (grouped: {group_by})"
        parts.append(rendered)

    return ", ".join(parts) if parts else "Default"

def parse_report(table_name, report_value, table_key, report_key, identifier_index,
                 app_key="",
                 table_schema=None, table_fields=None):
    table_info = TableResolver.resolve_from_logical_id(table_key, identifier_index, table_schema, app_key)
    table_id = table_info.get("table_id", "")
    
    props = PropertyExtractor(report_value)

    report_id = props.id()
    report_name = props.name("Unnamed Report")
    description = props.description("N/A")
    
    filters = props.safe_get("Filters", "Criteria", default="N/A")
    sorting = _format_sorting(props.get("SortAndGroup", "Default"))
    report_type = props.type().split("::")[-1] if props.type() else ""

    formulas = []
    for formula_key, formula_value in report_value.get("ReportFormulas", {}).items():
        formula_props = PropertyExtractor(formula_value)
        f_type = formula_props.type().split("::")[-1] if formula_props.type() else ""
        f_label = formula_props.label("Unnamed Formula")
        f_content = formula_props.formula("N/A")
        formulas.append(f"{f_label} ({f_type}): {f_content}")

    dynamic_fields = _extract_dynamic_fields(props.properties, table_fields, table_key, identifier_index, app_key)

    return {
        "App Logical ID": app_key or "",
        "Table Logical ID": table_key or "",
        "Table Name": table_name,
        "Table ID": table_id,
        "Report Logical ID": report_key or "",
        "Report ID": report_id,
        "Report Name": report_name,
        "Type": report_type,
        "Description": description,
        "Filters": filters,
        "Dynamic Fields": dynamic_fields,
        "Sorting": sorting,
        "Report Formulas": "\n".join(formulas) if formulas else "N/A",
        "Used Last": "",
        "Used Count": "",
        "Used in Forms": "No",
        "Used in Dashboards": "No",
    }


def _extract_dynamic_fields(properties_dict, table_fields=None, table_key=None, identifier_index=None, app_key=""):
    try:
        filters = properties_dict.get("Filters", {})
        if not isinstance(filters, dict):
            return "Default"
        
        dynamic_fields = filters.get("DynamicFields", "Default")
        
        if dynamic_fields == "Default" or dynamic_fields is None:
            return "Default"
        
        if isinstance(dynamic_fields, list):
            formatted_fields = []
            
            for field_item in dynamic_fields:
                if isinstance(field_item, dict) and field_item.get("__bad_ref__"):
                    continue
                
                if isinstance(field_item, dict):
                    field_ref = field_item.get("Field", "")
                    
                    if field_ref and isinstance(field_ref, str) and field_ref.startswith("$Field_"):
                        field_info = _get_field_info(field_ref, table_fields, table_key, identifier_index, app_key)
                        
                        if field_info:
                            formatted_fields.append(field_info)
                
                elif isinstance(field_item, str) and field_item.startswith("$Field_"):
                    field_info = _get_field_info(field_item, table_fields, table_key, identifier_index, app_key)
                    if field_info:
                        formatted_fields.append(field_info)
            
            return ", ".join(formatted_fields) if formatted_fields else "Default"
        
        return str(dynamic_fields)
        
    except Exception as e:
        print(f"Warning: Could not extract dynamic fields: {e}")
        return "Default"


def _get_field_info(field_ref, table_fields, table_key, identifier_index, app_key=""):
    try:
        field_label = _get_field_label_from_ref(field_ref, table_fields)
        
        field_id = TableResolver.resolve_field_id(table_key, field_ref, identifier_index, app_key)
        
        if field_label and field_id:
            return f"{field_label} - {field_id}"
        elif field_label:
            return field_label
        
        return None
        
    except Exception as e:
        print(f"Warning: Could not get field info for {field_ref}: {e}")
        return None


def _get_field_label_from_ref(field_ref, table_fields):
    try:
        if table_fields and isinstance(table_fields, dict):
            field_data = table_fields.get(field_ref, {})
            
            if isinstance(field_data, dict):
                field_props = PropertyExtractor(field_data)
                field_label = field_props.label()
                
                if field_label and field_label != "":
                    return field_label
        
        clean_name = field_ref.replace("$Field_", "").replace("_", " ")
        return clean_name if clean_name else None
        
    except Exception:
        try:
            return field_ref.replace("$Field_", "").replace("_", " ")
        except:
            return None


def parse_report_field_matrix(table_name, report_value, fields, table_key, report_key, identifier_index, app_key="", table_schema=None):
    table_info = TableResolver.resolve_from_logical_id(table_key, identifier_index, table_schema, app_key)
    table_id = table_info.get("table_id", "")
    
    report_props = PropertyExtractor(report_value)

    parsed_matrix = []
    raw_cols = report_props.get("Columns", [])

    if not isinstance(raw_cols, list):
        for field_ref, field_def in fields.items():
            field_props = PropertyExtractor(field_def)
            field_type = field_props.type()
            
            should_include = (
                field_props.get("AddToAllNewReports", False) or
                
                field_type in [
                    "QB::Field::RecordId", 
                    "QB::Field::DateCreated", 
                    "QB::Field::DateModified",
                    "QB::Field::LastModifiedBy",
                    "QB::Field::RecordOwner"
                ] or
                
                field_props.allowed_in_reports() is True or
                
                field_props.is_required() is True
            )
            
            if should_include:
                field_id = TableResolver.resolve_field_id(table_key, field_ref, identifier_index, app_key)
                report_id_value = str(report_props.id("0"))
                field_id_value = field_id if field_id else str(field_props.id("0"))

                parsed_matrix.append({
                    "App Logical ID": app_key or "",
                    "Table Logical ID": table_key or "",
                    "Table ID": table_id,
                    "Table Name": table_name,
                    "Report Logical ID": report_key or "",
                    "Report ID": report_id_value,
                    "Report Name": report_props.name("Unnamed Report"),
                    "Field Logical ID": field_ref,
                    "Field ID": field_id_value,
                    "Field Label": field_props.label("Unnamed Field"),
                    "Field Type": field_props.type().split("::")[-1] if field_props.type() else "",
                    "Used As": "DefaultColumns",
                })

        parsed_matrix.sort(key=lambda x: str(x["Field ID"]))
        return parsed_matrix

    for col in raw_cols:
        if isinstance(col, dict):
            field_ref = col.get("Field")
            if not isinstance(field_ref, str):
                continue
        elif isinstance(col, str):
            field_ref = col
        else:
            continue

        if not field_ref.startswith("$Field_"):
            continue

        field_def = fields.get(field_ref, {})
        field_props = PropertyExtractor(field_def)
        
        field_id = TableResolver.resolve_field_id(table_key, field_ref, identifier_index, app_key)
        
        report_id_value = str(report_props.id("0"))
        field_id_value = field_id if field_id else str(field_props.id("0"))

        parsed_matrix.append({
            "App Logical ID": app_key or "",
            "Table Logical ID": table_key or "",
            "Table ID": table_id,
            "Table Name": table_name,
            "Report Logical ID": report_key or "",
            "Report ID": report_id_value,
            "Report Name": report_props.name("Unnamed Report"),
            "Field Logical ID": field_ref,
            "Field ID": field_id_value,
            "Field Label": field_props.label("Unnamed Field"),
            "Field Type": field_props.type().split("::")[-1] if field_props.type() else "",
            "Used As": "Columns",
        })

    already = {row["Field Logical ID"] for row in parsed_matrix}
    field_ids = {
        str(field_value["Id"]): field_key
        for field_key, field_value in fields.items()
        if isinstance(field_value, dict) and field_value.get("Id") is not None
    }
    for field_ref, used_as in report_field_uses(report_value, field_ids=field_ids):
        if field_ref in already:
            continue
        already.add(field_ref)

        field_props = PropertyExtractor(fields.get(field_ref, {}))
        field_id = TableResolver.resolve_field_id(table_key, field_ref, identifier_index, app_key)

        parsed_matrix.append({
            "App Logical ID": app_key or "",
            "Table Logical ID": table_key or "",
            "Table ID": table_id,
            "Table Name": table_name,
            "Report Logical ID": report_key or "",
            "Report ID": str(report_props.id("0")),
            "Report Name": report_props.name("Unnamed Report"),
            "Field Logical ID": field_ref,
            "Field ID": field_id if field_id else str(field_props.id("0")),
            "Field Label": field_props.label("Unnamed Field"),
            "Field Type": field_props.type().split("::")[-1] if field_props.type() else "",
            "Used As": used_as,
        })

    parsed_matrix.sort(key=lambda x: (
        x["Table Name"],
        str(x["Report ID"]),
        str(x["Field ID"])
    ))
    return parsed_matrix

def parse_report_permissions(table_name, report_key, report_value, table_key, identifier_index=None, app_key="", table_schema=None):
    
    table_info = TableResolver.resolve_from_logical_id(table_key, identifier_index, table_schema, app_key)
    table_id = table_info.get("table_id", "")
    
    report_props = PropertyExtractor(report_value)
    role_permissions = report_props.get("RolePermissions", {})
    parsed_permissions = []

    for role_key, permissions in role_permissions.items():
        role_id = ""
        role_name = role_key
        
        if identifier_index:
            for map_app_key, app_data in identifier_index.items():
                if isinstance(app_data, dict) and "roles" in app_data:
                    role_data = app_data["roles"].get(role_key, {})
                    role_id = str(role_data.get("id", ""))
                    if role_id:
                        break
        
        parsed_permission = {
            "App Logical ID": app_key or "",
            "Table Logical ID": table_key or "",
            "Table ID": table_id,
            "Table Name": table_name,
            
            "Report Logical ID": report_key or "",
            "Report ID": report_props.id(""),
            "Report Name": report_props.name("Unnamed Report"),
            
            "Role Logical ID": role_key,
            "Role ID": role_id,
            "Role Name": role_name,
        }

        if isinstance(permissions, bool):
            parsed_permission["Has Access"] = "TRUE" if permissions else "FALSE"
        elif isinstance(permissions, dict):
            has_access = permissions.get("HasAccess", True)
            parsed_permission["Has Access"] = "TRUE" if has_access else "FALSE"
            
        else:
            parsed_permission["Has Access"] = "FALSE"

        parsed_permissions.append(parsed_permission)

    parsed_permissions.sort(key=lambda x: (
        x["Table Logical ID"], 
        x["Report Logical ID"], 
        x["Role Logical ID"]
    ))

    return parsed_permissions


