# Code pages: native first, then the rules

Code pages: when to build one, how the builder builds it, and what it is checked for.

A code page is HTML, JavaScript or CSS that Quickbase serves from the
application itself. QBL carries one as a `QB::CodePage` holding two
properties - a `Name` and the `RawCode` - so the platform side of building one
is small. Everything that makes one *safe to deploy* is in the code, and
nothing else reads a line of it: structural checks only confirm that `RawCode`
is a string under 1 MB and that code pages exist. The code-page review reads it.

## Native first

A code page is browser code the application owner maintains. No platform
upgrade looks after it, there is no test framework for it, and it should be
reviewed and tested before it is deployed. So it is the last resort,
built only for a requirement nothing native meets. Before writing one, rule
out:

    a formula field          computed values, URL and rich text buttons, icons
    a form rule              show, hide, require, set a value, abort a save
    a report or chart        filters, grouping, kanban, calendar, timeline
    a dashboard              filters across widgets, KPIs, several tabs
    a pipeline               anything on a schedule or an event, anything that
                             needs more access than the user has, any call to
                             another system
    an email or a document   notifications, generated PDFs

and build a code page only where the requirement is something such as an
interactive layout (drag to reorder, a multi-record editing grid, a wizard
writing several tables at once), a client-side file operation, or a
visualisation no chart kind can draw. `PageSpec.native_gap` records which of
the above was considered and why it does not meet the requirement. An `.html`
code page without one is refused at generation.

Out of scope for a code page at any volume: a portal for people without a
Quickbase login, anything that must act as a service account rather than the
person clicking, and anything above **4 requests per second** combined - which
is Quickbase's threshold for a plain code page, and above which the answer is
CDN hosting or browser caching. Say so rather than building one.

## What the builder does

    PageSpec("task-board.html", "CodePage", purpose=..., native_gap=...,
             auth="TempToken", requests_per_second=1, body=...)

- **The name is the file name.** Its extension sets the content type, so one
  without `.html`, `.htm`, `.js` or `.css` is refused - the platform would serve
  it as plain text and show the source. No spaces: every URL naming the page
  would have to encode them.
- **It writes the review header** every code page carries, as the first thing
  in the page: purpose, the native gap, how it is opened, its auth pattern, the
  external libraries and the Quickbase endpoints it calls (both read from the
  code), its URL parameters, its data sensitivity, its stated volume, and
  `Review status: DRAFT - review and test this page before deploying it.`
  A body that already carries one is refused, so there is never a stale second
  header disagreeing with the first.
- **It resolves field ids.** The builder numbers fields, so a body cannot
  know that `Status` will be field 7. Write `[[fid:Tasks|Status]]` where a JS
  number belongs - typically once each, in a map of the fields the page uses -
  and it becomes `7 /*qbl:fid Tasks|Status*/`. The comment is what lets
  `plan_update` move it when a rebuild against a deployed app keeps that field
  on a different id. An unknown table or label is an error.
- **It writes the buttons that open it.** `FieldSpec(kind="URL::Formula",
  opens_page="task-board.html")` becomes the formula Quickbase's own exports
  use - `URLRoot() & "db/" & Dbid() & "?a=dbpage&pageName=task-board.html&rid="
  & [Record ID#]` - shown as a button. A `HomeWidgetLinkSpec(page=...)` naming a
  code page opens it with `a=dbpage` rather than `a=showpage`. A role can land on
  one through `role_home_pages`, and a guide can link to one.

## The temporary token

A code page authenticates as the person who opened it, with a temporary token
from `GET https://api.quickbase.com/v1/auth/temporary/{dbid}` (sent with
`credentials: "include"` and `QB-Realm-Hostname`). The token stands in for a
user token on both the REST API (`Authorization: QB-TEMP-TOKEN <token>`) and the
XML API, can do only what that user can, and expires after five minutes. Because
it stands in for a user token, an app's *Require Application Tokens* setting -
which Quickbase turns on for every app a QBL create makes - does not apply to
it, and no app token belongs in the page.

It is issued only from the user's Quickbase session, to a page served from the
realm's own subdomain. So a code page cannot be exercised from Postman, a local
file or another host; the only test is to open it from Quickbase, in a
development app first. The developer portal allows an app or a table as the
`dbid`. Ask for the table the page reads or writes: a token scoped to one table
can do less (`CPG013` warns on an app-scoped one).

Pages are addressed by name, not by `pageID`, because `plan_update` keeps a
deployed page on its deployed id and a link written with the builder's id
would then open a different page.

Tables are addressed in the body by alias token - `<!~db~[_DBID_TASKS]~db~>`,
and the application by `<!~db~[_APP_ID_]~db~>` - never by a literal dbid. Writing ids that
way makes the page work in whichever app a create makes. The review checks
each token names a table the application declares (`CPG014`).

## The review

`review_code_pages(document, spec)` reads every `QB::CodePage`. Errors block
`build_app`; warnings are decisions to state. Comments are read only by
`CPG001`, since a credential in a comment is still a credential in the page;
every other rule reads the code with comments blanked out. All of it is pattern
matching over source text: it catches the mistakes it names and proves nothing
else, which is why `CPG000` is never cleared.

    CPG000  warning  every code page: a draft until reviewed and tested;
                     there is no test framework for it
    CPG001  error    a credential in the source: a user token, an app token, a
                     password, a bearer token, an API key, API_Authenticate
    CPG002  error    a credential written to localStorage, sessionStorage, a
                     cookie, IndexedDB or an app variable
    CPG003  error    dynamic code: eval, new Function, document.write, a string
                     passed to setTimeout or setInterval
    CPG004  error    markup built from data: innerHTML, outerHTML,
                     insertAdjacentHTML or jQuery .html() given anything but a
                     literal - use textContent
    CPG005  error    Quickbase internals: DoSave(), gReq* globals, the hosting
                     page's DOM through parent/top/opener, scripts Quickbase
                     hosts for its own pages
    CPG006  error    an endpoint outside the documented REST API, or a request
                     to an a= action that is not an API_* call
    CPG007  error    an external library not pinned to an exact x.y.z version
    CPG008  warning  an external library from outside jsdelivr.net and
                     cdnjs.cloudflare.com, the trusted CDNs
    CPG009  warning  an external library at all - vanilla JS is the default;
                     confirm each one is warranted
    CPG010  error    a destructive call (delete, purge, copy an app) with no
                     confirm() or modal dialog before it
    CPG011  error    requests with no 429 / Retry-After handling
    CPG012  error    the REST or XML API with no temporary token, or
                     `auth="None"` on a page that calls Quickbase
    CPG013  warning  a temporary token fetched without credentials: "include"
                     or for the app rather than a table, or a REST call
                     without the QB-Realm-Hostname header
    CPG014  error    an alias token naming a table the application lacks
    CPG015  warning  a literal dbid or realm hostname, which exists in one
                     realm only
    CPG016  error    pageName= or pageID= naming a page the application lacks
    CPG017  warning  on a page handling sensitive data, values put in a URL
    CPG018  warning  a raw error or response shown to the user
    CPG019  warning  a URL parameter read with no validation in sight
    CPG020  warning  debug leftovers: console.log, console.debug, debugger
    CPG021  warning  request volume not stated, or above 4 per second
    CPG022  warning  nothing opens this page
    CPG023  warning  `auth="TempToken"` on a page that calls nothing
    CPG024  warning  no review header (a document not built by this builder)
    CPG025  warning  a name the platform will serve as plain text

## The rules behind it

A code page follows these rules:

- Use a temporary token for the acting user, never a stored credential.
- Give elevated access only through a pipeline the application owner controls.
- Use documented REST endpoints first, and `API_*` XML calls only where REST has
  no equivalent.
- Do not use internal Quickbase functions or hosted libraries, and do not
  manipulate the DOM of the hosting page.
- Use vanilla JS by default. Pin any library to an exact version, load it from a
  trusted CDN and name it in the header.
- Send POST bodies rather than query strings for anything sensitive.
- Use `textContent` rather than `innerHTML`.
- Show friendly errors in the page and raw ones only in the console.
- Respect `429` and `Retry-After`, with exponential backoff for transient
  failures.
- Ask for confirmation before anything destructive.
- Request only the fields the page shows.
- Put the review header on every file.

`STARTER_CODE_PAGE` is a page that clears every rule above: it reads `rid` and
validates it, fetches a temporary token for one table, queries only the fields
it shows, backs off on `429` and on network faults, and renders with
`textContent`. Adapt it rather than starting from nothing.
