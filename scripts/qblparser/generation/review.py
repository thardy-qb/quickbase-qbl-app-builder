from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterator, List, Mapping, Optional

from qblparser.utils.parameters import build_parameter_map, resolve_parameters

from .behaviour import check_behaviour
from .requirements import check_deployed_trace, traceability


def _plain(node: Any) -> Any:
    if isinstance(node, Mapping):
        return {str(key): _plain(value) for key, value in node.items()}
    if isinstance(node, (list, tuple)):
        return [_plain(value) for value in node]
    if node is None or isinstance(node, (bool, int, float)):
        return node
    return str(node)


def _short(text: Any, limit: Optional[int]) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip()
    if limit is None or len(text) <= limit:
        return text
    return text[:limit] + " …"


def _refs(node: Any, key: str) -> List[str]:
    found: List[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, Mapping):
            for name, value in item.items():
                if name == key and isinstance(value, str):
                    found.append(value)
                walk(value)
        elif isinstance(item, list):
            for value in item:
                walk(value)
    walk(node)
    return found


def _types(node: Any) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    def walk(item: Any) -> None:
        if isinstance(item, Mapping):
            if isinstance(item.get("Type"), str):
                counts[item["Type"]] = counts.get(item["Type"], 0) + 1
            for value in item.values():
                walk(value)
        elif isinstance(item, list):
            for value in item:
                walk(value)
    walk(node)
    return counts


def _access(permission: Any) -> str:
    if not isinstance(permission, Mapping):
        return str(permission)
    when = permission.get("When")
    criteria = permission.get("CustomAccessCriteria")
    return f"{when} {criteria}" if when == "CustomRule" and criteria else str(when)


def digest(document: Mapping[str, Any], *, formula_limit: Optional[int] = 600) -> str:
    parameters = build_parameter_map(document)
    if parameters:
        document = resolve_parameters(document, parameters)
    doc = _plain(document)
    resources = doc.get("Resources") or {}
    app = next((node for node in resources.values()
                if isinstance(node, dict) and node.get("Type") == "QB::Application"), {})
    tables = app.get("Tables") or {}
    table_name = {key: (node.get("Properties") or {}).get("Name", key)
                  for key, node in tables.items()}
    labels: Dict[str, Dict[str, str]] = {}
    for key, node in tables.items():
        labels[key] = {fk: (f.get("Properties") or {}).get("Label", fk)
                       for fk, f in (node.get("Fields") or {}).items()}
    report_name = {rk: f"{table_name[key]}/{(r.get('Properties') or {}).get('Name', rk)}"
                   for key, node in tables.items()
                   for container in ("Reports", "Charts")
                   for rk, r in (node.get(container) or {}).items()}
    roles = {key: (role.get("Properties") or {}).get("Name", key)
             for key, role in (app.get("Roles") or {}).items()}

    out: List[str] = []
    w = out.append
    props = app.get("Properties") or {}
    w(f"# {props.get('Name', 'Application')}")
    if props.get("Description"):
        w(f"\n{_short(props['Description'], 600)}")

    w("\n## Roles")
    for key, role in (app.get("Roles") or {}).items():
        p = role.get("Properties") or {}
        hidden = [table_name.get(k, k) for k, v in (p.get("TableUI") or {}).items()
                  if isinstance(v, dict) and v.get("HideInBar")]
        w(f"- **{p.get('Name')}** - edits app: {bool(p.get('EditApp'))}, manages users: "
          f"{bool(p.get('ManageUsers'))}, default: {bool(p.get('Default'))}"
          + (f"; hidden tables: {', '.join(hidden)}" if hidden else "")
          + (f"\n  - {_short(p['Description'], 300)}" if p.get("Description") else ""))

    for key, table in tables.items():
        p = table.get("Properties") or {}
        lab = labels[key]
        w(f"\n## Table: {p.get('Name')} ({len(table.get('Fields') or {})} fields)")
        if p.get("Description"):
            w(_short(p["Description"], 400))
        rules = p.get("CustomDataRules") or {}
        if isinstance(rules, dict) and rules.get("TurnedOn") and rules.get("Formula"):
            w(f"**Data rule (refuses the save when it returns text):** "
              f"`{_short(rules['Formula'], formula_limit)}`")
        for role_key, perm in (p.get("RolePermissions") or {}).items():
            if not isinstance(perm, dict):
                continue
            w(f"- access **{roles.get(role_key, role_key)}**: add {bool(perm.get('CanAddRecords'))}, "
              f"delete {bool(perm.get('CanDeleteRecords'))}, view "
              f"{_access(perm.get('CanViewRecords'))}, modify {_access(perm.get('CanModifyRecords'))}")
        parent_of = {rk: table_name.get(((r.get("Properties") or {}).get("Parent") or {})
                                        .get("Table"), rk)
                     for rk, r in (table.get("Relationships") or {}).items()
                     if isinstance(r, dict) and r.get("Type") == "QB::Relationship::Child"}
        w("\n### Fields")
        for fk, item in (table.get("Fields") or {}).items():
            fp = item.get("Properties") or {}
            if "Label" not in fp:
                continue
            kind = str(item.get("Type", "")).replace("QB::Field::", "")
            bits = []
            if fp.get("IsRequired"):
                bits.append("required")
            if fp.get("IsUnique"):
                bits.append("unique")
            if fp.get("DefaultValue") not in (None, "", False):
                bits.append(f"default {_short(fp['DefaultValue'], 60)}")
            choices = (fp.get("InputOptions") or {}).get("ListChoices")
            if choices:
                bits.append("choices " + " | ".join(map(str, choices)))
            if fp.get("Formula"):
                bits.append(f"= `{_short(fp['Formula'], formula_limit)}`")
            for name in ("Reference", "Lookup", "Summary"):
                block = fp.get(name)
                if isinstance(block, dict):
                    via = [parent_of.get(r, r) for r in _refs(block.get("Relationship"), "Relationship")]
                    reads = [lab.get(r, r) for r in _refs(block.get("Proxy") or block.get("Field"), "Field")]
                    function = block.get("Function") or block.get("SummaryFunction")
                    bits.append(f"{name.lower()} via {', '.join(via) or '?'}"
                                + (f" of {', '.join(reads)}" if reads else "")
                                + (f" ({function})" if function else ""))
            permissions = fp.get("RolePermissions") or {}
            limited = {roles.get(r, r): v for r, v in permissions.items() if v != "Modify"}
            if limited:
                bits.append("field access " + ", ".join(f"{r}: {v}" for r, v in limited.items()))
            if fp.get("HelpText"):
                bits.append(f"help: {_short(fp['HelpText'], 120)}")
            w(f"- [{item.get('Id')}] {fp['Label']} ({kind})" + (" - " + "; ".join(bits) if bits else ""))
        relationships = [r for r in (table.get("Relationships") or {}).values()
                         if isinstance(r, dict) and r.get("Type") == "QB::Relationship::Child"]
        if relationships:
            w("\n### Parents")
            for rel in relationships:
                parent = ((rel.get("Properties") or {}).get("Parent") or {}).get("Table")
                w(f"- {table_name.get(parent, parent)}")
        for container in ("Reports", "Charts"):
            items = table.get(container) or {}
            if not items:
                continue
            w(f"\n### {container}")
            for report in items.values():
                rp = report.get("Properties") or {}
                criteria = (rp.get("Filters") or {}).get("Criteria")
                columns = rp.get("Columns")
                if isinstance(columns, list):
                    columns = ", ".join(lab.get(c, c) for c in _refs(columns, "Field"))
                grouped = ", ".join(lab.get(c, c) for c in _refs(rp.get("SortAndGroup"), "Field"))
                colour = rp.get("ColorCoding") or {}
                visible = rp.get("RolePermissions") or {}
                hidden_from = [roles.get(r, r) for r, shown in visible.items() if not shown]
                w(f"- {str(report.get('Type', '')).split('::')[-1]} **{rp.get('Name')}**"
                  + (f" - filter `{_short(criteria, formula_limit)}`" if criteria not in (None, "Default") else "")
                  + (f"; columns {columns}" if columns not in (None, "Default") else "")
                  + (f"; sorted/grouped by {grouped}" if grouped else "")
                  + (f"; coloured by `{_short(colour.get('ColorFormula'), 120)}`"
                     if colour.get("ColorBy") not in (None, "None") else "")
                  + (f"; hidden from {', '.join(hidden_from)}" if hidden_from else ""))
        forms = table.get("Forms") or {}
        if forms.get("Resources"):
            w("\n### Forms")
            defaults = (forms.get("Properties") or {}).get("RoleDefaults") or {}
            opens = {roles.get(r, r): _refs(v, "FormV2") + _refs(v, "Form")
                     for r, v in defaults.items()}
            opens = {r: v for r, v in opens.items() if v}
            for form_key, form in forms["Resources"].items():
                fp = form.get("Properties") or {}
                used_by = [r for r, keys in opens.items() if form_key in keys]
                members = list(dict.fromkeys(lab.get(f, f) for f in _refs(form, "Field")))
                embedded = list(dict.fromkeys(report_name.get(r, r) for r in _refs(form, "Report")))
                w(f"- {form.get('Type')} **{fp.get('Name')}**"
                  + (f" (opened by {', '.join(used_by)})" if used_by else "")
                  + (f" - {len(members)} field(s): {_short(', '.join(members), 900)}" if members
                     else " - **no fields**")
                  + (f"; embeds {', '.join(embedded)}" if embedded else ""))
                for rule in _rules(form):
                    w(f"  - rule **{rule['name']}**: when {_short(rule['when'], formula_limit)} "
                      f"then {_short(rule['then'], 400)}")
        for email in (table.get("Emails") or {}).values():
            ep = email.get("Properties") or {}
            settings = ep.get("EmailSettings") or {}
            to = [lab.get(f, f) for f in _refs(settings.get("To"), "Field")]
            w(f"\n### Email: {ep.get('Name')}")
            w(f"- sends {json.dumps(ep.get('SendOptions'))} to "
              f"{', '.join(to) or json.dumps(settings.get('To'))}")
            w(f"- subject `{settings.get('Subject')}`; body `{_short(settings.get('Content'), formula_limit)}`")
            if email.get("Conditions"):
                w(f"- conditions `{_short(json.dumps(email['Conditions']), 400)}`")

    pages = (app.get("Pages") or {}).get("Resources") or {}
    if pages:
        w("\n## Pages")
        defaults = (app.get("Pages") or {}).get("Properties", {}).get("RoleDefaults") or {}
        for key, page in pages.items():
            pp = page.get("Properties") or {}
            landing = [roles.get(r, r) for r, v in defaults.items() if key in json.dumps(v)]
            reports = list(dict.fromkeys(report_name.get(r, r) for r in _refs(page, "Report")))
            widgets = {k.split("::")[-1]: v for k, v in _types(page).items() if "Widget" in k}
            w(f"- {page.get('Type')} **{pp.get('Name')}**"
              + (f" (home for {', '.join(landing)})" if landing else "")
              + (f" - widgets {widgets}" if widgets else "")
              + (f"; shows {', '.join(reports)}" if reports else ""))
            for text in _refs(page, "Content") + _refs(page, "Code"):
                w(f"  - content `{_short(text, 500)}`")

    pipelines = [node for node in resources.values()
                 if isinstance(node, dict) and node.get("Type") == "QB::Pipeline"]
    if pipelines:
        w("\n## Pipelines")
    field_label = {fk: lbl for key in labels for fk, lbl in labels[key].items()}
    for pipeline in pipelines:
        pp = pipeline.get("Properties") or {}
        schedule = (f"scheduled `{pp['Crontab']}` {pp.get('CrontabTimezone', '')}"
                    if pp.get("Crontab") else "event-triggered")
        w(f"\n### {pp.get('Name')} ({schedule})")
        if pp.get("Description"):
            w(_short(pp["Description"], 400))
        for line in _steps(pipeline.get("Steps") or [], table_name, field_label, formula_limit):
            w(line)
    return "\n".join(out) + "\n"


def _rules(form: Mapping[str, Any]) -> Iterator[Dict[str, str]]:
    def walk(item: Any) -> Iterator[Mapping[str, Any]]:
        if isinstance(item, Mapping):
            kind = str(item.get("Type", ""))
            if "::Rule" in kind and "::Rule::" not in kind:
                yield item
            for value in item.values():
                yield from walk(value)
        elif isinstance(item, list):
            for value in item:
                yield from walk(value)

    for rule in walk(form):
        name = (rule.get("Properties") or {}).get("Name", "")
        yield {"name": name,
               "when": json.dumps(rule.get("When") or rule.get("Conditions") or ""),
               "then": json.dumps(rule.get("Actions") or "")}


def _steps(steps: List[Any], table_name: Mapping[str, str], field_label: Mapping[str, str],
           limit: Optional[int], indent: str = "") -> Iterator[str]:
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        p = step.get("Properties") or {}
        kind = str(step.get("Type", "")).split("::")[-1]
        channel = p.get("Channel") or {}
        tables = [table_name.get(t, t) for t in _refs(step.get("InputsMeta"), "Table")]
        target = (p.get("Target") or {}).get("StepId")
        what = f"{channel.get('Id', '')}/{channel.get('Selector', '')}" if channel else kind.lower()
        detail = []
        if tables:
            detail.append(f"on {sorted(set(tables))[0]}")
        if target:
            detail.append(f"target step {target}")
        if p.get("Filters"):
            detail.append(f"filter `{_short(json.dumps(p['Filters'].get('Expression', p['Filters'])), limit)}`")
        if p.get("Inputs") is not None:
            detail.append(f"writes `{_short(json.dumps(p['Inputs']), limit)}`"
                          if p["Inputs"] else "**writes nothing**")
        elif p.get("SubType") == "action":
            detail.append("**writes nothing**")
        if kind == "Condition" and not p.get("Filters"):
            detail.append("**no condition**")
        yield (f"{indent}- [{p.get('Id', '')}] {kind} **{p.get('Name', '')}** {what} "
               + "; ".join(detail))
        if isinstance(step.get("Steps"), list):
            yield from _steps(step["Steps"], table_name, field_label, limit, indent + "  ")
        for branch in ("Then", "Else"):
            if isinstance(step.get(branch), list):
                yield f"{indent}  - {branch}:"
                yield from _steps(step[branch], table_name, field_label, limit, indent + "    ")


def review_export(export: Mapping[str, Any], spec: Any = None, *,
                  formula_limit: Optional[int] = 600) -> Dict[str, Any]:
    findings = list(check_behaviour(export))
    summary = None
    if spec is not None and getattr(spec, "requirements", None):
        findings.extend(check_deployed_trace(spec, export))
        summary = traceability(spec)
    return {"findings": findings, "digest": digest(export, formula_limit=formula_limit),
            "traceability": summary}


__all__ = ["digest", "review_export"]
