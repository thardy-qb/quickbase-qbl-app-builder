# The gate ladder, and why the order matters

Each gate sees what the ones before it cannot, so they run in this order and a
failure at one is fixed before the next is read.

| Gate | Command | What it proves | What it cannot see |
| --- | --- | --- | --- |
| 1 compile | `check`, `build` | The spec is expressible: every name resolves, every closed value is one the builder can emit | Whether Quickbase will build the result |
| 1a requirements | `check`, `build` | Every acceptance criterion names what meets it, or says why not and who agreed; every choice a person did not make is confirmed (`REQ*`, `DEC*`) | Whether what meets a criterion does so correctly |
| 1b design | `check`, `build` | The data model is one an application should have (`DSN*`) | Anything about the platform |
| 1c code pages | `check`, `build` | Each code page clears the rules it must (`CPG*`); it is pattern matching over source, not a security review | What the code does when it runs |
| 2 offline | `check`, `build`, `create` | Schema, references, values, structure and formulas are well-formed (`SCH*`, `REF*`, `VAL*`, `STR*`, `FML*`) | Whether a formula means what you intend |
| 3 conformance | `check`, `build`, `create` | Every node type is one Quickbase supports in a solution create (`GEN001`, `GEN003`) | Combinations of nodes |
| 3b behaviour | `check`, `build`, `create` | No step writes nothing, no state is set by nothing, no send repeats (`BHV*`) | Runtime data |
| 3c create catalog | `check`, `build`, `create` | The document matches none of the shapes a create is known to fail on | New failures |
| 4 create | `create`, `probe` | Quickbase actually builds the document | Whether the application meets its requirements |

## Gate 4 is the proof, and it is not free

A create makes a real application. A document can clear gates 1 to 3c and still
be refused, or hang with no message. Formula bodies in particular are read by
nothing until the create. Treat a clean gate 4 as "it builds", never as "it
works": the requirements review (`requirements-review.md`) and a test against
real records are what show that.

## Reading the outcomes of a create

- `CREATED` with no errors: it builds. The ledger records the solution id, the
  app ids and a link to each.
- `REJECTED`: Quickbase answered with errors. They are listed as findings,
  grouped by code. Fix the spec and rebuild.
- `TIMEOUT`: no answer within the timeout. This is an outcome, not an
  exception: the create may still finish on the server later, so look for an
  application with that exact name. A hang means "this document", not "this
  kind of node"; run `probe` rather than reading the document for it.
- `ERROR`: no readable answer. An application may exist; check by name.
- A message that names no resource ("failure in creating one of the resources")
  is the same case as a timeout: run `probe`.

## Why the probe is a ladder of complete applications

Removing nodes at random from a failing document gives fragments that fail for
unrelated reasons. A ladder keeps every rung a whole, valid application: a floor
of tables, fields, relationships, forms and roles, then one family of additions
per rung in dependency order. The first rung that fails names the family, and
halving the family's items names the item. Each rung is named
`QBL probe <stamp> rung <n>: <family>` and is ledgered for cleanup.

## Updating a deployed application

A PUT replaces the solution wholesale and deletes whatever the document omits,
including the data in omitted fields. So:

1. Fetch the export (`fetch-deployed`) and build with `--deployed`, which keeps
   every deployed id and reports each node the document would delete.
2. Create validation copies (`create --intent edit`) until one is clean.
3. Ask the user, naming the solution id, the realm and the deletions.
4. Update with `--confirm <solutionId>`.
