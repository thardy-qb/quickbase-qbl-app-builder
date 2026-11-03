from qblparser.qbl_schema import QBL_SCHEMA
from ..base_validator import BaseValidator


def validate_relationship(resource, context):
    issues = []
    r_type = resource.get("Type")
    properties = resource.get("Properties", {})
    
    if isinstance(resource, str):
        issues.append({
            "LogicalID": context["LogicalID"],
            "Path": context["Path"],
            "Type": "QB::Relationship::CrossApp",
            "Problem": "Cross-app relationship is a string reference, detailed validation not possible"
        })
        return issues
    
    if isinstance(properties, dict):
        parent = properties.get("Parent", {})
        if isinstance(parent, dict) and parent.get("__bad_ref__"):
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": context["Path"],
                "Type": r_type or "QB::Relationship",
                "Problem": f"Bad reference in Parent: {parent.get('message', 'Unknown error')}"
            })
            return issues

    schema = QBL_SCHEMA.get(r_type, QBL_SCHEMA.get("QB::Relationship", {}))

    if not isinstance(properties, dict):
        issues.append({
            "LogicalID": context["LogicalID"],
            "Path": context["Path"],
            "Type": r_type or "QB::Relationship",
            "Problem": f"Properties should be an object/dictionary, got {type(properties)}"
        })
        return issues

    for req_field in schema.get("required", []):
        if req_field not in properties:
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": context["Path"],
                "Type": r_type or "QB::Relationship",
                "Problem": f"Missing required property '{req_field}'"
            })

    for prop in properties:
        if (prop not in schema.get("required", []) and 
            prop not in schema.get("optional", [])):
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": context["Path"],
                "Type": r_type or "QB::Relationship",
                "Problem": f"Unexpected property '{prop}'"
            })

    issues.extend(validate_relationship_parent(properties, context))
    
    if r_type == "QB::Relationship::CrossApp" or properties.get("CrossApp"):
        cross_app = properties.get("CrossApp")
        if cross_app is not None and not isinstance(cross_app, bool):
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": context["Path"],
                "Type": r_type or "QB::Relationship",
                "Problem": f"CrossApp should be a boolean, got {type(cross_app)}"
            })

    return issues


def validate_relationship_parent(properties, context):
    issues = []
    validator = BaseValidator()
    
    parent = properties.get("Parent", {})
    
    if not isinstance(parent, dict):
        if parent:
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": f"{context['Path']} > Parent",
                "Type": "QB::Relationship::Parent",
                "Problem": f"Parent should be an object/dictionary, got {type(parent)}"
            })
        return issues
    
    parent_schema = QBL_SCHEMA.get("QB::Relationship::Parent", {})
    if parent_schema:
        parent_context = context.copy()
        parent_context["Path"] = f"{context['Path']} > Parent"
        
        issues.extend(validator.validate_nested_properties(
            parent, parent_schema, parent_context, "Parent"
        ))
    
    table_ref = parent.get("Table")
    if table_ref:
        if not isinstance(table_ref, str):
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": f"{context['Path']} > Parent > Table",
                "Type": "QB::Relationship::Parent",
                "Problem": f"Parent Table reference should be a string, got {type(table_ref)}"
            })
        elif not table_ref.startswith("$Table_"):
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": f"{context['Path']} > Parent > Table",
                "Type": "QB::Relationship::Parent",
                "Problem": f"Parent Table reference should start with '$Table_', got '{table_ref}'"
            })
    
    relationship_ref = parent.get("Relationship")
    if relationship_ref:
        if not isinstance(relationship_ref, str):
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": f"{context['Path']} > Parent > Relationship",
                "Type": "QB::Relationship::Parent",
                "Problem": f"Parent Relationship reference should be a string, got {type(relationship_ref)}"
            })
        elif not relationship_ref.startswith("$Relationship_"):
            issues.append({
                "LogicalID": context["LogicalID"],
                "Path": f"{context['Path']} > Parent > Relationship",
                "Type": "QB::Relationship::Parent",
                "Problem": f"Parent Relationship reference should start with '$Relationship_', got '{relationship_ref}'"
            })

    return issues