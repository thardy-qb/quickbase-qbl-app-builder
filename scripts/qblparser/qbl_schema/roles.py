ROLES_SCHEMA = {
    "QB::Role::AppUI": {
        "required": [],
        "optional": [
            "HideSettings", "HideUsers", "HideFavorites",
            "HideSearch", "HideHelp", "HideTestAs",
        ]
    },

    "QB::Role::TableUI": {
        "required": [],
        "optional": [
            "HideInBar", "HideNewRecord", "HideGridEdit", "HideEmail", "HidePrint",
            "HideImportExport", "HideSaveSpreadsheet", "HideCreateCustomizeReport",
            "HidePersonalSettings",
        ]
    },
}
