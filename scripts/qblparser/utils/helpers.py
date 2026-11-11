import re
import json
import yaml
from collections import defaultdict
from typing import Any, Dict, List, Optional, Union, Callable

from qblparser.utils.qbl_tags import scalar_ref_value


class SafeExtractor:
    
    @staticmethod
    def get_nested(data: Any, *keys: str, default: Any = "") -> Any:
        current = data
        try:
            for key in keys:
                if isinstance(current, dict):
                    current = current.get(key, {})
                elif hasattr(current, key):
                    current = getattr(current, key, {})
                else:
                    return default
                    
                if current is None:
                    return default
            return current if current != {} else default
        except (AttributeError, KeyError, TypeError):
            return default
    
    @staticmethod
    def get_list(data: Any, *keys: str, default: Optional[List] = None) -> List:
        if default is None:
            default = []
        result = SafeExtractor.get_nested(data, *keys, default=default)
        return result if isinstance(result, list) else default
    
    @staticmethod
    def get_dict(data: Any, *keys: str, default: Optional[Dict] = None) -> Dict:
        if default is None:
            default = {}
        result = SafeExtractor.get_nested(data, *keys, default=default)
        return result if isinstance(result, dict) else default


class FieldExtractor:
    
    FIELD_PATTERNS = [
        r'\[([^\]]+)\]',
        r'(\$Field_[A-Za-z0-9_]+)',
    ]

    QUERY_FIELD_PATTERN = r"\{\s*'?(\d+)'?\s*\."

    @classmethod
    def from_query_criteria(cls, criteria: Any) -> List[str]:
        if not isinstance(criteria, str) or not criteria.strip():
            return []
        if criteria.strip() == "Default":
            return []

        found = []
        for field_id in re.findall(cls.QUERY_FIELD_PATTERN, criteria):
            if field_id not in found:
                found.append(field_id)
        return found

    @classmethod
    def from_reference(cls, field_ref: Any) -> str:
        if isinstance(field_ref, str):
            return field_ref if field_ref.startswith("$Field_") else ""

        scalar = scalar_ref_value(field_ref)
        if scalar:
            return scalar if scalar.startswith("$Field_") else ""

        if isinstance(field_ref, dict):
            field_val = field_ref.get("Field", "")
            if isinstance(field_val, str):
                return field_val if field_val.startswith("$Field_") else ""
            elif isinstance(field_val, dict):
                return cls.from_reference(field_val)

        return ""
    
    @classmethod
    def from_formula(cls, formula: Union[str, Any]) -> List[str]:
        if not isinstance(formula, str) or not formula.strip():
            return []
        
        referenced_fields = []
        for pattern in cls.FIELD_PATTERNS:
            try:
                matches = re.findall(pattern, formula)
                referenced_fields.extend(matches)
            except Exception:
                continue
        
        return [ref for ref in referenced_fields 
                if isinstance(ref, str) and (ref.startswith("$Field_") or ref)]
    
    @classmethod
    def from_grouping(cls, group_by: Any) -> List[str]:
        entries: List[Any]
        if isinstance(group_by, list):
            entries = list(group_by)
        elif isinstance(group_by, dict):
            entries = [group_by]
        else:
            return []

        fields = []
        for entry in entries:
            field_ref = cls.from_reference(entry)
            if field_ref:
                fields.append(field_ref)
                continue

            for nested in SafeExtractor.get_list(entry, "GroupBy"):
                nested_ref = cls.from_reference(nested)
                if nested_ref:
                    fields.append(nested_ref)

        return fields


_FIELD_NAMING_KEYS = ("Field", "Source")

_SCALAR_FIELD_KEYS = (
    "StartDate", "EndDate", "StartField", "EndField", "Milestone",
    "AddressField", "GroupBy", "DisplayFields", "DynamicFields", "Bars",
)

_QUERY_KEYS = ("Criteria",)

_FIELD_PREFIX = "$Field_"


def report_field_uses(node, path="", field_ids=None):
    if isinstance(node, dict):
        for key, value in node.items():
            child = path if key == "Properties" else (f"{path}.{key}" if path else key)
            if key in _FIELD_NAMING_KEYS and isinstance(value, str) and value.startswith(_FIELD_PREFIX):
                yield value, path or key
            elif key in _SCALAR_FIELD_KEYS and isinstance(value, str) and value.startswith(_FIELD_PREFIX):
                yield value, child
            elif key in _QUERY_KEYS and field_ids:
                for field_id in FieldExtractor.from_query_criteria(value):
                    logical_id = field_ids.get(field_id)
                    if logical_id:
                        yield logical_id, child
            else:
                yield from report_field_uses(value, child, field_ids)
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, str) and item.startswith(_FIELD_PREFIX):
                yield item, path
            else:
                yield from report_field_uses(item, path, field_ids)


class ElementTraverser:
    
    NESTED_KEYS = [
        "Elements", "Sections", "Columns", "Pages", "PinnedSection", "Widgets",
        "Tabs", "Items", "Children", "Components"
    ]
    
    SPECIAL_KEYS = ["Layout", "Form"]
    
    def __init__(self, processor_func: Callable):
        self.processor_func = processor_func
        self.processed_keys = set()
        self.results = []
    
    def traverse(self, elements: Any, parent_path: Optional[List[str]] = None, depth: int = 0):
        if parent_path is None:
            parent_path = []
        
        if isinstance(elements, list):
            elements = {f"element_{i}": el for i, el in enumerate(elements) 
                       if isinstance(el, dict)}
        
        if not isinstance(elements, dict):
            return
        
        for element_key, element_value in elements.items():
            if not isinstance(element_value, dict):
                continue
            
            element_full_key = ".".join(parent_path + [element_key]) if parent_path else element_key
            if element_full_key in self.processed_keys:
                continue
            self.processed_keys.add(element_full_key)
            
            current_parent_path = list(parent_path)
            
            processed_element = self.processor_func(element_key, element_value, current_parent_path, depth)
            if processed_element:
                self.results.append(processed_element)
            
            self._traverse_nested(element_value, current_parent_path + [element_key], depth)
    
    def _traverse_nested(self, element_value: Dict, current_path: List[str], depth: int):
        for nested_key in self.NESTED_KEYS:
            nested_elements = element_value.get(nested_key)
            if nested_elements:
                self.traverse(nested_elements, parent_path=current_path, depth=depth + 1)
        
        for special_key in self.SPECIAL_KEYS:
            if special_key in element_value:
                special_value = element_value[special_key]
                if isinstance(special_value, dict):
                    self.traverse(special_value, 
                                parent_path=current_path + [special_key], 
                                depth=depth + 1)
    
    def get_results(self) -> List[Dict]:
        return self.results


class TableResolver:
    
    @staticmethod
    def _parse_table_schema(table_schema: Any) -> List[Dict]:
        if not table_schema:
            return []
        
        if isinstance(table_schema, str):
            try:
                return json.loads(table_schema)
            except json.JSONDecodeError:
                print("Warning: Could not parse table schema JSON")
                return []
        
        if isinstance(table_schema, list):
            return table_schema
        
        print(f"Warning: Unexpected table schema format: {type(table_schema)}")
        return []

    @classmethod
    def get_schema_entry(
        cls,
        table_schema: Any,
        table_id: str = "",
        table_alias: str = "",
        table_name: str = "",
    ) -> Dict[str, Any]:
        parsed_schema = cls._parse_table_schema(table_schema)
        if not parsed_schema:
            return {}

        normalized_table_id = str(table_id).strip() if table_id is not None else ""
        normalized_alias = str(table_alias).strip() if table_alias is not None else ""
        normalized_name = str(table_name).strip() if table_name is not None else ""

        if normalized_table_id:
            for table_entry in parsed_schema:
                if not isinstance(table_entry, dict):
                    continue
                if str(table_entry.get("id", "")).strip() == normalized_table_id:
                    return table_entry

        alias_matches = []
        if normalized_alias:
            alias_matches = [
                table_entry
                for table_entry in parsed_schema
                if isinstance(table_entry, dict)
                and str(table_entry.get("alias", "")).strip() == normalized_alias
            ]
            if len(alias_matches) == 1:
                return alias_matches[0]

        if normalized_name:
            name_matches = [
                table_entry
                for table_entry in parsed_schema
                if isinstance(table_entry, dict)
                and str(table_entry.get("name", "")).strip() == normalized_name
            ]
            if len(name_matches) == 1:
                return name_matches[0]

        if alias_matches:
            return alias_matches[0]

        return {}
    
    @classmethod
    def resolve_from_logical_id(cls, table_logical_id: str, identifier_index: Optional[Dict] = None,
                               table_schema: Any = None, app_logical_id: str = "") -> Dict[str, str]:
        if not table_logical_id:
            return {"table_id": "", "table_name": "", "table_logical_id": ""}
        
        if not identifier_index:
            return {"table_id": "", "table_name": "", "table_logical_id": table_logical_id}
        
        table_alias = ""
        table_id = ""

        app_candidates = []
        if app_logical_id and app_logical_id in identifier_index:
            app_candidates.append((app_logical_id, identifier_index.get(app_logical_id, {})))
        app_candidates.extend(
            (app_key, app_data)
            for app_key, app_data in identifier_index.items()
            if not app_logical_id or app_key != app_logical_id
        )

        for _, app_data in app_candidates:
            if isinstance(app_data, dict) and "tables" in app_data:
                tables = app_data.get("tables", {})
                if table_logical_id in tables:
                    table_info = tables[table_logical_id]
                    if isinstance(table_info, dict):
                        table_alias = table_info.get("id", "")
                        break
        
        if table_alias and table_schema:
            parsed_schema = cls._parse_table_schema(table_schema)
            for table_entry in parsed_schema:
                if isinstance(table_entry, dict) and table_entry.get("alias") == table_alias:
                    table_id = str(table_entry.get("id", ""))
                    break
        
        table_name = ""
        if table_id and table_schema:
            table_name = cls._get_table_name_from_schema(table_id, table_schema)
        
        return {
            "table_id": table_id,
            "table_name": table_name,
            "table_logical_id": table_logical_id,
            "table_alias": table_alias
        }
    
    @classmethod
    def resolve_from_table_id(cls, table_id: str, identifier_index: Optional[Dict] = None,
                             table_schema: Any = None) -> Dict[str, str]:
        if not table_id:
            return {"table_id": "", "table_name": "", "table_logical_id": ""}
        
        table_name = cls._get_table_name_from_schema(table_id, table_schema) if table_schema else ""
        
        table_logical_id = ""
        table_alias = ""
        
        if identifier_index and table_schema:
            parsed_schema = cls._parse_table_schema(table_schema)
            for table_entry in parsed_schema:
                if isinstance(table_entry, dict) and str(table_entry.get("id", "")) == str(table_id):
                    table_alias = table_entry.get("alias", "")
                    break
            
            if table_alias:
                for app_key, app_data in identifier_index.items():
                    if isinstance(app_data, dict) and "tables" in app_data:
                        tables = app_data.get("tables", {})
                        for logical_id, table_info in tables.items():
                            if isinstance(table_info, dict) and table_info.get("id") == table_alias:
                                table_logical_id = logical_id
                                break
                        if table_logical_id:
                            break
        
        return {
            "table_id": table_id,
            "table_name": table_name,
            "table_logical_id": table_logical_id,
            "table_alias": table_alias
        }
    
    @classmethod
    def _get_table_name_from_schema(cls, table_id: str, table_schema: Any) -> str:
        if not table_schema or not table_id:
            return ""
        
        parsed_schema = cls._parse_table_schema(table_schema)
        table_id_str = str(table_id)
        
        for table_entry in parsed_schema:
            if isinstance(table_entry, dict) and str(table_entry.get("id", "")) == table_id_str:
                return table_entry.get("name", "")
        
        return ""
    
    @classmethod
    def resolve_complete_info(cls, table_logical_id: Optional[str] = None,
                             table_id: Optional[str] = None, identifier_index: Optional[Dict] = None,
                             table_schema: Any = None, app_logical_id: str = "") -> Dict[str, str]:
        if table_logical_id:
            return cls.resolve_from_logical_id(table_logical_id, identifier_index, table_schema, app_logical_id)
        elif table_id:
            return cls.resolve_from_table_id(table_id, identifier_index, table_schema)
        else:
            return {"table_id": "", "table_name": "", "table_logical_id": "", "table_alias": ""}

    @classmethod
    def resolve_field_id(cls, table_logical_id: str, field_logical_id: str,
                         identifier_index: Optional[Dict] = None, app_logical_id: str = "") -> str:
        if not identifier_index or not table_logical_id or not field_logical_id:
            return ""

        try:
            app_candidates = []
            if app_logical_id and app_logical_id in identifier_index:
                app_candidates.append(identifier_index.get(app_logical_id, {}))
            app_candidates.extend(
                app_data
                for key, app_data in identifier_index.items()
                if not app_logical_id or key != app_logical_id
            )

            for app_data in app_candidates:
                elements = SafeExtractor.get_nested(
                    app_data, "tables", table_logical_id, "elements", default={}
                )
                field_info = SafeExtractor.get_dict(elements, field_logical_id)
                if isinstance(field_info, dict):
                    field_id = field_info.get("id")
                    if field_id:
                        return str(field_id)
        except Exception as exc:
            print(f"Warning: Failed resolving field ID for {field_logical_id}: {exc}")

        return ""


def extract_fields(elements: Any, field_id_lookup: Optional[Dict] = None) -> List[Dict]:
    field_id_lookup = field_id_lookup or {}
    
    def process_element(element_key: str, element_value: Dict, parent_path: Optional[List[str]], depth: int) -> Optional[Dict]:
        properties = SafeExtractor.get_dict(element_value, "Properties")
        element_type = element_value.get("Type", "")
        parent_key = parent_path[-1] if parent_path else None
        
        field_ref_raw = properties.get("Field", {})
        field_ref = FieldExtractor.from_reference(field_ref_raw)
        field_label = properties.get("LabelOverride") or properties.get("Label", "")
        if field_ref:
            lookup_entry = field_id_lookup.get(field_ref, {})
            if isinstance(lookup_entry, dict):
                fallback_label = lookup_entry.get("Label") or lookup_entry.get("Name", "")
                if not field_label or (isinstance(field_label, str) and field_label.startswith("$Field_")):
                    field_label = fallback_label or field_label
        if (not field_label or (isinstance(field_label, str) and not field_label.strip())) and isinstance(field_ref_raw, dict):
            field_label = field_ref_raw.get("Field", "")
        
        return {
            "Field": field_ref or "N/A",
            "Field ID": SafeExtractor.get_nested(field_id_lookup, field_ref, "Id", default=""),
            "Element Key": element_key,
            "Element Type": element_type,
            "Parent Key": parent_key,
            "Field Label": field_label,
            "Parent Path": list(parent_path) if parent_path else [],
            "Order": properties.get("Order", float('inf')),
            "Depth": depth,
        }
    
    traverser = ElementTraverser(process_element)
    traverser.traverse(elements)
    results = traverser.get_results()
    for idx, item in enumerate(results, start=1):
        order_val = item.get("Order")
        if order_val in (None, "", float("inf")):
            item["Order"] = idx
    return results


def unknown_tag_constructor(loader, tag_suffix, node):
    from qblparser.utils.qbl_yaml import _unknown_tag_constructor

    return _unknown_tag_constructor(loader, tag_suffix, node)
