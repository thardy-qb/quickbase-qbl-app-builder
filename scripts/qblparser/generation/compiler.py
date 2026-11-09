from __future__ import annotations

import copy
from dataclasses import dataclass
import difflib
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from qblparser.generation.spec import (
    AppSpec,
    ChartSpec,
    DashboardSpec,
    DashboardWidgetSpec,
    FieldSpec,
    FormRuleActionSpec,
    FormRuleConditionSpec,
    FormRuleSpec,
    FormRuleTriggerSpec,
    FormColumnSpec,
    FormSectionSpec,
    FormElementSpec,
    ConnectedTableSpec,
    FormSpec,
    HomeWidgetSpec,
    LegacyFormSectionSpec,
    LegacyFormSpec,
    PageSpec,
    PipelineActionSpec,
    PipelineFilterSpec,
    PipelineSpec,
    PipelineStepSpec,
    RelationshipSpec,
    ReportSpec,
    RoleSpec,
    TableRolePermissionSpec,
    TableSpec,
)
from qblparser.qbl_schema.versioned import RENAMED_NESTED as _RENAMED_NESTED
from qblparser.utils.qbl_tags import QBLTaggedMapping
from qblparser.generation import code_pages as _code_pages
from qblparser.generation.tokens import FieldTokenError, resolve_field_tokens

QBL_VERSION = 0.15

BUILTIN_FIELDS = (
    ("Date Created", "DateCreated", 1),
    ("Date Modified", "DateModified", 2),
    ("Record ID#", "RecordID", 3),
    ("Record Owner", "RecordOwner", 4),
    ("Last Modified By", "LastModifiedBy", 5),
)

LEGACY_FORM_FIRST_ID = 2
LEGACY_FORM_NEXT_ID = 10

FORM_V2_MODES = ["Edit", "View", "Create"]

FORM_SECTION_WIDTH = 12
FORM_SECTION_MAX_COLUMNS = 6


ID_FLOORS = {
    "field": 6,
    "report": 1,
    "chart": 1,
    "form": 10,
    "page": 2,
    "form_page": 1,
    "legacy_form": LEGACY_FORM_FIRST_ID,
    "template": 1,
}

REPORTS_WITHOUT_COLOR_CODING = frozenset({"Summary", "GridEdit"})

SUMMARY_FUNCTIONS = {
    "Count": "Count",
    "Total": "Total",
    "Sum": "Total",
    "Average": "Average",
    "Maximum": "Maximum",
    "Minimum": "Minimum",
    "DistinctCount": "DistinctCount",
    "CombinedText": "CombinedText",
    "CombinedUser": "CombinedUser",
    "AnyRelatedRecords": "AnyRelatedRecords",
}

FIELDLESS_SUMMARY_FUNCTIONS = frozenset({"Count", "AnyRelatedRecords"})


class QBLCompileError(ValueError):
    pass


DEFAULT_TABLE_ICON = "Table Header"

KNOWN_TABLE_ICONS = frozenset({
    "Nurse", "Satellite Dish", "Shopping Cart",
    "Activity", "Aid", "Animation",
    "Attendance List", "Balloons", "Bank Transaction",
    "Bell", "Book", "Bookmark",
    "Bug", "Calculator", "Calendar",
    "Calendar Year", "Car Front", "Cellphone",
    "Chart", "Clipboard", "Clipboard Pencil",
    "Clock", "College", "Command",
    "Competitors", "Copy", "Copy 2",
    "Cube", "Curriculum", "Customer",
    "Customers", "Directive Board", "Document",
    "Dollar Sign", "Economics", "Edit",
    "Engineering", "Envelope", "Field Image",
    "File", "Film", "Flag",
    "Folder", "Frames", "Geography",
    "Group", "Hammer", "Handshake",
    "Hourglass", "ID", "Inventory",
    "Lightbulb", "List", "Mailbox",
    "Male", "Marker", "Offer",
    "One", "Pages", "Paper Clip",
    "Paste", "Phone", "Plus",
    "Protocol", "Purchase", "Report",
    "Report 2", "Risk", "Router",
    "Salesman", "Sandals", "Schedule",
    "Schedule 2", "Screwdriver", "Signs",
    "Smudge", "Sole Proprietorship", "Star",
    "Student", "Table Header", "Task",
    "Task Complete", "Tasks", "Taxi",
    "Team", "Team Members", "Thumbs Up",
    "Timer", "Two", "Up Arrow",
    "Upload", "Upload 2", "User",
    "White List", "Wrench"
})


def _table_alias(name: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "_", name).strip("_").upper()
    return f"_DBID_{slug or 'TABLE'}"


def logical_id(prefix: str, name: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "_", name).strip("_")
    return f"${prefix}_{slug or 'Unnamed'}"


PER_TABLE_FAMILIES = frozenset({
    "field", "report", "chart", "form", "form_page", "legacy_form",
})


SHARED_ID_SPACES = {"chart": "report"}


class _IdMinter:

    def __init__(self) -> None:
        self._app_scoped = dict(ID_FLOORS)
        self._table_scoped: Dict[str, int] = {}

    def enter_table(self) -> None:
        self._table_scoped = {
            family: floor for family, floor in ID_FLOORS.items()
            if family in PER_TABLE_FAMILIES
        }

    def take(self, family: str) -> int:
        family = SHARED_ID_SPACES.get(family, family)
        counters = self._table_scoped if family in PER_TABLE_FAMILIES else self._app_scoped
        if family not in counters:
            raise QBLCompileError(
                f"no id counter for '{family}'; enter_table() must be called first"
            )
        value = counters[family]
        counters[family] = (
            LEGACY_FORM_NEXT_ID
            if family == "legacy_form" and value == LEGACY_FORM_FIRST_ID
            else value + 1
        )
        return value


def _numeric_id(value: Any, what: str, owner: str) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        raise QBLCompileError(
            f"{owner} has {what} {value!r}, which is not a number. Quickbase "
            f"writes these as numbers and the id has to name a real account."
        ) from None


def _relationship_key(rel: RelationshipSpec) -> str:
    return getattr(rel, "_qbl_key", None) or f"{rel.parent}_{rel.child}"


def _with_relationship_keys(spec: AppSpec) -> AppSpec:
    pairs: Dict[Tuple[str, str], int] = {}
    for rel in spec.relationships:
        pairs[(rel.parent, rel.child)] = pairs.get((rel.parent, rel.child), 0) + 1
    if all(count == 1 for count in pairs.values()):
        return spec
    spec = copy.deepcopy(spec)
    for rel in spec.relationships:
        if pairs[(rel.parent, rel.child)] > 1:
            rel._qbl_key = f"{rel.parent}_{rel.child}_{rel.reference_label}"
    return spec


def _relationship_ids(rel: RelationshipSpec) -> Tuple[str, str]:
    child_key = logical_id("Relationship", _relationship_key(rel))
    return child_key, f"{child_key}_Parent"


def _ref(**targets: str) -> QBLTaggedMapping:
    node = QBLTaggedMapping(targets)
    node.qbl_tag = "Ref"
    return node


def _builtin_fields() -> Dict[str, Any]:
    return {
        logical_id("Field", label): {
            "Type": f"QB::Field::{kind}",
            "Id": field_id,
            "Properties": {"Label": label},
        }
        for label, kind, field_id in BUILTIN_FIELDS
    }


def _require_known_properties(qbl_type: str, properties: Dict[str, Any], subject: str) -> None:
    from qblparser.qbl_schema import QBL_SCHEMA

    entry = QBL_SCHEMA.get(qbl_type)
    if not entry:
        return
    permitted = set(entry.get("required", ())) | set(entry.get("optional", ()))
    unknown = sorted(name for name in properties if name not in permitted)
    if unknown:
        raise QBLCompileError(
            f"{subject} sets {', '.join(unknown)}, which '{qbl_type}' does not define"
        )


def _merge_properties(target: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    for name, value in overrides.items():
        existing = target.get(name)
        if isinstance(existing, dict) and isinstance(value, dict):
            _merge_properties(existing, value)
        else:
            target[name] = value
    return target


GRID_EDIT_BEHAVIOURS = ("None", "StandardBehavior")

EVERYONE_MOBILE_BEHAVIOURS = ("UseFullSiteForms",)
ROLE_MOBILE_BEHAVIOURS = ("Default",)


def _forms_properties(table: TableSpec, spec: AppSpec, form_id: str,
                      form: Optional[FormSpec]) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}

    def form_reference(name: str, subject: str) -> Any:
        if name == "Default":
            return "Default"
        if form is not None and name == form.name:
            return _ref(Form=form_id)
        if table.legacy_form is not None and name == table.legacy_form.name:
            return _ref(Form=logical_id("Form", table.name))
        raise QBLCompileError(
            f"{subject} names form '{name}', which table '{table.name}' does not "
            f"declare"
        )

    def everyone_opens() -> Optional[Dict[str, Any]]:
        if form is not None:
            reference: Any = _ref(Form=form_id)
        elif table.legacy_form is not None:
            reference = _ref(Form=logical_id("Form", table.name))
        else:
            return None
        return {
            "ViewForm": reference,
            "EditForm": reference,
            "AddForm": reference,
            "GridEdit": "None",
            "Mobile": EVERYONE_MOBILE_BEHAVIOURS[0],
        }

    role_names = {role.name for role in spec.roles}
    defaults: Dict[str, Any] = {}
    fallback = everyone_opens()
    if fallback is not None:
        defaults["Everyone"] = fallback
    for role_name, entry in table.role_forms.items():
        if role_name != "Everyone" and role_name not in role_names:
            raise QBLCompileError(
                f"table '{table.name}' sets form defaults for '{role_name}', "
                f"which is not a role in this spec"
            )
        subject = f"table '{table.name}' role '{role_name}'"
        is_everyone = role_name == "Everyone"
        mobile_domain = (EVERYONE_MOBILE_BEHAVIOURS if is_everyone
                         else ROLE_MOBILE_BEHAVIOURS)
        mobile = entry.mobile if entry.mobile is not None else mobile_domain[0]
        for label, value, permitted in (
            ("grid_edit", entry.grid_edit, GRID_EDIT_BEHAVIOURS),
            ("mobile", mobile, mobile_domain),
        ):
            if value not in permitted:
                whose = "Everyone" if is_everyone else "a role"
                raise QBLCompileError(
                    f"{subject} sets {label} to '{value}'; on {whose} the "
                    f"value is {' or '.join(permitted)}. The platform answers "
                    f"anything else `BadProperty` and drops the whole "
                    f"RoleDefaults container with it"
                )
        key = "Everyone" if is_everyone else logical_id("Role", role_name)
        defaults[key] = {
            "ViewForm": form_reference(entry.view_form, subject),
            "EditForm": form_reference(entry.edit_form, subject),
            "AddForm": form_reference(entry.add_form, subject),
            "GridEdit": entry.grid_edit,
            "Mobile": mobile,
        }
    if defaults:
        properties["RoleDefaults"] = defaults

    if table.report_form_overrides:
        report_names = {r.name for r in table.reports} | {c.name for c in table.charts}
        overrides: Dict[str, Any] = {}
        for report_name, entry in table.report_form_overrides.items():
            if report_name not in report_names:
                raise QBLCompileError(
                    f"table '{table.name}' overrides forms for '{report_name}', which "
                    f"it does not declare as a report or a chart"
                )
            prefix = "Report" if any(r.name == report_name for r in table.reports) else "Chart"
            subject = f"table '{table.name}' report '{report_name}'"
            overrides[logical_id(prefix, f"{table.name}_{report_name}")] = {
                "ViewForm": entry.view_form if entry.view_form == "UseRoleSettings"
                            else form_reference(entry.view_form, subject),
                "EditForm": entry.edit_form if entry.edit_form == "UseRoleSettings"
                            else form_reference(entry.edit_form, subject),
                "GridEdit": entry.grid_edit,
                "Mobile": entry.mobile,
            }
        properties["ReportOverrides"] = overrides

    if "RoleDefaults" in properties:
        properties.setdefault("ReportOverrides", {})

    return properties


PERMISSION_WHEN = ("Always", "Never", "CustomRule")

DEFAULT_ROLES = (
    RoleSpec(name="Viewer", description="Can view records"),
    RoleSpec(name="Participant", is_default=True,
             description="Can add records and edit the records they own"),
    RoleSpec(name="Administrator", can_edit_app=True, manage_users=True,
             description="Full access to every table, plus app and user management"),
)

DEFAULT_ROLE_ACCESS: Dict[str, TableRolePermissionSpec] = {
    "Viewer": TableRolePermissionSpec(view_records="Always", modify_records="Never"),
    "Participant": TableRolePermissionSpec(
        can_add=True, view_records="Always", modify_records="CustomRule",
        modify_criteria="{'4'.EX.'_curuser_'}"),
    "Administrator": TableRolePermissionSpec(
        can_add=True, can_delete=True, can_save_common_reports=True,
        can_edit_field_properties=True, view_records="Always",
        modify_records="Always"),
}

_DEFAULT_ACCESS_BY_NAME = {name.casefold(): access
                           for name, access in DEFAULT_ROLE_ACCESS.items()}


def _with_default_roles(spec: AppSpec) -> AppSpec:
    if not spec.default_roles:
        return spec
    present = {role.name.casefold() for role in spec.roles}
    missing = [role for role in DEFAULT_ROLES if role.name.casefold() not in present]
    if not missing:
        return spec
    spec = copy.copy(spec)
    added = [copy.deepcopy(role) for role in missing]
    if any(role.is_default for role in spec.roles):
        for role in added:
            role.is_default = False
    spec.roles = added + list(spec.roles)
    return spec


def _table_role_permissions(table: TableSpec, spec: AppSpec) -> Dict[str, Any]:
    role_names = {role.name for role in spec.roles}
    permissions: Dict[str, Any] = {}

    for role_name in table.role_permissions:
        if role_name not in role_names:
            raise QBLCompileError(
                f"table '{table.name}' grants permissions to '{role_name}', which is "
                f"not a role in this spec"
            )

    entries: Dict[str, TableRolePermissionSpec] = {}
    for role in spec.roles:
        entry = table.role_permissions.get(role.name)
        if entry is None and spec.default_roles:
            entry = _DEFAULT_ACCESS_BY_NAME.get(role.name.casefold())
        if entry is not None:
            entries[role.name] = entry

    for role_name, entry in entries.items():
        for label, when in (("view_records", entry.view_records),
                            ("modify_records", entry.modify_records)):
            if when not in PERMISSION_WHEN:
                raise QBLCompileError(
                    f"table '{table.name}' sets {label} to '{when}' for role "
                    f"'{role_name}'; known values are {', '.join(PERMISSION_WHEN)}"
                )
        permissions[logical_id("Role", role_name)] = {
            "CanAddRecords": entry.can_add,
            "CanDeleteRecords": entry.can_delete,
            "CanSaveCommonReports": entry.can_save_common_reports,
            "CanEditFieldProperties": entry.can_edit_field_properties,
            "CanViewRecords": _access_rule(entry.view_records, entry.view_criteria),
            "CanModifyRecords": _access_rule(entry.modify_records, entry.modify_criteria),
        }

    return permissions


def _access_rule(when: str, criteria: Optional[str]) -> Dict[str, Any]:
    rule: Dict[str, Any] = {"When": when}
    if criteria:
        rule["CustomAccessCriteria"] = criteria
    return rule


def _role_properties(role: RoleSpec) -> Dict[str, Any]:
    properties: Dict[str, Any] = {
        "Name": role.name,
        "EditApp": role.can_edit_app,
        "Default": role.is_default,
        "ManageUsers": role.manage_users,
        "DisableAccess": role.disable_access,
    }
    if role.description:
        properties["Description"] = role.description
    if role.properties:
        _require_known_properties(
            "QB::Application::Role", role.properties, f"role '{role.name}'"
        )
        _merge_properties(properties, role.properties)
    return properties


FIELD_KIND_ALIASES = {
    "TextMultiLine": "TextMultiline",
}


def _require_known_table_icon(table: TableSpec) -> None:
    icon = table.properties.get("TableIconName")
    if icon is None or icon in KNOWN_TABLE_ICONS:
        return

    lowered = str(icon).lower()
    near = sorted(
        name for name in KNOWN_TABLE_ICONS
        if lowered in name.lower() or name.lower() in lowered
        or name.lower().split()[0] == lowered.split()[0]
    )
    hint = f" Did you mean {' or '.join(near[:4])}?" if near else ""
    raise QBLCompileError(
        f"table '{table.name}' asks for the icon {icon!r}, which is not a known "
        f"table icon. Quickbase does not reject an unknown name - it silently "
        f"replaces it with 'Folder', which renders as no icon at all, so this "
        f"would deploy looking correct and be wrong.{hint} If you have "
        f"confirmed {icon!r} survives a create, add it to KNOWN_TABLE_ICONS."
    )


def _require_known_field_properties(qbl_type: str, field_spec: FieldSpec) -> None:
    _require_known_properties(
        qbl_type, field_spec.properties, f"field '{field_spec.label}'"
    )


def _summary_containers(report) -> Dict[str, Any]:
    containers: Dict[str, Any] = {}
    summary_columns = getattr(report, "summary_columns", ())

    if summary_columns:
        containers["Columns"] = {
            f"SummaryColumn_{index}": {
                "Type": "QB::Report::Summary::Column",
                "Properties": {
                    "Source": _ref(Field=logical_id("Field", column.field)),
                    "SummarizeBy": column.summarize_by,
                },
            }
            for index, column in enumerate(summary_columns, start=1)
        }

    if report.summary_variables:
        containers["SummaryVariables"] = {
            f"SummaryVariable_{index}": {
                "Type": "QB::Report::SummaryVariable",
                "Properties": {
                    "Source": _ref(Field=logical_id("Field", variable.field)),
                    "SummarizeBy": variable.summarize_by,
                },
            }
            for index, variable in enumerate(report.summary_variables, start=1)
        }

    if report.summary_formulas:
        containers["SummaryFormulas"] = {
            f"SummaryFormula_{index}": {
                "Type": _formula_type("QB::Report::SummaryFormula::", formula, report),
                "Properties": {"Label": formula.label, "Formula": formula.formula},
            }
            for index, formula in enumerate(
                _at_most_three(report.summary_formulas, "summary", report), start=1)
        }

    if report.report_formulas:
        containers["ReportFormulas"] = {
            f"ReportFormula_{index}": {
                "Type": _formula_type("QB::Report::Formula::", formula, report),
                "Properties": {"Label": formula.label, "Formula": formula.formula},
            }
            for index, formula in enumerate(
                _at_most_three(report.report_formulas, "report", report), start=1)
        }

    return containers


MAX_FORMULAS_PER_REPORT = 3


def _at_most_three(formulas: List[Any], which: str, report: Any) -> List[Any]:
    if len(formulas) > MAX_FORMULAS_PER_REPORT:
        raise QBLCompileError(
            f"report '{report.name}' has {len(formulas)} {which} formulas; the "
            f"platform allows {MAX_FORMULAS_PER_REPORT} per report")
    return formulas


def _formula_type(prefix: str, formula: Any, report: Any) -> str:
    from qblparser.qbl_schema import QBL_SCHEMA, canonical_type

    qbl_type = canonical_type(prefix + formula.kind)
    if qbl_type not in QBL_SCHEMA:
        known = sorted(t[len(prefix):] for t in QBL_SCHEMA
                       if t.startswith(prefix) and t.count("::") == 3)
        raise QBLCompileError(
            f"report '{report.name}' formula '{formula.label}' has kind "
            f"'{formula.kind}'; the kinds are {', '.join(known)}")
    return qbl_type


def _summary_field(spec: FieldSpec, parent: str, table_names: Dict[str, str],
                   reference_fields: Dict[Tuple[str, str], str],
                   app: AppSpec) -> Dict[str, Any]:
    child = spec.summarize_table
    if child not in table_names:
        raise QBLCompileError(
            f"summary field '{spec.label}' summarises '{child}', which is not a table "
            f"in this spec"
        )
    if (parent, child) not in reference_fields:
        others = sorted({key[0] for key in reference_fields
                         if len(key) == 2 and key[1] == child})
        if others:
            raise QBLCompileError(
                f"table '{parent}' declares summary field '{spec.label}' over "
                f"'{child}', but '{child}' is not its child - a summary reads up a "
                f"relationship, and '{child}' is a child of "
                f"{', '.join(repr(name) for name in others)}"
            )
        raise QBLCompileError(
            f"summary field '{spec.label}' summarises '{child}', but no relationship "
            f"makes it a child - a summary reads up a relationship, so one has to exist"
        )

    function = SUMMARY_FUNCTIONS.get(spec.summarize_by)
    if function is None:
        raise QBLCompileError(
            f"summary field '{spec.label}' uses function '{spec.summarize_by}'; "
            f"known functions are {', '.join(sorted(SUMMARY_FUNCTIONS))}"
        )

    display_type = FIXED_SUMMARY_DISPLAY_TYPES.get(function, "QB::Field::Number")
    reads_a_field = function not in FIELDLESS_SUMMARY_FUNCTIONS
    if reads_a_field:
        if not spec.summarize_field:
            raise QBLCompileError(
                f"summary field '{spec.label}' uses '{function}', which needs a "
                f"summarize_field; only "
                f"{' and '.join(sorted(FIELDLESS_SUMMARY_FUNCTIONS))} read no field"
            )
        source_kind = _field_kind(app, child, spec.summarize_field)
        if source_kind is None:
            raise QBLCompileError(
                f"summary field '{spec.label}' summarises '{spec.summarize_field}', "
                f"which table '{child}' does not declare"
            )
        if function not in FIXED_SUMMARY_DISPLAY_TYPES:
            display_type = _summary_display_type(app, child, spec.summarize_field)

    through = [key for key in reference_fields
               if len(key) == 3 and key[:2] == (parent, child)]
    if spec.lookup_via is not None:
        if (parent, child, spec.lookup_via) not in reference_fields:
            raise QBLCompileError(
                f"summary field '{spec.label}' rolls up through "
                f"'{spec.lookup_via}', which is not a reference from '{child}' "
                f"to '{parent}'")
        reference = reference_fields[(parent, child, spec.lookup_via)]
    elif len(through) > 1:
        raise QBLCompileError(
            f"summary field '{spec.label}' rolls up '{child}', which references "
            f"'{parent}' {len(through)} times ("
            + ", ".join(repr(key[2]) for key in through)
            + "); say which with lookup_via")
    else:
        reference = reference_fields[(parent, child)]
    summary: Dict[str, Any] = {
        "ReferenceField": _ref(Table=table_names[child], Field=reference),
        "Function": function,
        "DisplayType": display_type,
        "DrillDownReport": "Default",
    }
    if reads_a_field:
        summary["FieldToSummarize"] = _ref(
            Table=table_names[child], Field=logical_id("Field", spec.summarize_field)
        )
    return summary


def _summary_display_type(app: AppSpec, table_name: str, field_label: str,
                          depth: int = 0) -> str:
    if depth > 8:
        return "QB::Field::Number"
    kind = _field_kind(app, table_name, field_label)
    if kind is None:
        return "QB::Field::Number"
    if kind == "Summary":
        for table in app.tables:
            if table.name != table_name:
                continue
            for field_spec in table.fields:
                if field_spec.label != field_label:
                    continue
                if not field_spec.summarize_field:
                    return "QB::Field::Number"
                return _summary_display_type(
                    app, field_spec.summarize_table, field_spec.summarize_field,
                    depth + 1)
        return "QB::Field::Number"
    produces = kind.split("::")[0]
    return SUMMARY_DISPLAY_TYPES.get(
        kind, SUMMARY_DISPLAY_TYPES.get(produces, "QB::Field::Number"))


def _field_kind(app: AppSpec, table_name: str, field_label: str) -> Optional[str]:
    for table in app.tables:
        if table.name != table_name:
            continue
        for field_spec in table.fields:
            if field_spec.label == field_label:
                return field_spec.kind
    return None


def _require_known_field_kind(qbl_type: str, field_spec: FieldSpec, table: TableSpec) -> None:
    from qblparser.qbl_schema import QBL_SCHEMA

    if qbl_type in QBL_SCHEMA:
        return

    formula = field_spec.kind.endswith("::Formula")
    known = sorted(
        name.replace("QB::Field::", "")
        for name in QBL_SCHEMA
        if name.startswith("QB::Field::")
        and (name.endswith("::Formula") if formula
             else "::" not in name[len("QB::Field::"):])
        and not name.endswith("Block")
    )
    near = [k for k in known if k.lower().startswith(field_spec.kind[:4].lower())]
    if not near:
        near = difflib.get_close_matches(field_spec.kind, known, n=2, cutoff=0.6)
    hint = f" Did you mean {' or '.join(near)}?" if near else ""
    raise QBLCompileError(
        f"table '{table.name}' field '{field_spec.label}' has kind "
        f"'{field_spec.kind}', which is not a QBL field type.{hint}"
    )


SUMMARY_DISPLAY_TYPES = {
    "Currency": "QB::Field::Currency",
    "Percent": "QB::Field::Percent",
    "Duration": "QB::Field::Duration",
    "Rating": "QB::Field::Rating",
    "Date": "QB::Field::Date",
    "DateTime": "QB::Field::DateTime",
    "TimeOfDay": "QB::Field::TimeOfDay",
}

FIXED_SUMMARY_DISPLAY_TYPES = {
    "Count": "QB::Field::Number",
    "DistinctCount": "QB::Field::Number",
    "AnyRelatedRecords": "QB::Field::Checkbox",
    "CombinedText": "QB::Field::MultiselectText",
    "CombinedUser": "QB::Field::ListUser",
}


ADDRESS_PARTS = (
    ("Street1", "AddressStreet1", "Street 1"),
    ("Street2", "AddressStreet2", "Street 2"),
    ("City", "AddressCity", "City"),
    ("State", "AddressState", "State/Region"),
    ("PostalCode", "AddressPostalCode", "Postal Code"),
    ("Country", "AddressCountry", "Country"),
)


def _address_fields(field_spec: FieldSpec, minter: "_IdMinter") -> Dict[str, Any]:
    built: Dict[str, Any] = {}
    references: Dict[str, Any] = {}

    address_id = logical_id("Field", field_spec.label)
    address_node: Dict[str, Any] = {
        "Type": "QB::Field::Address",
        "Id": minter.take("field"),
        "Properties": {},
    }
    built[address_id] = address_node

    for prop, suffix, part_label in ADDRESS_PARTS:
        part_id = logical_id("Field", f"{field_spec.label} {part_label}")
        part_node: Dict[str, Any] = {
            "Type": f"QB::Field::{suffix}",
            "Id": minter.take("field"),
            "Properties": {},
        }
        built[part_id] = part_node
        references[prop] = _ref(Field=part_id)

    address_node["Properties"] = {
        "Label": field_spec.label,
        "Format": field_spec.address_format,
        "InputWidth": 60,
        "DefaultMapType": "Road",
        **references,
    }
    if field_spec.help_text is not None:
        address_node["Properties"]["HelpText"] = field_spec.help_text
    if field_spec.comments is not None:
        address_node["Properties"]["Comments"] = field_spec.comments
    return built


def _lookup_block(field_spec: FieldSpec, table: TableSpec,
                  table_names: Dict[str, str],
                  parents_of: Dict[str, List[RelationshipSpec]]) -> Dict[str, Any]:
    parent = field_spec.lookup_table
    if not parent or not field_spec.lookup_field:
        raise QBLCompileError(
            f"lookup field '{field_spec.label}' needs lookup_table and lookup_field"
        )
    relationships = [r for r in parents_of.get(table.name, []) if r.parent == parent]
    if not relationships:
        raise QBLCompileError(
            f"lookup field '{field_spec.label}' reads from '{parent}', but no "
            f"relationship makes '{table.name}' its child"
        )
    if field_spec.lookup_via is not None:
        relationships = [r for r in relationships
                         if r.reference_label == field_spec.lookup_via]
        if not relationships:
            raise QBLCompileError(
                f"lookup field '{field_spec.label}' reads through "
                f"'{field_spec.lookup_via}', which is not a reference from "
                f"'{table.name}' to '{parent}'")
    elif len(relationships) > 1:
        raise QBLCompileError(
            f"lookup field '{field_spec.label}' reads from '{parent}', which "
            f"'{table.name}' references "
            f"{len(relationships)} times ("
            + ", ".join(repr(r.reference_label) for r in relationships)
            + "); say which with lookup_via")
    rel = relationships[0]
    return {
        "Relationship": _ref(
            Relationship=logical_id("Relationship", _relationship_key(rel))
        ),
        "TargetField": _ref(
            Table=table_names[parent], Field=logical_id("Field", field_spec.lookup_field)
        ),
    }


GAUGE_CHARTS = frozenset({"Gauge", "ProgressBar"})

PIE_CHARTS = frozenset({"Pie"})

DONUT_CHARTS = frozenset({"Donut", "Donut3D", "Pie3D", "Funnel3D"})

UNCREATABLE_CHART_KINDS = {
    "Donut": "Pie",
    "Donut3D": "Pie",
    "Pie3D": "Pie",
    "Funnel3D": "Funnel",
}

FUNNEL_CHARTS = frozenset({"Funnel"})

COMPACT_AXIS_CHARTS = frozenset({"RadialBar", "VariwideBar", "Scatter3D"})

HEATMAP_CHARTS = frozenset({"Heatmap"})

LINEBAR_CHARTS = frozenset({"LineBar"})

GOAL_LINE_CHARTS = frozenset({
    "Bar", "StackedBar", "HorizontalBar", "HorizontalStackedBar",
})
AXIS_CHARTS = GOAL_LINE_CHARTS | frozenset({
    "Area", "Area3D", "AreaSpline", "Bar3D", "Spline", "StackedBar3D", "Waterfall",
    "Line", "Scatter", "Streamgraph", "Bubble",
})

SUPPORTED_CHART_KINDS = (
    AXIS_CHARTS | PIE_CHARTS | DONUT_CHARTS | GAUGE_CHARTS
    | FUNNEL_CHARTS | COMPACT_AXIS_CHARTS | HEATMAP_CHARTS | LINEBAR_CHARTS
)

CREATABLE_CHART_KINDS = SUPPORTED_CHART_KINDS - set(UNCREATABLE_CHART_KINDS)

NO_SORT_BY_CHARTS = frozenset({"Scatter", "Bubble"})

SECOND_MEASURE_PROPERTY = {
    "Bubble": "BubbleSize", "VariwideBar": "BarWidth",
    "Scatter3D": next(r for r in _RENAMED_NESTED["QB::Chart::Scatter3D"]
                      if r.path == "DataDetails").name_at(QBL_VERSION),
}


DATE_CATEGORY_KINDS = frozenset({
    "Date", "DateTime", "WorkDate", "TimeOfDay",
    "Date::Formula", "DateTime::Formula", "WorkDate::Formula",
    "DateCreated", "DateModified",
})


def _category_group_by(category_kind: Optional[str]) -> str:
    return "Month" if category_kind in DATE_CATEGORY_KINDS else "Value"


def _chart_properties(chart: ChartSpec, value_field: str,
                      category_field: Optional[str],
                      second_field: Optional[str] = None,
                      category_kind: Optional[str] = None) -> Dict[str, Any]:
    replacement = UNCREATABLE_CHART_KINDS.get(chart.kind)
    if replacement is not None:
        raise QBLCompileError(
            f"chart '{chart.name}' is a {chart.kind}, which Quickbase accepts in "
            f"a document and then cannot create - a solution containing one "
            f"times out with no diagnostic. Quickbase's solution create does "
            f"not support any of {sorted(UNCREATABLE_CHART_KINDS)}. "
            f"Use kind='{replacement}' instead."
        )
    properties = _chart_body(chart, value_field, category_field, second_field,
                             category_kind)
    if chart.properties:
        _require_known_properties(
            f"QB::Chart::{chart.kind}", chart.properties, f"chart '{chart.name}'"
        )
        _merge_properties(properties, chart.properties)
    return properties


DEFAULT_SERIES_COLOR = "#005CF5"

COMPACT_WITHOUT_AXIS_LABELS = frozenset({"RadialBar"})
COMPACT_WITHOUT_LEGEND_COLOR = frozenset({"VariwideBar"})


def _chart_body(chart: ChartSpec, value_field: str,
                category_field: Optional[str],
                second_field: Optional[str] = None,
                category_kind: Optional[str] = None) -> Dict[str, Any]:
    if chart.kind not in SUPPORTED_CHART_KINDS:
        raise QBLCompileError(
            f"chart '{chart.name}' is a {chart.kind}, which is not a QBL chart type. "
            f"Supported kinds are {', '.join(sorted(SUPPORTED_CHART_KINDS))}"
        )

    series = {"Source": _ref(Field=value_field), "SummarizeBy": chart.summarize_by}

    def second(prop: str) -> Dict[str, Any]:
        if second_field is None:
            raise QBLCompileError(
                f"chart '{chart.name}' is a {chart.kind}, which plots a second "
                f"measure as its {prop}; set second_field"
            )
        return {"Source": _ref(Field=second_field), "SummarizeBy": chart.summarize_by}

    if chart.kind in GAUGE_CHARTS:
        return {
            "Name": chart.name,
            "Data": {**series, "Label": chart.name},
            "GaugeLimits": {"StartAt": 0, "Goal": 100},
        }

    if category_field is None:
        raise QBLCompileError(
            f"chart '{chart.name}' is a {chart.kind}, which plots values against a "
            f"category, so it needs a category_field"
        )

    grouped = {"Source": _ref(Field=category_field),
               "GroupBy": _category_group_by(category_kind)}
    category = {**grouped, "Label": chart.name, "HideEmptyCategories": True}

    if chart.kind in PIE_CHARTS:
        return {
            "Name": chart.name,
            "DataDetails": {"Series": grouped, "DataSource": "CountOfRecords",
                            "DataLabels": "Value"},
            "Sorting": {"Order": "Ascending", "SortBy": "Category"},
        }

    if chart.kind in DONUT_CHARTS:
        return {
            "Name": chart.name,
            "DataDetails": {"Data": series, "Series": grouped, "DataLabels": "Value"},
        }

    if chart.kind in FUNNEL_CHARTS:
        return {
            "Name": chart.name, "Data": series, "Series": grouped,
            "Sorting": {"Order": "Ascending"}, "DataLabels": "Value",
        }

    if chart.kind in HEATMAP_CHARTS:
        return {
            "Name": chart.name,
            "DataDetails": {
                "DataAxis": series,
                "CategoryAxisX": category,
                "CategoryAxisY": grouped,
                "DataLabels": "Value",
            },
        }

    if chart.kind in LINEBAR_CHARTS:
        axis = {"Data": [series], "Label": chart.name, "LogScale": False}
        return {
            "Name": chart.name,
            "DataDetails": {
                "DataAxisLine": axis, "DataAxisBar": axis, "CategoryAxis": category,
                "Sorting": {"SortBy": "Category", "Direction": "Ascending"},
                "DataLabels": "Value",
            },
        }

    if chart.kind in COMPACT_AXIS_CHARTS:
        compact_series = dict(series)
        if chart.kind not in COMPACT_WITHOUT_LEGEND_COLOR:
            compact_series.setdefault("LegendColor", DEFAULT_SERIES_COLOR)
        compact_category = dict(grouped)
        axis_block: Dict[str, Any] = {"Data": compact_series}
        if chart.kind not in COMPACT_WITHOUT_AXIS_LABELS:
            axis_block["Label"] = None
            axis_block["LogScale"] = False
            compact_category.setdefault("Label", None)
        compact_category.setdefault("HideEmptyCategories", False)
        details: Dict[str, Any] = {
            "DataAxis": axis_block,
            "CategoryAxis": compact_category,
            "Sorting": {"SortBy": "Category", "Direction": "Ascending"},
            "DataLabels": "Value",
        }
        prop = SECOND_MEASURE_PROPERTY.get(chart.kind)
        if prop:
            details[prop] = {"Source": second(prop)["Source"]}
        return {"Name": chart.name, "DataDetails": details}

    axis: Dict[str, Any] = {"Data": [series]}
    if chart.kind != "Streamgraph":
        axis["Label"] = chart.name
        axis["LogScale"] = False

    details = {
        ("DataAxisPrimary" if chart.kind == "Line" else "DataAxis"): axis,
        "CategoryAxis": category,
        "DataLabels": "Value",
    }
    if chart.kind not in NO_SORT_BY_CHARTS:
        details["Sorting"] = {"SortBy": "Category", "Direction": "Ascending"}
    if chart.kind in GOAL_LINE_CHARTS:
        details["GoalLine"] = {"Goal": 0, "Label": None}
    if chart.kind == "Bubble":
        details["BubbleSize"] = second("BubbleSize")
    return {"Name": chart.name, "DataDetails": details}


def _default_form(table: TableSpec,
                  parents_of: Dict[str, List[RelationshipSpec]]) -> Optional[FormSpec]:
    if table.legacy_form is not None:
        return None
    labels: List[Any] = []
    for rel in parents_of.get(table.name, []):
        reference = rel.reference_label or f"Related {rel.parent}"
        proxy = _proxy_lookup(table, rel)
        if proxy is None:
            labels.append(reference)
            continue
        labels.append(FormElementSpec(
            field=reference, properties={"ModesToShowIn": ["Create", "Edit"]}))
        labels.append(FormElementSpec(
            field=proxy.label, label=reference,
            properties={"ModesToShowIn": ["View"]}))
    proxies = set(_proxy_lookups(table, parents_of))
    labels += [f.label for f in table.fields
               if f.kind != "ReportLink" and f.label not in proxies]
    if not labels:
        return None
    return FormSpec(sections=[FormSectionSpec(columns=[FormColumnSpec(labels)])])


def _section_modes(section: FormSectionSpec, form: FormSpec) -> List[str]:
    if section.modes is None:
        return list(FORM_V2_MODES)

    unknown = [mode for mode in section.modes if mode not in FORM_V2_MODES]
    if unknown:
        raise QBLCompileError(
            f"form '{form.name}' shows a section in {', '.join(unknown)}; the "
            f"modes are {', '.join(FORM_V2_MODES)} - the third is spelled "
            f"'Create', not 'Add'"
        )
    if not section.modes:
        raise QBLCompileError(
            f"form '{form.name}' has a section showing in no mode at all, which "
            f"renders it blank with no error. Name the modes it should show in, "
            f"or leave `modes` unset for all of them"
        )
    return [mode for mode in FORM_V2_MODES if mode in section.modes]


def _column_widths(section: FormSectionSpec, form: FormSpec, index: int) -> List[int]:
    where = f"form '{form.name}' section {index}"
    given = [column.layout_width for column in section.columns]

    for width in given:
        if width is None:
            continue
        if not isinstance(width, int) or isinstance(width, bool):
            raise QBLCompileError(
                f"{where} sets a column width of {width!r}; `LayoutWidth` is a "
                f"whole number of columns and the platform answers anything "
                f"else `BadProperty: LayoutWidth`"
            )
        if width < 1:
            raise QBLCompileError(
                f"{where} sets a column width of {width}; a column spans at "
                f"least one of the section's {FORM_SECTION_WIDTH}. The platform "
                f"accepts {width} without complaint and renders a column with "
                f"nothing in it"
            )

    if len(section.columns) > FORM_SECTION_MAX_COLUMNS:
        raise QBLCompileError(
            f"{where} has {len(section.columns)} columns; a section holds at "
            f"most {FORM_SECTION_MAX_COLUMNS} - `TooManyChildren: Node has too "
            f"many children of type Columns.` Split it across two sections"
        )

    spoken = sum(width for width in given if width is not None)
    if spoken > FORM_SECTION_WIDTH:
        raise QBLCompileError(
            f"{where} sets column widths totalling {spoken}, which exceeds the "
            f"{FORM_SECTION_WIDTH} a section has to give. The platform answers "
            f"`BadMaxItems: the total layout width of all columns is {spoken}, "
            f"which exceeds the maximum allowed value of {FORM_SECTION_WIDTH}.` "
            f"Widths totalling less than {FORM_SECTION_WIDTH} are accepted; more "
            f"is not"
        )

    unset = [position for position, width in enumerate(given) if width is None]
    if not unset:
        return [width for width in given if width is not None]

    share, remainder = divmod(FORM_SECTION_WIDTH - spoken, len(unset))
    if share < 1:
        raise QBLCompileError(
            f"{where} leaves {len(unset)} column(s) for the "
            f"{FORM_SECTION_WIDTH - spoken} of its {FORM_SECTION_WIDTH} that "
            f"are unspoken for, which is less than one each. Give them widths, "
            f"or take width back from the columns that named one"
        )

    widths = list(given)
    for rank, position in enumerate(unset):
        widths[position] = share + (1 if rank < remainder else 0)
    return widths


V2_ELEMENT_DEFAULTS = {
    "QB::FormV2::Element::Field": {"LabelMode": "Default"},
    "QB::FormV2::Element::RichText": {
        "LabelMode": "Default", "LabelOverride": None,
        "BackgroundColor": None, "ShowBackgroundColor": False,
        "Width": "Default",
    },
    "QB::FormV2::Element::Report": {
        "LabelMode": "Default", "LabelOverride": None,
        "AllowCreateRecords": True, "HideToolbar": False,
        "ShouldOpenInEmbedded": True, "SubForm": "Default",
    },
}

V2_ELEMENT_KINDS = ("Field", "Report", "RichText", "Group")

V2_ELEMENT_WITHOUT_MODES = "QB::FormV2::Element::Group"


def _v2_element_kind(member: FormElementSpec, form: FormSpec) -> str:
    if member.kind:
        if member.kind not in V2_ELEMENT_KINDS:
            extra = ""
            if member.kind == "Text":
                extra = (" - prose on a FormV2 is a 'RichText', and `content` "
                         "alone is enough to say so")
            elif member.kind == "Empty":
                extra = (" - a FormV2 has no spacer; give the column fewer "
                         "elements, or narrow it")
            raise QBLCompileError(
                f"form '{form.name}' has an element of kind '{member.kind}'; a "
                f"FormV2 element is one of {', '.join(V2_ELEMENT_KINDS)}{extra}"
            )
        return member.kind
    if member.members:
        return "Group"
    if member.content is not None:
        return "RichText"
    if member.embedded_report is not None:
        return "Report"
    if member.field is not None:
        return "Field"
    raise QBLCompileError(
        f"form '{form.name}' has an element that names no field, no content, "
        f"no embedded report and no members, so there is nothing for it to be"
    )


def _placed_twice(form: FormSpec, first: str, second: str) -> str:
    if first == second:
        return (f"form '{form.name}' places '{first}' twice in one column; "
                f"a column holds each field once")
    return (f"form '{form.name}' places '{first}' and '{second}' in one column, "
            f"which are one and the same element to QBL; a column holds each "
            f"field once")


def _v2_element(member: Any, form: FormSpec, modes: Sequence[str],
                table: TableSpec, spec: AppSpec, anonymous: List[int],
                in_group: bool = False) -> Tuple[str, Dict[str, Any]]:
    if not isinstance(member, FormElementSpec):
        key = logical_id("FormV2Element", f"{form.name}_{member}")
        return key, {
            "Type": "QB::FormV2::Element::Field",
            "Properties": {
                "Field": _ref(Field=logical_id("Field", str(member))),
                "LabelMode": "Default",
                "ModesToShowIn": list(modes),
            },
        }

    kind = _v2_element_kind(member, form)
    qbl_type = f"QB::FormV2::Element::{kind}"

    if kind == "Group" and in_group:
        raise QBLCompileError(
            f"form '{form.name}' puts a group inside a group; the platform "
            f"refuses that with `BadChild: Group element cannot contain "
            f"nested group elements.` Flatten it, or give the outer group's "
            f"members their own column"
        )

    properties: Dict[str, Any] = dict(V2_ELEMENT_DEFAULTS.get(qbl_type, {}))
    if qbl_type != V2_ELEMENT_WITHOUT_MODES:
        properties["ModesToShowIn"] = list(modes)

    node: Dict[str, Any] = {"Type": qbl_type, "Properties": properties}

    if kind == "Field":
        if member.field is None:
            raise QBLCompileError(
                f"form '{form.name}' has a field element naming no field")
        properties["Field"] = _ref(Field=logical_id("Field", member.field))
    elif kind == "Report":
        if member.embedded_report is None:
            raise QBLCompileError(
                f"form '{form.name}' has a report element naming no report to "
                f"show; set `embedded_report`")
        table_name, target = _embedded_target(member, table, spec)
        properties["Report"] = _ref(Table=logical_id("Table", table_name),
                                    Report=target)
        if member.field is not None:
            properties["ReportLinkField"] = _ref(
                Field=logical_id("Field", member.field))
    elif kind == "RichText":
        if member.content is None:
            raise QBLCompileError(
                f"form '{form.name}' has a rich-text element with no content; "
                f"set `content`")
        properties["Content"] = member.content
    elif kind == "Group":
        if not member.members:
            raise QBLCompileError(
                f"form '{form.name}' has a group holding no elements; give it "
                f"`members`, or remove it")
        node["Elements"] = _v2_elements(
            member.members, form, modes, table, spec, anonymous, in_group=True)

    if member.label is not None:
        properties["LabelOverride"] = member.label
        properties["LabelMode"] = "Custom"
    elif kind == "Group":
        node.pop("Properties")

    if member.properties:
        _require_known_properties(
            qbl_type, member.properties, f"form element on '{form.name}'")
        _merge_properties(node.setdefault("Properties", {}), member.properties)

    if member.field is not None:
        key = logical_id("FormV2Element", f"{form.name}_{member.field}")
    else:
        anonymous[0] += 1
        key = logical_id("FormV2Element", f"{form.name}_{kind}_{anonymous[0]}")
    return key, node


def _v2_elements(members: Sequence[Any], form: FormSpec, modes: Sequence[str],
                 table: TableSpec, spec: AppSpec, anonymous: List[int],
                 in_group: bool = False) -> Dict[str, Any]:
    elements: Dict[str, Any] = {}
    placed: Dict[str, str] = {}
    for member in members:
        key, node = _v2_element(member, form, modes, table, spec, anonymous,
                                in_group=in_group)
        label = member.field if isinstance(member, FormElementSpec) else str(member)
        if key in placed:
            raise QBLCompileError(_placed_twice(form, placed[key], label or key))
        placed[key] = label or key
        elements[key] = node
    return elements


def _form_layout(form: FormSpec, minter: "_IdMinter", table: TableSpec,
                 spec: AppSpec) -> Dict[str, Any]:
    anonymous = [0]
    sections: Dict[str, Any] = {}
    section_keys: Dict[str, str] = {}
    column_keys: Dict[Tuple[str, int], str] = {}
    for index, section in enumerate(form.sections, start=1):
        modes = _section_modes(section, form)
        widths = _column_widths(section, form, index)
        columns: Dict[str, Any] = {}
        for column_index, column in enumerate(section.columns, start=1):
            elements = _v2_elements(
                column.fields, form, modes, table, spec, anonymous)
            column_key = logical_id("FormV2Column", f"{form.name}_{index}_{column_index}")
            if section.title:
                column_keys.setdefault((section.title, column_index), column_key)
            columns[column_key] = {
                "Type": "QB::FormV2::Column",
                "Properties": {"LayoutWidth": widths[column_index - 1]},
                "Elements": elements,
            }
        section_key = logical_id("FormV2Section", f"{form.name}_{index}")
        if section.title:
            section_keys.setdefault(section.title, section_key)
        section_properties: Dict[str, Any] = {"ModesToShowIn": list(modes)}
        if section.title:
            section_properties["Title"] = section.title
        else:
            section_properties["IsCollapsible"] = False
        sections[section_key] = {
            "Type": "QB::FormV2::Section",
            "Properties": section_properties,
            "Columns": columns,
        }

    page_key = logical_id("FormV2Page", form.name)
    layout: Dict[str, Any] = {
        "Pages": {
            page_key: {
                "Type": "QB::FormV2::Page",
                "Id": minter.take("form_page"),
                "Properties": {"Name": form.name},
                "Sections": sections,
            }
        }
    }

    if form.rules:
        layout["Rules"] = {
            logical_id("FormV2Rule", f"{form.name}_{rule.name}"):
                _v2_rule(rule, page_key, section_keys, column_keys)
            for rule in form.rules
        }

    return layout


ACTION_SPELLINGS = (("UnRequire", "Unrequire"), ("MakeReadOnly", "MakeReadonly"))


def _action_kind(action: str, legacy: bool) -> str:
    for legacy_spelling, v2_spelling in ACTION_SPELLINGS:
        if action in (legacy_spelling, v2_spelling):
            return legacy_spelling if legacy else v2_spelling
    return action


V2_RUN_ON = ("RecordOpenSaveOrChange", "RecordSave", "RecordSaveAfterValidating")

V2_TARGETED_ACTIONS = ("Hide", "Show", "Require", "Unrequire", "MakeReadonly",
                       "MakeEditable", "SetColor", "SetLabel")


def _v2_condition(condition: FormRuleConditionSpec, rule_name: str) -> Dict[str, Any]:
    if condition.kind == "Formula":
        if not condition.formula:
            raise QBLCompileError(
                f"form rule '{rule_name}' has a Formula condition with no formula")
        return {"Type": "QB::FormV2::Rule::Condition::FormulaIsTrue",
                "Properties": {"Formula": condition.formula}}
    if condition.kind == "User":
        if not condition.role:
            raise QBLCompileError(
                f"form rule '{rule_name}' has a user condition naming no role")
        return {"Type": "QB::FormV2::Rule::Condition::Role", "Properties": {
            "Comparison": (condition.comparison
                           if condition.comparison != "IsEqualTo" else "IsInRole"),
            "Role": _ref(Role=logical_id("Role", condition.role)),
        }}
    if condition.kind not in ("Field", "FieldIncludes"):
        raise QBLCompileError(
            f"form rule '{rule_name}' has condition kind '{condition.kind}', which "
            f"a FormV2 rule cannot express; it takes Field, FieldIncludes, User "
            f"and Formula")
    if not condition.field:
        raise QBLCompileError(
            f"form rule '{rule_name}' has a {condition.kind} condition naming no "
            f"field")
    comparison = condition.comparison
    if condition.kind == "FieldIncludes" and comparison == "IsEqualTo":
        comparison = "Includes"
    value = condition.value
    if comparison in ("Includes", "DoesNotInclude") and not (
            isinstance(value, Mapping) and "Choices" in value):
        value = {"Choices": list(value) if isinstance(value, (list, tuple))
                 else [value]}
    elif value == "":
        value = None
    return {"Type": "QB::FormV2::Rule::Condition::Field", "Properties": {
        "Field": _ref(Field=logical_id("Field", condition.field)),
        "Comparison": comparison,
        "Value": value,
    }}


def _v2_action(action: FormRuleActionSpec, rule_name: str, page_key: str,
               section_keys: Mapping[str, str],
               column_keys: Mapping[Tuple[str, int], str]) -> Dict[str, Any]:
    kind = _action_kind(action.action, legacy=False)
    from qblparser.qbl_schema import QBL_SCHEMA

    qbl_type = f"QB::FormV2::Rule::Action::{kind}"
    if qbl_type not in QBL_SCHEMA:
        raise QBLCompileError(
            f"form rule '{rule_name}' has action '{action.action}', which a FormV2 "
            f"rule does not have")
    properties: Dict[str, Any] = {}
    if kind == "SetColor":
        if action.target_field is not None or action.target_section is None:
            raise QBLCompileError(
                f"form rule '{rule_name}': SetColor colours a column of a section, "
                f"so it takes a target_section (and target_column), not a field - "
                f"pointed at a field it hangs the create")
        column_key = column_keys.get((action.target_section, action.target_column))
        if column_key is None:
            raise QBLCompileError(
                f"form rule '{rule_name}': section '{action.target_section}' has no "
                f"column {action.target_column}")
        if not action.color:
            raise QBLCompileError(f"form rule '{rule_name}': SetColor needs a color")
        properties["Target"] = _ref(FormV2Page=page_key,
                                    FormV2Section=section_keys[action.target_section],
                                    FormV2Column=column_key)
        properties["Color"] = action.color
    elif kind in V2_TARGETED_ACTIONS:
        if action.target_section is not None:
            if action.target_field is not None:
                raise QBLCompileError(
                    f"form rule '{rule_name}' targets both a field and a section "
                    f"with one '{kind}'; use two actions")
            section_key = section_keys.get(action.target_section)
            if section_key is None:
                raise QBLCompileError(
                    f"form rule '{rule_name}' targets section "
                    f"'{action.target_section}', which is not the title of a "
                    f"section on this form")
            properties["Target"] = _ref(FormV2Page=page_key,
                                        FormV2Section=section_key)
        elif action.target_field is not None:
            properties["Target"] = _ref(Field=logical_id("Field", action.target_field))
        else:
            raise QBLCompileError(
                f"form rule '{rule_name}': '{kind}' needs a target_field or a "
                f"target_section")
        if kind == "SetLabel":
            if not action.label:
                raise QBLCompileError(
                    f"form rule '{rule_name}': SetLabel needs a label")
            properties["Label"] = action.label
    elif kind == "Change":
        if action.target_field is None:
            raise QBLCompileError(
                f"form rule '{rule_name}': Change needs a target_field")
        properties["Field"] = _ref(Field=logical_id("Field", action.target_field))
        properties["Value"] = (_ref(Field=logical_id("Field", action.value_field))
                               if action.value_field is not None else action.value)
    elif kind in ("DisplayMessage", "AbortSave"):
        if action.target_field is not None or action.target_section is not None:
            raise QBLCompileError(
                f"form rule '{rule_name}': {kind} acts on the record, so it "
                f"takes no target")
        properties["Message"] = action.message or ""
        if kind == "DisplayMessage":
            properties["MessageType"] = action.message_type
            if action.message_level is not None:
                properties["MessageLevel"] = action.message_level
    return {"Type": qbl_type, "Properties": properties}


def _v2_rule(rule: FormRuleSpec, page_key: str,
             section_keys: Mapping[str, str],
             column_keys: Mapping[Tuple[str, int], str]) -> Dict[str, Any]:
    if rule.trigger is not None and rule.trigger.kind != "User":
        raise QBLCompileError(
            f"form rule '{rule.name}' has a {rule.trigger.kind} trigger, which is "
            f"a legacy form rule's; a FormV2 rule runs on `run_on` and its "
            f"conditions")
    if rule.run_on not in V2_RUN_ON:
        raise QBLCompileError(
            f"form rule '{rule.name}' runs on '{rule.run_on}'; the choices are "
            f"{', '.join(V2_RUN_ON)}")
    if rule.true_when not in ("All", "Any"):
        raise QBLCompileError(
            f"form rule '{rule.name}' has true_when '{rule.true_when}'; it is "
            f"All or Any")

    conditions: List[Dict[str, Any]] = []
    if rule.when_field is not None:
        conditions.append(_v2_condition(FormRuleConditionSpec(
            field=rule.when_field, value=rule.equals, comparison=rule.comparison),
            rule.name))
    if rule.trigger is not None:
        conditions.append(_v2_condition(FormRuleConditionSpec(
            kind="User", role=rule.trigger.role,
            comparison=rule.trigger.comparison), rule.name))
    conditions += [_v2_condition(c, rule.name) for c in rule.conditions]
    if not conditions:
        raise QBLCompileError(
            f"form rule '{rule.name}' has no condition, so nothing makes it fire")
    if (len(conditions) == 1
            and conditions[0]["Type"].endswith("FormulaIsTrue")):
        when = conditions
    else:
        group: Dict[str, Any] = {"Type": "QB::FormV2::Rule::Condition::Group",
                                 "When": conditions}
        if rule.true_when != "All" or len(conditions) > 1:
            group["Properties"] = {"TrueWhen": rule.true_when}
        when = [group]

    actions: List[FormRuleActionSpec] = []
    if rule.target_field is not None or not rule.actions:
        actions.append(FormRuleActionSpec(action=rule.action,
                                          target_field=rule.target_field))
    actions += rule.actions

    properties: Dict[str, Any] = {"Name": rule.name, "RunOn": rule.run_on}
    if rule.disabled:
        properties["Disabled"] = True
    if rule.fire_only_on_change:
        properties["FireOnlyOnChange"] = True
    if rule.properties:
        _require_known_properties(
            "QB::FormV2::Rule", rule.properties, f"form rule '{rule.name}'")
        _merge_properties(properties, rule.properties)
    return {
        "Type": "QB::FormV2::Rule",
        "Properties": properties,
        "When": when,
        "Actions": [_v2_action(a, rule.name, page_key, section_keys, column_keys)
                    for a in actions],
    }


PAGE_BODY_PROPERTY = {"RichTextPage": "RawText", "CodePage": "RawCode"}

CODE_PAGE_ATTRIBUTES = ("purpose", "native_gap", "requests_per_second", "drafted_on")


def _check_code_page(page: PageSpec) -> None:
    if page.kind != "CodePage":
        stray = [name for name in CODE_PAGE_ATTRIBUTES if getattr(page, name) is not None]
        if page.sensitive_data:
            stray.append("sensitive_data")
        if page.auth != "TempToken":
            stray.append("auth")
        if stray:
            raise QBLCompileError(
                f"page '{page.name}' is a {page.kind}, and {', '.join(stray)} "
                f"describe a code page")
        return
    where = f"code page '{page.name}'"
    if not _code_pages.CODE_PAGE_NAME.match(page.name):
        raise QBLCompileError(
            f"{where}: a code page's name is the file it is served as, and the "
            f"extension sets its content type - without .html, .htm, .js or .css "
            f"Quickbase serves it as plain text and shows the source. Use letters, "
            f"digits, dots, dashes and underscores, no spaces, e.g. "
            f"'{re.sub(r'[^A-Za-z0-9._-]+', '-', page.name).strip('-').lower() or 'page'}"
            f"{'' if page.name.lower().endswith(_code_pages.CODE_PAGE_EXTENSIONS) else '.html'}'")
    if not page.body.strip():
        raise QBLCompileError(f"{where} has no body")
    if page.auth not in _code_pages.AUTH_PATTERNS:
        raise QBLCompileError(
            f"{where} has auth '{page.auth}'; known patterns are "
            f"{', '.join(_code_pages.AUTH_PATTERNS)}. There is no stored-token "
            f"pattern: a token in a code page is readable by everyone who opens it")
    if _code_pages.is_entry_page(page.name) and not (page.native_gap or "").strip():
        raise QBLCompileError(
            f"{where} states no native_gap. A code page is the last resort: say "
            f"which native feature - a formula, form rule, report, dashboard, "
            f"pipeline, email or document template - was considered and why it "
            f"does not meet the requirement")
    if "Review status:" in page.body:
        raise QBLCompileError(
            f"{where} carries its own review header; the builder writes one from "
            f"the spec and the code, so remove it from the body")


def _code_page_body(page: PageSpec, tables: Mapping[str, Any],
                    opened_by: Sequence[str]) -> str:

    def field_id(table_name: str, label: str) -> Optional[int]:
        table = tables.get(logical_id("Table", table_name)) or {}
        if (table.get("Properties") or {}).get("Name") != table_name:
            return None
        for node in (table.get("Fields") or {}).values():
            if (node.get("Properties") or {}).get("Label") == label:
                return node.get("Id")
        return None

    body = _code_pages.resolve_field_tokens(page.body, field_id, f"code page '{page.name}'")
    return _code_pages.review_header(page, opened_by, body) + body


def _code_page_button(field_spec: FieldSpec, table: TableSpec,
                      spec: AppSpec) -> Dict[str, Any]:
    where = f"field '{field_spec.label}' on '{table.name}'"
    if FIELD_KIND_ALIASES.get(field_spec.kind, field_spec.kind) != "URL::Formula":
        raise QBLCompileError(
            f"{where} opens a page, which only a 'URL::Formula' field can; its kind "
            f"is '{field_spec.kind}'")
    if field_spec.formula is not None:
        raise QBLCompileError(
            f"{where} sets both formula and opens_page; opens_page writes the formula")
    page = next((p for p in spec.pages if p.name == field_spec.opens_page), None)
    if page is None or page.kind != "CodePage" or not _code_pages.is_entry_page(page.name):
        known = sorted(p.name for p in spec.pages
                       if p.kind == "CodePage" and _code_pages.is_entry_page(p.name))
        raise QBLCompileError(
            f"{where} opens '{field_spec.opens_page}', which is not an .html code "
            f"page in this spec. Known: {known}")
    if not _code_pages.CODE_PAGE_NAME.match(page.name):
        _check_code_page(page)
    return {
        "Formula": (f'URLRoot() & "db/" & Dbid() & "?a=dbpage&pageName={page.name}'
                    f'&rid=" & [Record ID#]'),
        "DisplayAsButton": True,
        "LinkText": field_spec.label,
    }


DEFAULT_DASHBOARD_NAME = "Overview"


def _default_dashboards(spec: AppSpec,
                        report_keys: Dict[Tuple[str, str], str]) -> List[DashboardSpec]:
    widgets: List[DashboardWidgetSpec] = []
    for table in spec.tables:
        reports = table.reports or [ReportSpec(f"All {table.name}")]
        name = reports[0].name
        if (table.name, name) not in report_keys:
            continue
        widgets.append(DashboardWidgetSpec(
            kind="Table", title=table.name, table=table.name, report=name,
            width=6,
        ))
    if not widgets:
        return []
    return [DashboardSpec(name=DEFAULT_DASHBOARD_NAME, widgets=widgets)]


def _pages(spec: AppSpec, minter: "_IdMinter",
           report_keys: Dict[Tuple[str, str], str],
           tables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    resources: Dict[str, Any] = {}

    home_key = logical_id("Page", spec.home_page_name)
    home: Dict[str, Any] = {
        "Type": "QB::HomePage",
        "Id": minter.take("page"),
        "Properties": {"Name": spec.home_page_name},
    }
    page_ids: Dict[str, int] = {spec.home_page_name: home["Id"]}
    for page in spec.pages:
        page_ids[page.name] = minter.take("page")
    context = _HomeContext(
        report_keys, tables or {}, page_ids, home["Id"],
        code_pages=tuple(p.name for p in spec.pages
                         if p.kind == "CodePage" and _code_pages.is_entry_page(p.name)),
        code_assets=tuple(p.name for p in spec.pages
                          if p.kind == "CodePage" and not _code_pages.is_entry_page(p.name)))

    widget_ids = iter(range(HOME_WIDGET_FIRST_ID, HOME_WIDGET_FIRST_ID + 10_000))
    for section, row_prefix, row_type in (
        ("MainSection", "MainSectionHomePageRow", "QB::HomePage::MainSectionRow"),
        ("Sidebar", "SidebarHomePageRow", "QB::HomePage::SidebarRow"),
    ):
        rows = _home_rows([w for w in spec.home_widgets if w.section == section], section)
        if not rows:
            continue
        home[section] = {
            logical_id(row_prefix, str(index)): {
                "Type": row_type,
                "Widgets": {
                    f"$HomePageWidget_{next(widget_ids)}":
                        _home_widget(widget, context, width)
                    for widget, width in zip(row, _home_row_widths(row, section))
                },
            }
            for index, row in enumerate(rows, start=1)
        }

    unknown_sections = sorted(
        {w.section for w in spec.home_widgets} - {"MainSection", "Sidebar"}
    )
    if unknown_sections:
        raise QBLCompileError(
            f"home widget section {', '.join(unknown_sections)} is not a home page "
            f"container; use MainSection or Sidebar"
        )

    resources[home_key] = home

    opened_by = _code_pages.launchers(spec)
    for page in spec.pages:
        body_property = PAGE_BODY_PROPERTY.get(page.kind)
        if body_property is None:
            raise QBLCompileError(
                f"page '{page.name}' has kind '{page.kind}'; known kinds are "
                f"{', '.join(sorted(PAGE_BODY_PROPERTY))}"
            )
        _check_code_page(page)
        body = page.body
        if page.kind == "CodePage":
            body = _code_page_body(page, tables or {}, opened_by.get(page.name, []))
        resources[logical_id("Page", page.name)] = {
            "Type": f"QB::{page.kind}",
            "Id": page_ids[page.name],
            "Properties": {"Name": page.name, body_property: body},
        }

    dashboards = spec.dashboards or _default_dashboards(spec, report_keys)
    for dashboard in dashboards:
        resources[logical_id("Dashboard", dashboard.name)] = _dashboard(
            dashboard, report_keys
        )

    properties: Dict[str, Any] = {}
    role_defaults = _page_role_defaults(spec, dashboards)
    if role_defaults:
        properties["RoleDefaults"] = role_defaults

    return {"Properties": properties, "Resources": resources}


def _page_role_defaults(spec: AppSpec,
                        dashboards: Sequence[DashboardSpec]) -> Dict[str, Any]:
    if not spec.role_home_pages:
        if not dashboards:
            return {}
        return {"Everyone": _ref(
            Dashboard=logical_id("Dashboard", dashboards[0].name))}

    page_names = {page.name for page in spec.pages}
    dashboard_names = {dashboard.name for dashboard in dashboards}
    defaults: Dict[str, Any] = {}
    role_names = {role.name for role in spec.roles}

    for role_name, page_name in spec.role_home_pages.items():
        if role_name != "Everyone" and role_name not in role_names:
            raise QBLCompileError(
                f"role_home_pages names '{role_name}', which is not a role in this spec"
            )
        if page_name == "UseDefault":
            target: Any = "UseDefault"
        elif page_name == spec.home_page_name or page_name in page_names:
            target = _ref(Page=logical_id("Page", page_name))
        elif page_name in dashboard_names:
            target = _ref(Dashboard=logical_id("Dashboard", page_name))
        else:
            known = sorted(page_names | dashboard_names | {spec.home_page_name})
            raise QBLCompileError(
                f"role '{role_name}' opens on '{page_name}', which is neither a "
                f"page nor a dashboard in this spec. Known: {known}"
            )
        if role_name == "Everyone":
            defaults["Everyone"] = target
        else:
            defaults[logical_id("Role", role_name)] = {
                "Desktop": target,
                "Mobile": "UseDesktop",
            }

    return defaults


_WIDGET_CHILD_CONTAINERS = {
    "ButtonBar": ("Buttons", "QB::HomePage::Widget::Button"),
    "LinkBar": ("Links", "QB::HomePage::Widget::Link"),
}

HOME_WIDGET_FIRST_ID = 101

from qblparser.validators.structure import (
    HOME_REPORT_VISIBLE_ROWS,
    HOME_REPORTS_LIST_MAX_TABLES,
    HOME_ROW_LIMITS,
    HOME_ROW_WIDTHS,
    HOME_WIDGET_MIN_HEIGHT,
)

_HOME_WIDTH_COMPLEMENT = {"50%": "50%", "66.6666%": "33.3333%", "33.3333%": "66.6666%"}


@dataclass
class _HomeContext:

    report_keys: Dict[Tuple[str, str], str]
    tables: Dict[str, Any]
    page_ids: Dict[str, int]
    home_id: int
    code_pages: Tuple[str, ...] = ()
    code_assets: Tuple[str, ...] = ()


def _home_rows(widgets: Sequence[HomeWidgetSpec], section: str) -> List[List[HomeWidgetSpec]]:
    rows: List[List[HomeWidgetSpec]] = []
    named: Dict[str, List[HomeWidgetSpec]] = {}
    for widget in widgets:
        if widget.row is None:
            rows.append([widget])
        elif widget.row in named:
            named[widget.row].append(widget)
        else:
            named[widget.row] = [widget]
            rows.append(named[widget.row])
    limit = HOME_ROW_LIMITS.get(section, 1)
    for row in rows:
        if len(row) > limit:
            raise QBLCompileError(
                f"home page row '{row[0].row}' in the {section} holds {len(row)} "
                f"widgets; a {section} row holds at most {limit}"
            )
    return rows


def _home_row_widths(row: Sequence[HomeWidgetSpec], section: str) -> Tuple[str, ...]:
    asked = [w.width for w in row]
    if all(width is None for width in asked):
        return HOME_ROW_WIDTHS[len(row)][0]
    if len(row) == 2 and asked.count(None) == 1:
        given = next(width for width in asked if width is not None)
        other = _HOME_WIDTH_COMPLEMENT.get(given)
        if other is not None:
            return tuple(width if width is not None else other for width in asked)
    widths = tuple(width if width is not None else "100%" for width in asked)
    if widths not in HOME_ROW_WIDTHS[len(row)]:
        allowed = " or ".join(" & ".join(combo) for combo in HOME_ROW_WIDTHS[len(row)])
        raise QBLCompileError(
            f"home page row {'named ' + repr(row[0].row) + ' ' if row[0].row else ''}"
            f"has widths {' & '.join(widths)}; a row of {len(row)} takes {allowed}"
        )
    return widths


def _home_widget(widget: HomeWidgetSpec, context: "_HomeContext",
                 width: str = "100%") -> Dict[str, Any]:
    qbl_type = f"QB::HomePage::Widget::{widget.kind}"
    properties: Dict[str, Any] = {"Width": width}
    if widget.title:
        properties["Title"] = widget.title
        properties["ShowTitle"] = True
    if widget.kind == "Report":
        properties["Report"] = _report_reference(widget, context.report_keys)
    if widget.height is not None:
        properties["Height"] = f"{widget.height}px"
    if widget.max_rows is not None:
        if widget.kind != "Report":
            raise QBLCompileError(
                f"max_rows applies to a Report widget, not a {widget.kind}")
        properties["MaximumVisibleRows"] = widget.max_rows
    if widget.tables:
        if widget.kind != "ReportsList":
            raise QBLCompileError(
                f"a {widget.kind} widget lists no tables; a ReportsList does")
        if len(widget.tables) > HOME_REPORTS_LIST_MAX_TABLES:
            raise QBLCompileError(
                f"a reports list names {len(widget.tables)} tables; the platform "
                f"takes at most {HOME_REPORTS_LIST_MAX_TABLES}")
        properties["ShowReportsFrom"] = "SelectedTables"
        properties["TargetTables"] = [
            _ref(Table=_home_table_key(name, context, "reports list"))
            for name in widget.tables
        ]
    if widget.fields:
        properties["SearchTarget"] = "SelectedFields"
        if (widget.kind == "Search" and not widget.table
                and "SearchTable" not in widget.properties):
            raise QBLCompileError(
                f"the {widget.kind} widget "
                f"{'named ' + repr(widget.title) if widget.title else ''} "
                f"searches named fields, so it needs the table those fields "
                f"belong to; set table. Without `SearchTable` nothing says "
                f"which table `TargetField` refers to and the whole solution "
                f"fails to create."
            )
        if widget.table:
            properties["SearchTable"] = _ref(
                Table=logical_id("Table", widget.table))
    if widget.properties:
        _require_known_properties(
            qbl_type, widget.properties, f"{widget.kind} widget"
        )
        properties.update(widget.properties)
    _check_home_widget_values(widget, properties)

    node: Dict[str, Any] = {"Type": qbl_type, "Properties": properties}

    if widget.links:
        container, child_type = _WIDGET_CHILD_CONTAINERS.get(
            widget.kind, ("Buttons", "QB::HomePage::Widget::Button")
        )
        if widget.kind not in _WIDGET_CHILD_CONTAINERS:
            raise QBLCompileError(
                f"a {widget.kind} widget holds no links or buttons; "
                f"{' or '.join(sorted(_WIDGET_CHILD_CONTAINERS))} does"
            )
        node[container] = {
            logical_id(container.rstrip("s"), f"{widget.title or widget.kind}_{index}"): {
                "Type": child_type,
                "Properties": _widget_link_properties(link, context),
            }
            for index, link in enumerate(widget.links, start=1)
        }

    if widget.fields:
        if widget.kind != "Search":
            raise QBLCompileError(
                f"a {widget.kind} widget searches no fields; a Search widget does"
            )
        node["Fields"] = {}
        for index, searched in enumerate(widget.fields, start=1):
            field_id = _home_field_id(widget, searched, context)
            key = f"$WidgetField_{field_id}" if field_id is not None else logical_id(
                "WidgetField", f"{widget.title or 'Search'}_{index}")
            node["Fields"][key] = {
                "Type": "QB::HomePage::Widget::Field",
                "Properties": _widget_field_properties(searched),
            }

    return node


def _check_home_widget_values(widget: HomeWidgetSpec, properties: Dict[str, Any]) -> None:
    height = properties.get("Height")
    if height is not None:
        match = re.fullmatch(r"(\d+)px", str(height))
        if not match:
            raise QBLCompileError(
                f"a {widget.kind} widget's Height is {height!r}; Quickbase takes "
                f"whole pixels written like '400px'")
        least = HOME_WIDGET_MIN_HEIGHT.get(widget.kind)
        if least is not None and int(match.group(1)) < least:
            raise QBLCompileError(
                f"a {widget.kind} widget is {height} tall; the platform's "
                f"minimum is {least}px")
    rows = properties.get("MaximumVisibleRows")
    if rows is not None and rows != 0 and rows not in HOME_REPORT_VISIBLE_ROWS:
        raise QBLCompileError(
            f"a Report widget shows {rows} rows; Quickbase takes 0 for all rows, "
            f"or 5 to 250")


def _home_table_key(name: str, context: "_HomeContext", subject: str) -> str:
    key = logical_id("Table", name)
    if context.tables and key not in context.tables:
        raise QBLCompileError(
            f"a home page {subject} names table '{name}', which this spec does "
            f"not declare")
    return key


def _home_field_id(widget: HomeWidgetSpec, searched, context: "_HomeContext") -> Optional[int]:
    table = context.tables.get(logical_id("Table", widget.table or ""))
    if not table:
        return None
    node = (table.get("Fields") or {}).get(logical_id("Field", searched.field))
    if node is None:
        raise QBLCompileError(
            f"the search widget {widget.title or ''!r} searches '{searched.field}', "
            f"which table '{widget.table}' does not declare")
    if (node.get("Properties") or {}).get("IsSearchable") is False:
        raise QBLCompileError(
            f"the search widget {widget.title or ''!r} searches '{searched.field}', "
            f"which is not searchable; the widget would show 'You do not have "
            f"access to the information in this widget' and no search box")
    return node.get("Id")


def _guide_properties(guide) -> Dict[str, Any]:
    properties: Dict[str, Any] = {
        "Title": guide.title,
        "LinksTo": _ref(Page=logical_id("Page", guide.links_to)),
    }
    if guide.description is not None:
        properties["Description"] = guide.description
    return properties


def _widget_link_properties(link, context: Optional["_HomeContext"] = None) -> Dict[str, Any]:
    targets = [name for name, value in (("url", link.url), ("table", link.table),
                                        ("page", link.page)) if value]
    if len(targets) > 1:
        raise QBLCompileError(
            f"link '{link.name}' names {' and '.join(targets)}; name one thing to open")
    if link.report and not link.table:
        raise QBLCompileError(
            f"link '{link.name}' names report '{link.report}' without its table")

    link_type, url, redirect = link.link_type, link.url, link.redirect_url
    if link.table:
        if context is None:
            raise QBLCompileError(f"link '{link.name}' names a table outside a home page")
        table_key = _home_table_key(link.table, context, f"link '{link.name}'")
        table = context.tables.get(table_key) or {}
        alias = (table.get("Properties") or {}).get("AliasHint") or _table_alias(link.table)
        if link.report:
            report_key = context.report_keys.get((link.table, link.report))
            if report_key is None:
                raise QBLCompileError(
                    f"link '{link.name}' opens report '{link.report}' on table "
                    f"'{link.table}', which this spec does not declare")
            container = "Charts" if report_key.startswith("$Chart_") else "Reports"
            report_id = ((table.get(container) or {}).get(report_key) or {}).get("Id")
            link_type, url = "Report", f"/db/<!~db~[{alias}]~db~>?a=q&qid={report_id}"
        else:
            link_type, url = "Record", f"/db/<!~db~[{alias}]~db~>?a=nwr"
            if link.return_home and redirect is None:
                redirect = ("&nexturl=%2Fdb%2F<!~db~[_APP_ID_]~db~>%3Fa%3Dshowpage"
                            f"%26pageid%3D{context.home_id}")
    elif link.page:
        if context is None or link.page not in context.page_ids:
            known = sorted(context.page_ids) if context else []
            raise QBLCompileError(
                f"link '{link.name}' opens page '{link.page}', which is not a page "
                f"in this spec. Known: {known}")
        if link.page in context.code_assets:
            raise QBLCompileError(
                f"link '{link.name}' opens '{link.page}', a code page asset; a link "
                f"opens an .html code page, and the page loads the asset")
        if link.page in context.code_pages:
            link_type = "Url"
            url = f"/db/<!~db~[_APP_ID_]~db~>?a=dbpage&pageName={link.page}"
        else:
            link_type = "Page"
            url = f"/db/<!~db~[_APP_ID_]~db~>?a=showpage&pageid={context.page_ids[link.page]}"

    properties: Dict[str, Any] = {"Name": link.name, "LinkType": link_type}
    if url:
        properties["Url"] = url
    if redirect is not None:
        properties["RedirectUrl"] = redirect
    return properties


def _widget_field_properties(searched) -> Dict[str, Any]:
    properties: Dict[str, Any] = {
        "TargetField": _ref(Field=logical_id("Field", searched.field))
    }
    if searched.label is not None:
        properties["Label"] = searched.label
    if searched.placeholder is not None:
        properties["Placeholder"] = searched.placeholder
    return properties


def _report_reference(widget: Any, report_keys: Dict[Tuple[str, str], str]):
    if not widget.table or not widget.report:
        raise QBLCompileError(
            f"a {widget.kind} widget needs a table and a report to point at"
        )
    key = report_keys.get((widget.table, widget.report))
    if key is None:
        raise QBLCompileError(
            f"widget points at report '{widget.report}' on table '{widget.table}', "
            f"which this spec does not declare"
        )
    kind = "Chart" if key.startswith("$Chart_") else "Report"
    return _ref(**{"Table": logical_id("Table", widget.table), kind: key})


DASHBOARD_ROW_WIDTH = 12

DASHBOARD_ROW_COUNTS = (1, 2, 3, 4, 6)


DEFAULT_DASHBOARD_WIDGET_HEIGHTS = {
    "Table": 12,
    "Summary": 12,
    "Chart": 10,
    "Map": 16,
    "Timeline": 12,
    "Calendar": 16,
    "WebPage": 12,
    "Kpi": 6,
    "Spacer": 6,
    "RichText": 4,
    "Search": 4,
}

FALLBACK_DASHBOARD_WIDGET_HEIGHT = 4


def _widget_height(widget: Any) -> int:
    if getattr(widget, "height", None) is not None:
        return widget.height
    return DEFAULT_DASHBOARD_WIDGET_HEIGHTS.get(
        widget.kind, FALLBACK_DASHBOARD_WIDGET_HEIGHT)


def _dashboard_rows(widgets: Sequence[Any]) -> List[List[Any]]:
    rows: List[List[Any]] = []
    current: List[Any] = []
    for widget in widgets:
        wanted = max(1, min(widget.width, DASHBOARD_ROW_WIDTH))
        per_row = max(1, DASHBOARD_ROW_WIDTH // wanted)
        per_row = max(count for count in DASHBOARD_ROW_COUNTS if count <= per_row)
        current.append(widget)
        if len(current) >= per_row:
            rows.append(current)
            current = []
    if current:
        rows.append(current)
    return rows


def _widget_accepts(qbl_type: str, prop: str) -> bool:
    from qblparser.qbl_schema import QBL_SCHEMA

    entry = QBL_SCHEMA.get(qbl_type)
    if not entry:
        return False
    return prop in entry.get("optional", ()) or prop in entry.get("required", ())


def _dashboard(dashboard: DashboardSpec,
               report_keys: Dict[Tuple[str, str], str]) -> Dict[str, Any]:
    if dashboard.tabs:
        if dashboard.widgets or dashboard.filters or dashboard.tab_name != "Main":
            raise QBLCompileError(
                f"dashboard '{dashboard.name}' sets tabs and also widgets, filters "
                f"or tab_name; put every widget and filter inside a tab")
        names = [tab.name for tab in dashboard.tabs]
        repeated = sorted({name for name in names if names.count(name) > 1})
        if repeated:
            raise QBLCompileError(
                f"dashboard '{dashboard.name}' has more than one tab named "
                f"{', '.join(repeat for repeat in repeated)}")
        tabs = [(tab.name, tab.widgets, tab.filters, f"{dashboard.name}_{tab.name}")
                for tab in dashboard.tabs]
    else:
        tabs = [(dashboard.tab_name, dashboard.widgets, dashboard.filters,
                 dashboard.name)]

    return {
        "Type": "QB::Dashboard",
        "Properties": {"Name": dashboard.name},
        "Tabs": {
            logical_id("DashboardTab", f"{dashboard.name}_{name}"):
                _dashboard_tab(name, widgets, filters, prefix, report_keys)
            for name, widgets, filters, prefix in tabs
        },
    }


def _dashboard_tab(name: str, tab_widgets: Sequence[Any], filters: Sequence[Any],
                   prefix: str,
                   report_keys: Dict[Tuple[str, str], str]) -> Dict[str, Any]:
    widgets: Dict[str, Any] = {}
    cursor_y = 0
    index = 0

    for row in _dashboard_rows(tab_widgets):
        width = DASHBOARD_ROW_WIDTH // len(row)
        cursor_x = 0
        row_height = max(_widget_height(widget) for widget in row)
        for widget in row:
            index += 1
            qbl_type = f"QB::Dashboard::Widget::{widget.kind}"
            properties: Dict[str, Any] = {
                "X": cursor_x, "Y": cursor_y,
                "Width": width, "Height": _widget_height(widget),
            }
            if widget.title and _widget_accepts(qbl_type, "Title"):
                properties["Title"] = widget.title
                if _widget_accepts(qbl_type, "ShowTitle"):
                    properties["ShowTitle"] = True
            if _widget_accepts(qbl_type, "Content"):
                properties["Content"] = widget.title or ""
            if _widget_accepts(qbl_type, "Report"):
                properties["Report"] = _report_reference(widget, report_keys)

            widgets[logical_id("DashboardWidget", f"{prefix}_{index}")] = {
                "Type": qbl_type,
                "Properties": properties,
            }
            cursor_x += width
        cursor_y += row_height

    tab: Dict[str, Any] = {
        "Type": "QB::Dashboard::Tab",
        "Properties": {"Name": name, "CanvasVersion": 2},
        "Widgets": widgets,
    }

    if filters:
        tab["Filters"] = {
            logical_id("DashboardFilter", f"{prefix}_{index}"):
                _dashboard_filter(filter_spec, report_keys)
            for index, filter_spec in enumerate(filters, start=1)
        }

    return tab


def _dashboard_filter(filter_spec: Any,
                      report_keys: Dict[Tuple[str, str], str]) -> Dict[str, Any]:
    table_id = logical_id("Table", filter_spec.table)
    targets = []
    for target in filter_spec.targets:
        key = report_keys.get((filter_spec.table, target))
        if key is None:
            raise QBLCompileError(
                f"dashboard filter '{filter_spec.name}' targets '{target}' on table "
                f"'{filter_spec.table}', which this spec does not declare"
            )
        kind = "Chart" if key.startswith("$Chart_") else "Report"
        targets.append({
            "CompareField": _ref(
                Table=table_id, Field=logical_id("Field", filter_spec.field)),
            "Report": _ref(**{"Table": table_id, kind: key}),
            "IsActive": True,
        })

    return {
        "Type": "QB::Dashboard::Filter",
        "Properties": {
            "Name": filter_spec.name,
            "FilterType": filter_spec.filter_type,
            "SearchType": filter_spec.search_type,
            "Targets": targets,
        },
    }


QUICKBASE_CHANNEL_ACCOUNT = "$PipelineChannelAccount_Quickbase"

PIPELINE_TRIGGER_SELECTORS = {
    "create": "on_create", "update": "on_update", "delete": "on_delete",
}

QUICKBASE_RECORD_SELECTORS = frozenset({
    "on_create", "on_update", "on_delete", "on_new_bulk_event", "on_new_event",
    "create", "update", "delete", "search", "fetch_link", "look_up",
})

_UNWRITABLE_FIELD_TYPES = (
    "QB::Field::RecordID", "QB::Field::DateCreated", "QB::Field::DateModified",
    "QB::Field::LastModifiedBy", "QB::Field::Lookup", "QB::Field::Summary",
)

_JINJA_TRIGGER_REFERENCE = re.compile(r"\{\{[^}]*?\ba\.([A-Za-z0-9_]+)")


def pipeline_field_key(label: str) -> str:
    if label == "Record ID#" or label == "Record ID":
        return "id"
    return re.sub(r"[^0-9a-z]+", "_", label.lower()).strip("_")


def pipeline_input_key(label: str) -> str:
    return "_".join(part.capitalize()
                    for part in pipeline_field_key(label).split("_"))


def _pipeline_fields(table_node: Mapping[str, Any]) -> Dict[str, Tuple[str, str]]:
    out = {}
    for key, node in (table_node.get("Fields") or {}).items():
        label = (node.get("Properties") or {}).get("Label")
        if isinstance(label, str):
            out[label] = (key, str(node.get("Type", "")))
    return out


def _pipeline_step_meta(step_id: str, app_id: str, table_key: str,
                        field_sets: List[Tuple[str, List[str]]]) -> Dict[str, Any]:
    before = [entry for entry in field_sets if entry[0] == "export_fields"]
    after = [entry for entry in field_sets if entry[0] != "export_fields"]
    app_source = "$PipelineStep_DataSource_1"
    table_source = f"$PipelineStep_DataSource_{len(before) + 2}"

    def field_list(name: str, field_keys: List[str]) -> Dict[str, Any]:
        return {
            "Type": "QB::PipelineStep::DataSource::Fields",
            "Properties": {
                "Fields": [_ref(App=app_id, Table=table_key, Field=key)
                           for key in field_keys],
                "Name": name,
                "Source": _ref(PipelineStep_DataSource=table_source),
            },
        }

    ordered = [{
        "Type": "QB::PipelineStep::DataSource::App",
        "Properties": {"App": _ref(App=app_id), "Name": "app"},
    }]
    ordered += [field_list(name, keys) for name, keys in before]
    ordered.append({
        "Type": "QB::PipelineStep::DataSource::Table",
        "Properties": {
            "Table": _ref(App=app_id, Table=table_key),
            "Name": "table",
            "Source": _ref(PipelineStep_DataSource=app_source),
        },
    })
    ordered += [field_list(name, keys) for name, keys in after]
    sources = {f"$PipelineStep_DataSource_{index}": node
               for index, node in enumerate(ordered, start=1)}
    return {f"$PipelineStep_InputsMeta_{step_id}": {
        "Type": "QB::PipelineStep::InputsMeta",
        "PipelineStep_DataSources": sources,
    }}


def _pipeline(pipeline: PipelineSpec, table_names: Dict[str, str],
              app_id: str, tables: Mapping[str, Any]) -> Dict[str, Any]:
    if pipeline.steps or pipeline.schedule:
        return _pipeline_with_steps(pipeline, table_names, app_id, tables)
    where = f"pipeline '{pipeline.name}'"
    properties: Dict[str, Any] = {
        "Name": pipeline.name, "Owner": pipeline.owner, "Tags": []}
    if pipeline.description:
        properties["Description"] = pipeline.description
    node: Dict[str, Any] = {"Type": "QB::Pipeline", "Properties": properties}
    if not pipeline.trigger_table:
        if pipeline.actions or pipeline.trigger_fields:
            raise QBLCompileError(
                f"{where} has actions or trigger fields but no trigger_table")
        return node

    def table_of(name: str, role: str) -> Tuple[str, Dict[str, Tuple[str, str]]]:
        if name not in table_names:
            raise QBLCompileError(
                f"{where} {role} '{name}', which is not a table in this spec")
        key = table_names[name]
        return key, _pipeline_fields(tables[key])

    selector = PIPELINE_TRIGGER_SELECTORS.get(pipeline.trigger_event)
    if selector is None:
        raise QBLCompileError(
            f"{where} has trigger_event '{pipeline.trigger_event}'; expected one "
            f"of {', '.join(sorted(PIPELINE_TRIGGER_SELECTORS))}")
    trigger_key, trigger_fields = table_of(pipeline.trigger_table, "triggers on")
    by_jinja_key = {pipeline_field_key(label): label for label in trigger_fields}

    if pipeline.trigger_fields and pipeline.trigger_event != "update":
        raise QBLCompileError(
            f"{where}: trigger_fields only mean something on an update trigger")
    for label in pipeline.trigger_fields:
        if label not in trigger_fields:
            raise QBLCompileError(
                f"{where} fires on a change to '{label}', which is not a field "
                f"of '{pipeline.trigger_table}'")

    exported: List[str] = []
    trigger_filter = (_pipeline_filters(pipeline.trigger_filters, pipeline.trigger_table,
                                        trigger_fields, where, exported)
                      if pipeline.trigger_filters else None)
    action_steps = []
    for index, action in enumerate(pipeline.actions):
        step_id = chr(ord("b") + index)
        if action.kind not in ("create", "update"):
            raise QBLCompileError(
                f"{where} action {index + 1} has kind '{action.kind}'; expected "
                f"'create' or 'update'")
        if action.kind == "update":
            if pipeline.trigger_event == "delete":
                raise QBLCompileError(
                    f"{where} updates the record that fired a delete trigger; "
                    f"that record no longer exists")
            if action.table != pipeline.trigger_table:
                raise QBLCompileError(
                    f"{where} action {index + 1} updates the triggering record, "
                    f"so its table must be '{pipeline.trigger_table}', not "
                    f"'{action.table}'")
        if not action.values:
            raise QBLCompileError(
                f"{where} action {index + 1} writes no values")
        action_key, action_fields = table_of(action.table, "writes to")
        inputs: Dict[str, str] = {}
        written: List[str] = []
        for label, value in action.values.items():
            if label not in action_fields:
                raise QBLCompileError(
                    f"{where} writes '{label}', which is not a field of "
                    f"'{action.table}'")
            field_key, field_type = action_fields[label]
            if (field_type in _UNWRITABLE_FIELD_TYPES
                    or field_type.endswith("::Formula")):
                raise QBLCompileError(
                    f"{where} writes '{label}', a {field_type} the platform "
                    f"computes; a pipeline cannot set it")
            for reference in _JINJA_TRIGGER_REFERENCE.findall(str(value)):
                source = by_jinja_key.get(reference)
                if source is None:
                    close = difflib.get_close_matches(reference, by_jinja_key, n=1)
                    hint = f"; did you mean a.{close[0]}?" if close else ""
                    raise QBLCompileError(
                        f"{where} reads a.{reference}, which is no field of "
                        f"'{pipeline.trigger_table}'{hint}")
                if source not in exported:
                    exported.append(source)
            inputs[pipeline_input_key(label)] = str(value)
            written.append(field_key)
            if action.kind == "update" and label not in exported:
                exported.append(label)
        step_properties: Dict[str, Any] = {
            "Id": step_id,
            "Type": "pipe",
            "Name": action.name or (
                f"Create {action.table} record" if action.kind == "create"
                else f"Update {action.table} record"),
            "SubType": "action",
        }
        step: Dict[str, Any] = {"Type": "QB::PipelineStep::Quickbase",
                                "Properties": step_properties}
        if action.kind == "create":
            step_properties["PipelineChannelAccount"] = _ref(
                PipelineChannelAccount=QUICKBASE_CHANNEL_ACCOUNT)
        step_properties["Channel"] = {"Resource": "record", "Id": "quickbase",
                                      "Selector": action.kind}
        step_properties["Inputs"] = inputs
        if action.kind == "create":
            step["InputsMeta"] = _pipeline_step_meta(
                step_id, app_id, action_key, [("export_fields", written)])
        else:
            step_properties["Target"] = {"StepId": "a", "Type": "step-reference"}
        action_steps.append(step)

    field_sets: List[Tuple[str, List[str]]] = []
    if exported:
        field_sets.append(("export_fields",
                           [trigger_fields[label][0] for label in exported]))
    meta_properties: Dict[str, Any] = {}
    if pipeline.trigger_event == "update":
        if pipeline.trigger_fields:
            field_sets.append(("trigger_fields", [
                trigger_fields[label][0] for label in pipeline.trigger_fields]))
            meta_properties["Trigger_On_All_Fields"] = False
        else:
            meta_properties["Trigger_On_All_Fields"] = True
    trigger_meta = _pipeline_step_meta("a", app_id, trigger_key, field_sets)
    if meta_properties:
        trigger_meta["$PipelineStep_InputsMeta_a"]["Properties"] = meta_properties
    event_word = {"create": "created", "update": "updated", "delete": "deleted"}
    trigger = {
        "Type": "QB::PipelineStep::Quickbase",
        "Properties": {
            "Id": "a",
            "Type": "pipe",
            "Name": f"{pipeline.trigger_table} record "
                    f"{event_word[pipeline.trigger_event]}",
            "SubType": "trigger",
            "PipelineChannelAccount": _ref(
                PipelineChannelAccount=QUICKBASE_CHANNEL_ACCOUNT),
            "Channel": {"Resource": "record", "Id": "quickbase",
                        "Selector": selector},
        },
        "InputsMeta": trigger_meta,
    }
    if trigger_filter is not None:
        trigger["Properties"]["Filters"] = trigger_filter
    node["Steps"] = [trigger] + action_steps
    return node


PIPELINE_FILTER_OPERATORS = frozenset({
    "is", "!is", "equals", "!equals", "contains", "!contains", "starts",
    "set", "!set", "after", "on_date",
})

PIPELINE_STEP_NAME_LIMIT = 50

_JINJA_STEP_REFERENCE = re.compile(
    r"\{\{[^}]*?(?<![A-Za-z0-9_.])([a-z][a-z0-9_]*)\.(?:\$prev\.)?([A-Za-z0-9_]+)")


def _pipeline_filters(filters: List[PipelineFilterSpec], table: str,
                      fields: Dict[str, Tuple[str, str]], where: str,
                      exported: List[str]) -> Dict[str, Any]:
    expression: List[Dict[str, Any]] = []
    for index, condition in enumerate(filters):
        if condition.field not in fields and condition.field not in ("Record ID#", "Record ID"):
            close = difflib.get_close_matches(condition.field, fields, n=1)
            hint = f"; did you mean '{close[0]}'?" if close else ""
            raise QBLCompileError(
                f"{where} filters on '{condition.field}', which is not a field of "
                f"'{table}'{hint}")
        if condition.operator not in PIPELINE_FILTER_OPERATORS:
            raise QBLCompileError(
                f"{where} filters '{condition.field}' with operator "
                f"'{condition.operator}', which no real pipeline uses; expected one of "
                f"{', '.join(sorted(PIPELINE_FILTER_OPERATORS))}")
        term: Dict[str, Any] = {"Type": "relational-expression",
                                "Field": pipeline_field_key(condition.field),
                                "Operator": condition.operator}
        if condition.value is not None:
            term["Value"] = condition.value
        expression.append(term)
        if index:
            expression.append({"Type": "logical-operator", "Operator": "AND"})
        if condition.field in fields and condition.field not in exported:
            exported.append(condition.field)
    return {"Type": "composite-expression", "Notation": "postfix",
            "Expression": expression}


def _pipeline_with_steps(pipeline: PipelineSpec, table_names: Dict[str, str],
                         app_id: str, tables: Mapping[str, Any]) -> Dict[str, Any]:
    where = f"pipeline '{pipeline.name}'"
    if pipeline.actions:
        raise QBLCompileError(f"{where} sets both actions and steps; use steps")
    if not pipeline.steps:
        raise QBLCompileError(f"{where} has a schedule and no steps")
    if pipeline.schedule and pipeline.trigger_table:
        raise QBLCompileError(
            f"{where} has both a schedule and a trigger_table; a pipeline starts "
            f"from one or the other")
    if pipeline.schedule and not pipeline.timezone:
        raise QBLCompileError(
            f"{where} has a schedule and no timezone. Name the IANA zone the "
            f"schedule means - 'America/Chicago' - rather than letting a default "
            f"decide when it runs.")
    if pipeline.schedule and len(str(pipeline.schedule).split()) != 5:
        raise QBLCompileError(
            f"{where} schedule '{pipeline.schedule}' is not a five-field cron")
    if not pipeline.schedule and not pipeline.trigger_table:
        raise QBLCompileError(f"{where} has steps and neither a trigger_table nor a schedule")

    def table_of(name: Optional[str], role: str) -> Tuple[str, Dict[str, Tuple[str, str]]]:
        if not name or name not in table_names:
            raise QBLCompileError(
                f"{where} {role} '{name}', which is not a table in this spec")
        key = table_names[name]
        return key, _pipeline_fields(tables[key])

    info: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    used = set()

    if pipeline.trigger_table:
        selector = PIPELINE_TRIGGER_SELECTORS.get(pipeline.trigger_event)
        if selector is None:
            raise QBLCompileError(
                f"{where} has trigger_event '{pipeline.trigger_event}'; expected one "
                f"of {', '.join(sorted(PIPELINE_TRIGGER_SELECTORS))}")
        key, fields = table_of(pipeline.trigger_table, "triggers on")
        info["a"] = {"kind": "trigger", "table": pipeline.trigger_table, "key": key,
                     "fields": fields, "export": []}
        used.add("a")
        for label in pipeline.trigger_fields:
            if label not in fields:
                raise QBLCompileError(
                    f"{where} fires on a change to '{label}', which is not a field "
                    f"of '{pipeline.trigger_table}'")
        if pipeline.trigger_fields and pipeline.trigger_event != "update":
            raise QBLCompileError(
                f"{where}: trigger_fields only mean something on an update trigger")
    elif pipeline.trigger_filters or pipeline.trigger_fields:
        raise QBLCompileError(f"{where} filters a trigger it does not have")

    letters = iter("abcdefghijklmnopqrstuvwxyz")

    def next_id() -> str:
        for letter in letters:
            if letter not in used:
                used.add(letter)
                return letter
        raise QBLCompileError(f"{where} has more than 26 steps; give them ids")

    def assign(steps: List[PipelineStepSpec], loop_over: Tuple[str, ...]) -> None:
        for step in steps:
            if step.kind not in ("search", "create", "update", "loop"):
                raise QBLCompileError(
                    f"{where} has a step of kind '{step.kind}'; expected search, "
                    f"create, update or loop")
            if step.kind == "loop":
                if not step.steps:
                    raise QBLCompileError(f"{where} has a loop with no steps")
                if step.target not in info or info[step.target]["kind"] != "search":
                    raise QBLCompileError(
                        f"{where} loops over '{step.target}', which is not an earlier "
                        f"search step")
                step_id = f"loop:{len(order)}"
                info[step_id] = {"kind": "loop", "spec": step, "loop_over": loop_over}
                order.append(step_id)
                assign(step.steps, loop_over + (step.target,))
                continue
            if step.id is not None:
                if not re.fullmatch(r"[a-z][a-z0-9_]*", step.id) or step.id in used:
                    raise QBLCompileError(
                        f"{where} step id '{step.id}' is taken or is not a lower-case "
                        f"identifier")
                used.add(step.id)
                step_id = step.id
            else:
                step_id = next_id()
            if step.kind == "update":
                target = step.target or ("a" if "a" in info and info["a"]["kind"] == "trigger"
                                         else None)
                if target not in info or info[target]["kind"] not in ("trigger", "search", "create"):
                    raise QBLCompileError(
                        f"{where} step {step_id} updates '{target}', which is not the "
                        f"trigger or an earlier search or create")
                if info[target]["kind"] == "search" and target not in loop_over:
                    raise QBLCompileError(
                        f"{where} step {step_id} updates search '{target}' outside a "
                        f"loop over it; put the update inside the loop")
                if target == "a" and pipeline.trigger_event == "delete":
                    raise QBLCompileError(
                        f"{where} updates the record that fired a delete trigger; "
                        f"that record no longer exists")
                if step.table and step.table != info[target]["table"]:
                    raise QBLCompileError(
                        f"{where} step {step_id} updates step {target}'s record, which "
                        f"is a '{info[target]['table']}', not a '{step.table}'")
                info[step_id] = {"kind": "update", "spec": step, "target": target,
                                 "table": info[target]["table"], "key": info[target]["key"],
                                 "fields": info[target]["fields"], "loop_over": loop_over}
            else:
                key, fields = table_of(step.table, "searches" if step.kind == "search"
                                       else "writes to")
                info[step_id] = {"kind": step.kind, "spec": step, "table": step.table,
                                 "key": key, "fields": fields, "export": [],
                                 "loop_over": loop_over}
            order.append(step_id)

    assign(pipeline.steps, ())

    def readable(step_id: str, value: Any, visible: List[str]) -> None:
        for head, name in _JINJA_STEP_REFERENCE.findall(str(value)):
            if head not in info or info[head]["kind"] == "loop":
                continue
            if head not in visible:
                raise QBLCompileError(
                    f"{where} step {step_id} reads {head}.{name} before step {head} has run")
            source = info[head] if info[head]["kind"] != "update" else info[info[head]["target"]]
            by_key = {pipeline_field_key(label): label for label in source["fields"]}
            if name == "id":
                continue
            label = by_key.get(name)
            if label is None:
                close = difflib.get_close_matches(name, by_key, n=1)
                hint = f"; did you mean {head}.{close[0]}?" if close else ""
                raise QBLCompileError(
                    f"{where} step {step_id} reads {head}.{name}, which is no field of "
                    f"'{source['table']}'{hint}")
            if label not in source["export"]:
                source["export"].append(label)

    def name_of(step_id: str, default: str) -> str:
        spec = info[step_id].get("spec")
        name = (spec.name if spec is not None and spec.name else default)
        if len(name) > PIPELINE_STEP_NAME_LIMIT:
            raise QBLCompileError(
                f"{where} step name '{name}' is {len(name)} characters; a PUT refuses "
                f"pipeline step names over {PIPELINE_STEP_NAME_LIMIT}")
        return name

    has_trigger = bool(pipeline.trigger_table)
    visible = ["a"] if has_trigger else []
    built: Dict[str, Dict[str, Any]] = {}
    trigger_filter = None
    if has_trigger:
        trigger_filter = (_pipeline_filters(pipeline.trigger_filters, pipeline.trigger_table,
                                            info["a"]["fields"], where, info["a"]["export"])
                          if pipeline.trigger_filters else None)
    for step_id in order:
        entry = info[step_id]
        spec = entry["spec"]
        if entry["kind"] == "loop":
            continue
        if entry["kind"] == "search":
            if not spec.filters:
                raise QBLCompileError(
                    f"{where} step {step_id} searches '{spec.table}' with no filter; "
                    f"filter on what it needs - `Record ID#` `set` for every record")
            for condition in spec.filters:
                readable(step_id, condition.value, visible)
            filters = _pipeline_filters(spec.filters, spec.table, entry["fields"], where,
                                        entry["export"])
            for label in spec.export:
                if label not in entry["fields"]:
                    raise QBLCompileError(
                        f"{where} step {step_id} exports '{label}', which is not a field "
                        f"of '{spec.table}'")
                if label not in entry["export"]:
                    entry["export"].append(label)
            built[step_id] = {"Type": "QB::PipelineStep::Quickbase", "Properties": {
                "Id": step_id, "Type": "pipe",
                "Name": name_of(step_id, f"Search {spec.table} records"),
                "SubType": "query",
                "PipelineChannelAccount": _ref(PipelineChannelAccount=QUICKBASE_CHANNEL_ACCOUNT),
                "Channel": {"Resource": "record", "Id": "quickbase", "Selector": "search"},
                "Filters": filters}}
        else:
            if not spec.values:
                raise QBLCompileError(f"{where} step {step_id} writes no values")
            inputs: Dict[str, str] = {}
            written: List[str] = []
            for label, value in spec.values.items():
                if label not in entry["fields"]:
                    close = difflib.get_close_matches(label, entry["fields"], n=1)
                    hint = f"; did you mean '{close[0]}'?" if close else ""
                    raise QBLCompileError(
                        f"{where} step {step_id} writes '{label}', which is not a field "
                        f"of '{entry['table']}'{hint}")
                field_key, field_type = entry["fields"][label]
                if field_type in _UNWRITABLE_FIELD_TYPES or field_type.endswith("::Formula"):
                    raise QBLCompileError(
                        f"{where} step {step_id} writes '{label}', a {field_type} the "
                        f"platform computes; a pipeline cannot set it")
                if str(value) == "":
                    raise QBLCompileError(
                        f"{where} step {step_id} writes '' to '{label}'. The platform "
                        f"skips a blank value rather than clearing the field; write "
                        f"'{{{{CLEAR}}}}' to clear it.")
                readable(step_id, value, visible)
                inputs[pipeline_input_key(label)] = value if isinstance(value, bool) else str(value)
                written.append(field_key)
                if entry["kind"] == "update":
                    target = info[entry["target"]]
                    if label not in target["export"]:
                        target["export"].append(label)
            properties: Dict[str, Any] = {
                "Id": step_id, "Type": "pipe",
                "Name": name_of(step_id, f"{entry['kind'].capitalize()} {entry['table']} record"),
                "SubType": "action"}
            if entry["kind"] == "create":
                properties["PipelineChannelAccount"] = _ref(
                    PipelineChannelAccount=QUICKBASE_CHANNEL_ACCOUNT)
            properties["Channel"] = {"Resource": "record", "Id": "quickbase",
                                     "Selector": entry["kind"]}
            properties["Inputs"] = inputs
            node_step: Dict[str, Any] = {"Type": "QB::PipelineStep::Quickbase",
                                         "Properties": properties}
            if entry["kind"] == "update":
                properties["Target"] = {"StepId": entry["target"], "Type": "step-reference"}
            else:
                entry["written"] = written
            built[step_id] = node_step
        visible.append(step_id)

    for step_id, entry in info.items():
        if entry["kind"] == "search":
            built[step_id]["InputsMeta"] = _pipeline_step_meta(
                step_id, app_id, entry["key"],
                [("export_fields", [entry["fields"][label][0] for label in entry["export"]])]
                if entry["export"] else [])
        elif entry["kind"] == "create":
            keys = list(entry["written"]) + [entry["fields"][label][0] for label in entry["export"]
                                             if entry["fields"][label][0] not in entry["written"]]
            built[step_id]["InputsMeta"] = _pipeline_step_meta(
                step_id, app_id, entry["key"], [("export_fields", keys)])

    def emit(steps: List[PipelineStepSpec]) -> List[Dict[str, Any]]:
        out = []
        for step in steps:
            if step.kind == "loop":
                loop_name = step.name or "Loop"
                if len(loop_name) > PIPELINE_STEP_NAME_LIMIT:
                    raise QBLCompileError(
                        f"{where} step name '{loop_name}' is over {PIPELINE_STEP_NAME_LIMIT} characters")
                out.append({"Type": "QB::PipelineStep::Loop", "Properties": {
                    "Type": "loop", "Name": loop_name,
                    "Target": {"StepId": step.target, "Type": "step-reference"}},
                    "Steps": emit(step.steps)})
            else:
                step_id = next(sid for sid in order
                               if info[sid].get("spec") is step and info[sid]["kind"] != "loop")
                out.append(built[step_id])
        return out

    properties: Dict[str, Any] = {"Name": pipeline.name}
    if pipeline.description:
        properties["Description"] = pipeline.description
    if pipeline.schedule:
        properties["Crontab"] = pipeline.schedule
        properties["CrontabTimezone"] = pipeline.timezone
    properties.update(Tags=[], Owner=pipeline.owner)
    steps_out = emit(pipeline.steps)

    if has_trigger:
        trigger = info["a"]
        field_sets: List[Tuple[str, List[str]]] = []
        if trigger["export"]:
            field_sets.append(("export_fields",
                               [trigger["fields"][label][0] for label in trigger["export"]]))
        meta_properties: Dict[str, Any] = {}
        if pipeline.trigger_event == "update":
            if pipeline.trigger_fields:
                field_sets.append(("trigger_fields", [
                    trigger["fields"][label][0] for label in pipeline.trigger_fields]))
                meta_properties["Trigger_On_All_Fields"] = False
            else:
                meta_properties["Trigger_On_All_Fields"] = True
        meta = _pipeline_step_meta("a", app_id, trigger["key"], field_sets)
        if meta_properties:
            meta["$PipelineStep_InputsMeta_a"]["Properties"] = meta_properties
        event_word = {"create": "created", "update": "updated", "delete": "deleted"}
        trigger_node: Dict[str, Any] = {
            "Type": "QB::PipelineStep::Quickbase",
            "Properties": {
                "Id": "a", "Type": "pipe",
                "Name": (pipeline.trigger_name
                         or f"{pipeline.trigger_table} record "
                            f"{event_word[pipeline.trigger_event]}")[:PIPELINE_STEP_NAME_LIMIT],
                "SubType": "trigger",
                "PipelineChannelAccount": _ref(PipelineChannelAccount=QUICKBASE_CHANNEL_ACCOUNT),
                "Channel": {"Resource": "record", "Id": "quickbase",
                            "Selector": PIPELINE_TRIGGER_SELECTORS[pipeline.trigger_event]},
            },
            "InputsMeta": meta,
        }
        if trigger_filter is not None:
            trigger_node["Properties"]["Filters"] = trigger_filter
        steps_out = [trigger_node] + steps_out
    return {"Type": "QB::Pipeline", "Properties": properties, "Steps": steps_out}


EMAIL_RECIPIENT_FIELD_TYPES = frozenset({
    "QB::Field::User", "QB::Field::User::Formula", "QB::Field::ListUser",
})


EMAIL_RECORD_EVENTS = ("Add", "Modify", "Delete")


def _email_send_options(email: Any, where: str,
                        by_label: Mapping[Any, Tuple[str, Any]]) -> Dict[str, Any]:
    record_events = list(getattr(email, "record_events", None) or [])
    trigger_fields = list(getattr(email, "trigger_fields", None) or [])
    if email.trigger == "Scheduled":
        if record_events or trigger_fields:
            raise QBLCompileError(
                f"{where} is scheduled; record_events and trigger_fields belong to a "
                f"RecordChange email")
        return {"TriggerType": "Scheduled", "Schedule": email.schedule}
    options: Dict[str, Any] = {"TriggerType": email.trigger}
    if email.trigger != "RecordChange":
        return options
    if not record_events:
        raise QBLCompileError(
            f"{where} is a RecordChange email with no record_events. Say which of "
            f"{', '.join(EMAIL_RECORD_EVENTS)} send it: without them the platform "
            f"stores an email that never sends, and its export cannot be re-imported")
    unknown = [event for event in record_events if event not in EMAIL_RECORD_EVENTS]
    if unknown:
        raise QBLCompileError(
            f"{where} record_events {unknown} - each must be one of "
            f"{', '.join(EMAIL_RECORD_EVENTS)}")
    if len(set(record_events)) != len(record_events):
        raise QBLCompileError(f"{where} names a record event twice")
    options["RecordEventTrigger"] = record_events
    if trigger_fields:
        refs = []
        for label in trigger_fields:
            if label not in by_label:
                close = difflib.get_close_matches(label, [l for l in by_label if l], n=1)
                hint = f"; did you mean '{close[0]}'?" if close else ""
                raise QBLCompileError(f"{where} triggers on '{label}', which is not a "
                                      f"field of the table{hint}")
            refs.append(_ref(Field=by_label[label][0]))
        options["Fields"] = refs
    return options


def _custom_email(email: Any, table: str, fields: Mapping[str, Any]) -> Dict[str, Any]:
    where = f"email '{email.name}' on '{table}'"
    by_label = {(node.get("Properties") or {}).get("Label"): (key, node.get("Type"))
                for key, node in fields.items()}
    properties: Dict[str, Any] = {
        "Name": email.name,
        "SendOptions": _email_send_options(email, where, by_label),
    }
    if email.description:
        properties["Description"] = email.description
    settings: Dict[str, Any] = {}
    if email.to_fields:
        refs = []
        for label in email.to_fields:
            if label not in by_label:
                close = difflib.get_close_matches(label, [l for l in by_label if l], n=1)
                hint = f"; did you mean '{close[0]}'?" if close else ""
                raise QBLCompileError(f"{where} sends to '{label}', which is not a field "
                                      f"of the table{hint}")
            key, kind = by_label[label]
            if kind not in EMAIL_RECIPIENT_FIELD_TYPES:
                raise QBLCompileError(
                    f"{where} sends to '{label}', a {kind}; an email can send to a "
                    f"User, User::Formula or ListUser field - make a User::Formula of "
                    f"it if it is a lookup")
            refs.append(_ref(Field=key))
        settings.update(BulkChange="SendSeparate", From="Default", To={"Fields": refs},
                        CheckRecipientPermissions=email.check_recipient_permissions)
    if email.trigger == "Scheduled" and email.send_when_empty:
        settings["SendScheduledEmailEvenWhenEmpty"] = True
    settings.update(Subject=email.subject, Content=email.content)
    properties["EmailSettings"] = settings
    node: Dict[str, Any] = {"Type": "QB::CustomEmail", "Properties": properties}
    if email.conditions:
        if email.trigger == "Scheduled":
            raise QBLCompileError(
                f"{where} is scheduled and has conditions. The platform accepts a "
                f"scheduled email's conditions and drops them - they are absent from "
                f"the export, and every record sends. Gate it through a recipient "
                f"field instead: a User::Formula that is blank unless the record "
                f"needs the email.")
        if email.true_when not in ("All", "Any"):
            raise QBLCompileError(f"{where} true_when must be All or Any")
        when = []
        for condition in email.conditions:
            if condition.field not in by_label:
                raise QBLCompileError(f"{where} has a condition on '{condition.field}', "
                                      f"which is not a field of the table")
            props: Dict[str, Any] = {"Field": _ref(Field=by_label[condition.field][0]),
                                     "Comparison": condition.comparison}
            if condition.value is not None:
                props["Value"] = condition.value
            when.append({"Type": "QB::CustomEmail::Condition::Field", "Properties": props})
        node["Conditions"] = [{"Type": "QB::CustomEmail::Condition::Group",
                               "Properties": {"TrueWhen": email.true_when}, "When": when}]
    return node


CONNECTED_COLUMN_FIELD_KINDS = {
    "BigInt": "Number", "Decimal": "Number", "Double": "Number",
    "Float": "Number", "Integer": "Number", "Serial": "Number",
    "SmallInt": "Number", "TinyInt": "Number",
    "Boolean": "Checkbox",
    "Date": "Date",
    "Time": "TimeOfDay", "TimeWithTimeZone": "TimeOfDay",
    "Timestamp": "DateTime", "TimestampWithTimeZone": "DateTime",
    "Interval": "Duration",
}


def _connected_key_column(table: ConnectedTableSpec) -> Optional[ConnectedColumnSpec]:
    mapped = [c for c in table.columns if c.kind != "Placeholder"]
    if table.key_column is None:
        return mapped[0] if mapped else None
    for column in mapped:
        if column.name == table.key_column:
            return column
    raise QBLCompileError(
        f"connected table '{table.name}' keys on '{table.key_column}', which is "
        f"not one of its named columns")


def _connected_schedule(table: ConnectedTableSpec) -> Any:
    if table.schedule == "Manual":
        return "Manual"
    parts = table.schedule.split()
    if len(parts) != 5:
        raise QBLCompileError(
            f"connected table '{table.name}' has schedule '{table.schedule}'; "
            f"expected 'Manual' or a five-part cron string")
    if parts[0].strip("0") == "" :
        raise QBLCompileError(
            f"connected table '{table.name}' refreshes at minute 0 "
            f"('{table.schedule}'), which the platform silently replaces with "
            f"Manual; pick another minute")
    return {"CronTab": table.schedule, "NotifyOnFailure": table.notify_on_failure}


def _connected_table_binding(table: ConnectedTableSpec) -> Dict[str, Any]:
    mapped = [c for c in table.columns if c.kind != "Placeholder"]
    field_map = {
        logical_id("Field", f"{table.name} {column.name}"): _ref(
            ConnectedColumn=logical_id("ConnectedColumn", f"{table.name}_{column.name}"))
        for column in mapped
    }

    binding: Dict[str, Any] = {
        "DataSource": _ref(
            DataSource=logical_id("DataSource", table.name),
            RecordSet=logical_id("RecordSet", table.name),
        ),
        "Connected": True,
        "UpdateMode": "Additive",
        "Schedule": _connected_schedule(table),
        "DataFilter": "None",
        "FieldMap": field_map,
    }
    key = _connected_key_column(table)
    if key is not None:
        binding["KeyFields"] = [
            _ref(Field=logical_id("Field", f"{table.name} {key.name}"))
        ]
    return binding


def _connected_table_spec(table: ConnectedTableSpec) -> TableSpec:
    mapped = [c for c in table.columns if c.kind != "Placeholder"]
    key = _connected_key_column(table)
    return TableSpec(
        name=table.name,
        fields=[
            FieldSpec(
                label=f"{table.name} {column.name}",
                kind=CONNECTED_COLUMN_FIELD_KINDS.get(column.kind, "Text"),
                unique=(column is key),
            )
            for column in mapped
        ],
    )


def _connected_table(table: ConnectedTableSpec, minter: "_IdMinter") -> Dict[str, Any]:
    minter.enter_table()
    columns: Dict[str, Any] = {}
    for column in table.columns:
        qbl_type = f"QB::ConnectedColumn::{column.kind}"
        from qblparser.qbl_schema import QBL_SCHEMA

        if qbl_type not in QBL_SCHEMA:
            raise QBLCompileError(
                f"connected column '{column.name}' has kind '{column.kind}', which is "
                f"not a QBL connected-column type"
            )
        minted = minter.take("field")
        columns[logical_id("ConnectedColumn", f"{table.name}_{column.name}")] = {
            "Type": qbl_type,
            "Id": (column.source_field_id if column.source_field_id is not None
                   else minted),
            "Properties": {} if column.kind == "Placeholder" else {"Name": column.name},
        }

    key = _connected_key_column(table)
    first = (logical_id("ConnectedColumn", f"{table.name}_{key.name}")
             if key is not None else next(iter(columns), None))
    record_set: Dict[str, Any] = {
        "Type": "QB::ConnectedRecordSet",
        "Properties": {
            "Name": table.name,
            "SetType": "Table",
            "ExternalSetId": table.external_set_id,
            "ExternalSetIsInSolution": False,
        },
        "Columns": columns,
    }
    if first:
        record_set["Properties"]["PrimaryKey"] = [_ref(ConnectedColumn=first)]

    return {
        "Type": "QB::ConnectedDataSource::Quickbase",
        "Properties": {
            "ConnectionId": _numeric_id(
                table.connection_id, "connection_id", f"connected table '{table.name}'"),
            "IsPlaceholder": False,
            **({"Owner": table.owner} if table.owner else {}),
        },
        "RecordSets": {
            logical_id("RecordSet", table.name): record_set,
        },
    }


LEGACY_ELEMENT_OVERRIDES = {
    "DateCreated": "DateTimeField",
    "DateModified": "DateTimeField",
    "RecordID": "NumberField",
    "RecordOwner": "UserField",
    "LastModifiedBy": "UserField",
    "TextMultiLine": "TextMultilineField",
    "TextMultiline": "TextMultilineField",
    "MultiSelectText": "MultiselectTextField",
}

def _legacy_element_type(kind: str) -> str:
    if kind.endswith("::Formula"):
        return "QB::Form::Element::FormulaField"
    return f"QB::Form::Element::{LEGACY_ELEMENT_OVERRIDES.get(kind, kind + 'Field')}"


def _report_link_relationship(field_spec: FieldSpec, table: TableSpec,
                              table_names: Dict[str, str]) -> Dict[str, Any]:
    target_table = field_spec.link_table or table.name
    if target_table not in table_names:
        raise QBLCompileError(
            f"field '{field_spec.label}' links to table '{target_table}', which is "
            f"not a table in this spec"
        )
    if not field_spec.link_field:
        raise QBLCompileError(
            f"field '{field_spec.label}' names a link source but no link_field to "
            f"match it against"
        )
    return {
        "Source": _ref(Field=logical_id("Field", field_spec.link_source)),
        "Target": _ref(
            Table=table_names[target_table],
            Field=logical_id("Field", field_spec.link_field),
        ),
    }


def _embedded_target(member: FormElementSpec, table: TableSpec,
                     spec: AppSpec) -> Tuple[str, str]:
    table_name = member.embedded_table or table.name
    owner = next((t for t in spec.tables if t.name == table_name), None)
    if owner is None:
        raise QBLCompileError(
            f"element embeds '{member.embedded_report}' from table '{table_name}', "
            f"which is not a table in this spec"
        )

    if any(r.name == member.embedded_report for r in owner.reports):
        return table_name, logical_id("Report", f"{table_name}_{member.embedded_report}")
    if any(c.name == member.embedded_report for c in owner.charts):
        return table_name, logical_id("Chart", f"{table_name}_{member.embedded_report}")
    raise QBLCompileError(
        f"element embeds '{member.embedded_report}', which table "
        f"'{table_name}' does not declare as a report or a chart"
    )


def _embedded_view(member: FormElementSpec, table: TableSpec,
                   spec: AppSpec) -> Dict[str, Any]:
    table_name, target = _embedded_target(member, table, spec)

    return {
        "TargetReport": _ref(Table=logical_id("Table", table_name), Report=target),
        "RowsToDisplay": member.embedded_rows,
        "Editable": False,
        "MaxHeightInPixels": 0,
    }


def _legacy_element(label: Optional[str], kind: Optional[str], key: str,
                    member: Optional[FormElementSpec] = None,
                    table: Optional[TableSpec] = None,
                    spec: Optional[AppSpec] = None) -> Tuple[str, Dict[str, Any]]:
    from qblparser.qbl_schema import QBL_SCHEMA

    if member is not None and member.kind:
        qbl_type = f"QB::Form::Element::{member.kind}"
    else:
        qbl_type = _legacy_element_type(kind or "")
    entry = QBL_SCHEMA.get(qbl_type)
    if entry is None:
        subject = f"'{kind}' field ('{label}')" if label else f"element type '{qbl_type}'"
        raise QBLCompileError(f"no legacy form element exists for a {subject}")
    allowed = set(entry.get("optional", ())) | set(entry.get("required", ()))

    properties: Dict[str, Any] = {}
    if label is not None:
        properties["Field"] = _ref(Field=logical_id("Field", label))
    if "DisplayOn" in allowed:
        properties["DisplayOn"] = {"Add": True, "Edit": True, "View": True}
    for prop, value in (("Required", False), ("ReadOnly", False)):
        if prop in allowed:
            properties[prop] = value

    if member is not None:
        if member.label is not None:
            if "Label" not in allowed:
                raise QBLCompileError(
                    f"element '{qbl_type}' takes no Label"
                )
            properties["Label"] = member.label
        if member.embedded_report is not None:
            if "EmbeddedView" not in allowed:
                raise QBLCompileError(
                    f"element '{qbl_type}' takes no EmbeddedView, so it cannot "
                    f"embed '{member.embedded_report}'"
                )
            properties["EmbeddedView"] = _embedded_view(member, table, spec)
        if member.properties:
            _require_known_properties(
                qbl_type, member.properties,
                f"form element {label or qbl_type}",
            )
            _merge_properties(properties, member.properties)

    return key, {"Type": qbl_type, "Properties": properties}


def _legacy_form(form: LegacyFormSpec, table: TableSpec, minter: "_IdMinter",
                 field_kinds: Dict[str, str], spec: AppSpec) -> Dict[str, Any]:
    counter = [0]

    def next_key() -> str:
        counter[0] += 1
        return logical_id("FormElement", f"{table.name}_{counter[0]}")

    placed: set = set()

    def element_for(member) -> Tuple[str, Dict[str, Any]]:
        spec_member = member if isinstance(member, FormElementSpec) else None
        label = spec_member.field if spec_member is not None else member

        if label is None:
            if spec_member is None or not spec_member.kind:
                raise QBLCompileError(
                    f"legacy form '{form.name}' has an element naming neither a "
                    f"field nor a kind"
                )
            return _legacy_element(None, None, next_key(), spec_member, table, spec)

        kind = field_kinds.get(label)
        if kind is None:
            raise QBLCompileError(
                f"legacy form '{form.name}' places '{label}', which table "
                f"'{table.name}' does not declare"
            )
        if label in placed:
            raise QBLCompileError(
                f"legacy form '{form.name}' places '{label}' more than once; a "
                f"field may appear on a form only once"
            )
        placed.add(label)
        return _legacy_element(label, kind, next_key(), spec_member, table, spec)

    elements: Dict[str, Any] = {}
    for member in form.fields:
        key, node = element_for(member)
        elements[key] = node

    row_counter = [0]

    def add_row(into: Dict[str, Any], members) -> None:
        row_elements: Dict[str, Any] = {}
        for member in members:
            key, node = element_for(member)
            row_elements[key] = node
        if not row_elements:
            return
        row_counter[0] += 1
        into[logical_id("Row", f"{table.name}_{row_counter[0]}")] = {
            "Type": "QB::Form::Element::Row",
            "Elements": row_elements,
        }

    for section in form.sections:
        section_elements: Dict[str, Any] = {}
        for member in section.fields:
            key, node = element_for(member)
            section_elements[key] = node
        for members in section.rows:
            add_row(section_elements, members)
        for tab in section.tabs:
            tab_properties: Dict[str, Any] = {"Label": tab.label}
            if tab.color is not None:
                tab_properties["Color"] = tab.color
            section_elements[next_key()] = {
                "Type": "QB::Form::Element::Tab",
                "Properties": tab_properties,
            }
            for members in tab.rows:
                add_row(section_elements, members)
        elements[next_key()] = {
            "Type": "QB::Form::Element::Section",
            "Properties": {
                "Heading": section.heading or "",
                "Collapse": False,
                "LabelPosition": "AboveField",
                "DisplayOn": {"Add": True, "Edit": True, "View": True},
            },
            "Elements": section_elements,
        }

    node: Dict[str, Any] = {
        "Type": "QB::Form",
        "Id": minter.take("legacy_form"),
        "Properties": {"Name": form.name},
        "Elements": elements,
    }
    if form.properties:
        _require_known_properties(
            "QB::Form", form.properties, f"legacy form '{form.name}'"
        )
        _merge_properties(node["Properties"], form.properties)

    if form.rules:
        node["Rules"] = [_legacy_rule(rule) for rule in form.rules]

    return node


def _legacy_rule(rule: FormRuleSpec) -> Dict[str, Any]:
    def condition_node(field_label, value, comparison):
        return {
            "Type": "QB::FormRule::Condition::Field",
            "Properties": {
                "Comparison": comparison,
                "Field": _ref(Field=logical_id("Field", field_label)),
                "Value": value,
            },
        }

    def spec_condition(condition: FormRuleConditionSpec) -> Dict[str, Any]:
        return _legacy_rule_condition(condition, rule.name)

    properties: Dict[str, Any] = {
        "TrueWhen": rule.true_when,
        "Disable": rule.disabled,
    }
    if rule.fire_only_on_change:
        properties["FireOnlyOnChange"] = True
    if rule.properties:
        _require_known_properties(
            "QB::FormRule", rule.properties, f"form rule '{rule.name}'"
        )
        _merge_properties(properties, rule.properties)

    primary = ([] if rule.target_field is None and rule.actions
               else [_legacy_rule_action(FormRuleActionSpec(
                   action=rule.action, target_field=rule.target_field))])
    node: Dict[str, Any] = {
        "Type": "QB::FormRule",
        "Properties": properties,
        "Actions": primary,
    }

    if rule.trigger is not None:
        node["When"] = [_legacy_rule_trigger(rule.trigger, rule.name)]
        if rule.conditions:
            node["If"] = [spec_condition(condition) for condition in rule.conditions]
    elif rule.conditions:
        if not rule.when_field:
            raise QBLCompileError(
                f"form rule '{rule.name}' names no when_field and no trigger, so "
                f"nothing makes it fire"
            )
        node["When"] = [{
            "Type": "QB::FormRule::Trigger::MultipleConditions",
            "Properties": {"IfConditionsAre": True},
        }]
        node["If"] = [condition_node(rule.when_field, rule.equals, rule.comparison)] + [
            spec_condition(condition) for condition in rule.conditions
        ]
    else:
        if not rule.when_field:
            raise QBLCompileError(
                f"form rule '{rule.name}' names no when_field and no trigger, so "
                f"nothing makes it fire"
            )
        node["When"] = [{
            "Type": "QB::FormRule::Trigger::Field",
            "Properties": {
                "Comparison": rule.comparison,
                "Field": _ref(Field=logical_id("Field", rule.when_field)),
                "Value": rule.equals,
            },
        }]

    node["Actions"].extend(_legacy_rule_action(action) for action in rule.actions)
    return node


RECORD_STATES = ("IsOpened", "IsSaving", "IsSavingAfterChecking")


LEGACY_CONDITION_COMPARISONS = {
    "FieldChange": ("Changed", "ChangedTo", "ChangedFrom"),
    "FieldIncludes": ("Includes", "DoesNotInclude"),
}


def _legacy_rule_condition(condition: FormRuleConditionSpec,
                           rule_name: str) -> Dict[str, Any]:
    if condition.kind == "User":
        if not condition.role:
            raise QBLCompileError(
                f"form rule '{rule_name}' has a user condition naming no role")
        return {
            "Type": "QB::FormRule::Condition::User",
            "Properties": {
                "Comparison": (condition.comparison
                               if condition.comparison != "IsEqualTo" else "IsInRole"),
                "Value": _ref(Role=logical_id("Role", condition.role)),
            },
        }
    if condition.kind not in ("Field",) + tuple(LEGACY_CONDITION_COMPARISONS):
        raise QBLCompileError(
            f"form rule '{rule_name}' has condition kind '{condition.kind}'; the "
            f"kinds are Field, FieldChange, FieldIncludes and User")
    if not condition.field:
        raise QBLCompileError(
            f"form rule '{rule_name}' has a {condition.kind} condition naming no "
            f"field")
    comparison = condition.comparison
    allowed = LEGACY_CONDITION_COMPARISONS.get(condition.kind)
    if allowed is not None:
        if comparison == "IsEqualTo":
            comparison = allowed[0]
        if comparison not in allowed:
            raise QBLCompileError(
                f"form rule '{rule_name}' compares a {condition.kind} condition "
                f"with '{comparison}'; it takes {', '.join(allowed)}")
    properties: Dict[str, Any] = {
        "Comparison": comparison,
        "Field": _ref(Field=logical_id("Field", condition.field)),
    }
    if not (condition.kind == "FieldChange" and comparison == "Changed"):
        properties["Value"] = condition.value
    return {"Type": f"QB::FormRule::Condition::{condition.kind}",
            "Properties": properties}


def _legacy_rule_trigger(trigger: FormRuleTriggerSpec, rule_name: str) -> Dict[str, Any]:
    if trigger.kind == "RecordState":
        if trigger.record_state not in RECORD_STATES:
            raise QBLCompileError(
                f"form rule '{rule_name}' triggers on record state "
                f"'{trigger.record_state}'; known states are {', '.join(RECORD_STATES)}"
            )
        return {
            "Type": "QB::FormRule::Trigger::RecordState",
            "Properties": {"RecordState": trigger.record_state},
        }

    if trigger.kind == "User":
        if not trigger.role:
            raise QBLCompileError(
                f"form rule '{rule_name}' triggers on a user but names no role"
            )
        return {
            "Type": "QB::FormRule::Trigger::User",
            "Properties": {
                "Comparison": trigger.comparison if trigger.comparison != "IsEqualTo"
                              else "IsInRole",
                "Value": _ref(Role=logical_id("Role", trigger.role)),
            },
        }

    if trigger.kind in ("Field", "FieldIncludes"):
        if not trigger.field:
            raise QBLCompileError(
                f"form rule '{rule_name}' triggers on a field but names none"
            )
        comparison = trigger.comparison
        if trigger.kind == "FieldIncludes":
            allowed = LEGACY_CONDITION_COMPARISONS["FieldIncludes"]
            if comparison == "IsEqualTo":
                comparison = allowed[0]
            if comparison not in allowed:
                raise QBLCompileError(
                    f"form rule '{rule_name}' compares a FieldIncludes trigger "
                    f"with '{comparison}'; it takes {', '.join(allowed)}")
        return {
            "Type": f"QB::FormRule::Trigger::{trigger.kind}",
            "Properties": {
                "Comparison": comparison,
                "Field": _ref(Field=logical_id("Field", trigger.field)),
                "Value": trigger.value,
            },
        }

    raise QBLCompileError(
        f"form rule '{rule_name}' has trigger kind '{trigger.kind}'; known kinds "
        f"are Field, FieldIncludes, RecordState and User"
    )


def _legacy_rule_action(action: FormRuleActionSpec) -> Dict[str, Any]:
    from qblparser.qbl_schema import QBL_SCHEMA

    qbl_type = f"QB::FormRule::Action::{_action_kind(action.action, legacy=True)}"
    entry = QBL_SCHEMA.get(qbl_type)
    if entry is None:
        raise QBLCompileError(
            f"no form rule action exists for '{action.action}'"
        )
    allowed = set(entry.get("optional", ())) | set(entry.get("required", ()))

    properties: Dict[str, Any] = {}
    if action.target_field is not None:
        if "Target" not in allowed:
            raise QBLCompileError(
                f"action '{action.action}' acts on the record rather than on a "
                f"field, so it takes no target ('{action.target_field}' given)"
            )
        properties["Target"] = _ref(Field=logical_id("Field", action.target_field))
    if action.value is not None:
        properties["Value"] = action.value
    if action.value_field is not None:
        properties["Value"] = _ref(Field=logical_id("Field", action.value_field))
    if action.message is not None:
        if "Message" not in allowed:
            raise QBLCompileError(
                f"action '{action.action}' takes no message"
            )
        properties["Message"] = action.message
    return {"Type": qbl_type, "Properties": properties}


def compile_app(spec: AppSpec, *, resolve_tokens: bool = True) -> Dict[str, Any]:
    if not spec.tables:
        raise QBLCompileError("an application needs at least one table")

    for page in spec.pages:
        _check_code_page(page)

    spec = _with_default_roles(spec)
    spec = _with_reference_labels(spec)
    spec = _with_relationship_keys(spec)
    spec = _with_reference_proxies(spec)
    spec = _with_relationship_views(spec)
    minter = _IdMinter()
    app_id = logical_id("App", spec.name)
    table_names = {t.name: logical_id("Table", t.name) for t in spec.tables}

    seen: Dict[str, int] = {}
    for table in spec.tables:
        seen[table.name] = seen.get(table.name, 0) + 1
    duplicates = [name for name, count in seen.items() if count > 1]
    if duplicates:
        raise QBLCompileError(f"duplicate table names: {sorted(duplicates)}")

    reference_fields: Dict[Tuple[str, str], str] = {}
    parents_of: Dict[str, List[RelationshipSpec]] = {}
    for rel in spec.relationships:
        for side in (rel.parent, rel.child):
            if side not in table_names:
                raise QBLCompileError(
                    f"relationship names '{side}', which is not a table in this spec"
                )
        label = rel.reference_label or f"Related {rel.parent}"
        reference_fields[(rel.parent, rel.child)] = logical_id("Field", label)
        reference_fields[(rel.parent, rel.child, label)] = logical_id("Field", label)
        parents_of.setdefault(rel.child, []).append(rel)

    relationship_ids: Dict[str, RelationshipSpec] = {}
    for rel in spec.relationships:
        for key in _relationship_ids(rel):
            clash = relationship_ids.get(key)
            if clash is not None:
                raise QBLCompileError(
                    f"relationships '{clash.parent}' -> '{clash.child}' and "
                    f"'{rel.parent}' -> '{rel.child}' both compile to the "
                    f"relationship ID '{key}'; rename a table so the two differ"
                )
            relationship_ids[key] = rel

    tables: Dict[str, Any] = {}
    report_keys: Dict[Tuple[str, str], str] = {}
    for table in spec.tables:
        minter.enter_table()
        tables[table_names[table.name]] = _compile_table(
            table, spec, minter, table_names, reference_fields, parents_of, report_keys
        )

    for connected in spec.connected_tables:
        if connected.name in table_names:
            raise QBLCompileError(
                f"connected table '{connected.name}' has the same name as a table "
                f"in this spec; the two would compile to one"
            )
        minter.enter_table()
        connected_key = logical_id("Table", connected.name)
        compiled = _compile_table(
            _connected_table_spec(connected), spec, minter, table_names,
            reference_fields, parents_of, report_keys,
        )
        compiled["Properties"]["ConnectedData"] = _connected_table_binding(connected)
        tables[connected_key] = compiled

    roles = {
        logical_id("Role", role.name): {
            "Type": "QB::Application::Role",
            "Properties": _role_properties(role),
        }
        for role in spec.roles
    }

    application: Dict[str, Any] = {
        "Type": "QB::Application",
        "Properties": {"Name": spec.name},
        "Tables": tables,
        "Pages": _pages(spec, minter, report_keys, tables),
    }
    if spec.description:
        application["Properties"]["Description"] = spec.description
    if spec.properties:
        _require_known_properties(
            "QB::Application", spec.properties, f"application '{spec.name}'"
        )
        _merge_properties(application["Properties"], spec.properties)
    if roles:
        application["Roles"] = roles
    if spec.guides:
        page_names = {page.name for page in spec.pages}
        for guide in spec.guides:
            if guide.links_to not in page_names:
                raise QBLCompileError(
                    f"guide '{guide.title}' links to '{guide.links_to}', which is "
                    f"not a page in this spec"
                )
        application["Guides"] = {
            logical_id("AppGuide", guide.title): {
                "Type": "QB::Application::Guide",
                "Properties": _guide_properties(guide),
            }
            for guide in spec.guides
        }
    if spec.variables:
        application["Variables"] = {
            logical_id("Variable", variable.name): {
                "Type": "QB::Application::Variable",
                "Properties": {"Name": variable.name, "Value": variable.value},
            }
            for variable in spec.variables
        }

    _mark_searchable(application)

    resources: Dict[str, Any] = {app_id: application}

    for pipeline in spec.pipelines:
        if ((pipeline.trigger_table or pipeline.steps)
                and QUICKBASE_CHANNEL_ACCOUNT not in resources):
            resources[QUICKBASE_CHANNEL_ACCOUNT] = {
                "Type": "QB::PipelineChannelAccount",
                "Properties": {
                    "AccountId": _numeric_id(
                        pipeline.account_id, "account_id",
                        f"pipeline '{pipeline.name}'"),
                    "Channel": "quickbase",
                    "AccountType": "tokenless",
                    "Alias": "realm-default-account",
                },
            }
        pipeline_key = logical_id("Pipeline", pipeline.name)
        if pipeline_key in resources:
            raise QBLCompileError(
                f"two pipelines compile to the logical ID '{pipeline_key}'")
        resources[pipeline_key] = _pipeline(pipeline, table_names, app_id, tables)

    document: Dict[str, Any] = {"Version": QBL_VERSION, "Resources": resources}

    if spec.connected_tables:
        document["ExternalResources"] = {
            logical_id("DataSource", table.name): _connected_table(table, minter)
            for table in spec.connected_tables
        }

    if resolve_tokens:
        try:
            resolve_field_tokens(document)
        except FieldTokenError as exc:
            raise QBLCompileError(str(exc)) from exc
    return document


SEARCHABLE_BY_DEFAULT = frozenset({
    "QB::Field::Address", "QB::Field::Checkbox", "QB::Field::Checkbox::Formula",
    "QB::Field::Date", "QB::Field::Date::Formula", "QB::Field::Duration",
    "QB::Field::Email", "QB::Field::ListUser", "QB::Field::Lookup",
    "QB::Field::MultiselectText", "QB::Field::MultiselectText::Formula",
    "QB::Field::RichText", "QB::Field::RichText::Formula", "QB::Field::Text",
    "QB::Field::Text::Formula", "QB::Field::TextMultipleChoice",
    "QB::Field::User", "QB::Field::User::Formula",
})


def _mark_searchable(application: Dict[str, Any]) -> None:
    for table in (application.get("Tables") or {}).values():
        for node in (table.get("Fields") or {}).values():
            if node.get("Type") in SEARCHABLE_BY_DEFAULT:
                node.setdefault("Properties", {}).setdefault("IsSearchable", True)


KANBAN_MAX_CARD_FIELDS = 3

KANBAN_GROUP_BY_KINDS = frozenset({
    "TextMultipleChoice", "User", "AddressCountry", "AddressState",
})


QB_FILTER_OPERATORS = frozenset({
    "EX", "XEX", "CT", "XCT", "SW", "XSW", "GT", "GTE", "LT", "LTE",
    "BF", "OBF", "AF", "OAF", "IR", "XIR", "TV",
})


def _report_filters(report, fields: Dict[str, Any],
                    table: TableSpec) -> Dict[str, Any]:
    by_label = {
        node["Properties"]["Label"]: node["Id"]
        for node in fields.values()
        if "Id" in node and "Label" in node.get("Properties", {})
    }
    clauses = []
    for entry in report.filters:
        try:
            label, operator, value = entry
        except (TypeError, ValueError):
            raise QBLCompileError(
                f"report '{report.name}' has the filter {entry!r}, which is not "
                f"a (field label, operator, value) triple"
            ) from None
        if label not in by_label:
            raise QBLCompileError(
                f"report '{report.name}' filters on '{label}', which table "
                f"'{table.name}' does not declare"
            )
        if operator not in QB_FILTER_OPERATORS:
            raise QBLCompileError(
                f"report '{report.name}' filters with '{operator}', which is "
                f"not a Quickbase comparison operator. Use one of "
                f"{sorted(QB_FILTER_OPERATORS)}."
            )
        clauses.append("({{'{0}'.{1}.'{2}'}})".format(
            by_label[label], operator, value))

    criteria = clauses[0] if len(clauses) == 1 else "(" + "AND".join(clauses) + ")"
    return {"Criteria": criteria, "DynamicFields": "Default",
            "AllowQuickSearch": False}


def _field_labels_of(table: TableSpec,
                     parents_of: Dict[str, List[RelationshipSpec]]) -> List[str]:
    labels = [label for label, _kind, _id in BUILTIN_FIELDS]
    labels += [rel.reference_label or f"Related {rel.parent}"
               for rel in parents_of.get(table.name, [])]
    for field_spec in table.fields:
        labels.append(field_spec.label)
        if field_spec.kind == "Address":
            labels += [f"{field_spec.label} {part}" for _p, _s, part in ADDRESS_PARTS]
    return labels


def _default_columns(table: TableSpec,
                     parents_of: Dict[str, List[RelationshipSpec]]) -> List[str]:
    if table.default_columns is not None:
        known = set(_field_labels_of(table, parents_of))
        unknown = [label for label in table.default_columns if label not in known]
        if unknown:
            raise QBLCompileError(
                f"table '{table.name}' names default columns it does not have: "
                f"{unknown}")
        return list(table.default_columns)

    ordered: List[str] = []
    for report in table.reports:
        for label in report.columns:
            if label not in ordered:
                ordered.append(label)
    if ordered:
        return ordered
    return [f.label for f in table.fields if f.kind != "ReportLink"]


def _mark_default_columns(table: TableSpec, fields: Dict[str, Any],
                          parents_of: Dict[str, List[RelationshipSpec]]) -> None:
    subfield_parent: Dict[str, str] = {}
    for field_spec in table.fields:
        if field_spec.kind == "Address":
            for _prop, _suffix, part in ADDRESS_PARTS:
                subfield_parent[f"{field_spec.label} {part}"] = field_spec.label

    for label in _default_columns(table, parents_of):
        node = fields.get(logical_id("Field", subfield_parent.get(label, label)))
        if node is None:
            continue
        node.setdefault("Properties", {}).setdefault("AddToAllNewReports", True)


def _default_sort_order(table: TableSpec, fields: Dict[str, Any],
                        record_id: str) -> Dict[str, Any]:
    for report in table.reports:
        for label in report.sort_by:
            if logical_id("Field", label) in fields:
                return {"SortOrder": "Ascending",
                        "TargetField": _ref(Field=logical_id("Field", label))}
    return {"SortOrder": "Descending", "TargetField": _ref(Field=record_id)}


EMBED_MODES = ("Create", "Edit", "View")


EMBEDDED_REPORT_NAME = "Embedded for {parent}"


def _place_embed(form: Any, link_label: str, report_name: str, child: str) -> str:
    found = "absent"

    def bare(member: Any) -> bool:
        if isinstance(member, str):
            return member == link_label
        return (isinstance(member, FormElementSpec) and member.field == link_label
                and member.embedded_report is None and not member.members
                and member.content is None and member.kind is None)

    def visit(container: List[Any]) -> None:
        nonlocal found
        for index, member in enumerate(container):
            if isinstance(member, FormElementSpec):
                if member.field == link_label and member.embedded_report:
                    found = "explicit"
                    continue
                visit(member.members)
            if bare(member):
                if isinstance(member, str):
                    container[index] = FormElementSpec(
                        field=link_label, embedded_report=report_name,
                        embedded_table=child)
                else:
                    member.embedded_report = report_name
                    member.embedded_table = child
                if found == "absent":
                    found = "placed"

    if isinstance(form, FormSpec):
        for section in form.sections:
            for column in section.columns:
                visit(column.fields)
    elif isinstance(form, LegacyFormSpec):
        visit(form.fields)
        for section in form.sections:
            visit(section.fields)
            for row in section.rows:
                visit(row)
            for tab in section.tabs:
                for row in tab.rows:
                    visit(row)
    return found


def _with_reference_labels(spec: AppSpec) -> AppSpec:
    if all(rel.reference_label for rel in spec.relationships):
        return spec
    spec = copy.deepcopy(spec)
    singular = {table.name: (table.singular or table.name) for table in spec.tables}
    for rel in spec.relationships:
        if not rel.reference_label:
            rel.reference_label = f"Related {singular.get(rel.parent, rel.parent)}"
    return spec


def _proxy_lookup(table: TableSpec, rel: RelationshipSpec) -> Optional[FieldSpec]:
    if not rel.display_parent or not rel.display_field:
        return None
    for field_spec in table.fields:
        if (field_spec.kind == "Lookup" and field_spec.lookup_table == rel.parent
                and field_spec.lookup_field == rel.display_field
                and field_spec.lookup_via in (None, rel.reference_label)):
            return field_spec
    return None


def _proxy_lookups(table: TableSpec,
                   parents_of: Dict[str, List[RelationshipSpec]]) -> List[str]:
    out = []
    for rel in parents_of.get(table.name, []):
        proxy = _proxy_lookup(table, rel)
        if proxy is not None:
            out.append(proxy.label)
    return out


def _reference_block(rel: RelationshipSpec, table: TableSpec) -> Dict[str, Any]:
    block: Dict[str, Any] = {
        "Relationship": _ref(
            Relationship=logical_id("Relationship", _relationship_key(rel))
        ),
    }
    proxy = _proxy_lookup(table, rel)
    if proxy is not None:
        block["Proxy"] = _ref(Field=logical_id("Field", proxy.label))
        block["DisplayAsLinkToParent"] = True
    block["DisplayType"] = "QB::Field::Number"
    return block


def _with_reference_proxies(spec: AppSpec) -> AppSpec:
    tables = {table.name: table for table in spec.tables}
    wanted = [rel for rel in spec.relationships if rel.display_parent
              and rel.parent in tables and rel.child in tables]
    if not wanted:
        return spec
    spec = copy.deepcopy(spec)
    tables = {t.name: t for t in spec.tables}
    for rel in spec.relationships:
        if not rel.display_parent or rel.parent not in tables or rel.child not in tables:
            continue
        parent, child = tables[rel.parent], tables[rel.child]
        parent_fields = {f.label: f for f in parent.fields}
        if rel.display_field is None:
            rel.display_field = parent.title_field or next(
                (f.label for f in parent.fields if f.kind == "Text"), None)
            if rel.display_field is None:
                continue
        if rel.display_field not in parent_fields:
            raise QBLCompileError(
                f"relationship '{rel.parent}' -> '{rel.child}' displays "
                f"'{rel.display_field}', which is not a field of '{rel.parent}'")
        if _proxy_lookup(child, rel) is not None:
            continue
        singular = parent.singular or parent.name
        prefix = (singular if rel.reference_label == f"Related {singular}"
                  else rel.reference_label)
        label = f"{prefix} - {rel.display_field}"
        if any(f.label == label for f in child.fields):
            raise QBLCompileError(
                f"relationship '{rel.parent}' -> '{rel.child}' would add the "
                f"lookup '{label}', and '{rel.child}' already has a field by "
                f"that name")
        child.fields.append(FieldSpec(
            label, "Lookup", lookup_table=rel.parent,
            lookup_field=rel.display_field, lookup_via=rel.reference_label,
            comments=f"Shown by {rel.reference_label} in place of the "
                     f"{singular} record id."))
    return spec


def _with_relationship_views(spec: AppSpec) -> AppSpec:
    if not any(rel.embed_on_parent for rel in spec.relationships):
        return spec

    tables = {table.name: table for table in spec.tables}
    if any(rel.parent not in tables or rel.child not in tables
           for rel in spec.relationships):
        return spec

    spec = copy.deepcopy(spec)
    tables = {table.name: table for table in spec.tables}
    parents_of: Dict[str, List[RelationshipSpec]] = {}
    for rel in spec.relationships:
        parents_of.setdefault(rel.child, []).append(rel)
    role_ids = [logical_id("Role", role.name) for role in spec.roles]

    for rel in spec.relationships:
        if not rel.embed_on_parent:
            continue
        parent, child = tables[rel.parent], tables[rel.child]
        reference = rel.reference_label or f"Related {rel.parent}"

        link = next((f for f in parent.fields if f.kind == "ReportLink"
                     and (f.link_table or parent.name) == child.name
                     and f.link_field == reference), None)
        if link is None:
            label = rel.embed_label or child.plural or child.name
            if label in _field_labels_of(parent, parents_of):
                raise QBLCompileError(
                    f"relationship '{rel.parent}' -> '{rel.child}' would give "
                    f"'{rel.parent}' a report link labelled '{label}', and it "
                    f"already has a field by that name; set `embed_label`, or "
                    f"`embed_on_parent=False` to build none")
            link = FieldSpec(label, "ReportLink", link_source="Record ID#",
                             link_table=child.name, link_field=reference,
                             properties={"MatchValuesExactly": True})
            parent.fields.append(link)

        if parent.form is None and parent.legacy_form is None:
            parent.form = _default_form(parent, parents_of)
        form = parent.form if parent.form is not None else parent.legacy_form
        if form is None:
            continue

        report_name = EMBEDDED_REPORT_NAME.format(parent=parent.name)
        placement = _place_embed(form, link.label, report_name, child.name)
        if placement == "explicit":
            continue

        if not child.reports:
            child.reports.append(ReportSpec(f"All {child.name}"))
        declared = next((r for r in child.reports if r.name == report_name), None)
        if declared is not None and role_ids and "RolePermissions" not in declared.properties:
            declared.properties = {**declared.properties, "RolePermissions":
                                   {role: False for role in role_ids}}
        if declared is None:
            through_here = {f.label for f in child.fields
                            if f.kind == "Lookup" and f.lookup_table == parent.name}
            columns = rel.embed_columns
            if columns is None:
                columns = [label for label in _default_columns(child, parents_of)
                           if label != reference and label not in through_here]
            child.reports.append(ReportSpec(
                report_name, columns=list(columns),
                properties=({"RolePermissions": {role: False for role in role_ids}}
                            if role_ids else {})))

        if placement == "placed":
            continue
        element = FormElementSpec(field=link.label, embedded_report=report_name,
                                  embedded_table=child.name)
        title = rel.embed_label or link.label
        if isinstance(form, FormSpec):
            form.sections.append(FormSectionSpec(
                title=title, modes=list(EMBED_MODES),
                columns=[FormColumnSpec([element])]))
        else:
            form.sections.append(LegacyFormSectionSpec(heading=title, rows=[[element]]))
    return spec


def _compile_table(table: TableSpec, spec: AppSpec, minter: _IdMinter,
                   table_names: Dict[str, str],
                   reference_fields: Dict[Tuple[str, str], str],
                   parents_of: Dict[str, List[RelationshipSpec]],
                   report_keys: Dict[Tuple[str, str], str]) -> Dict[str, Any]:
    fields: Dict[str, Any] = _builtin_fields()

    for rel in parents_of.get(table.name, []):
        label = rel.reference_label or f"Related {rel.parent}"
        properties = {
            "Label": label,
            "Reference": _reference_block(rel, table),
        }
        extra = getattr(rel, "reference_properties", None) or {}
        if extra:
            owned = sorted({"Label", "Reference"} & set(extra))
            if owned:
                raise QBLCompileError(
                    f"relationship '{rel.parent}' -> '{rel.child}' sets "
                    f"{', '.join(owned)} in reference_properties; the builder "
                    f"builds those - name the field with reference_label"
                )
            _require_known_properties(
                "QB::Field::Reference", extra, f"reference field '{label}'")
            properties.update(extra)
        fields[logical_id("Field", label)] = {
            "Type": "QB::Field::Reference",
            "Id": minter.take("field"),
            "Properties": properties,
        }

    for field_spec in table.fields:
        field_id = logical_id("Field", field_spec.label)
        if field_id in fields:
            raise QBLCompileError(
                f"table '{table.name}' declares '{field_spec.label}' twice"
            )
        qbl_type = f"QB::Field::{FIELD_KIND_ALIASES.get(field_spec.kind, field_spec.kind)}"
        _require_known_field_kind(qbl_type, field_spec, table)

        if field_spec.kind == "Address":
            fields.update(_address_fields(field_spec, minter))
            continue

        properties: Dict[str, Any] = {"Label": field_spec.label}
        if field_spec.kind == "Summary":
            properties["Summary"] = _summary_field(
                field_spec, table.name, table_names, reference_fields, spec
            )
        elif field_spec.kind == "Lookup":
            properties["Lookup"] = _lookup_block(field_spec, table, table_names, parents_of)
        elif field_spec.kind == "ReportLink" and field_spec.link_source:
            properties["FieldRelationship"] = _report_link_relationship(
                field_spec, table, table_names
            )
        if field_spec.formula is not None:
            if not field_spec.kind.endswith("::Formula"):
                raise QBLCompileError(
                    f"field '{field_spec.label}' carries a formula but its kind is "
                    f"'{field_spec.kind}'. There is no generic formula field - the "
                    f"kind names what it produces, such as 'Text::Formula'"
                )
            properties["Formula"] = field_spec.formula
        if field_spec.opens_page is not None:
            properties.update(_code_page_button(field_spec, table, spec))
        if field_spec.unique:
            properties["IsUnique"] = True
        if field_spec.required:
            properties["IsRequired"] = True
        if field_spec.help_text is not None:
            properties["HelpText"] = field_spec.help_text
        if field_spec.comments is not None:
            properties["Comments"] = field_spec.comments
        if field_spec.default_value is not None:
            properties["DefaultValue"] = field_spec.default_value
        if field_spec.choices is not None:
            properties["InputOptions"] = {
                "InputType": "FromList",
                "ListChoices": list(field_spec.choices),
                "AllowCreateChoices": False,
                "ChoiceOrder": "Alphabetical",
            }

        if field_spec.properties:
            _require_known_field_properties(qbl_type, field_spec)
            properties.update(field_spec.properties)

        fields[field_id] = {
            "Type": qbl_type,
            "Id": minter.take("field"),
            "Properties": properties,
        }

    _mark_default_columns(table, fields, parents_of)

    record_id = logical_id("Field", "Record ID#")

    table_properties: Dict[str, Any] = {
        "Name": table.name,
        "TableIconName": DEFAULT_TABLE_ICON,
        "AliasHint": _table_alias(table.name),
        "KeyField": _ref(Field=record_id),
        "DefaultReportSettings": {
            "ActionOnNewFieldAdd": "MakeDefault",
            "DefaultColorCoding": {"ColorBy": "None", "Appearance": "Pale"},
            "DefaultFilters": {"DynamicFields": "Default", "AllowQuickSearch": False},
            "DefaultSortOrder": _default_sort_order(table, fields, record_id),
        },
        "TableHomePageSettings": {
            "HomepageView": "SameForEveryone",
            "RoleViews": {"Everyone": {"View": "DefaultReport"}},
        },
    }

    form = table.form if table.form is not None else _default_form(table, parents_of)
    form_id = logical_id("FormV2", table.name)
    form_node: Dict[str, Any] = {
        "Type": "QB::FormV2",
        "Id": minter.take("form"),
        "Properties": {},
    }
    if form is not None:
        form_node["Properties"] = {"Name": form.name}
        form_node.update(_form_layout(form, minter, table, spec))

    field_kinds = {label: kind for label, kind, _ in BUILTIN_FIELDS}
    for rel in parents_of.get(table.name, []):
        field_kinds[rel.reference_label or f"Related {rel.parent}"] = "Reference"
    field_kinds.update({f.label: f.kind for f in table.fields})
    legacy_node = None
    if table.legacy_form is not None:
        legacy_node = _legacy_form(table.legacy_form, table, minter, field_kinds, spec)
    compiled: Dict[str, Any] = {
        "Type": "QB::Table",
        "Properties": table_properties,
        "Fields": fields,
        "Forms": {
            "Properties": _forms_properties(table, spec, form_id, form),
            "Resources": (
                {logical_id("Form", table.name): legacy_node, form_id: form_node}
                if legacy_node is not None else {form_id: form_node}
            ),
        },
    }
    if table.singular:
        compiled["Properties"]["RecordNameSingular"] = table.singular
    if table.plural:
        compiled["Properties"]["RecordNamePlural"] = table.plural
    role_permissions = _table_role_permissions(table, spec)
    if role_permissions:
        compiled["Properties"]["RolePermissions"] = role_permissions
    if table.title_field is not None:
        if table.title_field not in field_kinds:
            raise QBLCompileError(
                f"table '{table.name}' is titled by '{table.title_field}', which "
                f"it does not declare")
        compiled["Properties"]["RecordTitleField"] = _ref(
            Field=logical_id("Field", table.title_field))
        compiled["Properties"]["UseCustomRecordTitleField"] = True
    if table.properties:
        _require_known_properties(
            "QB::Table", table.properties, f"table '{table.name}'"
        )
        _require_known_table_icon(table)
        _merge_properties(compiled["Properties"], table.properties)

    reports = table.reports or [ReportSpec(f"All {table.name}")]
    compiled_reports: Dict[str, Any] = {}
    members: List[Any] = []
    for report in reports:
        report_key = logical_id("Report", f"{table.name}_{report.name}")
        qbl_type = f"QB::Report::{report.kind}"
        properties: Dict[str, Any] = {"Name": report.name}
        if report.kind not in REPORTS_WITHOUT_COLOR_CODING:
            properties["ColorCoding"] = {"ColorBy": "None"}
        if report.kind == "Kanban" and "CardGroups" not in report.properties:
            if not report.group_by_field:
                raise QBLCompileError(
                    f"report '{report.name}' is a Kanban, which groups its "
                    f"cards into columns by a field; set group_by_field. "
                    f"Without `CardGroups` the board has no columns, and the "
                    f"platform's answer is a create that hangs with no "
                    f"diagnostic, though the document looks valid."
                )
            group_kind = field_kinds.get(report.group_by_field)
            if group_kind is None:
                raise QBLCompileError(
                    f"report '{report.name}' groups by "
                    f"'{report.group_by_field}', which table '{table.name}' "
                    f"does not declare"
                )
            if group_kind not in KANBAN_GROUP_BY_KINDS:
                raise QBLCompileError(
                    f"report '{report.name}' groups by "
                    f"'{report.group_by_field}', which is a {group_kind}. A "
                    f"kanban column comes from a closed set of values, so "
                    f"`CardGroups.GroupBy` takes one of "
                    f"{sorted(KANBAN_GROUP_BY_KINDS)} and nothing else."
                )
            properties["CardGroups"] = {
                "GroupBy": _ref(Field=logical_id("Field", report.group_by_field)),
                "Values": "All",
            }
            properties.setdefault("DisplayFields", "Default")
            properties.setdefault("Sort", "Default")
        from qblparser.qbl_schema import QBL_SCHEMA

        report_schema = QBL_SCHEMA.get(qbl_type, {})
        report_properties = (set(report_schema.get("required", []))
                             | set(report_schema.get("optional", [])))
        if report.columns and report.kind == "Kanban":
            if len(report.columns) > KANBAN_MAX_CARD_FIELDS:
                raise QBLCompileError(
                    f"report '{report.name}' is a Kanban showing "
                    f"{len(report.columns)} fields on each card; the platform "
                    f"allows {KANBAN_MAX_CARD_FIELDS} (`BadMaxItems` at 4)")
            properties["DisplayFields"] = [
                _ref(Field=logical_id("Field", label)) for label in report.columns
            ]
        elif report.columns:
            if "Columns" not in report_properties:
                raise QBLCompileError(
                    f"report '{report.name}' is a {report.kind}, which has no "
                    f"column list; `columns` applies to Table, GridEdit, Map and "
                    f"Timeline reports. Say what a {report.kind} shows through "
                    f"`properties` - a calendar's `CalendarEvents.DisplayFields`, "
                    f"a summary's `summary_columns`.")
            properties["Columns"] = [
                _ref(Field=logical_id("Field", label)) for label in report.columns
            ]
        if report.sort_by and "SortAndGroup" not in report_properties:
            raise QBLCompileError(
                f"report '{report.name}' is a {report.kind}, which takes no "
                f"`SortAndGroup`; `sort_by` applies to Table and Timeline reports")
        if report.sort_by:
            properties["SortAndGroup"] = [
                {"Field": _ref(Field=logical_id("Field", label)), "SortOrder": "Ascending"}
                for label in report.sort_by
            ]
        if report.properties:
            _require_known_properties(
                qbl_type, report.properties, f"report '{report.name}'"
            )
            properties.update(report.properties)

        node: Dict[str, Any] = {
            "Type": qbl_type,
            "Id": minter.take("report"),
            "Properties": properties,
        }
        node.update(_summary_containers(report))
        compiled_reports[report_key] = node
        members.append(_ref(Report=report_key))
        report_keys[(table.name, report.name)] = report_key
        if report.filters:
            compiled_reports[report_key]["Properties"]["Filters"] = (
                _report_filters(report, fields, table))
    compiled["Reports"] = compiled_reports

    if table.charts:
        compiled_charts: Dict[str, Any] = {}
        for chart in table.charts:
            chart_key = logical_id("Chart", f"{table.name}_{chart.name}")
            chart_node: Dict[str, Any] = {
                "Type": f"QB::Chart::{chart.kind}",
                "Id": minter.take("chart"),
                "Properties": _chart_properties(
                    chart,
                    logical_id("Field", chart.value_field),
                    logical_id("Field", chart.category_field) if chart.category_field else None,
                    logical_id("Field", chart.second_field) if chart.second_field else None,
                    field_kinds.get(chart.category_field),
                ),
            }
            chart_node.update(_summary_containers(chart))
            compiled_charts[chart_key] = chart_node
            members.append(_ref(Chart=chart_key))
            report_keys[(table.name, chart.name)] = chart_key
        compiled["Charts"] = compiled_charts

    compiled["ReportGroups"] = {
        logical_id("ReportGroup", f"{table.name}_Common"): {
            "Type": "QB::ReportGroup",
            "Properties": {"Name": "Common", "Reports": members},
        }
    }

    if table.emails:
        compiled["Emails"] = {
            logical_id("CustomEmail", f"{table.name}_{email.name}"): _custom_email(
                email, table.name, compiled["Fields"])
            for email in table.emails
        }

    if table.document_templates:
        compiled["DocumentTemplates"] = {
            logical_id("DocumentTemplate", f"{table.name}_{template.name}"): {
                "Type": "QB::DocumentTemplate",
                "Id": minter.take("template"),
                "Properties": {"Name": template.name},
            }
            for template in table.document_templates
        }

    relationships: Dict[str, Any] = {}
    for rel in spec.relationships:
        child_key, parent_key = _relationship_ids(rel)
        if rel.parent == table.name:
            relationships[parent_key] = {"Type": "QB::Relationship::Parent"}
        if rel.child == table.name:
            relationships[child_key] = {
                "Type": "QB::Relationship::Child",
                "Properties": {
                    "Parent": _ref(Table=table_names[rel.parent], Relationship=parent_key)
                },
            }
    if relationships:
        compiled["Relationships"] = relationships

    return compiled


__all__ = ["compile_app", "logical_id", "QBLCompileError"]
