# Quickbase QBL App Builder

An open-source Claude Skill that generates Quickbase QBL from a description or
a requirements document, and validates it by creating it in your own realm.

Whether a document will build is settled by Quickbase creating it, so the proof
is a create. This Skill therefore:

- builds the document and runs offline gates (requirements traceability, design
  review, schema, references, formulas, behaviour, a catalog of known create
  failures);
- creates it through the Quickbase Solutions API and reads the answer;
- records every call that may have created an application in a cleanup ledger,
  with a link to each, so you can delete them;
- localises a hang or an unnamed failure with a ladder of smaller creates;
- for an edit, validates on a clearly named copy and updates the deployed
  application only after you approve, with the deletions listed.

**It makes real applications in your realm. You delete them afterwards.** There
is no delete call in this Skill.

## Install

Upload the folder (or the zip) as a Skill in Claude. Python 3.9 or later is the
only requirement; the QBL library is in `scripts/qblparser/`, and PyYAML is
bundled under `scripts/vendor/`.

## Token setup

The only token source is your operating system's credential store (macOS
Keychain, Windows Credential Manager, Linux Secret Service), or a Claude
extension that holds the token. Run this yourself in a terminal:

    python3 scripts/store_token.py

It prompts for your realm (`myrealm` or `myrealm.quickbase.com`) and then for the
token, twice, without echo. There is no environment variable, file, argument or
pipe route, and the Skill will not accept a token pasted into a chat. If you
pasted one, rotate it in Quickbase. The token never appears in a command's
arguments: macOS reads it from standard input of `security -i`, Linux from
`secret-tool`, and Windows in-process.

    python3 scripts/store_token.py --where     # which store, which realm
    python3 scripts/store_token.py --remove    # delete it
    python3 scripts/check_token.py             # presence only; never reads it

## Workflow

Ask Claude to build an application. It follows `SKILL.md`. The commands are in
`scripts/build_qbl.py`:

    template, requirements, check, build, create, probe, fetch-deployed,
    update, cleanup, review, selftest

In short: draft requirements, write a spec, pass the offline gates, ask your
permission, create, and finish with the cleanup list.

### Approval to update an existing application

An update replaces a deployed solution and deletes whatever the document omits.
The agent must run `update ... --dry-run`, show you the output, and wait for your
explicit yes in the conversation before running `update ... --confirm`. Approval
is enforced by the agent following the Skill's instructions, together with your
host's own command-permission prompt. The script checks that a dry run was
recorded in the last 60 minutes for the same solution, document and deployed
export; it cannot verify that a person approved it.

## Cleanup

The cleanup ledger is `qbl-cleanup.json` in the current directory for every
command (`--ledger` overrides). `python3 scripts/build_qbl.py cleanup` lists
every test application still to delete, newest first, with links. After you
delete one in Quickbase, `cleanup --mark-deleted <solutionId>` records it.

## Layout

    SKILL.md        Instructions the agent follows
    scripts/        build_qbl.py and the Quickbase client scripts, the QBL
                    library (qblparser/) and bundled PyYAML (vendor/)
    references/     Spec reference, gate ladder, code pages, requirements and
                    behaviour checks
    examples/       A complete example application and a code page
    tests/          Unit tests, which need no network

## Tests

From this folder, with no network:

    python3 -I -S -m unittest discover -s tests

## Licence

MIT. See `LICENSE` and `NOTICE`.
