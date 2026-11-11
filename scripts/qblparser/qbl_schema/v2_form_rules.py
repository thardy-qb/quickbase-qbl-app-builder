FORM_RULE_SCHEMA = {
    "QB::FormV2::Rule": {
        "required": [],
        "optional": ["RunOn", "Name", "Description", "Tags", "Disabled", "FireOnlyOnChange", "TrueWhen"]
    },
    "QB::FormV2::Rule::Action::AbortSave": {
        "required": [],
        "optional": ["Message"]
    },
    "QB::FormV2::Rule::Action::Change": {
        "required": [],
        "optional": ["Field", "Value"]
    },
    "QB::FormV2::Rule::Action::DisplayMessage": {
        "required": [],
        "optional": ["MessageType", "Message", "MessageLevel", "FieldTarget"]
    },
    "QB::FormV2::Rule::Action::Hide": {
        "required": [],
        "optional": ["Target"]
    },
    "QB::FormV2::Rule::Action::MakeEditable": {
        "required": [],
        "optional": ["Target"]
    },
    "QB::FormV2::Rule::Action::MakeReadOnly": {
        "required": [],
        "optional": ["Target"]
    },
    "QB::FormV2::Rule::Action::Require": {
        "required": [],
        "optional": ["Target"]
    },
    "QB::FormV2::Rule::Action::SetColor": {
        "required": [],
        "optional": ["Color", "Target"]
    },
    "QB::FormV2::Rule::Action::SetLabel": {
        "required": [],
        "optional": ["Label", "Target"]
    },
    "QB::FormV2::Rule::Action::Show": {
        "required": [],
        "optional": ["Target"]
    },
    "QB::FormV2::Rule::Action::Unrequire": {
        "required": [],
        "optional": ["Target"]
    },
    "QB::FormV2::Rule::Condition::DaysAgo": {
        "required": [],
        "optional": ["Field", "Comparison", "DaysAgo"]
    },
    "QB::FormV2::Rule::Condition::Field": {
        "required": [],
        "optional": ["Field", "Comparison", "Value"]
    },
    "QB::FormV2::Rule::Condition::FormulaIsTrue": {
        "required": [],
        "optional": ["Formula"]
    },
    "QB::FormV2::Rule::Condition::Group": {
        "required": [],
        "optional": ["TrueWhen"]
    },
    "QB::FormV2::Rule::Condition::Range": {
        "required": [],
        "optional": ["Field", "Comparison", "RelativeTo", "TimeFrame", "Range"]
    },
    "QB::FormV2::Rule::Condition::Relative": {
        "required": [],
        "optional": ["Field", "Comparison", "RelativeTo"]
    },
    "QB::FormV2::Rule::Condition::Role": {
        "required": [],
        "optional": ["Comparison", "Role"]
    }
}
