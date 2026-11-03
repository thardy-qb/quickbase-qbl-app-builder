from .v09 import QBLv09Handler
from .v11 import parse_guides, parse_page_widgets, parse_pages
from qblparser.parsing_registry import PARSING_REGISTRY

class QBLv012Handler(QBLv09Handler):

    def get_version(self):
        return "0.12"

    def get_supported_entities(self):
        entities = super().get_supported_entities()
        entities.extend(["pages", "guides", "page_widgets"])
        entities.extend([
            "connected_tables",
            "connected_table_fields",
            "connected_table_matrix"
        ])
        return entities

    def parse_qbl(self, qbl_data):
        parsed_entities = super().parse_qbl(qbl_data)

        parsed_entities["pages"] = self._parse_pages(qbl_data)
        parsed_entities["guides"] = self._parse_guides(qbl_data)
        parsed_entities["page_widgets"] = self._parse_page_widgets(qbl_data)

        connected_nodes = self._collect_connected_table_nodes(qbl_data)

        parsed_entities["connected_tables"] = self._parse_connected_tables(qbl_data, connected_nodes)
        parsed_entities["connected_table_fields"] = self._parse_connected_table_fields(qbl_data, connected_nodes)
        parsed_entities["connected_table_matrix"] = self._parse_connected_table_matrix(qbl_data, connected_nodes)

        return parsed_entities

    def _parse_pages(self, qbl_data):
        return parse_pages(qbl_data, self.identifier_index)

    def _parse_guides(self, qbl_data):
        return parse_guides(qbl_data, self.identifier_index)

    def _parse_page_widgets(self, qbl_data):
        return parse_page_widgets(qbl_data, self.identifier_index)

    def _parse_connected_tables(self, qbl_data, connected_nodes):
        connected_tables = []

        for node in connected_nodes:
            try:
                ct_data = PARSING_REGISTRY["connected_table"](
                    node["table_key"],
                    node["table_value"],
                    self.identifier_index,
                    self.table_schema,
                    node["app_key"],
                    connected_data=node["connected_data"],
                    qbl_resources=qbl_data,
                )
                if ct_data:
                    connected_tables.append(ct_data)
            except Exception as e:
                print(f"Error parsing connected table {node['table_key']}: {e}")
                continue

        return connected_tables

    def _parse_connected_table_fields(self, qbl_data, connected_nodes):
        connected_table_fields = []

        for node in connected_nodes:
            try:
                field_data = PARSING_REGISTRY["connected_table_fields"](
                    node["table_key"],
                    node["table_value"],
                    self.identifier_index,
                    self.table_schema,
                    node["app_key"],
                    connected_data=node["connected_data"],
                    qbl_resources=qbl_data,
                )
                if field_data:
                    if isinstance(field_data, list):
                        connected_table_fields.extend(field_data)
                    else:
                        connected_table_fields.append(field_data)
            except Exception as e:
                print(f"Error parsing connected table fields for {node['table_key']}: {e}")
                continue

        return connected_table_fields

    def _parse_connected_table_matrix(self, qbl_data, connected_nodes):
        try:
            connected_table_matrix = PARSING_REGISTRY["connected_table_matrix"](
                qbl_data,
                self.identifier_index,
                self.table_schema,
                "",
                connected_entries=connected_nodes,
                qbl_resources=qbl_data,
            )
            return connected_table_matrix
        except Exception as e:
            print(f"Error parsing connected table matrix: {e}")
            return []

    def _collect_connected_table_nodes(self, qbl_data):
        connected_nodes = []
        resources = qbl_data.get("Resources", {})

        for app_key, app_value in resources.items():
            if not isinstance(app_value, dict):
                continue

            tables = app_value.get("Tables", {})
            for table_key, table_value in tables.items():
                if not isinstance(table_value, dict):
                    continue

                connected_data = table_value.get("Properties", {}).get("ConnectedData")
                if connected_data:
                    connected_nodes.append({
                        "app_key": app_key,
                        "table_key": table_key,
                        "table_value": table_value,
                        "connected_data": connected_data,
                    })

        return connected_nodes
