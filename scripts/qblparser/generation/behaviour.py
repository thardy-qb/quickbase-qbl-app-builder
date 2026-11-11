from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Set, Tuple

from qblparser.utils.parameters import build_parameter_map, resolve_parameters

from .compiler import PIPELINE_FILTER_OPERATORS

BHV_CODES = tuple(f"BHV{n:03d}" for n in range(1, 18))

_AUDIT_TABLE = re.compile(r"\baudit\s*(log|trail|history|entries|events)\b|^audits?$",
                          re.IGNORECASE)
_HISTORY_TABLE = re.compile(r"\b(change|interface|event|activity|transaction)\s*logs?\b"
                            r"|\b(change|status|approval)\s*history\b", re.IGNORECASE)
_SETTINGS_TABLE = re.compile(r"\b(settings?|config(uration)?|parameters?)\b", re.IGNORECASE)
_ACTIVE_LABEL = re.compile(r"^(is\s+)?active$", re.IGNORECASE)
_QUICKBASE_HOST = re.compile(r"https?://([A-Za-z0-9-]+)\.quickbase\.com", re.IGNORECASE)
_SHARED_HOSTS = frozenset({"api", "images", "exchange-cdn", "cdn", "www", "help",
                           "community", "login", "developer", "resources", "static"})
_FORMULA_QUERY = re.compile(r"\bGet(Records|FieldValues|Record)\s*\(", re.IGNORECASE)
_SELF_QUERY = re.compile(r"\{\s*'?3'?\s*\.\s*EX\s*\.\s*'?\"\s*&\s*\[Record ID#\]",
                         re.IGNORECASE)
_DATE_WORDS = ("day", "date", "week", "month", "year", "before", "after",
               "within", "during", "between")


def pipeline_key(label: str) -> str:
    if label in ("Record ID#", "Record ID"):
        return "id"
    return re.sub(r"[^0-9a-z]+", "_", label.lower()).strip("_")


def input_key(label: str) -> str:
    return "_".join(part.capitalize() for part in pipeline_key(label).split("_"))


def _props(node: Any) -> Mapping[str, Any]:
    properties = node.get("Properties") if isinstance(node, Mapping) else None
    return properties if isinstance(properties, Mapping) else {}


def _refs(node: Any, key: str) -> Iterator[str]:
    if isinstance(node, Mapping):
        for name, value in node.items():
            if name == key and isinstance(value, str):
                yield value
            else:
                yield from _refs(value, key)
    elif isinstance(node, list):
        for value in node:
            yield from _refs(value, key)


def _strings(node: Any, path: str = "") -> Iterator[Tuple[str, str]]:
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, Mapping):
        for name, value in node.items():
            yield from _strings(value, f"{path}.{name}" if path else str(name))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _strings(value, f"{path}[{index}]")


def _finding(code: str, severity: str, location: str, problem: str, fix: str
             ) -> Dict[str, Any]:
    return {"Code": code, "Severity": severity, "Problem": problem,
            "Location": location, "Fix": fix}


@dataclass
class _Field:
    key: str
    id: Any
    label: str
    type: str
    formula: str = ""


@dataclass
class _Table:
    key: str
    name: str
    node: Mapping[str, Any]
    fields: Dict[str, _Field] = field(default_factory=dict)

    def by_label(self, label: str) -> Optional[_Field]:
        return next((f for f in self.fields.values() if f.label == label), None)

    def by_pipeline_key(self) -> Dict[str, _Field]:
        return {pipeline_key(f.label): f for f in self.fields.values()}


@dataclass
class _Step:
    pipeline: str
    path: str
    node: Mapping[str, Any]
    within: Tuple[str, ...]
    table: Optional[str] = None

    @property
    def properties(self) -> Mapping[str, Any]:
        return _props(self.node)

    @property
    def channel(self) -> Mapping[str, Any]:
        channel = self.properties.get("Channel")
        return channel if isinstance(channel, Mapping) else {}

    @property
    def selector(self) -> str:
        return str(self.channel.get("Selector") or "")

    @property
    def step_id(self) -> str:
        return str(self.properties.get("Id") or "")

    @property
    def name(self) -> str:
        return str(self.properties.get("Name") or self.step_id or self.node.get("Type"))


class _App:
    def __init__(self, document: Mapping[str, Any]):
        parameters = build_parameter_map(document)
        self.document = resolve_parameters(document, parameters) if parameters else document
        resources = self.document.get("Resources") or {}
        self.app = next((node for node in resources.values() if isinstance(node, Mapping)
                         and node.get("Type") == "QB::Application"), {})
        self.tables: Dict[str, _Table] = {}
        for key, node in (self.app.get("Tables") or {}).items():
            table = _Table(key, str(_props(node).get("Name") or key), node)
            for field_key, item in (node.get("Fields") or {}).items():
                label = _props(item).get("Label")
                if isinstance(label, str):
                    table.fields[field_key] = _Field(
                        field_key, item.get("Id"), label, str(item.get("Type") or ""),
                        str(_props(item).get("Formula") or ""))
            self.tables[key] = table
        self.roles = {key: _props(role) for key, role in (self.app.get("Roles") or {}).items()}
        self.pipelines = [(key, node) for key, node in resources.items()
                          if isinstance(node, Mapping) and node.get("Type") == "QB::Pipeline"]
        self.accounts = {key: _props(node) for key, node in resources.items()
                         if isinstance(node, Mapping)
                         and node.get("Type") == "QB::PipelineChannelAccount"}
        self.steps: List[_Step] = []
        for key, node in self.pipelines:
            self._walk(str(_props(node).get("Name") or key), key, node.get("Steps") or [], ())
        by_id = {(step.pipeline, step.step_id): step for step in self.steps if step.step_id}
        for step in self.steps:
            if step.table is None and step.selector == "update":
                target = (step.properties.get("Target") or {}).get("StepId")
                source = by_id.get((step.pipeline, str(target)))
                if source is not None:
                    step.table = source.table

    def _walk(self, pipeline: str, path: str, steps: Sequence[Any],
              within: Tuple[str, ...]) -> None:
        for index, node in enumerate(steps):
            if not isinstance(node, Mapping):
                continue
            here = f"{path}.Steps[{index}]" if not within else f"{path}[{index}]"
            step = _Step(pipeline, here, node, within, self._step_table(node))
            self.steps.append(step)
            kind = str(node.get("Type") or "")
            if kind.endswith("::Loop"):
                self._walk(pipeline, f"{here}.Steps", node.get("Steps") or [],
                           within + ("loop",))
            for branch in ("Then", "Else"):
                if isinstance(node.get(branch), list):
                    self._walk(pipeline, f"{here}.{branch}", node[branch],
                               within + ("condition",))

    def _step_table(self, node: Mapping[str, Any]) -> Optional[str]:
        for meta in (node.get("InputsMeta") or {}).values():
            for source in ((meta or {}).get("PipelineStep_DataSources") or {}).values():
                if isinstance(source, Mapping) and _props(source).get("Name") == "table":
                    table = (_props(source).get("Table") or {})
                    key = table.get("Table") if isinstance(table, Mapping) else None
                    if isinstance(key, str):
                        return key
        return None

    def pipeline_schedule(self, name: str) -> Optional[str]:
        for _, node in self.pipelines:
            if _props(node).get("Name") == name:
                return _props(node).get("Crontab")
        return None

    def role_name(self, key: str) -> str:
        return str(self.roles.get(key, {}).get("Name") or key)

    def admin(self, key: str) -> bool:
        return bool(self.roles.get(key, {}).get("EditApp"))


def _step_location(step: _Step) -> str:
    return f"pipeline '{step.pipeline}', step '{step.name}'"


def _filters(node: Any) -> List[Mapping[str, Any]]:
    expression = (_props(node).get("Filters") or {}).get("Expression") if isinstance(
        _props(node).get("Filters"), Mapping) else None
    return [term for term in expression or []
            if isinstance(term, Mapping) and term.get("Type") == "relational-expression"]


def _empty_actions(app: _App) -> List[Dict[str, Any]]:
    out = []
    for step in app.steps:
        if step.properties.get("SubType") != "action":
            continue
        if step.properties.get("Inputs"):
            continue
        if step.selector in ("delete", "look_up", "search", "fetch_link"):
            continue
        quickbase = step.channel.get("Id") == "quickbase"
        if quickbase and step.table is None and not (
                step.selector == "update" and step.properties.get("Target")):
            continue
        out.append(_finding(
            "BHV001", "Error", _step_location(step),
            f"'{step.name}' is a {step.selector or 'pipeline'} step that writes no "
            f"values. It runs, succeeds and changes nothing"
            + (" - or creates a record with every field blank." if step.selector == "create"
               else "."),
            "Give it the field values it is there to write, or remove it."))
    return out


def _empty_conditions(app: _App) -> List[Dict[str, Any]]:
    return [_finding(
        "BHV002", "Error", _step_location(step),
        f"Condition '{step.name}' has no condition, so its branches do not depend "
        f"on anything.",
        "Give it the `Filters` it branches on, or replace it with the steps of the "
        "branch that should always run.")
        for step in app.steps
        if str(step.node.get("Type", "")).endswith("::Condition")
        and not _filters(step.node)]


def _broken_loops(app: _App) -> List[Dict[str, Any]]:
    out = []
    ids = {(step.pipeline, step.step_id) for step in app.steps if step.step_id}
    for step in app.steps:
        if not str(step.node.get("Type", "")).endswith("::Loop"):
            continue
        target = (step.properties.get("Target") or {}).get("StepId")
        if not step.node.get("Steps"):
            problem = f"Loop '{step.name}' has no steps inside it."
        elif target is None or (step.pipeline, str(target)) not in ids:
            problem = f"Loop '{step.name}' loops over step '{target}', which is not in the pipeline."
        else:
            continue
        out.append(_finding("BHV003", "Error", _step_location(step), problem,
                            "Point the loop at the search step whose records it "
                            "iterates, and put the per-record steps inside it."))
    return out


def _personal_connections(app: _App) -> List[Dict[str, Any]]:
    out = []
    for key, account in app.accounts.items():
        channel = str(account.get("Channel") or "")
        if channel in ("", "quickbase"):
            continue
        users = sorted({step.pipeline for step in app.steps
                        if key in _refs(step.node, "PipelineChannelAccount")})
        out.append(_finding(
            "BHV005", "Warning", key,
            f"Pipeline step(s) in {', '.join(users) or 'this solution'} use a "
            f"{channel} connection ('{account.get('Alias', '')}'). It runs as the "
            f"person who connected it: their mailbox sends, and it stops when "
            f"they leave or their authorisation lapses.",
            "Connect a shared or service account for the channel, or use a "
            "Quickbase custom email where one will do."))
    return out


def _date_bounded(app: _App, search: _Step) -> bool:
    table = app.tables.get(search.table or "")
    fields = table.by_pipeline_key() if table else {}
    for term in _filters(search.node):
        operator = str(term.get("Operator") or "").lower()
        value = str(term.get("Value") or "")
        item = fields.get(str(term.get("Field") or ""))
        if any(word in operator for word in _DATE_WORDS) or "time." in value:
            return True
        if item is not None and "Date" in item.type:
            return True
    return False


def _repeated_sends(app: _App) -> List[Dict[str, Any]]:
    out = []
    for pipeline in {step.pipeline for step in app.steps}:
        if not app.pipeline_schedule(pipeline):
            continue
        steps = [step for step in app.steps if step.pipeline == pipeline]
        searches = {step.step_id: step for step in steps if step.selector == "search"}
        for loop in steps:
            if not str(loop.node.get("Type", "")).endswith("::Loop"):
                continue
            target = str((loop.properties.get("Target") or {}).get("StepId"))
            search = searches.get(target)
            if search is None:
                continue
            inside = [step for step in steps if step.path.startswith(loop.path + ".")]
            sends = [step for step in inside
                     if step.channel.get("Id") not in (None, "quickbase")
                     and "send" in step.selector]
            if not sends:
                continue
            marks = [step for step in inside if step.selector == "update"
                     and str((step.properties.get("Target") or {}).get("StepId")) == target]
            if marks or _date_bounded(app, search):
                continue
            out.append(_finding(
                "BHV007", "Warning", _step_location(search),
                f"'{pipeline}' runs on a schedule and sends "
                f"{', '.join(repr(s.name) for s in sends)} for every record "
                f"'{search.name}' finds. Its filter has no date bound and nothing "
                f"marks a record once it has been sent, so every record still "
                f"matching is sent again on every run - including old ones.",
                "Bound the search to the period the notice is about (the week "
                "just ended, the last day), or set a sent date on each record and "
                "filter on it."))
    return out


def _empty_runs(app: _App) -> List[Dict[str, Any]]:
    out = []
    for pipeline in {step.pipeline for step in app.steps}:
        if not app.pipeline_schedule(pipeline):
            continue
        steps = [step for step in app.steps if step.pipeline == pipeline]
        if not any(step.selector == "search" for step in steps):
            continue
        for step in steps:
            if step.selector == "create" and not step.within:
                out.append(_finding(
                    "BHV008", "Warning", _step_location(step),
                    f"'{pipeline}' runs on a schedule and creates a record with "
                    f"'{step.name}' on every run, whether its search found "
                    f"anything or not.",
                    "Put the create behind a condition on the search finding "
                    "something, or accept - and say - that empty runs are logged."))
    return out


_CREATE_VERB = re.compile(
    r"^\s*(?:create|add|insert|log|write|record|make)\s+(?:(?:an?|the|new)\s+)*(.+)$",
    re.IGNORECASE)


def _misnamed_steps(app: _App) -> List[Dict[str, Any]]:
    def claimed(name: str) -> Optional[str]:
        match = _CREATE_VERB.match(name)
        if not match:
            return None
        rest = match.group(1).lower()
        best = None
        for table in app.tables.values():
            forms = [table.name] + ([table.name[:-1]] if table.name.endswith("s") else [])
            for form in forms:
                if re.match(rf"{re.escape(form.lower())}(?![a-z])", rest):
                    if best is None or len(form) > len(best[1]):
                        best = (table.key, form)
        return best[0] if best else None

    out = []
    for step in app.steps:
        if step.selector != "create" or step.table not in app.tables:
            continue
        claim = claimed(step.name)
        if claim is None or claim == step.table:
            continue
        out.append(_finding(
            "BHV015", "Warning", _step_location(step),
            f"'{step.name}' says it creates a record in '{app.tables[claim].name}', "
            f"and creates it in '{app.tables[step.table].name}'.",
            "Point the step at the table its name says, or rename it to say what "
            "it does."))
    return out


def _orphan_state(app: _App) -> List[Dict[str, Any]]:
    formulas = [f.formula for table in app.tables.values() for f in table.fields.values()
                if f.formula]
    criteria = list(_criteria_strings(app))
    pipeline_reads: Dict[Optional[str], Set[str]] = {}
    pipeline_writes: Dict[Optional[str], Set[str]] = {}
    for step in app.steps:
        for term in _filters(step.node):
            pipeline_reads.setdefault(step.table, set()).add(str(term.get("Field")))
        for key in (step.properties.get("Inputs") or {}):
            pipeline_writes.setdefault(step.table, set()).add(str(key))
    out = []
    for table in app.tables.values():
        on_forms = set(_refs(table.node.get("Forms") or {}, "Field"))
        rule_targets = {key for typed in _typed(table.node.get("Forms") or {})
                        if typed["Type"].endswith("::Action::Change")
                        for key in _refs(_props(typed).get("Field"), "Field")}
        for item in table.fields.values():
            if item.formula or not (item.type.endswith("TextMultipleChoice")
                                    or item.type.endswith("::Checkbox")):
                continue
            reads = (
                any(f"[{item.label}]" in formula for formula in formulas)
                or any(f"'{item.id}'." in text or f"{{{item.id}." in text
                       for text in criteria)
                or pipeline_key(item.label) in pipeline_reads.get(table.key, set()))
            if not reads:
                continue
            written = (
                item.key in on_forms or item.key in rule_targets
                or input_key(item.label) in pipeline_writes.get(table.key, set())
                or any(f"_fid_{item.id}=" in formula for formula in formulas))
            if written:
                continue
            out.append(_finding(
                "BHV006", "Warning", f"{table.name}/{item.label}",
                f"'{item.label}' on '{table.name}' is read by formulas, access rules "
                f"or pipelines, and nothing sets it: it is on no form, no form rule "
                f"or button writes it, and no pipeline does. It keeps its default "
                f"unless somebody edits it in a grid.",
                "Set it where the state actually changes - a pipeline on the "
                "event, a form rule, a button - or put it on the form where the "
                "person who decides it will see it."))
    return out


def _typed(node: Any) -> Iterator[Mapping[str, Any]]:
    if isinstance(node, Mapping):
        if isinstance(node.get("Type"), str):
            yield node
        for key, value in node.items():
            if key != "Type":
                yield from _typed(value)
    elif isinstance(node, list):
        for value in node:
            yield from _typed(value)


def _criteria_strings(app: _App) -> Iterator[str]:
    for table in app.tables.values():
        for permission in (_props(table.node).get("RolePermissions") or {}).values():
            for name in ("CanViewRecords", "CanModifyRecords"):
                value = (permission or {}).get(name)
                if isinstance(value, Mapping) and value.get("CustomAccessCriteria"):
                    yield str(value["CustomAccessCriteria"])
        for container in ("Reports", "Charts"):
            for report in (table.node.get(container) or {}).values():
                criteria = (_props(report).get("Filters") or {})
                if isinstance(criteria, Mapping) and isinstance(criteria.get("Criteria"), str):
                    yield criteria["Criteria"]


def _access(permission: Mapping[str, Any], name: str) -> str:
    value = (permission or {}).get(name)
    return str(value.get("When") if isinstance(value, Mapping) else value or "")


def _role_access(app: _App) -> List[Dict[str, Any]]:
    out = []
    for table in app.tables.values():
        audit = bool(_AUDIT_TABLE.search(table.name) or _HISTORY_TABLE.search(table.name))
        settings = bool(_SETTINGS_TABLE.search(table.name))
        if not (audit or settings):
            continue
        for role_key, permission in (_props(table.node).get("RolePermissions") or {}).items():
            if app.admin(role_key) or not isinstance(permission, Mapping):
                continue
            role = app.role_name(role_key)
            modify = _access(permission, "CanModifyRecords") in ("Always", "CustomRule")
            delete = bool(permission.get("CanDeleteRecords"))
            if audit and (modify or delete):
                out.append(_finding(
                    "BHV009", "Warning", f"{table.name}/{role}",
                    f"Role '{role}' can {' and '.join(w for w, on in (('edit', modify), ('delete', delete)) if on)} "
                    f"records in '{table.name}'. A record of what happened is only "
                    f"evidence if nobody it describes can change it.",
                    "Give non-admin roles add and view at most on audit and log "
                    "tables; let pipelines write them."))
            if settings and (modify or delete or permission.get("CanAddRecords")):
                out.append(_finding(
                    "BHV010", "Warning", f"{table.name}/{role}",
                    f"Role '{role}' can change '{table.name}', which configures "
                    f"how the application behaves for everyone.",
                    "Leave settings to the administrator role, or say why this "
                    "role owns them."))
    return out


def _empty_default_forms(app: _App) -> List[Dict[str, Any]]:
    out = []
    for table in app.tables.values():
        forms = table.node.get("Forms") or {}
        nodes = forms.get("Resources") or {}
        defaults = (_props(forms).get("RoleDefaults") or {})
        used = {key for key in _refs(defaults, "FormV2")} | {key for key in _refs(defaults, "Form")}
        for key in sorted(used):
            form = nodes.get(key)
            if not isinstance(form, Mapping):
                continue
            if any("::Element" in typed["Type"] for typed in _typed(form)):
                continue
            out.append(_finding(
                "BHV011", "Error", f"{table.name}/{_props(form).get('Name', key)}",
                f"'{table.name}' opens records on '{_props(form).get('Name', key)}', "
                f"which has nothing on it. Every record of the table opens blank.",
                "Point the role defaults at a form with the table's fields, or "
                "fill this one."))
    return out


def _formula_queries(app: _App) -> List[Dict[str, Any]]:
    out = []
    for table in app.tables.values():
        queries = [f.label for f in table.fields.values() if _FORMULA_QUERY.search(f.formula)]
        rule = (_props(table.node).get("CustomDataRules") or {})
        rule_text = str(rule.get("Formula") or "") if isinstance(rule, Mapping) else ""
        if _FORMULA_QUERY.search(rule_text):
            queries.append("the table's data rule")
        selves = [f.label for f in table.fields.values() if _SELF_QUERY.search(f.formula)]
        if len(queries) < 3 and not selves:
            continue
        out.append(_finding(
            "BHV012", "Warning", table.name,
            f"'{table.name}' runs {len(queries)} formula quer"
            f"{'y' if len(queries) == 1 else 'ies'} ({', '.join(queries[:6])}"
            f"{', ...' if len(queries) > 6 else ''})"
            + (f"; {', '.join(selves)} quer{'y' if len(selves) == 1 else 'ies'} "
               f"the record's own row to compare with its saved value" if selves else "")
            + ". Each runs for every record a report shows or a save checks, which "
              "is the first thing to slow at volume.",
            "Prove it at the expected volume before relying on it; prefer a summary "
            "field or a stored value set by a pipeline where one will do."))
    return out


def _active_cascade(app: _App) -> List[Dict[str, Any]]:
    active = {key: next((f for f in table.fields.values()
                         if _ACTIVE_LABEL.match(f.label) and f.type.endswith("::Checkbox")
                         and not f.formula), None)
              for key, table in app.tables.items()}
    formulas = [f.formula for t in app.tables.values() for f in t.fields.values() if f.formula]
    criteria = list(_criteria_strings(app))
    pipeline_reads = {(step.table, str(term.get("Field")))
                      for step in app.steps for term in _filters(step.node)}

    def gates(table_key: str) -> bool:
        item = active.get(table_key)
        if item is None:
            return False
        return (any(f"[{item.label}]" in formula for formula in formulas)
                or any(f"'{item.id}'." in text or f"{{{item.id}." in text for text in criteria)
                or (table_key, pipeline_key(item.label)) in pipeline_reads)

    left: Dict[str, List[str]] = {}
    for child_key, child in app.tables.items():
        if not gates(child_key):
            continue
        for rel in (child.node.get("Relationships") or {}).values():
            if not isinstance(rel, Mapping) or rel.get("Type") != "QB::Relationship::Child":
                continue
            parent_key = (_props(rel).get("Parent") or {}).get("Table")
            if parent_key == child_key or not gates(parent_key):
                continue
            cascades = any(
                step.table == parent_key and step.selector == "on_update"
                and any(other.pipeline == step.pipeline and other.table == child_key
                        and other.selector in ("search", "update")
                        for other in app.steps)
                for step in app.steps)
            if not cascades and child.name not in left.setdefault(parent_key, []):
                left[parent_key].append(child.name)
    out = []
    for parent_key, children in left.items():
        if not children:
            continue
        parent = app.tables[parent_key]
        out.append(_finding(
            "BHV013", "Warning", parent.name,
            f"'{parent.name}' has '{active[parent_key].label}', and so "
            f"{'does its child' if len(children) == 1 else 'do its children'} "
            f"{', '.join(repr(c) for c in children)}. Nothing carries a "
            f"change in the parent's flag down, so deactivating a {parent.name} "
            f"record leaves its children active.",
            "Add a pipeline on the parent's change that updates its children, or a "
            "formula on each child that reads the parent's flag - or confirm they "
            "are meant to be independent."))
    return out


def _audit_coverage(app: _App) -> List[Dict[str, Any]]:
    audits = {key for key, table in app.tables.items() if _AUDIT_TABLE.search(table.name)}
    if not audits:
        return []
    audited = {step.table for step in app.steps
               if step.selector in ("on_update", "on_create", "on_new_event")
               and any(other.pipeline == step.pipeline and other.table in audits
                       and other.selector == "create" for other in app.steps)}
    out = []
    for key, table in app.tables.items():
        if key in audits or key in audited:
            continue
        statuses = [f.label for f in table.fields.values()
                    if "status" in f.label.lower() and not f.formula
                    and f.type.endswith("TextMultipleChoice")]
        if not statuses:
            continue
        out.append(_finding(
            "BHV014", "Warning", table.name,
            f"'{table.name}' changes {', '.join(repr(s) for s in statuses)}, and no "
            f"pipeline writes those changes to "
            f"{', '.join(repr(app.tables[a].name) for a in sorted(audits))}.",
            "Write them to the audit table on change, or confirm this table's "
            "history is not part of the audit."))
    return out


def _hostnames(app: _App) -> List[Dict[str, Any]]:
    found: Dict[str, List[str]] = {}
    for path, text in _strings(app.document.get("Resources") or {}):
        for match in _QUICKBASE_HOST.finditer(text):
            if match.group(1).lower() in _SHARED_HOSTS:
                continue
            found.setdefault(match.group(0).lower(), []).append(path)
    return [_finding(
        "BHV004", "Warning", paths[0],
        f"'{host}' is written into the application in {len(paths)} place(s). It "
        f"is right in one realm only, and wrong in every copy of the app made "
        f"anywhere else.",
        "Build the link from `URLRoot()` in a formula, or from a field holding "
        "the app's own link, so that it follows the app.")
        for host, paths in sorted(found.items())]


def _unsupported_operators(app: _App) -> List[Dict[str, Any]]:
    out = []
    for step in app.steps:
        for term in _filters(step.node):
            operator = term.get("Operator")
            if operator in PIPELINE_FILTER_OPERATORS or operator is None:
                continue
            out.append(_finding(
                "BHV016", "Warning", _step_location(step),
                f"'{step.name}' filters '{term.get('Field')}' with operator "
                f"'{operator}', which is not a known pipeline filter operator. If "
                f"Quickbase does not recognise it, the filter matches nothing and "
                f"the step never acts.",
                f"Use one of {', '.join(sorted(PIPELINE_FILTER_OPERATORS))}, or "
                f"build the step in the pipeline designer and export it to see the "
                f"operator it writes."))
    return out


def _scheduled_email_conditions(app: _App) -> List[Dict[str, Any]]:
    out = []
    for table in app.tables.values():
        for email in (table.node.get("Emails") or {}).values():
            send = (_props(email).get("SendOptions") or {})
            if send.get("TriggerType") == "Scheduled" and email.get("Conditions"):
                out.append(_finding(
                    "BHV017", "Warning", f"{table.name}/{_props(email).get('Name')}",
                    f"Scheduled email '{_props(email).get('Name')}' on '{table.name}' "
                    f"has conditions. The platform accepts them and drops them, so "
                    f"every record sends.",
                    "Gate who receives it instead: a User::Formula recipient that is "
                    "blank unless the record needs the email."))
    return out


CHECKS = (
    _unsupported_operators, _scheduled_email_conditions,
    _empty_actions, _empty_conditions, _broken_loops, _hostnames,
    _personal_connections, _orphan_state, _repeated_sends, _empty_runs,
    _role_access, _empty_default_forms, _formula_queries, _active_cascade,
    _audit_coverage, _misnamed_steps,
)


def check_behaviour(document: Mapping[str, Any]) -> List[Dict[str, Any]]:
    app = _App(document)
    findings: List[Dict[str, Any]] = []
    for check in CHECKS:
        findings.extend(check(app))
    order = {code: index for index, code in enumerate(BHV_CODES)}
    return sorted(findings, key=lambda f: order.get(f["Code"], 99))


__all__ = ["BHV_CODES", "check_behaviour"]
