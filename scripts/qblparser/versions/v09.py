from .v07 import QBLv07Handler
from qblparser.parsing_registry import PARSING_REGISTRY

class QBLv09Handler(QBLv07Handler):
    
    def get_version(self):
        return "0.9"
    
    def get_supported_entities(self):
        entities = super().get_supported_entities()
        entities.extend(["pipelines", "pipeline_steps", "pipeline_table_matrix", "field_pipeline_matrix"])
        return entities
    
    def parse_qbl(self, qbl_data):
        parsed_entities = super().parse_qbl(qbl_data)
        
        parsed_entities["pipelines"] = self._parse_pipelines(qbl_data)
        parsed_entities["pipeline_steps"] = self._parse_pipeline_steps(qbl_data)
        parsed_entities["pipeline_table_matrix"] = self._parse_pipeline_table_matrix(qbl_data)
        parsed_entities["field_pipeline_matrix"] = self._parse_field_pipeline_matrix(qbl_data)
        
        return parsed_entities
    
    def _parse_pipelines(self, qbl_data):
        pipelines = []
        resources = qbl_data.get("Resources", {})
        
        for resource_key, resource_value in resources.items():
            if resource_key.startswith("$Pipeline_"):
                try:
                    pipeline_data = PARSING_REGISTRY["pipeline"](
                        resource_key, resource_value, self.identifier_index, qbl_data
                    )
                    pipelines.append(pipeline_data)
                except Exception as e:
                    print(f"Error parsing pipeline {resource_key}: {e}")
                    continue
        
        return pipelines
    
    def _parse_pipeline_steps(self, qbl_data):
        pipeline_steps = []
        resources = qbl_data.get("Resources", {})
        
        for resource_key, resource_value in resources.items():
            if resource_key.startswith("$Pipeline_"):
                try:
                    step_data = PARSING_REGISTRY["pipeline_steps"](
                        resource_key, resource_value, self.identifier_index, qbl_data
                    )
                    pipeline_steps.extend(step_data)
                except Exception as e:
                    print(f"Error parsing pipeline steps for {resource_key}: {e}")
                    continue
        
        return pipeline_steps
    
    def _parse_pipeline_table_matrix(self, qbl_data):
        pipeline_table_matrix = []
        resources = qbl_data.get("Resources", {})
        
        for resource_key, resource_value in resources.items():
            if resource_key.startswith("$Pipeline_"):
                try:
                    table_matrix_data = PARSING_REGISTRY["pipeline_table_matrix"](
                        resource_key, resource_value, self.identifier_index, self.table_schema, qbl_data
                    )
                    pipeline_table_matrix.extend(table_matrix_data)
                except Exception as e:
                    print(f"Error parsing pipeline table matrix for {resource_key}: {e}")
                    continue
        
        return pipeline_table_matrix
    

    def _parse_field_pipeline_matrix(self, qbl_data):
        try:
            field_pipeline_matrix = PARSING_REGISTRY["field_pipeline_matrix"](
                qbl_data, self.identifier_index, self.table_schema
            )
            return field_pipeline_matrix
        except Exception as e:
            print(f"Error parsing field-to-pipeline matrix: {e}")
            return []
