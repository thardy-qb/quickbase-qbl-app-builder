from qblparser.qbl_schema import QBL_SCHEMA
from ..base_validator import BaseValidator


def validate_role_table_ui(resource, context):
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

    table_ui = QBL_SCHEMA.get("QB::Role::TableUI", {})
    valid_ui_props = set(table_ui.get("required", [])) | set(table_ui.get("optional", []))

    for section_name, section_props in properties.items():
        if section_name == "Global" or section_name.startswith("$Table_"):
            if isinstance(section_props, dict):
                for prop_name, prop_value in section_props.items():
                    if not _is_valid_ui_property(prop_name, valid_ui_props):
                        issues.append({
                            "LogicalID": context["LogicalID"],
                            "Path": f"{context['Path']} > {section_name}",
                            "Type": r_type,
                            "Problem": f"Unexpected UI property '{prop_name}' (expected Hide* properties)"
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
                "Problem": f"Unexpected top-level property '{section_name}' (expected 'Global' or '$Table_*')"
            })

    return issues

def _is_valid_ui_property(prop_name, valid_props):
    return isinstance(prop_name, str) and prop_name in valid_props