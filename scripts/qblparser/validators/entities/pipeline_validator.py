from qblparser.qbl_schema import QBL_SCHEMA
from ..base_validator import BaseValidator


def validate_pipeline_step(resource, context):
    issues = []
    properties = resource.get("Properties", {})
    r_type = resource.get("Type")

    if not isinstance(properties, dict):
        issues.append({
            "LogicalID": context["LogicalID"],
            "Path": context["Path"],
            "Type": r_type,
            "Problem": f"Properties should be an object/dictionary, got {type(properties)}"
        })
        return issues

    step_type = properties.get("Type", "")
    
    if step_type == "loop":
        loop_schema = QBL_SCHEMA.get("QB::PipelineStep::Loop", {})
        issues.extend(validate_control_flow_step(properties, loop_schema, context, "Loop"))
        
    elif step_type == "branch":
        branch_schema = QBL_SCHEMA.get("QB::PipelineStep::Branch", {})
        issues.extend(validate_control_flow_step(properties, branch_schema, context, "Branch"))
        
    elif step_type == "pipe":
        required_properties = ["Id", "SubType", "Name"]
        
        for req_field in required_properties:
            if req_field not in properties:
                issues.append({
                    "LogicalID": context["LogicalID"],
                    "Path": context["Path"],
                    "Type": r_type,
                    "Problem": f"Missing required property '{req_field}' for pipeline step"
                })
    
    issues.extend(validate_pipeline_nested_structures(properties, context))

    return issues


def validate_control_flow_step(properties, step_schema, context, step_type_name):
    issues = []
    
    if not step_schema:
        return issues
    
    for req_field in step_schema.get("required", []):
        if req_field not in properties:
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": context["Path"],
                "Type": f"QB::PipelineStep::{step_type_name}",
                "Problem": f"Missing required {step_type_name.lower()} property '{req_field}'"
            })
    
    
    return issues


def validate_pipeline_nested_structures(properties, context):
    issues = []
    validator = BaseValidator()
    
    if "Channel" in properties:
        channel_props = properties["Channel"]
        if isinstance(channel_props, dict):
            channel_schema = QBL_SCHEMA.get("QB::PipelineStep::Channel", {})
            if channel_schema:
                issues.extend(validator.validate_nested_properties(
                    channel_props, channel_schema, context, "Channel"
                ))
        else:
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": f"{context['Path']} > Channel",
                "Type": "QB::PipelineStep::Channel",
                "Problem": "Channel should be an object/dictionary"
            })

    if "Filters" in properties:
        filters_props = properties["Filters"]
        if isinstance(filters_props, dict):
            filters_schema = QBL_SCHEMA.get("QB::PipelineStep::Filters", {})
            if filters_schema:
                issues.extend(validator.validate_nested_properties(
                    filters_props, filters_schema, context, "Filters"
                ))
                
                if "Expression" in filters_props and isinstance(filters_props["Expression"], list):
                    for idx, expr in enumerate(filters_props["Expression"]):
                        if isinstance(expr, dict):
                            expr_schema = QBL_SCHEMA.get("QB::PipelineStep::Expression", {})
                            if expr_schema:
                                expr_context = context.copy()
                                expr_context["Path"] = f"{context['Path']} > Filters > Expression[{idx}]"
                                issues.extend(validator.validate_nested_properties(
                                    expr, expr_schema, expr_context, "Expression"
                                ))
        else:
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": f"{context['Path']} > Filters",
                "Type": "QB::PipelineStep::Filters",
                "Problem": "Filters should be an object/dictionary"
            })
    
    return issues
