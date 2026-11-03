from qblparser.utils.property_extractor import PropertyExtractor
from qblparser.utils.helpers import SafeExtractor
from qblparser.utils.role_defaults import collect_role_default_references

def parse_page_metadata(page_key, page_value, identifier_index=None, app_key="", pages_node=None, **kwargs):
    props = PropertyExtractor(page_value)
    page_type = page_value.get("Type", "")
    page_role_defaults = SafeExtractor.get_dict(pages_node or {}, "Properties").get("RoleDefaults", {})
    assigned_page_ids = collect_role_default_references(page_role_defaults, ("$Page_",))
    role_permissions = props.get("RolePermissions", {})
    mapped_to_role_permissions = "Yes" if isinstance(role_permissions, dict) and bool(role_permissions) else "No"
    assigned_to_role_homepage = "Yes" if page_key in assigned_page_ids else "No"
    
    base_metadata = {
        "App Logical ID": app_key or "",
        "Page Logical ID": page_key,
        "Page ID": props.id(),
        "Page Name": props.name(),
        "Page Type": page_type.split("::")[-1] if page_type else "",
        "Assigned to Role Homepage": assigned_to_role_homepage,
        "Mapped to Role Permissions": mapped_to_role_permissions,
        "Used by Roles": "Yes" if "Yes" in (assigned_to_role_homepage, mapped_to_role_permissions) else "No",
    }
    
    if page_type == 'QB::HomePage':
        base_metadata.update({
            "Has Sidebar": 'Sidebar' in page_value,
            "Has Main Section": 'MainSection' in page_value,
            "Total Widgets": _count_widgets(page_value)
        })
    elif page_type == 'QB::CodePage':
        raw_code = props.safe_get("RawCode", default="")
        if not isinstance(raw_code, str):
            raw_code = ""
        base_metadata.update({
            "Has Code": bool(raw_code),
            "Code Length": int(len(raw_code))
        })
    elif page_type == 'QB::RichTextPage':
        raw_text = props.safe_get("RawText", default="")
        if not isinstance(raw_text, str):
            raw_text = ""
        base_metadata.update({
            "Has Text": bool(raw_text),
            "Text Length": int(len(raw_text))
        })
    return base_metadata


def parse_guide_metadata(guide_key, guide_value, identifier_index=None, app_key="", **kwargs):
    props = PropertyExtractor(guide_value)
    links_to = props.safe_get("LinksTo", default="")

    return {
        "App Logical ID": app_key or "",
        "Guide Logical ID": guide_key,
        "Title": props.safe_get("Title", default=""),
        "Description": props.safe_get("Description", default=""),
        "Links To Page": _reference_target(links_to, "Page"),
    }


PAGE_SECTIONS = ("MainSection", "Sidebar")

_WIDGET_TARGETS = (
    ("Report", "Report"),
    ("SearchReport", "Report"),
    ("SearchTable", "Table"),
    ("TargetField", "Field"),
)


def parse_page_widgets(page_key, page_value, app_key="", **kwargs):
    props = PropertyExtractor(page_value)
    page_name = props.name()
    rows = []

    for section in PAGE_SECTIONS:
        container = page_value.get(section)
        if not isinstance(container, dict):
            continue
        for row_order, (row_key, row_value) in enumerate(container.items(), start=1):
            if not isinstance(row_value, dict):
                continue
            widgets = row_value.get("Widgets")
            if not isinstance(widgets, dict):
                continue
            for widget_order, (widget_key, widget_value) in enumerate(widgets.items(), start=1):
                if not isinstance(widget_value, dict):
                    continue
                rows.extend(_widget_rows(
                    app_key, page_key, page_name, section, row_key, row_order,
                    widget_order, widget_key, widget_value, parent="",
                ))
    return rows


def _widget_rows(app_key, page_key, page_name, section, row_key, row_order,
                 widget_order, widget_key, widget_value, parent):
    props = PropertyExtractor(widget_value)
    widget_type = str(widget_value.get("Type", ""))

    points_at = ""
    for prop, reference_key in _WIDGET_TARGETS:
        target = _reference_target(props.safe_get(prop, default=""), reference_key)
        if isinstance(target, str) and target.startswith("$"):
            points_at = target
            break

    rows = [{
        "App Logical ID": app_key or "",
        "Page Logical ID": page_key,
        "Page Name": page_name,
        "Section": section,
        "Row Logical ID": row_key,
        "Row Order": row_order,
        "Widget Order": widget_order,
        "Widget Logical ID": widget_key,
        "Widget Type": widget_type.split("::")[-1] if widget_type else "",
        "Parent Widget Logical ID": parent,
        "Title": props.safe_get("Title", default="") or "",
        "Width": props.safe_get("Width", default="") or "",
        "Points At": points_at,
        "Url": props.safe_get("Url", default="") or "",
    }]

    for container_key, children in widget_value.items():
        if container_key in ("Type", "Properties", "Id") or not isinstance(children, dict):
            continue
        for child_order, (child_key, child_value) in enumerate(children.items(), start=1):
            if not isinstance(child_value, dict) or "Type" not in child_value:
                continue
            rows.extend(_widget_rows(
                app_key, page_key, page_name, section, row_key, row_order,
                child_order, child_key, child_value, parent=widget_key,
            ))
    return rows


def _reference_target(value, key):
    if isinstance(value, dict):
        target = value.get(key)
        return target if isinstance(target, str) else ""
    return value if isinstance(value, str) else ""

def _count_widgets(page_data):
    count = 0
    for section_name in ['Sidebar', 'MainSection']:
        section = page_data.get(section_name, {})
        for row_key, row_data in section.items():
            if isinstance(row_data, dict):
                widgets = row_data.get('Widgets', {})
                count += int(len(widgets))
    return int(count)
