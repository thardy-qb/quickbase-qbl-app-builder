from __future__ import annotations

import re
from typing import Any, Dict, Iterator, List, Mapping, Tuple

from qblparser.contracts import QBLIssue


HOME_PAGE_TYPE = "QB::HomePage"

FORM_TYPE_PREFIXES = ("QB::FormV2", "QB::Form")

REPORT_LIKE_PREFIXES = ("$Report_", "$Chart_")

BUILTIN_REPORT_TYPE_PREFIX = "QB::Report::Default"

BUILTIN_FIELD_TYPES = (
    "QB::Field::DateCreated",
    "QB::Field::DateModified",
    "QB::Field::RecordID",
    "QB::Field::RecordOwner",
    "QB::Field::LastModifiedBy",
)

V2_SECTION_TYPE = "QB::FormV2::Section"
V2_COLUMN_TYPE = "QB::FormV2::Column"
V2_SECTION_WIDTH = 12
V2_SECTION_MAX_COLUMNS = 6

V2_ELEMENT_PREFIX = "QB::FormV2::Element::"
V2_GROUP_TYPE = "QB::FormV2::Element::Group"


def _issue(code: str, severity: str, logical_id: str, path: str, qbl_type: str, problem: str) -> QBLIssue:
    return {
        "LogicalID": logical_id,
        "Path": path,
        "Type": qbl_type,
        "Problem": problem,
        "Code": code,
        "Severity": severity,
    }


def iter_applications(qbl_data: Any) -> Iterator[Tuple[str, Mapping[str, Any]]]:
    if not isinstance(qbl_data, Mapping):
        return
    resources = qbl_data.get("Resources")
    if not isinstance(resources, Mapping):
        return
    for logical_id, node in resources.items():
        if isinstance(node, Mapping) and node.get("Type") == "QB::Application":
            yield str(logical_id), node


def _check_home_page(logical_id: str, app: Mapping[str, Any]) -> List[QBLIssue]:
    pages = app.get("Pages")
    page_resources = pages.get("Resources") if isinstance(pages, Mapping) else None

    if isinstance(page_resources, Mapping):
        for node in page_resources.values():
            if isinstance(node, Mapping) and node.get("Type") == HOME_PAGE_TYPE:
                return []

    return [_issue(
        "STR001", "error", logical_id, f"{logical_id} > Pages", "QB::Application",
        f"application declares no {HOME_PAGE_TYPE}; the platform rejects an app "
        f"with no home page, and a dashboard in the same container does not count",
    )]


def _check_pages_properties(logical_id: str, app: Mapping[str, Any]) -> List[QBLIssue]:
    pages = app.get("Pages")
    if not isinstance(pages, Mapping) or "Properties" in pages:
        return []

    return [_issue(
        "STR002", "error", logical_id, f"{logical_id} > Pages", "QB::Application",
        "`Pages` has no `Properties` key; the platform rejects the whole document "
        "as `Unparsed: No Type defined for node with logicalId Resources`, which "
        "names the wrong node. An empty `Properties: {}` satisfies it",
    )]


def _iter_tables(app: Mapping[str, Any]) -> Iterator[Tuple[str, Mapping[str, Any]]]:
    tables = app.get("Tables")
    if not isinstance(tables, Mapping):
        return
    for logical_id, node in tables.items():
        if isinstance(node, Mapping):
            yield str(logical_id), node


def _check_table_has_a_form(app_id: str, table_id: str, table: Mapping[str, Any]) -> List[QBLIssue]:
    forms = table.get("Forms")
    form_resources = forms.get("Resources") if isinstance(forms, Mapping) else None

    if isinstance(form_resources, Mapping):
        for node in form_resources.values():
            node_type = node.get("Type", "") if isinstance(node, Mapping) else ""
            if str(node_type).startswith(FORM_TYPE_PREFIXES):
                return []

    return [_issue(
        "STR003", "error", table_id, f"{app_id} > Tables > {table_id} > Forms", "QB::Table",
        "table contains no form; the platform requires at least one, and either "
        "a QB::FormV2 or a legacy QB::Form satisfies it",
    )]


def _grouped_report_ids(table: Mapping[str, Any]) -> set:
    groups = table.get("ReportGroups")
    if not isinstance(groups, Mapping):
        return set()

    named = set()
    for group in groups.values():
        if not isinstance(group, Mapping):
            continue
        members = group.get("Properties", {}).get("Reports")
        if not isinstance(members, list):
            continue
        for member in members:
            if isinstance(member, str):
                named.add(member)
            elif isinstance(member, Mapping):
                for key in ("Report", "Chart", "value"):
                    target = member.get(key)
                    if isinstance(target, str):
                        named.add(target)
    return named


def _check_reports_are_grouped(app_id: str, table_id: str, table: Mapping[str, Any]) -> List[QBLIssue]:
    grouped = _grouped_report_ids(table)
    issues = []
    for container in ("Reports", "Charts"):
        nodes = table.get(container)
        if not isinstance(nodes, Mapping):
            continue
        for report_id, node in nodes.items():
            if not isinstance(node, Mapping) or not str(report_id).startswith(REPORT_LIKE_PREFIXES):
                continue
            if str(report_id) in grouped:
                continue
            if str(node.get("Type", "")).startswith(BUILTIN_REPORT_TYPE_PREFIX):
                continue
            issues.append(_issue(
                "STR004", "error", str(report_id),
                f"{app_id} > Tables > {table_id} > {container} > {report_id}",
                str(node.get("Type", "")),
                f"'{report_id}' belongs to no report group; the platform requires "
                f"every report and chart to be named by a QB::ReportGroup in the "
                f"table's ReportGroups container",
            ))
    return issues


def _check_builtin_fields(app_id: str, table_id: str, table: Mapping[str, Any]) -> List[QBLIssue]:
    fields = table.get("Fields")
    declared = set()
    if isinstance(fields, Mapping):
        for node in fields.values():
            if isinstance(node, Mapping):
                declared.add(str(node.get("Type", "")))

    return [
        _issue(
            "STR005", "error", table_id,
            f"{app_id} > Tables > {table_id} > Fields", "QB::Table",
            f"table declares no {field_type}; Quickbase creates the five built-in "
            f"fields itself and still requires QBL to declare each one",
        )
        for field_type in BUILTIN_FIELD_TYPES
        if field_type not in declared
    ]


ABORT_SAVE_ACTION = "QB::FormRule::Action::AbortSave"
RECORD_STATE_TRIGGER = "QB::FormRule::Trigger::RecordState"
SAVING_RECORD_STATES = ("IsSaving", "IsSavingAfterChecking")
FIELD_CHANGE_CONDITION = "QB::FormRule::Condition::FieldChange"
SAVING_TRIGGER_ACTIONS = (ABORT_SAVE_ACTION, "QB::FormRule::Action::Change")


def _has_saving_trigger(rule: Mapping[str, Any]) -> bool:
    triggers = rule.get("When")
    triggers = triggers if isinstance(triggers, list) else []
    return any(
        isinstance(trigger, Mapping)
        and trigger.get("Type") == RECORD_STATE_TRIGGER
        and (trigger.get("Properties") or {}).get("RecordState") in SAVING_RECORD_STATES
        for trigger in triggers)


def _check_saving_trigger_actions(
    app_id: str, table_id: str, form_id: str, rules: Any
) -> List[QBLIssue]:
    if not isinstance(rules, list):
        return []
    issues = []
    for index, rule in enumerate(rules):
        if not isinstance(rule, Mapping) or not _has_saving_trigger(rule):
            continue
        actions = rule.get("Actions") if isinstance(rule.get("Actions"), list) else []
        others = sorted({str(action.get("Type")) for action in actions
                         if isinstance(action, Mapping)
                         and action.get("Type") not in SAVING_TRIGGER_ACTIONS})
        if others:
            issues.append(_issue(
                "STR017", "error", form_id,
                f"{app_id} > Tables > {table_id} > Forms > {form_id} > Rules[{index}]",
                RECORD_STATE_TRIGGER,
                f"a rule triggered as the record saves may only take "
                f"{' and '.join(SAVING_TRIGGER_ACTIONS)} actions; this one also "
                f"takes {', '.join(others)}, and the platform refuses the rule",
            ))
    return issues
LEGACY_RULE_TYPE = "QB::FormRule"


def _check_abort_save_has_a_saving_trigger(
    app_id: str, table_id: str, form_id: str, rules: Any
) -> List[QBLIssue]:
    if not isinstance(rules, list):
        return []

    issues = []
    for index, rule in enumerate(rules):
        if not isinstance(rule, Mapping):
            continue

        actions = rule.get("Actions") if isinstance(rule.get("Actions"), list) else []
        conditions = rule.get("If") if isinstance(rule.get("If"), list) else []
        aborts = any(isinstance(action, Mapping)
                     and action.get("Type") == ABORT_SAVE_ACTION for action in actions)
        tests_change = any(isinstance(condition, Mapping)
                           and condition.get("Type") == FIELD_CHANGE_CONDITION
                           for condition in conditions)
        if not (aborts or tests_change):
            continue
        offender = ABORT_SAVE_ACTION if aborts else FIELD_CHANGE_CONDITION

        triggers = rule.get("When")
        triggers = triggers if isinstance(triggers, list) else []
        if any(
            isinstance(trigger, Mapping)
            and trigger.get("Type") == RECORD_STATE_TRIGGER
            and (trigger.get("Properties") or {}).get("RecordState") in SAVING_RECORD_STATES
            for trigger in triggers
        ):
            continue

        issues.append(_issue(
            "STR006", "error", form_id,
            f"{app_id} > Tables > {table_id} > Forms > {form_id} > Rules[{index}]",
            offender,
            f"a rule using {offender} needs a {RECORD_STATE_TRIGGER} in its "
            f"'When' whose RecordState is one of {', '.join(SAVING_RECORD_STATES)}; "
            f"the action is otherwise valid and so is the trigger, so what the "
            f"platform rejects is the pairing",
        ))
    return issues


def _check_legacy_rule_has_a_trigger(
    app_id: str, table_id: str, form_id: str, rules: Any
) -> List[QBLIssue]:
    if not isinstance(rules, list):
        return []

    issues = []
    for index, rule in enumerate(rules):
        if not isinstance(rule, Mapping) or rule.get("Type") != LEGACY_RULE_TYPE:
            continue
        triggers = rule.get("When")
        if isinstance(triggers, list) and triggers:
            continue
        issues.append(_issue(
            "STR010", "error", form_id,
            f"{app_id} > Tables > {table_id} > Forms > {form_id} > Rules[{index}]",
            LEGACY_RULE_TYPE,
            "legacy form rule declares no trigger; the platform requires at "
            "least one entry under 'When' and reports the rule by type rather "
            "than by logical ID, so a form with several rules does not say "
            "which one is short",
        ))
    return issues


def _check_legacy_rule_has_an_action(
    app_id: str, table_id: str, form_id: str, rules: Any
) -> List[QBLIssue]:
    if not isinstance(rules, list):
        return []

    issues = []
    for index, rule in enumerate(rules):
        if not isinstance(rule, Mapping) or rule.get("Type") != LEGACY_RULE_TYPE:
            continue
        actions = rule.get("Actions")
        if isinstance(actions, list) and actions:
            continue
        issues.append(_issue(
            "STR011", "error", form_id,
            f"{app_id} > Tables > {table_id} > Forms > {form_id} > Rules[{index}]",
            LEGACY_RULE_TYPE,
            "legacy form rule declares no action; the platform requires at "
            "least one entry under 'Actions' and answers BadMinItems, naming "
            "the rule by type rather than by logical ID",
        ))
    return issues


LEGACY_ROW_TYPE = "QB::Form::Element::Row"


def _check_legacy_rows_have_elements(
    app_id: str, table_id: str, form_id: str, elements: Any
) -> List[QBLIssue]:
    if not isinstance(elements, Mapping):
        return []

    issues = []
    for element_id, element in elements.items():
        if not isinstance(element, Mapping) or element.get("Type") != LEGACY_ROW_TYPE:
            continue
        children = element.get("Elements")
        if isinstance(children, Mapping) and children:
            continue
        issues.append(_issue(
            "STR012", "error", str(element_id),
            f"{app_id} > Tables > {table_id} > Forms > {form_id} > Elements > {element_id}",
            LEGACY_ROW_TYPE,
            "legacy form row holds no elements; the platform requires a row to "
            "have defined Elements and answers BadChild",
        ))
    return issues


def _iter_v2_sections(
    form: Mapping[str, Any]
) -> Iterator[Tuple[str, str, Mapping[str, Any]]]:
    pages = form.get("Pages")
    if not isinstance(pages, Mapping):
        return
    for page_id, page in pages.items():
        sections = page.get("Sections") if isinstance(page, Mapping) else None
        if not isinstance(sections, Mapping):
            continue
        for section_id, section in sections.items():
            if isinstance(section, Mapping) and section.get("Type") == V2_SECTION_TYPE:
                yield str(page_id), str(section_id), section


def _section_columns(section: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    columns = section.get("Columns")
    if not isinstance(columns, Mapping):
        return []
    return [column for column in columns.values()
            if isinstance(column, Mapping) and column.get("Type") == V2_COLUMN_TYPE]


def _check_section_columns_fit(
    app_id: str, table_id: str, form_id: str, form: Mapping[str, Any]
) -> List[QBLIssue]:
    issues = []
    for page_id, section_id, section in _iter_v2_sections(form):
        widths = [(column.get("Properties") or {}).get("LayoutWidth")
                  for column in _section_columns(section)]
        total = sum(width for width in widths if isinstance(width, int)
                    and not isinstance(width, bool))
        if total <= V2_SECTION_WIDTH:
            continue
        issues.append(_issue(
            "STR013", "error", section_id,
            f"{app_id} > Tables > {table_id} > Forms > {form_id} > Pages > "
            f"{page_id} > Sections > {section_id}",
            V2_SECTION_TYPE,
            f"the section's columns span {total} of a possible "
            f"{V2_SECTION_WIDTH}; the platform answers BadMaxItems and rejects "
            f"the document. A total below {V2_SECTION_WIDTH} is accepted",
        ))
    return issues


def _check_section_column_count(
    app_id: str, table_id: str, form_id: str, form: Mapping[str, Any]
) -> List[QBLIssue]:
    issues = []
    for page_id, section_id, section in _iter_v2_sections(form):
        count = len(_section_columns(section))
        if count <= V2_SECTION_MAX_COLUMNS:
            continue
        issues.append(_issue(
            "STR014", "error", section_id,
            f"{app_id} > Tables > {table_id} > Forms > {form_id} > Pages > "
            f"{page_id} > Sections > {section_id}",
            V2_SECTION_TYPE,
            f"the section holds {count} columns and a section holds at most "
            f"{V2_SECTION_MAX_COLUMNS}; the platform answers TooManyChildren. "
            f"Split it across two sections",
        ))
    return issues


def _iter_v2_elements(
    section: Mapping[str, Any]
) -> Iterator[Tuple[str, Mapping[str, Any]]]:
    def walk(elements: Any) -> Iterator[Tuple[str, Mapping[str, Any]]]:
        if not isinstance(elements, Mapping):
            return
        for element_id, element in elements.items():
            if not isinstance(element, Mapping):
                continue
            if str(element.get("Type", "")).startswith(V2_ELEMENT_PREFIX):
                yield str(element_id), element
            yield from walk(element.get("Elements"))

    for column in _section_columns(section):
        yield from walk(column.get("Elements"))


def _check_modes_to_show_in(
    app_id: str, table_id: str, form_id: str, form: Mapping[str, Any]
) -> List[QBLIssue]:
    issues = []
    for page_id, section_id, section in _iter_v2_sections(form):
        where = (f"{app_id} > Tables > {table_id} > Forms > {form_id} > Pages > "
                 f"{page_id} > Sections > {section_id}")
        subjects: List[Tuple[str, str, Mapping[str, Any], str]] = [
            (section_id, V2_SECTION_TYPE, section, where)
        ]
        subjects += [
            (element_id, str(element.get("Type")), element,
             f"{where} > Elements > {element_id}")
            for element_id, element in _iter_v2_elements(section)
            if element.get("Type") != V2_GROUP_TYPE
        ]

        for node_id, qbl_type, node, path in subjects:
            modes = (node.get("Properties") or {}).get("ModesToShowIn")
            if isinstance(modes, list) and modes:
                continue
            state = "an empty ModesToShowIn" if isinstance(modes, list) \
                else "no ModesToShowIn"
            issues.append(_issue(
                "STR015", "error", node_id, path, qbl_type,
                f"the node carries {state}, so it shows in no mode at all and "
                f"the form renders blank. The platform reports nothing for "
                f"this - set ModesToShowIn to some of View, Edit and Create",
            ))
    return issues


def _iter_forms(table: Mapping[str, Any]) -> Iterator[Tuple[str, Mapping[str, Any]]]:
    forms = table.get("Forms")
    resources = forms.get("Resources") if isinstance(forms, Mapping) else None
    if not isinstance(resources, Mapping):
        return
    for form_id, form in resources.items():
        if isinstance(form, Mapping):
            yield str(form_id), form


def _iter_declared(container: Any) -> Iterator[Tuple[str, Mapping[str, Any]]]:
    if not isinstance(container, Mapping):
        return
    for logical_id, node in container.items():
        if isinstance(logical_id, str) and isinstance(node, Mapping) and "Type" in node:
            yield logical_id, node


def _report_collisions(seen: Mapping[Any, List[str]], code: str, path: str,
                       qbl_type: str, describe) -> List[QBLIssue]:
    issues: List[QBLIssue] = []
    for value, owners in seen.items():
        if len(owners) < 2:
            continue
        for owner in sorted(owners):
            others = ", ".join(o for o in sorted(owners) if o != owner)
            issues.append(_issue(code, "error", owner, path, qbl_type,
                                 describe(value, others)))
    return issues


def _check_field_ids_are_unique(app_id: str, table_id: str,
                                table: Mapping[str, Any]) -> List[QBLIssue]:
    seen: Dict[Any, List[str]] = {}
    for field_id, field in _iter_declared(table.get("Fields")):
        node_id = field.get("Id")
        if node_id is not None:
            seen.setdefault(node_id, []).append(field_id)

    return _report_collisions(
        seen, "STR007", f"{app_id} > Tables > {table_id} > Fields", "QB::Table",
        lambda value, others: (
            f"field Id {value} is also used by {others} in this table; a field's "
            f"Id is its identity inside the table and the platform rejects the "
            f"document with DuplicateId"
        ),
    )


def _check_field_labels_are_unique(app_id: str, table_id: str,
                                   table: Mapping[str, Any]) -> List[QBLIssue]:
    seen: Dict[Any, List[str]] = {}
    for field_id, field in _iter_declared(table.get("Fields")):
        properties = field.get("Properties")
        label = properties.get("Label") if isinstance(properties, Mapping) else None
        if isinstance(label, str) and label:
            seen.setdefault(label, []).append(field_id)

    return _report_collisions(
        seen, "STR008", f"{app_id} > Tables > {table_id} > Fields", "QB::Table",
        lambda value, others: (
            f"field label '{value}' is also used by {others} in this table; "
            f"labels must be unique within a table and the platform rejects the "
            f"document with DuplicatePropertyValue. The same label in another "
            f"table is fine"
        ),
    )


def _check_role_names_are_unique(app_id: str, app: Mapping[str, Any]) -> List[QBLIssue]:
    seen: Dict[Any, List[str]] = {}
    for role_id, role in _iter_declared(app.get("Roles")):
        properties = role.get("Properties")
        name = properties.get("Name") if isinstance(properties, Mapping) else None
        if isinstance(name, str) and name:
            seen.setdefault(name, []).append(role_id)

    return _report_collisions(
        seen, "STR009", f"{app_id} > Roles", "QB::Application",
        lambda value, others: (
            f"role name '{value}' is also used by {others}; role names must be "
            f"unique within an application and the platform rejects the document "
            f"with DuplicatePropertyValue"
        ),
    )


FORMULAS_PER_REPORT = 3


def _check_report_formula_counts(app_id: str, table_id: str,
                                 table: Mapping[str, Any]) -> List[QBLIssue]:
    issues: List[QBLIssue] = []
    for container_name in ("Reports", "Charts"):
        container = table.get(container_name)
        if not isinstance(container, Mapping):
            continue
        for report_id, report in container.items():
            if not isinstance(report, Mapping):
                continue
            for key, family in (("ReportFormulas", "report"),
                                ("SummaryFormulas", "summary")):
                formulas = report.get(key)
                if isinstance(formulas, Mapping) and len(formulas) > FORMULAS_PER_REPORT:
                    issues.append(_issue(
                        "STR016", "error", str(report_id),
                        f"{app_id} > Tables > {table_id} > {container_name} > "
                        f"{report_id} > {key}",
                        str(report.get("Type", "")),
                        f"the report carries {len(formulas)} {family} formulas; "
                        f"the platform allows {FORMULAS_PER_REPORT} and refuses "
                        f"each one past that with BadChild",
                    ))
    return issues


HOME_SECTIONS = ("MainSection", "Sidebar")

HOME_ROW_LIMITS = {"MainSection": 3, "Sidebar": 1}

HOME_ROW_WIDTHS = {
    1: (("100%",),),
    2: (("50%", "50%"), ("66.6666%", "33.3333%"), ("33.3333%", "66.6666%")),
    3: (("33.3333%",) * 3, ("33%",) * 3),
}

HOME_WIDGET_MIN_HEIGHT = {"Report": 150, "ReportsList": 300, "WebPage": 20}

HOME_REPORT_VISIBLE_ROWS = range(5, 251)

HOME_REPORTS_LIST_MAX_TABLES = 8


def _iter_home_rows(app: Mapping[str, Any]) -> Iterator[Tuple[str, str, str, Mapping[str, Any]]]:
    pages = app.get("Pages")
    resources = pages.get("Resources") if isinstance(pages, Mapping) else None
    for page_id, page in (resources or {}).items():
        if not isinstance(page, Mapping) or page.get("Type") != HOME_PAGE_TYPE:
            continue
        for section in HOME_SECTIONS:
            for row_id, row in (page.get(section) or {}).items():
                if isinstance(row, Mapping):
                    yield str(page_id), section, str(row_id), row


def _check_home_row_layout(app_id: str, app: Mapping[str, Any]) -> List[QBLIssue]:
    issues: List[QBLIssue] = []
    for page_id, section, row_id, row in _iter_home_rows(app):
        widgets = [w for w in (row.get("Widgets") or {}).values() if isinstance(w, Mapping)]
        path = f"{app_id} > Pages > {page_id} > {section} > {row_id}"
        limit = HOME_ROW_LIMITS[section]
        if len(widgets) > limit:
            issues.append(_issue(
                "STR018", "error", row_id, path, str(row.get("Type", "")),
                f"the row holds {len(widgets)} widgets; a {section} row holds at "
                f"most {limit}"))
            continue
        if not widgets:
            continue
        widths = tuple(str((w.get("Properties") or {}).get("Width", "100%")) for w in widgets)
        if widths not in HOME_ROW_WIDTHS[len(widgets)]:
            allowed = " or ".join(" & ".join(c) for c in HOME_ROW_WIDTHS[len(widgets)])
            issues.append(_issue(
                "STR018", "error", row_id, path, str(row.get("Type", "")),
                f"the row's widths are {' & '.join(widths)}; a row of "
                f"{len(widgets)} takes {allowed}, written exactly"))
    return issues


def _check_home_widget_values(app_id: str, app: Mapping[str, Any]) -> List[QBLIssue]:
    issues: List[QBLIssue] = []
    for page_id, section, row_id, row in _iter_home_rows(app):
        for widget_id, widget in (row.get("Widgets") or {}).items():
            if not isinstance(widget, Mapping):
                continue
            qbl_type = str(widget.get("Type", ""))
            kind = qbl_type.rsplit("::", 1)[-1]
            props = widget.get("Properties") or {}
            path = f"{app_id} > Pages > {page_id} > {section} > {row_id} > {widget_id}"
            problems = []
            height = props.get("Height")
            if height is not None:
                match = re.fullmatch(r"(\d+)px", str(height))
                least = HOME_WIDGET_MIN_HEIGHT.get(kind)
                if not match:
                    problems.append(f"Height '{height}' is not whole pixels written like '400px'")
                elif least is not None and int(match.group(1)) < least:
                    problems.append(f"Height {height} is under the {least}px minimum for a {kind}")
            visible = props.get("MaximumVisibleRows")
            if (isinstance(visible, int) and not isinstance(visible, bool)
                    and visible != 0 and visible not in HOME_REPORT_VISIBLE_ROWS):
                problems.append(f"MaximumVisibleRows {visible} is not 0 or 5 to 250")
            targets = props.get("TargetTables")
            if isinstance(targets, list) and len(targets) > HOME_REPORTS_LIST_MAX_TABLES:
                problems.append(f"TargetTables names {len(targets)} tables; at most "
                                f"{HOME_REPORTS_LIST_MAX_TABLES}")
            for problem in problems:
                issues.append(_issue("STR019", "error", str(widget_id), path, qbl_type, problem))
    return issues


def validate_qbl_structure(qbl_data: Any) -> List[QBLIssue]:
    issues: List[QBLIssue] = []
    for logical_id, app in iter_applications(qbl_data):
        issues.extend(_check_home_page(logical_id, app))
        issues.extend(_check_pages_properties(logical_id, app))
        issues.extend(_check_role_names_are_unique(logical_id, app))
        issues.extend(_check_home_row_layout(logical_id, app))
        issues.extend(_check_home_widget_values(logical_id, app))
        for table_id, table in _iter_tables(app):
            issues.extend(_check_table_has_a_form(logical_id, table_id, table))
            issues.extend(_check_reports_are_grouped(logical_id, table_id, table))
            issues.extend(_check_builtin_fields(logical_id, table_id, table))
            issues.extend(_check_field_ids_are_unique(logical_id, table_id, table))
            issues.extend(_check_field_labels_are_unique(logical_id, table_id, table))
            issues.extend(_check_report_formula_counts(logical_id, table_id, table))
            for form_id, form in _iter_forms(table):
                issues.extend(_check_abort_save_has_a_saving_trigger(
                    logical_id, table_id, form_id, form.get("Rules")
                ))
                issues.extend(_check_saving_trigger_actions(
                    logical_id, table_id, form_id, form.get("Rules")
                ))
                issues.extend(_check_legacy_rule_has_a_trigger(
                    logical_id, table_id, form_id, form.get("Rules")
                ))
                issues.extend(_check_legacy_rule_has_an_action(
                    logical_id, table_id, form_id, form.get("Rules")
                ))
                issues.extend(_check_legacy_rows_have_elements(
                    logical_id, table_id, form_id, form.get("Elements")
                ))
                issues.extend(_check_section_columns_fit(
                    logical_id, table_id, form_id, form
                ))
                issues.extend(_check_section_column_count(
                    logical_id, table_id, form_id, form
                ))
                issues.extend(_check_modes_to_show_in(
                    logical_id, table_id, form_id, form
                ))
    return issues
