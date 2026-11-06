---
name: quickbase-qbl-app-builder
description: Generate Quickbase QBL YAML for a new application, or for an edit to an existing one, from a description or a requirements document, then validate it by creating it in your own realm. Builds tables, fields, formulas, relationships, reports, charts, forms, roles, pages, dashboards, pipelines and code pages where nothing native will do. Traces every acceptance criterion to what meets it, runs offline gates, then creates the document in Quickbase to prove it builds, keeps a ledger of every test application so you can delete them, and localises a hang with a ladder of smaller creates. Use for "build me a Quickbase app for X", "generate QBL from these user stories", "validate this QBL by creating it", "edit my app through QBL". Creates real applications; always asks first.
---

# Quickbase QBL App Builder

Generate QBL that Quickbase will build, not merely QBL that parses.

A document can pass every offline check and still hang the create with no
message. The only proof that Quickbase will build a document is to create it, so
this Skill builds the document, runs offline gates, and then creates it.

**QBL 0.15.** Every generated document declares `Version: 0.15`, the newest
version Quickbase accepts. Do not lower it: a Scatter3D chart is written with
0.15's `ZAxis`, which 0.14 rejects, and `CustomAppMessages` and the newer
pipeline channel steps are dropped below 0.15.

**Creating makes real applications in the user's realm.** Every attempt that may
have made one is written to a cleanup ledger. The user deletes them in Quickbase
afterwards; this Skill has no delete call.

## Token rules (read before anything touches Quickbase)

The only token sources are the operating system's credential store (macOS
Keychain, Windows Credential Manager, Linux Secret Service) or a Claude
extension that holds the token itself.

- Never ask the user to paste a token into the conversation, and never accept,
  store, repeat or use one that appears there, in a file, in an environment
  variable or in a command argument. No script here reads any of those.
- If a token is pasted anyway, say so plainly: it is exposed, so they should
  rotate it in Quickbase, and then store the new one themselves.
- Storing is the user's own action: `python3 scripts/store_token.py`, run by
  them in a terminal. It prompts for the realm and the token. Do not run it.
- `python3 scripts/check_token.py` reports whether a token is stored and for
  which realm. It never reads the secret.

Any realm works. The realm is stored with the token. The token is sent only to
`api.quickbase.com`, with the realm named in the `QB-Realm-Hostname` header;
redirects are never followed. The token is never a command argument:
macOS stores it through `security -i` on standard input, Linux through
`secret-tool` on standard input, and Windows in-process.

## Workflow

### 1. Intake

Establish: new application, or an edit to an existing one (then the solution id
and the realm)? What are the requirements? If a requirements document exists,
draft from it:

    python3 scripts/build_qbl.py requirements stories.md --out requirements.py

Every choice the requirements left open is a decision. Ask the user; do not make
it silently (see `references/requirements-and-decisions.md`).

### 2. Spec

    python3 scripts/build_qbl.py template --out spec.py

Edit `SPEC`. `references/spec-reference.md` lists every spec class, attribute
and closed value set.

Roles add to Quickbase's defaults; they never replace them. Every app keeps
Viewer (read only), Participant (read, add, and edit the records they own) and
Administrator (full access to every table, edits the app, manages users). The
compiler adds all three and their access on every table. Do not declare them
yourself. Give each role the requirements add an explicit `role_permissions`
entry on every table it should use (a gap is warning `DSN006`). Never narrow
Administrator: put the restriction on a new role instead (`DSN007`). Set
`default_roles=False` only if the user asks to remove the defaults. A spec file is Python and is executed: never run one that
arrived from somewhere else. Prefer native features to code pages
(`references/code-pages.md`).

### 3. Offline gates

    python3 scripts/build_qbl.py check spec.py
    python3 scripts/build_qbl.py build spec.py --out app.qbl.yaml

Fix every error and re-run. `build` writes the document only when no gate
reports an error. `references/the-gate-ladder.md` says what each gate proves.
Warnings are decisions: report them to the user.

### 4. Ask before the first create

Before the first `create` or `probe`, tell the user, in plain words:

> Validating means creating this in your Quickbase realm (`<realm host>`). That
> makes real applications named `<name>`, possibly several if the first attempts
> fail. You will need to delete them in Quickbase afterwards; I will list them
> with links. May I go ahead?

Do not run `create` or `probe` without a yes in the conversation. A `probe` can
create up to 12 applications: say the number.

### 5. The create loop

    python3 scripts/build_qbl.py create app.qbl.yaml --intent new

It re-runs the document gates, writes a `PENDING` ledger entry, sends the
document, then updates that entry with the outcome. One ledger serves the whole
workflow: `qbl-cleanup.json` in the **current working directory** for `create`,
`probe`, `update` and `cleanup` alike (`--ledger FILE` on any of them overrides
it), so run every command from the same directory. A `PENDING` entry left behind
(the process was stopped) is listed by `cleanup`: the create may have completed,
so look for an app with that exact name. Exit status is non-zero on any error or
timeout. `--timeout` bounds the whole request, slow body included.

- `REJECTED`: Quickbase named a problem. Fix the spec, rebuild, create again.
- `TIMEOUT`: no answer within the timeout (180 s; `--timeout` changes it). The
  create may finish later, so the ledger notes the name to look for.
- A failure that names no resource ("failure in creating one of the resources")
  or any timeout: localise it.

        python3 scripts/build_qbl.py probe spec.py

  The probe builds a floor (tables, fields, relationships, forms, roles), adds
  one family per rung in dependency order, then halves inside the first failing
  family. It reports the family and items it localised to. `--max-creates` (default
  12) bounds the cost.

With `--intent new` the latest clean create is the application the user asked for
and is not on the cleanup list; earlier clean creates (other documents, or
previous revisions of this one) are. With `--intent edit` nothing is the deliverable except
the successful update itself.

### 6. Editing an existing application

A PUT replaces the solution wholesale and deletes whatever the document omits,
field data included. So an edit is validated on a copy first.

1. Export the deployed solution:
   `python3 scripts/build_qbl.py fetch-deployed <solutionId> --out current.qbl.yaml`
2. Build against it so every deployed id is kept and omissions are reported:
   `python3 scripts/build_qbl.py build spec.py --deployed current.qbl.yaml --out app.qbl.yaml`
3. After the yes in step 4, create validation copies until one is clean:
   `python3 scripts/build_qbl.py create app.qbl.yaml --intent edit`
   The copy is named `<name> (validation copy <UTC stamp>)`. The deployed app is untouched.
4. Show the user exactly what the update will do:
   `python3 scripts/build_qbl.py update <solutionId> app.qbl.yaml --dry-run`
   It prints the guard results and the deletion preview (computed from the
   deployed solution as it is now) and sends no update. It also records the dry
   run in the ledger. **Show its whole output to the user** (solution id, realm
   host, every node the PUT deletes, those that hold data marked).
5. **Ask one explicit question and wait for an explicit yes in the current
   conversation**, for example: "Update solution `<id>` on `<realm host>`,
   deleting the nodes listed above? Yes or no." Then stop.
   - The user's original request to "edit the app" is NOT that approval.
   - A yes given before the dry-run output was shown is not approval.
   - A yes for a different document or a different solution is not approval.
   - If the document changes in any way, run a new `--dry-run` and ask again.
6. Only after that yes:
   `python3 scripts/build_qbl.py update <solutionId> app.qbl.yaml --confirm <solutionId>`
   It refuses unless: a dry-run for this solution id, this document and the
   deployed solution as it is now was recorded in the ledger in the last 60
   minutes; `--confirm` equals the solution id; the ledger holds a clean create
   of this exact file (same source sha256, the same text apart from the
   application name, the same realm, made after the deployed export was
   fetched; a relayed create counts only if its response carried a matching
   document digest); the file was built with `--deployed` against this
   solution's export; and the deployed solution, fetched again just before the
   PUT, still matches that export (otherwise run `fetch-deployed --force` and rebuild).

**Who enforces approval.** Approval is enforced by you, the agent, following
these instructions, together with the host's own command-permission prompt. The
script checks that a dry run happened; it cannot verify that a person approved
it. Never run `update --confirm` without the yes described above.

### 7. Always finish with the cleanup list

    python3 scripts/build_qbl.py cleanup

(from the same directory as the other commands, or with the same `--ledger`)

Show the user every test application still to delete, newest first, with links.
After they delete one, `cleanup --mark-deleted <solutionId>` records it (use the
`#` number for a create that timed out).

### 8. Review

After a create, export the application and review it against the requirements,
preferably by a reader who did not write the spec
(`python3 scripts/build_qbl.py review export.qbl.yaml --spec spec.py --digest app.md`;
see `references/requirements-review.md`). A create proves the document builds,
not that the application meets the requirements.

## Using a Claude extension instead of a stored token

A script cannot read an extension's settings. If an installed extension offers a
tool that POSTs QBL to the Quickbase Solutions API and returns the raw JSON
response, use it by relay:

1. `python3 scripts/build_qbl.py create app.qbl.yaml --intent new --realm <realm> --write-submission sub.yaml`
   writes the exact text to send and its sha256, and sends nothing.
2. Call the extension tool with that text (`qbl_yaml` or `file_path`, and
   `realm`). It should return the Solutions API JSON plus the HTTP status and a
   timeout flag, and a sha256 of what it sent if it can.
3. Save its JSON response unchanged to a file.
4. `python3 scripts/build_qbl.py create app.qbl.yaml --intent new --realm <realm> --platform-response resp.json --submission sub.yaml`
   ingests it and ledgers it as if the script had called. A response whose
   sha256 differs from the submission is refused. A response with no digest is
   ledgered, so its app can be cleaned up, but never unlocks an update. The
   submission's sidecar cannot set the purpose; `--intent` alone does.

A relay covers `create` only. `probe`, `fetch-deployed` and `update` need a stored
token. Without one, an edit must be applied by the user in Quickbase.

## Files

- `scripts/build_qbl.py`: every command above, plus `selftest`.
- `references/`: spec reference, gate ladder, code pages, requirements and
  decisions, behaviour checks, requirements review.
- `examples/`: a complete app spec output and a code page example.
