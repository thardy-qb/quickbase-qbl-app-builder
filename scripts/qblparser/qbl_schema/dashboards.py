DASHBOARD_SCHEMA = {
    "QB::Dashboard": {
        "required": [],
        "optional": ["Name"]
    },
    "QB::Dashboard::Filter": {
        "required": [],
        "optional": [
            "Name", "Description", "FilterType", "SearchType", "Targets", "IsActive",
        ],
    },
    "QB::Dashboard::Tab": {
        "required": ["CanvasVersion"],
        "optional": ["Name"]
    },
    "QB::Dashboard::Widget": {
        "required": ["X", "Y", "Width", "Height"],
        "optional": []
    },
    "QB::Dashboard::Widget::Button": {
        "required": ["X", "Y", "Width", "Height", "Alignment", "OpenInNewWindow"],
        "optional": ["Text", "Color", "Icon"]
    },
    "QB::Dashboard::Widget::Button::CreateRecord": {
        "required": ["X", "Y", "Width", "Height", "Alignment", "OpenInNewWindow", "AfterSaveAction"],
        "optional": ["Text", "Color", "Icon", "AfterSaveGoTo", "App", "NonDashboardPageId", "Table"]
    },
    "QB::Dashboard::Widget::Button::OpenLink": {
        "required": ["X", "Y", "Width", "Height", "Alignment", "OpenInNewWindow"],
        "optional": ["Text", "Color", "Icon", "Link"]
    },
    "QB::Dashboard::Widget::Button::OpenPage": {
        "required": ["X", "Y", "Width", "Height", "Alignment", "OpenInNewWindow"],
        "optional": ["Text", "Color", "Icon", "Page", "NonDashboardPageId", "App"]
    },
    "QB::Dashboard::Widget::Button::OpenReport": {
        "required": ["X", "Y", "Width", "Height", "Alignment", "OpenInNewWindow"],
        "optional": ["Text", "Color", "Icon", "Report"]
    },
    "QB::Dashboard::Widget::Calendar": {
        "required": ["X", "Y", "Width", "Height", "DefaultView", "Report"],
        "optional": ["Title", "ShowTitle", "ShowWeekends"]
    },
    "QB::Dashboard::Widget::Chart": {
        "required": ["X", "Y", "Width", "Height", "Report"],
        "optional": ["Title"]
    },
    "QB::Dashboard::Widget::Kanban": {
        "required": ["X", "Y", "Width", "Height", "Report"],
        "optional": ["Title", "ShowTitle"]
    },
    "QB::Dashboard::Widget::Kpi": {
        "required": ["X", "Y", "Width", "Height", "KpiType", "Report"],
        "optional": [
            "Title", "Description", "IncludesDelta", "ShowTitle", "ShowTarget", "Scale", 
                     "DecimalPlaces", "TextColor", "DeltaOptions", "Period", "Field"
                     ]
    },
    "QB::Dashboard::Widget::Map": {
        "required": ["X", "Y", "Width", "Height", "Report"],
        "optional": ["Title", "ShowTitle"]
    },
    "QB::Dashboard::Widget::RichText": {
        "required": ["X", "Y", "Width", "Height"],
        "optional": ["Content"]
    },
    "QB::Dashboard::Widget::Search": {
        "required": ["X", "Y", "Width", "Height", "SearchType", "ResultsView", "BackgroundColor", "SearchTarget"],
        "optional": ["Title", "ShowTitle", "ShowHintText", "HintText", "SearchTable", "SearchReport", "SearchFields", "Table", "Fields", "SearchBoxStyle"]
    },
    "QB::Dashboard::Widget::Spacer": {
        "required": ["X", "Y", "Width", "Height", "DividerType"],
        "optional": []
    },
    "QB::Dashboard::Widget::Summary": {
        "required": ["X", "Y", "Width", "Height", "Report"],
        "optional": ["Title", "ShowTitle"]
    },
    "QB::Dashboard::Widget::Table": {
        "required": ["X", "Y", "Width", "Height", "Report"],
        "optional": ["ShowTitle", "Title", "DisableSpreadsheetEdit"]
    },
    "QB::Dashboard::Widget::Timeline": {
        "required": ["X", "Y", "Width", "Height", "Report"],
        "optional": ["Title", "ShowTitle"]
    }
}
