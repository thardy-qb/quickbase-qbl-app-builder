"""The record of every platform call that may have created an application.

Creating to validate leaves real applications in the user's realm, and there is
no delete call here: the user deletes them in Quickbase. So every call that may
have created something is written down, with a link, and `cleanup` lists what is
still there.

The entry is written BEFORE the request, as `PENDING`, and the same entry is
updated with the outcome afterwards. A process killed mid-request leaves a
`PENDING` entry, and `cleanup` lists it: the create may have completed.

The ledger is one JSON file for the whole workflow: `qbl-cleanup.json` in the
current working directory, for every subcommand, unless `--ledger` says
otherwise. An entry holds:

    id, time, call, purpose, app_name, source_sha256, sent_sha256, realm_host,
    outcome, solution_id, app_ids, links, errors, warnings, note, relay,
    digest_verified, deleted_at

`purpose` is `attempt`, `validation-copy`, `probe`, `update` or `deliverable`.
Only `deliverable` entries are left out of the cleanup list. With `--intent new`
the deliverable is the latest clean create; with `--intent edit` nothing is a
deliverable except a successful PUT.

Load-modify-save runs under an exclusive lock file, so two processes cannot
lose each other's entries or issue the same entry id.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time as _time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import qb_auth
from qb_common import SkillInputError, utc_now
from qb_solutions import CREATED, ERROR, REJECTED, TIMEOUT, UPDATED, Outcome

LEDGER_NAME = "qbl-cleanup.json"
PURPOSES = ("attempt", "validation-copy", "probe", "update", "deliverable")
PENDING = "PENDING"
PUT_CALL = "PUT update"
POST_CALL = "POST create"

LOCK_STALE_SECONDS = 120
LOCK_WAIT_SECONDS = 30

TIMEOUT_NOTE = ("The platform did not answer within the timeout. The create may have "
                "completed later: look in the realm for an application with exactly "
                "this name, and delete it if it is there.")
ERROR_NOTE = ("The call failed without a readable answer, so an application may exist. "
              "Look in the realm for an application with exactly this name.")
PENDING_NOTE = ("This call was started and no outcome was recorded (the process was "
                "stopped). The create may have completed: look in the realm for an "
                "application with exactly this name, and delete it if it is there.")
PUT_NOTE = ("An update was started and its outcome is unknown. Nothing here needs "
            "deleting; export the deployed solution to see whether it was applied.")


def default_path(document: Optional[Path] = None) -> Path:
    """The one ledger for the workflow: `qbl-cleanup.json` in the working directory."""
    return Path.cwd() / LEDGER_NAME


def app_link(realm_host: str, app_id: str) -> str:
    """A link on a validated host; the host is checked, not trusted."""
    host = qb_auth.normalize_realm(realm_host).host
    return f"https://{host}/nav/app/{app_id}"


def _links(realm_host: str, app_ids: List[str]) -> List[str]:
    try:
        return [app_link(realm_host, app_id) for app_id in app_ids]
    except qb_auth.AuthError:
        return []


# --------------------------------------------------------------------------
# Locking
# --------------------------------------------------------------------------

@contextlib.contextmanager
def locked(path: Path) -> Iterator[None]:
    """Hold an exclusive lock file beside the ledger. Stdlib only, any platform.

    The lock is `<ledger>.lock`, created with `O_CREAT | O_EXCL`. One older than
    `LOCK_STALE_SECONDS` belongs to a process that died and is removed.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = Path(str(path) + ".lock")
    deadline = _time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        try:
            descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(descriptor, str(os.getpid()).encode())
            os.close(descriptor)
            break
        except FileExistsError:
            try:
                if _time.time() - lock.stat().st_mtime > LOCK_STALE_SECONDS:
                    lock.unlink()
                    continue
            except OSError:
                continue
            if _time.monotonic() > deadline:
                raise SkillInputError(f"the ledger is locked by another process ({lock}); "
                                      "try again, or delete the lock file if no other "
                                      "command is running")
            _time.sleep(0.05)
    try:
        yield
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


def load(path: Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {"version": 1, "entries": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SkillInputError(f"{path} is not a readable ledger: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise SkillInputError(f"{path} is not a cleanup ledger")
    if "dry_runs" in data and not isinstance(data["dry_runs"], list):
        raise SkillInputError(f"{path} is not a cleanup ledger")
    return data


def save(path: Path, ledger: Dict[str, Any]) -> None:
    """Write the ledger atomically, so a crash cannot leave half a record."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".qbl-ledger-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(ledger, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


DRY_RUN_VALID_SECONDS = 3600


def record_dry_run(path: Path, *, solution_id: str, document_sha256: str,
                   export_sha256: str, realm_host: str) -> Dict[str, Any]:
    """Note that `update --dry-run` ran for exactly this solution, document and export."""
    with locked(path):
        ledger = load(path)
        item = {"time": utc_now(), "solution_id": solution_id,
                "document_sha256": document_sha256, "export_sha256": export_sha256,
                "realm_host": realm_host}
        ledger.setdefault("dry_runs", []).append(item)
        save(path, ledger)
    return item


def has_recent_dry_run(ledger: Dict[str, Any], *, solution_id: str, document_sha256: str,
                       export_sha256: str, realm_host: str,
                       within: int = DRY_RUN_VALID_SECONDS) -> bool:
    """A dry run for the same solution, document and fresh export in the last hour."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    for item in ledger.get("dry_runs") or []:
        if not isinstance(item, dict):
            continue
        if (item.get("solution_id"), item.get("document_sha256"), item.get("export_sha256"),
                item.get("realm_host")) != (solution_id, document_sha256, export_sha256,
                                            realm_host):
            continue
        try:
            when = datetime.fromisoformat(str(item.get("time")))
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if 0 <= (now - when).total_seconds() <= within:
            return True
    return False


def preflight(path: Path) -> Dict[str, Any]:
    """Load and validate the ledger. Call before any request: a bad ledger refuses here."""
    return load(path)


def _next_id(ledger: Dict[str, Any]) -> int:
    ids = [entry.get("id") for entry in ledger["entries"]
           if isinstance(entry.get("id"), int) and not isinstance(entry.get("id"), bool)]
    return (max(ids) if ids else 0) + 1


def begin(path: Path, *, purpose: str, app_name: str, source_sha256: str,
          sent_sha256: str, realm_host: str, call: str = POST_CALL,
          relay: bool = False) -> Dict[str, Any]:
    """Write a `PENDING` entry before the request is made, and return it."""
    if purpose not in PURPOSES:
        raise ValueError(f"unknown purpose {purpose!r}")
    with locked(path):
        ledger = load(path)
        entry = {
            "id": _next_id(ledger),
            "time": utc_now(),
            "call": call,
            "purpose": purpose,
            "app_name": app_name,
            "source_sha256": source_sha256,
            "sent_sha256": sent_sha256,
            "realm_host": realm_host,
            "outcome": PENDING,
            "http": 0,
            "solution_id": "",
            "app_ids": [],
            "links": [],
            "errors": 0,
            "warnings": 0,
            "note": PUT_NOTE if call == PUT_CALL else PENDING_NOTE,
            "relay": bool(relay),
            "digest_verified": False,
            "deleted_at": "",
        }
        ledger["entries"].append(entry)
        save(path, ledger)
    return dict(entry)


def discard(path: Path, entry_id: int) -> None:
    """Remove a `PENDING` entry whose request provably never left (no credential)."""
    with locked(path):
        ledger = load(path)
        kept = [e for e in ledger["entries"]
                if not (e.get("id") == entry_id and e.get("outcome") == PENDING)]
        if len(kept) != len(ledger["entries"]):
            ledger["entries"] = kept
            save(path, ledger)


def finish(path: Path, entry_id: int, outcome: Outcome, *, intent: str = "",
           ) -> Dict[str, Any]:
    """Update the `PENDING` entry `entry_id` with the outcome.

    Purpose rules: a clean create with `--intent new` becomes the deliverable and
    any earlier create-deliverable goes back on the cleanup list as an attempt;
    with `--intent edit` a create is never a deliverable; a PUT is the
    deliverable only when it succeeded.
    """
    with locked(path):
        ledger = load(path)
        entry = next((e for e in ledger["entries"] if e.get("id") == entry_id), None)
        if entry is None:
            raise SkillInputError(f"ledger entry #{entry_id} is missing from {path}")
        call = entry.get("call", POST_CALL)
        purpose = entry.get("purpose", "attempt")
        note = ""
        if call == PUT_CALL:
            purpose = "deliverable" if outcome.outcome == "UPDATED" else "update"
            if outcome.outcome in (TIMEOUT, ERROR):
                note = PUT_NOTE
        else:
            if purpose == "deliverable":
                purpose = "attempt"
            if purpose == "attempt" and intent == "new" and outcome.clean:
                for other in ledger["entries"]:
                    if (other is not entry and other.get("purpose") == "deliverable"
                            and other.get("call", POST_CALL) == POST_CALL):
                        other["purpose"] = "attempt"
                purpose = "deliverable"
            if outcome.outcome == TIMEOUT:
                note = TIMEOUT_NOTE
            elif outcome.outcome == ERROR:
                note = ERROR_NOTE
        entry.update({
            "purpose": purpose,
            "outcome": outcome.outcome,
            "http": outcome.http,
            "solution_id": outcome.solution_id,
            "app_ids": list(outcome.app_ids),
            "links": _links(entry.get("realm_host", ""), list(outcome.app_ids)),
            "errors": outcome.error_count,
            "warnings": outcome.warning_count,
            "note": note,
            "digest_verified": bool(getattr(outcome, "digest_verified", False)),
        })
        save(path, ledger)
        return dict(entry)


def record(path: Path, *, purpose: str, app_name: str, source_sha256: str,
           sent_sha256: str, realm_host: str, outcome: Outcome,
           intent: str = "", call: str = POST_CALL, relay: bool = False) -> Dict[str, Any]:
    """`begin` then `finish`, for an outcome already in hand (a relayed answer)."""
    entry = begin(path, purpose=purpose, app_name=app_name, source_sha256=source_sha256,
                  sent_sha256=sent_sha256, realm_host=realm_host, call=call, relay=relay)
    return finish(path, entry["id"], outcome, intent=intent)


def to_delete(ledger: Dict[str, Any]) -> List[Dict[str, Any]]:
    """What may still exist and is not the deliverable, newest first.

    Create calls only (a PUT makes nothing to delete): `CREATED`, `TIMEOUT`,
    `ERROR`, `PENDING`, and a `REJECTED` entry that carries a solution id or app
    ids.
    """
    def may_exist(entry: Dict[str, Any]) -> bool:
        outcome = entry.get("outcome")
        if outcome in (CREATED, TIMEOUT, ERROR, PENDING):
            return True
        return outcome == REJECTED and bool(entry.get("solution_id") or entry.get("app_ids"))

    # A solution that a later PUT updated is a deployed application, whatever
    # purpose its create was left with: never list it for deletion.
    updated = {entry.get("solution_id") for entry in ledger["entries"]
               if entry.get("call") == PUT_CALL and entry.get("outcome") == UPDATED
               and entry.get("solution_id")}
    pending = [entry for entry in ledger["entries"]
               if entry.get("purpose") != "deliverable"
               and entry.get("call", POST_CALL) == POST_CALL
               and not (entry.get("solution_id") and entry.get("solution_id") in updated)
               and may_exist(entry) and not entry.get("deleted_at")]
    return sorted(pending, key=lambda entry: (entry.get("time", ""), entry.get("id", 0)),
                  reverse=True)


def unfinished_updates(ledger: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [entry for entry in ledger["entries"]
            if entry.get("call") == PUT_CALL
            and entry.get("outcome") in (PENDING, TIMEOUT, ERROR)]


def mark_deleted(path: Path, key: str) -> int:
    """Record that the user deleted the application(s) for a solution id.

    A call that timed out has no solution id, so an entry number (shown in the
    cleanup list as `#<n>`) is accepted too.
    """
    key = key.lstrip("#")
    with locked(path):
        ledger = load(path)
        marked = 0
        for entry in ledger["entries"]:
            matches = (entry.get("solution_id") == key if not key.isdigit()
                       else entry.get("id") == int(key))
            if matches and not entry.get("deleted_at"):
                entry["deleted_at"] = utc_now()
                marked += 1
        if marked:
            save(path, ledger)
    return marked


def clean_create_for(ledger: Dict[str, Any], source_sha256: str) -> Optional[Dict[str, Any]]:
    """The newest CREATED entry with zero errors for exactly this source document.

    A relayed entry counts only if the extension's response carried a digest that
    matched. `qb_update` adds the stricter checks an update needs.
    """
    for entry in reversed(ledger["entries"]):
        if (entry.get("outcome") == CREATED and entry.get("errors", 1) == 0
                and entry.get("source_sha256") == source_sha256
                and entry.get("call", POST_CALL) == POST_CALL
                and (not entry.get("relay") or entry.get("digest_verified"))):
            return entry
    return None


def _same_name_known_apps(ledger: Dict[str, Any], entry: Dict[str, Any]) -> List[str]:
    """Known applications sharing a link-less entry's name, as `#n <link or id>`.

    A create that timed out and its corrected re-create carry the same name, so
    "delete the app with exactly this name" could point at the deliverable.
    """
    out: List[str] = []
    for other in ledger["entries"]:
        if (other is entry or other.get("app_name") != entry.get("app_name")
                or other.get("outcome") != CREATED or other.get("deleted_at")):
            continue
        where = ", ".join(other.get("links") or []) or (
            f"solution {other['solution_id']}" if other.get("solution_id") else "")
        if where:
            out.append(f"#{other.get('id')} ({other.get('purpose')}) {where}")
    return out


def cleanup_lines(ledger: Dict[str, Any]) -> List[str]:
    pending = to_delete(ledger)
    updates = unfinished_updates(ledger)
    lines: List[str] = ["CLEANUP", ""]
    if not pending:
        lines.append("  Nothing is waiting to be deleted.")
    else:
        lines += [f"  {len(pending)} call(s) may have left an application in your realm. "
                  "There is no delete call here: delete each one in Quickbase, newest first.",
                  ""]
    for entry in pending:
        lines.append(f"  #{entry['id']}  {entry['time']}  {entry['purpose']}  {entry['outcome']}  "
                     f"{entry['app_name']!r}")
        if entry.get("solution_id"):
            lines.append(f"    solution id: {entry['solution_id']}")
        for link in entry.get("links") or []:
            lines.append(f"    {link}")
        if not entry.get("links") and entry.get("outcome") != CREATED:
            lines.append(f"    no link: {entry.get('note') or 'search the realm for the name'}")
            known = _same_name_known_apps(ledger, entry)
            if known:
                lines.append("    CAREFUL: an application with this exact name is already "
                             "accounted for and is not this one: "
                             + ", ".join(known)
                             + ". Delete only another application with this name.")
        elif entry.get("note"):
            lines.append(f"    {entry['note']}")
        lines.append("")
    if pending:
        lines.append("  After deleting one, record it with "
                     "`build_qbl.py cleanup --mark-deleted <solutionId or #>`.")
    if updates:
        lines += ["", "  UPDATES WITH NO CONFIRMED OUTCOME", ""]
        for entry in updates:
            lines.append(f"  #{entry['id']}  {entry['time']}  {entry['outcome']}  "
                         f"{entry['app_name']!r}  {entry.get('note') or PUT_NOTE}")
    return lines
