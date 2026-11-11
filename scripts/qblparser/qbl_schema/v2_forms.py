FORM_ELEMENTS_SCHEMA = {
    "QB::FormV2": {
        "required": [],
        "optional": [
            "Name", "DisplayPagesAs", "ShouldAutoAddFields", 
            "ShouldShowBuiltInFieldsFooter", "AlwaysTabsForViewRecord", 
            "AllowedSaveActions",
            "BotCheckModes"
        ]
    },
    "QB::FormV2::Column": {
        "required": [],
        "optional": [
            "LayoutWidth",
            "Title", "BackgroundColor", "ShowBackgroundColor",
            "OnlyBorderColor"
        ]
    },
    "QB::FormV2::Element": {
        "required": [],
        "optional": [
            "LabelOverride", "LabelMode"
        ]
    },
    "QB::FormV2::Element::Field": {
        "required": [],
        "optional": [
            "Field", "ForceRequireOnForm", "ForceReadOnlyOnForm",
            "HideMap",
            "LabelOverride", "LabelMode", "Width", "HelpText", 
            "ModesToShowIn", "FilterChoicesBy", "EntryMode", 
            "ShouldValidate", "NumberOfLines", "MultipleChoiceDisplayAs"
        ]
    },
    "QB::FormV2::Element::Group": {
        "required": [],
        "optional": [
            "LabelOverride", "LabelMode"
        ]
    },
    "QB::FormV2::Element::Report": {
        "required": [],
        "optional": [
            "ReportLinkField",
            "LabelOverride", "LabelMode", "Width", "Height", "Report", 
            "ModesToShowIn", "ShouldOpenInEmbedded", "HideToolbar", 
            "AllowCreateRecords", "SubForm"
        ]
    },
    "QB::FormV2::Element::RichText": {
        "required": [],
        "optional": [
            "LabelOverride", "LabelMode", "ModesToShowIn", "Width", 
            "Content", "ShowBackgroundColor", "BackgroundColor"
        ]
    },
    "QB::FormV2::Page": {
        "required": [],
        "optional": [
            "Name", "Color"
        ]
    },
    "QB::FormV2::Section": {
        "required": [],
        "optional": [
            "Title", "ModesToShowIn", "IsCollapsible", 
            "IsCollapsedByDefault", "ShowColumnDividers"
        ]
    }
}