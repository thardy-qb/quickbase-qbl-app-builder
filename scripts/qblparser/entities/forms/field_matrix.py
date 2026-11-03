from typing import Any, Dict, List

from qblparser.utils.helpers import SafeExtractor, TableResolver, extract_fields
from qblparser.utils.property_extractor import PropertyExtractor


def parse_field_to_form_matrix(table_name: str, form_key: str, form_value: Dict[str, Any], field_id_lookup: Dict[str, Any], table_key: str, table_schema, identifier_index=None, app_key="") -> List[Dict[str, Any]]:
    table_info = TableResolver.resolve_from_logical_id(table_key, identifier_index, table_schema, app_key)
    table_id = table_info.get("table_id", "")
    
    form_props = PropertyExtractor(form_value)
    form_name = form_props.name("Unnamed Form")

    field_form_matrix: List[Dict[str, Any]] = []
    sequence_counter = 1

    def append_entries(extracted_fields, context=None):
        nonlocal sequence_counter
        context = context or {}
        page_map = context.get("page", {})
        section_map = context.get("section", {})
        column_map = context.get("column", {})
        element_map = context.get("element", {})
        type_map = context.get("type")

        for field in extracted_fields:
            field_logical = field.get("Field")
            if not field_logical or field_logical == "N/A":
                continue

            parent_path = field.get("Parent Path", [])
            row_key = ""
            if type_map is None:
                page_key = _find_parent_in_path(parent_path, "$FormV2Page_")
                section_key = _find_parent_in_path(parent_path, "$FormV2Section_")
                column_key = _find_parent_in_path(parent_path, "$FormV2Column_")
                element_key = field.get("Element Key", _find_parent_in_path(parent_path, "$FormV2Element_"))
            else:
                page_key = _find_tab_scope(
                    parent_path, field.get("Element Key", ""), context.get("tab_scope", {})
                )
                section_key = _find_parent_of_type(parent_path, type_map, "Section")
                row_key = _find_parent_of_type(parent_path, type_map, "Row")
                column_key = ""
                element_key = field.get("Element Key", "")
            is_pinned = "PinnedSection" in parent_path

            page_key_display = page_key
            page_name = page_map.get(page_key_display, page_key_display)
            if is_pinned and not page_key_display:
                page_key_display = "PinnedSection"
                page_name = page_map.get("PinnedSection", "Pinned Section")
            elif not page_name:
                page_name = page_key_display

            entry = {
                "App Logical ID": app_key or "",
                "Table Logical ID": table_key or "",
                "Table ID": table_id,
                "Table Name": table_name,
                "Form Name": form_name,
                "Form ID": form_props.id(),
                "Form Logical ID": form_key,
                "Field Logical ID": field_logical,
                "Field Label": field.get("Field Label", ""),
                "Field ID": field.get("Field ID", ""),
                "Field Type": field.get("Element Type", "").split("::")[-1] if field.get("Element Type", "") else "",
                "Form Page Logical ID": page_key_display,
                "Form Page Name": page_name,
                "Form Section Logical ID": section_key,
                "Form Section Name": section_map.get(section_key, section_key),
                "Form Column Logical ID": column_key,
                "Form Row Logical ID": row_key,
                "Form Element Logical ID": element_key,
                "Form Element Label": element_map.get(element_key) or field.get("Field Label", "") or element_key,
                "Form Element Type": field.get("Element Type", "").split("::")[-1] if field.get("Element Type", "") else "",
                "Element Order": field.get("Order", ""),
                "Element Depth": field.get("Depth", ""),
                "Form Parent Path": " > ".join([p for p in parent_path if isinstance(p, str)]),
                "Display Sequence": sequence_counter,
            }
            sequence_counter += 1

            field_form_matrix.append(entry)

    if form_key.startswith("$FormV2_"):
        try:
            metadata = _collect_form_v2_metadata(form_value)
            extracted_fields = []
            pinned = form_value.get("PinnedSection")
            if pinned:
                pinned_structure = {
                    "PinnedSection": {
                        "Sections": pinned if isinstance(pinned, dict) else {}
                    }
                }
                extracted_fields.extend(extract_fields(pinned_structure, field_id_lookup=field_id_lookup))
            pages = form_value.get("Pages")
            if isinstance(pages, dict) and pages:
                extracted_fields.extend(extract_fields(pages, field_id_lookup=field_id_lookup))
            layout = form_value.get("Layout")
            if layout:
                extracted_fields.extend(extract_fields(layout, field_id_lookup=field_id_lookup))
            if not extracted_fields:
                extracted_fields = extract_fields(form_value, field_id_lookup=field_id_lookup)
            append_entries(extracted_fields, metadata)
        except Exception as e:
            print(f"Error extracting fields from FormV2 {form_key}: {e}")
    else:
        try:
            elements = form_value.get("Elements", {})
            if isinstance(elements, dict):
                elements_node = elements
            elif isinstance(elements, list):
                elements_node = elements
            else:
                print(f"Warning: Unexpected Elements format in form {form_key}: {type(elements)}")
                elements_node = {}

            extracted_fields = extract_fields(elements_node, field_id_lookup=field_id_lookup)
            append_entries(extracted_fields, context=_collect_legacy_form_metadata(elements_node))
        except Exception as e:
            print(f"Error processing legacy form {form_name}: {e}")

    return field_form_matrix


def _collect_legacy_form_metadata(elements_node):
    metadata = {"page": {}, "section": {}, "column": {}, "element": {}, "type": {}, "tab_scope": {}}

    def walk(node):
        if isinstance(node, list):
            node = {f"element_{i}": item for i, item in enumerate(node) if isinstance(item, dict)}
        if not isinstance(node, dict):
            return
        current_tab = ""
        for key, value in node.items():
            if not isinstance(value, dict):
                continue
            element_type = value.get("Type", "")
            if isinstance(element_type, str) and element_type.startswith("QB::Form::Element::"):
                leaf = element_type.split("::")[-1]
                metadata["type"][key] = leaf
                props = SafeExtractor.get_dict(value, "Properties")
                if leaf == "Section":
                    metadata["section"][key] = _name_or_key(props.get("Heading"), key)
                elif leaf == "Tab":
                    current_tab = key
                    metadata["page"][key] = _name_or_key(props.get("Label"), key)
                if current_tab:
                    metadata["tab_scope"][key] = current_tab
                label = props.get("LabelOverride") or props.get("Label")
                if isinstance(label, str) and label.strip():
                    metadata["element"][key] = label
            walk(value.get("Elements"))

    walk(elements_node)
    return metadata


def _name_or_key(name, key):
    return name if isinstance(name, str) and name.strip() else key


def _find_tab_scope(parent_path, element_key, tab_scope):
    for key in [element_key] + list(reversed(parent_path or [])):
        if isinstance(key, str) and tab_scope.get(key):
            return tab_scope[key]
    return ""


def _find_parent_of_type(parent_path, type_map, wanted):
    if not parent_path:
        return ""
    for key in reversed(parent_path):
        if isinstance(key, str) and type_map.get(key) == wanted:
            return key
    return ""


def _collect_form_v2_metadata(form_value):
    metadata = {
        "page": {},
        "section": {},
        "column": {},
        "element": {},
    }
    metadata["page"]["PinnedSection"] = "Pinned Section"

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, dict):
                    props = SafeExtractor.get_dict(value, "Properties")
                    if key.startswith("$FormV2Page_"):
                        metadata["page"][key] = props.get("Name", key)
                    elif key.startswith("$FormV2Section_"):
                        metadata["section"][key] = props.get("Title", key)
                    elif key.startswith("$FormV2Column_"):
                        metadata["column"][key] = props.get("Title", key)
                    elif key.startswith("$FormV2Element_"):
                        label = props.get("LabelOverride") or props.get("Label") or props.get("Title", "")
                        if not label:
                            field_ref = props.get("Field")
                            if isinstance(field_ref, dict):
                                label = field_ref.get("Field", "")
                        metadata["element"][key] = label or key
                    walk(value)
                elif isinstance(value, list):
                    for item in value:
                        walk(item)

    walk(form_value)
    return metadata


def _find_parent_in_path(parent_path, prefix):
    if not parent_path:
        return ""
    for key in reversed(parent_path):
        if isinstance(key, str) and key.startswith(prefix):
            return key
    return ""
