#!/usr/bin/env python3
"""Shared helpers for the scripts in this Skill: loading, gates, reporting.

Nothing in this module talks to Quickbase and nothing in it touches a
credential. Those live in `qb_solutions.py` and `qb_auth.py`.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
VENDOR_DIR = SCRIPT_DIR / "vendor"  # third-party code only (PyYAML)

# `qblparser` is the Skill's own package in this directory; PyYAML is under
# `vendor/`. Both go on the path whatever the interpreter's isolation flags.
for _path in (VENDOR_DIR, SCRIPT_DIR):
    if _path.is_dir() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from qblparser import QBLParseError, load_qbl_file, validate_qbl_document  # noqa: E402
from qblparser.generation import check_behaviour, check_conformance, create_risks  # noqa: E402
from qblparser.utils.qbl_yaml import dump_qbl_yaml  # noqa: E402
from qblparser.validators.remediation import remediation_for  # noqa: E402

MAX_INPUT_BYTES = 100 * 1024 * 1024
SEVERITY_ORDER = {"error": 0, "warning": 1, "note": 2}

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_INPUT = 2
EXIT_INTERNAL = 3


class SkillInputError(RuntimeError):
    """Something about the user's input, stated so it can be repeated to them."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def utc_stamp() -> str:
    """A compact UTC stamp, safe inside an application name."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H%MZ")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# Loading and writing
# --------------------------------------------------------------------------

def load_document(path: str) -> Dict[str, Any]:
    """Load a QBL document, including the two-document shape exports have."""
    file_path = Path(path)
    if not file_path.is_file():
        raise SkillInputError(f"no such file: {path}")
    size = file_path.stat().st_size
    if size == 0:
        raise SkillInputError(f"{file_path.name} is empty")
    if size > MAX_INPUT_BYTES:
        raise SkillInputError(f"{file_path.name} is over the "
                              f"{MAX_INPUT_BYTES // 1_048_576} MB limit")
    try:
        document = load_qbl_file(str(file_path))
    except QBLParseError as exc:
        raise SkillInputError(f"{file_path.name} is not loadable QBL: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise SkillInputError(f"{file_path.name} could not be read: {exc}") from exc
    if not isinstance(document, Mapping) or "Resources" not in document:
        raise SkillInputError(f"{file_path.name} carries no `Resources` key, so it "
                              "is not a QBL solution")
    return dict(document)


def document_yaml(document: Mapping[str, Any]) -> str:
    buffer = io.StringIO()
    dump_qbl_yaml(document, buffer)
    return buffer.getvalue()


def find_application(document: Mapping[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """The `QB::Application` resource: `(logical id, node)`."""
    for key, node in (document.get("Resources") or {}).items():
        if isinstance(node, Mapping) and node.get("Type") == "QB::Application":
            return str(key), node
    raise SkillInputError("the document has no QB::Application resource")


def application_name(document: Mapping[str, Any]) -> str:
    _, node = find_application(document)
    return str((node.get("Properties") or {}).get("Name", ""))


def renamed_text(document: Mapping[str, Any], new_name: str) -> str:
    """The document as YAML with the application's name replaced."""
    import copy

    working = copy.deepcopy(dict(document))
    _, node = find_application(working)
    node.setdefault("Properties", {})["Name"] = new_name
    return document_yaml(working)


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------

def normalize(finding: Mapping[str, Any]) -> Dict[str, Any]:
    severity = str(finding.get("Severity", finding.get("severity", "error"))).lower()
    if severity not in SEVERITY_ORDER:
        severity = "error"
    return {
        "code": finding.get("Code") or finding.get("code") or "",
        "severity": severity,
        "problem": str(finding.get("Problem") or finding.get("problem") or "").strip(),
        "where": str(finding.get("Path") or finding.get("Location")
                     or finding.get("LogicalID") or "").strip(),
        "fix": str(finding.get("Fix") or finding.get("fix") or "").strip(),
    }


def counts(findings: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    normalized = [normalize(finding) for finding in findings]
    return {
        "errors": sum(1 for f in normalized if f["severity"] == "error"),
        "warnings": sum(1 for f in normalized if f["severity"] == "warning"),
        "total": len(normalized),
    }


def _remediation(code: str) -> str:
    if not code:
        return ""
    try:
        return remediation_for(code) or ""
    except Exception:  # noqa: BLE001
        return ""


def group_by_code(findings: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse repeats and attach the fix, worst first."""
    buckets: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for finding in sorted((normalize(f) for f in findings),
                          key=lambda f: (SEVERITY_ORDER[f["severity"]], f["code"], f["where"])):
        key = (finding["code"], finding["severity"])
        bucket = buckets.setdefault(key, {
            "code": finding["code"], "severity": finding["severity"], "count": 0,
            "problem": finding["problem"], "examples": [],
            "fix": _remediation(finding["code"]) or finding["fix"],
        })
        bucket["count"] += 1
        if len(bucket["examples"]) < 3 and finding["where"]:
            bucket["examples"].append(finding["where"])
    return sorted(buckets.values(),
                  key=lambda b: (SEVERITY_ORDER[b["severity"]], -b["count"], b["code"]))


def render_groups(groups: Sequence[Mapping[str, Any]], *, limit: int = 40) -> List[str]:
    out: List[str] = []
    for group in groups[:limit]:
        head = f"[{group['severity']}] {group['code']}"
        if group["count"] > 1:
            head += f" x{group['count']}"
        out.append(head)
        out.append(f"    {group['problem']}")
        if group["examples"]:
            out.append(f"    where: {', '.join(group['examples'])}"
                       + (" ..." if group["count"] > len(group["examples"]) else ""))
        if group["fix"]:
            fix_lines = group["fix"].strip().splitlines()
            out.append(f"    fix: {fix_lines[0]}")
            out.extend(f"         {line}" for line in fix_lines[1:])
        out.append("")
    if len(groups) > limit:
        out.append(f"... and {len(groups) - limit} more finding group(s); "
                   "re-run with --format json for all of them")
    return out


def render_gate_line(name: str, findings: Sequence[Mapping[str, Any]]) -> str:
    tally = counts(findings)
    verdict = "FAIL" if tally["errors"] else ("PASS" if not tally["warnings"] else "PASS*")
    return (f"  {name:22} {verdict:9} {tally['errors']} error(s), "
            f"{tally['warnings']} warning(s)")


# --------------------------------------------------------------------------
# The document-level gates
# --------------------------------------------------------------------------

def document_gates(document: Mapping[str, Any]) -> Dict[str, Any]:
    """Every gate that needs only the finished document.

    The spec-level gates (requirements, design review, code page review) run in
    `build_qbl.py build`, which has the spec. This is the set `create` can
    re-run from the file alone, so a document edited by hand after it was built
    is still checked before it is sent.
    """
    findings = [dict(f) for f in validate_qbl_document(document)]
    findings += [dict(f) for f in check_conformance(document, codes=("GEN001", "GEN003"))]
    findings += [dict(f) for f in check_behaviour(document)]
    risks = create_risks(document)
    risk_errors = [risk for risk in risks if risk.severity == "error"]
    tally = counts(findings)
    return {
        "findings": findings,
        "risks": risks,
        "errors": tally["errors"] + len(risk_errors),
        "passed": not (tally["errors"] or risk_errors),
    }


def risk_lines(risks) -> List[str]:
    lines: List[str] = []
    for risk in risks:
        lines.append(f"  [{risk.severity}] {risk.code} - {risk.location or 'document root'}")
        lines.append(f"    {risk.problem}")
        lines.append(f"    Fix: {risk.fix}")
        lines.append("")
    return lines


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def emit(payload: Mapping[str, Any], text: Sequence[str], fmt: str) -> None:
    if fmt == "json":
        json.dump(payload, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        sys.stdout.write("\n".join(text).rstrip() + "\n")


def run_guarded(main_function, argv: Optional[Sequence[str]] = None) -> int:
    """Turn an exception into an exit code and a sentence, not a traceback."""
    try:
        return main_function(argv)
    except SkillInputError as exc:
        print(f"input: {exc}", file=sys.stderr)
        return EXIT_INPUT
    except KeyboardInterrupt:  # pragma: no cover
        return EXIT_INTERNAL
    except Exception as exc:  # noqa: BLE001
        print(f"internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_INTERNAL
