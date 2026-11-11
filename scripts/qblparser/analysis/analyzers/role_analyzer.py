from qblparser.analysis.base_analyzer import BaseAnalyzer
from qblparser.utils.property_extractor import PropertyExtractor

class RoleAnalyzer(BaseAnalyzer):
    
    def get_analysis_name(self):
        return "Role Usage Analysis"
    
    def get_priority(self):
        return 35
    
    def get_description(self):
        return "Analyzes role usage in permissions, form rules, formulas, and access criteria"
    
    def analyze(self, qbl_data, role_usage):
        roles_processed = 0
        
        for app_data in self.navigator.get_applications(qbl_data):
            self.tracker.set_source_app(app_data["key"])
            roles_processed += self._analyze_app_role_usage(app_data, role_usage)
        
        self.log_analysis_complete(roles_processed)
    
    def _analyze_app_role_usage(self, app_data, role_usage):
        roles_found = 0
        app_key = app_data["key"]
        app_value = app_data["data"]
        
        try:
            for table_data in self.navigator.get_tables(app_data):
                roles_found += self._analyze_table_permissions_for_roles(table_data, role_usage)
                roles_found += self._analyze_field_permissions_for_roles(table_data, role_usage)
                roles_found += self._analyze_report_permissions_for_roles(table_data, role_usage)
                roles_found += self._analyze_form_usage_for_roles(table_data, role_usage)
                roles_found += self._analyze_custom_data_rules_for_roles(table_data, role_usage)
            
            roles_found += self._analyze_dashboard_permissions_for_roles(app_value, role_usage)
            
            roles_found += self._analyze_pipeline_usage_for_roles(app_value, role_usage)
            
        except Exception as e:
            print(f"Error analyzing role usage for app {app_key}: {e}")
        
        return roles_found
    
    def _analyze_table_permissions_for_roles(self, table_data, role_usage):
        roles_found = 0
        
        try:
            table_props = PropertyExtractor(table_data["data"])
            role_permissions = table_props.get("RolePermissions", {})
            
            for role_key, permissions in role_permissions.items():
                if self.tracker.mark_used_if_exists(role_usage, role_key, "Used in Table Permissions"):
                    roles_found += 1
                
                if isinstance(permissions, dict):
                    for perm_key, perm_value in permissions.items():
                        if isinstance(perm_value, dict):
                            criteria = perm_value.get("CustomAccessCriteria", "")
                            if criteria and isinstance(criteria, str):
                                formula_roles = self._extract_roles_from_formula_string(criteria)
                                for formula_role in formula_roles:
                                    if self.tracker.mark_used_if_exists(role_usage, formula_role, "Used in Custom Access Rules"):
                                        roles_found += 1
        except Exception as error:
            print(f"Error in role_analyzer._analyze_table_permissions_for_roles: {error}")
        
        return roles_found
    
    def _analyze_field_permissions_for_roles(self, table_data, role_usage):
        roles_found = 0
        
        try:
            fields = table_data["data"].get("Fields", {})
            for field_value in fields.values():
                if isinstance(field_value, dict):
                    field_props = PropertyExtractor(field_value)
                    field_role_perms = field_props.get("RolePermissions", {})
                    
                    for role_key, permissions in field_role_perms.items():
                        if self.tracker.mark_used_if_exists(role_usage, role_key, "Used in Field Permissions"):
                            roles_found += 1
                        
                        if isinstance(permissions, dict):
                            for perm_key, perm_value in permissions.items():
                                if isinstance(perm_value, dict):
                                    criteria = perm_value.get("CustomAccessCriteria", "")
                                    if criteria and isinstance(criteria, str):
                                        formula_roles = self._extract_roles_from_formula_string(criteria)
                                        for formula_role in formula_roles:
                                            if self.tracker.mark_used_if_exists(role_usage, formula_role, "Used in Custom Access Rules"):
                                                roles_found += 1
        except Exception as error:
            print(f"Error in role_analyzer._analyze_field_permissions_for_roles: {error}")
        
        return roles_found
    
    def _analyze_report_permissions_for_roles(self, table_data, role_usage):
        roles_found = 0
        
        try:
            reports = table_data["data"].get("Reports", {})
            for report_value in reports.values():
                if isinstance(report_value, dict):
                    report_props = PropertyExtractor(report_value)
                    report_role_perms = report_props.get("RolePermissions", {})
                    
                    for role_key, permissions in report_role_perms.items():
                        if self.tracker.mark_used_if_exists(role_usage, role_key, "Used in Report Permissions"):
                            roles_found += 1
                        
                        if isinstance(permissions, dict):
                            for perm_key, perm_value in permissions.items():
                                if isinstance(perm_value, dict):
                                    criteria = perm_value.get("CustomAccessCriteria", "")
                                    if criteria and isinstance(criteria, str):
                                        formula_roles = self._extract_roles_from_formula_string(criteria)
                                        for formula_role in formula_roles:
                                            if self.tracker.mark_used_if_exists(role_usage, formula_role, "Used in Custom Access Rules"):
                                                roles_found += 1
        except Exception as error:
            print(f"Error in role_analyzer._analyze_report_permissions_for_roles: {error}")
        
        return roles_found
    
    def _analyze_form_usage_for_roles(self, table_data, role_usage):
        roles_found = 0
        
        try:
            forms_section = table_data["data"].get("Forms", {})
            
            forms_props = PropertyExtractor(forms_section)
            role_defaults = forms_props.get("RoleDefaults", {})
            
            for role_key in role_defaults.keys():
                if self.tracker.mark_used_if_exists(role_usage, role_key, "Used in Default Forms"):
                    roles_found += 1
            
            forms = forms_section.get("Resources", {})
            for form_value in forms.values():
                if isinstance(form_value, dict):
                    form_roles = self._extract_roles_from_form_rules(form_value)
                    for role_key in form_roles:
                        if self.tracker.mark_used_if_exists(role_usage, role_key, "Used in Form Rules"):
                            roles_found += 1
        except Exception as error:
            print(f"Error in role_analyzer._analyze_form_usage_for_roles: {error}")
        
        return roles_found
    
    def _analyze_custom_data_rules_for_roles(self, table_data, role_usage):
        roles_found = 0
        
        try:
            table_props = PropertyExtractor(table_data["data"])
            custom_rules = table_props.safe_get("CustomDataRules", default={})
            
            if isinstance(custom_rules, dict):
                formula = custom_rules.get("Formula", "")
                if formula and isinstance(formula, str):
                    role_refs = self._extract_roles_from_formula_string(formula)
                    for role_key in role_refs:
                        if self.tracker.mark_used_if_exists(role_usage, role_key, "Referenced in Formulas"):
                            roles_found += 1
        except Exception as error:
            print(f"Error in role_analyzer._analyze_custom_data_rules_for_roles: {error}")
        
        return roles_found
    
    def _analyze_dashboard_permissions_for_roles(self, app_value, role_usage):
        roles_found = 0
        
        try:
            pages = app_value.get("Pages", {})
            if isinstance(pages, dict) and "Resources" in pages:
                dashboards_root = pages["Resources"]
            else:
                dashboards_root = pages or {}
            
            for dashboard_key, dashboard_value in dashboards_root.items():
                if dashboard_key.startswith("$Dashboard_") and isinstance(dashboard_value, dict):
                    dashboard_role_perms = dashboard_value.get("Properties", {}).get("RolePermissions", {})
                    for role_key in dashboard_role_perms.keys():
                        if self.tracker.mark_used_if_exists(role_usage, role_key, "Used in Dashboard Permissions"):
                            roles_found += 1
        except Exception as error:
            print(f"Error in role_analyzer._analyze_dashboard_permissions_for_roles: {error}")
        
        return roles_found
    
    def _analyze_pipeline_usage_for_roles(self, app_value, role_usage):
        return 0
    
    def _extract_roles_from_form_rules(self, form_value):
        role_refs = set()
        
        try:
            is_form_v2 = form_value.get("Type", "").startswith("QB::FormV2")
            rules_node = form_value.get("Rules", {} if is_form_v2 else [])
            
            if is_form_v2 and isinstance(rules_node, dict):
                for rule_value in rules_node.values():
                    if isinstance(rule_value, dict):
                        rule_roles = self._extract_roles_from_single_rule(rule_value)
                        role_refs.update(rule_roles)
            
            elif not is_form_v2 and isinstance(rules_node, list):
                for rule_value in rules_node:
                    if isinstance(rule_value, dict):
                        rule_roles = self._extract_roles_from_single_rule(rule_value)
                        role_refs.update(rule_roles)
        except Exception as error:
            print(f"Error in role_analyzer._extract_roles_from_form_rules: {error}")
        
        return list(role_refs)
    
    def _extract_roles_from_single_rule(self, rule_value):
        role_refs = set()
        
        try:
            conditions = rule_value.get("When", [])
            rule_roles = self._extract_roles_from_conditions_usage(conditions)
            role_refs.update(rule_roles)
            
            actions = rule_value.get("Actions", [])
            for action in actions:
                if isinstance(action, dict):
                    action_formula = action.get("Properties", {}).get("Value", "")
                    if action_formula and isinstance(action_formula, str):
                        formula_roles = self._extract_roles_from_formula_string(action_formula)
                        role_refs.update(formula_roles)
        except Exception as error:
            print(f"Error in role_analyzer._extract_roles_from_single_rule: {error}")
        
        return list(role_refs)

    def _extract_roles_from_conditions_usage(self, conditions):
        role_refs = set()
        
        for condition in conditions:
            if not isinstance(condition, dict):
                continue
                
            condition_type = condition.get("Type", "")
            condition_props = condition.get("Properties", {})
            
            if condition_type == "QB::FormV2::Rule::Condition::Role":
                role_ref = condition_props.get("Role")
                if isinstance(role_ref, dict):
                    role_logical_id = role_ref.get("Role", "")
                    if role_logical_id and role_logical_id.startswith("$Role_"):
                        role_refs.add(role_logical_id)
                elif isinstance(role_ref, str) and role_ref.startswith("$Role_"):
                    role_refs.add(role_ref)
            
            elif condition_type == "QB::FormV2::Rule::Condition::Group":
                nested_conditions = condition.get("When", [])
                nested_roles = self._extract_roles_from_conditions_usage(nested_conditions)
                role_refs.update(nested_roles)
            
            elif condition_type == "QB::FormV2::Rule::Condition::FormulaIsTrue":
                formula = condition_props.get("Formula", "")
                if formula and isinstance(formula, str):
                    formula_roles = self._extract_roles_from_formula_string(formula)
                    role_refs.update(formula_roles)
            
            elif condition_type == "QB::Form::Rule::Condition::Role":
                role_ref = condition_props.get("Role")
                comparison = condition_props.get("Comparison", "")
                
                role_logical_id = self._parse_role_reference_for_usage(role_ref)
                if role_logical_id:
                    role_refs.add(role_logical_id)
            
            elif condition_type == "QB::Form::Rule::Condition::User":
                comparison = condition_props.get("Comparison", "")
                
                if comparison in ["IsInRole", "IsNotInRole", "HasRole"]:
                    role_ref = (condition_props.get("Role") or 
                            condition_props.get("Value") or 
                            condition_props.get("User"))
                    
                    role_logical_id = self._parse_role_reference_for_usage(role_ref)
                    if role_logical_id:
                        role_refs.add(role_logical_id)
            
            elif "Trigger" in condition_type and "User" in condition_type:
                comparison = condition_props.get("Comparison", "")
                
                if comparison in ["IsInRole", "IsNotInRole", "HasRole"]:
                    value_prop = condition_props.get("Value", {})
                    role_ref = None
                    
                    if isinstance(value_prop, dict):
                        role_ref = value_prop.get("Role")
                    else:
                        role_ref = condition_props.get("Role")
                    
                    role_logical_id = self._parse_role_reference_for_usage(role_ref)
                    if role_logical_id:
                        role_refs.add(role_logical_id)
            
            elif condition_type == "QB::Form::Rule::Condition::Group":
                nested_conditions = condition.get("When", [])
                nested_roles = self._extract_roles_from_conditions_usage(nested_conditions)
                role_refs.update(nested_roles)
            
            elif condition_type == "QB::Form::Rule::Condition::FormulaIsTrue":
                formula = condition_props.get("Formula", "")
                if formula and isinstance(formula, str):
                    formula_roles = self._extract_roles_from_formula_string(formula)
                    role_refs.update(formula_roles)
            
            else:
                for prop_key, prop_value in condition_props.items():
                    if isinstance(prop_value, str) and prop_value.startswith("$Role_"):
                        role_refs.add(prop_value)
                    elif isinstance(prop_value, dict):
                        nested_role = prop_value.get("Role", "")
                        if nested_role and isinstance(nested_role, str) and nested_role.startswith("$Role_"):
                            role_refs.add(nested_role)
        
        return list(role_refs)

    def _parse_role_reference_for_usage(self, role_ref):
        if not role_ref:
            return ""
        
        if isinstance(role_ref, str) and role_ref.startswith("$Role_"):
            return role_ref
        
        if isinstance(role_ref, dict):
            logical_id = (role_ref.get("Role") or 
                        role_ref.get("LogicalID") or 
                        role_ref.get("$ref", ""))
            
            if logical_id and isinstance(logical_id, str) and logical_id.startswith("$Role_"):
                return logical_id
        
        return ""
    
    def _extract_roles_from_formula_string(self, formula):
        import re
        
        role_refs = set()
        
        try:
            role_pattern = r'(\$Role_[A-Za-z0-9_]+)'
            matches = re.findall(role_pattern, formula)
            role_refs.update(matches)
            
        except Exception as error:
            print(f"Error in role_analyzer._extract_roles_from_formula_string: {error}")
        
        return list(role_refs)
