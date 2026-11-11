# Requirements and decisions: gate 1a

What the application was asked to do, and what in the document does it.

A document can be valid QBL, parse, and create cleanly while missing half of
its requirements. None of those checks asks whether it does what was asked for.
The usual causes are an acceptance criterion nobody connected to anything:
totals the requirements asked for and nobody built; a notice meant for one
period that goes to every period; or a list the requirements asked for that the
build delivers as a count.

So the requirements become part of the spec, and the gate makes the connection
explicit:
    RequirementSpec("US-4", "Order entry", criteria=[
        CriterionSpec("US-4.AC1", "The order form lists its lines in a grid",
                      met_by=["form:Orders/Order Form",
                              "report:Order Lines/Embedded for Orders"]),
        CriterionSpec("US-4.AC2", "The form shows the order total",
                      met_by=["field:Orders/Order Total"]),
        CriterionSpec("US-4.AC3", "A typical order is entered in under two minutes",
                      status="runtime", met_by=["form:Orders/Order Form"],
                      note="Five pilot users time a ten-line order."),
    ])

Every criterion either names the artifacts that meet it or says, in so many
words, that it is not built, built differently, or out of scope - and the last
three need someone other than the builder to have agreed.

## Decisions

A build also makes choices the requirements leave open, and some they do not:
for example, a list of people that becomes two named users, or a one-click
action that becomes two clicks. `DecisionSpec` is where such a choice is recorded *before* it is
built, with who made it, and a choice only the builder has made is refused
until someone confirms it.

    REQ000  the spec states no requirements, so nothing traces           warning
    REQ001  a criterion traces to no artifact                            error
    REQ002  a traced artifact does not exist in the document             error
    REQ003  a criterion has a status the check does not know            error
    REQ004  a criterion needing a runtime test says nothing about it     warning
    REQ005  two requirements or criteria share an id                     error
    REQ006  a criterion not built, or built differently, gives no reason error
    REQ007  an artifact the spec traced is missing from a deployed export error
    DEC001  a builder's choice nobody has confirmed                       error
    DEC002  a decision the requirements ask to confirm, not confirmed     error
    DEC003  a criterion not built, or built differently, not confirmed    error
    DEC004  an artifact's notes record an assumption no decision covers   warning
    DEC005  a decision with a source the check does not know            error
    DEC006  a decision names an artifact the document does not have      error

## Artifact references

A reference is `kind:Table/Name` for things that live on a table and
`kind:Name` for things that live on the application:

    table:Orders                   field:Orders/Order Date
    report:Orders/My Orders        chart:Orders/Orders by Month
    form:Orders/Order Form         form_rule:Order Lines/Lock submitted lines
    data_rule:Orders               permission:Orders/Sales Rep
    email:Orders/Overdue reminder  document_template:Orders/Invoice
    relationship:Customers/Orders  (parent/child)
    role:Finance   page:Help   dashboard:My Work   pipeline:Nightly Export

They are resolved against the generated document rather than the spec, so the
fields and reports the builder adds on its own - a reference field, the
lookup that names its parent, an `Embedded for` report - can be traced too. The
same resolver reads a deployed export, which is how `REQ007` tells a build that
traced cleanly from a deployment that lost something on the way.
