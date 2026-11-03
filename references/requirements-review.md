# Reviewing a built application against its requirements

A build's own requirements check is written by whoever built it, after building
it, so it checks what was built. A reviewer who did not write the spec should
read the deployed export against the requirements, criterion by criterion.

So the review is a separate step, with a separate reader, against what
Quickbase actually holds.

## When

- After every create or update, on the solution's **export**, not on the document
  that was sent. The platform can drop what it was sent: a schedule becomes
  `Manual`, an email loses its conditions, a pipeline step loses its inputs.
- Before handing a build to its owner, and whenever someone asks how well an
  application meets its requirements. That includes applications this Skill
  didn't build.

## Prepare the evidence

```bash
python3 scripts/build_qbl.py review export.qbl.yaml --spec spec.py --digest app.md
```

- The **findings** are what can be decided mechanically:
  - behaviour (`BHV*`): steps that write nothing, state nothing sets, sends that
    repeat, access nobody restricted;
  - `REQ007`: a traced artifact missing from the export.
- The **digest** (`app.md`) is the whole application in one readable file:
  - every table, field and formula, and every data rule;
  - every role's access, and the field-level permissions;
  - every report's filter and columns;
  - which form each role opens, every form rule, every email;
  - every pipeline step with what it writes, and **writes nothing** where it
    writes nothing.
- Pass `--full-formulas` when a criterion depends on the exact text of a
  formula.

Without a spec (an application built elsewhere), drop `--spec`. The review is
then behaviour plus the digest.

## Run the reviewer

Give a **fresh subagent** three things: the requirements document, `app.md`,
and the findings. It must not be the agent that wrote the spec, and it must not
see the spec or the build notes. A reviewer that has read the builder's
reasoning grades the reasoning, not the application.

Instruct it as follows:

> You are reviewing a Quickbase application against its requirements. You have
> the requirements document, a complete digest of the deployed application, and
> the findings of an automated behaviour check. You did not build it and should
> not assume anything works because it is named as if it does.
>
> For every acceptance criterion in the requirements, give one verdict:
>
> - **Met**: the digest shows what meets it. Cite the table, field, formula,
>   report, rule, role permission or pipeline step, by name.
> - **Partial**: something addresses it but not all of it. Say exactly which
>   part is missing.
> - **Not met**: nothing in the digest does it. Say what you looked for.
> - **Runtime**: the schema supports it, and only a test against real records
>   can prove it. Say the test.
>
> Rules:
>
> - A field or report with the right name is not evidence on its own. A status
>   only means something if a rule, pipeline or button sets it. A pipeline only
>   does what its steps write. An access rule is only enforced under
>   `CustomRule`.
> - Check that each automated step names its table, writes values, and targets
>   what its name says. Treat every behaviour finding as evidence about the
>   criteria it touches.
> - Where the application does something the requirements don't ask for, or
>   does it a different way, note it as a departure, whether or not it seems
>   reasonable.
> - Do not grade effort, code quality or intent. Grade what the application
>   does.
>
> Return a table with one row per criterion: id, verdict, evidence. Then list
> the departures. Then give a tally of met, partial, not met and runtime.

## Report it

- Give the tally first, then every partial and not-met criterion with its
  evidence, then the departures.
- Keep the reviewer's verdicts apart from the builder's traceability claims
  (`TRACEABILITY` in the review output). Where they disagree, the reviewer's
  verdict stands, and the disagreement is a finding about the trace.
- A runtime criterion is unproven, not met. Say which test would prove it.
- When reviewing someone else's application, describe what it does, not how it
  was made.
