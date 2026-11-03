from .entities.field_validator import validate_field_summary, validate_field_lookup, validate_field_reference
from .entities.pipeline_validator import validate_pipeline_step
from .entities.legacy_form_validator import validate_legacy_form, validate_legacy_form_element
from .entities.legacy_dynamic_form_rules_validator import validate_legacy_dynamic_form_rule
from .entities.relationship_validator import validate_relationship
from .entities.role_validator import validate_role_table_ui
from .entities.table_validator import validate_table_role_permissions
from .entities.custom_email_validator import validate_custom_email


CUSTOM_VALIDATORS = {
    
    "QB::Field::Summary": validate_field_summary,
    "QB::Field::Lookup": validate_field_lookup,
    "QB::Field::Reference": validate_field_reference,
    
    "QB::PipelineStep": validate_pipeline_step,
    
    "QB::Form": validate_legacy_form,
    "QB::FormRule": validate_legacy_dynamic_form_rule,
    
    "QB::Relationship::Parent": validate_relationship,
    "QB::Relationship::Child": validate_relationship,
    "QB::Relationship::CrossAppParent": validate_relationship,
    "QB::Relationship::CrossAppChild": validate_relationship,
    
    "QB::Role::TableUI": validate_role_table_ui,
    "QB::Table::RolePermissions": validate_table_role_permissions,

    "QB::CustomEmail": validate_custom_email,
}


def register_validator(qbl_type, validator_function):
    CUSTOM_VALIDATORS[qbl_type] = validator_function


def get_validator(qbl_type):
    return CUSTOM_VALIDATORS.get(qbl_type)

