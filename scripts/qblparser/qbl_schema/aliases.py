from __future__ import annotations

from typing import Dict


TYPE_ALIASES: Dict[str, str] = {
    "QB::ConnectedColumn::Varchar": "QB::ConnectedColumn::VarChar",
    "QB::ConnectedColumn::XML": "QB::ConnectedColumn::Xml",

    "QB::Field::MultiSelectText": "QB::Field::MultiselectText",
    "QB::Field::MultiSelectText::Formula": "QB::Field::MultiselectText::Formula",
    "QB::Report::Formula::MultiselectText": "QB::Report::Formula::MultiSelectText",
    "QB::Report::SummaryFormula::MultiselectText":
        "QB::Report::SummaryFormula::MultiSelectText",

    "QB::Field::RecordId": "QB::Field::RecordID",

    "QB::Field::TextMultiLine": "QB::Field::TextMultiline",

    "QB::FormV2::Rule::Action::MakeReadOnly": "QB::FormV2::Rule::Action::MakeReadonly",
}


def canonical_type(qbl_type: str) -> str:
    return TYPE_ALIASES.get(qbl_type, qbl_type)
