_WIDGET_CHROME = ("IsCollapsible", "Title", "ShowTitle", "Width", "Height")

PAGES_SCHEMA = {
    "QB::RichTextPage": {
        "required": ["Name"],
        "optional": ["RawText"],
    },
    "QB::HomePage::Widget::LinkBar": {
        "required": [],
        "optional": list(_WIDGET_CHROME) + ["Alignment", "IsVerticalAligned", "LinkSeparator", "Color"],
    },
    "QB::HomePage::Widget::ReportsList": {
        "required": [],
        "optional": list(_WIDGET_CHROME) + ["ShowReportsFrom", "TargetTables"],
    },
    "QB::HomePage::Widget::Search": {
        "required": [],
        "optional": list(_WIDGET_CHROME) + [
            "AllowUserDoExactSearch", "DoExactSearch", "SearchFieldLabel",
            "SearchFieldPlaceholder", "SearchForm",
            "ResultsView", "SearchTarget", "SearchTable", "SearchReport",
        ],
    },
    "QB::HomePage::Widget::WebPage": {
        "required": [],
        "optional": list(_WIDGET_CHROME) + ["Url"],
    },
    "QB::HomePage::Widget::Link": {
        "required": ["Name"],
        "optional": ["Url", "LinkType", "RedirectUrl"],
    },
    "QB::HomePage::Widget::Field": {
        "required": [],
        "optional": ["TargetField", "Label", "Placeholder"],
    },
    "QB::HomePage::SidebarRow": {
        "required": [],
        "optional": [],
    },
}
