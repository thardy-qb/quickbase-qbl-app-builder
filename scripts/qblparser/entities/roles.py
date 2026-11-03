from qblparser.utils.helpers import FieldExtractor, SafeExtractor, TableResolver
from qblparser.utils.property_extractor import PropertyExtractor
from qblparser.utils.role_defaults import resolve_role_default_reference

def _safe_text(value, default=""):
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


def _get_role_default_entry(role_defaults, role_key):
    if not isinstance(role_defaults, dict):
        return {}
    if role_key in role_defaults:
        return role_defaults.get(role_key, {})
    if role_key == "$Role_Everyone":
        return role_defaults.get("Everyone", {})
    return {}

def extract_role_permissions(table_key, table_value, identifier_index, table_schema=None, app_key="", app_value=None):
    
    table_props = PropertyExtractor(table_value)
    alias = table_props.get("AliasHint", "")
    
    table_id = ""
    if alias and table_schema:
        parsed_schema = TableResolver._parse_table_schema(table_schema)
        for table_entry in parsed_schema:
            if isinstance(table_entry, dict) and table_entry.get("alias") == alias:
                table_id = str(table_entry.get("id", ""))
                break

    permissions = []
    role_perms = table_props.get("RolePermissions", {})

    forms_node = table_value.get("Forms", {})
    forms_properties = forms_node.get("Properties", {})
    role_defaults = forms_properties.get("RoleDefaults", {})
    everyone_defaults = role_defaults.get("Everyone", {})

    pages_properties = SafeExtractor.get_dict(app_value, "Pages", "Properties")
    page_role_defaults = pages_properties.get("RoleDefaults", {})
    everyone_page_default = page_role_defaults.get("Everyone", {}) if isinstance(page_role_defaults, dict) else {}

    def resolve_setting(val, everyone_val):
        resolved = resolve_role_default_reference(val, everyone_val, ("$Form_", "$FormV2_"))
        if resolved:
            return resolved
        if val is None:
            return ""
        if val == "Default":
            if everyone_val is None:
                return ""
            return str(everyone_val)
        return str(val)

    col_map = {
        "ViewForm": "View Form",
        "EditForm": "Edit Form", 
        "AddForm": "Add Form",
        "GridEdit": "Grid Edit",
        "Mobile": "Mobile",
    }

    for role_key, perms in role_perms.items():
        entry = {
            "App Logical ID": app_key or "",
            "Table Logical ID": table_key,
            "Table ID": table_id,
            "Role Logical ID": role_key,
        }

        if isinstance(perms, dict):
            for perm_key, perm_val in perms.items():
                if isinstance(perm_val, dict):
                    when = perm_val.get("When", "")
                    crit = perm_val.get("CustomAccessCriteria", "")
                    if when == "CustomRule":
                        entry[perm_key] = f"Custom: {crit}"
                    else:
                        entry[perm_key] = f"When: {when}" if when else "FALSE"
                else:
                    entry[perm_key] = "TRUE" if perm_val else "FALSE"
        else:
            entry["Can View"] = "TRUE" if perms else "FALSE"

        role_form_defaults = _get_role_default_entry(role_defaults, role_key)
        for qbl_key, col_name in col_map.items():
            role_val = role_form_defaults.get(qbl_key) if isinstance(role_form_defaults, dict) else None
            everyone_val = everyone_defaults.get(qbl_key)
            entry[col_name] = resolve_setting(role_val, everyone_val)

        role_page_val = _get_role_default_entry(page_role_defaults, role_key)
        entry["Home Page"] = resolve_role_default_reference(
            role_page_val,
            everyone_page_default,
            ("$Page_", "$Dashboard_"),
        )

        permissions.append(entry)

    permissions.sort(key=lambda x: (x["Table Logical ID"], x["Role Logical ID"]))
    return permissions


def parse_roles(app_key, app_value, identifier_index=None):
    from qblparser.utils.property_extractor import PropertyExtractor
    
    roles = []
    app_roles = app_value.get("Roles", {})
    
    for role_key, role_value in app_roles.items():
        if isinstance(role_value, dict):
            props = PropertyExtractor(role_value)
            
            role_id = ""
            if identifier_index:
                for map_app_key, app_data in identifier_index.items():
                    if isinstance(app_data, dict) and "roles" in app_data:
                        role_data = app_data["roles"].get(role_key, {})
                        role_id = str(role_data.get("id", ""))
                        if role_id:
                            break
            
            role_name = _safe_text(props.name("Unnamed Role"), "Unnamed Role")
            roles.append({
                "App Logical ID": app_key,
                "Role Logical ID": role_key,
                "Role ID": role_id or props.id(""),
                "Role Name": role_name,
                "Description": _safe_text(props.description("")),
                "Default Role": "Yes" if props.get("Default", False) else "No",
                "Manage Users": "Yes" if props.get("ManageUsers", False) else "No",
                "Edit App": "Yes" if props.get("EditApp", False) else "No",
                "Disable Access": "Yes" if props.get("DisableAccess", False) else "No",
                "Restrict Access To New Tables": (
                    "Yes" if props.get("RestrictAccessToNewTablesForThisRole", False) else "No"),
                
            })
    
    roles.sort(key=lambda x: (x["App Logical ID"], x["Role Name"]))
    return roles

def enhance_role_metadata_with_usage(role_metadata, role_usage):
    enhanced_metadata = []
    
    for role_data in role_metadata:
        role_key = role_data["Role Logical ID"]
        usage = role_usage.get(role_key, {})
        
        usage_categories = [
            "Used in Form Rules", "Used in Table Permissions", "Used in Field Permissions",
            "Used in Report Permissions", "Used in Default Forms", "Used in Custom Access Rules",
            "Referenced in Formulas", "Used in Dashboard Permissions", "Used in Pipeline Rules",
            "Cross-App References"
        ]
        usage_count = sum(1 for category in usage_categories if usage.get(category, False))
        
        is_system_role = role_key in ["$Role_Everyone", "$Role_Administrator", "$Role_Manager"]
        is_unused = usage_count == 0 and not is_system_role
        
        enhanced_role = role_data.copy()
        enhanced_role.update({
            "Used in Form Rules": "Yes" if usage.get("Used in Form Rules") else "No",
            "Used in Table Permissions": "Yes" if usage.get("Used in Table Permissions") else "No",
            "Used in Field Permissions": "Yes" if usage.get("Used in Field Permissions") else "No",
            "Used in Report Permissions": "Yes" if usage.get("Used in Report Permissions") else "No",
            "Used in Default Forms": "Yes" if usage.get("Used in Default Forms") else "No",
            "Used in Custom Access Rules": "Yes" if usage.get("Used in Custom Access Rules") else "No",
            "Referenced in Formulas": "Yes" if usage.get("Referenced in Formulas") else "No",
            "Used in Dashboard Permissions": "Yes" if usage.get("Used in Dashboard Permissions") else "No",
            "Used in Pipeline Rules": "Yes" if usage.get("Used in Pipeline Rules") else "No",
            "Cross-App References": "Yes" if usage.get("Cross-App References") else "No",
            
            "Total Usage Count": usage_count,
            "Potentially Unused": "Yes" if is_unused else "No",
        })
        
        enhanced_metadata.append(enhanced_role)
    
    return enhanced_metadata

_ACCESS_RULES = ("CanViewRecords", "CanModifyRecords")


def _custom_access_rows(app_key, table_key, table_name, role_key, role_name,
                        permissions, fields_by_id):
    if not isinstance(permissions, dict):
        return []

    rows = []
    for rule_name in _ACCESS_RULES:
        rule = permissions.get(rule_name)
        if not isinstance(rule, dict):
            continue

        when = _safe_text(rule.get("When"), "")
        for field_id in FieldExtractor.from_query_criteria(rule.get("CustomAccessCriteria")):
            known = fields_by_id.get(field_id)
            field_props = known[1] if known else None

            context = f"{rule_name} custom access criteria"
            if when and when != "CustomRule":
                context += f" (dormant: When is {when})"
            if known is None:
                context += "; no field in this table carries that id"

            rows.append({
                "App Logical ID": app_key,
                "Table Logical ID": table_key,
                "Table Name": table_name,
                "Field Logical ID": known[0] if known else "",
                "Field ID": field_id,
                "Field Label": _safe_text(
                    field_props.label("Unnamed Field"), "Unnamed Field"
                ) if field_props else "",
                "Field Type": field_props.type().split("::")[-1] if field_props else "",
                "Role Logical ID": role_key,
                "Role Name": role_name,
                "Usage Type": "Custom Access Rule",
                "Usage Context": context,
            })

    return rows


def parse_field_to_role_matrix(app_key, app_value, identifier_index=None):
    
    field_role_matrix = []
    
    app_roles = app_value.get("Roles", {})
    role_names = {}
    for role_key, role_value in app_roles.items():
        if not isinstance(role_value, dict):
            continue
        role_name = PropertyExtractor(role_value).name("Unnamed Role")
        role_names[role_key] = _safe_text(role_name, "Unnamed Role")
    
    
    tables = app_value.get("Tables", {})
    for table_key, table_value in tables.items():
        if not isinstance(table_value, dict):
            continue
            
        table_props = PropertyExtractor(table_value)
        table_name = _safe_text(table_props.name("Unknown Table"), "Unknown Table")
        
        fields_by_id = {}
        for field_key, field_value in (table_value.get("Fields") or {}).items():
            if not isinstance(field_value, dict):
                continue
            numeric_id = field_value.get("Id")
            if numeric_id is not None:
                fields_by_id[str(numeric_id)] = (field_key, PropertyExtractor(field_value))

        table_role_perms = table_props.get("RolePermissions", {})
        if isinstance(table_role_perms, dict):
            for role_key, permissions in table_role_perms.items():

                if role_key in role_names:
                    field_role_matrix.append({
                        "App Logical ID": app_key,
                        "Table Logical ID": table_key,
                        "Table Name": table_name,
                        "Field Logical ID": "",
                        "Field ID": "",
                        "Field Label": "",
                        "Field Type": "",
                        "Role Logical ID": role_key,
                        "Role Name": role_names[role_key],
                        "Usage Type": "Table Permission",
                        "Usage Context": "Role has table-level permissions",
                    })
                    field_role_matrix.extend(_custom_access_rows(
                        app_key, table_key, table_name, role_key,
                        role_names[role_key], permissions, fields_by_id,
                    ))
        
        fields = table_value.get("Fields", {})
        for field_key, field_value in fields.items():
            if isinstance(field_value, dict):
                field_props = PropertyExtractor(field_value)
                field_role_perms = field_props.get("RolePermissions", {})
                
                if isinstance(field_role_perms, dict):
                    field_id = TableResolver.resolve_field_id(
                        table_key, field_key, identifier_index, app_key
                    ) or _safe_text(field_props.id(""), "")

                    for role_key in field_role_perms.keys():
                        if role_key in role_names:
                            field_role_matrix.append({
                                "App Logical ID": app_key,
                                "Table Logical ID": table_key,
                                "Table Name": table_name,
                                "Field Logical ID": field_key,
                                "Field ID": field_id or "",
                                "Field Label": _safe_text(field_props.label("Unnamed Field"), "Unnamed Field"),
                                "Field Type": field_props.type().split("::")[-1] if "::" in field_props.type() else field_props.type(),
                                "Role Logical ID": role_key,
                                "Role Name": role_names[role_key],
                                "Usage Type": "Field Permission",
                                "Usage Context": "Field has role-specific permissions",
                            })
    
    field_role_matrix.sort(key=lambda x: (
        x["App Logical ID"], x["Table Name"], x["Field Label"], x["Role Name"]
    ))
    
    return field_role_matrix
