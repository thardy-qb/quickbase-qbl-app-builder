from qblparser.analysis.base_analyzer import BaseAnalyzer
from qblparser.utils.helpers import extract_fields

class FormAnalyzer(BaseAnalyzer):
    
    def get_analysis_name(self):
        return "Form Usage Analysis"
    
    def get_priority(self):
        return 20
    
    def get_description(self):
        return "Analyzes field usage in form elements across legacy and FormV2 structures"
    
    def analyze(self, qbl_data, field_usage):
        fields_processed = 0
        
        for app_data in self.navigator.get_applications(qbl_data):
            self.tracker.set_source_app(app_data["key"])
            for table_data in self.navigator.get_tables(app_data):
                for form_data in self.navigator.get_forms(table_data):
                    fields_processed += self._analyze_single_form(form_data, field_usage)
        
        self.log_analysis_complete(fields_processed)
    
    def _analyze_single_form(self, form_data, field_usage):
        fields_found = 0
        form_key = form_data["key"]
        form_value = form_data["data"]
        
        try:
            if form_key.startswith("$FormV2_"):
                fields_found += self._analyze_formv2_structure(form_value, field_usage)
            else:
                fields_found += self._analyze_legacy_form_structure(form_value, field_usage)
                
        except Exception as e:
            print(f"Error analyzing form {form_key}: {e}")
        
        return fields_found
    
    def _analyze_formv2_structure(self, form_value, field_usage):
        fields_found = 0
        
        pages = form_value.get("Pages", {})
        if isinstance(pages, dict):
            for page_key, page_value in pages.items():
                sections = page_value.get("Sections", {})
                if isinstance(sections, dict):
                    for section_key, section_value in sections.items():
                        columns = section_value.get("Columns", {})
                        if isinstance(columns, dict):
                            for column_key, column_value in columns.items():
                                elements = column_value.get("Elements", {})
                                if isinstance(elements, dict):
                                    fields_found += self._extract_fields_from_elements(
                                        elements, field_usage
                                    )
        
        layout = form_value.get("Layout", {})
        if layout:
            fields_found += self._extract_fields_from_elements(layout, field_usage)
        
        return fields_found
    
    def _analyze_legacy_form_structure(self, form_value, field_usage):
        fields_found = 0
        
        elements = form_value.get("Elements", {})
        if isinstance(elements, dict):
            elements = list(elements.values())
        elif not isinstance(elements, list):
            elements = []
        
        fields_found += self._extract_fields_from_elements(elements, field_usage)
        
        return fields_found
    
    def _extract_fields_from_elements(self, elements, field_usage):
        fields_found = 0
        
        try:
            field_id_lookup = {}
            form_fields = extract_fields(elements, field_id_lookup)
            
            for field_info in form_fields:
                field_ref = field_info.get("Field", "")
                if self.tracker.mark_used_if_exists(field_usage, field_ref, "Used in Forms"):
                    fields_found += 1
                    
        except Exception as e:
            print(f"Error extracting fields from form elements: {e}")
        
        return fields_found
