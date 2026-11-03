FORMULA_FIELD_SCHEMA = {
    "QB::Field::Checkbox::Formula": {
        "required": ["Label"],
        "optional": [
            "Formula", "OverrideSubFieldAccess", "IsRequired", "AllowDataCopy", 
            "IsBold", "DisplayWithoutWrapping", "HelpText", "IsSearchable", 
            "AllowedInReports", "AddToAllNewReports", "SharedWith", "RolePermissions",
            "DefaultValue", "ShowAsCheckmark", "DoesTotal", "Comments", "SnapshotSourceLookupField"
        ]
    },
    "QB::Field::Currency::Formula": {
        "required": ["Label"],
        "optional": [
            "Formula", "OverrideSubFieldAccess", "IsUnique", "IsRequired", 
            "AllowDataCopy", "IsBold", "DisplayWithoutWrapping", "HelpText", 
            "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith", 
            "RolePermissions", "Units", "Width", "DoesTotal", "DoesAverage", 
            "TreatBlankAsZero", "DefaultValue", "DecimalPlaces", "DefaultSortOrder", 
            "SeparatorStart", "NumberFormat", "SeparatorStyle", "SeparatorPlaces", 
            "CurrencySymbol", "CurrencySymbolPosition", "Comments", "SnapshotSourceLookupField"
        ]
    },
    "QB::Field::Date::Formula": {
        "required": ["Label"],
        "optional": [
            "Formula", "OverrideSubFieldAccess", "IsUnique", "IsRequired", 
            "AllowDataCopy", "IsBold", "DisplayWithoutWrapping", "HelpText", 
            "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith", 
            "RolePermissions", "ShowMonthAsAlpha", "HideCurrentYear", "ShowDayOfWeek", 
            "DefaultIsToday", "DefaultSortOrder", "UseFormulaBuilder", "FiveDayWorkWeek", "Comments","SnapshotSourceLookupField"
        ]
    },
    "QB::Field::DateTime::Formula": {
        "required": ["Label"],
        "optional": [
            "Formula", "OverrideSubFieldAccess", "IsUnique", "IsRequired", 
            "AllowDataCopy", "IsBold", "DisplayWithoutWrapping", "HelpText", 
            "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith", 
            "RolePermissions", "ShowMonthAsAlpha", "HideCurrentYear", "ShowDayOfWeek", 
            "ShowTimeZone", "ShowTime", "DefaultIsNow", "DefaultSortOrder", "Comments", "SnapshotSourceLookupField"
        ]
    },
    "QB::Field::Duration::Formula": {
        "required": ["Label"],
        "optional": [
            "Formula", "OverrideSubFieldAccess", "IsUnique", "IsRequired", 
            "AllowDataCopy", "IsBold", "DisplayWithoutWrapping", "HelpText", 
            "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith", 
            "RolePermissions", "TreatBlankAsZero", "DoesTotal", "DoesAverage", 
            "DefaultValue", "DecimalPlaces", "DisplayUnits", "AddFieldToAllNewReports", "Comments", "SnapshotSourceLookupField"
        ]
    },
    "QB::Field::Email::Formula": {
        "required": ["Label"],
        "optional": [
            "Formula", "OverrideSubFieldAccess", "IsUnique", "IsRequired", 
            "AllowDataCopy", "Comments", "IsBold", "DisplayWithoutWrapping", 
            "HelpText", "IsSearchable", "AllowedInReports", "AddToAllNewReports", 
            "SharedWith", "RolePermissions", "DefaultValue", "DefaultDomain", 
            "SortByDomain", "EnableEmailAll", "LinkText", "DisplayAs", "SnapshotSourceLookupField"
        ]
    },
    "QB::Field::ListUser::Formula": {
        "required": ["Label"],
        "optional": [
            "Formula", "OverrideSubFieldAccess", "IsRequired", "AllowDataCopy", 
            "IsBold", "DisplayWithoutWrapping", "HelpText", "IsSearchable", 
            "AllowedInReports", "AddToAllNewReports", "SharedWith", "RolePermissions", 
            "Choices", "UserSet", "AllowCreateChoices", "AllowInviteExternalUser", 
            "DefaultValue", "Comments", "SnapshotSourceLookupField"
        ]
    },
    "QB::Field::MultiSelectText::Formula": {
        "required": ["Label"],
        "optional": [
            "Formula", "OverrideSubFieldAccess", "IsUnique", "IsRequired", 
            "AllowDataCopy", "IsBold", "DisplayWithoutWrapping", "HelpText", 
            "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith", 
            "RolePermissions", "Comments", "SnapshotSourceLookupField", "DefaultColumnWidth"
        ]
    },
    "QB::Field::Percent::Formula": {
        "required": ["Label"],
        "optional": [
            "Formula", "OverrideSubFieldAccess", "IsUnique", "IsRequired", 
            "AllowDataCopy", "IsBold", "DisplayWithoutWrapping", "HelpText", 
            "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith", 
            "RolePermissions", "Units", "Width", "DoesTotal", "DoesAverage", 
            "TreatBlankAsZero", "DefaultValue", "DecimalPlaces", "DefaultSortOrder", 
            "SeparatorStart", "NumberFormat", "SeparatorStyle", "SeparatorPlaces", "Comments", "SnapshotSourceLookupField"
        ]
    },
    "QB::Field::PhoneNumber::Formula": {
        "required": ["Label"],
        "optional": [
            "Formula", "OverrideSubFieldAccess", "IsUnique", "IsRequired", 
            "AllowDataCopy", "IsBold", "DisplayWithoutWrapping", "HelpText", 
            "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith", 
            "RolePermissions", "DefaultValue", "HasExtension", "IsInternational", 
            "DefaultCountry", "Comments", "SnapshotSourceLookupField"
        ]
    },
    "QB::Field::Rating::Formula": {
        "required": ["Label"],
        "optional": [
            "Formula", "OverrideSubFieldAccess", "IsUnique", "IsRequired", 
            "AllowDataCopy", "IsBold", "DisplayWithoutWrapping", "HelpText", 
            "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith", 
            "RolePermissions", "Units", "Width", "DoesTotal", "DoesAverage", 
            "TreatBlankAsZero", "DefaultValue", "DecimalPlaces", "DefaultSortOrder", 
            "SeparatorStart", "NumberFormat", "SeparatorStyle", "SeparatorPlaces", "Comments", "SnapshotSourceLookupField"
        ]
    },
    "QB::Field::RichText::Formula": {
        "required": ["Label"],
        "optional": [
            "Formula", "OverrideSubFieldAccess", "IsUnique", "IsRequired", 
            "AllowDataCopy", "IsBold", "DisplayWithoutWrapping", "HelpText", 
            "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith", 
            "RolePermissions", "MaxLength", "DefaultValue", "EditHistory", "Enable", 
            "ExpandedHistory", "PrependHistory", "UseFullName", "IncludeTime", 
            "IncludeTimeZone", "Width", "Comments", "SnapshotSourceLookupField"
        ]
    },
    "QB::Field::Text::Formula": {
        "required": ["Label"],
        "optional": [
            "Formula", "OverrideSubFieldAccess", "IsUnique", "IsRequired", 
            "AllowDataCopy", "IsBold", "DisplayWithoutWrapping", "HelpText", 
            "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith", 
            "RolePermissions", "MaxLength", "DefaultValue", "EditHistory", "Enable", 
            "ExpandedHistory", "PrependHistory", "UseFullName", "IncludeTime", 
            "IncludeTimeZone", "Comments", "SnapshotSourceLookupField"
        ]
    },
    "QB::Field::TimeOfDay::Formula": {
        "required": ["Label"],
        "optional": [
            "Formula", "OverrideSubFieldAccess", "IsUnique", "IsRequired", 
            "AllowDataCopy", "IsBold", "DisplayWithoutWrapping", "HelpText", 
            "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith", 
            "RolePermissions", "DefaultValue", "DisplayAs", "Use24HourClock", 
            "ShowTimeZone", "DecimalPlaces", "Comments", "SnapshotSourceLookupField"
        ]
    },
    "QB::Field::URL::Formula": {
        "required": ["Label"],
        "optional": [
            "Formula", "OverrideSubFieldAccess", "IsUnique", "IsRequired", 
            "AllowDataCopy", "IsBold", "DisplayWithoutWrapping", "HelpText", 
            "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith", 
            "RolePermissions", "LinkText", "DefaultValue", "Abbreviate", 
            "DisplayAsButton", "ButtonColor", "EmbedAsIframe", "IframeWidth", 
            "IframeHeight", "Target", "Comments", "SnapshotSourceLookupField"
        ]
    },
    "QB::Field::User::Formula": {
        "required": ["Label"],
        "optional": [
            "Formula", "OverrideSubFieldAccess", "IsRequired", "AllowDataCopy", 
            "IsBold", "DisplayWithoutWrapping", "HelpText", "IsSearchable", 
            "AllowedInReports", "AddToAllNewReports", "SharedWith", "RolePermissions", 
            "Choices", "UserSet", "AllowCreateChoices", "AllowInviteExternalUser", 
            "DisplayAs", "Comments", "SnapshotSourceLookupField"
        ]
    },
    "QB::Field::WorkDate::Formula": {
        "required": ["Label"],
        "optional": [
            "Formula", "OverrideSubFieldAccess", "IsUnique", "IsRequired", 
            "AllowDataCopy", "IsBold", "DisplayWithoutWrapping", "HelpText", 
            "IsSearchable", "AllowedInReports", "AddToAllNewReports", "SharedWith", 
            "RolePermissions", "ShowMonthAsAlpha", "HideCurrentYear", "ShowDayOfWeek", 
            "DefaultIsToday", "DefaultSortOrder", "UseFormulaBuilder", "FiveDayWorkWeek", "Comments", "SnapshotSourceLookupField"
        ]
    }
}