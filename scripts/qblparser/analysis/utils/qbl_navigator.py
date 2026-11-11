from qblparser.utils.property_extractor import PropertyExtractor

class QBLNavigator:

    def __init__(self, tracker=None):
        self.tracker = tracker
    
    def get_applications(self, qbl_data):
        resources = qbl_data.get("Resources", {})
        for app_key, app_value in resources.items():
            if app_key.startswith("$App_"):
                yield {"key": app_key, "data": app_value}
    
    def get_tables(self, app_data):
        tables = app_data["data"].get("Tables", {})
        for table_key, table_value in tables.items():
            if self.tracker is not None:
                self.tracker.set_source_table(table_key)
            yield {"key": table_key, "data": table_value}
        if self.tracker is not None:
            self.tracker.set_source_table("")
    
    def get_reports(self, table_data):
        reports = table_data["data"].get("Reports", {})
        for report_key, report_value in reports.items():
            yield {"key": report_key, "data": report_value}
    
    def get_forms(self, table_data):
        forms = table_data["data"].get("Forms", {}).get("Resources", {})
        for form_key, form_value in forms.items():
            yield {"key": form_key, "data": form_value}
    
    def get_fields(self, table_data):
        fields = table_data["data"].get("Fields", {})
        for field_key, field_value in fields.items():
            yield {"key": field_key, "data": field_value}
    
    def get_charts(self, table_data):
        charts = table_data["data"].get("Charts", {})
        for chart_key, chart_value in charts.items():
            yield {"key": chart_key, "data": chart_value}
    
    def get_dashboards(self, app_data):
        pages = app_data["data"].get("Pages", {})
        
        if isinstance(pages, dict) and "Resources" in pages:
            dashboards_root = pages["Resources"]
        else:
            dashboards_root = pages
        
        for dashboard_key, dashboard_value in dashboards_root.items():
            if dashboard_key.startswith("$Dashboard_"):
                yield {"key": dashboard_key, "data": dashboard_value}
    
    def get_dashboard_widgets(self, dashboard_data):
        tabs = dashboard_data["data"].get("Tabs", {})
        for tab_key, tab_value in tabs.items():
            widgets = tab_value.get("Widgets", {})
            for widget_key, widget_value in widgets.items():
                yield {
                    "key": widget_key, 
                    "data": widget_value,
                    "tab_key": tab_key
                }
    
    def get_report_columns(self, report_data):
        props = PropertyExtractor(report_data["data"])
        return props.get("Columns", [])
    
    def get_report_filters(self, report_data):
        props = PropertyExtractor(report_data["data"])
        return props.safe_get("Filters", "Criteria", default="")
    
    def get_form_rules(self, form_data):
        form_key = form_data["key"]
        form_value = form_data["data"]
        
        is_form_v2 = form_key.startswith("$FormV2_")
        rules_node = form_value.get("Rules", {} if is_form_v2 else [])
        
        if is_form_v2 and isinstance(rules_node, dict):
            for rule_key, rule_value in rules_node.items():
                if isinstance(rule_value, dict):
                    yield {"key": rule_key, "data": rule_value, "is_v2": True}
        
        elif not is_form_v2 and isinstance(rules_node, list):
            for rule_index, rule_value in enumerate(rules_node):
                if isinstance(rule_value, dict):
                    yield {"key": f"Rule_{rule_index}", "data": rule_value, "is_v2": False}
