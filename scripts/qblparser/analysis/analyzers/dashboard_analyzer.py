from qblparser.analysis.base_analyzer import BaseAnalyzer
from qblparser.utils.helpers import FieldExtractor
from qblparser.utils.property_extractor import PropertyExtractor

class DashboardAnalyzer(BaseAnalyzer):
    
    def get_analysis_name(self):
        return "Dashboard Usage Analysis"
    
    def get_priority(self):
        return 70
    
    def get_description(self):
        return "Analyzes field usage in dashboard widgets, KPIs, and search configurations"
    
    def analyze(self, qbl_data, field_usage):
        fields_processed = 0
        
        for app_data in self.navigator.get_applications(qbl_data):
            self.tracker.set_source_app(app_data["key"])
            for dashboard_data in self.navigator.get_dashboards(app_data):
                for widget_data in self.navigator.get_dashboard_widgets(dashboard_data):
                    fields_processed += self._analyze_dashboard_widget(widget_data, field_usage)
        
        self.log_analysis_complete(fields_processed)
    
    def _analyze_dashboard_widget(self, widget_data, field_usage):
        fields_found = 0
        widget_key = widget_data["key"]
        widget_value = widget_data["data"]
        
        try:
            widget_props = PropertyExtractor(widget_value)
            widget_type = widget_props.type()
            
            if "Kpi" in widget_type:
                fields_found += self._analyze_kpi_widget(widget_props, field_usage)
            
            elif "Search" in widget_type:
                fields_found += self._analyze_search_widget(widget_props, field_usage)
            
                        
        except Exception as e:
            print(f"Error analyzing dashboard widget {widget_key}: {e}")
        
        return fields_found
    
    def _analyze_kpi_widget(self, widget_props, field_usage):
        fields_found = 0
        
        try:
            field_ref = widget_props.get("Field")
            field_ref = FieldExtractor.from_reference(field_ref)
            
            if self.tracker.mark_used_if_exists(field_usage, field_ref, "Used in Dashboards"):
                fields_found += 1
                
        except Exception as error:
            print(f"Error in dashboard_analyzer._analyze_kpi_widget: {error}")
        
        return fields_found
    
    def _analyze_search_widget(self, widget_props, field_usage):
        fields_found = 0
        
        try:
            search_fields = widget_props.get("SearchFields", [])
            
            if isinstance(search_fields, list):
                for field_ref in search_fields:
                    field_ref = FieldExtractor.from_reference(field_ref)
                    if self.tracker.mark_used_if_exists(field_usage, field_ref, "Used in Dashboards"):
                        fields_found += 1
                        
        except Exception as error:
            print(f"Error in dashboard_analyzer._analyze_search_widget: {error}")
        
        return fields_found
