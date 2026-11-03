from qblparser.analysis.base_analyzer import BaseAnalyzer
from qblparser.utils.helpers import FieldExtractor
from qblparser.utils.property_extractor import PropertyExtractor

class FieldPropertyAnalyzer(BaseAnalyzer):
    
    def get_analysis_name(self):
        return "Field Property Usage Analysis"
    
    def get_priority(self):
        return 90
    
    def get_description(self):
        return "Analyzes field usage in field properties like default values and conditional formatting"
    
    def analyze(self, qbl_data, field_usage):
        fields_processed = 0
        
        for app_data in self.navigator.get_applications(qbl_data):
            self.tracker.set_source_app(app_data["key"])
            for table_data in self.navigator.get_tables(app_data):
                for field_data in self.navigator.get_fields(table_data):
                    fields_processed += self._analyze_field_properties(field_data, field_usage)
        
        self.log_analysis_complete(fields_processed)
    
    def _analyze_field_properties(self, field_data, field_usage):
        fields_found = 0
        field_key = field_data["key"]
        field_value = field_data["data"]
        
        try:
            field_props = PropertyExtractor(field_value)
            
            fields_found += self._analyze_default_value(field_props, field_usage)
            
            fields_found += self._analyze_conditional_values(field_props, field_usage)
                        
        except Exception as e:
            print(f"Error analyzing field properties for {field_key}: {e}")
        
        return fields_found
    
    def _analyze_default_value(self, field_props, field_usage):
        fields_found = 0
        
        try:
            default_value = field_props.default_value("")
            
            if default_value and isinstance(default_value, str):
                referenced_fields = FieldExtractor.from_formula(default_value)
                
                for ref_field in referenced_fields:
                    if self.tracker.mark_used_if_exists(field_usage, ref_field, "Used in Field Properties"):
                        fields_found += 1
                        
        except Exception as error:
            print(f"Error in field_analyzer._analyze_default_value: {error}")
        
        return fields_found
    
    def _analyze_conditional_values(self, field_props, field_usage):
        fields_found = 0
        
        try:
            reference_props = field_props.safe_get("Reference", default={})
            conditional_values = reference_props.get("ConditionalValues", [])
            
            if isinstance(conditional_values, list):
                for condition in conditional_values:
                    if isinstance(condition, dict):
                        condition_formula = condition.get("When", "")
                        
                        if condition_formula and isinstance(condition_formula, str):
                            referenced_fields = FieldExtractor.from_formula(condition_formula)
                            
                            for ref_field in referenced_fields:
                                if self.tracker.mark_used_if_exists(field_usage, ref_field, "Used in Field Properties"):
                                    fields_found += 1
                                    
        except Exception as error:
            print(f"Error in field_analyzer._analyze_conditional_values: {error}")
        
        return fields_found
