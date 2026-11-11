from qblparser.qbl_schema import QBL_SCHEMA
from ..base_validator import BaseValidator


def validate_legacy_form(resource, context):
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

    issues.extend(validate_legacy_form_elements(resource, context))
    
    issues.extend(validate_legacy_form_rules_shape(resource, context))

    return issues


def validate_legacy_form_elements(resource, context):
    return _validate_element_container(resource, context, BaseValidator())


def _validate_element_container(node, context, validator):
    issues = []
    elements = node.get("Elements", {})
    base = f"{context['Path']} > Elements"

    if isinstance(elements, list):
        entries = [(f"{base}[{idx}]", None, item) for idx, item in enumerate(elements)]
    elif isinstance(elements, dict):
        entries = [(f"{base} > {key}", key, value) for key, value in elements.items()]
    elif elements:
        return [{
            "LogicalID": context["LogicalID"],
            "Path": base,
            "Type": "QB::Form::Elements",
            "Problem": f"Elements should be a list or dictionary, got {type(elements)}"
        }]
    else:
        return issues

    for path, key, element in entries:
        if not isinstance(element, dict):
            continue
        element_context = context.copy()
        element_context["Path"] = path
        if key is not None:
            element_context["LogicalID"] = key
        issues.extend(validate_single_legacy_element(element, element_context, validator))
        issues.extend(_validate_element_container(element, element_context, validator))

    return issues


def validate_single_legacy_element(element, context, validator):
    issues = []
    
    element_type = element.get("Type", "")
    element_properties = element.get("Properties", {})
    
    if not element_type:
        issues.append({
            "LogicalID": context["LogicalID"],
            "Path": context["Path"],
            "Type": "Unknown",
            "Problem": "Missing 'Type' in legacy form element"
        })
        return issues
    
    element_schema = QBL_SCHEMA.get(element_type)

    if element_schema is None:
        from ..base_validator import schema_issue
        from qblparser.qbl_schema.platform_requirements import near_miss_for

        problem = (
            f"Unknown resource type '{element_type}'; the platform answers an "
            f"unrecognised type with a NodeRemoved warning and drops the node, "
            f"so this deploys without error and leaves the element missing"
        )
        instead = near_miss_for(element_type)
        if instead:
            problem += f". Did you mean '{instead}'?"
        return [schema_issue(
            "SCH001", context["LogicalID"], context["Path"], element_type, problem,
        )]

    issues.extend(validator.validate_nested_properties(
        element_properties, element_schema, context, "Element"
    ))
    
    if element_type == "QB::FormElement::Field":
        field_ref = element_properties.get("Field")
        if not field_ref:
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": context["Path"],
                "Type": element_type,
                "Problem": "Field element missing required 'Field' reference"
            })
        elif not isinstance(field_ref, (str, dict)):
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": context["Path"],
                "Type": element_type,
                "Problem": f"Field reference should be string or dict, got {type(field_ref)}"
            })

    return issues


def validate_legacy_form_rules_shape(resource, context):
    issues = []
    
    rules = resource.get("Rules", [])

    if not isinstance(rules, list):
        if rules:
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": f"{context['Path']} > Rules",
                "Type": "QB::Form::Rules",
                "Problem": f"Legacy form rules should be a list, got {type(rules)}"
            })
        return issues

    for idx, rule in enumerate(rules):
        if not isinstance(rule, dict):
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": f"{context['Path']} > Rules[{idx}]",
                "Type": "QB::FormRule",
                "Problem": f"Rule should be a dictionary, got {type(rule)}"
            })

    return issues


def validate_legacy_form_element(resource, context):
    issues = []
    r_type = resource.get("Type")
    properties = resource.get("Properties", {})

    if not r_type:
        issues.append({
            "LogicalID": context["LogicalID"],
            "Path": context["Path"],
            "Type": "Unknown",
            "Problem": "Missing 'Type' in legacy form element"
        })
        return issues

    schema = QBL_SCHEMA.get(r_type, {})
    if not schema:
        return issues

    if not isinstance(properties, dict):
        issues.append({
            "LogicalID": context["LogicalID"],
            "Path": context["Path"],
            "Type": r_type,
            "Problem": f"Properties should be an object/dictionary, got {type(properties)}"
        })
        return issues

    for req_field in schema["required"]:
        if req_field not in properties:
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": context["Path"],
                "Type": r_type,
                "Problem": f"Missing required property '{req_field}'"
            })

    for prop in properties:
        if prop not in schema["required"] and prop not in schema["optional"]:
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": context["Path"],
                "Type": r_type,
                "Problem": f"Unexpected property '{prop}'"
            })

    return issues