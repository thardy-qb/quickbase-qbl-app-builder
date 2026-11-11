from qblparser.analysis.analyzers.role_analyzer import RoleAnalyzer
from qblparser.analysis.utils.qbl_navigator import QBLNavigator
from qblparser.analysis.utils.usage_tracker import UsageTracker
from qblparser.analysis.analyzers.report_analyzer import ReportAnalyzer
from qblparser.analysis.analyzers.form_analyzer import FormAnalyzer
from qblparser.analysis.analyzers.rule_analyzer import RuleAnalyzer
from qblparser.analysis.analyzers.custom_data_rule_analyzer import CustomDataRuleAnalyzer
from qblparser.analysis.analyzers.formula_analyzer import FormulaAnalyzer
from qblparser.analysis.analyzers.relationship_analyzer import RelationshipAnalyzer
from qblparser.analysis.analyzers.dashboard_analyzer import DashboardAnalyzer
from qblparser.analysis.analyzers.chart_analyzer import ChartAnalyzer
from qblparser.analysis.analyzers.field_analyzer import FieldPropertyAnalyzer
from qblparser.analysis.analyzers.permission_analyzer import PermissionAnalyzer

class UsageCoordinator:
    
    def __init__(self):
        self.tracker = UsageTracker()
        self.navigator = QBLNavigator(self.tracker)
        self.analyzers = self._create_analyzers()
    
    def _create_analyzers(self):
        analyzers = [
            ReportAnalyzer(self.navigator, self.tracker),
            FormAnalyzer(self.navigator, self.tracker),
            RuleAnalyzer(self.navigator, self.tracker),
            CustomDataRuleAnalyzer(self.navigator, self.tracker),
            FormulaAnalyzer(self.navigator, self.tracker),
            RelationshipAnalyzer(self.navigator, self.tracker),
            DashboardAnalyzer(self.navigator, self.tracker),
            ChartAnalyzer(self.navigator, self.tracker),
            FieldPropertyAnalyzer(self.navigator, self.tracker),
            PermissionAnalyzer(self.navigator, self.tracker),
            RoleAnalyzer(self.navigator, self.tracker)
        ]
        
        return sorted(analyzers, key=lambda x: x.get_priority())
    
    def analyze_comprehensive_usage(self, app_key, app_value, items, item_usage, analyzer_type="fields", full_qbl_data=None):
        qbl_data = {"Resources": {app_key: app_value}}
        self.tracker.set_target_app(app_key)
        
        relevant_analyzers = self.analyzers
        if analyzer_type == "roles":
            relevant_analyzers = [a for a in self.analyzers if isinstance(a, RoleAnalyzer)]
        
        successful_analyses = 0
        total_analyses = len([a for a in relevant_analyzers if a.is_enabled()])
        
        try:
            for analyzer in relevant_analyzers:
                if analyzer.safe_analyze(qbl_data, item_usage):
                    successful_analyses += 1
                    
                    categories = self.tracker.get_usage_categories()
                    used_count = sum(
                        1 for item_data in item_usage.values()
                        if any(item_data.get(category, False) for category in categories)
                    )
        finally:
            self.tracker.clear_context()

        return item_usage
    
    def get_usage_summary(self, usage_dict):
        return self.tracker.get_usage_summary(usage_dict)
