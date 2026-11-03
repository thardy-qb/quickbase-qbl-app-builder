from __future__ import annotations

from typing import Dict


REMEDIATION: Dict[str, str] = {
    "SCH000": (
        "Add a `Type` to the node. `Type` is a sibling of `Id` and "
        "`Properties`, not a key inside `Properties`."
    ),
    "SCH001": (
        "Correct the type name; when the message names a replacement, use it. "
        "This cannot be worked around by filling in properties correctly - the "
        "platform answers an unrecognised type with `NodeRemoved`, which is a "
        "warning, so the document deploys successfully and the app comes out "
        "missing the object."
    ),
    "SCH002": (
        "Make `Properties` a mapping. Where a type requires no properties, an "
        "empty `Properties: {}` is valid and is not the same as omitting it."
    ),
    "SCH003": "Add the named property under this node's `Properties`.",
    "SCH004": (
        "Remove the property, or correct its spelling against the property "
        "names for this type."
    ),
    "SCH005": (
        "Add the named property at the nested path the finding gives. Note "
        "that nested requirements here are a lower bound: some missing nested "
        "properties come back "
        "only as `Unparsed`, naming nothing, so a document can pass this check "
        "and still be rejected."
    ),
    "SCH006": (
        "Change the container kind at the nested path - a mapping where a list "
        "is required, or the reverse."
    ),
    "SCH007": (
        "Add or correct the node-level `Id`. It is a sibling of `Type` and "
        "`Properties`, not a key inside `Properties`, and the allowed range is "
        "per type: a page needs 2, a `QB::FormV2` needs 10 or more, and a "
        "legacy `QB::Form` needs exactly 2 or 10-and-up."
    ),
    "SCH008": (
        "Nothing to fix. This qualifies the other findings rather than "
        "describing a defect: property requirements describe a different QBL "
        "version than this document declares, so requiredness "
        "findings may not apply. Treat them as advisory for this version."
    ),
    "SCH009": (
        "Repoint or remove the reference. It was already unresolvable when the "
        "solution was exported, so this is pre-existing debt in the source app "
        "rather than something introduced here."
    ),
    "SCH010": (
        "Raise the document's `Version` to the one the finding names, or remove "
        "the node. Filling in its properties changes nothing: below that version "
        "the platform does not know the type, answers `NodeRemoved` - a warning "
        "- and deploys without it. For example, a v0.15 pipeline channel in a "
        "v0.14 document."
    ),
    "SCH011": (
        "Raise the document's `Version` to the one the finding names, or remove "
        "the property. Below that version the platform answers `ExtraProperty`, "
        "a warning, and the setting is silently not applied."
    ),
    "SCH999": (
        "Read the message, which is authoritative. The finding could not be "
        "matched to a known code."
    ),

    "REF000": (
        "Repoint or remove the reference. A `!BadRef` is Quickbase's own "
        "marker that the reference could not be resolved when the solution was "
        "exported; it is pre-existing debt and will not block a deployment."
    ),
    "REF001": (
        "Declare the target, or repoint the reference at something that "
        "exists. A logical ID is unique within its table, not across the "
        "solution, so a bare `Field: $Field_Status` means 'in this table' - "
        "if the target is elsewhere, name its `Table` (and `App`) too."
    ),
    "REF002": (
        "Point the key at a resource of the kind it names. This is the "
        "platform's `BadPropertyWrongReferenceType` family, which it "
        "*downgrades to a warning* - the property is not processed further, so "
        "the reference is dropped and the app deploys wrong rather than not "
        "at all."
    ),
    "REF003": (
        "Add the parameter to `ParameterDefinitions`, or reference a name that "
        "is already declared there."
    ),
    "REF004": (
        "Rename one of the two declarations. Take care which: a logical ID is "
        "stable identity, and changing the ID of an object that already "
        "exists in the solution turns an update into a delete and recreate."
    ),
    "REF005": (
        "Add the declared table or role to the ordering property, or remove "
        "the ordering property entirely - it is optional, and the platform "
        "accepts an app that declares tables and omits `TableOrder`. An "
        "ordering that is present and incomplete is what it rejects."
    ),

    "VAL001": (
        "Wrap the logical ID in a reference. `KeyField: $Field_Record_ID` "
        "becomes `KeyField: !Ref` with `Field: $Field_Record_ID` beneath it."
    ),
    "VAL002": "Use one of the documented values the message lists.",
    "VAL003": (
        "Unquote the version: `Version: 0.14`, not `Version: '0.14'`. A quoted "
        "version is a string where a number is expected, and the platform "
        "rejects the whole document with `Unparsed: The provided YAML has "
        "syntax errors`, naming no line and no property."
    ),
    "VAL009": (
        "Change the document `Version` to one the platform accepts - 0.7, "
        "0.12, 0.14 or 0.15. The platform refuses the whole document for any "
        "other version and names nothing else in the response. This Skill can "
        "read more versions than the platform accepts, so an export declaring "
        "an older version parses, but cannot be submitted unchanged. Where "
        "this is a warning rather than an error, the version is not on the "
        "accepted list: check before relying on it."
    ),
    "VAL004": (
        "Change the container kind at the nested path. The platform requires "
        "this container kind at this path."
    ),
    "VAL005": (
        "Check the spelling against the documented property names - this is "
        "most often a typo, and nothing else in this Skill checks nested "
        "property names at all. It stays a warning because the documented list "
        "may be incomplete, and the platform answers an unknown property with "
        "`ExtraProperty`, which does not block a deployment."
    ),
    "VAL006": (
        "If you are writing this document, leave the element out: it "
        "cannot be created or updated through QBL. If you are checking an "
        "export, nothing is wrong - the platform writes these on export and "
        "ignores them on import."
    ),
    "VAL007": (
        "Use one of the values the message lists. It stays a warning because "
        "the list holds the known accepted values, not necessarily everything "
        "the platform allows, so another value is not necessarily wrong."
    ),
    "VAL008": "Change the value to satisfy the rule the message quotes.",
    "VAL010": (
        "Use one of the values the message lists. Unlike VAL007 this is a "
        "complete list rather than a list of known values: the property only "
        "accepts these values, so a value outside it is one the platform has "
        "no node for. If the value looks right, confirm it "
        "against a fresh export before assuming the document is wrong."
    ),

    "STR001": (
        "Add a `QB::HomePage` under the application's `Pages`. A dashboard in "
        "the same container does not satisfy this."
    ),
    "STR002": (
        "Add `Properties: {}` to the `Pages` container. The platform's own "
        "message for this names the wrong node - `Unparsed: No Type defined "
        "for node with logicalId Resources`."
    ),
    "STR003": (
        "Add a form to the table. Either a `QB::FormV2` or a legacy "
        "`QB::Form` satisfies the requirement."
    ),
    "STR004": (
        "Put the report or chart in a `QB::ReportGroup`. Mind the three "
        "containers, which are easy to confuse: reports live under `Reports`, "
        "charts under `Charts`, and the groups themselves under `ReportGroups`."
    ),
    "STR005": (
        "Declare the missing built-in field. All five - Record ID#, Date "
        "Created, Date Modified, Record Owner, Last Modified By - must be "
        "declared on every table, always. Quickbase creates them itself and "
        "still requires QBL to declare each one."
    ),
    "STR010": (
        "Give the rule at least one entry under `When`. The platform's message "
        "names the rule by type rather than by logical ID, so a form with "
        "several rules does not say which."
    ),
    "STR011": (
        "Give the rule at least one entry under `Actions`. A rule with a "
        "trigger and no action is well-formed and does nothing, and the "
        "platform rejects it with `BadMinItems` rather than letting it through."
    ),
    "STR012": (
        "Give the row child elements under `Elements`, or remove the row. The "
        "platform answers an empty one with `BadChild: Form Rows must have "
        "defined Elements`."
    ),
    "STR013": (
        "Reduce the columns' `LayoutWidth` values until they total 12 or less "
        "- two columns of 6, three of 4. A total *below* 12 is accepted, so "
        "there is no need to make them add up exactly; only going over is "
        "refused, with `BadMaxItems`."
    ),
    "STR015": (
        "Set `ModesToShowIn` on the section or element - `[View, Edit, "
        "Create]` for one that always shows. Nothing else reports this: the "
        "platform accepts the document, and the form then opens blank in "
        "every mode. A `QB::FormV2::Element::Group` is the one exception and "
        "states no visibility of its own."
    ),
    "STR014": (
        "Move the surplus columns into a second section. A section holds at "
        "most six columns whatever their widths; a seventh is refused with "
        "`TooManyChildren`."
    ),
    "STR017": (
        "Move the other actions to a second rule on a different trigger. As "
        "the record saves, a legacy rule may only change a field's value or "
        "abort the save."
    ),
    "STR018": (
        "Split the row, or set the widths to a combination the platform takes, "
        "written exactly: one widget at `100%`; two at `50%` and `50%`, or "
        "`66.6666%` and `33.3333%` either way round; three at `33.3333%` each. "
        "A main section row holds three widgets and a sidebar row one."
    ),
    "STR019": (
        "Write Height in whole pixels, like `400px`, and at least the kind's "
        "minimum - 150px for a report, 300px for a reports list, 20px for a web "
        "page. MaximumVisibleRows is 0 for all rows or 5 to 250; a reports list "
        "names at most eight tables."
    ),
    "STR016": (
        "Move the surplus formulas onto a second report. Three report formulas "
        "and three summary formulas are each the per-report limit, on a summary "
        "report and an ordinary table report alike."
    ),
    "STR007": (
        "Give the fields distinct `Id` values. The `Id` is a sibling of `Type` "
        "and `Properties`, and it is the field's identity inside the table - "
        "the platform rejects a collision with `DuplicateId`, naming both "
        "fields. When assigning ids, this is the collision to guard "
        "against, and reusing the id of a field that already exists in the "
        "solution rewrites that field rather than adding one."
    ),
    "STR008": (
        "Rename one of the fields. Labels must be unique within a table and the "
        "platform rejects a collision with `DuplicatePropertyValue`. The scope "
        "is the table, so the same label on a field in a different table is "
        "fine and needs no change."
    ),
    "STR009": (
        "Rename one of the roles. Role names must be unique within an "
        "application and the platform rejects a collision with "
        "`DuplicatePropertyValue`."
    ),
    "STR006": (
        "Give the rule a record-state trigger in its `When` whose "
        "`RecordState` is a saving state. The action is valid and the trigger "
        "is valid; what the platform rejects is the pairing."
    ),

    "FML001": (
        "Correct the field label in the formula, or declare the field it "
        "names. Nothing else will catch this: a formula addresses fields by "
        "label rather than by logical ID, and the platform does not read "
        "formula bodies at all, so the app deploys and the formula fails in "
        "use."
    ),
    "FML002": (
        "Correct the table alias in the formula, or declare the table it "
        "names."
    ),
}


def remediation_for(code: str) -> str:
    return REMEDIATION.get(code, "")
