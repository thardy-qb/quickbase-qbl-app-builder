REPORT_SCHEMA = {
    "QB::Report": {
        "required": ["Name"],
        "optional": [
            "Description", "ShowDescription", "Filters", "RolePermissions",
            "ColorCoding", "ColorBy", "ColorFormula", "CalendarEvents", "StartDate", "EndDate",
            "DisplayFields", "AllowRecordCreationFromCalendar", "DisplayCalendarEventsAs",
            "MaxEventsPerDay", "FirstDayOfTheWeek", "InitialMonthToDisplay", "SpecificMonthToDisplay",
            "Month", "Year", "Sort", "SortAndGroup", "SortGroupsByStartField", "Timeline",
            "Columns", "ColumnsUI", "AllowEditingRecords", "AllowViewingRecords", "HideTotals",
            "DisplayOnlyNewOrChangedRecords", "ShowSummaryTable", "HideMainTable", "AddressField",
            "MapType", "Icons", "DrilldownReport", "GroupingAndCrosstabs", "Rows", "Crosstabs",
            "Source", "SummarizeBy", "DisplayAs", "Criteria", "DynamicFields", "AllowQuickSearch",
            "CardGroups", "GroupBy", "Values", "Appearance", "DefaultTimeline", "Label",
            "Formula", "DecimalPlaces"
        ]
    },
}

REPORT_SCHEMA["QB::Report::DefaultCalendar"] = {
    "required": [],
    "optional": ["CalendarEvents"],
}

REPORT_SCHEMA["QB::Report::DefaultTimeline"] = {
    "required": [],
    "optional": ["Columns", "SortAndGroup", "Timeline", "SortGroupsByStartField"],
}


_FORMULA_COLUMN_TYPES = (
    "Checkbox", "Date", "DateTime", "Duration", "EmailAddress", "ListUsers",
    "MultiselectText", "Numeric", "NumericCurrency", "NumericPercent",
    "NumericRating", "PhoneNumber", "RichText", "Text", "TimeOfDay", "URL", "User",
)

_DECIMAL_PLACES_TYPES = frozenset({"Numeric", "NumericCurrency", "NumericPercent", "NumericRating"})

for _family in ("Formula", "SummaryFormula"):
    for _name in _FORMULA_COLUMN_TYPES:
        _optional = ["Label", "Formula"]
        if _name in _DECIMAL_PLACES_TYPES:
            _optional.append("DecimalPlaces")
        REPORT_SCHEMA[f"QB::Report::{_family}::{_name}"] = {
            "required": [],
            "optional": _optional,
        }

del _family, _name, _optional
