from __future__ import annotations

from typing import Dict


PLATFORM_REJECTS: Dict[str, str] = {
    "QB::PipelineAccount":
        "NodeRemoved: Unsupported node type QB::PipelineAccount. The real type "
        "is QB::PipelineChannelAccount.",
    "QB::Field::Formula":
        "NodeRemoved: Unsupported node type QB::Field::Formula - a warning, so "
        "the field is dropped and the app deploys without it. A formula field "
        "names the type it produces, e.g. QB::Field::Text::Formula.",
    "QB::Field::ReferenceProxy":
        "Rejected as Unsupported node type in a table's Fields. The concept "
        "exists one level up, as the form element "
        "QB::Form::Element::ReferenceProxyField.",
}

_RULE_BASES_NOTE = (
    "Not a usable node type; the platform answers NodeRemoved.")
PLATFORM_REJECTS.update({
    "QB::FormRule::Action": _RULE_BASES_NOTE + " An abstract base.",
    "QB::FormRule::Condition": _RULE_BASES_NOTE + " An abstract base.",
    "QB::FormRule::Trigger": _RULE_BASES_NOTE + " An abstract base.",
    "QB::FormRule::RuleCondition": _RULE_BASES_NOTE + " A v0.1 base.",
    "QB::FormRule::Action::SaveAbort":
        _RULE_BASES_NOTE + " A v0.1 spelling; the action is AbortSave.",
    "QB::FormRule::RuleCondition::FieldRule":
        _RULE_BASES_NOTE + " A v0.1 shape; the condition is Condition::Field.",
    "QB::FormRule::RuleCondition::UserRule":
        _RULE_BASES_NOTE + " A v0.1 shape; the condition is Condition::User.",
    "QB::FormV2::Rule::Action":
        "An abstract base the platform drops from the rule without error; "
        "name the action, e.g. QB::FormV2::Rule::Action::Hide.",
    "QB::FormV2::Rule::Condition":
        "An abstract base the platform drops from the rule without error; "
        "name the condition, e.g. QB::FormV2::Rule::Condition::Field.",
})


_HOME_BASES_NOTE = (
    "Not a usable node type; the platform answers NodeRemoved.")
PLATFORM_REJECTS.update({
    "QB::HomePage::Widget":
        _HOME_BASES_NOTE + " An abstract base; name the kind, e.g. "
        "QB::HomePage::Widget::RichText.",
    "QB::HomePage::Widget::Bar":
        _HOME_BASES_NOTE + " The base of ButtonBar and LinkBar.",
    "QB::HomePage::Row":
        _HOME_BASES_NOTE + " The base of MainSectionRow and SidebarRow.",
})


NODE_ID_NOT_ENFORCED: Dict[str, str] = {
    "QB::ConnectedDataSource::AdminConsole": "ExternalResources node; exported without an Id",
    "QB::ConnectedDataSource::Quickbase": "Exported without an Id",
    "QB::ConnectedDataSource::Sample": "ExternalResources node; exported without an Id",
    "QB::ConnectedRecordSet": "ExternalResources node; exported without an Id",
    "QB::PlaceholderRecordSet": "ExternalResources node; exported without an Id",
}

NODE_ID_NOT_ENFORCED_PREFIXES = ("QB::ConnectedColumn::",)


def node_id_is_enforced(qbl_type: str) -> bool:
    if qbl_type in NODE_ID_NOT_ENFORCED:
        return False
    return not qbl_type.startswith(NODE_ID_NOT_ENFORCED_PREFIXES)


PLATFORM_PERMITS: Dict[str, Dict[str, str]] = {
    "QB::Application::Role": {
        "RestrictAccessToNewTablesForThisRole":
            "a boolean",
    },
    "QB::Report::Table": {
        "RowNumberVisibility":
            "one of Default, Hidden or Visible",
    },
}
