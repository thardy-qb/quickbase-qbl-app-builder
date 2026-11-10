# `AppSpec` reference


The application spec that the builder compiles into QBL.

QBL is not a good target to generate directly. The constraints that decide
whether a document deploys are spread across containers that look
interchangeable and are not, shapes that look uniform and are not, and numeric
ranges that differ per type. None of them is anything a caller describing an
application should have to know.

So this is what a caller writes::

    AppSpec(
        name="Project Tracker",
        tables=[
            TableSpec("Clients", fields=[FieldSpec("Client Name", "Text")]),
            TableSpec("Projects", fields=[FieldSpec("Budget", "Currency")]),
        ],
        relationships=[RelationshipSpec("Clients", "Projects")],
    )

and `compile_app` turns it into QBL. The spec carries no logical IDs, no numeric
IDs, no containers and no built-in fields: those are all decisions with a right
answer, so the builder makes them.

## Index

- [`FieldSpec`](#fieldspec)
- [`SummaryColumnSpec`](#summarycolumnspec)
- [`SummaryFormulaSpec`](#summaryformulaspec)
- [`ReportSpec`](#reportspec)
- [`FormRuleTriggerSpec`](#formruletriggerspec)
- [`FormRuleConditionSpec`](#formruleconditionspec)
- [`FormRuleActionSpec`](#formruleactionspec)
- [`FormRuleSpec`](#formrulespec)
- [`FormColumnSpec`](#formcolumnspec)
- [`FormSectionSpec`](#formsectionspec)
- [`FormSpec`](#formspec)
- [`FormElementSpec`](#formelementspec)
- [`LegacyFormTabSpec`](#legacyformtabspec)
- [`LegacyFormSectionSpec`](#legacyformsectionspec)
- [`LegacyFormSpec`](#legacyformspec)
- [`ChartSpec`](#chartspec)
- [`RoleFormDefaultSpec`](#roleformdefaultspec)
- [`ReportFormOverrideSpec`](#reportformoverridespec)
- [`TableRolePermissionSpec`](#tablerolepermissionspec)
- [`TableSpec`](#tablespec)
- [`RelationshipSpec`](#relationshipspec)
- [`PageSpec`](#pagespec)
- [`DashboardWidgetSpec`](#dashboardwidgetspec)
- [`DashboardFilterSpec`](#dashboardfilterspec)
- [`DashboardTabSpec`](#dashboardtabspec)
- [`DashboardSpec`](#dashboardspec)
- [`HomeWidgetLinkSpec`](#homewidgetlinkspec)
- [`HomeWidgetFieldSpec`](#homewidgetfieldspec)
- [`HomeWidgetSpec`](#homewidgetspec)
- [`GuideSpec`](#guidespec)
- [`EmailConditionSpec`](#emailconditionspec)
- [`CustomEmailSpec`](#customemailspec)
- [`DocumentTemplateSpec`](#documenttemplatespec)
- [`VariableSpec`](#variablespec)
- [`PipelineFilterSpec`](#pipelinefilterspec)
- [`PipelineStepSpec`](#pipelinestepspec)
- [`PipelineActionSpec`](#pipelineactionspec)
- [`PipelineSpec`](#pipelinespec)
- [`ConnectedColumnSpec`](#connectedcolumnspec)
- [`ConnectedTableSpec`](#connectedtablespec)
- [`RoleSpec`](#rolespec)
- [`AppSpec`](#appspec)

## Specs

### `FieldSpec`

A field. `kind` is the part of `QB::Field::<kind>` a caller cares about.

Three kinds need more than a label, and the builder supplies the rest:

- `Address` is six fields plus one. The platform refuses a bare
  `QB::Field::Address` (`Missing required property Format`, `Street1`, ...)
  and refuses each subfield on its own (`QB::Field::AddressCity must have a
  related QB::Field::Address`), so neither half exists without the other.
- `Lookup` reads a field from a parent table through a relationship.
- `Summary` rolls a child table up, and its function word is not the one
  most tools use.

- **`label`** — `str`, default required
- **`kind`** — `str`, default `'Text'`
- **`formula`** — `Optional[str]`, default `None`
  For a formula field. The kind still names what it produces, e.g.
  `Text::Formula` - there is no generic `QB::Field::Formula`.
- **`choices`** — `Optional[List[str]]`, default `None`
  For `TextMultipleChoice` and `MultiselectText`.
- **`lookup_table`** — `Optional[str]`, default `None`
  For a lookup: the parent table and the field to pull down.
- **`lookup_field`** — `Optional[str]`, default `None`
- **`lookup_via`** — `Optional[str]`, default `None`
  Where a child references one parent more than once - an Assigned
  Auditor and an Updated By both pointing at Staff - the label of the
  reference field a lookup reads through, or a summary rolls up through.
  Required in that case: without it the builder would have to guess
  which relationship to use.
- **`link_source`** — `Optional[str]`, default `None`
  For a `ReportLink`: the field in this table to match on, and the table
  and field elsewhere to match it against.

  A report link is a field relationship, not a report reference - `Source`
  names a field here, `Target` a table and a field there, and both are
  `!Ref`s. Unwired, the platform answers any form element embedding a view
  through it with `BadPropertyWrongReferenceType: ... refers to a deleted
  or changed report or chart`, so the field and the embedded view that
  reads it are only usable together.
- **`link_table`** — `Optional[str]`, default `None`
- **`link_field`** — `Optional[str]`, default `None`
- **`address_format`** — `str`, default `'United States'`
  For an address: which country format the subfields follow.
- **`summarize_table`** — `Optional[str]`, default `None`
  Only for a summary field: the child table it counts or totals.
- **`summarize_field`** — `Optional[str]`, default `None`
  Only for a summary field: the child field to total. Omit to count rows.
- **`summarize_by`** — `str`, default `'Count'`
  `Count` or `Total`. `Sum` is what every other tool calls it and the
  platform rejects it, so the spec takes the friendly word and the
  builder emits what Quickbase wants.
- **`unique`** — `bool`, default `False`
  Whether the field's values must be unique. Required of the key field a
  connected table refreshes on - the platform answers a non-unique one
  with `BadProperty: Only unique fields are allowed to be used as
  refreshed keys`.
- **`required`** — `bool`, default `False`
  Whether a value has to be supplied before a record can be saved.

  A business rule, not a tidiness default. Every user meets it, on every
  record including the ones already in the table, so set it only when
  the requirements say the value is mandatory, or when something the
  requirements asked for cannot work without it. "It names the record" is
  not a reason on its own: making a person's first and last name required
  when nobody asked for it blocks a record for someone known only by a
  surname. Record why in `comments`.
  The design review lists every required field (`DSN003`) so the choice is
  confirmed rather than assumed.
- **`help_text`** — `Optional[str]`, default `None`
  The hover text **end users** see beside the field.

  Leave it unset unless the requirements ask for guidance on a field.
  It is content in front of every user of the app, so it is theirs to
  word; a builder's reasons, examples of the data, where a value came
  from and what it drives all belong in `comments` - not text such as a
  planned approach for asking a donor, or an example code. Put a
  suggested wording in `comments` if one is worth offering. The design
  review lists every help text (`DSN004`).
- **`comments`** — `Optional[str]`, default `None`
  A note for **builders**, shown only in the field's settings: why the
  field exists, the requirement behind it, where its data came from, what
  depends on it. For example, "Used in project
  intake pipeline. Do not delete." Requirement and design notes belong
  here rather than in `help_text`, which would put them in front of
  every end user.
- **`default_value`** — `Optional[Any]`, default `None`
  The value a new record starts with.
- **`opens_page`** — `Optional[str]`, default `None`
  For a `URL::Formula` field: the name of a code page this field opens,
  as a button, for the record it is on. The builder writes the formula
  Quickbase's own exports use -
  `URLRoot() & "db/" & Dbid() & "?a=dbpage&pageName=<page>&rid=" & [Record ID#]`
  - so the page reads the record id from `rid`. Leave `formula` unset.
- **`properties`** — `Dict[str, Any]`, default `{}`
  Anything else the field's type permits, by its QBL property name:
  `{"DecimalPlaces": 2, "Units": "hrs", "TreatBlankAsZero": True}`.

  An escape hatch rather than forty named attributes. A field carries a
  display and formatting layer this spec had no way to express at all -
  `DecimalPlaces`, `CurrencySymbol`, `NumberFormat`, `Units`, `Width`,
  `MaxLength`, `TreatBlankAsZero` - and naming each one would go stale the
  next time QBL adds a property while still not covering the ones that
  differ per field kind. Every name is checked against the schema for the
  field's type, so a typo is a compile error rather than a property the
  platform silently drops.

### `SummaryColumnSpec`

One aggregate column of a summary report, or one summary variable.

Both are the same shape - a field and how to roll it up - and both hang off
the report beside `Properties` rather than inside it, which is why a reader
looking only at `Properties` finds neither.

- **`field`** — `str`, default required
  The label of the field being rolled up.
- **`summarize_by`** — `str`, default `'Total'`
  `Total`, `Average`, `Maximum`, `Minimum`, `DistinctCount` or
  `StdDeviation`.

### `SummaryFormulaSpec`

A formula column computed from a report's own aggregates.

Its `formula` names those aggregates rather than fields: a summary variable
over `Hours` summarised by `Total` is written `[Hours (tot)]`.

- **`label`** — `str`, default required
- **`formula`** — `str`, default required
- **`kind`** — `str`, default `'Numeric'`
  The part of `QB::Report::SummaryFormula::<kind>` that says what it
  produces - there is no generic one.

### `ReportSpec`

- **`name`** — `str`, default required
- **`kind`** — `str`, default `'Table'`
- **`columns`** — `List[str]`, default `[]`
  The fields the report shows, by label. Omit for the table's defaults.
- **`sort_by`** — `List[str]`, default `[]`
  Fields to sort and group by, by label, ascending.
- **`filters`** — `List[tuple]`, default `[]`
  Rows the report shows, as `(field label, operator, value)` triples
  combined with AND. Quickbase writes a filter as a criteria string
  addressing fields by *numeric* id - `({'28'.EX.'Completed'})` - and the
  builder assigns those ids, so a caller cannot write one by hand without
  knowing what the builder decided. Declared by label here and resolved
  when the ids exist.

  Operators are Quickbase's own: `EX` equals, `XEX` does not equal, `CT`
  contains, `XCT` does not contain, `GT`/`GTE`/`LT`/`LTE`, `BF` before,
  `OAF` on or after, `TV` true value.

  filters=[("Status", "XEX", "Closed"), ("Is Overdue", "EX", "1")]
- **`group_by_field`** — `Optional[str]`, default `None`
  The field a `Kanban` groups its columns by, by label. Required for that
  kind: a kanban with no `CardGroups` has no columns to put cards in, and
  the platform answers one with a create that hangs and no diagnostic.
  Ignored by every other kind.
- **`summary_columns`** — `List[SummaryColumnSpec]`, default `[]`
  Aggregate columns, for a `Summary` report.
- **`summary_variables`** — `List[SummaryColumnSpec]`, default `[]`
  Aggregates a summary formula can name. Quickbase derives the name from
  the field's label and the rollup: `Total` becomes `(tot)`.
- **`summary_formulas`** — `List[SummaryFormulaSpec]`, default `[]`
  Formula columns over those aggregates.
- **`report_formulas`** — `List[SummaryFormulaSpec]`, default `[]`
  Formula columns computed per row, which any report kind may carry - not
  only a summary. A summary formula reads a group's aggregates
  (`[Hours (tot)]`); a report formula reads the row's own fields
  (`Today() - ToDate([Due])`), and the two are told apart only by their
  container and their type.
- **`properties`** — `Dict[str, Any]`, default `{}`
  Anything else the report's kind permits, by its QBL property name.

  The shapes differ far too much between kinds to name them all here - a
  calendar's `CalendarEvents`, a timeline's `Timeline`, a kanban's
  `CardGroups`, a map's `AddressField` - so those go here, checked against
  the schema for the report's type.

### `FormRuleTriggerSpec`

What makes a rule fire, when a field comparison is not it.

A rule is written with one of two triggers - a `Trigger::Field`, or a
`Trigger::MultipleConditions` when it carries conditions. The platform has
two more:

- `RecordState` fires on the form itself rather than on any field:
  `IsOpened` when the record is opened, `IsSaving` as it saves. It takes no
  field and no comparison, only the state.
- `User` fires on who is looking: `Comparison: IsInRole` against a `!Ref`
  naming a role.

Set `kind` and the attributes that kind reads. A `Field` trigger is what
`FormRuleSpec`'s own `when_field`/`equals`/`comparison` already build, so
this is only needed for the other two.

- **`kind`** — `str`, default `'RecordState'`
  `Field`, `FieldIncludes`, `RecordState` or `User`. `FieldIncludes`
  fires on a multi-select field including (`Includes`) or not including
  (`DoesNotInclude`) a `value`.
- **`record_state`** — `str`, default `'IsSaving'`
  For `RecordState`: `IsOpened` or `IsSaving`.
- **`role`** — `Optional[str]`, default `None`
  For `User`: the name of the role to test against.
- **`field`** — `Optional[str]`, default `None`
  For `Field`: the label of the field tested, and what against.
- **`value`** — `Any`, default `None`
- **`comparison`** — `str`, default `'IsEqualTo'`
  For `Field` and `User`. A user trigger compares with `IsInRole`.

### `FormRuleConditionSpec`

One entry in a rule's `If` - a further condition on top of the trigger.

`value` is written straight through, so a structured comparison value works
as well as a scalar. A user or multiple-choice field is compared by choice
rather than by text:

    FormRuleConditionSpec("Team Member",
                          value={"MatchExactChoice": True, "BaseValue": -1002})

- **`field`** — `Optional[str]`, default `None`
  The label of the field tested. Unused by `User` and `Formula`.
- **`value`** — `Any`, default `''`
- **`comparison`** — `str`, default `'IsEqualTo'`
- **`kind`** — `str`, default `'Field'`
  What the condition tests, as the part of `QB::FormRule::Condition::<kind>`:

  - `Field` compares a field's value (`IsEqualTo`, ...).
  - `FieldChange` asks whether a field changed as the record saves:
  `Changed`, `ChangedTo` or `ChangedFrom` (with a `value`). Only valid
  on a rule whose trigger is a saving `RecordState` - checked as STR006.
  - `FieldIncludes` tests a multi-select field: `Includes` or
  `DoesNotInclude` a `value`.
  - `User` tests who is looking: `IsInRole` against `role`.
  - `Formula`, on a FormV2 rule only: true when `formula` is -
  `QB::FormV2::Rule::Condition::FormulaIsTrue`.

  On a FormV2 rule `FieldIncludes` is a `Field` condition comparing with
  `Includes`, `User` is a `Role` condition, and `FieldChange` has no
  equivalent.
- **`role`** — `Optional[str]`, default `None`
  For a `User` condition: the role's name.
- **`formula`** — `Optional[str]`, default `None`
  For a `Formula` condition.

### `FormRuleActionSpec`

One entry in a rule's `Actions`.

- **`action`** — `str`, default `'Hide'`
  The part of `QB::FormRule::Action::<action>` that names what it does.
- **`target_field`** — `Optional[str]`, default `None`
  The label of the field acted on. Not every action has one - `AbortSave`
  and `DisplayMessage` act on the record and the user.
- **`value`** — `Optional[Any]`, default `None`
  For `Change`: what to set the target to.
- **`value_field`** — `Optional[str]`, default `None`
  For `Change`: the label of a field to copy the value *from*, rather than
  a literal. Written as a `!Ref`, which `value` cannot express - useful to
  keep a history field in step with the field it mirrors.
- **`message`** — `Optional[str]`, default `None`
  For `DisplayMessage` and `AbortSave`.
- **`target_section`** — `Optional[str]`, default `None`
  FormV2 only: a section to act on, by its title, in place of a field -
  hide an Admin section from everyone but admins.
- **`target_column`** — `int`, default `1`
  Which column of `target_section` to act on, from 1. `SetColor` colours a
  column; the same action pointed at a field hangs the create with no
  diagnostic. Ignored by every other action.
- **`color`** — `Optional[str]`, default `None`
  FormV2 `SetColor`: a hex colour.
- **`label`** — `Optional[str]`, default `None`
  FormV2 `SetLabel`: the label to show.
- **`message_type`** — `str`, default `'Modal'`
  FormV2 `DisplayMessage`: `Modal` or `Notification`; and `Info` or
  `Error`.
- **`message_level`** — `Optional[str]`, default `None`

### `FormRuleSpec`

A rule that acts on a field when another field holds a value.

`When` and `Actions` are arrays on the emitted node while `Rules` itself is
keyed - two conventions in one object, and the wrong one costs the whole
document with an `Unparsed` that names nothing.

`If` is a third array beside those two, and it is *not* a key inside a
trigger. Written there the platform accepts the document and never reads the
container, so a rule's conditions are silently discarded and the rule fires
on its trigger alone - established by planting a bogus type in each position
and seeing `NodeRemoved` from only one of them.

- **`name`** — `str`, default required
- **`when_field`** — `Optional[str]`, default `None`
  The field the rule watches, and the value it watches for. Not needed
  when `trigger` names a record state or a user instead.
- **`equals`** — `Any`, default `None`
- **`target_field`** — `Optional[str]`, default `None`
  The field the rule's first action acts on. `AbortSave` and
  `DisplayMessage` act on the record and on the user, so they take none -
  and the platform answers a target on either with `ExtraProperty`, which
  it then ignores, so nothing says the target was meaningless.
- **`action`** — `str`, default `'Hide'`
- **`comparison`** — `str`, default `'IsEqualTo'`
  How the trigger compares `when_field` against `equals`.
- **`conditions`** — `List[FormRuleConditionSpec]`, default `[]`
  Further conditions, all of which must hold. These are the rule's `If`.
- **`actions`** — `List[FormRuleActionSpec]`, default `[]`
  Actions beyond the one named by `action` and `target_field`.
- **`trigger`** — `Optional[FormRuleTriggerSpec]`, default `None`
  A trigger other than a field comparison - a record state, or who is
  looking. Replaces `when_field`/`equals`/`comparison` when set.
- **`true_when`** — `str`, default `'All'`
  Whether every condition must hold (`All`) or any one of them (`Any`).
  `All` or `Any` of the conditions.
- **`run_on`** — `str`, default `'RecordOpenSaveOrChange'`
  FormV2 only: when the rule is evaluated. `RecordOpenSaveOrChange` is the
  usual choice, including for rules that abort a save; `RecordSave` and
  `RecordSaveAfterValidating` are the others.
- **`fire_only_on_change`** — `bool`, default `False`
  Whether the rule fires only when the triggering value changes.
- **`disabled`** — `bool`, default `False`
  Whether the rule is switched off.
- **`properties`** — `Dict[str, Any]`, default `{}`
  Anything else `QB::FormRule` permits - in practice `CompactSpaceOnHide`.

### `FormColumnSpec`

One column of a section, holding fields by label.

- **`fields`** — `List['FormMember']`, default `[]`
  A field label, or a `FormElementSpec` where a label cannot say enough -
  an embedded report, prose, a group, or a field under its own label.
- **`layout_width`** — `Optional[int]`, default `None`
  How many of a section's twelve columns this one spans. An integer, not a
  width keyword - `LayoutWidth: Full` is refused with an `Unparsed` naming
  nothing, and a fraction with `BadProperty: LayoutWidth`.

  Left unset, the section's twelve are divided between its columns, so two
  columns are six each and three are four each. The widths must total no
  more than twelve: two columns of twelve is 24 and the platform answers
  `BadMaxItems: the total layout width of all columns is 24, which exceeds
  the maximum allowed value of 12.`

  Set it when the columns are not equal. The section's widths may total
  less than twelve - the platform accepts 4 and 4 - but not more.

### `FormSectionSpec`

- **`title`** — `Optional[str]`, default `None`
- **`columns`** — `List[FormColumnSpec]`, default `[]`
- **`modes`** — `Optional[List[str]]`, default `None`
  The modes this section and its elements show in - any of `Edit`, `View`
  and `Create`. Left unset they show in all three.

  The third mode is spelled `Create`, not `Add`; `Add` is answered
  `BadProperty`. An empty list is not "no opinion" - it is the platform's
  own reading of an omitted `ModesToShowIn`, and it hides the section in
  every mode. Pass `["View"]` for a section only a saved record shows, not
  `[]`.

### `FormSpec`

A FormV2 layout.

Omit it and the table still gets a form: one section listing every field
the table has, which is what Quickbase itself would build. Name it here to
say anything more than that.

- **`name`** — `str`, default `'Main Form'`
- **`sections`** — `List[FormSectionSpec]`, default `[]`
- **`rules`** — `List[FormRuleSpec]`, default `[]`
- **`properties`** — `Dict[str, Any]`, default `{}`
  Anything else `QB::FormV2` permits, by its QBL property name.

### `FormElementSpec`

One element of a form, where a field label alone is not enough.

A legacy row or section, and a FormV2 column, all take plain label strings,
and that is still the common case. This is for the things a string cannot
say.

Which element type it becomes is inferred from what is set, so the same
spec reads the same way on either form family:

    members set          a `QB::FormV2::Element::Group`
    content set          a `RichText` on a FormV2, a `::Text` on a legacy
    embedded_report set  a `Report` on a FormV2, an `EmbeddedView` on a
                         legacy element
    field set            an ordinary field element

`kind` overrides the inference and is checked against the family being
built. Two of the possibilities are FormV2's alone: it has no spacer to
match a legacy `::Empty`, and a legacy form has no group.

The first is a property on the element itself. An element carries its own
layer separate from the field's - a `Label` that overrides the field's
label on this form only, and the `EmbeddedView` that makes a report link
show a report inline (`TargetReport`, `RowsToDisplay`, `MaxHeightInPixels`,
`Editable`).

The second is an element that is not a field at all. A legacy form's
`::Text` element holds prose (with `IsHTML` to say how to read it) and its
`::Empty` element is a spacer; both are ordinary members of a row and
neither has a field to name. Give `kind` and leave `field` unset.

- **`field`** — `Optional[str]`, default `None`
  The label of the field this element places. Omit for a `Text` or `Empty`.
- **`kind`** — `Optional[str]`, default `None`
  The element type, as the part of `QB::Form::Element::<kind>`. Inferred
  from the field's own kind when a field is named, so it is only needed for
  an element that has no field.
- **`label`** — `Optional[str]`, default `None`
  A label for this element, overriding the field's own on this form.
- **`embedded_report`** — `Optional[str]`, default `None`
  The report or chart to show inline, by name. Needs a `ReportLink` field,
  or a reference field, in `field`.

  Named rather than left to `properties` because the property body is a
  `!Ref` over two logical IDs:

  EmbeddedView:
  TargetReport: !Ref
  Table: $Table_Tasks
  Report: $Report_Embedded_for_Projects

  Written as a plain mapping instead, the platform answers `ExtraProperty`
  for `Table` and for `Report` and the element embeds nothing - so an
  escape hatch alone would hand a caller a document that looks right and
  silently shows no report.
- **`embedded_table`** — `Optional[str]`, default `None`
  The table holding that report. Defaults to the form's own table; a report
  from another table can be embedded as well.
- **`embedded_rows`** — `int`, default `50`
  How many rows the embedded report shows.
- **`content`** — `Optional[str]`, default `None`
  `Editable` and `MaxHeightInPixels` are not attributes here because the
  builder always emits them - an `EmbeddedView` carrying only
  `TargetReport` and `RowsToDisplay` makes a create time out. Override
  either through `properties`, which deep-merges over what the builder
  built.
  Prose. On a FormV2 this is a `QB::FormV2::Element::RichText` and the
  text is its `Content`; on a legacy form it is a `::Text` element and
  the text is its `Text`, written as HTML.

  Both sides treat it as rich text, so a `<` is markup. Escape it if it
  is meant to be read as a character.
- **`members`** — `List['FormMember']`, default `[]`
  The elements inside a `QB::FormV2::Element::Group`, which is a FormV2
  element that holds other elements rather than showing a value of its
  own. A legacy form has no equivalent and a group is refused there.

  A group may not contain another group - the platform answers
  `BadChild: Group element cannot contain nested group elements.`
- **`properties`** — `Dict[str, Any]`, default `{}`
  Anything else the element type permits, by its QBL property name.
  Checked against the schema for that type. Merged over anything named
  above, so a caller can add `Editable` or `MaxHeightInPixels` to an
  `EmbeddedView` without restating the reference.

### `LegacyFormTabSpec`

A tab inside a legacy form's section.

A tab is a *marker*, not a container. The platform writes it as an element in
the section's own `Elements`, and the rows after it belong to it until the
next tab - so a section with tabs is a flat ordered sequence of tab markers
and rows.

- **`label`** — `str`, default required
- **`color`** — `Optional[str]`, default `None`
  A hex colour for the tab strip, e.g. `#0a69c7`.
- **`rows`** — `List[List[FormMember]]`, default `[]`
  Each entry is one row of members - a field label, or a
  `FormElementSpec` where a label is not enough.

### `LegacyFormSectionSpec`

A section of a legacy form, holding fields by label.

- **`heading`** — `Optional[str]`, default `None`
- **`fields`** — `List[FormMember]`, default `[]`
  Members placed straight into the section, without a row around them.
- **`rows`** — `List[List[FormMember]]`, default `[]`
  Each entry is one row of field labels. This is how a legacy form is built -
  its fields sit in rows inside sections, and `QB::Form::Element::Row` answers `BadChild: Form Rows must have
  defined Elements` if given none, so the row is real structure rather than
  presentation.
- **`tabs`** — `List[LegacyFormTabSpec]`, default `[]`
  Tabs, in order, each with the rows that belong to it.

### `LegacyFormSpec`

A `QB::Form`, the layout Quickbase built before FormV2.

Worth generating even though a new application would not use one: existing
applications are full of them, and a table may carry both.

The shapes are the opposite of FormV2's in two places. `Elements` is keyed
and `Rules` is an array, where a FormV2 keys its `Rules` and puts arrays
inside them. And the element type has to match the field's kind: a currency
field needs a `CurrencyField` element, and every formula field of any kind
needs a `FormulaField`.

- **`name`** — `str`, default `'Main Form'`
- **`fields`** — `List[FormMember]`, default `[]`
- **`sections`** — `List[LegacyFormSectionSpec]`, default `[]`
- **`rules`** — `List['FormRuleSpec']`, default `[]`
- **`properties`** — `Dict[str, Any]`, default `{}`
  Anything else `QB::Form` permits, by its QBL property name:
  `{"WrapFieldLabels": True, "NewFieldAction": "Add"}`.

  `QB::Form` has twenty-five properties, among them
  `HorizontalRuleBetweenSections`, `ShowBuiltInFields`, `WrapFieldLabels`,
  `ShowSaveAndCancelButtons`, `ShowSaveAndKeepWorking`,
  `WaitForEmbeddedReports` and `NewFieldAction`.

### `ChartSpec`

A chart. `kind` is the part of `QB::Chart::<kind>` a caller cares about.

The 28 chart types fall into three shapes, and which one a type wants is
not deducible from its name - `Funnel` and `Funnel3D` differ, and so do
`Gauge` and `RadialBar`. The builder picks; a caller names the two fields
and the picture.

- **`name`** — `str`, default required
- **`value_field`** — `str`, default required
  The field plotted on the value axis. Never `Record ID#`: a chart
  series refuses it as a source. To count records, add a hidden
  `Numeric::Formula` field whose formula is `1` and chart its `Sum`.
- **`category_field`** — `Optional[str]`, default `None`
  The field the values are grouped by. Not used by gauges.
- **`kind`** — `str`, default `'Bar'`
- **`summarize_by`** — `str`, default `'Sum'`
  How the series aggregates. `Sum` (the default), `Average`, `Minimum`,
  `Maximum`, `DistinctCount` or `StdDeviation`. Not `Count`, which a
  summary field takes and a chart series refuses with `BadProperty`.
- **`second_field`** — `Optional[str]`, default `None`
  A second measure, for the kinds that plot one: a bubble's size, a
  variwide bar's width, a 3D scatter's X axis.
- **`report_formulas`** — `List[SummaryFormulaSpec]`, default `[]`
  Formula columns the chart computes for itself, keyed beside its
  `Properties` the way a report's are.
- **`summary_variables`** — `List[SummaryColumnSpec]`, default `[]`
  Aggregates a chart's formulas can name, and formulas over them.
- **`summary_formulas`** — `List[SummaryFormulaSpec]`, default `[]`
- **`properties`** — `Dict[str, Any]`, default `{}`
  Anything else the chart's kind permits, by its QBL property name:
  `{"Description": "...", "DrilldownReport": "Default"}`.

  A chart's filters, `DrilldownReport`, description, role permissions,
  sort direction, goal line label, legend colours, secondary axis and - on
  a gauge - its colour thresholds are all set here.

  An escape hatch rather than a named attribute per kind, for the reason
  `ReportSpec` has one: the shapes differ far too much between kinds to
  name them here, and every name is checked against the schema for the
  chart's type, so a typo is a compile error rather than a property the
  platform drops. Nested bodies are merged into what the builder builds
  rather than replacing it, so setting `DataDetails.GoalLine` does not
  discard the axes.

### `RoleFormDefaultSpec`

Which form a role opens, per way of opening a record.

QBL keeps these on the table under `Forms.Properties.RoleDefaults`, keyed by
logical role ID with an `Everyone` entry beside them - the other half of the
permission model from `TableRolePermissionSpec`. Without it a generated
table gives every role the platform's default form.

A form is named by its own name, matched against the table's `form` and
`legacy_form`. `Default` means "whatever `Everyone` says".

`grid_edit` is `None` or `StandardBehavior` on any entry. `Default` is
answered `BadProperty` - and the platform then reports the role and the
whole `RoleDefaults` container as bad too, so one wrong word costs every
role's form assignment.

`mobile` is the odd one: its value depends on *which* entry carries it,
and the two domains are each other's refusal.

    Everyone   UseFullSiteForms
    a role     Default

Leave it unset and each entry gets the one value it accepts.

- **`view_form`** — `str`, default `'Default'`
- **`edit_form`** — `str`, default `'Default'`
- **`add_form`** — `str`, default `'Default'`
- **`grid_edit`** — `str`, default `'None'`
- **`mobile`** — `Optional[str]`, default `None`
  Left unset, each entry gets the one value it accepts. Set it only to be
  explicit - there is nothing to choose between.

### `ReportFormOverrideSpec`

Which form a particular report opens a record with.

Keyed by report name under `Forms.Properties.ReportOverrides`. `UseRoleSettings`
defers to the role and is the default, so an override has to be asked for.

- **`view_form`** — `str`, default `'UseRoleSettings'`
- **`edit_form`** — `str`, default `'UseRoleSettings'`
- **`grid_edit`** — `str`, default `'UseRoleSettings'`
- **`mobile`** — `str`, default `'UseRoleSettings'`

### `TableRolePermissionSpec`

What one role may do in one table.

QBL records these on the *table*, under
`Properties.RolePermissions.$Role_<name>`, not on the role - so this hangs
off `TableSpec` even though it reads like a property of a role.

Without a permission here every role gets the platform's default access
to every table, which makes a generated application unusable rather than
merely plain.

`view_records` and `modify_records` take `Always`, `Never` or `CustomRule`.
A criteria string is a Quickbase query - `{'6'.TV.'_curuser_'}` - and only
means anything under `CustomRule`; the platform keeps one written beside
`Always` and ignores it.

- **`can_add`** — `bool`, default `False`
- **`can_delete`** — `bool`, default `False`
- **`can_save_common_reports`** — `bool`, default `False`
- **`can_edit_field_properties`** — `bool`, default `False`
- **`view_records`** — `str`, default `'Always'`
- **`view_criteria`** — `Optional[str]`, default `None`
- **`modify_records`** — `str`, default `'Always'`
- **`modify_criteria`** — `Optional[str]`, default `None`

### `TableSpec`

- **`name`** — `str`, default required
- **`fields`** — `List[FieldSpec]`, default `[]`
- **`reports`** — `List[ReportSpec]`, default `[]`
- **`charts`** — `List[ChartSpec]`, default `[]`
- **`form`** — `Optional['FormSpec']`, default `None`
- **`legacy_form`** — `Optional['LegacyFormSpec']`, default `None`
- **`emails`** — `List['CustomEmailSpec']`, default `[]`
- **`document_templates`** — `List['DocumentTemplateSpec']`, default `[]`
- **`singular`** — `Optional[str]`, default `None`
- **`plural`** — `Optional[str]`, default `None`
- **`role_permissions`** — `Dict[str, 'TableRolePermissionSpec']`, default `{}`
  What each role may do in this table, by role name. See
  `TableRolePermissionSpec` - a table is where QBL records them, not the
  role.
- **`role_forms`** — `Dict[str, 'RoleFormDefaultSpec']`, default `{}`
  Which form each role opens, by role name or `Everyone`.
- **`report_form_overrides`** — `Dict[str, 'ReportFormOverrideSpec']`, default `{}`
  Which form a given report opens a record with, by report name.
- **`properties`** — `Dict[str, Any]`, default `{}`
  Anything else `QB::Table` permits, by its QBL property name:
  `{"Description": "...", "CustomDataRules": {"Formula": "...",
  "TurnedOn": True}}`.

  A table row carries a name, a singular and a plural; a table has about
  forty other properties -
  `CustomDataRules`, `RecordTitleField`, `DefaultReportSettings`,
  `KanbanManualOrderField`, `TableIconName`, `Searchable`, `SaveOnExit`,
  `IndexFileAttachments`, `TableHomePageSettings` among them. Checked against the schema for
  `QB::Table`.
- **`default_columns`** — `Optional[List[str]]`, default `None`
  The table's default columns, by label: the fields a new report, the
  table's "List All" and a `Default` embedded view show.

  QBL has no column list for this. A field is a default column when it
  carries `AddToAllNewReports: true`, which the Quickbase UI ticks for
  every field it creates. A generated field that carries nothing gets
  `false`, and the table opens on an empty default report, which reads as
  a broken application.

  Left unset, the columns of this table's own planned reports are used, in
  the order they first appear; a table whose reports name no columns
  falls back to every field it declares. An address subfield counts as
  its address, since subfields carry no properties of their own. A
  field's own `properties={"AddToAllNewReports": ...}` still wins.
- **`title_field`** — `Optional[str]`, default `None`
  The field that names a record of this table, by label: what the record's
  page, its breadcrumb and its browser tab are titled with, in place of
  `Request #1`. Also the field a relationship to this table displays by
  default - see `RelationshipSpec.display_field`.

### `RelationshipSpec`

A parent table and a child table, by name.

Creating a relationship in the Quickbase UI does more than add the
reference field: the parent gets a report link named after the child, the
child gets an `Embedded for <Parent>` report, and the parent's form shows
that report, so a parent record lists its children. Without the other
two halves a parent record shows none of its children.

`embed_on_parent` builds them, as the UI does. It stands down wherever
the caller already has: a `ReportLink` on the parent that targets this
relationship's reference field is reused rather than duplicated, and a
parent form that already embeds a report through that link is left alone.

**Every relationship list is named `Embedded for <parent-table-name>`**, on
the child. That is the whole convention, and three things follow from it:

- *Where it goes.* Place the relationship's report link on the parent's
  form - its label as a plain member, or a `FormElementSpec(field=...)`
  naming no report - and the list is embedded right there. Place nothing
  and it gets a section of its own at the end of the form.
- *What it shows.* Declare a report named `Embedded for <Parent>` on the
  child to choose its columns and sort; it is used, and hidden from the
  role report lists like the one that would otherwise be built. Declare
  nothing and it shows the child's default columns, less the reference
  field and the lookups read through it.
- *Opting out of the name.* A form element that names a different report
  explicitly is the caller's choice and is left exactly as written.

- **`parent`** — `str`, default required
- **`child`** — `str`, default required
- **`reference_label`** — `Optional[str]`, default `None`
  The label of the reference field created on the child. Left unset it is
  `Related <parent's singular record name>` - "Related Donor", which is
  what the Quickbase UI names it - falling back to the parent's table name
  when the parent sets no `singular`. Name it only where the parent plays a
  role worth saying, and keep the prefix: "Related Caller", not "Caller".
  The design review flags a label without it (`DSN005`).
- **`embed_on_parent`** — `bool`, default `True`
  Whether the parent gets a report link, the child an `Embedded for
  <Parent>` report, and the parent's form a section showing it.
- **`embed_label`** — `Optional[str]`, default `None`
  The label of that report link and the title of the form section.
  Defaults to the child's plural name, which is what the UI uses.
- **`embed_columns`** — `Optional[List[str]]`, default `None`
  The child fields the embedded report shows. Defaults to the child's
  default columns, less this relationship's reference field and the
  lookups read through it - those only repeat the parent the list is
  already sitting on.
- **`display_field`** — `Optional[str]`, default `None`
  The parent field the reference field displays, by label, in place of the
  parent's record id. Left unset it is the parent's `title_field`, then
  its first text field.

  A reference field holds a record id, and without this it shows one: a
  request's Related Customer read `1`. The Quickbase UI builds a lookup of
  the parent's name on the child - `Customer - Customer Name` - and points
  the reference's `Proxy` at it with `DisplayAsLinkToParent`, so the field
  reads as the customer's name and links to the customer. The builder
  builds the same pair, reusing a lookup the child already declares.
- **`display_parent`** — `bool`, default `True`
  Set False to keep the bare record id.
- **`reference_properties`** — `Dict[str, Any]`, default `{}`
  Anything else the reference field's type permits, by its QBL property
  name: `{"IsRequired": True, "IsAuditable": True,
  "RolePermissions": {"$Role_Team_Member": "View"}}`.

  The reference field is built by the builder rather than declared as a
  `FieldSpec`, so this is where a field-level permission, an audit flag or
  a required flag goes - often on the fields that most need them, such as
  an employee's manager. Checked against the schema for
  `QB::Field::Reference`. `Label` and `Reference` are the builder's and
  are refused here; name the field with `reference_label`.

### `PageSpec`

A page in the application's `Pages` container.

`kind` is `RichTextPage` or `CodePage`. Both need an id of 2 or more - the
platform answers 1 with `the page ID is 1, which is less than the minimum
allowed value of 2`.

A code page is the last resort, not a page kind like the other one. It is
browser code the application owner maintains, outside anything a platform
upgrade looks after, and it should be reviewed and security-scanned before
it is deployed. So the spec asks for the reason alongside the code::

    PageSpec(
        "task-board.html", "CodePage",
        purpose="Drag tasks between status columns",
        native_gap="A kanban report moves one card per save and cannot "
                   "reorder within a column; the requirement is ordering.",
        requests_per_second=1,
        body=TASK_BOARD_HTML,
    )

and the builder writes the review header every code page carries - its
purpose, the gap it fills, how it is opened, how it authenticates, the
libraries and endpoints it uses, and a `DRAFT` review status - from those
attributes and from the code itself. Do not write a header in `body`.

Its `name` is the file name it is served under, and the extension is the
content type: a name with none is served as plain text and shows the raw
source. `.html` or `.htm` for a page, `.js` or `.css` for an asset another
page loads by `?a=dbpage&pageName=<name>`. No spaces, which every URL
naming the page would have to encode.

Address a table inside `body` by its alias token, `<!~db~[_DBID_TASKS]~db~>`,
and the application by `<!~db~[_APP_ID_]~db~>`. Writing every id in a code
page that way makes the page work in whichever app a create makes; a literal
dbid exists in one app only. The code page review
(`CPG*`) checks each token names a table the app declares.

- **`name`** — `str`, default required
- **`kind`** — `str`, default `'RichTextPage'`
- **`body`** — `str`, default `''`
- **`purpose`** — `Optional[str]`, default `None`
  For a code page: what it does, in one line. Written into its header.
- **`native_gap`** — `Optional[str]`, default `None`
  For an `.html` code page: the requirement nothing native meets, and why
  - which report, form rule, formula, pipeline or widget was considered.
  Required, because a code page built where a native feature would do is
  maintenance the application owner did not need to take on.
- **`auth`** — `str`, default `'TempToken'`
  How it reaches Quickbase data. `TempToken` - a temporary token for the
  user who opened it, fetched in the page, so it can do only what that
  user can; `Pipeline` - it posts to a pipeline's webhook, which holds any
  elevated access server-side; `None` - it calls no Quickbase API.
  Never a stored token: there is no option for one.
- **`requests_per_second`** — `Optional[float]`, default `None`
  Combined requests per second across everything it calls, at peak.
  Quickbase's threshold for a plain code page is 4; above that the answer
  is CDN hosting or browser caching, not this page.
- **`sensitive_data`** — `bool`, default `False`
  Whether it handles PII, health or financial data. Keeps those values
  out of URLs and flags the page for closer review.
- **`drafted_on`** — `Optional[str]`, default `None`
  The date it was drafted, as the header should state it (`YYYY-MM-DD`).
  Left unset, the header states no date, so that generating the same spec
  twice gives the same document.

### `DashboardWidgetSpec`

One widget on a dashboard tab.

Geometry is `X` and `Width`; `Y` and `Height` are accepted and not required,
because the platform answers a missing one with an `Unparsed` that names
nothing.

- **`kind`** — `str`, default `'RichText'`
- **`title`** — `Optional[str]`, default `None`
- **`table`** — `Optional[str]`, default `None`
  For a report or chart widget: the table it lives in and its name.
- **`report`** — `Optional[str]`, default `None`
- **`x`** — `int`, default `0`
- **`y`** — `int`, default `0`
- **`width`** — `int`, default `6`
- **`height`** — `Optional[int]`, default `None`
  Rows tall. Left unset, the widget gets the standard height for
  that kind - see `DEFAULT_DASHBOARD_WIDGET_HEIGHTS`. A flat default made
  every widget four rows tall, which is right for a rich text note and
  unusably short for a table.

### `DashboardFilterSpec`

A filter on a dashboard tab, driving one or more widgets.

`CompareField` and `Report` are not properties of the filter - they are
keys inside each entry of `Targets`.

- **`name`** — `str`, default required
- **`table`** — `str`, default required
  The table the compared field lives on.
- **`field`** — `str`, default required
  The field a value is matched against.
- **`targets`** — `List[str]`, default `[]`
  Reports or charts on that table which the filter drives.
- **`filter_type`** — `str`, default `'Text'`
- **`search_type`** — `str`, default `'ExactMatch'`

### `DashboardTabSpec`

One tab of a dashboard, with its own widgets and filters.

A tab is the only navigation a dashboard has: a role lands on one
dashboard, and a second dashboard is reachable only if something links to
it. A dashboard may carry two to ten tabs.

- **`name`** — `str`, default required
- **`widgets`** — `List[DashboardWidgetSpec]`, default `[]`
- **`filters`** — `List[DashboardFilterSpec]`, default `[]`

### `DashboardSpec`

- **`name`** — `str`, default required
- **`widgets`** — `List[DashboardWidgetSpec]`, default `[]`
- **`filters`** — `List[DashboardFilterSpec]`, default `[]`
- **`tab_name`** — `str`, default `'Main'`
- **`tabs`** — `List[DashboardTabSpec]`, default `[]`
  Several tabs, in order. Leave `widgets`, `filters` and `tab_name` at
  their defaults when setting this; the builder refuses both at once.
  Quickbase warns past five Table widgets on one tab, so a tab is also the
  way to give an audience more than five reports on one dashboard.

### `HomeWidgetLinkSpec`

A button on a `ButtonBar`, or a link on a `LinkBar`.

Both are the same shape under different type names, and both live in a
container on the bar rather than in the row's `Widgets` - a bar with no
children is a bar with nothing on it.

Name what it opens rather than writing a URL. A table alone is an
add-a-record button, a table and a report opens that report, and a page
opens that page; the builder writes the URL and the link type::

    HomeWidgetLinkSpec("New project", table="Projects")
    HomeWidgetLinkSpec("Overdue work", table="Tasks", report="Overdue")
    HomeWidgetLinkSpec("How we work", page="Team Notes")
    HomeWidgetLinkSpec("Help", url="https://help.quickbase.com")

The URL names a table by its alias - `/db/<!~db~[_DBID_PROJECTS]~db~>?a=nwr`
- which a create resolves to the new table's real id, so the button works
in whatever realm the app lands in. A hand-written `/db/<dbid>` cannot: the
id does not exist until the create has run.

- **`name`** — `str`, default required
- **`url`** — `str`, default `''`
  An address outside the app, or one written by hand.
- **`link_type`** — `str`, default `'Url'`
  `Url`, `Record`, `Report` or `Page`. Worked out from what the link names
  when it names a table or a page.
- **`redirect_url`** — `Optional[str]`, default `None`
  Where to go after the linked action finishes.
- **`table`** — `Optional[str]`, default `None`
  A table: on its own, open a new record of it.
- **`report`** — `Optional[str]`, default `None`
  A report on `table` to open instead.
- **`page`** — `Optional[str]`, default `None`
  A page in this spec to open - a rich text page, a code page, or the home
  page itself.
- **`return_home`** — `bool`, default `False`
  For an add-a-record link: `True` comes back to the home page once the
  record is saved, rather than showing it.

### `HomeWidgetFieldSpec`

One field a `Search` widget searches, in the widget's `Fields`.

- **`field`** — `str`, default required
  The label of the field to search.
- **`label`** — `Optional[str]`, default `None`
- **`placeholder`** — `Optional[str]`, default `None`

### `HomeWidgetSpec`

A widget on the application's home page.

`section` picks which of the page's two row containers it goes in. A home
page has `MainSection` and `Sidebar`, holding the same shape under different
row type names, and only the first was reachable.

- **`kind`** — `str`, default `'RichText'`
- **`title`** — `Optional[str]`, default `None`
- **`table`** — `Optional[str]`, default `None`
- **`report`** — `Optional[str]`, default `None`
- **`section`** — `str`, default `'MainSection'`
  `MainSection` or `Sidebar`.
- **`row`** — `Optional[str]`, default `None`
  Widgets naming the same `row` sit side by side, in the order declared;
  a widget naming none has a row to itself. A main section row holds up to
  three and a sidebar row one - the platform's limits, enforced here.
- **`width`** — `Optional[str]`, default `None`
  The widget's share of its row. Left unset the row is divided evenly.
  Quickbase accepts exactly `100%` alone; `50%` and `50%`, or `66.6666%`
  and `33.3333%` in either order, for two; and `33.3333%` each for three.
  Set one of a pair and the other is worked out.
- **`height`** — `Optional[int]`, default `None`
  Height in pixels. A report needs at least 150, a reports list 300 and a
  web page 20; the platform refuses less.
- **`max_rows`** — `Optional[int]`, default `None`
  For a `Report` widget: how many rows it shows before scrolling - 0 for
  all of them, or 5 to 250.
- **`tables`** — `List[str]`, default `[]`
  For a `ReportsList`: the tables whose reports it lists, up to eight.
  Leave empty to list every table's.
- **`links`** — `List[HomeWidgetLinkSpec]`, default `[]`
  For a `ButtonBar` or a `LinkBar`: what it holds.
- **`fields`** — `List[HomeWidgetFieldSpec]`, default `[]`
  For a `Search` widget: the fields it searches.
- **`properties`** — `Dict[str, Any]`, default `{}`
  Anything else the widget's kind permits, by its QBL property name -
  a `RichText`'s `Content`, a `WebPage`'s `Url`, a `Search`'s
  `SearchTarget`.

### `GuideSpec`

An application guide - the custom help entry an app can define.

`links_to` names a page by its `PageSpec` name. It has to be a content page:
pointed at a `QB::RichTextPage` or a `QB::CodePage` the platform is clean,
and pointed at the home page it answers `BadProperty: LinksTo`. A guide
links to content, not to a dashboard.

- **`title`** — `str`, default required
- **`links_to`** — `str`, default required
  The name of the page the guide opens.
- **`description`** — `Optional[str]`, default `None`

### `EmailConditionSpec`

One condition on a custom email: a field of the email's table, compared.

`comparison` is the platform's word - `IsEqualTo`, `IsNotEqualTo`,
`IsGreaterThan`, `IsLessThan`, `Contains`, `IsBlank`, `IsNotBlank`.

- **`field`** — `str`, default required
- **`comparison`** — `str`, default `'IsEqualTo'`
- **`value`** — `Any`, default `None`

### `CustomEmailSpec`

A custom email on a table.

Without recipients an email is a subject and a body that nobody receives,
and every generated one was exactly that: the recipients had to be written
onto the compiled document by hand. `to_fields` names the table's own
`User`, `User::Formula` or `ListUser` fields, which is how a scheduled email
reaches a different person per record - and a `User::Formula` that is blank
unless the record needs the email is how it reaches *only* the records that
do, because the platform drops a scheduled email's `conditions` (see
`conditions`).

`content` may name fields as `<qb-field field-id="[[fid:Due Date]]">`;
the token is resolved to the field's id on this table.

- **`name`** — `str`, default required
- **`subject`** — `str`, default required
- **`content`** — `str`, default required
- **`trigger`** — `str`, default `'Scheduled'`
  `Scheduled` needs a cron `schedule`; `RecordChange` needs `record_events`.
- **`schedule`** — `str`, default `'0 9 * * *'`
- **`record_events`** — `List[str]`, default `[]`
  For a `RecordChange` email, required: which record events send it, from
  `Add`, `Modify` and `Delete`. There is no default - the platform accepts a
  record-change email with none, stores an email that never sends, and
  exports it with no `SendOptions` at all, so the export cannot be
  re-imported. Refused on a scheduled email.
- **`trigger_fields`** — `List[str]`, default `[]`
  For a `RecordChange` email: send only when one of these fields changes,
  by label on this table. Empty means any change. Refused on a scheduled
  email.
- **`to_fields`** — `List[str]`, default `[]`
  Recipient fields on this table, by label.
- **`check_recipient_permissions`** — `bool`, default `True`
  Send only to recipients allowed to see the record.
- **`send_when_empty`** — `bool`, default `False`
  For a scheduled email: send even when no record qualifies.
- **`conditions`** — `List[EmailConditionSpec]`, default `[]`
  Which records send, all of `conditions` (`All`) or any (`Any`).

  Honoured on a `RecordChange` email. **Dropped by the platform on a
  `Scheduled` one** - sent, accepted, and absent from the export - so the
  builder refuses them there rather than write a guard that does not
  exist; gate a scheduled email through its recipient formula instead.
- **`true_when`** — `str`, default `'All'`
- **`description`** — `Optional[str]`, default `None`

### `DocumentTemplateSpec`

- **`name`** — `str`, default required

### `VariableSpec`

An application variable, referenced from formulas and pages.

- **`name`** — `str`, default required
- **`value`** — `str`, default required

### `PipelineFilterSpec`

One condition a pipeline trigger or search step filters on, AND-ed.

`field` is a label on the step's table. `operator` is the pipeline's own
word - see `PIPELINE_FILTER_OPERATORS` - and `value` may be Jinja reading an
earlier step: `"{{ a.id }}"`. Every filtered field is exported by the step
automatically: a search filtering on a field it does not export creates
cleanly and then makes the whole solution unexportable.

- **`field`** — `str`, default required
- **`operator`** — `str`, default `'equals'`
- **`value`** — `Any`, default `None`

### `PipelineStepSpec`

A step in a pipeline's `steps`: a search, a create, an update or a loop.

The trigger, when there is one, is step `a`; steps are lettered after it in
order (nested ones included) unless given an `id`. Jinja reads a step by its
id - `{{ b.due_date }}` - and every field read that way is checked against
the step's table and exported by that step::

    PipelineSpec("Monthly report seed", owner=OWNER, schedule="30 0 1 * *",
                 timezone="America/Chicago", steps=[
        PipelineStepSpec("search", "Projects", name="Find active projects",
                         filters=[PipelineFilterSpec("Active", "is", True)]),
        PipelineStepSpec("loop", target="a", steps=[
            PipelineStepSpec("create", "Status Reports", values={
                "Related Project": "{{ a.id }}",
                "Period Start": "{{ a.current_month_start }}"}),
        ]),
    ])

- `search` - `table` and `filters`; `export` names fields later steps read
  that Jinja alone does not reveal.
- `create` - `table` and `values`.
- `update` - `values`, written to the record of the step `target` names: the
  trigger (`a`), a create, or - inside a loop over it - a search. Its table
  is the target's.
- `loop` - `target` names the search it iterates; `steps` run per record.

A value of `""` is refused: the platform skips a blank value rather than
clearing the field. Write `{{CLEAR}}` to clear one.

- **`kind`** — `str`, default required
- **`table`** — `Optional[str]`, default `None`
- **`name`** — `Optional[str]`, default `None`
- **`id`** — `Optional[str]`, default `None`
- **`filters`** — `List[PipelineFilterSpec]`, default `[]`
- **`values`** — `Dict[str, str]`, default `{}`
- **`target`** — `Optional[str]`, default `None`
- **`steps`** — `List['PipelineStepSpec']`, default `[]`
- **`export`** — `List[str]`, default `[]`

### `PipelineActionSpec`

One Quickbase step after a pipeline's trigger.

`values` maps a field label in `table` to what to write there. A value is
text, and may read the record that fired the trigger with Jinja: the
trigger is step `a`, a field is the snake case of its label, and Record ID
is `id`::

    PipelineActionSpec("Activity Log", values={
        "Event": "Request created: {{ a.subject }}",
        "Related Request": "{{ a.id }}",
    })

Both sides are checked when the pipeline compiles. The platform checks
neither: a step writing a field that does not exist, or reading
`{{ a.subjcet }}`, creates cleanly and writes blanks for ever.

- **`table`** — `str`, default required
- **`kind`** — `str`, default `'create'`
  `create` a record in `table`, or `update` the record that fired the
  trigger - in which case `table` must be the trigger table.
- **`values`** — `Dict[str, str]`, default `{}`
- **`name`** — `Optional[str]`, default `None`
  The step's name in the pipeline designer. Defaults from the kind and
  table.

### `PipelineSpec`

A Quickbase pipeline: one record trigger, then actions.

A pipeline sits beside the application rather than inside it, and every
Quickbase step names the channel account it runs as. The builder declares
that account as the realm's default Quickbase connection
(`AccountType: tokenless`, `Alias: realm-default-account`), which a create
binds to a real account in whatever realm it runs in - so a generated
pipeline runs without anyone reconnecting it. Any other account shape is
swapped for a placeholder with only a warning, and the pipeline does
nothing until a builder opens it and connects an account by hand.

A pipeline with no `trigger_table` is a shell: a name and an owner, no
steps.

**A created pipeline is switched off.** QBL has no property for it, so
someone has to turn each one on in Pipelines after the create; a later PUT
leaves it on. The three shapes this spec builds each run on real records
once switched on (create risk `CRT013`).

- **`name`** — `str`, default required
- **`owner`** — `str`, default required
- **`trigger_table`** — `Optional[str]`, default `None`
  The table whose records fire the pipeline.
- **`trigger_event`** — `str`, default `'update'`
  `create`, `update` or `delete`.
- **`trigger_fields`** — `List[str]`, default `[]`
  For an `update` trigger: fire only when one of these fields changes, by
  label. Left empty, a change to any field fires it.
- **`actions`** — `List[PipelineActionSpec]`, default `[]`
- **`description`** — `Optional[str]`, default `None`
  Shown in the pipelines list. Left unset the platform writes "Your new
  pipeline" on every one, which tells a builder nothing.
- **`account_id`** — `Union[int, str]`, default `1`
  Emitted as a number. The platform replaces it with the realm's own
  default account on create, so it only has to be a positive number - a
  string of digits is coerced; anything else is a compile error.
- **`trigger_filters`** — `List[PipelineFilterSpec]`, default `[]`
  For a record trigger: fire only for records matching all of these.
- **`trigger_name`** — `Optional[str]`, default `None`
  The trigger step's name in the designer, with `steps`. Defaults to
  "<table> record <event>".
- **`schedule`** — `Optional[str]`, default `None`
  A cron schedule in place of a record trigger: `"0 22 * * 1"` is Mondays
  at 22:00. Leave `trigger_table` unset, and give `steps`.
- **`timezone`** — `Optional[str]`, default `None`
  The schedule's time zone, as an IANA name. Required with a schedule:
  the requirements rarely say, and a default would decide it for them.
- **`steps`** — `List[PipelineStepSpec]`, default `[]`
  The steps after the trigger, or the whole pipeline for a scheduled one.
  The richer form of `actions`, which it replaces; set one or the other.

### `ConnectedColumnSpec`

A column of a connected table. Every named kind requires a `Name`.

- **`name`** — `str`, default required
- **`kind`** — `str`, default `'Text'`
- **`source_field_id`** — `Optional[int]`, default `None`
  For a Quickbase source, the id of the field this column reads in the
  source table - which is what Quickbase writes as the column's `Id`
  (`Name` is 9, `Record ID#` is 3). Left unset the builder numbers the
  columns itself, which creates but names no real source field.

### `ConnectedTableSpec`

A table synced from a Quickbase-hosted source.

Lives under `ExternalResources`, a top-level key beside `Resources`.

**Every connected table a solution creates arrives as a placeholder.**
A generated table, one with a real connection and source table, and one
recreated verbatim from an export all come back `IsPlaceholder: true` with
`QB::ConnectedColumn::Placeholder` columns. Someone finishes the connection
in the UI (create risk `CRT015`).

- **`name`** — `str`, default required
- **`columns`** — `List[ConnectedColumnSpec]`, default `[]`
- **`connection_id`** — `Union[int, str]`, default `1`
  The realm's connection to the source - a number the Quickbase UI shows
  under Connections. The default is a placeholder: it creates, and comes
  back with `ConnectionId: 0` and `Owner: <Unknown>`.
- **`external_set_id`** — `str`, default `'external'`
  For a Quickbase source, the source table's dbid (`bs7q3tj68`).
- **`owner`** — `Optional[str]`, default `None`
  The email of the user who owns the connection.
- **`schedule`** — `str`, default `'Manual'`
  How the table refreshes: `Manual`, or a cron string such as
  `21 * * * *`. Required in effect - a binding with no `Schedule` fails
  the create with "failure in creating one of the resources" though
  Quickbase's own schema calls it defaultable - and a cron at minute 0 is
  silently replaced with `Manual`. Most bindings carry a cron.
- **`notify_on_failure`** — `bool`, default `True`
  Whether a failed refresh notifies the owner, for a cron schedule.
- **`key_column`** — `Optional[str]`, default `None`
  The column a refresh matches records on, by name; the first column
  when unset. Its field is made unique, as the platform requires.

### `RoleSpec`

A role in the application's `Roles` container.

What a role may do in a *table* is not here - QBL records that on the
table, so see `TableSpec.role_permissions`. What is here is the role itself
and what it may do to the application.

- **`name`** — `str`, default required
- **`can_edit_app`** — `bool`, default `False`
- **`description`** — `Optional[str]`, default `None`
- **`is_default`** — `bool`, default `False`
  Whether a new user without an explicit role lands in this one.
- **`manage_users`** — `bool`, default `False`
  Whether the role may invite and remove users.
- **`disable_access`** — `bool`, default `False`
  Whether the role is denied access to the application outright.
- **`properties`** — `Dict[str, Any]`, default `{}`
  Anything else `QB::Application::Role` permits, by its QBL property name.
  In practice that is the two chrome containers, which are the whole of a
  role's user interface configuration and were unreachable:

  {"AppUI": {"HideHelp": True, "HideSearch": True},
  "TableUI": {"Global": {"HideImportExport": True},
  "$Table_Orders": {"HideNewRecord": True}}}

  `TableUI` keys are a logical table ID or `Global`; the builder does not
  rewrite them, so a caller naming a table must use the ID QBL will carry.

### `AppSpec`

- **`name`** — `str`, default required
- **`tables`** — `List[TableSpec]`, default `[]`
- **`relationships`** — `List[RelationshipSpec]`, default `[]`
- **`roles`** — `List[RoleSpec]`, default `[]`
- **`default_roles`** — `bool`, default `True`
  Keep the three roles Quickbase gives every new application - Viewer,
  Participant and Administrator - beside whatever `roles` adds. A role in
  `roles` with one of those names is used as given rather than duplicated;
  a table that grants one of them nothing explicitly gets its standard
  access (`compiler.DEFAULT_ROLE_ACCESS`), so Administrator always has
  full access. Turn off only when the requirements ask for the defaults to
  be removed.
- **`description`** — `Optional[str]`, default `None`
- **`home_page_name`** — `str`, default `'Home'`
- **`pages`** — `List[PageSpec]`, default `[]`
- **`dashboards`** — `List[DashboardSpec]`, default `[]`
- **`home_widgets`** — `List[HomeWidgetSpec]`, default `[]`
- **`guides`** — `List[GuideSpec]`, default `[]`
- **`variables`** — `List[VariableSpec]`, default `[]`
- **`pipelines`** — `List[PipelineSpec]`, default `[]`
- **`connected_tables`** — `List[ConnectedTableSpec]`, default `[]`
- **`role_home_pages`** — `Dict[str, str]`, default `{}`
  Which page each role opens on, by role name. A value is the name of a
  page in `pages`, or `UseDefault` to fall back to `Everyone`. QBL writes
  these under the application's `Pages.Properties.RoleDefaults`, one
  `Desktop` and one `Mobile` per role.
- **`requirements`** — `List['RequirementSpec']`, default `[]`
  What the application was asked to do: user stories, business rules, BRD
  items, each with its acceptance criteria and what in the document meets
  them. See `generation/requirements.py`. Left empty, the build says so
  (`REQ000`) - every other gate passes a document that does half of what
  was asked.
- **`decisions`** — `List['DecisionSpec']`, default `[]`
  The choices that shaped the application and who made each - the
  requirements' defaults, the user's answers, and anything the builder
  chose, which blocks the build until someone confirms it (`DEC001`).
- **`properties`** — `Dict[str, Any]`, default `{}`
  Anything else `QB::Application` permits, by its QBL property name.

  An application node has a name and a description and about forty-three
  other properties: all of its branding (`Branding.AppHeader`, `Branding.AppFooter`), every locale and
  format setting (`DateFormat`, `Timezone`, `CurrencySymbol`,
  `NumberFormat`, `FirstDayOfWeek`, the fiscal year), the security and
  governance flags (`RequireAppToken`, `CanExportData`, `CanCopyApp`,
  `CrossApplicationAccess`), `AppColor`, `AppIcon`, and `TableOrder` and
  `RoleOrder`.

  Checked against the schema for `QB::Application`, which lists the nested
  container names as well as their leaves, so `Branding` is permitted here
  and a misspelling of it is not.

## Closed value sets

These are shapes Quickbase refuses. A value outside them is a compile error or - worse for the chart kinds - a create that hangs with no diagnostic.

### Chart kinds that create (24)

`Area`, `Area3D`, `AreaSpline`, `Bar`, `Bar3D`, `Bubble`, `Funnel`, `Gauge`, `Heatmap`, `HorizontalBar`, `HorizontalStackedBar`, `Line`, `LineBar`, `Pie`, `ProgressBar`, `RadialBar`, `Scatter`, `Scatter3D`, `Spline`, `StackedBar`, `StackedBar3D`, `Streamgraph`, `VariwideBar`, `Waterfall`

### Chart kinds that do not create (4)

A document using one validates, but the create times out with no message.

`Donut`, `Donut3D`, `Funnel3D`, `Pie3D`

### Table icons (95), default `Table Header`

An unknown icon name is **silently swapped for `Table Header`** on create - no error, no warning, and the table renders with no icon at all. Found only by exporting the created app.

`Activity`, `Aid`, `Animation`, `Attendance List`, `Balloons`, `Bank Transaction`, `Bell`, `Book`, `Bookmark`, `Bug`, `Calculator`, `Calendar`, `Calendar Year`, `Car Front`, `Cellphone`, `Chart`, `Clipboard`, `Clipboard Pencil`, `Clock`, `College`, `Command`, `Competitors`, `Copy`, `Copy 2`, `Cube`, `Curriculum`, `Customer`, `Customers`, `Directive Board`, `Document`, `Dollar Sign`, `Economics`, `Edit`, `Engineering`, `Envelope`, `Field Image`, `File`, `Film`, `Flag`, `Folder`, `Frames`, `Geography`, `Group`, `Hammer`, `Handshake`, `Hourglass`, `ID`, `Inventory`, `Lightbulb`, `List`, `Mailbox`, `Male`, `Marker`, `Nurse`, `Offer`, `One`, `Pages`, `Paper Clip`, `Paste`, `Phone`, `Plus`, `Protocol`, `Purchase`, `Report`, `Report 2`, `Risk`, `Router`, `Salesman`, `Sandals`, `Satellite Dish`, `Schedule`, `Schedule 2`, `Screwdriver`, `Shopping Cart`, `Signs`, `Smudge`, `Sole Proprietorship`, `Star`, `Student`, `Table Header`, `Task`, `Task Complete`, `Tasks`, `Taxi`, `Team`, `Team Members`, `Thumbs Up`, `Timer`, `Two`, `Up Arrow`, `Upload`, `Upload 2`, `User`, `White List`, `Wrench`
