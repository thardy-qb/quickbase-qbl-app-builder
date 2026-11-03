FIELD_PROPERTIES_SCHEMA = {
    "QB::Field::Address": {
        "required": [
            "Format", "Street1", "Street2", "City", "State", "PostalCode", "Country", "Label"
        ],
        "optional": [
            "InputWidth", "DefaultMapType", "IsBold", "DisplayWithoutWrapping", "HelpText",
            "IsSearchable", "AllowedInReports", "AddToAllNewReports", "RolePermissions", "Comments"
        ]
    },
    "QB::Field::Address::State": {
        "required": [],
        "optional": ["Options"]
    },
    "QB::Field::Address::Country": {
        "required": [],
        "optional": ["Options"]
    },
    "QB::Field::Checkbox": {
        "required": ["Label"],
        "optional": [
            "IsAuditable", "IsRequired", "AllowDataCopy", "IsBold", "DisplayWithoutWrapping",
            "HelpText", "IsSearchable", "AllowedInReports", "AddToAllNewReports",
            "SharedWith", "RolePermissions", "DefaultValue", "ShowAsCheckmark", "DoesTotal", "SnapshotSourceLookupField", "Comments"
        ]
    },
    "QB::Field::Currency": {
        "required": ["Label"],
        "optional": [
            "IsAuditable", "InputOptions", "InputType", "AllowCreateChoices", "IsUnique",
            "IsRequired", "AllowDataCopy", "IsBold", "DisplayWithoutWrapping", "HelpText",
            "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith", "RolePermissions",
            "Units", "Width", "DoesTotal", "DoesAverage", "TreatBlankAsZero", "DefaultValue",
            "DecimalPlaces", "DefaultSortOrder", "SeparatorStart", "OverrideSubFieldAccess",
            "NumberFormat", "SeparatorStyle", "SeparatorPlaces", "CurrencySymbol", "CurrencySymbolPosition", "SnapshotSourceLookupField", "Comments", "ListChoices"
        ]
    },
    "QB::Field::Date": {
        "required": ["Label"],
        "optional": [
            "IsAuditable", "IsUnique", "IsRequired", "AllowDataCopy", "IsBold",
            "DisplayWithoutWrapping", "HelpText", "IsSearchable", "AllowedInReports",
            "AddToAllNewReports", "SharedWith", "RolePermissions", "ShowMonthAsAlpha",
            "HideCurrentYear", "ShowDayOfWeek", "DefaultIsToday", "DefaultSortOrder", "SnapshotSourceLookupField", "Comments"
        ]
    },
    "QB::Field::DateCreated": {
        "required": [],
        "optional": ["IsAuditable", "Label", "ShowTime", "ShowMonthAsAlpha", "HideCurrentYear", "ShowDayOfWeek", "ShowTimeZone", "Comments", "AllowedInReports", "IsSearchable",
                     "IsBold", "DisplayWithoutWrapping", "AddToAllNewReports", "DefaultSortOrder"
                     ]
    },
    "QB::Field::DateModified": {
        "required": ["Label"],
        "optional": ["IsAuditable", "ShowTime", "ShowMonthAsAlpha", "HideCurrentYear", "ShowDayOfWeek", "ShowTimeZone", "Comments", "AllowedInReports", "IsSearchable",
                     "IsBold", "DisplayWithoutWrapping", "AddToAllNewReports", "DefaultSortOrder"]
    },
    "QB::Field::DateTime": {
        "required": ["Label"],
        "optional": [
            "IsAuditable", "IsUnique", "IsRequired", "AllowDataCopy", "IsBold", "DisplayWithoutWrapping",
            "HelpText", "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith",
            "RolePermissions", "ShowMonthAsAlpha", "HideCurrentYear", "ShowDayOfWeek", "ShowTimeZone",
            "ShowTime", "DefaultIsNow", "DefaultSortOrder", "SnapshotSourceLookupField", "Comments"
        ]
    },
    "QB::Field::Duration": {
        "required": ["Label"],
        "optional": [
            "IsAuditable", "IsRequired", "AllowDataCopy", "IsBold", "DisplayWithoutWrapping",
            "HelpText", "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith",
            "RolePermissions", "TreatBlankAsZero", "DoesTotal", "DoesAverage", "DefaultValue",
            "DecimalPlaces", "DisplayUnits", "AddFieldToAllNewReports", "SnapshotSourceLookupField", "Comments"
        ]
    },
    "QB::Field::Email": {
        "required": ["Label"],
        "optional": [
            "IsAuditable", "IsUnique", "IsRequired", "AllowDataCopy", "Comments", "IsBold",
            "DisplayWithoutWrapping", "HelpText", "IsSearchable", "AllowedInReports",
            "AddToAllNewReports", "SharedWith", "RolePermissions", "DefaultValue", "DefaultDomain",
            "SortByDomain", "EnableEmailAll", "LinkText", "DisplayAs", "SnapshotSourceLookupField"
        ]
    },
    "QB::Field::FileAttachment": {
        "required": ["Label"],
        "optional": [
            "IsAuditable", "RevisionsToKeep", "AllowPromoteVersion", "UseNewBrowserWindow",
            "AllowOpenAccess", "LinkText", "ShowAsImages", "IsRequired", "IsBold",
            "DisplayWithoutWrapping", "HelpText", "IsSearchable", "AllowedInReports", "AddToAllNewReports",
            "SharedWith", "RolePermissions", "Comments"
        ]
    },
    "QB::Field::LastModifiedBy": {
        "required": ["Label"],
        "optional": ["IsAuditable", "Label", "Comments", "AddToAllNewReports", "AllowedInReports", "DisplayAs", "DisplayWithoutWrapping", "IsBold", "IsSearchable"]
    },
    "QB::Field::ListUser": {
        "required": ["Label"],
        "optional": [
            "IsAuditable", "IsRequired", "AllowDataCopy", "IsBold", "DisplayWithoutWrapping", "HelpText",
            "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith", "RolePermissions",
            "Choices", "UserSet", "AllowCreateChoices", "AllowInviteExternalUser", "DefaultValue", "SnapshotSourceLookupField", "Comments", "DisplayAs", "AllowedInReports", "IsSearchable",
            "IsBold", "DisplayWithoutWrapping", "AddToAllNewReports"
        ]
    },
    "QB::Field::Lookup": {
        "required": ["Lookup"],
        "optional": ["OverrideSubFieldAccess", "DisplayAsLinkToParent", "Comments", "Abbreviate", "AddToAllNewReports", "AllowMentions", "AllowedInReports", "CurrencySymbol",
                     "CurrencySymbolPosition", "DecimalPlaces", "DefaultSortOrder", "DisplayAs", "DisplayAsButton", "DisplayWithoutWrapping", "DoesAverage", "DoesTotal", "EmbedAsIframe",
                     "Height", "HelpText", "HideCurrentYear", "IsBold", "IsSearchable", "Label", "LinkText", "NumberFormat", "SeparatorStart", "ShowDayOfWeek", "ShowMonthAsAlpha",
                     "ShowTime", "ShowTimeZone", "Target", "TreatBlankAsZero", "Units", "Width", "TargetFieldType", "DisplayType", "AllowDataCopy", "DefaultIsToday", "DefaultValue",
                     "EditHistory", "InputOptions", "IsRequired", "IsUnique", "MaxLength", "RolePermissions", "ShowAsCheckmark", "ButtonColor", "Use24HourClock", "DefaultDomain", "EnableEmailAll", "SortByDomain",
                     "Choices", "DisplayUnits", "HasExtension", "IsInternational", "DefaultCountry", "DefaultColumnWidth", "SharedWith"
                     ]
    },
    "QB::Field::LookupBlock": {
        "required": ["Relationship", "TargetField"],
        "optional": ["DisplayType", "DisplayAsLinkToParent", "OverrideSubFieldAccess"]
    },
    "QB::Field::MultiSelectText": {
        "required": ["Label"],
        "optional": [
            "IsAuditable", "InputOptions", "InputType", "AllowCreateChoices", "ChoiceOrder",
            "IsRequired", "AllowDataCopy", "IsBold", "DisplayWithoutWrapping", "HelpText",
            "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith", "RolePermissions",
            "DefaultValue", "SnapshotSourceLookupField", "Comments", "ListChoices"
        ]
    },
    "QB::Field::Number": {
        "required": ["Label"],
        "optional": [
            "IsAuditable", "InputOptions", "InputType", "AllowCreateChoices", "IsUnique",
            "IsRequired", "AllowDataCopy", "IsBold", "DisplayWithoutWrapping", "HelpText",
            "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith", "RolePermissions",
            "Units", "Width", "DoesTotal", "DoesAverage", "TreatBlankAsZero", "DefaultValue",
            "DecimalPlaces", "DefaultSortOrder", "SeparatorStart", "OverrideSubFieldAccess",
            "NumberFormat", "SeparatorStyle", "SeparatorPlaces", "SnapshotSourceLookupField","Comments","ListChoices"
        ]
    },
    "QB::Field::Percent": {
        "required": ["Label"],
        "optional": [
            "IsAuditable", "AllowCreateChoices", "IsUnique", "IsRequired", "AllowDataCopy", "Comments",
            "IsBold", "DisplayWithoutWrapping", "HelpText", "IsSearchable", "AllowedInReports",
            "AddToAllNewReports", "SharedWith", "RolePermissions", "Units", "Width", "DoesTotal",
            "DoesAverage", "TreatBlankAsZero", "DefaultValue", "DecimalPlaces", "DefaultSortOrder",
            "SeparatorStart", "OverrideSubFieldAccess", "NumberFormat", "SeparatorStyle", "SeparatorPlaces", "SnapshotSourceLookupField", "InputOptions", "InputType", "ListChoices"
        ]
    },
    "QB::Field::PhoneNumber": {
        "required": ["Label"],
        "optional": [
            "IsAuditable", "IsUnique", "IsRequired", "AllowDataCopy", "IsBold", "DisplayWithoutWrapping",
            "HelpText", "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith",
            "RolePermissions", "DefaultValue", "HasExtension", "IsInternational", "DefaultCountry", "SnapshotSourceLookupField", "Comments"
        ]
    },
    "QB::Field::Predecessor": {
        "required": ["Label"],
        "optional": [
            "IsAuditable", "IsRequired", "AllowDataCopy", "IsBold", "DisplayWithoutWrapping", "HelpText",
            "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith", "RolePermissions",
            "DefaultValue", "StartDate", "EndDate", "SnapshotSourceLookupField", "Comments"
        ]
    },
    "QB::Field::Rating": {
        "required": ["Label"],
        "optional": [
            "IsAuditable", "AllowCreateChoices", "IsUnique", "IsRequired", "AllowDataCopy", "IsBold",
            "DisplayWithoutWrapping", "HelpText", "IsSearchable", "AllowedInReports", "AddToAllNewReports",
            "SharedWith", "RolePermissions", "Units", "Width", "DoesTotal", "DoesAverage", "TreatBlankAsZero",
            "DefaultValue", "DecimalPlaces", "DefaultSortOrder", "SeparatorStart", "OverrideSubFieldAccess",
            "NumberFormat", "SeparatorStyle", "SeparatorPlaces", "SnapshotSourceLookupField", "Comments", "InputOptions", "InputType", "ListChoices"
        ]
    },
    "QB::Field::RecordId": {
        "required": [],
        "optional": ["Label", "Comments"]
    },
    "QB::Field::RecordOwner": {
        "required": [],
        "optional": ["IsAuditable", "Label", "Comments", "AddToAllNewReports", "AllowedInReports", "DisplayAs", "DisplayWithoutWrapping", "IsBold", "IsSearchable"]
    },
    "QB::Field::Reference": {
        "required": ["Reference"],
        "optional": ["IsAuditable", "Reference", "DisplayAsLinkToParent", "UseRecordPickerForGridEdit", "Comments", "AddToAllNewReports", "AllowedInReports", "DecimalPlaces", 
                     "DefaultSortOrder", "DefaultValue", "DisplayWithoutWrapping", "DoesAverage", "DoesTotal", "HelpText", "IsBold", "IsRequired", "IsSearchable", "IsUnique", 
                     "Label", "NumberFormat", "RolePermissions", "SeparatorStart", "TreatBlankAsZero", "Units", "Width", "DisplayAs", "EditHistory", "Formula", "MaxLength", 
                     "OverrideSubFieldAccess", "SharedWith", "Summary", "LinkText", "DefaultDomain", "EnableEmailAll", "SortByDomain", "DefaultIsToday", "HideCurrentYear", 
                     "ShowDayOfWeek", "ShowMonthAsAlpha", "UseFormulaBuilder", "AllowDataCopy", "InputOptions"
                     ]
    },
    "QB::Field::ReferenceBlock": {
        "required": ["Relationship", "DisplayType"],
        "optional": ["UseRecordPickerForGridEdit", "DisplayAsLinkToParent", "Proxy", "ConditionalValues",
                     "Summary", "Lookup"]
    },
    "QB::Field::ReportLink": {
        "required": ["Label"],
        "optional": [
            "FieldRelationship", "Source", "Target", "MatchValuesExactly", "UseNewWindow",
            "LinkText", "AllowedInReports", "AddToAllNewReports", "IsSearchable", "IsBold",
            "DisplayWithoutWrapping", "HelpText", "SharedWith", "RolePermissions", "Comments"
        ]
    },
    "QB::Field::RichText": {
        "required": ["Label"],
        "optional": [
            "IsAuditable", "IsUnique", "IsRequired", "AllowDataCopy", "IsBold", "DisplayWithoutWrapping",
            "HelpText", "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith",
            "RolePermissions", "MaxLength", "DefaultValue", "EditHistory", "Enable", "ExpandedHistory",
            "PrependHistory", "UseFullName", "IncludeTime", "IncludeTimeZone", "Width", "Height",
            "AllowMentions", "SnapshotSourceLookupField", "Comments", "DefaultDomain", "SortByDomain", "EnableEmailAll"
        ]
    },
    "QB::Field::Summary": {
        "required": ["Summary",  "Label"],
        "optional": [
            "OverrideSubFieldAccess",
            "Comments", "AddToAllNewReports", "AllowedInReports", "CurrencySymbol", "CurrencySymbolPosition", "DecimalPlaces", "DefaultSortOrder", 
            "DisplayWithoutWrapping", "DoesAverage", "DoesTotal", "HelpText", "HideCurrentYear", "IsBold", "IsSearchable", "NumberFormat", "SeparatorStart", "ShowAsCheckmark", 
            "ShowDayOfWeek", "ShowMonthAsAlpha", "TreatBlankAsZero", "Units", "Width", "AllowDataCopy", "DefaultIsNow", "DefaultIsToday", "DefaultValue", "InputOptions", "IsRequired", 
            "IsUnique", "RolePermissions", "ShowTime", "ShowTimeZone", "DisplayUnits"
        ]
    },
    "QB::Field::SummaryBlock": {
        "required": ["ReferenceField", "Function"],
        "optional": [
            "DisplayType",
            "DrillDownReport", "Query", "DisplayAsLinkToChildren",
            "OverrideSubFieldAccess", "EvaluateOnlyOnChange", "FieldToSummarize", "DisplayAs", "EditHistory", "Formula", "MaxLength", "OverrideSubFieldAccess", "SharedWith"
        ]
    },
    "QB::Field::Text": {
        "required": [
            "InputOptions", "Label"
        ],
        "optional": [
            "IsAuditable", "IsUnique", "AllowCreateChoices", "ChoiceOrder", "IsRequired",
            "AllowDataCopy", "IsBold", "DisplayWithoutWrapping", "HelpText", "IsSearchable",
            "AllowedInReports", "AddToAllNewReports", "SharedWith", "RolePermissions", "MaxLength",
            "DefaultValue", "EditHistory", "Enable", "ExpandedHistory", "PrependHistory", "UseFullName",
            "IncludeTime", "IncludeTimeZone", "Width",  "SnapshotSourceLookupField", "Comments", "InputType", "ListChoices", "DisplayType"
        ]
    },
    "QB::Field::TextMultiLine": {
        "required": [
            "Label"
        ],
        "optional": [
            "IsAuditable", "AllowCreateChoices", "ChoiceOrder", "IsRequired", "AllowDataCopy",
            "IsBold", "DisplayWithoutWrapping", "HelpText", "IsSearchable", "AllowedInReports",
            "AddToAllNewReports", "SharedWith", "RolePermissions", "MaxLength", "DefaultValue",
            "EditHistory", "Enable", "ExpandedHistory", "PrependHistory", "UseFullName",
            "IncludeTime", "IncludeTimeZone", "Height", "Width",  "SnapshotSourceLookupField", "Comments", "InputType", "ListChoices", 
        ]
    },
    "QB::Field::TextMultipleChoice": {
        "required": [
            "Label"
        ],
        "optional": [
            "IsAuditable", "IsUnique", "AllowCreateChoices", "ChoiceOrder", "IsRequired",
            "AllowDataCopy", "IsBold", "DisplayWithoutWrapping", "HelpText", "IsSearchable",
            "AllowedInReports", "AddToAllNewReports", "SharedWith", "RolePermissions", "MaxLength",
            "DefaultValue", "EditHistory", "Enable", "ExpandedHistory", "PrependHistory", "UseFullName",
            "IncludeTime", "IncludeTimeZone",  "SnapshotSourceLookupField", "Comments",  "InputType", "ListChoices", "InputOptions", 
        ]
    },
    "QB::Field::TimeOfDay": {
        "required": ["Label"],
        "optional": [
            "IsAuditable", "IsUnique", "IsRequired", "AllowDataCopy", "IsBold", "DisplayWithoutWrapping",
            "HelpText", "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith",
            "RolePermissions", "DefaultValue", "DisplayAs", "Use24HourClock", "ShowTimeZone",
            "DecimalPlaces",  "SnapshotSourceLookupField", "Comments"
        ]
    },
    "QB::Field::URL": {
        "required": ["Label"],
        "optional": [
            "IsAuditable", "IsUnique", "IsRequired", "AllowDataCopy", "IsBold", "DisplayWithoutWrapping",
            "HelpText", "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith",
            "RolePermissions", "LinkText", "DefaultValue", "Abbreviate", "DisplayAsButton", "ButtonColor",
            "EmbedAsIframe", "IframeWidth", "IframeHeight", "Target",  "SnapshotSourceLookupField", "Comments"
        ]
    },
    "QB::Field::User": {
        "required": ["Label"],
        "optional": [
            "IsAuditable", "IsUnique", "IsRequired", "AllowDataCopy", "IsBold", "DisplayWithoutWrapping",
            "HelpText", "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith",
            "RolePermissions", "Choices", "UserSet", "AllowCreateChoices", "AllowInviteExternalUser",
            "DefaultValue", "DisplayAs",  "SnapshotSourceLookupField", "Comments"
        ]
    },
    "QB::Field::WorkDate": {
        "required": ["Label"],
        "optional": [
            "IsAuditable", "IsUnique", "IsRequired", "AllowDataCopy", "IsBold", "DisplayWithoutWrapping",
            "HelpText", "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith",
            "RolePermissions", "ShowMonthAsAlpha", "HideCurrentYear", "ShowDayOfWeek",
            "DefaultIsToday", "DefaultSortOrder",  "SnapshotSourceLookupField", "Comments"
        ]
    },
    "QB::Field::Unsupported": {
        "required": ["Label"],
        "optional": ["Explanation"]
    }
}
