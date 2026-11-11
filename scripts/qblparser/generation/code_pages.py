from __future__ import annotations

import re
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

ENTRY_EXTENSIONS = (".html", ".htm")
ASSET_EXTENSIONS = (".js", ".css")
CODE_PAGE_EXTENSIONS = ENTRY_EXTENSIONS + ASSET_EXTENSIONS

CODE_PAGE_NAME = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*\.(?:html|htm|js|css)$", re.IGNORECASE)

AUTH_PATTERNS = {
    "TempToken": ("temp token in place of a user token (the acting user's own access, "
                  "fetched per table from their session; no stored credential, no app token)"),
    "Pipeline": "Pipeline-mediated (a pipeline the application owner controls holds any elevated access server-side)",
    "None": "none (calls no Quickbase API)",
}

LOW_TRAFFIC_REQUESTS_PER_SECOND = 4

TRUSTED_CDN_SUFFIXES = ("jsdelivr.net", "cdnjs.cloudflare.com")

DOCUMENTED_REST_ROOTS = frozenset({
    "analytics", "apps", "audit", "auth", "docTemplates", "fields", "files",
    "formula", "groups", "records", "reports", "solutions", "tables", "users",
    "usertoken",
})

NON_REALM_HOSTS = frozenset({"api", "help", "helpv2", "developer", "community",
                             "www", "resources", "login"})

REVIEW_STATUS = "DRAFT - review and test this page before deploying it."

FIELD_ID_TOKEN = re.compile(r"\[\[fid:([^|\]]+)\|([^\]]+)\]\]")
RESOLVED_FIELD_ID = re.compile(r"\b(\d+) /\*qbl:fid ([^|*]+)\|([^*]+)\*/")

ALIAS_TOKEN = re.compile(r"<!~db~\[(_DBID_[A-Za-z0-9_]+|_APP_ID_)\]~db~>")

CPG_CODES = tuple(f"CPG{n:03d}" for n in range(0, 26))


def is_entry_page(name: str) -> bool:
    return name.lower().endswith(ENTRY_EXTENSIONS)


def mask_comments(text: str) -> str:
    out = list(text)
    i, n = 0, len(text)
    quote: Optional[str] = None

    def blank(start: int, end: int) -> None:
        for k in range(start, min(end, n)):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote or (ch == "\n" and quote != "`"):
                quote = None
            i += 1
            continue
        if text.startswith("<!--", i):
            end = text.find("-->", i + 4)
            end = n if end < 0 else end + 3
            blank(i, end)
            i = end
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            blank(i, end)
            i = end
            continue
        if text.startswith("//", i) and (i == 0 or text[i - 1] != ":"):
            end = text.find("\n", i)
            end = n if end < 0 else end
            blank(i, end)
            i = end
            continue
        if ch in "'\"`":
            quote = ch
        i += 1
    return "".join(out)


def _line_of(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def _lines(text: str, pattern: "re.Pattern[str]") -> List[int]:
    return sorted({_line_of(text, m.start()) for m in pattern.finditer(text)})


def _is_literal(text: str, start: int) -> bool:
    while start < len(text) and text[start] in " \t":
        start += 1
    if start >= len(text) or text[start] not in "'\"`":
        return False
    quote = text[start]
    i = start + 1
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if quote == "`" and text.startswith("${", i):
            return False
        if ch == quote:
            rest = text[i + 1:].lstrip(" \t")
            return rest[:1] in ("", ";", ")", "\n", ",", "}")
        if ch == "\n" and quote != "`":
            return False
        i += 1
    return False


REST_PATH = re.compile(r"api\.quickbase\.com(/v1/[A-Za-z0-9_/.{}$<>~\[\]-]*)")
XML_CALL = re.compile(r"\bAPI_[A-Za-z]+\b")
REQUEST = re.compile(r"\bfetch\s*\(|\bXMLHttpRequest\b|\$\.(?:ajax|get|post|getJSON)\s*\(|\baxios\b|\bnavigator\.sendBeacon\s*\(")
EXTERNAL_ASSET = re.compile(
    r"""<(?:script|link)\b[^>]*?\b(?:src|href)\s*=\s*['"]((?:https?:)?//([^'"/]+)[^'"]*)['"]""",
    re.IGNORECASE)
IMPORT_FROM = re.compile(r"""\bimport\b[^'";]*?['"]((?:https?:)?//([^'"/]+)[^'"]*)['"]""")
EXACT_VERSION = re.compile(r"(?:@|/)v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.]+)?(?:/|$|\?)")


def rest_endpoints(code: str) -> List[str]:
    found = set()
    for match in REST_PATH.finditer(code):
        words = []
        for segment in match.group(1).split("/")[2:]:
            if not re.fullmatch(r"[A-Za-z]+", segment):
                break
            words.append(segment)
        if words:
            found.add("/v1/" + "/".join(words))
    return sorted(found)


def xml_calls(code: str) -> List[str]:
    return sorted(set(XML_CALL.findall(code)))


def external_libraries(code: str) -> List[Tuple[str, str]]:
    found: Dict[str, str] = {}
    for pattern in (EXTERNAL_ASSET, IMPORT_FROM):
        for match in pattern.finditer(code):
            url, host = match.group(1), match.group(2).lower()
            if host.endswith("quickbase.com"):
                continue
            found.setdefault(url, host)
    return sorted(found.items())


def launchers(spec: Any) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {page.name: [] for page in getattr(spec, "pages", [])}
    for table in spec.tables:
        for field_spec in table.fields:
            target = getattr(field_spec, "opens_page", None)
            if target in out:
                out[target].append(
                    f"formula-URL button '{field_spec.label}' on {table.name} "
                    f"(passes rid, the record's id)")
    for widget in getattr(spec, "home_widgets", []):
        for link in getattr(widget, "links", []) or []:
            if getattr(link, "page", None) in out:
                kind = "button" if widget.kind == "ButtonBar" else "link"
                out[link.page].append(f"app home page {kind} '{link.name}'")
    for role, page in (getattr(spec, "role_home_pages", None) or {}).items():
        if page in out:
            out[page].append(f"landing page for role {role}")
    for guide in getattr(spec, "guides", []):
        if guide.links_to in out:
            out[guide.links_to].append(f"app guide '{guide.title}'")
    for page in getattr(spec, "pages", []):
        if page.kind != "CodePage":
            continue
        for other in getattr(spec, "pages", []):
            if other is not page and other.kind == "CodePage" and re.search(
                    rf"[?&]pageName={re.escape(page.name)}(?![A-Za-z0-9._-])",
                    other.body, re.IGNORECASE):
                out[page.name].append(f"loaded by {other.name}")
    return out


def url_parameters(code: str) -> List[str]:
    names = set(re.findall(r"""\.get\(\s*['"]([A-Za-z_][A-Za-z0-9_]*)['"]\s*\)""", code))
    return sorted(names)


def review_header(page: Any, opened_by: Sequence[str], body: str) -> str:
    code = mask_comments(body)
    libraries = external_libraries(code)
    endpoints = [f"REST {path}" for path in rest_endpoints(code)]
    endpoints += [f"XML {call}" for call in xml_calls(code)]
    if page.auth == "Pipeline":
        endpoints.append("a pipeline webhook (incoming HTTP request)")
    params = url_parameters(code)
    if page.requests_per_second is None:
        volume = "not stated"
    else:
        volume = f"{page.requests_per_second:g} requests/second combined at peak"
    lines = [
        f"Purpose: {page.purpose or page.name}",
    ]
    if page.native_gap:
        lines.append(f"Native gap: {page.native_gap}")
    lines += [
        f"Trigger: {'; '.join(opened_by) if opened_by else 'none declared'}",
        f"Auth pattern: {AUTH_PATTERNS.get(page.auth, page.auth)}",
        "External libraries: " + (
            "; ".join(f"{url} (source: {host})" for url, host in libraries)
            if libraries else "none (vanilla JS)"),
        "API endpoints used: " + (", ".join(endpoints) if endpoints else "none"),
        "URL parameters: " + (", ".join(params) if params else "none"),
        "Data sensitivity: " + (
            "handles PII, health or financial data - flagged for extra review"
            if page.sensitive_data else "no sensitive data declared"),
        f"Expected volume: {volume}",
        f"Review status: {REVIEW_STATUS}",
        (f"Drafted: {page.drafted_on}. " if page.drafted_on else "")
        + "Review and security-scan this page before deploying it.",
    ]
    if page.name.lower().endswith(ENTRY_EXTENSIONS):
        safe = [line.replace("--", "-") for line in lines]
        return "<!--\n" + "\n".join(f"  {line}" for line in safe) + "\n-->\n"
    safe = [line.replace("*/", "* /") for line in lines]
    return "/*\n" + "\n".join(f" * {line}" for line in safe) + "\n */\n"


def resolve_field_tokens(body: str,
                         field_id: Callable[[str, str], Optional[int]],
                         where: str) -> str:
    missing: List[str] = []

    def replace(match: "re.Match[str]") -> str:
        table, label = match.group(1).strip(), match.group(2).strip()
        value = field_id(table, label)
        if value is None:
            missing.append(f"{table}|{label}")
            return match.group(0)
        return f"{value} /*qbl:fid {table}|{label}*/"

    resolved = FIELD_ID_TOKEN.sub(replace, body)
    if missing:
        from qblparser.generation.compiler import QBLCompileError

        raise QBLCompileError(
            f"{where} names fields the application does not declare: "
            f"{', '.join(sorted(set(missing)))}. Write [[fid:<table name>|<field label>]] "
            f"with the table's name and the field's label as the spec gives them")
    return resolved


def _application(document: Mapping[str, Any]) -> Mapping[str, Any]:
    for node in (document.get("Resources") or {}).values():
        if isinstance(node, Mapping) and node.get("Type") == "QB::Application":
            return node
    return {}


def _code_page_nodes(document: Mapping[str, Any]) -> List[Tuple[str, Mapping[str, Any]]]:
    pages = (_application(document).get("Pages") or {}).get("Resources") or {}
    return [(key, node) for key, node in pages.items()
            if isinstance(node, Mapping) and node.get("Type") == "QB::CodePage"]


def _field_ids_by_label(document: Mapping[str, Any]) -> Dict[Tuple[str, str], int]:
    out: Dict[Tuple[str, str], int] = {}
    for table in (_application(document).get("Tables") or {}).values():
        if not isinstance(table, Mapping):
            continue
        name = (table.get("Properties") or {}).get("Name")
        for node in (table.get("Fields") or {}).values():
            if isinstance(node, Mapping) and "Id" in node:
                label = (node.get("Properties") or {}).get("Label")
                if name and label:
                    out[(str(name), str(label))] = node["Id"]
    return out


def reresolve_field_ids(document: Dict[str, Any]) -> List[Tuple[str, str, int, int]]:
    ids = _field_ids_by_label(document)
    changes: List[Tuple[str, str, int, int]] = []
    for key, node in _code_page_nodes(document):
        properties = node.get("Properties")
        if not isinstance(properties, dict):
            continue
        code = properties.get("RawCode")
        if not isinstance(code, str):
            continue

        def replace(match: "re.Match[str]") -> str:
            old = int(match.group(1))
            table, label = match.group(2), match.group(3)
            new = ids.get((table, label))
            if new is None or new == old:
                return match.group(0)
            changes.append((key, f"{table}|{label}", old, new))
            return f"{new} /*qbl:fid {table}|{label}*/"

        properties["RawCode"] = RESOLVED_FIELD_ID.sub(replace, code)
    return changes


CREDENTIALS = (
    (re.compile(r"QB-USER-TOKEN", re.IGNORECASE), "a QB-USER-TOKEN authorization"),
    (re.compile(r"(?<![A-Za-z0-9])[a-z0-9]{6}_[a-z0-9]{4}_\d{1,3}_[a-z0-9]{20,}(?![A-Za-z0-9])",
                re.IGNORECASE), "a Quickbase user token"),
    (re.compile(r"""\b(?:usertoken|apptoken)\s*[:=]\s*['"`][A-Za-z0-9_]{12,}""", re.IGNORECASE),
     "a user or app token"),
    (re.compile(r"[?&](?:usertoken|apptoken|ticket)=[A-Za-z0-9_]{12,}", re.IGNORECASE),
     "a token or ticket in a URL"),
    (re.compile(r"\bAPI_Authenticate\b"), "API_Authenticate, which signs in with a password"),
    (re.compile(r"""\bpassword\s*[:=]\s*['"`][^'"`\s]+""", re.IGNORECASE), "a password"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}"), "a bearer token"),
    (re.compile(r"""\b(?:api[_-]?key|client[_-]?secret|secret)\s*[:=]\s*['"`][^'"`\s]{8,}""",
                re.IGNORECASE), "an API key or secret"),
)
STORAGE = re.compile(r"\b(?:localStorage|sessionStorage|document\.cookie|indexedDB)\b|\bAPI_SetDBVar\b|/variables\b")
SECRETISH = re.compile(r"token|authoriz|ticket|secret|password|credential", re.IGNORECASE)
DYNAMIC_CODE = re.compile(
    r"\beval\s*\(|\bnew\s+Function\s*\(|\bdocument\.write(?:ln)?\s*\(|\bset(?:Timeout|Interval)\s*\(\s*['\"`]")
HTML_ASSIGN = re.compile(r"\.(?:innerHTML|outerHTML)\s*\+?=(?!=)")
HTML_INSERT = re.compile(r"\.insertAdjacentHTML\s*\(\s*['\"`][^'\"`]*['\"`]\s*,")
JQUERY_HTML = re.compile(r"\.html\s*\(\s*(?=[^)\s])")
INTERNALS = (
    (re.compile(r"\bDoSave\w*\s*\("), "DoSave(), an internal Quickbase form function"),
    (re.compile(r"\bgReq[A-Z]\w*"), "a gReq* global belonging to the Quickbase page"),
    (re.compile(r"\b(?:parent|top|opener)\.(?:document|\$|jQuery)\b"),
     "the hosting Quickbase page's DOM"),
    (re.compile(r"""<script\b[^>]*\bsrc\s*=\s*['"](?:https?://[^'"/]*quickbase\.com)?/(?:js|res|static|css|i)/""",
                re.IGNORECASE), "a script Quickbase hosts for its own pages"),
)
UI_ACTION = re.compile(r"[?&](?:a|act)=([A-Za-z_]+)")
DESTRUCTIVE = re.compile(
    r"\bAPI_(?:PurgeRecords|DeleteRecord|DeleteDatabase|DeleteField|CloneDatabase)\b"
    r"|method\s*:\s*['\"`]DELETE['\"`]|\.open\s*\(\s*['\"`]DELETE['\"`]"
    r"|/v1/apps/[^'\"`\s]*/copy")
CONFIRMATION = re.compile(r"\bconfirm\s*\(|\.showModal\s*\(")
TEMP_TOKEN = re.compile(r"/v1/auth/temporary/")
TEMP_TOKEN_FOR_APP = re.compile(r"/v1/auth/temporary/(?:<!~db~\[_APP_ID_\]~db~>|\$\{\s*app|['\"`]\s*\+\s*app)",
                                re.IGNORECASE)
REST_CALL = re.compile(r"api\.quickbase\.com/v1/(?!auth/temporary)")
LITERAL_DBID = re.compile(
    r"""(?:/db/|/auth/temporary/|\b(?:from|tableId|appId|dbid)['"]?\s*[:=]\s*['"`])(b[a-z0-9]{8})(?![a-z0-9])""")
REALM_HOST = re.compile(r"https?://([a-z0-9-]+)(?:\.ui)?\.quickbase\.com", re.IGNORECASE)
PAGE_NAME_REF = re.compile(r"[?&]pageName=([A-Za-z0-9._%-]+)", re.IGNORECASE)
PAGE_ID_REF = re.compile(r"[?&]pageID=(\d+)", re.IGNORECASE)
URL_BUILDING = re.compile(
    r"\bsearchParams\.(?:set|append)\s*\(|new\s+URLSearchParams\s*\(\s*\{"
    r"|[?&][A-Za-z_]+=['\"`]?\s*\+|[?&][A-Za-z_]+=\$\{")
RAW_ERRORS = (
    re.compile(r"\balert\s*\([^)\n]*\b(?:err|error|e|ex|exc|exception|response|res|resp)\b"),
    re.compile(r"\.(?:textContent|innerText|innerHTML|value)\s*=\s*[^;\n]*\b(?:err|error|e|ex)\.(?:message|stack)\b"),
    re.compile(r"\.(?:textContent|innerText|innerHTML)\s*=\s*[^;\n]*\bJSON\.stringify\s*\(\s*(?:err|error|response|resp|res)\b"),
)
READS_PARAMS = re.compile(r"\bURLSearchParams\b|\blocation\.(?:search|hash)\b")
VALIDATES = re.compile(r"\\d|Number\.isInteger|parseInt\s*\(|Number\s*\(|isNaN\s*\(|\.test\s*\(|\.match\s*\(")
DEBUG = re.compile(r"\bconsole\.(?:log|debug|info|trace)\s*\(|\bdebugger\b")
REALM_HEADER = re.compile(r"QB-Realm-Hostname", re.IGNORECASE)
INCLUDE_CREDENTIALS = re.compile(r"""credentials\s*:\s*['"`]include['"`]""")


def _finding(code: str, severity: str, location: str, problem: str, fix: str,
             lines: Sequence[int] = ()) -> Dict[str, Any]:
    if lines:
        shown = ", ".join(str(n) for n in list(lines)[:8])
        more = f" and {len(lines) - 8} more" if len(lines) > 8 else ""
        problem = f"{problem} (RawCode line {shown}{more})"
    return {"Code": code, "Severity": severity, "Problem": problem,
            "Location": location, "Fix": fix}


def _review_one(key: str, name: str, raw: str, *, aliases: Iterable[str],
                page_names: Iterable[str], page_ids: Iterable[int],
                page: Any = None, opened_by: Optional[Sequence[str]] = None,
                ) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    code = mask_comments(raw)
    add = out.append

    add(_finding(
        "CPG000", "Warning", key,
        f"'{name}' is browser code the application owner will maintain. It is a "
        f"DRAFT until it has been reviewed and security-scanned, and there is "
        f"no test framework for code pages, so nothing here has executed it."
        + (" It handles sensitive data and is flagged for extra review."
           if page is not None and page.sensitive_data else ""),
        "Review and security-scan it before deploying it. Test it by opening it from Quickbase in a "
        "development app - its temporary token comes from the Quickbase session "
        "on the realm's subdomain, so Postman or a local copy cannot run it. Keep "
        "its source in Git, and remove any prototype pages before go-live."))

    for pattern, what in CREDENTIALS:
        hits = _lines(raw, pattern)
        if hits:
            add(_finding(
                "CPG001", "Error", key,
                f"'{name}' carries {what}. Anything in a code page is readable by "
                f"every user who can open it.",
                "Remove it. Fetch a temporary token for the acting user "
                "(GET /v1/auth/temporary/{tableId}); route anything needing more "
                "access than they have through a pipeline that holds the "
                "credential server-side.", hits))

    stored = [n for n, line in enumerate(code.split("\n"), start=1)
              if STORAGE.search(line) and SECRETISH.search(line)]
    if stored:
        add(_finding(
            "CPG002", "Error", key,
            f"'{name}' writes what looks like a credential to browser storage or "
            f"an app variable, where other scripts and users can read it.",
            "Keep the temporary token in a local variable for the request that "
            "needs it and fetch a fresh one when it expires (about five minutes).",
            stored))

    hits = _lines(code, DYNAMIC_CODE)
    if hits:
        add(_finding(
            "CPG003", "Error", key,
            f"'{name}' executes code built at runtime (eval, new Function, "
            f"document.write or a string timer).",
            "Call functions directly, pass a function to setTimeout, and build "
            "the page with createElement and textContent.", hits))

    unsafe: List[int] = []
    for match in HTML_ASSIGN.finditer(code):
        if not _is_literal(code, match.end()):
            unsafe.append(_line_of(code, match.start()))
    for match in HTML_INSERT.finditer(code):
        if not _is_literal(code, match.end()):
            unsafe.append(_line_of(code, match.start()))
    for match in JQUERY_HTML.finditer(code):
        if not _is_literal(code, match.end()):
            unsafe.append(_line_of(code, match.start()))
    if unsafe:
        add(_finding(
            "CPG004", "Error", key,
            f"'{name}' renders markup built from data. Record values, user input "
            f"and URL parameters put through innerHTML execute any markup they "
            f"contain.",
            "Set textContent (or create elements and set their text) for anything "
            "that is not a fixed string.", sorted(set(unsafe))))

    for pattern, what in INTERNALS:
        hits = _lines(code, pattern)
        if hits:
            add(_finding(
                "CPG005", "Error", key,
                f"'{name}' depends on {what}. Quickbase does not support it, "
                f"changes it without notice, and will not help when it breaks.",
                "Use the documented REST API, or the code page insertion points "
                "(a formula-URL or rich text button, a home page button, a web "
                "page widget) instead of reaching into the Quickbase page.", hits))

    undocumented = sorted({
        f"/v1/{m.group(1)}" for m in re.finditer(r"api\.quickbase\.com/v1/([A-Za-z]+)", code)
        if m.group(1) not in DOCUMENTED_REST_ROOTS})
    actions: List[str] = []
    action_lines: List[int] = []
    for n, line in enumerate(code.split("\n"), start=1):
        if not REQUEST.search(line):
            continue
        for value in UI_ACTION.findall(line):
            if not value.startswith("API_") and value.lower() != "dbpage":
                actions.append(f"a={value}")
                action_lines.append(n)
    if undocumented or actions:
        add(_finding(
            "CPG006", "Error", key,
            f"'{name}' calls {', '.join(undocumented + sorted(set(actions)))}, "
            f"which is not part of the documented REST API or the API_* XML API.",
            "Use a documented endpoint from developer.quickbase.com; if none "
            "exists, say so rather than relying on an internal one.",
            action_lines))

    libraries = external_libraries(code)
    unpinned = [url for url, _ in libraries
                if not EXACT_VERSION.search(url) or re.search(r"@(?:latest|next)\b", url)]
    if unpinned:
        add(_finding(
            "CPG007", "Error", key,
            f"'{name}' loads {', '.join(unpinned)} without an exact version, so "
            f"what it runs can change under it without anybody noticing.",
            "Pin each to an exact version, e.g. "
            "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js."))
    untrusted = [url for url, host in libraries
                 if not any(host == s or host.endswith("." + s) for s in TRUSTED_CDN_SUFFIXES)]
    if untrusted:
        add(_finding(
            "CPG008", "Warning", key,
            f"'{name}' loads {', '.join(untrusted)} from outside the trusted "
            f"CDNs.",
            "Load it from cdn.jsdelivr.net or cdnjs.cloudflare.com."))
    if libraries:
        add(_finding(
            "CPG009", "Warning", key,
            f"'{name}' depends on {len(libraries)} external librar"
            f"{'y' if len(libraries) == 1 else 'ies'}. Each is a dependency the "
            f"application owner must keep patched.",
            "Keep one only where vanilla JS cannot reasonably do the job - complex "
            "stateful UI, charting, PDF or binary handling, hard timezone work - "
            "and say why in the page header."))

    if DESTRUCTIVE.search(code) and not CONFIRMATION.search(code):
        add(_finding(
            "CPG010", "Error", key,
            f"'{name}' deletes, purges or copies with no confirmation step. A bad "
            f"filter on a purge can empty a table.",
            "Ask first - confirm() or a modal that says what will happen and to how "
            "many records - and never run it on page load.",
            _lines(code, DESTRUCTIVE)))

    requests = REQUEST.search(code) is not None
    if requests and not ("429" in code and "retry-after" in code.lower()):
        add(_finding(
            "CPG011", "Error", key,
            f"'{name}' makes requests without handling a 429 and its Retry-After "
            f"header. Quickbase rate-limits at its edge, and a page that ignores "
            f"it either fails or retries straight into the limit.",
            "On 429 wait for Retry-After before retrying, back off exponentially "
            "on network faults and 5xx, and cap the attempts. STARTER_CODE_PAGE "
            "has the pattern."))

    calls_rest = REST_CALL.search(code) is not None
    calls_xml = bool(xml_calls(code))
    has_temp = TEMP_TOKEN.search(code) is not None
    auth = page.auth if page is not None else None
    if (calls_rest or calls_xml) and not has_temp:
        apis = " and ".join(a for a, used in (("REST", calls_rest), ("XML", calls_xml)) if used)
        add(_finding(
            "CPG012", "Error", key,
            f"'{name}' calls the {apis} API with no temporary token, so it either "
            f"fails or authenticates with something that should not be there - a "
            f"stored token, or the session ticket and an app token beside it.",
            "Fetch a temporary token for the acting user per table "
            "(GET /v1/auth/temporary/{tableId}, credentials: \"include\") and use "
            "it where a user token would go: `Authorization: QB-TEMP-TOKEN <token>` "
            "on REST, the user token's place on XML.",
            sorted(set(_lines(code, REST_CALL) + _lines(code, XML_CALL)))))
    if TEMP_TOKEN_FOR_APP.search(code):
        add(_finding(
            "CPG013", "Warning", key,
            f"'{name}' requests a temporary token for the whole application. The "
            f"endpoint allows it, and the token can then do more than the page "
            f"needs.",
            "Request it for the table being read or written: "
            "/v1/auth/temporary/<!~db~[_DBID_<TABLE>]~db~>.",
            _lines(code, TEMP_TOKEN_FOR_APP)))
    if auth == "None" and (calls_rest or has_temp or calls_xml):
        add(_finding(
            "CPG012", "Error", key,
            f"'{name}' is declared auth=\"None\" and calls Quickbase.",
            "Declare auth=\"TempToken\", or auth=\"Pipeline\" if a pipeline does the "
            "privileged part."))
    if has_temp and not INCLUDE_CREDENTIALS.search(code):
        add(_finding(
            "CPG013", "Warning", key,
            f"'{name}' fetches a temporary token without credentials: \"include\", "
            f"so the user's session is not sent and the request fails.",
            "Add credentials: \"include\" to the token request."))
    if calls_rest and not REALM_HEADER.search(code):
        add(_finding(
            "CPG013", "Warning", key,
            f"'{name}' calls the REST API without a QB-Realm-Hostname header, "
            f"which every REST call needs.",
            "Send QB-Realm-Hostname: window.location.hostname."))

    known_aliases = set(aliases)
    unknown = sorted({m.group(1) for m in ALIAS_TOKEN.finditer(raw)
                      if m.group(1) not in known_aliases})
    if unknown:
        add(_finding(
            "CPG014", "Error", key,
            f"'{name}' names {', '.join(unknown)}, which no table in this "
            f"application carries. The token is left unresolved and the page "
            f"addresses a table that does not exist.",
            f"Use one of: {', '.join(sorted(known_aliases)) or '(no tables)'}."))
    dbids = _lines(code, LITERAL_DBID)
    hosts = [n for n in _lines(code, REALM_HOST)
             if any(m.group(1).lower() not in NON_REALM_HOSTS
                    for m in REALM_HOST.finditer(code.split("\n")[n - 1]))]
    if dbids or hosts:
        add(_finding(
            "CPG015", "Warning", key,
            f"'{name}' writes a dbid or a realm hostname literally. Both exist in "
            f"one realm only; in the app a create makes, they point elsewhere.",
            "Address tables by alias token (<!~db~[_DBID_<TABLE>]~db~>), the app "
            "by <!~db~[_APP_ID_]~db~>, the realm by window.location.hostname, and "
            "other pages by relative URL (?a=dbpage&pageName=...).",
            sorted(set(dbids + hosts))))

    names = {n.lower() for n in page_names}
    missing = sorted({m.group(1) for m in PAGE_NAME_REF.finditer(code)
                      if m.group(1).lower() not in names})
    ids = set(page_ids)
    missing += sorted({f"pageID={m.group(1)}" for m in PAGE_ID_REF.finditer(code)
                       if int(m.group(1)) not in ids})
    if missing:
        add(_finding(
            "CPG016", "Error", key,
            f"'{name}' loads or links to {', '.join(missing)}, which is not a page "
            f"in this application.",
            "Declare the page, or correct the name. Prefer pageName= to pageID=: "
            "ids move when a rebuild is reconciled against a deployed app."))

    if page is not None and page.sensitive_data and URL_BUILDING.search(code):
        add(_finding(
            "CPG017", "Warning", key,
            f"'{name}' handles sensitive data and builds query strings from "
            f"values. URLs are kept in browser history, proxies and server logs.",
            "Send sensitive values in a POST body; keep URLs to ids.",
            _lines(code, URL_BUILDING)))

    raw_errors = sorted({n for pattern in RAW_ERRORS for n in _lines(code, pattern)})
    if raw_errors:
        add(_finding(
            "CPG018", "Warning", key,
            f"'{name}' shows a raw error or response to the user. API errors carry "
            f"field ids and table structure.",
            "Show a fixed, friendly message and console.error the detail.",
            raw_errors))

    if READS_PARAMS.search(code) and not VALIDATES.search(code):
        add(_finding(
            "CPG019", "Warning", key,
            f"'{name}' reads URL parameters with no validation in sight.",
            "Check each parameter's format before using it - a record id against "
            "/^\\d+$/ - and stop with a friendly message if it fails.",
            _lines(code, READS_PARAMS)))

    hits = _lines(code, DEBUG)
    if hits:
        add(_finding(
            "CPG020", "Warning", key,
            f"'{name}' still carries debug output.",
            "Remove console.log, console.debug and debugger; keep console.error for "
            "failures.", hits))

    if page is not None:
        rps = page.requests_per_second
        if rps is None:
            add(_finding(
                "CPG021", "Warning", key,
                f"'{name}' does not state its expected request volume, which decides "
                f"whether a plain code page fits at all.",
                f"Set requests_per_second. Up to {LOW_TRAFFIC_REQUESTS_PER_SECOND} "
                f"combined is a code page; above that, CDN hosting or browser caching."))
        elif rps > LOW_TRAFFIC_REQUESTS_PER_SECOND:
            add(_finding(
                "CPG021", "Warning", key,
                f"'{name}' expects {rps:g} requests/second, above Quickbase's "
                f"{LOW_TRAFFIC_REQUESTS_PER_SECOND}/second threshold for a plain "
                f"code page.",
                "Raise CDN hosting or browser caching with the requester before "
                "building this as a code page."))
        if opened_by is not None and not opened_by:
            add(_finding(
                "CPG022", "Warning", key,
                f"Nothing in the application opens '{name}'.",
                "Give a URL::Formula field opens_page=, point a home page link at "
                "it, land a role on it, or load it from another code page."
                if is_entry_page(name) else
                f"Load it from a page: <script src=\"?a=dbpage&pageName={name}\">."))
        if auth == "TempToken" and not (calls_rest or has_temp or calls_xml):
            add(_finding(
                "CPG023", "Warning", key,
                f"'{name}' is declared auth=\"TempToken\" and calls no Quickbase API.",
                "Declare auth=\"None\" so the header says what the page does."))
    else:
        if "Review status:" not in raw:
            add(_finding(
                "CPG024", "Warning", key,
                f"'{name}' has no review header saying what it does, how it "
                f"authenticates, what it depends on and whether it was reviewed.",
                "Build it from a PageSpec, which writes one, or add the header by "
                "hand."))
        if not str(name).lower().endswith(CODE_PAGE_EXTENSIONS):
            add(_finding(
                "CPG025", "Warning", key,
                f"'{name}' has no .html, .htm, .js or .css extension, so Quickbase "
                f"serves it as plain text and shows its source.",
                "Rename it with the extension of what it holds."))
    return out


def review_code_pages(document: Mapping[str, Any], spec: Any = None) -> List[Dict[str, Any]]:
    application = _application(document)
    tables = application.get("Tables") or {}
    aliases = {"_APP_ID_"} | {
        str((node.get("Properties") or {}).get("AliasHint"))
        for node in tables.values()
        if isinstance(node, Mapping) and (node.get("Properties") or {}).get("AliasHint")}
    pages = (application.get("Pages") or {}).get("Resources") or {}
    page_names = [str((node.get("Properties") or {}).get("Name", ""))
                  for node in pages.values() if isinstance(node, Mapping)]
    page_ids = [node["Id"] for node in pages.values()
                if isinstance(node, Mapping) and isinstance(node.get("Id"), int)]

    by_name: Dict[str, Any] = {}
    opened: Dict[str, List[str]] = {}
    if spec is not None:
        by_name = {page.name: page for page in spec.pages if page.kind == "CodePage"}
        opened = launchers(spec)

    findings: List[Dict[str, Any]] = []
    for key, node in _code_page_nodes(document):
        properties = node.get("Properties") or {}
        name = str(properties.get("Name", key))
        raw = properties.get("RawCode") or ""
        if not isinstance(raw, str):
            continue
        page = by_name.get(name)
        findings.extend(_review_one(
            key, name, raw, aliases=aliases, page_names=page_names,
            page_ids=page_ids, page=page,
            opened_by=opened.get(name) if page is not None else None))
    return findings


def starter_code_page(table: str = "Tasks", fields: Sequence[str] = ("Task Name", "Status"),
                      title: str = "Record summary") -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "_", table).strip("_").upper() or "TABLE"
    field_map = ",\n".join(
        f'    {{ label: "{label}", id: [[fid:{table}|{label}]] }}' for label in fields)
    return STARTER_TEMPLATE.replace("__TITLE__", title).replace(
        "__ALIAS__", f"_DBID_{slug}").replace("__FIELDS__", field_map)


STARTER_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 1.5rem; color: #1f2933; }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: .4rem 1rem; }
  dt { font-weight: 600; }
  .problem { color: #b42318; }
</style>
</head>
<body>
<main>
  <h1>__TITLE__</h1>
  <p id="status" role="status">Loading...</p>
  <dl id="details"></dl>
</main>
<script>
(function () {
  "use strict";

  // The table this page reads, by alias. A create replaces the token with the
  // table's real id, so the page works in whichever app it lands in.
  var TABLE_ID = "<!~db~[__ALIAS__]~db~>";
  // Only the fields this page shows: anything fetched is visible in the
  // browser whether or not it is rendered.
  var FIELDS = [
__FIELDS__
  ];
  var REALM = window.location.hostname;
  var MAX_ATTEMPTS = 4;

  var status = document.getElementById("status");
  var details = document.getElementById("details");

  function say(message, isProblem) {
    status.textContent = message;
    status.className = isProblem ? "problem" : "";
  }

  function recordId() {
    var rid = new URLSearchParams(window.location.search).get("rid");
    return /^\\d+$/.test(rid || "") ? rid : null;
  }

  function pause(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  // One request, retried with backoff: on 429 after Retry-After, on network
  // faults and 5xx exponentially, and never more than MAX_ATTEMPTS times.
  async function request(url, options, attempt) {
    attempt = attempt || 1;
    var response;
    try {
      response = await fetch(url, options);
    } catch (fault) {
      if (attempt >= MAX_ATTEMPTS) { throw fault; }
      await pause(Math.pow(2, attempt) * 250);
      return request(url, options, attempt + 1);
    }
    if ((response.status === 429 || response.status >= 500) && attempt < MAX_ATTEMPTS) {
      var retryAfter = Number(response.headers.get("Retry-After"));
      await pause(retryAfter > 0 ? retryAfter * 1000 : Math.pow(2, attempt) * 250);
      return request(url, options, attempt + 1);
    }
    if (!response.ok) { throw new Error("Request failed with status " + response.status); }
    return response.json();
  }

  // A temporary token for the person who opened the page, for one table. It
  // can do only what they can, lives about five minutes, and is never stored.
  async function temporaryToken(tableId) {
    var data = await request("https://api.quickbase.com/v1/auth/temporary/" + tableId, {
      method: "GET",
      credentials: "include",
      headers: { "QB-Realm-Hostname": REALM }
    });
    return data.temporaryAuthorization;
  }

  async function load() {
    var rid = recordId();
    if (!rid) { say("This page opens from a record.", true); return; }

    var token = await temporaryToken(TABLE_ID);
    var result = await request("https://api.quickbase.com/v1/records/query", {
      method: "POST",
      headers: {
        "QB-Realm-Hostname": REALM,
        "Authorization": "QB-TEMP-TOKEN " + token,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        from: TABLE_ID,
        select: FIELDS.map(function (f) { return f.id; }),
        where: "{3.EX." + rid + "}"
      })
    });

    var record = (result.data || [])[0];
    if (!record) { say("That record could not be found.", true); return; }

    FIELDS.forEach(function (f) {
      var term = document.createElement("dt");
      var value = document.createElement("dd");
      term.textContent = f.label;
      var cell = record[String(f.id)];
      value.textContent = cell && cell.value != null ? String(cell.value) : "";
      details.appendChild(term);
      details.appendChild(value);
    });
    say("");
  }

  load().catch(function (problem) {
    console.error(problem);
    say("Unable to load this record. Please refresh and try again.", true);
  });
})();
</script>
</body>
</html>
"""

STARTER_CODE_PAGE = starter_code_page()


__all__ = [
    "AUTH_PATTERNS",
    "CODE_PAGE_EXTENSIONS",
    "CPG_CODES",
    "LOW_TRAFFIC_REQUESTS_PER_SECOND",
    "STARTER_CODE_PAGE",
    "is_entry_page",
    "launchers",
    "mask_comments",
    "reresolve_field_ids",
    "resolve_field_tokens",
    "review_code_pages",
    "review_header",
    "starter_code_page",
]
