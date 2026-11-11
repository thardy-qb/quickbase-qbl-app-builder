from qblparser.analysis.base_analyzer import BaseAnalyzer
from qblparser.utils.helpers import FieldExtractor
from qblparser.utils.property_extractor import PropertyExtractor
from qblparser.entities.forms.metadata import RULE_FIELD_KEYS, iter_rule_conditions
import re

class RuleAnalyzer(BaseAnalyzer):
    
    def get_analysis_name(self):
        return "Form Rule Usage Analysis"
    
    def get_priority(self):
        return 30
    
    def get_description(self):
        return "Analyzes field usage in form rule conditions and actions"
    
    def analyze(self, qbl_data, field_usage):
        fields_processed = 0
        
        for app_data in self.navigator.get_applications(qbl_data):
            self.tracker.set_source_app(app_data["key"])
            for table_data in self.navigator.get_tables(app_data):
                field_label_to_logical_id = self._build_field_label_mapping(table_data)
                
                for form_data in self.navigator.get_forms(table_data):
                    for rule_data in self.navigator.get_form_rules(form_data):
                        fields_processed += self._analyze_single_rule(rule_data, field_usage, field_label_to_logical_id)
        
        self.log_analysis_complete(fields_processed)
    
    def _build_field_label_mapping(self, table_data):
        field_mapping = {}
        
        try:
            fields = table_data["data"].get("Fields", {})
            
            for logical_id, field_value in fields.items():
                if isinstance(field_value, dict):
                    field_props = PropertyExtractor(field_value)
                    field_label = field_props.label()
                    
                    if field_label:
                        field_mapping[field_label] = logical_id
                        
        except Exception as e:
            print(f"Error building field label mapping for table {table_data.get('key', 'unknown')}: {e}")
        
        return field_mapping
    
    def _analyze_single_rule(self, rule_data, field_usage, field_label_to_logical_id):
        fields_found = 0
        rule_value = rule_data["data"]
        
        try:
            fields_found += self._analyze_rule_conditions(rule_value, field_usage, field_label_to_logical_id)
            
            fields_found += self._analyze_rule_actions(rule_value, field_usage, field_label_to_logical_id)
            
        except Exception as e:
            print(f"Error analyzing rule {rule_data.get('key', 'unknown')}: {e}")
        
        return fields_found
    
    def _analyze_rule_conditions(self, rule_value, field_usage, field_label_to_logical_id):
        fields_found = 0

        conditions = list(rule_value.get("When") or []) + list(rule_value.get("If") or [])
        for condition in iter_rule_conditions(conditions):
            properties = condition.get("Properties", {})
            if not isinstance(properties, dict):
                continue
            fields_found += self._mark_field_keys(properties, field_usage)

            formula = properties.get("Formula", "")
            if formula:
                referenced_fields = self._extract_fields_from_formula_with_lookup(formula, field_label_to_logical_id)
                for ref_field in referenced_fields:
                    if self.tracker.mark_used_if_exists(field_usage, ref_field, "Used in Form Rules"):
                        fields_found += 1
        
        return fields_found

    def _mark_field_keys(self, properties, field_usage):
        found = 0
        for key in RULE_FIELD_KEYS:
            field_ref = FieldExtractor.from_reference(properties.get(key))
            if self.tracker.mark_used_if_exists(field_usage, field_ref, "Used in Form Rules"):
                found += 1
        value = properties.get("Value")
        if isinstance(value, dict):
            field_ref = FieldExtractor.from_reference(value)
            if self.tracker.mark_used_if_exists(field_usage, field_ref, "Used in Form Rules"):
                found += 1
        return found
    
    def _analyze_rule_actions(self, rule_value, field_usage, field_label_to_logical_id):
        fields_found = 0
        
        actions = rule_value.get("Actions", [])
        for action in actions:
            if isinstance(action, dict):
                properties = action.get("Properties", {})
                if not isinstance(properties, dict):
                    continue
                fields_found += self._mark_field_keys(properties, field_usage)
                
                value = properties.get("Value", "")
                if isinstance(value, str) and value:
                    referenced_fields = self._extract_fields_from_formula_with_lookup(value, field_label_to_logical_id)
                    for ref_field in referenced_fields:
                        if self.tracker.mark_used_if_exists(field_usage, ref_field, "Used in Form Rules"):
                            fields_found += 1
        
        return fields_found
    
    def _extract_fields_from_formula_with_lookup(self, formula, field_label_to_logical_id):
        try:
            if not isinstance(formula, str) or not formula.strip():
                return []
            
            referenced_logical_ids = []
            
            raw_field_references = FieldExtractor.from_formula(formula)
            
            for field_ref in raw_field_references:
                if field_ref.startswith("$Field_"):
                    referenced_logical_ids.append(field_ref)
                else:
                    if field_ref in field_label_to_logical_id:
                        logical_id = field_label_to_logical_id[field_ref]
                        referenced_logical_ids.append(logical_id)
            
            return referenced_logical_ids
            
        except Exception as e:
            print(f"Error extracting fields from formula: {e}")
            return []
