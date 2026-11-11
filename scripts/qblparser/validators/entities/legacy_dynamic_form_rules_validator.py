from qblparser.qbl_schema import QBL_SCHEMA
from ..base_validator import BaseValidator


RULE_CONTAINERS = (
    ("When", "Trigger"),
    ("If", "Condition"),
    ("Actions", "Action"),
)


def validate_legacy_dynamic_form_rule(resource, context):
    issues = []
    r_type = resource.get("Type")
    properties = resource.get("Properties", {})
    schema = QBL_SCHEMA.get(r_type, {})

    if not isinstance(properties, dict):
        issues.append({
            "LogicalID": context["LogicalID"],
            "Path": context["Path"],
            "Type": r_type,
            "Problem": f"Properties should be an object/dictionary, got {type(properties)}"
        })
        return issues

    for req_field in schema.get("required", []):
        if req_field not in properties:
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": context["Path"],
                "Type": r_type,
                "Problem": f"Missing required property '{req_field}'"
            })

    for prop in properties:
        if (prop not in schema.get("required", []) and
                prop not in schema.get("optional", [])):
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": context["Path"],
                "Type": r_type,
                "Problem": f"Unexpected property '{prop}'"
            })

    for container, noun in RULE_CONTAINERS:
        issues.extend(validate_rule_container(resource, context, container, noun))

    return issues


def validate_rule_container(resource, context, container, noun):
    issues = []
    validator = BaseValidator()
    members = resource.get(container, [])

    if not isinstance(members, list):
        if members:
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": f"{context['Path']} > {container}",
                "Type": f"QB::FormRule::{noun}s",
                "Problem": f"A rule's '{container}' should be a list, got {type(members)}"
            })
        return issues

    for idx, member in enumerate(members):
        member_context = context.copy()
        member_context["Path"] = f"{context['Path']} > {container}[{idx}]"

        if not isinstance(member, dict):
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": member_context["Path"],
                "Type": f"QB::FormRule::{noun}",
                "Problem": f"A {noun.lower()} should be a dictionary, got {type(member)}"
            })
            continue

        issues.extend(validate_rule_member(member, member_context, validator, noun))

    return issues


def validate_rule_member(member, context, validator, noun):
    issues = []
    member_type = member.get("Type", "")

    if not member_type:
        issues.append({
            "LogicalID": context["LogicalID"],
            "Path": context["Path"],
            "Type": "Unknown",
            "Problem": f"Missing 'Type' in form rule {noun.lower()}"
        })
        return issues

    schema = QBL_SCHEMA.get(member_type)
    if schema is None:
        from ..base_validator import schema_issue
        from qblparser.qbl_schema.platform_requirements import near_miss_for

        problem = (
            f"Unknown resource type '{member_type}'; the platform answers an "
            f"unrecognised type with a NodeRemoved warning and drops the node, "
            f"so this deploys without error and leaves the {noun.lower()} missing"
        )
        instead = near_miss_for(member_type)
        if instead:
            problem += f". Did you mean '{instead}'?"
        return [schema_issue(
            "SCH001", context["LogicalID"], context["Path"], member_type, problem,
        )]

    issues.extend(validator.validate_nested_properties(
        member.get("Properties", {}), schema, context, noun
    ))
    return issues
