_COMMON = ("Description", "DrilldownReport", "Filters", "RolePermissions", "ShowDescription")

_DATA_DETAILS_CHARTS = (
    "Area3D",
    "AreaSpline",
    "Bar3D",
    "Bubble",
    "Donut",
    "Donut3D",
    "Funnel3D",
    "Heatmap",
    "Pie3D",
    "Scatter",
    "Scatter3D",
    "Spline",
    "StackedBar3D",
    "Streamgraph",
    "VariwideBar",
    "Waterfall",
)

CHART_SCHEMA = {
    "QB::Chart": {
        "required": ["Name"],
        "optional": [
            "DrilldownReport", "RolePermissions", "Filters", "Description", "ShowDescription",
            "DataDetails", "Sorting", "Data", "Series", "LegendColors", "GaugeLimits", "Colors", "DataLabels"
        ]
    },
}

for _name in _DATA_DETAILS_CHARTS:
    CHART_SCHEMA[f"QB::Chart::{_name}"] = {
        "required": ["DataDetails", "Name"],
        "optional": list(_COMMON),
    }

CHART_SCHEMA["QB::Chart::Funnel"] = {
    "required": ["Data", "DataLabels", "Name", "Series", "Sorting"],
    "optional": list(_COMMON) + ["LegendColors"],
}

CHART_SCHEMA["QB::Chart::ProgressBar"] = {
    "required": ["Data", "GaugeLimits", "Name"],
    "optional": list(_COMMON) + ["Colors"],
}

del _name
