from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Union

_field = field


@dataclass
class FieldSpec:

    label: str
    kind: str = "Text"
    formula: Optional[str] = None
    choices: Optional[List[str]] = None
    lookup_table: Optional[str] = None
    lookup_field: Optional[str] = None
    lookup_via: Optional[str] = None
    link_source: Optional[str] = None
    link_table: Optional[str] = None
    link_field: Optional[str] = None
    address_format: str = "United States"
    summarize_table: Optional[str] = None
    summarize_field: Optional[str] = None
    summarize_by: str = "Count"
    unique: bool = False
    required: bool = False
    help_text: Optional[str] = None
    comments: Optional[str] = None
    default_value: Optional[Any] = None
    opens_page: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SummaryColumnSpec:

    field: str
    summarize_by: str = "Total"


@dataclass
class SummaryFormulaSpec:

    label: str
    formula: str
    kind: str = "Numeric"


@dataclass
class ReportSpec:
    name: str
    kind: str = "Table"
    columns: List[str] = field(default_factory=list)
    sort_by: List[str] = field(default_factory=list)
    filters: List[tuple] = field(default_factory=list)
    group_by_field: Optional[str] = None
    summary_columns: List[SummaryColumnSpec] = field(default_factory=list)
    summary_variables: List[SummaryColumnSpec] = field(default_factory=list)
    summary_formulas: List[SummaryFormulaSpec] = field(default_factory=list)
    report_formulas: List[SummaryFormulaSpec] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FormRuleTriggerSpec:

    kind: str = "RecordState"
    record_state: str = "IsSaving"
    role: Optional[str] = None
    field: Optional[str] = None
    value: Any = None
    comparison: str = "IsEqualTo"


@dataclass
class FormRuleConditionSpec:

    field: Optional[str] = None
    value: Any = ""
    comparison: str = "IsEqualTo"
    kind: str = "Field"
    role: Optional[str] = None
    formula: Optional[str] = None


@dataclass
class FormRuleActionSpec:

    action: str = "Hide"
    target_field: Optional[str] = None
    value: Optional[Any] = None
    value_field: Optional[str] = None
    message: Optional[str] = None
    target_section: Optional[str] = None
    target_column: int = 1
    color: Optional[str] = None
    label: Optional[str] = None
    message_type: str = "Modal"
    message_level: Optional[str] = None


@dataclass
class FormRuleSpec:

    name: str
    when_field: Optional[str] = None
    equals: Any = None
    target_field: Optional[str] = None
    action: str = "Hide"
    comparison: str = "IsEqualTo"
    conditions: List[FormRuleConditionSpec] = field(default_factory=list)
    actions: List[FormRuleActionSpec] = field(default_factory=list)
    trigger: Optional[FormRuleTriggerSpec] = None
    true_when: str = "All"
    run_on: str = "RecordOpenSaveOrChange"
    fire_only_on_change: bool = False
    disabled: bool = False
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FormColumnSpec:

    fields: List["FormMember"] = field(default_factory=list)
    layout_width: Optional[int] = None


@dataclass
class FormSectionSpec:
    title: Optional[str] = None
    columns: List[FormColumnSpec] = field(default_factory=list)
    modes: Optional[List[str]] = None


@dataclass
class FormSpec:

    name: str = "Main Form"
    sections: List[FormSectionSpec] = field(default_factory=list)
    rules: List[FormRuleSpec] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FormElementSpec:

    field: Optional[str] = None
    kind: Optional[str] = None
    label: Optional[str] = None
    embedded_report: Optional[str] = None
    embedded_table: Optional[str] = None
    embedded_rows: int = 50
    content: Optional[str] = None
    members: List["FormMember"] = _field(default_factory=list)
    properties: Dict[str, Any] = _field(default_factory=dict)


FormMember = Union[str, FormElementSpec]


@dataclass
class LegacyFormTabSpec:

    label: str
    color: Optional[str] = None
    rows: List[List[FormMember]] = field(default_factory=list)


@dataclass
class LegacyFormSectionSpec:

    heading: Optional[str] = None
    fields: List[FormMember] = field(default_factory=list)
    rows: List[List[FormMember]] = field(default_factory=list)
    tabs: List[LegacyFormTabSpec] = field(default_factory=list)


@dataclass
class LegacyFormSpec:

    name: str = "Main Form"
    fields: List[FormMember] = field(default_factory=list)
    sections: List[LegacyFormSectionSpec] = field(default_factory=list)
    rules: List["FormRuleSpec"] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChartSpec:

    name: str
    value_field: str
    category_field: Optional[str] = None
    kind: str = "Bar"
    summarize_by: str = "Sum"
    second_field: Optional[str] = None
    report_formulas: List[SummaryFormulaSpec] = _field(default_factory=list)
    summary_variables: List[SummaryColumnSpec] = _field(default_factory=list)
    summary_formulas: List[SummaryFormulaSpec] = _field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RoleFormDefaultSpec:

    view_form: str = "Default"
    edit_form: str = "Default"
    add_form: str = "Default"
    grid_edit: str = "None"
    mobile: Optional[str] = None


@dataclass
class ReportFormOverrideSpec:

    view_form: str = "UseRoleSettings"
    edit_form: str = "UseRoleSettings"
    grid_edit: str = "UseRoleSettings"
    mobile: str = "UseRoleSettings"


@dataclass
class TableRolePermissionSpec:

    can_add: bool = False
    can_delete: bool = False
    can_save_common_reports: bool = False
    can_edit_field_properties: bool = False
    view_records: str = "Always"
    view_criteria: Optional[str] = None
    modify_records: str = "Always"
    modify_criteria: Optional[str] = None


@dataclass
class TableSpec:
    name: str
    fields: List[FieldSpec] = field(default_factory=list)
    reports: List[ReportSpec] = field(default_factory=list)
    charts: List[ChartSpec] = field(default_factory=list)
    form: Optional["FormSpec"] = None
    legacy_form: Optional["LegacyFormSpec"] = None
    emails: List["CustomEmailSpec"] = field(default_factory=list)
    document_templates: List["DocumentTemplateSpec"] = field(default_factory=list)
    singular: Optional[str] = None
    plural: Optional[str] = None
    role_permissions: Dict[str, "TableRolePermissionSpec"] = field(default_factory=dict)
    role_forms: Dict[str, "RoleFormDefaultSpec"] = field(default_factory=dict)
    report_form_overrides: Dict[str, "ReportFormOverrideSpec"] = field(default_factory=dict)
    properties: Dict[str, Any] = field(default_factory=dict)
    default_columns: Optional[List[str]] = None
    title_field: Optional[str] = None


@dataclass
class RelationshipSpec:

    parent: str
    child: str
    reference_label: Optional[str] = None
    embed_on_parent: bool = True
    embed_label: Optional[str] = None
    embed_columns: Optional[List[str]] = None
    display_field: Optional[str] = None
    display_parent: bool = True
    reference_properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PageSpec:

    name: str
    kind: str = "RichTextPage"
    body: str = ""
    purpose: Optional[str] = None
    native_gap: Optional[str] = None
    auth: str = "TempToken"
    requests_per_second: Optional[float] = None
    sensitive_data: bool = False
    drafted_on: Optional[str] = None


@dataclass
class DashboardWidgetSpec:

    kind: str = "RichText"
    title: Optional[str] = None
    table: Optional[str] = None
    report: Optional[str] = None
    x: int = 0
    y: int = 0
    width: int = 6
    height: Optional[int] = None


@dataclass
class DashboardFilterSpec:

    name: str
    table: str
    field: str
    targets: List[str] = field(default_factory=list)
    filter_type: str = "Text"
    search_type: str = "ExactMatch"


@dataclass
class DashboardTabSpec:

    name: str
    widgets: List[DashboardWidgetSpec] = field(default_factory=list)
    filters: List[DashboardFilterSpec] = field(default_factory=list)


@dataclass
class DashboardSpec:
    name: str
    widgets: List[DashboardWidgetSpec] = field(default_factory=list)
    filters: List[DashboardFilterSpec] = field(default_factory=list)
    tab_name: str = "Main"
    tabs: List[DashboardTabSpec] = field(default_factory=list)


@dataclass
class HomeWidgetLinkSpec:

    name: str
    url: str = ""
    link_type: str = "Url"
    redirect_url: Optional[str] = None
    table: Optional[str] = None
    report: Optional[str] = None
    page: Optional[str] = None
    return_home: bool = False


@dataclass
class HomeWidgetFieldSpec:

    field: str
    label: Optional[str] = None
    placeholder: Optional[str] = None


@dataclass
class HomeWidgetSpec:

    kind: str = "RichText"
    title: Optional[str] = None
    table: Optional[str] = None
    report: Optional[str] = None
    section: str = "MainSection"
    row: Optional[str] = None
    width: Optional[str] = None
    height: Optional[int] = None
    max_rows: Optional[int] = None
    tables: List[str] = field(default_factory=list)
    links: List[HomeWidgetLinkSpec] = field(default_factory=list)
    fields: List[HomeWidgetFieldSpec] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GuideSpec:

    title: str
    links_to: str
    description: Optional[str] = None


@dataclass
class EmailConditionSpec:

    field: str
    comparison: str = "IsEqualTo"
    value: Any = None


@dataclass
class CustomEmailSpec:

    name: str
    subject: str
    content: str
    trigger: str = "Scheduled"
    schedule: str = "0 9 * * *"
    record_events: List[str] = _field(default_factory=list)
    trigger_fields: List[str] = _field(default_factory=list)
    to_fields: List[str] = _field(default_factory=list)
    check_recipient_permissions: bool = True
    send_when_empty: bool = False
    conditions: List[EmailConditionSpec] = _field(default_factory=list)
    true_when: str = "All"
    description: Optional[str] = None


@dataclass
class DocumentTemplateSpec:
    name: str


@dataclass
class VariableSpec:

    name: str
    value: str


@dataclass
class PipelineFilterSpec:

    field: str
    operator: str = "equals"
    value: Any = None


@dataclass
class PipelineStepSpec:

    kind: str
    table: Optional[str] = None
    name: Optional[str] = None
    id: Optional[str] = None
    filters: List[PipelineFilterSpec] = _field(default_factory=list)
    values: Dict[str, str] = _field(default_factory=dict)
    target: Optional[str] = None
    steps: List["PipelineStepSpec"] = _field(default_factory=list)
    export: List[str] = _field(default_factory=list)


@dataclass
class PipelineActionSpec:

    table: str
    kind: str = "create"
    values: Dict[str, str] = field(default_factory=dict)
    name: Optional[str] = None


@dataclass
class PipelineSpec:

    name: str
    owner: str
    trigger_table: Optional[str] = None
    trigger_event: str = "update"
    trigger_fields: List[str] = field(default_factory=list)
    actions: List[PipelineActionSpec] = field(default_factory=list)
    description: Optional[str] = None
    account_id: Union[int, str] = 1
    trigger_filters: List[PipelineFilterSpec] = field(default_factory=list)
    trigger_name: Optional[str] = None
    schedule: Optional[str] = None
    timezone: Optional[str] = None
    steps: List[PipelineStepSpec] = field(default_factory=list)


@dataclass
class ConnectedColumnSpec:

    name: str
    kind: str = "Text"
    source_field_id: Optional[int] = None


@dataclass
class ConnectedTableSpec:

    name: str
    columns: List[ConnectedColumnSpec] = field(default_factory=list)
    connection_id: Union[int, str] = 1
    external_set_id: str = "external"
    owner: Optional[str] = None
    schedule: str = "Manual"
    notify_on_failure: bool = True
    key_column: Optional[str] = None


@dataclass
class RoleSpec:

    name: str
    can_edit_app: bool = False
    description: Optional[str] = None
    is_default: bool = False
    manage_users: bool = False
    disable_access: bool = False
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AppSpec:
    name: str
    tables: List[TableSpec] = field(default_factory=list)
    relationships: List[RelationshipSpec] = field(default_factory=list)
    roles: List[RoleSpec] = field(default_factory=list)
    default_roles: bool = True
    description: Optional[str] = None
    home_page_name: str = "Home"
    pages: List[PageSpec] = field(default_factory=list)
    dashboards: List[DashboardSpec] = field(default_factory=list)
    home_widgets: List[HomeWidgetSpec] = field(default_factory=list)
    guides: List[GuideSpec] = field(default_factory=list)
    variables: List[VariableSpec] = field(default_factory=list)
    pipelines: List[PipelineSpec] = field(default_factory=list)
    connected_tables: List[ConnectedTableSpec] = field(default_factory=list)
    role_home_pages: Dict[str, str] = field(default_factory=dict)
    requirements: List["RequirementSpec"] = field(default_factory=list)
    decisions: List["DecisionSpec"] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)


__all__ = [
    "AppSpec",
    "ChartSpec",
    "SummaryColumnSpec",
    "SummaryFormulaSpec",
    "CustomEmailSpec",
    "DashboardFilterSpec",
    "DashboardSpec",
    "DashboardWidgetSpec",
    "DocumentTemplateSpec",
    "ConnectedColumnSpec",
    "ConnectedTableSpec",
    "GuideSpec",
    "HomeWidgetFieldSpec",
    "HomeWidgetLinkSpec",
    "HomeWidgetSpec",
    "PageSpec",
    "EmailConditionSpec",
    "PipelineActionSpec",
    "PipelineFilterSpec",
    "PipelineSpec",
    "PipelineStepSpec",
    "VariableSpec",
    "FormColumnSpec",
    "FormElementSpec",
    "FormRuleActionSpec",
    "FormRuleConditionSpec",
    "FormRuleTriggerSpec",
    "FormRuleSpec",
    "FormSectionSpec",
    "FormSpec",
    "LegacyFormSectionSpec",
    "LegacyFormSpec",
    "LegacyFormTabSpec",
    "FieldSpec",
    "RelationshipSpec",
    "ReportFormOverrideSpec",
    "RoleFormDefaultSpec",
    "ReportSpec",
    "RoleSpec",
    "TableRolePermissionSpec",
    "TableSpec",
]
