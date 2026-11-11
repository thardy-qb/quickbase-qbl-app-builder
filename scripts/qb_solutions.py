#!/usr/bin/env python3
"""A small client for the Quickbase Solutions API, and the reading of its answers.

    POST /v1/solutions        create a solution from QBL
    PUT  /v1/solutions/{id}   replace a solution wholesale
    GET  /v1/solutions/{id}   export a solution as QBL

Standard library only (`urllib`). Each call returns an `Outcome` rather than
raising for anything the platform did: a create that hangs, or that never
answers within the timeout, is a result to record, not an exception, because it
may still finish on the server afterwards.

`parse_response` is pure. `ingest_platform_response` reads the answer saved by
a Claude extension that made the call on this Skill's behalf, and turns it into
the same `Outcome`.
"""

from __future__ import annotations

import json
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

import qb_auth
from qb_common import SkillInputError, sha256_text

API_BASE = "https://api.quickbase.com/v1/solutions"

CREATED = "CREATED"
REJECTED = "REJECTED"
TIMEOUT = "TIMEOUT"
ERROR = "ERROR"
UPDATED = "UPDATED"

DEFAULT_TIMEOUT = 180


class RelayError(RuntimeError):
    """A relayed platform response that cannot be tied to the submission."""


@dataclass
class Outcome:
    outcome: str
    http: int = 0
    solution_id: str = ""
    app_ids: List[str] = field(default_factory=list)
    findings: List[Dict[str, Any]] = field(default_factory=list)
    detail: str = ""
    raw: str = ""
    hints: List[str] = field(default_factory=list)
    # True only for a relayed answer that carried a digest equal to the digest of
    # the text this Skill wrote. A direct call needs no digest and leaves it False.
    digest_verified: bool = False

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if str(f.get("Severity", "Error")).lower() != "warning")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if str(f.get("Severity", "")).lower() == "warning")

    @property
    def clean(self) -> bool:
        return self.outcome == CREATED and self.error_count == 0

    def as_dict(self) -> Dict[str, Any]:
        return {"outcome": self.outcome, "http": self.http, "solution_id": self.solution_id,
                "app_ids": list(self.app_ids), "errors": self.error_count,
                "warnings": self.warning_count, "findings": self.findings,
                "detail": self.detail, "hints": self.hints}


# --------------------------------------------------------------------------
# Reading an answer
# --------------------------------------------------------------------------

_APP_KEYS = ("appId", "appIds", "app_id", "app_ids", "applicationId", "applicationIds",
             "apps", "applications")
_ID_KEYS = ("id", "appId", "applicationId", "dbid")
# Where the ids are found: a create answers
# `createdResources: {apps: {<logical id>: <dbid>}, pipelines: {}}` and a PUT
# answers `resources: {apps: {<logical id>: <dbid>}}`.
_RESOURCE_KEYS = ("createdResources", "resources")
_DBID = re.compile(r"[a-z0-9]{6,12}")


def _collect_ids(value: Any) -> List[str]:
    found: List[str] = []
    if isinstance(value, str):
        if value.strip():
            found.append(value.strip())
    elif isinstance(value, Mapping):
        for key in _ID_KEYS:
            if isinstance(value.get(key), str) and value[key].strip():
                found.append(value[key].strip())
                break
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(_collect_ids(item))
    return found


def extract_app_ids(payload: Mapping[str, Any]) -> List[str]:
    """App ids from a create response, tolerant of where the platform puts them."""
    ids: List[str] = []
    for key in _RESOURCE_KEYS:
        resources = payload.get(key)
        if isinstance(resources, Mapping) and isinstance(resources.get("apps"), Mapping):
            ids.extend(str(value).strip() for value in resources["apps"].values()
                       if isinstance(value, str) and _DBID.fullmatch(value.strip()))
    for key in _APP_KEYS:
        if key in payload:
            ids.extend(_collect_ids(payload[key]))
    seen: List[str] = []
    for item in ids:
        if item not in seen:
            seen.append(item)
    return seen


def _as_finding(item: Any, severity: str) -> Dict[str, Any]:
    if isinstance(item, Mapping):
        code = str(item.get("code") or item.get("type") or item.get("errorCode") or "Error")
        message = str(item.get("message") or item.get("description") or item.get("detail")
                      or item.get("raw") or json.dumps(item, default=str))
        where = str(item.get("logicalId") or item.get("logicalID") or item.get("path")
                    or item.get("location") or "")
    else:
        code, message, where = "Error", str(item), ""
        # A platform error as a string, for example:
        # "BadProperty: SummarizeBy in $Chart_X at Line 783, Column 33"
        match = _PLATFORM_ERROR.match(message)
        if match:
            code = match.group("code")
            where = match.group("where") or ""
    return {"Code": f"PLT-{code}", "Severity": severity, "Problem": message, "Location": where}


_PLATFORM_ERROR = re.compile(r"(?P<code>[A-Z][A-Za-z]+): .*?(?: in (?P<where>\$\S+))?"
                             r"(?: at Line \d+, Column \d+)?$")


def _platform_lists(payload: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    """Where `errors` and `warnings` live: at the top, or (on a 400) under `description`.

    A typical rejection: `{"message": "Bad Request", "description": {"warnings": [],
    "errors": ["BadProperty: ... at Line 783, Column 33", ...]}}`.
    """
    nested = payload.get("description")
    if isinstance(nested, Mapping) and ("errors" in nested or "warnings" in nested):
        return [payload, nested]
    return [payload]


def _hints(text: str) -> List[str]:
    try:
        from qblparser.generation import classify_platform_error

        return [f"{d.means} Next: {d.next_step}" for d in classify_platform_error(text)[:3]]
    except Exception:  # noqa: BLE001
        return []


def parse_response(status: int, text: str, *, timed_out: bool = False,
                   expect_solution_id: bool = True, success_outcome: str = CREATED) -> Outcome:
    """Turn `(HTTP status, body)` into an `Outcome`. Pure; no network."""
    if timed_out:
        return Outcome(TIMEOUT, http=0, detail=text or "no response within the timeout",
                       raw="")
    raw = (text or "")[:4000]
    if (200 <= status < 300 and not expect_solution_id and not (text or "").strip()):
        return Outcome(success_outcome, http=status)
    try:
        payload = json.loads(text) if text else None
    except (TypeError, ValueError):
        payload = None
    if not isinstance(payload, Mapping):
        return Outcome(ERROR, http=status, detail=f"HTTP {status}: unreadable response",
                       raw=raw, hints=_hints(raw))

    findings: List[Dict[str, Any]] = []
    for source in _platform_lists(payload):
        findings += [_as_finding(item, "Error") for item in (source.get("errors") or [])]
    for source in _platform_lists(payload):
        findings += [_as_finding(item, "Warning") for item in (source.get("warnings") or [])]
    solution_id = str(payload.get("solutionId") or payload.get("id") or "")
    app_ids = extract_app_ids(payload)
    ok_status = 200 <= status < 300

    if any(f["Severity"] == "Error" for f in findings):
        return Outcome(REJECTED, http=status, solution_id=solution_id, app_ids=app_ids,
                       findings=findings, raw=raw, hints=_hints(raw))
    if ok_status and (solution_id or not expect_solution_id):
        return Outcome(success_outcome, http=status, solution_id=solution_id,
                       app_ids=app_ids, findings=findings, raw=raw)
    if 400 <= status < 500:
        description = payload.get("description")
        message = (payload.get("message")
                   or (description if isinstance(description, str) else "") or raw[:300])
        findings.append(_as_finding(message, "Error"))
        return Outcome(REJECTED, http=status, findings=findings, raw=raw, hints=_hints(raw))
    return Outcome(ERROR, http=status, findings=findings,
                   detail=f"HTTP {status}: no solutionId in the response" if ok_status
                   else f"HTTP {status}", raw=raw, hints=_hints(raw))


# --------------------------------------------------------------------------
# Making a call
# --------------------------------------------------------------------------

_SOLUTION_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


def validate_solution_id(solution_id: Any) -> str:
    """A solution id (UUID or alias) safe to put in a URL, or `SkillInputError`."""
    if not isinstance(solution_id, str) or not _SOLUTION_ID.fullmatch(solution_id):
        raise SkillInputError("that is not a solution id: use the UUID or alias, "
                              "letters, digits, `-` and `_` only (at most 64)")
    return solution_id


def solution_url(solution_id: Any) -> str:
    return f"{API_BASE}/{urllib.parse.quote(validate_solution_id(solution_id), safe='')}"


class RedirectRefused(RuntimeError):
    """The server answered with a redirect; it is not followed."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect, so `Authorization` never follows one anywhere."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RedirectRefused(f"HTTP {code}: the server redirected, which is not followed")


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_NoRedirect)


def _is_timeout(exc: BaseException) -> bool:
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return True
    if isinstance(exc, urllib.error.URLError):
        return isinstance(exc.reason, (socket.timeout, TimeoutError))
    return False


class _Deadline(Exception):
    pass


def _read_until(response: Any, deadline: float, cancelled: threading.Event) -> bytes:
    """Read a body in chunks, checking the clock between them."""
    chunks: List[bytes] = []
    while True:
        if cancelled.is_set() or time.monotonic() >= deadline:
            raise _Deadline()
        chunk = response.read(65536)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _exchange(request: urllib.request.Request, timeout: int, deadline: float,
              cancelled: threading.Event, box: Dict[str, Any]) -> None:
    """The whole request, run in a worker so the caller can enforce one deadline."""
    try:
        try:
            with _opener().open(request, timeout=timeout) as response:
                box["result"] = (response.status,
                                 _read_until(response, deadline, cancelled).decode(
                                     "utf-8", "replace"), False)
        except urllib.error.HTTPError as exc:
            try:
                try:
                    text = _read_until(exc, deadline, cancelled).decode("utf-8", "replace")
                except _Deadline:
                    raise
                except Exception:  # noqa: BLE001
                    text = ""
            finally:
                exc.close()
            box["result"] = (exc.code, text, False)
    except _Deadline:
        box["result"] = (0, f"no response within {timeout}s", True)
    except RedirectRefused as exc:
        box["result"] = (0, str(exc), False)
    except Exception as exc:  # noqa: BLE001
        if _is_timeout(exc):
            box["result"] = (0, f"no response within {timeout}s", True)
        elif isinstance(getattr(exc, "reason", None), RedirectRefused):
            box["result"] = (0, str(exc.reason), False)
        else:
            box["result"] = (0, f"the request could not be made: {type(exc).__name__}", False)


def send(method: str, url: str, *, realm_host: str, body: Optional[bytes] = None,
         accept: str = "application/json", content_type: Optional[str] = None,
         qbl_version: Optional[str] = None, timeout: int = DEFAULT_TIMEOUT
         ) -> Tuple[int, str, bool]:
    """One request. Returns `(status, text, timed_out)`; `status` is 0 with no answer.

    `timeout` bounds the whole exchange, body included, not each socket read: the
    request runs in a worker thread and a slow trickle is a timeout. Redirects are
    refused. The secret is read by `qb_auth.request_headers` for this request alone
    and goes straight into the request's headers.
    """
    extra = {"Accept": accept}
    if content_type:
        extra["Content-Type"] = content_type
    if qbl_version:
        extra["QBL-Version"] = str(qbl_version)
    headers = qb_auth.request_headers(realm_host, extra)
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    deadline = time.monotonic() + timeout
    cancelled = threading.Event()
    box: Dict[str, Any] = {}
    worker = threading.Thread(target=_exchange, args=(request, timeout, deadline, cancelled,
                                                      box), daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        cancelled.set()
        return 0, f"no response within {timeout}s", True
    return box.get("result", (0, "the request could not be made: no result", False))


def create(text: str, *, realm_host: str, timeout: int = DEFAULT_TIMEOUT,
           qbl_version: Optional[str] = None) -> Outcome:
    """POST a solution. A hang is an outcome (`TIMEOUT`); the create may still finish."""
    status, body, timed_out = send(
        "POST", API_BASE, realm_host=realm_host, body=text.encode("utf-8"),
        content_type="application/x-yaml", qbl_version=qbl_version, timeout=timeout)
    if status == 0 and not timed_out:
        return Outcome(ERROR, detail=body)
    return parse_response(status, body, timed_out=timed_out)


def update(solution_id: str, text: str, *, realm_host: str, qbl_version: str,
           timeout: int = DEFAULT_TIMEOUT) -> Outcome:
    """PUT a solution, replacing it wholesale."""
    url = solution_url(solution_id)
    status, body, timed_out = send(
        "PUT", url, realm_host=realm_host,
        body=text.encode("utf-8"), content_type="application/x-yaml",
        qbl_version=qbl_version, timeout=timeout)
    if status == 0 and not timed_out:
        return Outcome(ERROR, detail=body)
    return parse_response(status, body, timed_out=timed_out, expect_solution_id=False,
                          success_outcome=UPDATED)


def export(solution_id: str, *, realm_host: str, qbl_version: str,
           timeout: int = DEFAULT_TIMEOUT) -> Tuple[int, str, bool]:
    """GET a solution as QBL. Read-only. Returns `(status, text, timed_out)`."""
    return send("GET", solution_url(solution_id), realm_host=realm_host,
                accept="application/x-yaml", qbl_version=qbl_version, timeout=timeout)


# --------------------------------------------------------------------------
# The relay: a call made by a Claude extension
# --------------------------------------------------------------------------

_STATUS_KEYS = ("http_status", "httpStatus", "status_code", "statusCode", "status")
_BODY_KEYS = ("body", "response", "json", "data", "result")
_SHA_KEYS = ("document_sha256", "submission_sha256", "sha256", "documentSha256")


def ingest_platform_response(result: Any, submitted_text: str) -> Outcome:
    """The `Outcome` for an extension's saved response, as if this Skill had called.

    `result` is the JSON the extension returned, unchanged. Accepted shapes: the
    Solutions API JSON itself, or a wrapper holding it under `body`/`response`
    with an HTTP status and a timeout flag beside it. When the extension reports
    a digest of what it sent, it must equal the digest of `submitted_text`; a
    response for different text is refused rather than recorded.
    """
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except ValueError as exc:
            raise RelayError("the saved response is not JSON") from exc
    if not isinstance(result, Mapping):
        raise RelayError("the saved response is not a JSON object")

    expected = sha256_text(submitted_text)
    digest_verified = False
    for key in _SHA_KEYS:
        reported = result.get(key)
        if isinstance(reported, str) and reported:
            if reported.lower() != expected:
                raise RelayError(
                    "the response reports a digest that is not the digest of the text "
                    "this Skill wrote, so it belongs to a different submission; "
                    "nothing was recorded")
            digest_verified = True
            break

    status = 0
    for key in _STATUS_KEYS:
        if isinstance(result.get(key), int) and not isinstance(result.get(key), bool):
            status = int(result[key])
            break
    timed_out = bool(result.get("timed_out") or result.get("timedOut")
                     or result.get("timeout") is True)

    body: Any = result
    for key in _BODY_KEYS:
        if isinstance(result.get(key), (Mapping, str)):
            body = result[key]
            break
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            body = {}
    if timed_out:
        return parse_response(0, "", timed_out=True)
    if not status:
        status = 200 if (isinstance(body, Mapping) and body.get("solutionId")
                         and not body.get("errors")) else 400
    outcome = parse_response(status, json.dumps(body), timed_out=False)
    # A response with no digest is ledgered so its application can be cleaned up,
    # but nothing ties it to this submission, so it never unlocks an update.
    outcome.digest_verified = digest_verified
    return outcome
