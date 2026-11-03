from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

from qblparser.utils.parameters import build_parameter_map, resolve_parameters


CRITERION_STATUSES = ("built", "runtime", "deviation", "not_built", "out_of_scope")
_DEPARTURES = ("deviation", "not_built", "out_of_scope")
_MET = ("built", "runtime", "deviation")

DECISION_SOURCES = ("user", "requirements", "builder")

ARTIFACT_KINDS = {
    "table": False, "field": True, "report": True, "chart": True,
    "form": True, "form_rule": True, "data_rule": False, "permission": True,
    "email": True, "document_template": True, "relationship": True,
    "role": False, "page": False, "dashboard": False, "pipeline": False,
}

REQ_CODES = ("REQ000", "REQ001", "REQ002", "REQ003", "REQ004", "REQ005",
             "REQ006", "REQ007")
DEC_CODES = ("DEC001", "DEC002", "DEC003", "DEC004", "DEC005", "DEC006")


@dataclass
class CriterionSpec:

    id: str
    text: str = ""
    met_by: List[str] = field(default_factory=list)
    status: str = "built"
    note: str = ""
    confirmed_by: Optional[str] = None


@dataclass
class RequirementSpec:

    id: str
    title: str = ""
    text: str = ""
    criteria: List[CriterionSpec] = field(default_factory=list)
    met_by: List[str] = field(default_factory=list)
    status: str = "built"
    note: str = ""
    confirmed_by: Optional[str] = None
    priority: Optional[str] = None

    def units(self) -> List[CriterionSpec]:
        if self.criteria:
            return list(self.criteria)
        return [CriterionSpec(self.id, self.title or self.text, list(self.met_by),
                              self.status, self.note, self.confirmed_by)]


@dataclass
class DecisionSpec:

    id: str
    question: str
    choice: str
    source: str = "builder"
    must_confirm: bool = False
    confirmed_by: Optional[str] = None
    affects: List[str] = field(default_factory=list)
    criteria: List[str] = field(default_factory=list)
    rationale: str = ""

    @property
    def confirmed(self) -> bool:
        return bool(self.confirmed_by) or self.source == "user"


def _props(node: Any) -> Mapping[str, Any]:
    properties = node.get("Properties") if isinstance(node, Mapping) else None
    return properties if isinstance(properties, Mapping) else {}


def _untagged(value: Any, parameters: Mapping[str, Any]) -> Any:
    if (isinstance(value, Mapping) and set(value) == {"Name"}
            and value["Name"] in parameters):
        return parameters[value["Name"]]
    return value


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


class ArtifactIndex:

    def __init__(self, document: Mapping[str, Any]):
        parameters = build_parameter_map(document)
        if parameters:
            document = resolve_parameters(document, parameters)
        self.names: Dict[str, set] = {kind: set() for kind in ARTIFACT_KINDS}
        resources = document.get("Resources") or {}
        apps = [node for node in resources.values()
                if isinstance(node, Mapping) and node.get("Type") == "QB::Application"]
        role_names: Dict[str, str] = {}
        table_names: Dict[str, str] = {}
        for app in apps:
            for key, role in (app.get("Roles") or {}).items():
                name = _props(role).get("Name")
                if isinstance(name, str):
                    role_names[key] = name
                    self.names["role"].add(name)
            for key, table in (app.get("Tables") or {}).items():
                name = _props(table).get("Name")
                if isinstance(name, str):
                    table_names[key] = name
        for app in apps:
            for key, table in (app.get("Tables") or {}).items():
                self._table(table_names.get(key, key), table, role_names, table_names)
            pages = app.get("Pages") or {}
            for page in (pages.get("Resources") or {}).values():
                name = _props(page).get("Name")
                if not isinstance(name, str):
                    continue
                self.names["page"].add(name)
                if page.get("Type") == "QB::Dashboard":
                    self.names["dashboard"].add(name)
        for node in resources.values():
            if isinstance(node, Mapping) and node.get("Type") == "QB::Pipeline":
                name = _untagged(_props(node).get("Name"), parameters)
                if isinstance(name, str):
                    self.names["pipeline"].add(name)

    def _table(self, table: str, node: Mapping[str, Any],
               role_names: Mapping[str, str], table_names: Mapping[str, str]) -> None:
        self.names["table"].add(table)
        properties = _props(node)
        rules = properties.get("CustomDataRules")
        if isinstance(rules, Mapping) and str(rules.get("Formula") or "").strip():
            self.names["data_rule"].add(table)
        for role_key in (properties.get("RolePermissions") or {}):
            self.names["permission"].add(f"{table}/{role_names.get(role_key, role_key)}")
        for item in (node.get("Fields") or {}).values():
            label = _props(item).get("Label")
            if isinstance(label, str):
                self.names["field"].add(f"{table}/{label}")
        for kind, container in (("report", "Reports"), ("chart", "Charts"),
                                ("email", "Emails"),
                                ("document_template", "DocumentTemplates")):
            for item in (node.get(container) or {}).values():
                name = _props(item).get("Name")
                if isinstance(name, str):
                    self.names[kind].add(f"{table}/{name}")
        forms = node.get("Forms") or {}
        for form in (forms.get("Resources") or {}).values():
            name = _props(form).get("Name")
            if isinstance(name, str):
                self.names["form"].add(f"{table}/{name}")
            for typed in _typed(form):
                if "::Rule" in typed["Type"] and "::Rule::" not in typed["Type"]:
                    rule = _props(typed).get("Name")
                    if isinstance(rule, str):
                        self.names["form_rule"].add(f"{table}/{rule}")
        for rel in (node.get("Relationships") or {}).values():
            if not isinstance(rel, Mapping) or rel.get("Type") != "QB::Relationship::Child":
                continue
            parent = (_props(rel).get("Parent") or {}).get("Table")
            if isinstance(parent, str):
                self.names["relationship"].add(f"{table_names.get(parent, parent)}/{table}")

    def resolve(self, reference: str) -> Optional[str]:
        if not isinstance(reference, str) or ":" not in reference:
            return (f"'{reference}' is not a `kind:Name` reference; kinds are "
                    f"{', '.join(ARTIFACT_KINDS)}")
        kind, name = reference.split(":", 1)
        kind, name = kind.strip(), name.strip()
        if kind not in ARTIFACT_KINDS:
            return (f"'{reference}' names kind '{kind}'; kinds are "
                    f"{', '.join(ARTIFACT_KINDS)}")
        if ARTIFACT_KINDS[kind] and "/" not in name:
            return f"'{reference}' needs a table: `{kind}:<Table>/<Name>`"
        if name in self.names[kind]:
            return None
        if ARTIFACT_KINDS[kind]:
            table = name.split("/", 1)[0]
            if table not in self.names["table"]:
                return f"'{reference}': there is no table '{table}'"
        return f"'{reference}': no {kind.replace('_', ' ')} by that name"


def _finding(code: str, severity: str, location: str, problem: str, fix: str
             ) -> Dict[str, Any]:
    return {"Code": code, "Severity": severity, "Problem": problem,
            "Location": location, "Fix": fix}


def _units(spec: Any) -> Iterator[Tuple[RequirementSpec, CriterionSpec]]:
    for requirement in getattr(spec, "requirements", None) or []:
        for unit in requirement.units():
            yield requirement, unit


def check_requirements(spec: Any, document: Mapping[str, Any]) -> List[Dict[str, Any]]:
    requirements = getattr(spec, "requirements", None) or []
    if not requirements:
        return [_finding(
            "REQ000", "Warning", "requirements",
            "The spec states no requirements, so nothing connects this document "
            "to what was asked for. Every other check can pass a document that "
            "does half of it.",
            "Add the requirements to `AppSpec.requirements` - "
            "`build_qbl.py requirements <source.md>` drafts them from a stories "
            "document - and trace each acceptance criterion to what meets it.")]

    findings: List[Dict[str, Any]] = []
    index = ArtifactIndex(document)
    seen: Dict[str, int] = {}
    for requirement in requirements:
        seen[requirement.id] = seen.get(requirement.id, 0) + 1
        for criterion in requirement.criteria:
            seen[criterion.id] = seen.get(criterion.id, 0) + 1
    for duplicate in sorted(key for key, count in seen.items() if count > 1):
        findings.append(_finding(
            "REQ005", "Error", duplicate,
            f"'{duplicate}' is the id of more than one requirement or criterion, "
            f"so a trace to it is ambiguous.",
            "Give each requirement and criterion its own id."))

    for requirement, unit in _units(spec):
        if unit.status not in CRITERION_STATUSES:
            findings.append(_finding(
                "REQ003", "Error", unit.id,
                f"'{unit.id}' has status '{unit.status}'.",
                f"Use one of {', '.join(CRITERION_STATUSES)}."))
            continue
        if unit.status in _MET and not unit.met_by:
            findings.append(_finding(
                "REQ001", "Error", unit.id,
                f"'{unit.id}' ({_short(unit.text)}) is marked {unit.status} but "
                f"names nothing that meets it.",
                "Name the artifacts that meet it in `met_by`, or - if nothing "
                "does - mark it `not_built` with the reason and ask the person "
                "who owns the requirement to confirm."))
        for reference in unit.met_by:
            problem = index.resolve(reference)
            if problem:
                findings.append(_finding(
                    "REQ002", "Error", unit.id,
                    f"'{unit.id}' is traced to {problem}.",
                    "Correct the reference, or build what it names."))
        if unit.status == "runtime" and not unit.note.strip():
            findings.append(_finding(
                "REQ004", "Warning", unit.id,
                f"'{unit.id}' can only be proved at runtime and says nothing "
                f"about the test that would prove it.",
                "Put the test in `note`: the records to set up, the action, and "
                "what has to be true afterwards. The build report collects these "
                "into the runtime test plan."))
        if unit.status in _DEPARTURES and not unit.note.strip():
            findings.append(_finding(
                "REQ006", "Error", unit.id,
                f"'{unit.id}' is marked {unit.status} with no reason.",
                "Say in `note` what was built instead, or why nothing was, in "
                "words the requirement's owner can agree to or refuse."))
    return findings


def check_decisions(spec: Any, document: Mapping[str, Any]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    decisions = getattr(spec, "decisions", None) or []
    index = ArtifactIndex(document) if decisions or getattr(spec, "requirements", None) else None

    for decision in decisions:
        if decision.source not in DECISION_SOURCES:
            findings.append(_finding(
                "DEC005", "Error", decision.id,
                f"Decision '{decision.id}' has source '{decision.source}'.",
                f"Use one of {', '.join(DECISION_SOURCES)}."))
            continue
        if decision.source == "builder" and not decision.confirmed:
            findings.append(_finding(
                "DEC001", "Error", decision.id,
                f"Decision '{decision.id}' - {_short(decision.question)} - was made "
                f"by the builder ('{_short(decision.choice)}') and nobody has "
                f"confirmed it.",
                "Put the question and the choice to the person who owns the "
                "requirements, and record their answer in `confirmed_by`. If they "
                "decide differently, change the spec, not the record."))
        elif decision.must_confirm and not decision.confirmed:
            findings.append(_finding(
                "DEC002", "Error", decision.id,
                f"The requirements ask for decision '{decision.id}' - "
                f"{_short(decision.question)} - to be confirmed before building, "
                f"and it has not been.",
                "Ask, and record the answer in `confirmed_by`. The default the "
                "requirements suggest is not a confirmation of it."))
        for reference in decision.affects:
            problem = index.resolve(reference) if index else None
            if problem:
                findings.append(_finding(
                    "DEC006", "Error", decision.id,
                    f"Decision '{decision.id}' affects {problem}.",
                    "Correct the reference, or build what it names."))

    for requirement, unit in _units(spec):
        if unit.status in ("deviation", "not_built") and not unit.confirmed_by:
            findings.append(_finding(
                "DEC003", "Error", unit.id,
                f"'{unit.id}' ({_short(unit.text)}) is {unit.status.replace('_', ' ')} "
                f"and nobody but the builder has agreed to that.",
                "Put the departure and its reason to the requirement's owner and "
                "record their answer in `confirmed_by` - or build it as written."))

    covered = {reference for decision in decisions for reference in decision.affects}
    for reference, text in _assumptions(spec):
        if reference not in covered:
            findings.append(_finding(
                "DEC004", "Warning", reference,
                f"{reference} records an assumption ('{_short(text, 90)}') that no "
                f"decision covers, so nobody was asked about it.",
                "Record it as a `DecisionSpec` naming this artifact in `affects`, "
                "and confirm it - or drop the assumption."))
    return findings


_ASSUMPTION = re.compile(r"\bassum(?:e|ed|es|ing|ption|ptions)\b", re.IGNORECASE)


def _assumptions(spec: Any) -> Iterator[Tuple[str, str]]:
    for table in getattr(spec, "tables", None) or []:
        description = (getattr(table, "properties", None) or {}).get("Description")
        if isinstance(description, str) and _ASSUMPTION.search(description):
            yield f"table:{table.name}", description
        for item in table.fields:
            for text in (item.comments, item.help_text):
                if isinstance(text, str) and _ASSUMPTION.search(text):
                    yield f"field:{table.name}/{item.label}", text
                    break
        for report in table.reports:
            text = getattr(report, "description", None)
            if isinstance(text, str) and _ASSUMPTION.search(text):
                yield f"report:{table.name}/{report.name}", text
    for pipeline in getattr(spec, "pipelines", None) or []:
        if pipeline.description and _ASSUMPTION.search(pipeline.description):
            yield f"pipeline:{pipeline.name}", pipeline.description
    for role in getattr(spec, "roles", None) or []:
        if role.description and _ASSUMPTION.search(role.description):
            yield f"role:{role.name}", role.description


def check_deployed_trace(spec: Any, export: Mapping[str, Any]) -> List[Dict[str, Any]]:
    index = ArtifactIndex(export)
    findings = []
    for requirement, unit in _units(spec):
        for reference in unit.met_by:
            problem = index.resolve(reference)
            if problem:
                findings.append(_finding(
                    "REQ007", "Error", unit.id,
                    f"'{unit.id}' was traced to {reference}, and the deployed "
                    f"export has none: {problem}.",
                    "Compare the export with what was sent; the platform may have "
                    "dropped or renamed it on the way in."))
    return findings


def _short(text: str, limit: int = 70) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= limit else text[:limit - 1] + "…"


def traceability(spec: Any) -> Dict[str, Any]:
    rows = []
    for requirement, unit in _units(spec):
        rows.append({"requirement": requirement.id, "criterion": unit.id,
                     "text": unit.text, "status": unit.status,
                     "met_by": list(unit.met_by), "note": unit.note,
                     "confirmed_by": unit.confirmed_by})
    decisions = [{"id": d.id, "question": d.question, "choice": d.choice,
                  "source": d.source, "must_confirm": d.must_confirm,
                  "confirmed_by": d.confirmed_by or ("the user" if d.source == "user" else None),
                  "affects": list(d.affects)}
                 for d in getattr(spec, "decisions", None) or []]
    return {
        "criteria": rows,
        "counts": {status: sum(1 for row in rows if row["status"] == status)
                   for status in CRITERION_STATUSES},
        "departures": [row for row in rows if row["status"] in _DEPARTURES],
        "runtime_tests": [row for row in rows if row["status"] == "runtime"],
        "decisions": decisions,
    }


DEFAULT_REQUIREMENT_ID = r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+"
DEFAULT_DECISION_ID = r"D-\d+"

_CRITERION_LINE = re.compile(
    r"^\s*(?:[-*+]|\d+[.)])\s*(?:\*\*)?(AC\s*-?\s*\d+)(?:\*\*)?\s*[:.)—–-]\s*(.+)$",
    re.IGNORECASE)
_STAR = re.compile(r"[★☆*]{1}\s*$|★")


def extract_requirements(text: str, *, requirement_id: str = DEFAULT_REQUIREMENT_ID,
                         decision_id: str = DEFAULT_DECISION_ID
                         ) -> Tuple[List[RequirementSpec], List[DecisionSpec]]:
    header = re.compile(
        rf"^\s*(?:#+\s*|[-*+]\s*)?(?:\*\*)?({requirement_id})(?:\*\*)?"
        rf"\s*(?:[—–:.\-]\s*)?(.*)$")
    decision_row = re.compile(rf"^\s*\|\s*(?:\*\*)?\s*({decision_id})\b([^|]*)\|(.+)\|\s*$")

    requirements: List[RequirementSpec] = []
    decisions: List[DecisionSpec] = []
    current: Optional[RequirementSpec] = None
    body: List[str] = []

    def close() -> None:
        if current is not None and body and not current.text:
            current.text = " ".join(body)[:600]

    for raw in text.splitlines():
        line = raw.rstrip()
        row = decision_row.match(line)
        if row:
            cells = [cell.strip().strip("*").strip() for cell in row.group(3).split("|")]
            question = cells[0] if cells else ""
            default = cells[-1] if len(cells) > 1 else ""
            decisions.append(DecisionSpec(
                id=row.group(1), question=_strip_markdown(question),
                choice=_strip_markdown(default), source="requirements",
                must_confirm=bool(_STAR.search(row.group(2).replace("**", "")))))
            continue
        if line.lstrip().startswith("|"):
            continue
        match = header.match(line)
        if match and _is_requirement_header(line, match):
            close()
            title = _strip_markdown(re.split(r"\s[·|]\s|\*\*", match.group(2))[0])
            priority = None
            tail = match.group(2)
            found = re.search(r"·\s*([MSCW])\s*(?:·|$)", tail)
            if found:
                priority = found.group(1)
            current = RequirementSpec(id=match.group(1), title=title.strip(" -—"),
                                      priority=priority)
            requirements.append(current)
            body = []
            continue
        if current is None:
            continue
        criterion = _CRITERION_LINE.match(line)
        if criterion:
            number = re.sub(r"\D", "", criterion.group(1))
            current.criteria.append(CriterionSpec(
                id=f"{current.id}.AC{number}",
                text=_strip_markdown(criterion.group(2))))
        elif line.strip() and not current.criteria and not line.lstrip().startswith(("-", "*", ">")):
            body.append(_strip_markdown(line.strip()))
    close()
    return requirements, decisions


def _is_requirement_header(line: str, match: "re.Match[str]") -> bool:
    stripped = line.lstrip()
    if stripped.startswith(("#", "**", "- **", "* **")):
        return True
    return bool(re.match(r"\s*[—–:.\-]", line[match.end(1):]))


def _strip_markdown(text: str) -> str:
    text = re.sub(r"\*\*|__|`", "", text)
    return re.sub(r"\s+", " ", text).strip()


def requirements_module(requirements: Sequence[RequirementSpec],
                        decisions: Sequence[DecisionSpec], *, source: str = "") -> str:
    lines = [
        '"""Requirements and decisions, drafted from '
        + (f"`{source}`" if source else "the requirements document") + '.',
        "",
        "Trace every criterion: name what meets it in `met_by`, or mark it",
        "`runtime`, `deviation`, `not_built` or `out_of_scope` with a `note`.",
        "Decisions sourced from the requirements are their defaults; a starred",
        "one is `must_confirm` and blocks the build until `confirmed_by` is set.",
        '"""',
        "",
        "from qblparser.generation import CriterionSpec, DecisionSpec, RequirementSpec",
        "",
        "REQUIREMENTS = [",
    ]
    for requirement in requirements:
        lines.append(f"    RequirementSpec({requirement.id!r}, {requirement.title!r},")
        if requirement.priority:
            lines.append(f"        priority={requirement.priority!r},")
        if requirement.text:
            lines.append(f"        text={requirement.text!r},")
        if requirement.criteria:
            lines.append("        criteria=[")
            for criterion in requirement.criteria:
                lines.append(f"            CriterionSpec({criterion.id!r}, {criterion.text!r},")
                lines.append("                          met_by=[]),")
            lines.append("        ]),")
        else:
            lines.append("        met_by=[]),")
    lines += ["]", "", "DECISIONS = ["]
    for decision in decisions:
        lines.append(f"    DecisionSpec({decision.id!r}, {decision.question!r},")
        lines.append(f"                 {decision.choice!r}, source='requirements',")
        lines.append(f"                 must_confirm={decision.must_confirm!r}, affects=[]),")
    lines += ["]", ""]
    return "\n".join(lines)


__all__ = [
    "ARTIFACT_KINDS", "ArtifactIndex", "CRITERION_STATUSES", "CriterionSpec",
    "DECISION_SOURCES", "DEC_CODES", "DecisionSpec", "REQ_CODES", "RequirementSpec",
    "check_decisions", "check_deployed_trace", "check_requirements",
    "extract_requirements", "requirements_module", "traceability",
]
