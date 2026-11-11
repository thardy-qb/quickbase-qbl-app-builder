from qblparser.analysis.base_analyzer import BaseAnalyzer
from qblparser.utils.property_extractor import PropertyExtractor
import re
from qblparser.utils.helpers import FieldExtractor

class PermissionAnalyzer(BaseAnalyzer):
    
    def get_analysis_name(self):
        return "Permission Usage Analysis"
    
    def get_priority(self):
        return 100
    
    def get_description(self):
        return "Analyzes field usage in permission rules, custom access criteria, and field-level role permissions"
    
    def analyze(self, qbl_data, field_usage):
        fields_processed = 0
        
        for app_data in self.navigator.get_applications(qbl_data):
            self.tracker.set_source_app(app_data["key"])
            for table_data in self.navigator.get_tables(app_data):
                field_label_to_logical_id = self.build_field_label_mapping(table_data)
                field_id_to_logical_id = self.build_field_id_mapping(table_data)
                
                fields_processed += self._analyze_table_permissions(
                    table_data, field_usage, field_label_to_logical_id, field_id_to_logical_id)
                
                fields_processed += self._analyze_field_permissions(
                    table_data, field_usage, field_label_to_logical_id, field_id_to_logical_id)
        
        self.log_analysis_complete(fields_processed)
    
    def _analyze_table_permissions(self, table_data, field_usage, field_label_to_logical_id,
                                   field_id_to_logical_id):
        fields_found = 0
        table_key = table_data["key"]
        
        try:
            table_props = PropertyExtractor(table_data["data"])
            role_permissions = table_props.get("RolePermissions", {})
            
            if isinstance(role_permissions, dict):
                for role_key, permissions in role_permissions.items():
                    if isinstance(permissions, dict):
                        fields_found += self._analyze_role_permissions(permissions, field_usage, field_label_to_logical_id,
                                                            field_id_to_logical_id)
                        
        except Exception as e:
            print(f"Error analyzing table permissions for {table_key}: {e}")
        
        return fields_found
    
    def _analyze_field_permissions(self, table_data, field_usage, field_label_to_logical_id,
                                   field_id_to_logical_id):
        fields_found = 0
        table_key = table_data["key"]
        
        try:
            fields = table_data["data"].get("Fields", {})
            
            for field_key, field_value in fields.items():
                if isinstance(field_value, dict):
                    field_props = PropertyExtractor(field_value)
                    field_role_permissions = field_props.get("RolePermissions", {})
                    
                    if isinstance(field_role_permissions, dict) and field_role_permissions:
                        if self.tracker.mark_used_if_exists(field_usage, field_key, "Used in Permissions"):
                            fields_found += 1
                        
                        for role_key, permissions in field_role_permissions.items():
                            if isinstance(permissions, dict):
                                fields_found += self._analyze_role_permissions(permissions, field_usage, field_label_to_logical_id,
                                                            field_id_to_logical_id)
                        
        except Exception as e:
            print(f"Error analyzing field permissions for table {table_key}: {e}")
        
        return fields_found
    
    def _analyze_role_permissions(self, permissions, field_usage, field_label_to_logical_id,
                                  field_id_to_logical_id):
        fields_found = 0
        
        try:
            for perm_key, perm_value in permissions.items():
                if isinstance(perm_value, dict):
                    criteria = perm_value.get("CustomAccessCriteria", "")
                    
                    if criteria and isinstance(criteria, str):
                        referenced_fields = self.fields_named_by_criteria(
                            criteria, field_id_to_logical_id, field_label_to_logical_id
                        )
                        
                        for ref_field in referenced_fields:
                            if self.tracker.mark_used_if_exists(field_usage, ref_field, "Used in Permissions"):
                                fields_found += 1
                                
        except Exception as error:
            print(f"Error in permission_analyzer._analyze_role_permissions: {error}")
        
        return fields_found
    
