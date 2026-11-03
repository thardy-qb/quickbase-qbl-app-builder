TABLES_SCHEMA = {
    "QB::Table": {
        "required": ["Name", "KeyField", "AliasHint"],
        "optional": [
            "Description", "RecordNameSingular", "RecordNamePlural", "SaveOnExit",
            "Searchable", "IndexFileAttachments", "IncludeInTableBar", "TableNameOverride", 
            "TableIconName", "DefaultRecordPicker", "CustomDataRules", "TurnedOn", 
            "Formula", "UseCustomRecordTitleField", "RecordTitleField", "RolePermissions",
            "DefaultReportSettings", "TableHomePageSettings", "ConnectedData", "KanbanManualOrderField",
            "ReportGroupOrder",
        ]
    },
    
    "QB::Table::CustomDataRules": {
        "required": [],
        "optional": [
            "TurnedOn", "Formula"
        ]
    },
    
    "QB::Table::RolePermissions": {
        "required": [],
        "optional": [
            "CanAddRecords", "CanDeleteRecords", "CanSaveCommonReports",
            "CanEditFieldProperties", "CanViewRecords", "CanModifyRecords",
            "CanRefreshConnectedData",
        ]
    }
}