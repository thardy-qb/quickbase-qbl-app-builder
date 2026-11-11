APPLICATION_SCHEMA = {
    "QB::Application": {
        "required": ["Name", "Manager", "TableOrder", "RoleOrder"],
        "optional": [
            "Description", "AppIcon", "AppColor", "CurrencySymbol", "CurrencySymbolPosition",
            "NumberFormat", "SeparatorStyle", "SeparatorPlaces", "DateFormat", "FirstDayOfWeek",
            "FirstMonthOfFiscalYear", "FiscalYearDesignation", "Timezone", "HideNewUpdatedIcons",
            "DisableAllUsersSelection", "Utf8DataEncoding", "CanCopyApp", "CanExportData",
            "Searchable", "RequireAppToken", "ShowPerformanceBar", "ShowPerformanceAnalyzer",
            "GlobalSearchExactMatch", "DefaultViewMode", "Branding",
            "UseCustomHeaderAndFooter",
            "AppHeader",
            "HideQuickbaseStandardMenu", "UseCustom", "LeftText", "LeftLink", "RightText",
            "RightLink", "BackgroundColor", "TextColor", "AppFooter", "EmailUpperLeftElement",
            "DisplayChartShading",
            "CrossApplicationAccess",
            "DisableNonAdminSyncConnections", "TableV3State", "TableV3UserToggleState"
        ]
    },
    "QB::Application::Variable": {
        "required": ["Name"],
        "optional": ["Value"]
    }
}
