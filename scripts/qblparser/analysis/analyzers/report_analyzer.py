from qblparser.analysis.base_analyzer import BaseAnalyzer
from qblparser.utils.helpers import FieldExtractor
from qblparser.utils.property_extractor import PropertyExtractor

class ReportAnalyzer(BaseAnalyzer):
    
    def get_analysis_name(self):
        return "Report Usage Analysis"
    
    def get_priority(self):
        return 10
    
    def get_description(self):
        return "Analyzes field usage in report columns, filters, sorting, and grouping"
    
    def analyze(self, qbl_data, field_usage):
        fields_processed = 0
        
        for app_data in self.navigator.get_applications(qbl_data):
            self.tracker.set_source_app(app_data["key"])
            for table_data in self.navigator.get_tables(app_data):
                for report_data in self.navigator.get_reports(table_data):
                    fields_processed += self._analyze_single_report(report_data, field_usage, table_data)
        
        self.log_analysis_complete(fields_processed)
    
    def _build_field_id_mapping(self, table_data):
        field_mapping = {}
        
        try:
            fields = table_data["data"].get("Fields", {})
            
            for logical_id, field_value in fields.items():
                if isinstance(field_value, dict):
                    field_props = PropertyExtractor(field_value)
                    field_id = field_props.id()
                    
                    if field_id and field_id != "N/A":
                        field_mapping[str(field_id)] = logical_id
                        
        except Exception as e:
            print(f"Error building field ID mapping for table {table_data.get('key', 'unknown')}: {e}")
        
        return field_mapping
    
    def _analyze_report_columns(self, report_data, field_usage, table_data):
        fields_found = 0
        
        columns = self.navigator.get_report_columns(report_data)
        
        if isinstance(columns, list):
            for col in columns:
                try:
                    field_ref = FieldExtractor.from_reference(col)
                    if self.tracker.mark_used_if_exists(field_usage, field_ref, "Used in Reports"):
                        fields_found += 1
                except Exception:
                    continue
        else:
            fields_found += self._analyze_default_columns(table_data, field_usage)
        
        return fields_found
    
    def _analyze_default_columns(self, table_data, field_usage):
        fields_found = 0
        
        try:
            fields = table_data["data"].get("Fields", {})
            
            for field_ref, field_def in fields.items():
                field_props = PropertyExtractor(field_def)
                field_type = field_props.type()
                
                should_include = (
                    field_props.get("AddToAllNewReports", False) or
                    
                    field_type in [
                        "QB::Field::RecordId", 
                        "QB::Field::DateCreated", 
                        "QB::Field::DateModified",
                        "QB::Field::LastModifiedBy",
                        "QB::Field::RecordOwner"
                    ] or
                    
                    field_props.allowed_in_reports() is True or
                    
                    field_props.is_required() is True
                )
                
                if should_include:
                    if self.tracker.mark_used_if_exists(field_usage, field_ref, "Used in Reports"):
                        fields_found += 1
                        
        except Exception as e:
            print(f"Error analyzing default columns: {e}")
        
        return fields_found
    
    def _analyze_report_filters(self, report_data, field_usage, field_id_to_logical_id):
        fields_found = 0
        
        filters = self.navigator.get_report_filters(report_data)
        if filters:
            try:
                filter_field_ids = self._extract_field_ids_from_criteria(filters)
                
                for field_id in filter_field_ids:
                    logical_id = field_id_to_logical_id.get(field_id)
                    if logical_id and self.tracker.mark_used_if_exists(field_usage, logical_id, "Used in Reports"):
                        fields_found += 1
                        
            except Exception as e:
                print(f"Error analyzing report filters: {e}")
        
        return fields_found
    
    def _extract_field_ids_from_criteria(self, criteria):
        import re
        
        try:
            if not isinstance(criteria, str) or not criteria.strip():
                return []
            
            field_id_pattern = r"\{'(\d+)'\."
            
            field_ids = re.findall(field_id_pattern, criteria)
            
            unique_field_ids = list(dict.fromkeys(field_ids))
            
            return unique_field_ids
            
        except Exception as e:
            print(f"Error extracting field IDs from criteria: {e}")
            return []
    
    def _analyze_report_sorting(self, report_data, field_usage):
        fields_found = 0
        
        try:
            props = PropertyExtractor(report_data["data"])
            
            sort_info = props.get("Sort", [])
            if isinstance(sort_info, list):
                for sort_item in sort_info:
                    field_ref = FieldExtractor.from_reference(sort_item)
                    if self.tracker.mark_used_if_exists(field_usage, field_ref, "Used in Reports"):
                        fields_found += 1
            
        except Exception as error:
            print(f"Error in report_analyzer._analyze_report_sorting: {error}")
        
        return fields_found
    
    def _analyze_report_grouping(self, report_data, field_usage):
        fields_found = 0
        
        try:
            props = PropertyExtractor(report_data["data"])

            group_fields = FieldExtractor.from_grouping(props.get("SortAndGroup"))
            for field_ref in group_fields:
                if self.tracker.mark_used_if_exists(field_usage, field_ref, "Used in Reports"):
                    fields_found += 1

        except Exception as error:
            print(f"Error analyzing report grouping for {report_data.get('key', '')}: {error}")

        return fields_found
    
    def _analyze_calendar_fields(self, report_data, field_usage):
        fields_found = 0
        
        try:
            props = PropertyExtractor(report_data["data"])
            
            calendar_fields = [
                props.get("StartDate"),
                props.get("EndDate"), 
                props.get("AddressField")
            ]
            
            for field_ref in calendar_fields:
                field_ref = FieldExtractor.from_reference(field_ref)
                if self.tracker.mark_used_if_exists(field_usage, field_ref, "Used in Reports"):
                    fields_found += 1
        
        except Exception as error:
            print(f"Error in report_analyzer._analyze_calendar_fields: {error}")
        
        return fields_found
    
    def _analyze_dynamic_filters(self, report_data, field_usage):
        fields_found = 0
        
        try:
            props = PropertyExtractor(report_data["data"])
            
            filters = props.get("Filters", {})
            if not isinstance(filters, dict):
                return fields_found
            
            dynamic_fields = filters.get("DynamicFields", "Default")
            
            if dynamic_fields == "Default" or dynamic_fields is None:
                return fields_found
            
            if isinstance(dynamic_fields, list):
                for field_item in dynamic_fields:
                    if isinstance(field_item, dict) and field_item.get("__bad_ref__"):
                        continue
                    
                    field_ref = None
                    if isinstance(field_item, dict):
                        field_ref = field_item.get("Field", "")
                    elif isinstance(field_item, str):
                        field_ref = field_item
                    
                    if field_ref and isinstance(field_ref, str) and field_ref.startswith("$Field_"):
                        if self.tracker.mark_used_if_exists(field_usage, field_ref, "Used in Report Dynamic Filters"):
                            fields_found += 1
        
        except Exception as e:
            print(f"Error analyzing dynamic filters: {e}")
        
        return fields_found

    def _analyze_single_report(self, report_data, field_usage, table_data):
        fields_found = 0
        
        try:
            field_id_to_logical_id = self._build_field_id_mapping(table_data)
            
            fields_found += self._analyze_report_columns(report_data, field_usage, table_data)
            
            fields_found += self._analyze_report_filters(report_data, field_usage, field_id_to_logical_id)
            
            fields_found += self._analyze_report_sorting(report_data, field_usage)
            
            fields_found += self._analyze_report_grouping(report_data, field_usage)
            
            fields_found += self._analyze_calendar_fields(report_data, field_usage)
            
            fields_found += self._analyze_dynamic_filters(report_data, field_usage)
            
        except Exception as e:
            print(f"Error analyzing report {report_data.get('key', 'unknown')}: {e}")
        
        return fields_found

        
