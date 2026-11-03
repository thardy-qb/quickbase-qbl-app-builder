from qblparser.qbl_schema import QBL_SCHEMA
from ..base_validator import BaseValidator

def validate_table_role_permissions(resource, context):
    issues = []
    r_type = resource.get("Type")
    properties = resource.get("Properties", {})

    if not isinstance(properties, dict):
        issues.append({
            "LogicalID": context["LogicalID"],
            "Path": context["Path"],
            "Type": r_type,
            "Problem": f"Properties should be an object/dictionary, got {type(properties)}"
        })
        return issues

    permissions = QBL_SCHEMA.get("QB::Table::RolePermissions", {})
    valid_permission_props = (
        set(permissions.get("required", []))
        | set(permissions.get("optional", []))
        | {"When", "CustomAccessCriteria", "HasAccess"}
    )

    for section_name, section_props in properties.items():
        if section_name.startswith("$Role_"):
            if isinstance(section_props, dict):
                for prop_name, prop_value in section_props.items():
                    if not _is_valid_permission_property(prop_name, valid_permission_props):
                        issues.append({
                            "LogicalID": context["LogicalID"],
                            "Path": f"{context['Path']} > {section_name}",
                            "Type": r_type,
                            "Problem": f"Unexpected permission property '{prop_name}' (expected Can* properties or other known permission properties)"
                        })
            else:
                issues.append({
                    "LogicalID": context["LogicalID"],
                    "Path": f"{context['Path']} > {section_name}",
                    "Type": r_type,
                    "Problem": f"Section '{section_name}' should be an object/dictionary, got {type(section_props)}"
                })
        else:
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": context["Path"],
                "Type": r_type,
                "Problem": f"Unexpected top-level property '{section_name}' (expected '$Role_*')"
            })

    return issues

def _is_valid_permission_property(prop_name, valid_props):
    return isinstance(prop_name, str) and prop_name in valid_props