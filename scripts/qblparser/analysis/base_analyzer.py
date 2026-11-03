from abc import ABC, abstractmethod
from qblparser.analysis.utils.qbl_navigator import QBLNavigator
from qblparser.analysis.utils.usage_tracker import UsageTracker
from qblparser.utils.helpers import FieldExtractor
from qblparser.utils.property_extractor import PropertyExtractor

class BaseAnalyzer(ABC):
    
    def __init__(self, navigator: QBLNavigator = None, tracker: UsageTracker = None):
        self.navigator = navigator or QBLNavigator()
        self.tracker = tracker or UsageTracker()
        self._enabled = True
    
    @abstractmethod
    def analyze(self, qbl_data, usage_dict):
        pass
    
    @abstractmethod
    def get_analysis_name(self):
        pass
    
    def get_priority(self):
        return 50
    
    def is_enabled(self):
        return getattr(self, '_enabled', True)
    
    def get_description(self):
        return f"Analyzes usage for {self.get_analysis_name()}"
    
    def build_field_label_mapping(self, table_data):
        field_mapping = {}

        try:
            fields = table_data["data"].get("Fields", {})

            for logical_id, field_value in fields.items():
                if isinstance(field_value, dict):
                    field_label = PropertyExtractor(field_value).label()

                    if field_label:
                        field_mapping[field_label] = logical_id

        except Exception as e:
            print(f"Error building field label mapping for table {table_data.get('key', 'unknown')}: {e}")

        return field_mapping

    def build_field_id_mapping(self, table_data):
        field_mapping = {}

        try:
            fields = table_data["data"].get("Fields", {})

            for logical_id, field_value in fields.items():
                if isinstance(field_value, dict):
                    numeric_id = field_value.get("Id")
                    if numeric_id is not None:
                        field_mapping[str(numeric_id)] = logical_id

        except Exception as e:
            print(f"Error building field id mapping for table {table_data.get('key', 'unknown')}: {e}")

        return field_mapping

    def fields_named_by_criteria(self, criteria, field_id_to_logical_id,
                                 field_label_to_logical_id=None):
        resolved = []
        for field_id in FieldExtractor.from_query_criteria(criteria):
            logical_id = field_id_to_logical_id.get(field_id)
            if logical_id and logical_id not in resolved:
                resolved.append(logical_id)

        if field_label_to_logical_id:
            for logical_id in self.fields_named_by_formula(criteria, field_label_to_logical_id):
                if logical_id not in resolved:
                    resolved.append(logical_id)

        return resolved

    def fields_named_by_formula(self, formula, field_label_to_logical_id):
        try:
            if not isinstance(formula, str) or not formula.strip():
                return []

            referenced_logical_ids = []

            for field_ref in FieldExtractor.from_formula(formula):
                if field_ref.startswith("$Field_"):
                    referenced_logical_ids.append(field_ref)
                elif field_ref in field_label_to_logical_id:
                    referenced_logical_ids.append(field_label_to_logical_id[field_ref])

            return referenced_logical_ids

        except Exception as e:
            print(f"Error extracting fields from formula: {e}")
            return []

    def log_analysis_complete(self, items_processed=None):
        pass
    
    def safe_analyze(self, qbl_data, usage_dict):
        if not self.is_enabled():
            return True
        
        try:
            self.analyze(qbl_data, usage_dict)
            return True
        except Exception as e:
            print(f"Error in {self.get_analysis_name()}: {e}")
            return False
    
    def __str__(self):
        return f"{self.__class__.__name__}(priority={self.get_priority()}, enabled={self.is_enabled()})"
    
    def __repr__(self):
        return self.__str__()
