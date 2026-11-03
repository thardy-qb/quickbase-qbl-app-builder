from qblparser.analysis.base_analyzer import BaseAnalyzer
from qblparser.utils.property_extractor import PropertyExtractor
import re
from qblparser.utils.helpers import FieldExtractor

class FormulaAnalyzer(BaseAnalyzer):
    
    def get_analysis_name(self):
        return "Formula Usage Analysis"
    
    def get_priority(self):
        return 50
    
    def get_description(self):
        return "Analyzes field usage in field formulas and summary field formulas"
    
    def analyze(self, qbl_data, field_usage):
        fields_processed = 0
        
        for app_data in self.navigator.get_applications(qbl_data):
            self.tracker.set_source_app(app_data["key"])
            for table_data in self.navigator.get_tables(app_data):
                field_label_to_logical_id = self.build_field_label_mapping(table_data)
                
                for field_data in self.navigator.get_fields(table_data):
                    fields_processed += self._analyze_field_formulas(field_data, field_usage, field_label_to_logical_id)
        
        self.log_analysis_complete(fields_processed)
    
    def _analyze_field_formulas(self, field_data, field_usage, field_label_to_logical_id):
        fields_found = 0
        field_key = field_data["key"]
        field_value = field_data["data"]
        
        try:
            field_props = PropertyExtractor(field_value)
            field_type = field_props.type()
            
            formula = field_props.formula()
            if formula:
                referenced_fields = self.fields_named_by_formula(formula, field_label_to_logical_id)
                for ref_field in referenced_fields:
                    if self.tracker.mark_used_if_exists(field_usage, ref_field, "Referenced in Formulas"):
                        fields_found += 1
            
            if field_type == "QB::Field::Summary":
                summary_props = field_props.safe_get("Summary", default={})
                summary_formula = summary_props.get("Formula", "")
                if summary_formula:
                    referenced_fields = self.fields_named_by_formula(summary_formula, field_label_to_logical_id)
                    for ref_field in referenced_fields:
                        if self.tracker.mark_used_if_exists(field_usage, ref_field, "Referenced in Formulas"):
                            fields_found += 1
                            
        except Exception as e:
            print(f"Error analyzing formulas for field {field_key}: {e}")
        
        return fields_found
    
