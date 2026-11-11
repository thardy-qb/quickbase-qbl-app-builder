from qblparser.entities.fields import parse_field_metadata
from qblparser.entities.forms import parse_field_to_form_matrix, parse_form, parse_role_to_form_rule_matrix, parse_rule
from qblparser.entities.reports import parse_report, parse_report_field_matrix, parse_report_permissions
from qblparser.entities.roles import extract_role_permissions, parse_field_to_role_matrix, parse_roles
from qblparser.entities.tables import parse_table
from qblparser.entities.relationships import parse_relationship
from qblparser.entities.pipelines import parse_field_to_pipeline_matrix, parse_pipeline, parse_pipeline_steps, parse_pipeline_table_matrix
from qblparser.entities.pages import (
    parse_guide_metadata,
    parse_page_metadata,
    parse_page_widgets,
)
from qblparser.entities.connected_tables import (
    parse_connected_table,
    parse_connected_table_fields,
    parse_connected_table_matrix
)
from qblparser.entities.custom_emails import (
    parse_custom_email,
    parse_custom_email_field_matrix,
    parse_custom_email_document_matrix,
)
from qblparser.entities.document_templates import parse_document_template

PARSING_REGISTRY = {
    "table": parse_table,
    "report": parse_report,
    "report_field_matrix": parse_report_field_matrix,
    "permissions": extract_role_permissions,
    "report_permissions": parse_report_permissions,
    "form": parse_form,
    "rule": parse_rule,
    "field_form_matrix": parse_field_to_form_matrix,
    "field_metadata": parse_field_metadata,
    "relationship": parse_relationship,
    "pipeline": parse_pipeline,
    "pipeline_steps": parse_pipeline_steps,
    "pipeline_table_matrix": parse_pipeline_table_matrix,
    "field_pipeline_matrix": parse_field_to_pipeline_matrix,
    "role_form_rule_matrix": parse_role_to_form_rule_matrix,
    "roles": parse_roles,
    "field_role_matrix": parse_field_to_role_matrix,
    "page": parse_page_metadata,
    "guide": parse_guide_metadata,
    "page_widget": parse_page_widgets,
    "connected_table": parse_connected_table,
    "connected_table_fields": parse_connected_table_fields,
    "connected_table_matrix": parse_connected_table_matrix,
    "custom_email": parse_custom_email,
    "custom_email_field_matrix": parse_custom_email_field_matrix,
    "custom_email_document_matrix": parse_custom_email_document_matrix,
    "document_template": parse_document_template,
}
