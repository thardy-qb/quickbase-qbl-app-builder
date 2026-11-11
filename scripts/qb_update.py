#!/usr/bin/env python3
"""The guards on replacing a deployed solution, and the sidecar records they read.

A PUT replaces a solution wholesale and deletes whatever the document omits,
field data included. So `update` goes ahead only when all of these hold:

    1. `--confirm` equals the solution id, typed out;
    2. the ledger holds a clean create (CREATED, zero errors) of this exact
       source document: same source sha256, a sent text that is the source with
       only the application name changed, the realm the update will use, a
       create newer than the deployed export, and, if it was relayed, a
       response that carried a matching document digest;
    3. the document was built with `--deployed` against an export of this very
       solution, fetched with `fetch-deployed`, and neither file has changed
       since;
    4. (in `build_qbl.py`, just before the PUT) the solution as it is deployed
       right now still hashes to that export.

Two small JSON records make (3) checkable. `fetch-deployed` writes
`<export>.deployed.json` (solution id, realm, digest of the export). `build`
writes `<document>.build.json` (digest of the document and which deployed export
it was reconciled against).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import cleanup_ledger
from qb_common import (SkillInputError, application_name, load_document, renamed_text,
                       sha256_file, sha256_text, utc_now)


class UpdateRefused(RuntimeError):
    """The update must not be sent. The message is what to tell the user."""


def deployed_record_path(export: Path) -> Path:
    return Path(str(export) + ".deployed.json")


def build_record_path(document: Path) -> Path:
    return Path(str(document) + ".build.json")


def write_deployed_record(export: Path, *, solution_id: str, realm_host: str,
                          qbl_version: str) -> Dict[str, Any]:
    record = {"solution_id": solution_id, "realm_host": realm_host,
              "qbl_version": qbl_version, "export_sha256": sha256_file(export),
              "fetched_at": utc_now()}
    deployed_record_path(export).write_text(json.dumps(record, indent=2) + "\n",
                                            encoding="utf-8")
    return record


def _parse_time(text: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(text))
    except ValueError:
        return None


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_build_record(document: Path, *, deployed: Optional[Path]) -> Dict[str, Any]:
    """Record the build. `deployed` is the export it was reconciled against, if any."""
    record: Dict[str, Any] = {"document": str(document),
                              "document_sha256": sha256_file(document),
                              "built_at": utc_now(), "deployed": None}
    if deployed is not None:
        fetched = read_json(deployed_record_path(deployed)) or {}
        record["deployed"] = {
            "path": str(Path(deployed).resolve()),
            "export_sha256": sha256_file(deployed),
            # Empty when the export was not fetched with `fetch-deployed`; the
            # update then refuses, because nothing says which solution it is.
            "solution_id": fetched.get("solution_id", ""),
            "realm_host": fetched.get("realm_host", ""),
            "fetched_sha256_matches": fetched.get("export_sha256") == sha256_file(deployed),
            "fetched_at": fetched.get("fetched_at", ""),
        }
    build_record_path(document).write_text(json.dumps(record, indent=2) + "\n",
                                           encoding="utf-8")
    return record


@dataclass
class Checked:
    source_sha256: str
    deployed_export: Path
    realm_host: str
    ledger_entry: Dict[str, Any]
    reasons: List[str] = field(default_factory=list)


def _matching_create(ledger: Dict[str, Any], *, source_sha: str, document: Path,
                     realm_host: str, fetched_at: str) -> Optional[Dict[str, Any]]:
    """The newest ledger create that proves this document builds, for this update."""
    source = load_document(str(document))
    source_text = Path(document).read_text(encoding="utf-8")
    base_name = application_name(source)
    floor = _parse_time(fetched_at)
    for entry in reversed(ledger["entries"]):
        if not (entry.get("outcome") == cleanup_ledger.CREATED
                and entry.get("errors", 1) == 0
                and entry.get("call", cleanup_ledger.POST_CALL) == cleanup_ledger.POST_CALL
                and entry.get("source_sha256") == source_sha
                and entry.get("realm_host") == realm_host):
            continue
        if entry.get("relay") and not entry.get("digest_verified"):
            continue
        name = entry.get("app_name") or base_name
        expected = source_text if name == base_name else renamed_text(source, name)
        if entry.get("sent_sha256") not in (sha256_text(expected),):
            continue
        created = _parse_time(entry.get("time"))
        if floor is None or created is None or created < floor:
            continue
        return entry
    return None


def check_guards(*, solution_id: str, confirm: Optional[str], document: Path,
                 ledger_path: Path, realm_host: str, require_confirm: bool = True,
                 results: Optional[List[str]] = None) -> Checked:
    """Raise `UpdateRefused` unless every guard holds.

    `realm_host` is the realm the update will be sent to. When `results` is
    given, each guard that passes appends one line to it (for `--dry-run`).
    """
    results = results if results is not None else []
    if require_confirm:
        if not solution_id or confirm != solution_id:
            raise UpdateRefused(
                "--confirm must equal the solution id exactly. Re-run with "
                f"`--confirm {solution_id}` only after the user has said yes to this "
                "specific update.")
        results.append("confirmation equals the solution id")

    source_sha = sha256_file(document)
    ledger = cleanup_ledger.load(ledger_path)
    results.append("ledger is readable")

    record = read_json(build_record_path(document))
    if not record or record.get("document_sha256") != source_sha:
        raise UpdateRefused(
            f"no build record matches this document ({build_record_path(document).name}). "
            "Build it again with `build_qbl.py build ... --deployed <export>`; an edited "
            "file needs a fresh build.")
    results.append("build record matches this document's sha256")
    deployed = record.get("deployed")
    if not deployed:
        raise UpdateRefused(
            "this document was not built with --deployed, so its ids are not "
            "reconciled with the deployed solution and the PUT could move ids or delete "
            "fields. Fetch the export with `fetch-deployed` and build with --deployed.")
    if deployed.get("solution_id") != solution_id:
        raise UpdateRefused(
            f"the deployed export it was built against belongs to solution "
            f"{deployed.get('solution_id') or '(unknown: not fetched with fetch-deployed)'}, "
            f"not {solution_id}.")
    export_path = Path(deployed.get("path", ""))
    if not export_path.is_file() or sha256_file(export_path) != deployed.get("export_sha256"):
        raise UpdateRefused(
            "the deployed export recorded at build time is missing or has changed. "
            "Fetch it again and rebuild.")
    if not deployed.get("fetched_sha256_matches", False):
        raise UpdateRefused(
            "the deployed export was edited after it was fetched. Fetch it again.")
    if deployed.get("realm_host") and deployed.get("realm_host") != realm_host:
        raise UpdateRefused(
            f"the deployed export came from {deployed.get('realm_host')}, but this "
            f"update would go to {realm_host}.")
    results.append("built against this solution's own export, unchanged since")

    entry = _matching_create(ledger, source_sha=source_sha, document=document,
                             realm_host=realm_host, fetched_at=deployed.get("fetched_at", ""))
    if entry is None:
        raise UpdateRefused(
            "the ledger holds no clean create that proves this document for this update: "
            "it needs a CREATED entry with zero errors, the same source sha256, the same "
            "sent text apart from the application name, realm " + realm_host + ", made "
            "after the deployed export was fetched (and, if relayed, with a matching "
            "document digest). Create a validation copy with `create --intent edit` until "
            "it is clean, then update. If the file changed, validate it again.")
    results.append(f"clean create #{entry.get('id')} matches the source, sent text, realm "
                   "and export")
    return Checked(source_sha, export_path, deployed.get("realm_host", ""), entry)


def fresh_matches_built(fresh_text: str, checked: "Checked") -> bool:
    """Does the solution as deployed now hash to the export the document was built with?"""
    return sha256_text(fresh_text) == sha256_file(checked.deployed_export)


def deletion_preview(document: Dict[str, Any], deployed: Dict[str, Any]) -> List[Dict[str, Any]]:
    """What the PUT deletes: nodes in the deployed export that the document omits."""
    from qblparser.generation import plan_update

    plan = plan_update(document, deployed)
    flagged = {f["Path"]: f["Code"] for f in plan.findings() if f.get("Path")}
    rows = []
    for path, qbl_type in plan.removed:
        key = " > ".join(path)
        rows.append({"path": key, "node": path[-1], "type": qbl_type,
                     "deletes_data": flagged.get(key) == "UPD001"})
    return rows


def preview_lines(rows: List[Dict[str, Any]]) -> List[str]:
    if not rows:
        return ["  The PUT deletes nothing the deployed solution has."]
    lines = [f"  The PUT deletes {len(rows)} node(s) the document omits:"]
    for row in rows:
        suffix = "   <- DELETES ITS DATA" if row["deletes_data"] else ""
        lines.append(f"    {row['type']}  {row['path']}{suffix}")
    return lines


def require_ledger_exists(path: Path) -> None:
    if not Path(path).exists():
        raise SkillInputError(f"no ledger at {path}")
