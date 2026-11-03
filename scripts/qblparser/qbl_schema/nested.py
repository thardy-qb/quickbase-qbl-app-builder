SCHEMA_VERSION = "0.14"

KEYED_PATHS = {
    "QB::Table": {
        "TableHomePageSettings.RoleViews": {
            "required_keys": ["Everyone"],
            "required": ["View"],
        },
    },
}

NESTED_REQUIRED = {
    'QB::Chart::Area': {
        'DataDetails': ['CategoryAxis', 'DataAxis', 'DataLabels'],
        'DataDetails.CategoryAxis': ['Source'],
        'DataDetails.DataAxis': ['Data'],
    },
    'QB::Chart::Area3D': {
        'DataDetails': ['CategoryAxis', 'DataAxis', 'DataLabels'],
        'DataDetails.CategoryAxis': ['Source'],
        'DataDetails.DataAxis': ['Data'],
    },
    'QB::Chart::AreaSpline': {
        'DataDetails': ['CategoryAxis', 'DataAxis', 'DataLabels'],
        'DataDetails.CategoryAxis': ['Source'],
        'DataDetails.DataAxis': ['Data'],
    },
    'QB::Chart::Bar': {
        'DataDetails': ['CategoryAxis', 'DataAxis', 'DataLabels'],
        'DataDetails.CategoryAxis': ['Source'],
        'DataDetails.DataAxis': ['Data'],
    },
    'QB::Chart::Bar3D': {
        'DataDetails': ['CategoryAxis', 'DataAxis', 'DataLabels'],
        'DataDetails.CategoryAxis': ['Source'],
        'DataDetails.DataAxis': ['Data'],
    },
    'QB::Chart::Bubble': {
        'DataDetails': ['BubbleSize', 'CategoryAxis', 'DataAxis', 'DataLabels'],
        'DataDetails.CategoryAxis': ['Source'],
        'DataDetails.DataAxis': ['Data'],
    },
    'QB::Chart::Donut': {
        'DataDetails': ['Data', 'DataLabels', 'Series'],
        'DataDetails.Data': ['Source'],
        'DataDetails.Series': ['Source'],
    },
    'QB::Chart::Donut3D': {
        'DataDetails': ['Data', 'DataLabels', 'Series'],
        'DataDetails.Data': ['Source'],
        'DataDetails.Series': ['Source'],
    },
    'QB::Chart::Funnel': {
        'Data': ['Source'],
        'Series': ['Source'],
    },
    'QB::Chart::Funnel3D': {
        'DataDetails': ['Data', 'DataLabels', 'Series'],
        'DataDetails.Data': ['Source'],
        'DataDetails.Series': ['Source'],
    },
    'QB::Chart::Gauge': {
        'Data': ['Source'],
    },
    'QB::Chart::Heatmap': {
        'DataDetails': ['CategoryAxisX', 'CategoryAxisY', 'DataAxis', 'DataLabels'],
        'DataDetails.CategoryAxisX': ['Source'],
        'DataDetails.CategoryAxisY': ['Source'],
        'DataDetails.DataAxis': ['Source'],
    },
    'QB::Chart::HorizontalBar': {
        'DataDetails': ['CategoryAxis', 'DataAxis', 'DataLabels'],
        'DataDetails.CategoryAxis': ['Source'],
        'DataDetails.DataAxis': ['Data'],
    },
    'QB::Chart::HorizontalStackedBar': {
        'DataDetails': ['CategoryAxis', 'DataAxis', 'DataLabels'],
        'DataDetails.CategoryAxis': ['Source'],
        'DataDetails.DataAxis': ['Data'],
    },
    'QB::Chart::Line': {
        'DataDetails': ['CategoryAxis', 'DataAxisPrimary', 'DataLabels'],
        'DataDetails.CategoryAxis': ['Source'],
        'DataDetails.DataAxisPrimary': ['Data'],
    },
    'QB::Chart::LineBar': {
        'DataDetails': ['CategoryAxis', 'DataAxisBar', 'DataAxisLine', 'DataLabels'],
        'DataDetails.CategoryAxis': ['Source'],
        'DataDetails.DataAxisBar': ['Data'],
        'DataDetails.DataAxisLine': ['Data'],
    },
    'QB::Chart::Pie': {
        'DataDetails': ['DataLabels', 'DataSource', 'Series'],
        'DataDetails.Series': ['Source'],
    },
    'QB::Chart::Pie3D': {
        'DataDetails': ['Data', 'DataLabels', 'Series'],
        'DataDetails.Data': ['Source'],
        'DataDetails.Series': ['Source'],
    },
    'QB::Chart::ProgressBar': {
        'Data': ['Source'],
    },
    'QB::Chart::RadialBar': {
        'DataDetails': ['CategoryAxis', 'DataAxis', 'DataLabels'],
        'DataDetails.CategoryAxis': ['Source'],
        'DataDetails.DataAxis': ['Data'],
    },
    'QB::Chart::Scatter': {
        'DataDetails': ['CategoryAxis', 'DataAxis', 'DataLabels'],
        'DataDetails.CategoryAxis': ['Source'],
        'DataDetails.DataAxis': ['Data'],
    },
    'QB::Chart::Scatter3D': {
        'DataDetails': ['CategoryAxis', 'DataAxis', 'DataLabels', 'XAxis'],
        'DataDetails.CategoryAxis': ['Source'],
        'DataDetails.DataAxis': ['Data'],
        'DataDetails.XAxis': ['Source'],
    },
    'QB::Chart::Spline': {
        'DataDetails': ['CategoryAxis', 'DataAxis', 'DataLabels'],
        'DataDetails.CategoryAxis': ['Source'],
        'DataDetails.DataAxis': ['Data'],
    },
    'QB::Chart::StackedBar': {
        'DataDetails': ['CategoryAxis', 'DataAxis', 'DataLabels'],
        'DataDetails.CategoryAxis': ['Source'],
        'DataDetails.DataAxis': ['Data'],
    },
    'QB::Chart::StackedBar3D': {
        'DataDetails': ['CategoryAxis', 'DataAxis', 'DataLabels'],
        'DataDetails.CategoryAxis': ['Source'],
        'DataDetails.DataAxis': ['Data'],
    },
    'QB::Chart::Streamgraph': {
        'DataDetails': ['CategoryAxis', 'DataAxis', 'DataLabels'],
        'DataDetails.CategoryAxis': ['Source'],
        'DataDetails.DataAxis': ['Data'],
    },
    'QB::Chart::VariwideBar': {
        'DataDetails': ['BarWidth', 'CategoryAxis', 'DataAxis', 'DataLabels'],
        'DataDetails.CategoryAxis': ['Source'],
        'DataDetails.DataAxis': ['Data'],
    },
    'QB::Chart::Waterfall': {
        'DataDetails': ['CategoryAxis', 'DataAxis', 'DataLabels'],
        'DataDetails.CategoryAxis': ['Source'],
        'DataDetails.DataAxis': ['Data'],
    },
    'QB::CustomEmail': {
        'EmailSettings': ['Content', 'Subject'],
        'SendOptions': ['TriggerType'],
    },
    'QB::Report::Calendar': {
        'ColorCoding': ['ColorBy'],
    },
    'QB::Report::Kanban': {
        'ColorCoding': ['ColorBy'],
    },
    'QB::Report::Map': {
        'ColorCoding': ['ColorBy'],
    },
    'QB::Report::Table': {
        'ColorCoding': ['ColorBy'],
    },
    'QB::Report::Timeline': {
        'ColorCoding': ['ColorBy'],
    },
    'QB::Table': {
        'DefaultReportSettings': ['ActionOnNewFieldAdd', 'DefaultColorCoding', 'DefaultFilters', 'DefaultSortOrder'],
        'DefaultReportSettings.DefaultColorCoding': ['Appearance', 'ColorBy'],
        'DefaultReportSettings.DefaultFilters': ['AllowQuickSearch', 'DynamicFields'],
        'DefaultReportSettings.DefaultSortOrder': ['SortOrder', 'TargetField'],
        'TableHomePageSettings': ['RoleViews'],
    },
}
