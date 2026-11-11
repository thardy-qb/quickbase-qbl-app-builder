from qblparser.qbl_schema import QBL_SCHEMA
from ..base_validator import BaseValidator


def _validate_field_with_block(resource, context, block_name):
    issues = []
    r_type = resource.get("Type")
    properties = resource.get("Properties", {})
    schema = QBL_SCHEMA.get(r_type, {})

    if not isinstance(properties, dict):
        return [{
            "LogicalID": context["LogicalID"],
            "Path": context["Path"],
            "Type": r_type,
            "Problem": f"Properties should be an object/dictionary, got {type(properties)}"
        }]

    for req_field in schema.get("required", []):
        if req_field not in properties:
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": context["Path"],
                "Type": r_type,
                "Problem": f"Missing required property '{req_field}'"
            })

    for prop in properties:
        if (prop != block_name
                and prop not in schema.get("required", [])
                and prop not in schema.get("optional", [])):
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": context["Path"],
                "Type": r_type,
                "Problem": f"Unexpected property '{prop}'"
            })

    if block_name not in properties:
        return issues

    block_schema = QBL_SCHEMA.get(f"{r_type}Block", {})
    if block_schema:
        issues.extend(BaseValidator().validate_nested_properties(
            properties[block_name], block_schema, context, block_name
        ))

    return issues


def validate_field_summary(resource, context):
    return _validate_field_with_block(resource, context, "Summary")


def validate_field_lookup(resource, context):
    return _validate_field_with_block(resource, context, "Lookup")


def validate_field_reference(resource, context):
    return _validate_field_with_block(resource, context, "Reference")
