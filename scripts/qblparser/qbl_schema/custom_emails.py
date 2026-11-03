CUSTOM_EMAIL_SCHEMA = {
    "QB::CustomEmail": {
        "required": ["Name", "Owner"],
        "optional": ["Description", "SendOptions", "EmailSettings"],
    },
    "QB::CustomEmail::Condition::Group": {
        "required": [],
        "optional": ["TrueWhen"],
    },
    "QB::CustomEmail::Condition::Field": {
        "required": [],
        "optional": ["Field", "Comparison", "Value"],
    },
    "QB::CustomEmail::Condition::DaysAgo": {
        "required": [],
        "optional": ["Field", "Comparison", "DaysAgo"],
    },
    "QB::CustomEmail::Condition::Range": {
        "required": [],
        "optional": ["Field", "Comparison", "RelativeTo", "TimeFrame", "Range"],
    },
    "QB::CustomEmail::Condition::Relative": {
        "required": [],
        "optional": ["Field", "Comparison", "RelativeTo"],
    },
}


NESTED_DOCUMENTED_PROPERTIES = {
    "QB::CustomEmail": {
        "SendOptions": (
            "TriggerType",
            "RecordEventTrigger",
            "Fields",
            "Schedule",
        ),
        "EmailSettings": (
            "CheckRecipientPermissions",
            "BulkChange",
            "SendScheduledEmailEvenWhenEmpty",
            "Subject",
            "From",
            "To",
            "CC",
            "BCC",
            "Content",
            "FileAttachments",
            "Documents",
        ),
        "EmailSettings.To": (
            "UserEntities",
            "Users",
            "Fields",
            "Roles",
            "ExternalUsers",
            "Groups",
        ),
        "EmailSettings.CC": ("UserEntities", "Users", "ExternalUsers"),
        "EmailSettings.BCC": ("UserEntities", "Users", "ExternalUsers"),
    },
}
