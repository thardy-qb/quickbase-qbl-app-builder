PIPELINE_SCHEMA = {
    "QB::Pipeline": {
        "required": [],
        "optional": [
            "Name", "Tags", "Owner", "Description",
            "Crontab", "CrontabTimezone"
        ]
    },

    "QB::PipelineStep": {
        "required": [],
        "optional": [
            "Id", "SubType",
            "Name", "Type", "AccountId", "Channel", "Inputs", "InputsMeta", 
            "Outputs", "OutputsMeta", "Conditions", "Filters", "Target",
            "Then", "Else", "Steps",
            "PipelineChannelAccount"
        ]
    },
    "QB::PipelineStep::InputsMeta": {
        "required": [],
        "optional": ["Trigger_On_All_Fields", "PipelineStep_DataSources"]
    },
    "QB::PipelineStep::DataSource::Fields": {
        "required": [],
        "optional": ["Fields", "Name", "Source"]
    },
    "QB::PipelineStep::DataSource::Table": {
        "required": [],
        "optional": ["Table", "Name", "Source"]
    },
}
