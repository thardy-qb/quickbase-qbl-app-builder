from qblparser.utils.property_extractor import PropertyExtractor
from qblparser.utils.helpers import SafeExtractor


def _length(value):
    return len(value) if isinstance(value, str) else 0


def parse_document_template(
    dt_key,
    dt_value,
    identifier_index=None,
    table_schema=None,
    app_key="",
    table_key="",
    table_value=None,
    qbl_resources=None,
    **kwargs,
):
    props = PropertyExtractor(dt_value)
    template = SafeExtractor.get_dict(dt_value, "Properties", "Template")
    page_setup = SafeExtractor.get_dict(dt_value, "Properties", "PageSetup")
    margins = SafeExtractor.get_dict(dt_value, "Properties", "Margins")

    table_props = PropertyExtractor(table_value or {})
    table_name = table_props.name("") if table_value else ""

    header = template.get("Header", "")
    footer = template.get("Footer", "")
    content = template.get("Content", "")

    return {
        "App Logical ID": app_key or "",
        "Table Logical ID": table_key or "",
        "Table Name": table_name,
        "Document Template Logical ID": dt_key,
        "Document Template ID": dt_value.get("Id", "") if isinstance(dt_value, dict) else "",
        "Document Template Name": props.name(""),
        "Description": props.description("") or "",
        "Page Size": page_setup.get("Size", ""),
        "Orientation": page_setup.get("Orientation", ""),
        "Page Margins": margins.get("Page", ""),
        "Has Header": "Yes" if _length(header) else "No",
        "Has Footer": "Yes" if _length(footer) else "No",
        "Content Length": _length(content),
    }


