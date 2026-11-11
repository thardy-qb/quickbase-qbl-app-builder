#!/usr/bin/env python3
"""Build QBL from an `AppSpec`, and validate it against Quickbase by creating it.

    python3 scripts/build_qbl.py template --out spec.py
    python3 scripts/build_qbl.py requirements stories.md --out requirements.py
    python3 scripts/build_qbl.py check   spec.py
    python3 scripts/build_qbl.py build   spec.py --out app.qbl.yaml
    python3 scripts/build_qbl.py create  app.qbl.yaml --intent new
    python3 scripts/build_qbl.py probe   spec.py
    python3 scripts/build_qbl.py fetch-deployed <solutionId> --out current.qbl.yaml
    python3 scripts/build_qbl.py update  <solutionId> app.qbl.yaml --confirm <solutionId>
    python3 scripts/build_qbl.py cleanup
    python3 scripts/build_qbl.py review  export.qbl.yaml --spec spec.py --digest app.md
    python3 scripts/build_qbl.py selftest

`check` and `build` run every offline gate and send nothing. `build` writes the
document only when no gate reports an error.

`create` is the validation: a document builds when Quickbase builds it. Each create
makes a real application in your realm, so every call that may have made one is
written to a cleanup ledger, and `cleanup` lists what you still need to delete.

## The spec is a Python file

An `AppSpec` is a tree of dataclasses with defaults, and the defaults are the
point: the spec carries no logical IDs, no numeric IDs, no containers and no
built-in fields, because those are decisions with a right answer that the
builder makes. The consequence is that a spec file is **executed**. Never run
a spec file that arrived from somewhere else.

## The gates

    1  compile        is the spec expressible at all
    1a requirements   does every acceptance criterion trace to what meets it
    1b design         is the data model one an application should have
    1c code pages     does each code page clear the rules it must
    2  offline        schema, references, values, structure, formulas
    3  conformance    does each node have a shape Quickbase accepts
    3b behaviour      no step writing nothing, no state nothing sets
    4  create         will Quickbase actually build it   (`create`; it mutates)

Gates 1 to 3b run in `check` and `build`. `create` re-runs the ones that need
only the finished document before it sends anything.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import cleanup_ledger  # noqa: E402
import qb_auth
import qb_probe
import qb_solutions
import qb_update
from qb_common import (
    EXIT_FINDINGS,
    EXIT_OK,
    SkillInputError,
    application_name,
    counts,
    document_gates,
    document_yaml,
    emit,
    group_by_code,
    load_document,
    render_gate_line,
    render_groups,
    renamed_text,
    risk_lines,
    run_guarded,
    sha256_file,
    sha256_text,
    utc_stamp,
)

from qblparser.generation import (  # noqa: E402
    AppSpec,
    QBLCompileError,
    QBLGenerationError,
    build_app,
    compile_app,
    create_risks,
    extract_requirements,
    plan_update,
    requirements_module,
    review_export,
    traceability,
)
from qblparser.generation.compiler import QBL_VERSION  # noqa: E402


TEMPLATE = '''\
"""A starter `AppSpec`. Edit and run:

    python3 scripts/build_qbl.py check  this_file.py
    python3 scripts/build_qbl.py build  this_file.py --out app.qbl.yaml

The module must define `SPEC`. Everything importable from
`qblparser.generation` is available; `references/spec-reference.md` lists every
spec class, every attribute, and the closed value sets.
"""

from qblparser.generation import (
    AppSpec,
    CriterionSpec,
    DashboardSpec,
    DashboardWidgetSpec,
    FieldSpec,
    FormColumnSpec,
    FormElementSpec,
    FormSectionSpec,
    FormSpec,
    DecisionSpec,
    RelationshipSpec,
    ReportSpec,
    RequirementSpec,
    RoleSpec,
    TableSpec,
)

# What was asked for, and what meets it. Draft these from a requirements
# document with `build_qbl.py requirements <file.md>`; every criterion names the
# artifacts that meet it, or says why it is not built and who agreed.
REQUIREMENTS = [
    RequirementSpec("R-1", "Track projects by client", criteria=[
        CriterionSpec("R-1.AC1", "Each project belongs to one client",
                      met_by=["relationship:Clients/Projects"]),
        CriterionSpec("R-1.AC2", "Active projects are listed on the dashboard",
                      met_by=["report:Projects/Active Projects", "dashboard:Overview"]),
    ]),
]

# Choices the requirements left open. `source="builder"` blocks the build until
# `confirmed_by` records the person who agreed.
DECISIONS = [
    DecisionSpec("D-1", "Which statuses does a project move through?",
                 "Planned, Active, Done", source="user",
                 affects=["field:Projects/Status"]),
]

SPEC = AppSpec(
    name="Project Tracker",
    tables=[
        TableSpec(
            "Clients",
            fields=[
                FieldSpec("Client Name"),
                FieldSpec("Account Manager", "User"),
            ],
            reports=[ReportSpec("All Clients", kind="Table")],
            # Omit `form` entirely and the table still gets a modern FormV2
            # listing its fields. Name one to say more than that.
            form=FormSpec("Client Form", sections=[
                FormSectionSpec("Details", columns=[
                    FormColumnSpec(["Client Name", "Account Manager"]),
                ]),
            ]),
        ),
        TableSpec(
            "Projects",
            fields=[
                FieldSpec("Project Name"),
                FieldSpec("Budget", "Currency", properties={"DecimalPlaces": 2}),
                FieldSpec("Status", "TextMultipleChoice",
                          choices=["Planned", "Active", "Done"]),
            ],
            reports=[ReportSpec("Active Projects", kind="Table")],
            form=FormSpec("Project Form", sections=[
                # Two columns. Leave `layout_width` alone and the section's
                # twelve are split between them.
                FormSectionSpec("Overview", columns=[
                    FormColumnSpec(["Project Name", "Related Clients"]),
                    FormColumnSpec(["Budget", "Status"]),
                ]),
                # A column holds more than labels: prose, a group, a field
                # under its own label, or an embedded report.
                FormSectionSpec("Notes", columns=[
                    FormColumnSpec([
                        FormElementSpec(
                            content="<p>Update the status before each review.</p>"),
                    ]),
                ]),
            ]),
        ),
    ],
    relationships=[RelationshipSpec("Clients", "Projects")],
    roles=[RoleSpec("Viewer")],
    # Drop this and a dashboard like it is built anyway, with one widget per
    # table. Either way it is the page everyone opens on - the QB::HomePage
    # the platform insists on is emitted beside it and left empty.
    dashboards=[DashboardSpec("Overview", widgets=[
        DashboardWidgetSpec(kind="Table", title="Active Projects",
                            table="Projects", report="Active Projects", width=6),
        DashboardWidgetSpec(kind="Table", title="Clients",
                            table="Clients", report="All Clients", width=6),
    ])],
    requirements=REQUIREMENTS,
    decisions=DECISIONS,
)
'''


def _load_spec(path: str) -> AppSpec:
    """Import a spec file and return its `SPEC`.

    A missing or wrongly-typed `SPEC` is reported as an input problem rather
    than a traceback, because it is by far the most common mistake and the
    traceback for it says nothing useful.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise SkillInputError(f"no such spec file: {path}")

    module_spec = importlib.util.spec_from_file_location(
        "qbl_app_spec", str(file_path.resolve()))
    if module_spec is None or module_spec.loader is None:  # pragma: no cover
        raise SkillInputError(f"{file_path.name} cannot be imported as Python")

    module = importlib.util.module_from_spec(module_spec)
    try:
        module_spec.loader.exec_module(module)
    except SyntaxError as exc:
        raise SkillInputError(
            f"{file_path.name} line {exc.lineno}: {exc.msg}") from exc
    except Exception as exc:  # noqa: BLE001
        raise SkillInputError(
            f"{file_path.name} raised while being read: "
            f"{type(exc).__name__}: {exc}") from exc

    spec = getattr(module, "SPEC", None)
    if spec is None:
        raise SkillInputError(
            f"{file_path.name} defines no `SPEC`. The module must assign an "
            "`AppSpec` to a module-level name `SPEC`.")
    if not isinstance(spec, AppSpec):
        raise SkillInputError(
            f"{file_path.name} defines `SPEC` as {type(spec).__name__}, not an "
            "`AppSpec`.")
    return spec


def _run_gates(spec: AppSpec, *, conformance_codes=("GEN001", "GEN003")) -> Dict[str, Any]:
    """Build and gate, returning everything without deciding anything.

    `raise_on_error=False` so a caller sees every finding at once: a document
    with four problems should be reported with four, not one per run.
    """
    try:
        document, findings = build_app(
            spec,
            conformance_codes=conformance_codes, raise_on_error=False)
    except QBLCompileError as exc:
        return {"compiled": False, "stage": "compile", "reason": str(exc),
                "document": None, "findings": [], "risks": []}
    except QBLGenerationError as exc:
        return {"compiled": False, "stage": "gate", "reason": str(exc),
                "document": None, "findings": exc.findings, "risks": []}
    return {
        "compiled": True, "stage": "", "reason": "",
        "document": document, "findings": findings,
        "risks": create_risks(document),
        "traceability": traceability(spec),
    }


def _parse_rename(text: str):
    """`$Table_X:$Field_New=$Field_Old` -> `(("$Table_X", "$Field_New"), "$Field_Old")`."""
    try:
        target, old = text.split("=", 1)
        table, new = target.split(":", 1)
    except ValueError:
        raise SkillInputError(
            f"--rename {text!r}: expected $Table_X:$Field_New=$Field_Old")
    return (table.strip(), new.strip()), old.strip()


def _reconcile(args, result: Dict[str, Any], spec: AppSpec = None) -> None:
    """Fit the document to the solution it will replace, when one was given.

    A PUT that moves a deployed node's numeric id hangs and applies nothing,
    and a PUT that omits a field deletes it and its data without a warning.
    A spec numbers by position and names by label, so an edited spec does both
    unless its document is reconciled against an export of the solution first.
    Data loss becomes a blocking `UPD001`.
    """
    deployed_path = getattr(args, "deployed", None)
    if not deployed_path or not result["compiled"]:
        return
    from qblparser import load_qbl_file

    renames = dict(_parse_rename(text) for text in (args.rename or []))
    source = compile_app(spec, resolve_tokens=False) if spec is not None else result["document"]
    try:
        plan = plan_update(source, load_qbl_file(deployed_path), renames=renames)
    except ValueError as exc:
        raise SkillInputError(f"--rename or a field token: {exc}")
    result["document"] = plan.document
    result["findings"] = list(result["findings"]) + plan.findings()
    result["update_plan"] = {
        "deployed": deployed_path,
        "pinned": [{"node": path[-1], "sent": sent, "deployed": kept}
                   for path, sent, kept in plan.pinned],
        "reassigned": [{"node": path[-1], "sent": sent, "assigned": new}
                       for path, sent, new in plan.reassigned],
        "removed": [{"node": path[-1], "type": qbl_type}
                    for path, qbl_type in plan.removed],
        "field_tokens": plan.field_tokens,
    }


def _traceability_lines(summary) -> List[str]:
    """The build's claims about its requirements, for the person who owns them."""
    if not summary or not summary["criteria"]:
        return ["TRACEABILITY", "",
                "  No requirements in the spec, so nothing here says this document "
                "does what was asked (REQ000).", ""]
    counts_by = summary["counts"]
    lines = ["TRACEABILITY", "",
             "  " + ", ".join(f"{count} {status.replace('_', ' ')}"
                              for status, count in counts_by.items() if count)
             + f" - of {len(summary['criteria'])} criteria", ""]
    for row in summary["criteria"]:
        met = ", ".join(row["met_by"]) or "-"
        lines.append(f"  {row['criterion']:<12} {row['status']:<12} {met}")
    lines.append("")
    if summary["departures"]:
        lines += ["DEPARTURES FROM THE REQUIREMENTS", ""]
        for row in summary["departures"]:
            who = row["confirmed_by"] or "NOT CONFIRMED"
            lines.append(f"  {row['criterion']} ({row['status']}): {row['note']} "
                         f"- agreed by {who}")
        lines.append("")
    if summary["decisions"]:
        lines += ["DECISIONS", ""]
        for row in summary["decisions"]:
            who = row["confirmed_by"] or "NOT CONFIRMED"
            lines.append(f"  {row['id']}: {row['question']} -> {row['choice']} "
                         f"[{row['source']}; {who}]")
        lines.append("")
    if summary["runtime_tests"]:
        lines += ["RUNTIME TEST PLAN", "",
                  "  What only a run against real records can prove. Gate 5 and "
                  "these are not the same thing: a create proves the document "
                  "builds, these prove the application works.", ""]
        for row in summary["runtime_tests"]:
            lines.append(f"  {row['criterion']}: {row['note'] or '(no test written)'}")
        lines.append("")
    return lines


def _report(result: Dict[str, Any], *, wrote: str = "") -> List[str]:
    lines: List[str] = []

    if not result["compiled"]:
        lines += [
            f"COMPILE FAILED at gate 1 ({result['stage']})", "",
            result["reason"], "",
            "Nothing was generated and nothing was sent to Quickbase.",
        ]
        if result["findings"]:
            lines += ["", "Findings gathered before it stopped:", ""]
            lines += render_groups(group_by_code(result["findings"]))
        return lines

    findings = result["findings"]
    risks = result["risks"]
    tally = counts(findings)

    def prefixed(*prefixes):
        return [f for f in findings if str(f.get("Code", "")).startswith(prefixes)]

    offline = prefixed("SCH", "REF", "VAL", "STR", "FML")
    risk_errors = [risk for risk in risks if risk.severity == "error"]

    if tally["errors"] or risk_errors:
        lines.append(f"NOT WRITTEN - {tally['errors'] + len(risk_errors)} error(s)")
    elif wrote:
        lines.append(f"BUILT - wrote {wrote}")
    else:
        lines.append("BUILDS CLEANLY - nothing written (`check`)")
    lines += ["", "GATES", "", f"  {'1 compile':22} {'PASS':9}"]
    lines.append(render_gate_line("1a requirements", prefixed("REQ", "DEC")))
    lines.append(render_gate_line("1b design review", prefixed("DSN")))
    if prefixed("CPG"):
        lines.append(render_gate_line("1c code page review", prefixed("CPG")))
    lines.append(render_gate_line("2 offline layers", offline))
    lines.append(render_gate_line("3 conformance", prefixed("GEN")))
    lines.append(render_gate_line("3b behaviour", prefixed("BHV")))
    lines.append(f"  {'3c create catalog':22} {'FAIL' if risk_errors else 'PASS':9} "
                 f"{len(risk_errors)} error(s), {len(risks) - len(risk_errors)} suspect(s)")
    lines.append(f"  {'4 create':22} {'NOT RUN':9} `create` makes real applications")
    lines.append("")

    if prefixed("CPG"):
        lines.append("Every code page here is a DRAFT. It needs a developer's review "
                     "and testing before it is deployed, and nothing in "
                     "these gates has executed it. Gate 1c is pattern matching over its "
                     "source, not a security review.")
        lines.append("")

    lines += _traceability_lines(result.get("traceability"))

    update = result.get("update_plan")
    if update:
        lines += [f"UPDATE PLAN against {update['deployed']}", ""]
        lines.append(f"  {len(update['pinned'])} node(s) moved back to their deployed id, "
                     f"{len(update['reassigned'])} new node(s) given a free one, "
                     f"{len(update['removed'])} deployed node(s) the PUT will delete.")
        for entry in update["removed"]:
            lines.append(f"    deletes {entry['type']} {entry['node']}")
        lines.append("")

    if risks:
        lines += ["CREATE-FAILURE CATALOG", "",
                  "Shapes Quickbase is known not to create. An error here will "
                  "fail the create.", ""]
        lines += risk_lines(risks)

    if findings:
        lines += ["FINDINGS", ""] + render_groups(group_by_code(findings))
    elif not risks:
        lines += ["No findings from any gate that ran.", ""]

    lines += ["", "Gate 4 is the one that matters and it is separate: only creating the "
              "document shows that Quickbase will build it. A clean report here is "
              "not a promise, and formula bodies in particular are read by nothing "
              "until the create."]
    return lines


def _conformance_codes(args):
    if args.conformance_codes:
        return tuple(code.strip() for code in args.conformance_codes.split(",")
                     if code.strip())
    return ("GEN001", "GEN003")


def _payload(args, result, wrote) -> Dict[str, Any]:
    findings = result["findings"]
    risks = result["risks"]
    tally = counts(findings)
    risk_errors = [risk for risk in risks if risk.severity == "error"]
    return {
        "spec": args.spec,
        "compiled": result["compiled"],
        "compile_error": result["reason"],
        "written": wrote,
        "gates": {
            "compile": {"ran": True, "passed": result["compiled"]},
            "offline_and_conformance": {"counts": tally},
            "create_catalog": {"ran": result["compiled"], "errors": len(risk_errors),
                               "suspects": len(risks) - len(risk_errors)},
            "create": {"ran": False},
        },
        "findings": group_by_code(findings),
        "risks": [{"code": risk.code, "severity": risk.severity, "where": risk.location,
                   "problem": risk.problem, "fix": risk.fix} for risk in risks],
        "update_plan": result.get("update_plan"),
        "traceability": result.get("traceability"),
        "blocking": bool(not result["compiled"] or tally["errors"] or risk_errors),
    }


def _check(args) -> int:
    spec = _load_spec(args.spec)
    result = _run_gates(spec, conformance_codes=_conformance_codes(args))
    _reconcile(args, result, spec)
    payload = _payload(args, result, wrote="")
    emit(payload, _report(result), args.format)
    return EXIT_FINDINGS if payload["blocking"] else EXIT_OK


def _build(args) -> int:
    spec = _load_spec(args.spec)
    result = _run_gates(spec, conformance_codes=_conformance_codes(args))
    _reconcile(args, result, spec)
    payload = _payload(args, result, wrote="")
    if payload["blocking"]:
        emit(payload, _report(result), args.format)
        return EXIT_FINDINGS

    out_path = Path(args.out) if args.out else Path("app.qbl.yaml")
    out_path.write_text(document_yaml(result["document"]))
    deployed = Path(args.deployed) if args.deployed else None
    record = qb_update.write_build_record(out_path, deployed=deployed)
    payload["written"] = str(out_path)
    payload["build_record"] = str(qb_update.build_record_path(out_path))
    lines = _report(result, wrote=out_path.name)
    if deployed is not None and not (record["deployed"] or {}).get("solution_id"):
        lines += ["", "Note: that export was not fetched with `fetch-deployed`, so nothing "
                  "records which solution it is, and `update` will refuse this document."]
    emit(payload, lines, args.format)
    return EXIT_OK


def _requirements(args) -> int:
    """Draft a requirements module from a requirements document."""
    source = Path(args.source)
    if not source.is_file():
        raise SkillInputError(f"no such requirements document: {args.source}")
    kwargs = {}
    if args.id_pattern:
        kwargs["requirement_id"] = args.id_pattern
    if args.decision_pattern:
        kwargs["decision_id"] = args.decision_pattern
    found, decisions = extract_requirements(source.read_text(encoding="utf-8"), **kwargs)
    if not found:
        raise SkillInputError(
            f"{source.name}: no requirement found. A requirement starts on a line "
            f"that leads with its id (`**US-1 - Title**`, `### BR-3: Title`); pass "
            f"--id-pattern if the ids look different.")
    text = requirements_module(found, decisions, source=source.name)
    criteria = sum(len(item.criteria) or 1 for item in found)
    if args.out:
        out = Path(args.out)
        if out.exists() and not args.force:
            raise SkillInputError(f"{out} already exists; pass --force to overwrite it")
        out.write_text(text)
    payload = {"requirements": len(found), "criteria": criteria,
               "decisions": len(decisions),
               "must_confirm": [d.id for d in decisions if d.must_confirm],
               "written": args.out or ""}
    lines = [f"Drafted {len(found)} requirement(s), {criteria} criteria to trace, "
             f"{len(decisions)} decision(s)"
             + (f" ({len(payload['must_confirm'])} to confirm before building: "
                f"{', '.join(payload['must_confirm'])})" if payload["must_confirm"] else "")
             + ".",
             "",
             "Every criterion starts untraced, so `check` fails on each (REQ001) "
             "until it names what meets it or says why not.",
             f"wrote {args.out}" if args.out else ""]
    if not args.out:
        sys.stdout.write(text)
        return EXIT_OK
    emit(payload, lines, args.format)
    return EXIT_OK


def _review(args) -> int:
    """Review a deployed export: behaviour, lost traces, and a digest to read."""
    from qblparser import load_qbl_file

    export_path = Path(args.export)
    if not export_path.is_file():
        raise SkillInputError(f"no such export: {args.export}")
    spec = _load_spec(args.spec) if args.spec else None
    result = review_export(load_qbl_file(str(export_path)), spec,
                           formula_limit=None if args.full_formulas else 600)
    if args.digest:
        Path(args.digest).write_text(result["digest"])
    findings = result["findings"]
    tally = counts(findings)
    lines = [f"REVIEW of {export_path.name}", "",
             f"  {tally['errors']} error(s), {tally['warnings']} warning(s) from the "
             f"behaviour checks" + (" and the deployed trace" if spec else "") + ".",
             (f"  Digest written to {args.digest} ({len(result['digest'])} characters) - "
              f"give it, with the requirements, to a reviewer who did not write the "
              f"spec." if args.digest else "  Pass --digest to write the application "
              f"digest a reviewer scores the criteria against."), ""]
    lines += _traceability_lines(result["traceability"]) if spec else []
    if findings:
        lines += ["FINDINGS", ""] + render_groups(group_by_code(findings))
    payload = {"export": str(export_path), "findings": group_by_code(findings),
               "counts": tally, "digest": args.digest or "",
               "traceability": result["traceability"]}
    emit(payload, lines, args.format)
    return EXIT_FINDINGS if tally["errors"] else EXIT_OK


def _template(args) -> int:
    if args.out:
        out_path = Path(args.out)
        if out_path.exists() and not args.force:
            raise SkillInputError(
                f"{out_path} already exists; pass --force to overwrite it")
        out_path.write_text(TEMPLATE)
        print(f"wrote {out_path}")
    else:
        sys.stdout.write(TEMPLATE)
    return EXIT_OK


# --------------------------------------------------------------------------
# create: validate by building the real thing
# --------------------------------------------------------------------------

def _ledger_path(args, anchor: Optional[Path] = None) -> Path:
    """One ledger for the workflow: `--ledger`, else `qbl-cleanup.json` in the cwd."""
    if getattr(args, "ledger", None):
        return Path(args.ledger)
    return cleanup_ledger.default_path()


def _sent_call(ledger_path: Path, *, purpose: str, app_name: str, source_sha: str,
               sent_sha: str, realm_host: str, call: str, intent: str, send):
    """Write a PENDING entry, make the request, then update that entry.

    `(entry, outcome)`. If the request never left (no usable credential) the
    pending entry is removed again; any other interruption leaves it `PENDING`
    for `cleanup` to list.
    """
    entry = cleanup_ledger.begin(
        ledger_path, purpose=purpose, app_name=app_name, source_sha256=source_sha,
        sent_sha256=sent_sha, realm_host=realm_host, call=call)
    try:
        outcome = send()
    except (qb_auth.AuthError, SkillInputError):
        cleanup_ledger.discard(ledger_path, entry["id"])
        raise
    return cleanup_ledger.finish(ledger_path, entry["id"], outcome, intent=intent), outcome


def _realm_host(args, *, relay: bool) -> str:
    """The realm to send to. The stored one, unless a relay names it.

    A stored token works only in the realm it was created in, so a different
    `--realm` is refused rather than sent. For a relayed call the extension holds
    the token and `--realm` names where it will send.
    """
    given = qb_auth.normalize_realm(args.realm).host if getattr(args, "realm", None) else ""
    if relay:
        if given:
            return given
        try:
            return qb_auth.stored_realm_host()
        except qb_auth.AuthError:
            raise SkillInputError("pass --realm <realm> for a relayed create: the extension "
                                  "sends it, and this machine holds no stored token to read "
                                  "the realm from")
    stored = qb_auth.stored_realm_host()
    if given and given != stored:
        raise SkillInputError(f"the stored token is for {stored}, not {given}; a user "
                              "token works only in its own realm")
    return stored


def _gate_failure_lines(gated: Dict[str, Any]) -> List[str]:
    lines = [f"NOT SENT - the document fails {gated['errors']} offline gate error(s)", ""]
    lines += render_groups(group_by_code(gated["findings"]))
    lines += risk_lines(gated["risks"])
    lines.append("Nothing was sent to Quickbase, so nothing needs deleting.")
    return lines


def _outcome_lines(outcome: qb_solutions.Outcome, *, name: str, realm_host: str) -> List[str]:
    lines = [f"{outcome.outcome} - {name!r} on {realm_host}"
             + (f" (HTTP {outcome.http})" if outcome.http else ""), ""]
    if outcome.solution_id:
        lines.append(f"  solution id: {outcome.solution_id}")
    for app_id in outcome.app_ids:
        lines.append(f"  app: {cleanup_ledger.app_link(realm_host, app_id)}")
    if outcome.outcome == qb_solutions.TIMEOUT:
        lines += ["", cleanup_ledger.TIMEOUT_NOTE,
                  "Run `build_qbl.py probe <spec.py>` to find which part of the document "
                  "the platform cannot build."]
    elif outcome.outcome == qb_solutions.ERROR:
        lines += ["", outcome.detail or "no readable answer", cleanup_ledger.ERROR_NOTE]
    if outcome.findings:
        lines += ["", "FINDINGS FROM QUICKBASE", ""]
        lines += render_groups(group_by_code(outcome.findings))
    nameless = outcome.outcome == qb_solutions.REJECTED and all(
        "failure in creating one of the resources" in f.get("Problem", "")
        for f in outcome.findings if f.get("Severity") != "Warning") and outcome.findings
    if nameless:
        lines += ["That message names no resource. Run `build_qbl.py probe <spec.py>` to "
                  "localise it.", ""]
    for hint in outcome.hints:
        lines.append(f"  hint: {hint}")
    return lines


def _create(args) -> int:
    path = Path(args.document)
    document = load_document(str(path))
    gated = document_gates(document)
    relay_out = bool(args.write_submission)
    relay_in = bool(args.platform_response)
    if relay_out and relay_in:
        raise SkillInputError("--write-submission and --platform-response are two "
                              "separate runs of the same command")
    if not gated["passed"]:
        emit({"sent": False, "errors": gated["errors"],
              "findings": group_by_code(gated["findings"])},
             _gate_failure_lines(gated), args.format)
        return EXIT_FINDINGS

    source_sha = sha256_file(path)
    source_text = path.read_text(encoding="utf-8")
    app_name = application_name(document)
    sent_name = app_name
    purpose = "attempt"
    if args.intent == "edit":
        purpose = "validation-copy"
        sent_name = f"{app_name} (validation copy {utc_stamp()})"
    elif args.name_suffix:
        suffix = utc_stamp() if args.name_suffix is True else args.name_suffix
        sent_name = f"{app_name} ({suffix})"
    text = renamed_text(document, sent_name) if sent_name != app_name else source_text
    ledger_path = _ledger_path(args, path)
    cleanup_ledger.preflight(ledger_path)   # a corrupt ledger refuses before any request
    relay = relay_out or relay_in
    realm_host = _realm_host(args, relay=relay)
    submission = Path(args.submission) if args.submission else path.parent / "qbl-submission.yaml"

    if relay_out:
        target = Path(args.write_submission)
        target.write_text(text, encoding="utf-8")
        # The extension is about to send this text, so the entry is written now.
        pending = cleanup_ledger.begin(
            ledger_path, purpose=purpose, app_name=sent_name, source_sha256=source_sha,
            sent_sha256=sha256_text(text), realm_host=realm_host, relay=True)
        Path(str(target) + ".json").write_text(json.dumps({
            "text_sha256": sha256_text(text), "app_name": sent_name,
            "intent": args.intent, "source_sha256": source_sha, "realm_host": realm_host,
            "entry": pending["id"], "document": str(path)}, indent=2) + "\n",
            encoding="utf-8")
        lines = [f"wrote the exact text to send: {target}",
                 f"sha256: {sha256_text(text)}",
                 f"application name in it: {sent_name!r}",
                 f"realm: {realm_host}", "",
                 "Nothing has been sent. Have the extension tool POST that text, save its "
                 "JSON response unchanged to a file, then run this command again with "
                 f"--platform-response <file> --submission {target}."]
        emit({"submission": str(target), "sha256": sha256_text(text), "app_name": sent_name,
              "realm_host": realm_host}, lines, args.format)
        return EXIT_OK

    if relay_in:
        sent_path = Path(args.submission) if args.submission else submission
        meta = qb_update.read_json(Path(str(sent_path) + ".json"))
        if not meta or not sent_path.is_file():
            raise SkillInputError("the submission written by --write-submission is missing; "
                                  "pass it with --submission")
        text = sent_path.read_text(encoding="utf-8")
        if sha256_text(text) != meta.get("text_sha256"):
            raise SkillInputError("the submission file changed after it was written; "
                                  "write it again")
        if meta.get("source_sha256") != source_sha:
            raise SkillInputError("the submission was written from a different version of "
                                  "this document")
        try:
            saved = json.loads(Path(args.platform_response).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SkillInputError(f"cannot read the platform response: {exc}")
        try:
            outcome = qb_solutions.ingest_platform_response(saved, text)
        except qb_solutions.RelayError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return EXIT_FINDINGS
        # The sidecar is data to check, not instructions: the purpose comes from
        # --intent only, and the realm is validated again.
        sent_name = str(meta.get("app_name") or sent_name)
        try:
            meta_host = qb_auth.normalize_realm(meta.get("realm_host")).host
        except qb_auth.AuthError:
            raise SkillInputError("the submission's realm is not a valid realm host")
        if getattr(args, "realm", None) and meta_host != realm_host:
            raise SkillInputError("--realm is not the realm the submission was written for")
        realm_host = meta_host
        pending_id = meta.get("entry")
        pending = next((e for e in cleanup_ledger.load(ledger_path)["entries"]
                        if e.get("id") == pending_id and e.get("outcome") ==
                        cleanup_ledger.PENDING and e.get("relay")
                        and e.get("sent_sha256") == sha256_text(text)
                        and e.get("source_sha256") == source_sha), None)
        if pending is None:
            pending = cleanup_ledger.begin(
                ledger_path, purpose=purpose, app_name=sent_name, source_sha256=source_sha,
                sent_sha256=sha256_text(text), realm_host=realm_host, relay=True)
        entry = cleanup_ledger.finish(ledger_path, pending["id"], outcome, intent=args.intent)
    else:
        entry, outcome = _sent_call(
            ledger_path, purpose=purpose, app_name=sent_name, source_sha=source_sha,
            sent_sha=sha256_text(text), realm_host=realm_host, call=cleanup_ledger.POST_CALL,
            intent=args.intent,
            send=lambda: qb_solutions.create(text, realm_host=realm_host,
                                             timeout=args.timeout))

    lines = _outcome_lines(outcome, name=sent_name, realm_host=realm_host)
    lines += ["", f"ledger entry #{entry['id']} ({entry['purpose']}) in {ledger_path}"]
    if entry["purpose"] == "deliverable":
        lines.append("This is the application you asked for; it is not on the cleanup list.")
    elif outcome.clean and args.intent == "edit":
        lines += ["This is a validation copy of the edit. The deployed application has not "
                  "been touched. Delete the copy when you are done (see `cleanup`)."]
    payload = {**outcome.as_dict(), "ledger": str(ledger_path), "entry": entry["id"],
               "purpose": entry["purpose"], "app_name": sent_name, "realm_host": realm_host}
    emit(payload, lines, args.format)
    return EXIT_OK if outcome.clean else EXIT_FINDINGS


# --------------------------------------------------------------------------
# probe, fetch-deployed, update, cleanup
# --------------------------------------------------------------------------

def _probe(args) -> int:
    spec_path = Path(args.spec)
    spec = _load_spec(args.spec)
    realm_host = _realm_host(args, relay=False)
    ledger_path = _ledger_path(args, spec_path)
    cleanup_ledger.preflight(ledger_path)   # a corrupt ledger refuses before any request
    spec_sha = sha256_file(spec_path)
    stamp = utc_stamp()

    def create(document, name, label):
        text = document_yaml(document)
        _, outcome = _sent_call(
            ledger_path, purpose="probe", app_name=name, source_sha=spec_sha,
            sent_sha=sha256_text(text), realm_host=realm_host, call=cleanup_ledger.POST_CALL,
            intent="", send=lambda: qb_solutions.create(text, realm_host=realm_host,
                                                         timeout=args.timeout))
        return outcome

    report = qb_probe.run_probe(spec, stamp=stamp, create=create, gates=document_gates,
                                compile_fn=compile_app, max_creates=args.max_creates)
    lines = report.lines() + [""] + cleanup_ledger.cleanup_lines(
        cleanup_ledger.load(ledger_path))
    payload = {"creates": report.creates, "floor_failed": report.floor_failed,
               "family": report.localised_family, "items": report.localised_items,
               "exact": report.exact, "stopped": report.stopped, "ledger": str(ledger_path),
               "rungs": [r.__dict__ for r in report.results]}
    emit(payload, lines, args.format)
    return EXIT_OK if (report.localised_family or report.floor_failed) else EXIT_FINDINGS


def _fetch_deployed(args) -> int:
    qb_solutions.validate_solution_id(args.solution_id)
    out = Path(args.out)
    if out.exists() and not args.force:
        raise SkillInputError(f"{out} already exists; pass --force to replace it")
    realm_host = _realm_host(args, relay=False)
    version = args.qbl_version or QBL_VERSION
    status, text, timed_out = qb_solutions.export(
        args.solution_id, realm_host=realm_host, qbl_version=version, timeout=args.timeout)
    if timed_out or not 200 <= status < 300:
        print(f"fetch failed: {'no response within the timeout' if timed_out else f'HTTP {status}'}"
              + ("" if timed_out else f": {text[:300]}"), file=sys.stderr)
        return EXIT_FINDINGS
    out.write_bytes(text.encode("utf-8"))   # exact bytes: the digest is compared later
    qb_update.write_deployed_record(out, solution_id=args.solution_id,
                                    realm_host=realm_host, qbl_version=version)
    emit({"written": str(out), "solution_id": args.solution_id, "realm_host": realm_host},
         [f"wrote {out} ({len(text)} characters) for solution {args.solution_id} on "
          f"{realm_host}", "",
          "Build the edit against it: `build_qbl.py build spec.py --deployed "
          f"{out} --out app.qbl.yaml`."], args.format)
    return EXIT_OK


def _update(args) -> int:
    path = Path(args.document)
    dry_run = bool(getattr(args, "dry_run", False))
    ledger_path = _ledger_path(args, path)
    qb_solutions.validate_solution_id(args.solution_id)
    results: List[str] = []
    try:
        if not dry_run and (not args.solution_id or args.confirm != args.solution_id):
            raise qb_update.UpdateRefused(
                "--confirm must equal the solution id exactly. Re-run with "
                f"`--confirm {args.solution_id}` only after the user has said yes to this "
                "specific update (run `--dry-run` first and show its output).")
        realm_host = _realm_host(args, relay=False)
        cleanup_ledger.preflight(ledger_path)   # refuses before any request
        checked = qb_update.check_guards(
            solution_id=args.solution_id, confirm=args.confirm, document=path,
            ledger_path=ledger_path, realm_host=realm_host,
            require_confirm=not dry_run, results=results)
        document = load_document(str(path))
        gated = document_gates(document)
        if not gated["passed"]:
            raise qb_update.UpdateRefused(
                f"the document now fails {gated['errors']} offline gate error(s); fix it, "
                "validate it again, then update.")
        results.append("the document passes the offline gates")
        # Re-fetch the deployed solution: it must still be the export this was built with.
        fetched = qb_update.read_json(qb_update.deployed_record_path(checked.deployed_export)) or {}
        status, fresh, timed_out = qb_solutions.export(
            args.solution_id, realm_host=realm_host,
            qbl_version=str(fetched.get("qbl_version") or QBL_VERSION), timeout=args.timeout)
        if timed_out or not 200 <= status < 300:
            raise qb_update.UpdateRefused(
                "could not re-fetch the deployed solution to check it "
                + ("(no response within the timeout)" if timed_out else f"(HTTP {status})")
                + "; nothing was changed.")
        if not qb_update.fresh_matches_built(fresh, checked):
            raise qb_update.UpdateRefused(
                "the deployed solution has changed since the export this document was "
                f"built against (its sha256 differs). Run `fetch-deployed {args.solution_id} "
                f"--out {checked.deployed_export.name} --force` and rebuild the document, "
                "then validate and update.")
        results.append("the deployed solution still matches the export it was built against")
        fresh_sha = sha256_text(fresh)
        if not dry_run:
            if not cleanup_ledger.has_recent_dry_run(
                    cleanup_ledger.load(ledger_path), solution_id=args.solution_id,
                    document_sha256=checked.source_sha256, export_sha256=fresh_sha,
                    realm_host=realm_host):
                raise qb_update.UpdateRefused(
                    "no `update --dry-run` was recorded in the ledger in the last 60 "
                    "minutes for this solution id, this document and the deployed solution "
                    "as it is now. Run `update <solutionId> <document> --dry-run`, show its "
                    "output to the user, and get their explicit yes first.")
        with tempfile.TemporaryDirectory() as scratch:
            fresh_path = Path(scratch) / "deployed.qbl.yaml"
            fresh_path.write_bytes(fresh.encode("utf-8"))
            rows = qb_update.deletion_preview(document, load_document(str(fresh_path)))
    except qb_update.UpdateRefused as exc:
        if dry_run and results:
            print("\n".join(["DRY RUN - guards that passed before the refusal", ""]
                            + [f"  ok: {line}" for line in results]), file=sys.stderr)
        print(f"refused: {exc}", file=sys.stderr)
        return EXIT_FINDINGS

    if dry_run:
        cleanup_ledger.record_dry_run(
            ledger_path, solution_id=args.solution_id, document_sha256=checked.source_sha256,
            export_sha256=fresh_sha, realm_host=realm_host)
        lines = [f"DRY RUN - update of solution {args.solution_id} on {realm_host}", "",
                 "Nothing was updated or created; the dry run itself is noted in the ledger "
                 "(it unlocks `update` for 60 minutes, for this document only). The deployed "
                 "solution was read once (GET) to build this preview.", "", "GUARDS"]
        lines += [f"  ok: {line}" for line in results]
        lines += ["  (--confirm is not needed for a dry run)", "", "DELETION PREVIEW"]
        lines += qb_update.preview_lines(rows)
        lines += ["", "To apply it, only after the user has approved this exact preview: "
                  f"`update {args.solution_id} {path} --confirm {args.solution_id}`"]
        emit({"dry_run": True, "sent": False, "guards": results, "deletes": rows,
              "realm_host": realm_host}, lines, args.format)
        return EXIT_OK

    lines = [f"UPDATING solution {args.solution_id} on {realm_host}", ""]
    lines += qb_update.preview_lines(rows)
    print("\n".join(lines))
    text = path.read_text(encoding="utf-8")
    entry, outcome = _sent_call(
        ledger_path, purpose="update", app_name=application_name(document),
        source_sha=checked.source_sha256, sent_sha=checked.source_sha256,
        realm_host=realm_host, call=cleanup_ledger.PUT_CALL, intent="edit",
        send=lambda: qb_solutions.update(
            args.solution_id, text, realm_host=realm_host,
            qbl_version=str(document.get("Version") or QBL_VERSION), timeout=args.timeout))
    out_lines = [""] + _outcome_lines(outcome, name=application_name(document),
                                      realm_host=realm_host)
    out_lines += ["", f"ledger entry #{entry['id']} in {ledger_path}", ""]
    out_lines += cleanup_ledger.cleanup_lines(cleanup_ledger.load(ledger_path))
    emit({**outcome.as_dict(), "deletes": rows, "ledger": str(ledger_path)},
         out_lines, args.format)
    return EXIT_OK if outcome.outcome == qb_solutions.UPDATED else EXIT_FINDINGS


def _cleanup(args) -> int:
    ledger_path = _ledger_path(args)
    if args.mark_deleted:
        marked = cleanup_ledger.mark_deleted(ledger_path, args.mark_deleted)
        if not marked:
            print(f"no undeleted ledger entry matches {args.mark_deleted!r}", file=sys.stderr)
            return EXIT_FINDINGS
        print(f"recorded {marked} entr{'y' if marked == 1 else 'ies'} as deleted")
    ledger = cleanup_ledger.load(ledger_path)
    pending = cleanup_ledger.to_delete(ledger)
    emit({"ledger": str(ledger_path), "pending": pending},
         cleanup_ledger.cleanup_lines(ledger), args.format)
    return EXIT_OK


# --------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------

def _selftest(args) -> int:
    """Prove this Skill's own wiring. Sends nothing and reads no credential."""
    import tempfile

    from qblparser.generation import ChartSpec, FieldSpec, TableSpec

    checks = []
    namespace: Dict[str, Any] = {}
    exec(compile(TEMPLATE, "<template>", "exec"), namespace)  # noqa: S102
    spec = namespace.get("SPEC")
    checks.append(("the starter template is a valid AppSpec",
                   isinstance(spec, AppSpec), type(spec).__name__))

    result = _run_gates(spec)
    checks.append(("the template compiles", result["compiled"], result["reason"][:80]))
    if result["compiled"]:
        tally = counts(result["findings"])
        checks.append(("the template has no offline or conformance errors",
                       tally["errors"] == 0, f"{tally['errors']} error(s)"))
        checks.append(("it matches no known create failure",
                       not [r for r in result["risks"] if r.severity == "error"],
                       str([r.code for r in result["risks"]])))
        text = document_yaml(result["document"])
        checks.append(("it re-emits as QBL YAML", "QB::Application" in text,
                       f"{len(text)} chars"))
        gated = document_gates(result["document"])
        checks.append(("the document-level gates pass it", gated["passed"],
                       f"{gated['errors']} error(s)"))
        ladder = qb_probe.build_ladder(spec, "selftest")
        checks.append(("the probe ladder builds a floor and a rung per family",
                       len(ladder) >= 2 and ladder[0].family == "floor",
                       f"{len(ladder)} rung(s)"))

    refused = _run_gates(
        AppSpec(name="Refusal check",
                tables=[TableSpec("T", fields=[FieldSpec("Amount", "Currency"),
                                               FieldSpec("Kind", "Text")],
                                  charts=[ChartSpec("Share", kind="Donut",
                                                    value_field="Amount",
                                                    category_field="Kind")])]))
    checks.append(("an uncreatable chart kind is refused at compile",
                   not refused["compiled"], refused["reason"][:80] or "compiled!"))

    from qblparser.generation import CriterionSpec, DecisionSpec, RequirementSpec

    traced = _run_gates(
        AppSpec(name="Trace check", tables=[TableSpec("T", fields=[FieldSpec("Name")])],
                requirements=[RequirementSpec("R-1", "x", criteria=[
                    CriterionSpec("R-1.AC1", "untraced")])],
                decisions=[DecisionSpec("D-1", "q", "c")]))
    blocked = sorted({f["Code"] for f in traced["findings"]
                      if f.get("Severity") != "Warning"} & {"REQ001", "DEC001"})
    checks.append(("an untraced criterion and an unconfirmed builder choice block",
                   blocked == ["DEC001", "REQ001"], ", ".join(blocked)))

    checks.append(("a bare realm gains the default domain",
                   qb_auth.normalize_realm("MyRealm").host == "myrealm.quickbase.com", ""))
    try:
        qb_auth.normalize_realm("https://evil/x")
        realm_ok = False
    except qb_auth.AuthError:
        realm_ok = True
    checks.append(("a realm that is not a hostname is refused", realm_ok, ""))

    created = qb_solutions.parse_response(200, json.dumps(
        {"solutionId": "s-1", "apps": [{"id": "bxxxxxxxx1"}]}))
    rejected = qb_solutions.parse_response(400, json.dumps(
        {"errors": [{"code": "BadProperty", "message": "x"}]}))
    hung = qb_solutions.parse_response(0, "", timed_out=True)
    checks.append(("a create answer is read as created, rejected or timed out",
                   (created.clean and created.app_ids == ["bxxxxxxxx1"]
                    and rejected.outcome == qb_solutions.REJECTED
                    and hung.outcome == qb_solutions.TIMEOUT), ""))

    with tempfile.TemporaryDirectory() as scratch:
        ledger = Path(scratch) / cleanup_ledger.LEDGER_NAME
        cleanup_ledger.record(ledger, purpose="attempt", app_name="A", source_sha256="a",
                              sent_sha256="a", realm_host="example.quickbase.com",
                              outcome=created, intent="new")
        cleanup_ledger.record(ledger, purpose="attempt", app_name="A", source_sha256="a",
                              sent_sha256="a", realm_host="example.quickbase.com",
                              outcome=hung, intent="new")
        data = cleanup_ledger.load(ledger)
        checks.append(("the ledger keeps the deliverable off the cleanup list",
                       data["entries"][0]["purpose"] == "deliverable"
                       and [e["outcome"] for e in cleanup_ledger.to_delete(data)] == ["TIMEOUT"],
                       ""))

    lines = ["selftest", ""]
    for name, passed, detail in checks:
        lines.append(f"  {'ok  ' if passed else 'FAIL'} {name}" + (f" ({detail})" if detail else ""))
    failed = [name for name, passed, _ in checks if not passed]
    payload = {"checks": [{"name": n, "passed": p, "detail": d} for n, p, d in checks],
               "failed": failed}
    emit(payload, lines, getattr(args, "format", "text"))
    return EXIT_FINDINGS if failed else EXIT_OK


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _add_gate_arguments(parser) -> None:
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--conformance-codes", default=None,
                        help="comma-separated conformance codes (default: GEN001,GEN003; "
                             "add GEN002 to review a type's shape)")
    parser.add_argument("--deployed", default=None, metavar="EXPORT",
                        help="an export of the solution this document will replace by PUT "
                             "(from fetch-deployed): keeps every deployed id and reports "
                             "what the PUT would delete")
    parser.add_argument("--rename", action="append", metavar="T:NEW=OLD",
                        help="a field the spec renamed, as $Table_X:$Field_New=$Field_Old; "
                             "repeatable")


def _add_call_arguments(parser) -> None:
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--timeout", type=int, default=qb_solutions.DEFAULT_TIMEOUT,
                        help="seconds to wait for Quickbase (default: %(default)s)")
    parser.add_argument("--ledger", default=None,
                        help=f"cleanup ledger (default: ./{cleanup_ledger.LEDGER_NAME}, the "
                             "current directory, for every subcommand)")
    parser.add_argument("--realm", default=None,
                        help="the realm; the stored token's realm is used when omitted. "
                             "Needed only for a relayed create")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Build Quickbase QBL from an AppSpec, and validate it by creating it.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    template = subcommands.add_parser("template", help="print a starter spec file")
    template.add_argument("--out", default=None, help="write here instead of stdout")
    template.add_argument("--force", action="store_true", help="overwrite an existing file")
    template.add_argument("--format", choices=("text", "json"), default="text")
    template.set_defaults(handler=_template)

    check = subcommands.add_parser("check", help="build and gate, writing nothing")
    check.add_argument("spec", help="path to a Python file defining SPEC")
    _add_gate_arguments(check)
    check.set_defaults(handler=_check)

    build = subcommands.add_parser("build", help="build, gate, and write the document")
    build.add_argument("spec", help="path to a Python file defining SPEC")
    build.add_argument("--out", default=None, help="where to write the QBL (default: app.qbl.yaml)")
    _add_gate_arguments(build)
    build.set_defaults(handler=_build)

    drafted = subcommands.add_parser(
        "requirements", help="draft requirements and decisions from a document")
    drafted.add_argument("source", help="a markdown requirements or stories document")
    drafted.add_argument("--out", default=None, help="write the module here")
    drafted.add_argument("--force", action="store_true", help="overwrite --out")
    drafted.add_argument("--id-pattern", default=None,
                         help="regex for a requirement id (default matches US-12, BR-AP-3, REQ-7)")
    drafted.add_argument("--decision-pattern", default=None,
                         help="regex for a decision id (default: D-4)")
    drafted.add_argument("--format", choices=("text", "json"), default="text")
    drafted.set_defaults(handler=_requirements)

    review = subcommands.add_parser("review", help="review a deployed export against its spec")
    review.add_argument("export", help="the solution's QBL export")
    review.add_argument("--spec", default=None, help="the spec it was built from")
    review.add_argument("--digest", default=None, help="write the application digest here")
    review.add_argument("--full-formulas", action="store_true",
                        help="keep formulas whole in the digest")
    review.add_argument("--format", choices=("text", "json"), default="text")
    review.set_defaults(handler=_review)

    create = subcommands.add_parser(
        "create", help="create the document in your realm to validate it (makes a real app)")
    create.add_argument("document", help="a built QBL file")
    create.add_argument("--intent", choices=("new", "edit"), required=True,
                        help="new: the latest clean create is your application. edit: the "
                             "app is created as a clearly named validation copy and "
                             "nothing is a deliverable but the successful update")
    create.add_argument("--name-suffix", nargs="?", const=True, default=None, metavar="TEXT",
                        help="append TEXT (default: a UTC stamp) to the application name")
    create.add_argument("--write-submission", default=None, metavar="FILE",
                        help="relay, step 1: write the exact text to send and stop")
    create.add_argument("--platform-response", default=None, metavar="FILE",
                        help="relay, step 2: ingest the extension's saved JSON response")
    create.add_argument("--submission", default=None, metavar="FILE",
                        help="the file --write-submission wrote (for --platform-response)")
    _add_call_arguments(create)
    create.set_defaults(handler=_create)

    probe = subcommands.add_parser(
        "probe", help="localise a hang or an unnamed failure with a ladder of creates")
    probe.add_argument("spec", help="path to a Python file defining SPEC")
    probe.add_argument("--max-creates", type=int, default=12,
                       help="most applications to create (default: %(default)s)")
    _add_call_arguments(probe)
    probe.set_defaults(handler=_probe)

    fetch = subcommands.add_parser(
        "fetch-deployed", help="export a deployed solution as QBL (read-only)")
    fetch.add_argument("solution_id")
    fetch.add_argument("--out", required=True, help="where to write the export")
    fetch.add_argument("--force", action="store_true", help="overwrite --out")
    fetch.add_argument("--qbl-version", default=None,
                       help=f"QBL version to export (default: {QBL_VERSION})")
    _add_call_arguments(fetch)
    fetch.set_defaults(handler=_fetch_deployed)

    update = subcommands.add_parser(
        "update", help="PUT a validated document over a deployed solution")
    update.add_argument("solution_id")
    update.add_argument("document", help="the document built with --deployed")
    update.add_argument("--confirm", default=None, metavar="SOLUTION_ID",
                        help="the solution id again, typed out; only after the user's yes")
    update.add_argument("--dry-run", action="store_true",
                        help="print the deletion preview and the guard results, and send "
                             "no update (the deployed solution is read once)")
    _add_call_arguments(update)
    update.set_defaults(handler=_update)

    cleanup = subcommands.add_parser(
        "cleanup", help="list the applications you still need to delete")
    cleanup.add_argument("--ledger", default=None,
                         help=f"default: ./{cleanup_ledger.LEDGER_NAME} (the current directory)")
    cleanup.add_argument("--mark-deleted", default=None, metavar="SOLUTION_ID",
                         help="record a deletion you made (or an entry number for a timeout)")
    cleanup.add_argument("--format", choices=("text", "json"), default="text")
    cleanup.set_defaults(handler=_cleanup)

    selftest = subcommands.add_parser("selftest", help="check this Skill's own wiring")
    selftest.add_argument("--format", choices=("text", "json"), default="text")
    selftest.set_defaults(handler=_selftest)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(run_guarded(main))
