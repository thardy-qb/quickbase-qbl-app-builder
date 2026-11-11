from qblparser.analysis.base_analyzer import BaseAnalyzer
from qblparser.utils.helpers import report_field_uses

class ChartAnalyzer(BaseAnalyzer):

    def get_analysis_name(self):
        return "Chart Usage Analysis"

    def get_priority(self):
        return 80

    def get_description(self):
        return "Analyzes field usage in chart data series, axes, grouping and filters"

    def analyze(self, qbl_data, field_usage):
        fields_processed = 0

        for app_data in self.navigator.get_applications(qbl_data):
            self.tracker.set_source_app(app_data["key"])
            for table_data in self.navigator.get_tables(app_data):
                field_ids = self.build_field_id_mapping(table_data)
                for chart_data in self.navigator.get_charts(table_data):
                    fields_processed += self._analyze_single_chart(
                        chart_data, field_usage, field_ids)

        self.log_analysis_complete(fields_processed)

    def _analyze_single_chart(self, chart_data, field_usage, field_ids=None):
        fields_found = 0
        chart_key = chart_data["key"]
        chart_value = chart_data["data"]

        try:
            for field_ref, _used_as in report_field_uses(chart_value, field_ids=field_ids or {}):
                if self.tracker.mark_used_if_exists(field_usage, field_ref, "Used in Charts"):
                    fields_found += 1
        except Exception as e:
            print(f"Error analyzing chart {chart_key}: {e}")

        return fields_found
