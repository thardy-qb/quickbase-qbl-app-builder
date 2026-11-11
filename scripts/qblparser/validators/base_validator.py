from qblparser.qbl_schema import QBL_SCHEMA
from qblparser.qbl_schema.platform_requirements import near_miss_for
from qblparser.qbl_schema.schema_rules import export_omits


def schema_issue(code, logical_id, path, qbl_type, problem, severity="error"):
    return {
        "LogicalID": logical_id,
        "Path": path,
        "Type": qbl_type,
        "Problem": problem,
        "Code": code,
        "Severity": severity,
    }


_MESSAGE_CODES = (
    ("Missing 'Type'", "SCH000", "error"),
    ("Unknown resource type", "SCH001", "error"),
    ("Missing required node-level", "SCH007", "error"),
    ("Missing required", "SCH003", "error"),
    ("Unexpected", "SCH004", "error"),
    ("Bad reference", "SCH009", "warning"),
    ("should be", "SCH002", "error"),
)

UNCLASSIFIED_CODE = "SCH999"


def normalize_issue(issue):
    if not isinstance(issue, dict):
        return issue
    if "Code" in issue and "Severity" in issue:
        return issue

    problem = str(issue.get("Problem", ""))
    code, severity = UNCLASSIFIED_CODE, "error"
    for fragment, candidate_code, candidate_severity in _MESSAGE_CODES:
        if fragment in problem:
            code, severity = candidate_code, candidate_severity
            break

    normalized = dict(issue)
    normalized.setdefault("Code", code)
    normalized.setdefault("Severity", severity)
    return normalized


class BaseValidator:
    
    def create_context(self, logical_id, path, table_id=None, form_id=None, rule_id=None):
        return {
            "LogicalID": logical_id,
            "TableID": table_id,
            "FormID": form_id,
            "RuleID": rule_id,
            "Path": path
        }
    
    def validate_nested_properties(self, properties, schema, context, nested_name):
        issues = []
        
        if not isinstance(properties, dict):
            issues.append(schema_issue(
                "SCH006", context["LogicalID"], f"{context['Path']} > {nested_name}",
                f"Nested::{nested_name}",
                f"{nested_name} should be an object/dictionary, got {type(properties)}",
            ))
            return issues
        
        for req_field in schema.get("required", []):
            if req_field not in properties:
                issues.append(schema_issue(
                    "SCH005", context["LogicalID"], f"{context['Path']} > {nested_name}",
                    f"Nested::{nested_name}",
                    f"Missing required {nested_name.lower()} property '{req_field}'",
                ))
        
        for prop in properties:
            if (prop not in schema.get("required", []) and 
                prop not in schema.get("optional", [])):
                issues.append(schema_issue(
                    "SCH004", context["LogicalID"], f"{context['Path']} > {nested_name}",
                    f"Nested::{nested_name}",
                    f"Unexpected {nested_name.lower()} property '{prop}'",
                ))
        
        return issues


def validate_nested_tree(properties, tree, context, r_type, prefix):
    issues = []
    if not tree or not isinstance(properties, dict):
        return issues

    for name, spec in tree.items():
        if name not in properties:
            continue

        value = properties[name]
        path = f"{prefix}{name}"

        keyed = spec.get("keyed")
        if keyed is not None:
            if isinstance(value, dict):
                for required_key in keyed.get("required_keys", []):
                    if required_key not in value:
                        issues.append(schema_issue(
                            "SCH005", context.get("LogicalID", ""), context.get("Path", ""),
                            r_type, f"Missing required property '{path}.{required_key}'",
                        ))
                for key, entry in value.items():
                    issues.extend(
                        validate_nested_tree(
                            {key: entry},
                            {key: {"required": keyed.get("required", [])}},
                            context, r_type, f"{path}.",
                        )
                    )
            continue

        if not isinstance(value, dict):
            if spec.get("required"):
                issues.append(schema_issue(
                    "SCH006", context.get("LogicalID", ""), context.get("Path", ""),
                    r_type, f"Property '{path}' should be an object, got {type(value).__name__}",
                ))
            continue

        for required in spec.get("required", []):
            if required not in value:
                issues.append(schema_issue(
                    "SCH005", context.get("LogicalID", ""), context.get("Path", ""),
                    r_type, f"Missing required property '{path}.{required}'",
                ))

        issues.extend(validate_nested_tree(value, spec.get("nested"), context, r_type, f"{path}."))

    return issues


def validate_generic(resource, context):
    issues = []
    r_type = resource.get("Type")
    properties = resource.get("Properties", {})

    if not r_type:
        issues.append(schema_issue(
            "SCH000", context["LogicalID"], context.get("Path", ""), "Unknown",
            "Missing 'Type' in resource",
        ))
        return issues

    from qblparser.qbl_schema import QBL_SCHEMA
    schema = QBL_SCHEMA.get(r_type)

    if not schema:
        problem = (
            f"Unknown resource type '{r_type}'; the platform answers an "
            f"unrecognised type with a NodeRemoved warning and drops the node, "
            f"so this deploys without error and leaves the object missing"
        )
        instead = near_miss_for(r_type)
        if instead:
            problem += f". Did you mean '{instead}'?"
        issues.append(schema_issue(
            "SCH001", context["LogicalID"], context.get("Path", ""), r_type, problem,
        ))
        return issues

    if not isinstance(properties, dict):
        issues.append(schema_issue(
            "SCH002", context["LogicalID"], context.get("Path", ""), r_type,
            f"Properties should be an object/dictionary, got {type(properties)}",
        ))
        return issues

    for req_field in schema.get("required", []):
        if req_field not in properties:
            if export_omits(r_type, req_field):
                issues.append(schema_issue(
                    "SCH012", context["LogicalID"], context.get("Path", ""), r_type,
                    f"Missing required property '{req_field}', which Quickbase's "
                    f"own export is known to leave out",
                    severity="warning",
                ))
                continue
            issues.append(schema_issue(
                "SCH003", context["LogicalID"], context.get("Path", ""), r_type,
                f"Missing required property '{req_field}'",
            ))

    if not schema.get("open"):
        for prop in properties:
            if prop not in schema.get("required", []) and prop not in schema.get("optional", []):
                issues.append(schema_issue(
                    "SCH004", context["LogicalID"], context.get("Path", ""), r_type,
                    f"Unexpected property '{prop}'",
                ))

    issues.extend(validate_nested_tree(properties, schema.get("nested"), context, r_type, ""))

    if "When" in resource:
        for idx, cond in enumerate(resource["When"]):
            new_context = context.copy()
            new_context["Path"] = f"{context.get('Path', '')}.When[{idx}]"
            from .core import validate_resource
            issues.extend(validate_resource(cond, new_context))
            
            if cond.get("Type") == "QB::FormV2::Rule::Condition::Group" and "When" in cond:
                for j, subcond in enumerate(cond["When"]):
                    sub_context = context.copy()
                    sub_context["Path"] = f"{context.get('Path', '')}.When[{idx}].Sub[{j}]"
                    issues.extend(validate_resource(subcond, sub_context))

    if "Actions" in resource:
        for idx, action in enumerate(resource["Actions"]):
            action_context = context.copy()
            action_context["Path"] = f"{context.get('Path', '')}.Actions[{idx}]"
            from .core import validate_resource
            issues.extend(validate_resource(action, action_context))

    return issues

def print_unexpected_properties(issues):
    from collections import defaultdict
    
    grouped = defaultdict(set)
    for issue in issues:
        if issue["Problem"].startswith("Unexpected property"):
            field_type = issue["Type"]
            prop_name = issue["Problem"].split("'")[1]
            grouped[field_type].add(prop_name)

    for field_type, props in grouped.items():
        quoted_props = ', '.join(f'"{prop}"' for prop in sorted(props))
        print(f"{field_type} unexpected properties: [{quoted_props}]")