import re
from typing import Any, Dict, List

from qblparser.utils.helpers import TableResolver
from qblparser.utils.property_extractor import PropertyExtractor


def parse_role_to_form_rule_matrix(table_name: str, form_key: str, form_value: Dict[str, Any], table_key: str, table_schema, identifier_index=None, app_key="") -> List[Dict[str, Any]]:
    table_info = TableResolver.resolve_from_logical_id(table_key, identifier_index, table_schema, app_key)
    table_id = table_info.get("table_id", "")
    
    form_props = PropertyExtractor(form_value)
    form_name = form_props.name("Unnamed Form")
    form_id = form_props.id()
    
    role_rule_matrix: List[Dict[str, Any]] = []
    
    is_form_v2 = form_key.startswith("$FormV2_")
    rules_node = form_value.get("Rules", {} if is_form_v2 else [])
    
    if is_form_v2 and isinstance(rules_node, dict):
        for rule_key, rule_value in rules_node.items():
            if isinstance(rule_value, dict):
                role_references = _extract_role_references_from_rule(rule_key, rule_value)
                for role_ref in role_references:
                    role_rule_matrix.append({
                        "App Logical ID": app_key or "",
                        "Table Logical ID": table_key or "",
                        "Table ID": table_id,
                        "Table Name": table_name,
                        "Form Name": form_name,
                        "Form ID": form_id,
                        "Form Logical ID": form_key,
                        "Rule ID": rule_key,
                        "Rule Name": rule_value.get("Properties", {}).get("Name", rule_key),
                        "Rule Enabled": not rule_value.get("Properties", {}).get("Disabled", False),
                        "Role Logical ID": role_ref["role_logical_id"],
                        "Role Name": role_ref["role_name"],
                        "Usage Type": role_ref["usage_type"],
                        "Usage Context": role_ref["usage_context"],
                    })
    
    elif not is_form_v2 and isinstance(rules_node, list):
        for rule_index, rule_value in enumerate(rules_node):
            if isinstance(rule_value, dict):
                rule_key = f"Rule_{rule_index}"
                role_references = _extract_role_references_from_rule(rule_key, rule_value)
                for role_ref in role_references:
                    role_rule_matrix.append({
                        "App Logical ID": app_key or "",
                        "Table Logical ID": table_key or "",
                        "Table ID": table_id,
                        "Table Name": table_name,
                        "Form Name": form_name,
                        "Form ID": form_id,
                        "Form Logical ID": form_key,
                        "Rule ID": rule_key,
                        "Rule Name": rule_value.get("Properties", {}).get("Name", rule_key),
                        "Rule Enabled": not rule_value.get("Properties", {}).get("Disabled", False),
                        "Role Logical ID": role_ref["role_logical_id"],
                        "Role Name": role_ref["role_name"],
                        "Usage Type": role_ref["usage_type"],
                        "Usage Context": role_ref["usage_context"],
                    })
    
    return role_rule_matrix


def _extract_role_references_from_rule(rule_key: str, rule_value: Dict[str, Any]) -> List[Dict[str, Any]]:
    role_references: List[Dict[str, Any]] = []
    
    conditions = rule_value.get("When", [])
    role_references.extend(_extract_roles_from_conditions(conditions))
    
    actions = rule_value.get("Actions", [])
    for action in actions:
        if isinstance(action, dict):
            action_properties = action.get("Properties", {})
            action_formula = action_properties.get("Value", "")
            if action_formula and isinstance(action_formula, str):
                role_refs_in_formula = _extract_roles_from_formula(action_formula)
                for role_logical_id, context in role_refs_in_formula:
                    role_references.append({
                        "role_logical_id": role_logical_id,
                        "role_name": _get_role_name_from_logical_id(role_logical_id),
                        "usage_type": "Action (Formula)",
                        "usage_context": context
                    })
    
    return role_references


def _extract_roles_from_conditions(conditions, depth: int = 0) -> List[Dict[str, Any]]:
    role_references: List[Dict[str, Any]] = []
    
    for condition in conditions:
        if not isinstance(condition, dict):
            continue
            
        condition_props = PropertyExtractor(condition)
        condition_type = condition_props.type()
        
        if condition_type == "QB::FormV2::Rule::Condition::Role":
            role_ref = condition.get("Properties", {}).get("Role")
            comparison = condition.get("Properties", {}).get("Comparison", "")
            
            if role_ref:
                role_logical_id, role_name = _parse_role_reference(role_ref)
                if role_logical_id:
                    role_references.append({
                        "role_logical_id": role_logical_id,
                        "role_name": role_name,
                        "usage_type": "Condition",
                        "usage_context": f"{comparison} role check" if comparison else "Role condition"
                    })
        
        elif condition_type == "QB::FormV2::Rule::Condition::Group":
            nested_conditions = condition.get("When", [])
            if nested_conditions:
                role_references.extend(_extract_roles_from_conditions(nested_conditions, depth + 1))
        
        elif condition_type == "QB::FormV2::Rule::Condition::FormulaIsTrue":
            formula = condition.get("Properties", {}).get("Formula", "")
            if formula and isinstance(formula, str):
                role_refs_in_formula = _extract_roles_from_formula(formula)
                for role_logical_id, context in role_refs_in_formula:
                    role_references.append({
                        "role_logical_id": role_logical_id,
                        "role_name": _get_role_name_from_logical_id(role_logical_id),
                        "usage_type": "Condition (Formula)",
                        "usage_context": context
                    })
        
        elif condition_type == "QB::Form::Rule::Condition::Role":
            role_ref = condition.get("Properties", {}).get("Role")
            comparison = condition.get("Properties", {}).get("Comparison", "")
            
            if role_ref:
                role_logical_id, role_name = _parse_role_reference(role_ref)
                if role_logical_id:
                    role_references.append({
                        "role_logical_id": role_logical_id,
                        "role_name": role_name,
                        "usage_type": "Condition (Legacy)",
                        "usage_context": f"{comparison} role check" if comparison else "Legacy role condition"
                    })
        
        elif condition_type == "QB::Form::Rule::Condition::User":
            comparison = condition.get("Properties", {}).get("Comparison", "")
            if comparison in ["IsInRole", "IsNotInRole", "HasRole"]:
                role_ref = (condition.get("Properties", {}).get("Role") or 
                           condition.get("Properties", {}).get("Value") or 
                           condition.get("Properties", {}).get("User"))
                
                if role_ref:
                    role_logical_id, role_name = _parse_role_reference(role_ref)
                    if role_logical_id:
                        role_references.append({
                            "role_logical_id": role_logical_id,
                            "role_name": role_name,
                            "usage_type": "Condition (Legacy User)",
                            "usage_context": f"{comparison} user condition"
                        })
        
        elif condition_type == "QB::Form::Rule::Condition::Group":
            nested_conditions = condition.get("When", [])
            if nested_conditions:
                role_references.extend(_extract_roles_from_conditions(nested_conditions, depth + 1))
        
        elif condition_type == "QB::Form::Rule::Condition::FormulaIsTrue":
            formula = condition.get("Properties", {}).get("Formula", "")
            if formula and isinstance(formula, str):
                role_refs_in_formula = _extract_roles_from_formula(formula)
                for role_logical_id, context in role_refs_in_formula:
                    role_references.append({
                        "role_logical_id": role_logical_id,
                        "role_name": _get_role_name_from_logical_id(role_logical_id),
                        "usage_type": "Condition (Legacy Formula)",
                        "usage_context": context
                    })
        
        elif "Trigger" in condition_type and "User" in condition_type:
            comparison = condition.get("Properties", {}).get("Comparison", "")
            
            if comparison in ["IsInRole", "IsNotInRole", "HasRole"]:
                value_prop = condition.get("Properties", {}).get("Value", {})
                role_ref = None
                
                if isinstance(value_prop, dict):
                    role_ref = value_prop.get("Role")
                else:
                    role_ref = condition.get("Properties", {}).get("Role")
                
                if role_ref:
                    role_logical_id, role_name = _parse_role_reference(role_ref)
                    if role_logical_id:
                        role_references.append({
                            "role_logical_id": role_logical_id,
                            "role_name": role_name,
                            "usage_type": "Trigger Condition",
                            "usage_context": f"{comparison} trigger condition"
                        })
        
        else:
            properties = condition.get("Properties", {})
            for prop_key, prop_value in properties.items():
                if isinstance(prop_value, str) and prop_value.startswith("$Role_"):
                    role_references.append({
                        "role_logical_id": prop_value,
                        "role_name": _get_role_name_from_logical_id(prop_value),
                        "usage_type": "Condition (Property)",
                        "usage_context": f"{condition_type} - {prop_key}"
                    })
                elif isinstance(prop_value, dict):
                    nested_role = prop_value.get("Role", "")
                    if nested_role and isinstance(nested_role, str) and nested_role.startswith("$Role_"):
                        role_references.append({
                            "role_logical_id": nested_role,
                            "role_name": _get_role_name_from_logical_id(nested_role),
                            "usage_type": "Condition (Nested Property)",
                            "usage_context": f"{condition_type} - {prop_key}.Role"
                        })
    
    return role_references


def _parse_role_reference(role_ref):
    if isinstance(role_ref, dict):
        role_logical_id = role_ref.get("Role", "")
        if role_logical_id and role_logical_id.startswith("$Role_"):
            return role_logical_id, _get_role_name_from_logical_id(role_logical_id)
        
        logical_id = (role_ref.get("LogicalID") or 
                     role_ref.get("$ref", "") or
                     role_ref.get("role", ""))
        if logical_id and logical_id.startswith("$Role_"):
            return logical_id, _get_role_name_from_logical_id(logical_id)
        
        name = role_ref.get("Name", "")
        if name:
            return "", name
            
    elif isinstance(role_ref, str) and role_ref.startswith("$Role_"):
        return role_ref, _get_role_name_from_logical_id(role_ref)
    
    return "", ""


def _extract_roles_from_formula(formula: str):
    role_references = []
    
    try:
        patterns = [
            (r'(\$Role_[A-Za-z0-9_]+)', "Direct role reference"),
            (r'User\(\)\.Role\s*=\s*["\']([^"\']+)["\']', "User role comparison"),
            (r'HasRole\s*\(\s*["\']([^"\']+)["\'][^)]*\)', "HasRole function"),
            (r'CurrentUser\(\)\.Role\s*=\s*["\']([^"\']+)["\']', "Current user role check"),
            (r'User\(\)\.HasRole\s*\(\s*["\']([^"\']+)["\']', "User has role function"),
            (r'\[([^\]]*[Rr]ole[^\]]*)\]', "Role field reference"),
            (r'\[([^\]]*[Aa]dmin[^\]]*)\]', "Admin field reference"),
            (r'\[([^\]]*[Pp]ermission[^\]]*)\]', "Permission field reference"),
            (r'IsInRole\s*\(\s*["\']([^"\']+)["\']', "IsInRole function"),
            (r'CheckRole\s*\(\s*["\']([^"\']+)["\']', "CheckRole function"),
        ]
        
        for pattern, context_desc in patterns:
            matches = re.findall(pattern, formula, re.IGNORECASE)
            
            for match in matches:
                if isinstance(match, str):
                    if match.startswith("$Role_"):
                        role_references.append((match, context_desc))
                    else:
                        role_references.append(("", f"{context_desc}: {match}"))
    
    except Exception as e:
        print(f"Error extracting roles from formula: {e}")
    
    return role_references


def _get_role_name_from_logical_id(role_logical_id):
    if not role_logical_id:
        return ""
        
    if role_logical_id.startswith("$Role_"):
        clean_name = role_logical_id.replace("$Role_", "").replace("_", " ")
        return clean_name
    
    return role_logical_id
