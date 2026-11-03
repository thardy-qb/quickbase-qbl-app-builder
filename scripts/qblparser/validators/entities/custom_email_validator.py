from qblparser.validators.base_validator import validate_generic


def validate_custom_email(resource, context):
    issues = validate_generic(resource, context)

    conditions = resource.get("Conditions", [])
    if isinstance(conditions, list):
        from qblparser.validators.core import validate_resource

        for idx, condition in enumerate(conditions):
            if isinstance(condition, dict):
                condition_context = context.copy()
                condition_context["Path"] = f"{context.get('Path', '')} > Conditions[{idx}]"
                issues.extend(validate_resource(condition, condition_context))

    return issues
