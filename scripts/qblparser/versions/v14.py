from .v12 import QBLv012Handler
from qblparser.parsing_registry import PARSING_REGISTRY


class QBLv014Handler(QBLv012Handler):

    def get_version(self):
        return "0.14"

    def get_supported_entities(self):
        entities = super().get_supported_entities()
        entities.extend([
            "custom_emails",
            "custom_email_field_matrix",
            "custom_email_document_matrix",
            "document_templates",
        ])
        return entities

    def parse_qbl(self, qbl_data):
        parsed_entities = super().parse_qbl(qbl_data)

        custom_emails = []
        custom_email_field_matrix = []
        custom_email_document_matrix = []
        document_templates = []

        for app_key, table_key, table_value in self._iter_tables(qbl_data):
            emails = table_value.get("Emails", {})
            if isinstance(emails, dict):
                for email_key, email_value in emails.items():
                    if not email_key.startswith("$CustomEmail_"):
                        continue
                    self._parse_custom_email_node(
                        qbl_data, app_key, table_key, table_value, email_key, email_value,
                        custom_emails, custom_email_field_matrix, custom_email_document_matrix,
                    )

            templates = table_value.get("DocumentTemplates", {})
            if isinstance(templates, dict):
                for dt_key, dt_value in templates.items():
                    if not dt_key.startswith("$DocumentTemplate_"):
                        continue
                    try:
                        document_templates.append(
                            PARSING_REGISTRY["document_template"](
                                dt_key, dt_value, self.identifier_index, self.table_schema,
                                app_key=app_key, table_key=table_key, table_value=table_value,
                                qbl_resources=qbl_data,
                            )
                        )
                    except Exception as e:
                        print(f"Error parsing document template {dt_key}: {e}")
                        continue

        parsed_entities["custom_emails"] = custom_emails
        parsed_entities["custom_email_field_matrix"] = custom_email_field_matrix
        parsed_entities["custom_email_document_matrix"] = custom_email_document_matrix
        parsed_entities["document_templates"] = document_templates

        return parsed_entities

    def _parse_custom_email_node(
        self, qbl_data, app_key, table_key, table_value, email_key, email_value,
        custom_emails, custom_email_field_matrix, custom_email_document_matrix,
    ):
        try:
            custom_emails.append(
                PARSING_REGISTRY["custom_email"](
                    email_key, email_value, self.identifier_index, self.table_schema,
                    app_key=app_key, table_key=table_key, table_value=table_value,
                    qbl_resources=qbl_data,
                )
            )
        except Exception as e:
            print(f"Error parsing custom email {email_key}: {e}")
            return

        try:
            custom_email_field_matrix.extend(
                PARSING_REGISTRY["custom_email_field_matrix"](
                    email_key, email_value, self.identifier_index, self.table_schema,
                    app_key=app_key, table_key=table_key, table_value=table_value,
                    qbl_resources=qbl_data,
                )
            )
        except Exception as e:
            print(f"Error parsing custom email field matrix for {email_key}: {e}")

        try:
            custom_email_document_matrix.extend(
                PARSING_REGISTRY["custom_email_document_matrix"](
                    email_key, email_value, self.identifier_index, self.table_schema,
                    app_key=app_key, table_key=table_key, table_value=table_value,
                    qbl_resources=qbl_data,
                )
            )
        except Exception as e:
            print(f"Error parsing custom email document matrix for {email_key}: {e}")

    @staticmethod
    def _iter_tables(qbl_data):
        resources = qbl_data.get("Resources", {})
        for app_key, app_value in resources.items():
            if not isinstance(app_value, dict) or not app_key.startswith("$App_"):
                continue
            tables = app_value.get("Tables", {})
            if not isinstance(tables, dict):
                continue
            for table_key, table_value in tables.items():
                if isinstance(table_value, dict):
                    yield app_key, table_key, table_value
