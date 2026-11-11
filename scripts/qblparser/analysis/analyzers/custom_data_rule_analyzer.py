from qblparser.analysis.base_analyzer import BaseAnalyzer
from qblparser.utils.property_extractor import PropertyExtractor

class CustomDataRuleAnalyzer(BaseAnalyzer):
    
    def get_analysis_name(self):
        return "Custom Data Rule Usage Analysis"
    
    def get_priority(self):
        return 40
    
    def get_description(self):
        return "Analyzes field usage in table-level custom data rule formulas"
    
    def analyze(self, qbl_data, field_usage):
        fields_processed = 0
        
        for app_data in self.navigator.get_applications(qbl_data):
            self.tracker.set_source_app(app_data["key"])
            for table_data in self.navigator.get_tables(app_data):
                fields_processed += self._analyze_table_custom_rules(table_data, field_usage)
        
        self.log_analysis_complete(fields_processed)
    
    def _analyze_table_custom_rules(self, table_data, field_usage):
        fields_found = 0
        table_key = table_data["key"]
        
        try:
            table_props = PropertyExtractor(table_data["data"])
            
            custom_rules = table_props.safe_get("CustomDataRules", default={})
            
            if isinstance(custom_rules, dict):
                formula = custom_rules.get("Formula", "")
                
                if formula and isinstance(formula, str):
                    referenced_fields = self.fields_named_by_formula(
                        formula, self.build_field_label_mapping(table_data)
                    )

                    for ref_field in referenced_fields:
                        if self.tracker.mark_used_if_exists(field_usage, ref_field, "Used in Custom Data Rules"):
                            fields_found += 1
                            
        except Exception as e:
            print(f"Error analyzing custom data rules for table {table_key}: {e}")
        
        return fields_found
