LEGACY_FORM_SCHEMA = {
    "QB::Form": {
        "required": [],
        "optional": [
            "Name", "Description", "DisplayPagesAs", "ShouldAutoAddFields",
            "ShouldShowBuiltInFieldsFooter", "AlwaysTabsForViewRecord", 
            "AllowedSaveActions", "DefaultSaveAction", "ShowSaveAndAddAnother",
            "ShowSaveAndKeepWorking", "ShowDoneButton", "DoneButtonText",
            "FormHeader", "FormFooter", "PageHeader", "PageFooter",
            "HorizontalRuleBetweenSections", "NewFieldAction", "ShowBuiltInFields", 
            "ShowSaveAndCancelButtons", "WaitForEmbeddedReports", "WrapFieldLabels", 
            "ShowFieldBorders", "ShowSectionBorders", "FieldSpacing", "SectionSpacing"
        ]
    },
}

LEGACY_FORM_SCHEMA["QB::Form::Element::Tab"] = {
    "required": [],
    "optional": ["Label", "Color"],
}

LEGACY_FORM_SCHEMA["QB::Form::Element::RatingField"] = {
    "required": [],
    "optional": ["DisplayOn", "Field", "Label", "ReadOnly", "Required"],
}


