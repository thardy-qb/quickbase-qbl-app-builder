from qblparser.analysis.base_analyzer import BaseAnalyzer
from qblparser.utils.property_extractor import PropertyExtractor

class RelationshipAnalyzer(BaseAnalyzer):
    
    def get_analysis_name(self):
        return "Relationship Usage Analysis"
    
    def get_priority(self):
        return 60
    
    def get_description(self):
        return "Analyzes field usage in Reference and Lookup field relationships"
    
    def analyze(self, qbl_data, field_usage):
        fields_processed = 0
        
        for app_data in self.navigator.get_applications(qbl_data):
            self.tracker.set_source_app(app_data["key"])
            for table_data in self.navigator.get_tables(app_data):
                for field_data in self.navigator.get_fields(table_data):
                    fields_processed += self._analyze_field_relationships(field_data, field_usage, table_data)
        
        self.log_analysis_complete(fields_processed)
    
    def _analyze_field_relationships(self, field_data, field_usage, table_data):
        fields_found = 0
        field_key = field_data["key"]
        field_value = field_data["data"]
        
        try:
            field_props = PropertyExtractor(field_value)
            field_type = field_props.type()
            
            if field_type == "QB::Field::Reference":
                fields_found += self._analyze_reference_field(field_key, field_props, field_usage, table_data)
            
            elif field_type == "QB::Field::Lookup":
                fields_found += self._analyze_lookup_field(field_key, field_props, field_usage, table_data)
                
        except Exception as e:
            print(f"Error analyzing relationships for field {field_key}: {e}")
        
        return fields_found
    
    def _analyze_reference_field(self, field_key, field_props, field_usage, table_data):
        fields_found = 0
        
        if self.tracker.mark_used_if_exists(field_usage, field_key, "Used in Relationships"):
            fields_found += 1
        
        try:
            reference = field_props.safe_get("Reference", default={})
            if isinstance(reference, dict):
                proxy = reference.get("Proxy", {})
                proxy_field = None
                
                if isinstance(proxy, dict):
                    proxy_field = proxy.get("Field")
                elif isinstance(proxy, str):
                    proxy_field = proxy
                    
                if proxy_field and isinstance(proxy_field, str) and proxy_field.startswith("$Field_"):
                    if self.tracker.mark_used_if_exists(field_usage, proxy_field, "Used in Relationships"):
                        fields_found += 1
        except Exception as error:
            print(f"Error in relationship_analyzer._analyze_reference_field: {error}")

        try:
            relationship_ref = field_props.safe_get("Reference", "Relationship", default={})
            relationship_key = self._extract_relationship_key(relationship_ref)
            if relationship_key and self._is_cross_app_relationship(table_data, relationship_key):
                if self.tracker.mark_used_if_exists(field_usage, field_key, "Cross-App References"):
                    fields_found += 1
        except Exception as error:
            print(f"Error in relationship_analyzer._analyze_reference_field: {error}")
        
        return fields_found
    
    def _analyze_lookup_field(self, field_key, field_props, field_usage, table_data):
        fields_found = 0
        
        if self.tracker.mark_used_if_exists(field_usage, field_key, "Used in Relationships"):
            fields_found += 1
        
        try:
            lookup = field_props.safe_get("Lookup", default={})
            if isinstance(lookup, dict):
                target_field_ref = lookup.get("TargetField", {})
                target_field = None
                
                if isinstance(target_field_ref, dict):
                    target_field = target_field_ref.get("Field")
                elif isinstance(target_field_ref, str):
                    target_field = target_field_ref
                    
                if target_field and isinstance(target_field, str) and target_field.startswith("$Field_"):
                    if self.tracker.mark_used_if_exists(field_usage, target_field, "Used in Relationships"):
                        fields_found += 1
        except Exception as error:
            print(f"Error in relationship_analyzer._analyze_lookup_field: {error}")

        try:
            relationship_ref = field_props.safe_get("Lookup", "Relationship", default={})
            relationship_key = self._extract_relationship_key(relationship_ref)
            if relationship_key and self._is_cross_app_relationship(table_data, relationship_key):
                if self.tracker.mark_used_if_exists(field_usage, field_key, "Cross-App References"):
                    fields_found += 1
        except Exception as error:
            print(f"Error in relationship_analyzer._analyze_lookup_field: {error}")
        
        return fields_found

    def _extract_relationship_key(self, relationship_ref):
        if isinstance(relationship_ref, str):
            return relationship_ref
        if isinstance(relationship_ref, dict):
            rel = relationship_ref.get("Relationship", "")
            if isinstance(rel, str):
                return rel
        return ""

    def _is_cross_app_relationship(self, table_data, relationship_key):
        if not relationship_key:
            return False
        relationships = table_data.get("data", {}).get("Relationships", {})
        if not isinstance(relationships, dict):
            return False

        if relationship_key in relationships and isinstance(relationships[relationship_key], dict):
            rel_type = str(relationships[relationship_key].get("Type", ""))
            return "CrossApp" in rel_type

        candidate = None
        candidate_len = -1
        for rel_key, rel_value in relationships.items():
            if not isinstance(rel_value, dict):
                continue
            if (
                str(rel_key).startswith(relationship_key + "_")
                or relationship_key.startswith(str(rel_key) + "_")
            ):
                if len(str(rel_key)) > candidate_len:
                    candidate = rel_value
                    candidate_len = len(str(rel_key))
        if not isinstance(candidate, dict):
            return False
        rel_type = str(candidate.get("Type", ""))
        return "CrossApp" in rel_type
