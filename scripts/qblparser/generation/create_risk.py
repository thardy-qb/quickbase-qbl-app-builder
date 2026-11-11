from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from qblparser.entities.fields import FieldExtractor
from qblparser.utils.qbl_tags import tag_of

from .compiler import (KNOWN_TABLE_ICONS, QUICKBASE_RECORD_SELECTORS,
                       UNCREATABLE_CHART_KINDS)

try:
    from .create_risk_evidence import EVIDENCE as _EVIDENCE_BY_CODE
except ImportError:
    _EVIDENCE_BY_CODE = {}

TIMEOUT = "timeout"
RESOURCE_FAILURE = "resource-failure"
SILENT = "silent"
BUILDER = "builder"
UNPARSED = "unparsed"

SYMPTOMS = (TIMEOUT, RESOURCE_FAILURE, SILENT, BUILDER, UNPARSED)


@dataclass(frozen=True)
class Risk:

    code: str
    severity: str
    symptom: str
    location: str
    problem: str
    fix: str
    evidence: str = ""

    def as_finding(self) -> Dict[str, Any]:
        return {
            "Code": self.code,
            "Severity": self.severity.capitalize(),
            "Problem": self.problem,
            "Path": self.location,
            "Type": "",
        }


def _nodes(node: Any, path: str = "") -> Iterator[Tuple[str, str, Mapping[str, Any]]]:
    if isinstance(node, Mapping):
        qbl_type = node.get("Type")
        if isinstance(qbl_type, str):
            yield path, qbl_type, node
        for key, value in node.items():
            if key in ("Type", "Id"):
                continue
            yield from _nodes(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _nodes(value, f"{path}[{index}]")


def _tables(document: Mapping[str, Any]) -> Iterator[Tuple[str, Mapping[str, Any]]]:
    for app in (document.get("Resources") or {}).values():
        if not isinstance(app, Mapping):
            continue
        for table_id, table in (app.get("Tables") or {}).items():
            if isinstance(table, Mapping):
                yield table_id, table


def _properties(node: Mapping[str, Any]) -> Mapping[str, Any]:
    properties = node.get("Properties")
    return properties if isinstance(properties, Mapping) else {}


def _name(node: Mapping[str, Any], fallback: str) -> str:
    return str(_properties(node).get("Name") or _properties(node).get("Label") or fallback)


def _uncreatable_charts(document: Mapping[str, Any]) -> List[Risk]:
    out = []
    for path, qbl_type, node in _nodes(document):
        if not qbl_type.startswith("QB::Chart::"):
            continue
        kind = qbl_type.rsplit("::", 1)[-1]
        if kind not in UNCREATABLE_CHART_KINDS:
            continue
        out.append(Risk(
            code="CRT001",
            severity="error",
            symptom=TIMEOUT,
            location=path,
            problem=(f"`{qbl_type}` cannot be created. A solution containing "
                     "one times out on create with no diagnostic."),
            fix=(f"Change this chart to a creatable kind - `Pie` for a "
                 f"`Donut`, `Funnel` for a `Funnel3D`. The whole donut family "
                 f"({', '.join(sorted(UNCREATABLE_CHART_KINDS))}) is refused."),
        ))
    return out


def _search_widget_without_a_table(document: Mapping[str, Any]) -> List[Risk]:
    out = []
    for path, qbl_type, node in _nodes(document):
        if qbl_type != "QB::HomePage::Widget::Search":
            continue
        properties = _properties(node)
        if "SearchTable" in properties:
            continue
        out.append(Risk(
            code="CRT002",
            severity="error",
            symptom=RESOURCE_FAILURE,
            location=path,
            problem=("A `QB::HomePage::Widget::Search` with no `SearchTable` fails "
                     "the create. Its `TargetField` references name no table; "
                     "`SearchTable` is what scopes them."),
            fix=("Add `SearchTable: !Ref {Table: $Table_X}` naming the table "
                 "the searched fields belong to."),
        ))
    return out


def _kanban_without_columns(document: Mapping[str, Any]) -> List[Risk]:
    out = []
    for path, qbl_type, node in _nodes(document):
        if qbl_type != "QB::Report::Kanban":
            continue
        if "CardGroups" in _properties(node):
            continue
        out.append(Risk(
            code="CRT003",
            severity="error",
            symptom=TIMEOUT,
            location=path,
            problem=("A `QB::Report::Kanban` with no `CardGroups`. The board has "
                     "no columns and the create hangs with no diagnostic."),
            fix=("Add `CardGroups` with a `GroupBy` naming a field of kind "
                 "`TextMultipleChoice`, `User`, `AddressCountry` or "
                 "`AddressState`."),
        ))
    return out


def _unknown_table_icons(document: Mapping[str, Any]) -> List[Risk]:
    out = []
    for table_id, table in _tables(document):
        icon = _properties(table).get("TableIconName")
        if icon is None or icon in KNOWN_TABLE_ICONS:
            continue
        out.append(Risk(
            code="CRT004",
            severity="error",
            symptom=SILENT,
            location=f"{table_id}.Properties.TableIconName",
            problem=(f"`TableIconName: {icon!r}` is outside the "
                     f"{len(KNOWN_TABLE_ICONS)} names the platform keeps. It is "
                     "**silently swapped for the default** on create - no "
                     "error, no warning - and the table renders with no icon."),
            fix="Use one of the known icon names, or omit the property.",
        ))
    return out


def _quoted_version(document: Mapping[str, Any]) -> List[Risk]:
    version = document.get("Version")
    if not isinstance(version, str):
        return []
    return [Risk(
        code="CRT005",
        severity="error",
        symptom=UNPARSED,
        location="Version",
        problem=(f"`Version: '{version}'` is a string where the platform "
                 "expects a number. The whole document is answered "
                 "`Unparsed: The provided YAML has syntax errors.` - which "
                 "names no line, no property and no type, and is document-wide, "
                 "so every other finding in the same submission is lost."),
        fix=f"Write it unquoted: `Version: {version}`.",
    )]


def _address_id_blocks(document: Mapping[str, Any]) -> List[Risk]:
    from .compiler import ADDRESS_PARTS

    out = []
    for table_id, table in _tables(document):
        fields = table.get("Fields") or {}
        if not isinstance(fields, Mapping):
            continue
        ids = {key: _properties(node).get("Id")
               for key, node in fields.items() if isinstance(node, Mapping)}

        for key, node in fields.items():
            if not isinstance(node, Mapping) or node.get("Type") != "QB::Field::Address":
                continue
            parent_id = ids.get(key)
            properties = _properties(node)
            part_ids = []
            for prop, _suffix, _label in ADDRESS_PARTS:
                target = FieldExtractor.from_reference(properties.get(prop))
                if target and isinstance(ids.get(target), int):
                    part_ids.append(ids[target])

            if not isinstance(parent_id, int) or len(part_ids) != len(ADDRESS_PARTS):
                continue

            block = sorted([parent_id, *part_ids])
            contiguous = block == list(range(block[0], block[0] + len(block)))
            parent_lowest = parent_id == block[0]
            if contiguous and parent_lowest:
                continue

            out.append(Risk(
                code="CRT006",
                severity="warning",
                symptom=TIMEOUT,
                location=f"{table_id}.Fields.{key}",
                problem=(f"The address is numbered parent {parent_id}, subfields "
                         f"{min(part_ids)}-{max(part_ids)}. Quickbase numbers "
                         "an address as a **contiguous block with the parent "
                         "lowest**."),
                fix=("Renumber the seven as parent, parent+1 ... parent+6."),
            ))
    return out


THIN_NODES: Tuple[Tuple[str, Tuple[str, ...], str], ...] = (
    ("QB::CustomEmail", ("Owner",),
     "an owner email"),
    ("QB::CustomEmail", ("EmailSettings", "To"),
     "a `To` block with `UserEntities`"),
    ("QB::DocumentTemplate", ("Template",),
     "a `Template` with `Content` holding the HTML; a name alone builds nothing"),
)


def _walk_path(properties: Mapping[str, Any], path: Sequence[str]) -> bool:
    node: Any = properties
    for step in path:
        if not isinstance(node, Mapping) or step not in node:
            return False
        node = node[step]
    return node not in (None, "", {}, [])


def _thin_nodes(document: Mapping[str, Any]) -> List[Risk]:
    out = []
    for path, qbl_type, node in _nodes(document):
        for target_type, property_path, expected in THIN_NODES:
            if qbl_type != target_type:
                continue
            if _walk_path(_properties(node), property_path):
                continue
            dotted = ".".join(property_path)
            out.append(Risk(
                code="CRT007",
                severity="warning",
                symptom=TIMEOUT,
                location=f"{path}.Properties.{dotted}",
                problem=(f"`{qbl_type}` carries no `{dotted}`. It needs "
                         f"{expected}."),
                fix=f"Add `{dotted}`.",
            ))
    return out


_FIELD_TOKEN = re.compile(r"\[([^\]]+)\]")


def _forward_formula_references(document: Mapping[str, Any]) -> List[Risk]:
    out = []
    for table_id, table in _tables(document):
        fields = table.get("Fields") or {}
        if not isinstance(fields, Mapping):
            continue

        by_label: Dict[str, int] = {}
        for node in fields.values():
            if not isinstance(node, Mapping):
                continue
            properties = _properties(node)
            label, node_id = properties.get("Label"), node.get("Id")
            if isinstance(label, str) and isinstance(node_id, int):
                by_label[label] = node_id

        for key, node in fields.items():
            if not isinstance(node, Mapping):
                continue
            properties = _properties(node)
            formula, own_id = properties.get("Formula"), node.get("Id")
            if not isinstance(formula, str) or not isinstance(own_id, int):
                continue
            ahead = sorted({label for label in _FIELD_TOKEN.findall(formula)
                            if by_label.get(label, -1) > own_id})
            if not ahead:
                continue
            out.append(Risk(
                code="CRT008",
                severity="note",
                symptom=TIMEOUT,
                location=f"{table_id}.Fields.{key}.Properties.Formula",
                problem=(f"Field id {own_id} has a formula naming "
                         f"{', '.join(f'`{label}` (id {by_label[label]})' for label in ahead)}"
                         " - fields at higher ids than its own. Fields are "
                         "created in id order."),
                fix=("Renumber so each formula's inputs have lower ids than "
                     "the formula."),
            ))
    return out


def _quickbase_steps(document: Mapping[str, Any]
                     ) -> Iterator[Tuple[str, Mapping[str, Any], Mapping[str, Any]]]:
    for path, qbl_type, node in _nodes(document):
        if qbl_type == "QB::PipelineStep::Quickbase":
            yield path, node, _properties(node)


def _step_source_names(step: Mapping[str, Any]) -> List[str]:
    names = []
    for meta in (step.get("InputsMeta") or {}).values():
        if not isinstance(meta, Mapping):
            continue
        for source in (meta.get("PipelineStep_DataSources") or {}).values():
            if isinstance(source, Mapping):
                name = _properties(source).get("Name")
                if isinstance(name, str):
                    names.append(name)
    return names


def _pipeline_selectors(document: Mapping[str, Any]) -> List[Risk]:
    out = []
    for path, _step, properties in _quickbase_steps(document):
        channel = properties.get("Channel") or {}
        if not isinstance(channel, Mapping) or channel.get("Resource") != "record":
            continue
        selector = channel.get("Selector")
        if selector in QUICKBASE_RECORD_SELECTORS:
            continue
        out.append(Risk(
            code="CRT009",
            severity="error",
            symptom=RESOURCE_FAILURE,
            location=f"{path}.Properties.Channel.Selector",
            problem=(f"Quickbase record step selector `{selector}` is not one the "
                     "platform accepts. The create is refused outright, the "
                     "application included: `Failed to write pipeline schemas "
                     "... Invalid selector`."),
            fix=("Use one of " + ", ".join(sorted(QUICKBASE_RECORD_SELECTORS))
                 + "."),
        ))
    return out


def _pipeline_steps_without_a_table(document: Mapping[str, Any]) -> List[Risk]:
    out = []
    for path, step, properties in _quickbase_steps(document):
        channel = properties.get("Channel") or {}
        if not isinstance(channel, Mapping) or channel.get("Resource") != "record":
            continue
        if channel.get("Selector") == "update" and properties.get("Target"):
            continue
        if "table" in _step_source_names(step):
            continue
        dropped = bool(properties.get("Inputs"))
        out.append(Risk(
            code="CRT010",
            severity="error" if dropped else "warning",
            symptom=SILENT,
            location=f"{path}.InputsMeta",
            problem=("A Quickbase record step names no table. The create "
                     "succeeds with `PipelineStepWarning ... required field: "
                     "app,table`, and the step does nothing"
                     + (" - its `Inputs` are deleted on the way in, so an export "
                        "shows a create step writing no fields at all."
                        if dropped else ".")),
            fix=("Give the step an `InputsMeta` with a "
                 "`QB::PipelineStep::DataSource::Table` named `table`, and a "
                 "`DataSource::Fields` named `export_fields` listing the fields "
                 "it reads or writes."),
        ))
    return out


def _update_triggers_without_trigger_fields(document: Mapping[str, Any]) -> List[Risk]:
    out = []
    for path, step, properties in _quickbase_steps(document):
        channel = properties.get("Channel") or {}
        if not isinstance(channel, Mapping) or channel.get("Selector") != "on_update":
            continue
        all_fields = any(
            isinstance(meta, Mapping)
            and _properties(meta).get("Trigger_On_All_Fields") is True
            for meta in (step.get("InputsMeta") or {}).values())
        if all_fields or "trigger_fields" in _step_source_names(step):
            continue
        out.append(Risk(
            code="CRT011",
            severity="warning",
            symptom=SILENT,
            location=f"{path}.InputsMeta",
            problem=("An `on_update` trigger with neither a `trigger_fields` list "
                     "nor `Trigger_On_All_Fields: true`. The create warns "
                     "`required field: ... trigger_fields` and the trigger "
                     "never fires."),
            fix=("List the fields whose change should fire it as a "
                 "`DataSource::Fields` named `trigger_fields`, or set "
                 "`Trigger_On_All_Fields: true` in the trigger's `InputsMeta` "
                 "properties - not both: a list sent beside `true` is dropped."),
        ))
    return out


def _placeholder_channel_accounts(document: Mapping[str, Any]) -> List[Risk]:
    out = []
    for path, qbl_type, node in _nodes(document):
        if qbl_type != "QB::PipelineChannelAccount":
            continue
        properties = _properties(node)
        if properties.get("Channel") != "quickbase":
            continue
        if properties.get("AccountType") == "tokenless" and properties.get("Alias"):
            continue
        out.append(Risk(
            code="CRT012",
            severity="warning",
            symptom=SILENT,
            location=path,
            problem=("A Quickbase channel account with no `AccountType: "
                     "tokenless` and `Alias`. The create answers `This step "
                     "uses a placeholder account. Connect your Quickbase "
                     "account.` and substitutes `placeholder-quickbase-account`; "
                     "every step using it is inert until a builder reconnects "
                     "it in the pipeline designer."),
            fix=("Declare it as the realm's default Quickbase connection: "
                 "`AccountType: tokenless`, `Alias: realm-default-account`. A "
                 "create binds that to the realm's real account whatever "
                 "`AccountId` says."),
        ))
    return out


def _pipelines_are_created_off(document: Mapping[str, Any]) -> List[Risk]:
    out = []
    for path, qbl_type, node in _nodes(document):
        if qbl_type != "QB::Pipeline" or not node.get("Steps"):
            continue
        out.append(Risk(
            code="CRT013",
            severity="note",
            symptom=SILENT,
            location=path,
            problem=("Every pipeline a solution creates is switched **off**. The "
                     "create reports nothing, the pipeline is complete and "
                     "correct, and it never runs."),
            fix=("After the create, turn it on in Pipelines (My pipelines, the "
                 "On / Off column). A later PUT leaves it on. QBL has no "
                 "property for it: `Enabled`, `IsEnabled`, `State` and `Active` "
                 "are each answered `ExtraProperty`."),
        ))
    return out


def _connected_bindings(document: Mapping[str, Any]
                        ) -> Iterator[Tuple[str, Mapping[str, Any]]]:
    for table_id, table in _tables(document):
        binding = _properties(table).get("ConnectedData")
        if isinstance(binding, Mapping):
            yield table_id, binding


def _connected_tables_without_a_schedule(document: Mapping[str, Any]) -> List[Risk]:
    return [Risk(
        code="CRT014",
        severity="error",
        symptom=RESOURCE_FAILURE,
        location=f"{table_id}.Properties.ConnectedData",
        problem=("A connected table's `ConnectedData` carries no `Schedule`. The "
                 "create fails with \"failure in creating one of the "
                 "resources\"."),
        fix="Add `Schedule: Manual`, or a cron such as `21 * * * *`.",
    ) for table_id, binding in _connected_bindings(document)
        if "Schedule" not in binding]


def _connected_schedules_at_minute_zero(document: Mapping[str, Any]) -> List[Risk]:
    out = []
    for table_id, binding in _connected_bindings(document):
        schedule = binding.get("Schedule")
        cron = schedule.get("CronTab") if isinstance(schedule, Mapping) else None
        if not isinstance(cron, str) or not cron.split():
            continue
        if cron.split()[0].strip("0") != "":
            continue
        out.append(Risk(
            code="CRT016",
            severity="warning",
            symptom=SILENT,
            location=f"{table_id}.Properties.ConnectedData.Schedule",
            problem=(f"A refresh at minute 0 (`{cron}`) is replaced with `Manual` "
                     "on create, with no warning: the table never refreshes."),
            fix="Use any other minute.",
        ))
    return out


def _connected_tables_arrive_as_placeholders(document: Mapping[str, Any]) -> List[Risk]:
    external = document.get("ExternalResources") or {}
    if not isinstance(external, Mapping):
        return []
    return [Risk(
        code="CRT015",
        severity="note",
        symptom=SILENT,
        location=f"ExternalResources.{key}",
        problem=("Every connected table a solution creates arrives as a "
                 "placeholder - `IsPlaceholder: true`, its columns "
                 "`QB::ConnectedColumn::Placeholder` - and holds no data until "
                 "the connection is finished in Quickbase."),
        fix=("After the create, open the table's connection in Quickbase and "
             "complete it. A placeholder `ConnectionId` creates too, and comes "
             "back as `ConnectionId: 0`, `Owner: <Unknown>`."),
    ) for key, node in external.items()
        if isinstance(node, Mapping)
        and str(node.get("Type", "")).startswith("QB::ConnectedDataSource")
        and _properties(node).get("IsPlaceholder") is not True]


def _set_color_on_a_field(document: Mapping[str, Any]) -> List[Risk]:
    out = []
    for path, qbl_type, node in _nodes(document):
        if qbl_type != "QB::FormV2::Rule::Action::SetColor":
            continue
        target = _properties(node).get("Target")
        if isinstance(target, Mapping) and "FormV2Column" in target:
            continue
        out.append(Risk(
            code="CRT017",
            severity="error",
            symptom=TIMEOUT,
            location=f"{path}.Properties.Target",
            problem=("A FormV2 `SetColor` whose target is not a column. "
                     "The create hangs with no diagnostic."),
            fix=("Target a column - `!Ref {FormV2Page: ..., FormV2Section: ..., "
                 "FormV2Column: ...}` - which is what `SetColor` colours."),
        ))
    return out


_HOME_SECTIONS = ("MainSection", "Sidebar")
_WIDGET_SUFFIX = re.compile(r"_(-?\d+)$")


def _home_pages(document: Mapping[str, Any]) -> Iterator[Tuple[str, Mapping[str, Any]]]:
    for path, qbl_type, node in _nodes(document):
        if qbl_type == "QB::HomePage":
            yield path, node


def _home_rows(page: Mapping[str, Any]) -> Iterator[Tuple[str, str, Mapping[str, Any]]]:
    for section in _HOME_SECTIONS:
        for row_key, row in (page.get(section) or {}).items():
            if isinstance(row, Mapping):
                yield section, str(row_key), row


def _widget_ids_not_integers(document: Mapping[str, Any]) -> List[Risk]:
    out = []
    for page_path, page in _home_pages(document):
        for section, row_key, row in _home_rows(page):
            for key in (row.get("Widgets") or {}):
                if _WIDGET_SUFFIX.search(str(key)):
                    continue
                out.append(Risk(
                    code="CRT018",
                    severity="error",
                    symptom=RESOURCE_FAILURE,
                    location=f"{page_path}.{section}.{row_key}.Widgets.{key}",
                    problem=(f"Home page widget `{key}` does not end in a number. "
                             f"The platform reads the number after a widget's "
                             f"last underscore as its id; without one the whole "
                             f"create fails."),
                    fix=("Key the widget `$HomePageWidget_<n>` with a whole "
                         "number above 100, unique on the page."),
                ))
    return out


def _small_widget_ids_in_shared_rows(document: Mapping[str, Any]) -> List[Risk]:
    out = []
    for page_path, page in _home_pages(document):
        for section, row_key, row in _home_rows(page):
            widgets = list((row.get("Widgets") or {}))
            if len(widgets) < 2:
                continue
            for key in widgets:
                match = _WIDGET_SUFFIX.search(str(key))
                if not match or not 0 <= int(match.group(1)) <= 2:
                    continue
                out.append(Risk(
                    code="CRT019",
                    severity="warning",
                    symptom=SILENT,
                    location=f"{page_path}.{section}.{row_key}.Widgets.{key}",
                    problem=(f"Home page widget `{key}` shares a row and has a "
                             f"small id. A widget numbered 2 that opens a shared "
                             f"row is dropped by the create, and one numbered 1 "
                             f"after one numbered 0 goes the same way - with no "
                             f"warning, and an export that no longer has it."),
                    fix=("Renumber the page's widgets from 101 up, as the "
                         "compiler does. A PUT with the new keys is safe: it "
                         "replaces the layout and restores the widget."),
                ))
    return out


def _table_qualified_search_fields(document: Mapping[str, Any]) -> List[Risk]:
    out = []
    for path, qbl_type, node in _nodes(document):
        if qbl_type != "QB::HomePage::Widget::Field":
            continue
        target = _properties(node).get("TargetField")
        if not isinstance(target, Mapping) or "Table" not in target:
            continue
        out.append(Risk(
            code="CRT020",
            severity="error",
            symptom=RESOURCE_FAILURE,
            location=f"{path}.Properties.TargetField",
            problem=("A search widget's `TargetField` names its table. The "
                     "create fails."),
            fix=("Write the bare form, `TargetField: !Ref {Field: $Field_X}`; "
                 "the widget's `SearchTable` says which table it is."),
        ))
    return out


_BUILT_IN_FIELDS = frozenset({
    "QB::Field::RecordID", "QB::Field::DateCreated", "QB::Field::DateModified",
    "QB::Field::RecordOwner", "QB::Field::LastModifiedBy",
})


def _searchable(field: Mapping[str, Any]) -> bool:
    return _properties(field).get("IsSearchable") is True


def _tables_with_nothing_searchable(document: Mapping[str, Any]) -> List[Risk]:
    out = []
    for table_id, table in _tables(document):
        fields = [f for f in (table.get("Fields") or {}).values()
                  if isinstance(f, Mapping) and f.get("Type") not in _BUILT_IN_FIELDS]
        if not fields or any(_searchable(f) for f in fields):
            continue
        out.append(Risk(
            code="CRT021",
            severity="warning",
            symptom=SILENT,
            location=f"{table_id}.Fields",
            problem=(f"No field in {_name(table, table_id)} is searchable. A "
                     f"field is created unsearchable unless it says "
                     f"`IsSearchable: true`, so app search finds none of this "
                     f"table's records and no search widget can search it."),
            fix=("Set `IsSearchable: true` on the fields people look records up "
                 "by - names, titles, statuses, dates. A PUT applies it to an "
                 "app already deployed."),
        ))
    return out


def _search_widgets_over_unsearchable_fields(document: Mapping[str, Any]) -> List[Risk]:
    tables = dict(_tables(document))
    out = []
    for path, qbl_type, node in _nodes(document):
        if qbl_type != "QB::HomePage::Widget::Search":
            continue
        properties = _properties(node)
        if properties.get("SearchTarget") != "SelectedFields":
            continue
        search_table = properties.get("SearchTable")
        table = tables.get(search_table.get("Table")) if isinstance(search_table, Mapping) else None
        if not isinstance(table, Mapping):
            continue
        fields = table.get("Fields") or {}
        for child_key, child in (node.get("Fields") or {}).items():
            target = _properties(child).get("TargetField") if isinstance(child, Mapping) else None
            field_key = target.get("Field") if isinstance(target, Mapping) else None
            field = fields.get(field_key)
            if not isinstance(field, Mapping) or _searchable(field):
                continue
            out.append(Risk(
                code="CRT022",
                severity="warning",
                symptom=SILENT,
                location=f"{path}.Fields.{child_key}",
                problem=(f"The search widget searches {field_key}, which is not "
                         f"searchable. The widget renders \"You do not have "
                         f"access to the information in this widget\" for "
                         f"everyone, administrators included, and its field "
                         f"chooser is empty."),
                fix=f"Set `IsSearchable: true` on {field_key}.",
            ))
    return out


def _code_pages_not_create_proven(document: Mapping[str, Any]) -> List[Risk]:
    out = []
    for path, qbl_type, node in _nodes(document):
        if qbl_type != "QB::CodePage":
            continue
        code = _properties(node).get("RawCode")
        if not isinstance(code, str) or "<!~db~[" not in code:
            continue
        out.append(Risk(
            code="CRT023",
            severity="note",
            symptom=SILENT,
            location=path,
            problem=("This code page names tables by `<!~db~[_DBID_...]~db~>` "
                     "token. A token that is not replaced on create leaves "
                     "the page addressing a table that does not exist."),
            fix=("After the create, export the app and check the page's RawCode "
                 "holds real dbids where the tokens were, then open the page from "
                 "its button."),
        ))
    return out


def _emails_without_send_options(document: Mapping[str, Any]) -> List[Risk]:
    out = []
    for path, qbl_type, node in _nodes(document):
        if qbl_type != "QB::CustomEmail" or "SendOptions" in _properties(node):
            continue
        out.append(Risk(
            code="CRT024",
            severity="error",
            symptom=UNPARSED,
            location=path,
            problem=("A custom email with no `SendOptions`. Quickbase's validation answers "
                     "`MissingProperty: Missing required property SendOptions`. "
                     "On an export, the likely cause is the app it came from: "
                     "an email created as `SendOptions: {TriggerType: "
                     "RecordChange}` with no `RecordEventTrigger` (CRT026) is "
                     "stored with no trigger events, never sends, and exports "
                     "with no `SendOptions` at all."),
            fix=("On an export, restore the trigger under the email's "
                 "`Properties`: `SendOptions` with `TriggerType: RecordChange`, "
                 "`RecordEventTrigger` (some of `Add`, `Modify`, `Delete`) and, "
                 "if it watches particular fields, `Fields` as `!Ref`s. The "
                 "export holds none of it - take it from what the email is "
                 "meant to do, or fix the email in the source app (pick its "
                 "trigger events in the email's settings) and export again. "
                 "Check its `Conditions` too: the trigger-less email lost "
                 "them on export, while an email with its trigger complete "
                 "kept them. For a new document, write the trigger in full in "
                 "the first place (CRT026)."),
        ))
    return out


def _record_change_emails_without_events(document: Mapping[str, Any]) -> List[Risk]:
    out = []
    for path, qbl_type, node in _nodes(document):
        if qbl_type != "QB::CustomEmail":
            continue
        options = _properties(node).get("SendOptions")
        if not isinstance(options, Mapping) or options.get("TriggerType") != "RecordChange":
            continue
        if options.get("RecordEventTrigger"):
            continue
        out.append(Risk(
            code="CRT026",
            severity="error",
            symptom=SILENT,
            location=path,
            problem=("A `RecordChange` email with no `RecordEventTrigger`. The "
                     "create accepts it and stores an email with no trigger "
                     "events: it never sends, nothing reports it, and the app's "
                     "export then leaves `SendOptions` out entirely, so a copy "
                     "made from that export is refused (CRT024)."),
            fix=("Add `RecordEventTrigger` under `SendOptions`, listing the "
                 "events that send it from `Add`, `Modify` and `Delete`, and "
                 "`Fields` (`!Ref`s) if it should send only when particular "
                 "fields change. In a spec: `record_events` and "
                 "`trigger_fields` on the email."),
        ))
    return out


def _pipeline_names_from_parameters(document: Mapping[str, Any]) -> List[Risk]:
    out = []
    for path, qbl_type, node in _nodes(document):
        if qbl_type != "QB::Pipeline":
            continue
        name = _properties(node).get("Name")
        if not (isinstance(name, Mapping) and tag_of(name) == "Var"):
            continue
        parameter = name.get("Name", "")
        out.append(Risk(
            code="CRT025",
            severity="error",
            symptom=UNPARSED,
            location=path,
            problem=(f"This pipeline's `Name` is `!Var {parameter}`, as every "
                     "export writes it. Quickbase's validation answers **HTTP 500** - no "
                     "findings, no message - whenever any pipeline in the "
                     "document is named this way, so the platform gate cannot "
                     "speak for the document at all. A 500 here is not an "
                     "outage."),
            fix=("Write the pipeline's name as a literal string: replace the "
                 f"`!Var` with the `Value` of `{parameter}` in "
                 "`ParameterDefinitions` (or the trailing `Parameters` "
                 "document, which wins). Only the pipeline's `Name` needs it; "
                 "the definition and every other `!Var` can stay."),
        ))
    return out


CHECKS = (
    _quoted_version,
    _uncreatable_charts,
    _search_widget_without_a_table,
    _kanban_without_columns,
    _set_color_on_a_field,
    _widget_ids_not_integers,
    _table_qualified_search_fields,
    _pipeline_selectors,
    _pipeline_steps_without_a_table,
    _connected_tables_without_a_schedule,
    _unknown_table_icons,
    _address_id_blocks,
    _update_triggers_without_trigger_fields,
    _placeholder_channel_accounts,
    _connected_schedules_at_minute_zero,
    _pipelines_are_created_off,
    _connected_tables_arrive_as_placeholders,
    _small_widget_ids_in_shared_rows,
    _tables_with_nothing_searchable,
    _search_widgets_over_unsearchable_fields,
    _thin_nodes,
    _forward_formula_references,
    _code_pages_not_create_proven,
    _emails_without_send_options,
    _pipeline_names_from_parameters,
    _record_change_emails_without_events,
)


def create_risks(document: Mapping[str, Any], *,
                 symptom: Optional[str] = None) -> List[Risk]:
    if symptom is not None and symptom not in SYMPTOMS:
        raise ValueError(f"unknown symptom {symptom!r}; expected one of "
                         f"{', '.join(SYMPTOMS)}")

    risks: List[Risk] = []
    for check in CHECKS:
        risks.extend(replace(risk, evidence=_EVIDENCE_BY_CODE.get(risk.code, ""))
                     for risk in check(document))
    if symptom is not None:
        risks = [risk for risk in risks if risk.symptom == symptom]
    return risks


@dataclass(frozen=True)
class Diagnosis:

    pattern: str
    means: str
    next_step: str
    symptom: str


PLATFORM_MESSAGES: Tuple[Diagnosis, ...] = (
    Diagnosis(
        pattern=r"failure in creating one of the resources",
        means=("A resource-level failure. The message names nothing - not the "
               "type, not the logical ID, not the property."),
        next_step=("Do not read the document looking for it. Narrow it down "
                   "with a ladder of *complete* applications: strip to a floor of "
                   "tables, fields, relationships, forms and roles, confirm "
                   "that floor creates, then add one family per rung. A common "
                   "cause of this exact message is a Search widget with no "
                   "`SearchTable` (CRT002)."),
        symptom=RESOURCE_FAILURE,
    ),
    Diagnosis(
        pattern=r"The provided YAML has syntax errors",
        means=("`Unparsed`. This does **not** mean the YAML is malformed - it is "
               "what the platform returns whenever its typed deserialiser "
               "raises, on a document `yaml.safe_load` parses without "
               "complaint. It names no line, no property and no type, and it is "
               "document-wide, so one bad node makes every other result in the "
               "same submission unreadable."),
        next_step=("Check the two known causes first: a quoted `Version` "
                   "(CRT005) and a chart's `DataDetails.DataAxis.Data`. Then "
                   "narrow the document down by halves - there is no location "
                   "in the response to work from."),
        symptom=UNPARSED,
    ),
    Diagnosis(
        pattern=r"\bHTTP 500\b|\b500 Internal Server Error\b|status(?: code)?:? 500\b",
        means=("Quickbase's validation answered HTTP 500 with no findings. On a "
               "document exported from Quickbase the known cause is a pipeline "
               "whose `Name` is `!Var` (CRT025): any one of them is enough, and "
               "the same document with literal pipeline names checks cleanly."),
        next_step=("Write every pipeline's `Name` as a literal (CRT025) and "
                   "run the check again before treating it as an outage."),
        symptom=UNPARSED,
    ),
    Diagnosis(
        pattern=r"Internal server error",
        means=("Usually seen beside the resource-level failure above rather than "
               "alone. It says nothing on its own."),
        next_step="Read whatever accompanies it; if nothing does, narrow the document down by halves.",
        symptom=RESOURCE_FAILURE,
    ),
    Diagnosis(
        pattern=r"MissingProperty",
        means=("A property the type genuinely requires is absent. This is the "
               "most actionable answer the platform gives - it names the "
               "property, the logical ID and the line."),
        next_step="Add the named property at the named node.",
        symptom=UNPARSED,
    ),
    Diagnosis(
        pattern=r"ExtraProperty",
        means=("A **warning**. The property is unnecessary for this type and "
               "will be removed. It does not block a deployment, and on a "
               "migrated legacy form a crop of these is expected: legacy writes "
               "`Required` and `ReadOnly` on every element including the field "
               "kinds that refuse them."),
        next_step=("Remove it if it was not intended. Otherwise ignore it, and "
                   "do not report it beside errors as though it were one."),
        symptom=SILENT,
    ),
    Diagnosis(
        pattern=r"BadProperty(?!WrongReferenceType)",
        means=("**The property name is fine and the value is wrong.** The message "
               "names the property, which reads as an unsupported name, but "
               "it is not one."),
        next_step=("Check the value against the domain for that property, not "
                   "the spelling of the name. One bad value can cascade - a bad "
                   "`RoleDefaults.Everyone.Mobile` value draws many errors and "
                   "drops every role's form assignment."),
        symptom=UNPARSED,
    ),
    Diagnosis(
        pattern=r"BadPropertyWrongReferenceType",
        means=("A reference resolves to the wrong kind of thing. On a form, "
               "`refers to a deleted or changed report or chart` usually means "
               "an embedded view whose report-link field is not wired: the "
               "field and the element that embeds a view through it are only "
               "usable together."),
        next_step=("Wire the `ReportLink` field's `Source`, `Target` table and "
                   "`Target` field, or remove the embedded view."),
        symptom=BUILDER,
    ),
    Diagnosis(
        pattern=r"NodeRemoved",
        means=("A **warning**, and the most dangerous one here. The platform did "
               "not recognise the node's type, so it dropped it - and then "
               "deployed successfully. The application comes out missing the "
               "object with nothing reported as an error."),
        next_step=("Correct the type name. Do not respond by filling in more "
                   "properties: the node is not being rejected for its shape."),
        symptom=SILENT,
    ),
    Diagnosis(
        pattern=r"UnstableConfiguration",
        means=("Non-fatal on create. The common one is a summary field whose "
               "`DisplayType` disagrees with the type it summarises."),
        next_step=("Worth fixing and not worth blocking on. Say plainly that it "
                   "is not the reason a create failed."),
        symptom=SILENT,
    ),
    Diagnosis(
        pattern=r"Unsupported node type",
        means="The type name is not one this version of QBL defines.",
        next_step=("Correct it. If the type is real and recent, check the "
                   "document's `Version` - the platform accepts 0.7, 0.12, "
                   "0.14 and 0.15 and refuses 0.13 and 0.16. The 41 pipeline "
                   "channel steps added in 0.15, `QB::PipelineStep::Jira` and "
                   "the rest, draw exactly this at 0.14."),
        symptom=UNPARSED,
    ),
    Diagnosis(
        pattern=r"Version .* is not supported",
        means=("The document's `Version` is one the platform refuses. Accepted: "
               "0.7, 0.12, 0.14, 0.15. Refused: 0.1, 0.8, 0.9, 0.11, 0.13, 0.16 "
               "- so the rule is not \"anything older\"."),
        next_step=("Set `Version` to 0.15, the current version. Moving a document to 0.15 "
                   "renames one thing: a Scatter3D chart's `XAxis` must become "
                   "`ZAxis`."),
        symptom=UNPARSED,
    ),
    Diagnosis(
        pattern=r"Failed to write pipeline schemas",
        means=("A pipeline the platform could not build, and the whole solution "
               "is refused with it - the application too. Only a create "
               "reads pipeline step bodies. The detail after `failed with the following "
               "details` names the step and the problem; the known one is an "
               "invalid `Selector`."),
        next_step="Correct what the detail names (CRT009 for a selector).",
        symptom=RESOURCE_FAILURE,
    ),
    Diagnosis(
        pattern=r"placeholder account",
        means=("A **warning**: the pipeline was created on a placeholder "
               "Quickbase account and will not run until a builder reconnects "
               "it."),
        next_step=("Declare the account `AccountType: tokenless`, `Alias: "
                   "realm-default-account` (CRT012) and PUT again."),
        symptom=SILENT,
    ),
    Diagnosis(
        pattern=r"PipelineStepWarning.*required field",
        means=("A **warning** naming the data sources a pipeline step lacks. "
               "The step is created and does nothing; for `app,table` on an "
               "action, its `Inputs` were deleted on the way in."),
        next_step=("Add the named data sources to the step's `InputsMeta` "
                   "(CRT010 for a table, CRT011 for `trigger_fields`)."),
        symptom=SILENT,
    ),
    Diagnosis(
        pattern=r"At least one field must be set",
        means=("A pipeline `update` step writes no field the step it targets "
               "exports. An update takes its fields from that step's "
               "`export_fields`, not from an `InputsMeta` of its own."),
        next_step=("Add every field the update writes to the target step's "
                   "`export_fields`."),
        symptom=SILENT,
    ),
    Diagnosis(
        pattern=r"InvalidHexColor",
        means="A colour property is not a hex colour.",
        next_step="Write it as `#RRGGBB`.",
        symptom=UNPARSED,
    ),
    Diagnosis(
        pattern=r"Only unique fields are allowed to be used as refreshed keys",
        means=("A connected table's refresh key names a field that is not "
               "unique."),
        next_step="Set `Unique: true` on that field, or key on a different one.",
        symptom=UNPARSED,
    ),
    Diagnosis(
        pattern=r"will not do anything as it has no actions",
        means=("A rule whose `RunOn` is `RecordSave` with no `Change` or "
               "`AbortSave` action. A warning; the rule simply never fires."),
        next_step=("Give the rule a saving action, or set `RunOn` to "
                   "`RecordOpenSaveOrChange`."),
        symptom=SILENT,
    ),
    Diagnosis(
        pattern=r"must have a related QB::Field::Address",
        means=("An address subfield without its parent. The platform refuses a "
               "bare `QB::Field::Address` and refuses each subfield on its own: "
               "neither half exists without the other."),
        next_step="Emit the parent and all six subfields together (see CRT006).",
        symptom=UNPARSED,
    ),
    Diagnosis(
        pattern=r"Exporting dashboards failed|DashboardGroup data for app could not be retrieved",
        means=("A dashboard was created that the dashboard service cannot read "
               "back. The create said nothing; the export fails, and the "
               "dashboard renders \"500 ERROR, Quickbase is temporarily "
               "unavailable\" to anyone it opens for. Seen with a `Kpi` widget "
               "missing `KpiType` and `Report`, and a dashboard `Search` widget "
               "missing any of `SearchType`, `ResultsView` or `BackgroundColor`."),
        next_step=("Run the offline layers over the document that was sent: "
                   "every dashboard widget property they call required is one "
                   "the dashboard needs. A PUT of the corrected document "
                   "repairs the app."),
        symptom=SILENT,
    ),
    Diagnosis(
        pattern=r"UNEXPECTED ERROR|Something went wrong",
        means=("Shown by a dashboard whose widgets the page cannot draw, though "
               "the app exports cleanly. Seen with the `Button` kinds missing "
               "`Alignment`/`OpenInNewWindow`, a `Spacer` without `DividerType`, "
               "and a bare `RichText` or `WebPage` widget."),
        next_step=("Check the dashboard's widgets against the offline layers' "
                   "required properties."),
        symptom=SILENT,
    ),
)


def classify_platform_error(text: str) -> List[Diagnosis]:
    if not text:
        return []
    found = []
    for diagnosis in PLATFORM_MESSAGES:
        if re.search(diagnosis.pattern, text, re.IGNORECASE):
            found.append(diagnosis)
    return found


TIMED_OUT_WITH_NO_MESSAGE = (
    "A create that hangs with no diagnostic names nothing to work from. Every known cause is a node the platform cannot "
    "build from rather than one it refuses to parse: an uncreatable chart kind "
    "(CRT001), a kanban with no columns (CRT003), a Search widget with no table "
    "(CRT002), a two-property `EmbeddedView`, a mis-numbered address block "
    "(CRT006). Check those, then narrow it down with a ladder of complete applications - "
    "a hang means \"this document\", not \"this kind\", and reading a whole "
    "document for it does not work."
)


__all__ = [
    "BUILDER",
    "CHECKS",
    "Diagnosis",
    "PLATFORM_MESSAGES",
    "RESOURCE_FAILURE",
    "Risk",
    "SILENT",
    "SYMPTOMS",
    "THIN_NODES",
    "TIMED_OUT_WITH_NO_MESSAGE",
    "TIMEOUT",
    "UNPARSED",
    "classify_platform_error",
    "create_risks",
]
