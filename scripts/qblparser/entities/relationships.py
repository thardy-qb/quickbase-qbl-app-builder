import json
import re
from qblparser.utils.property_extractor import PropertyExtractor
from qblparser.utils.helpers import TableResolver, SafeExtractor

def create_empty_relationship_record(app_key, relationship_key, relationship_type):
    return {
        "App Logical ID": app_key,
        "Parent App Logical ID": "",
        "Child App Logical ID": "",
        "Relationship Logical ID": relationship_key,
        "Parent Table Logical ID": "",
        "Parent Table Name": "",
        "Parent Table Alias": "",
        "Child Table Logical ID": "",
        "Child Table Name": "",
        "Child Table Alias": "",
        "Reference Field Logical ID": "",
        "Reference Field ID": "",
        "Reference Field Name": "",
        "Reference Field Type": "",
        "Relationship Type": relationship_type,
        "Cross App": True,
        "Parent Relationship ID": "",
        "Total Reference Fields": 0,
        "Relationship Side": "",
        "Counterpart Relationship Logical ID": "",
    }


def relationship_side(relationship_type):
    text = str(relationship_type or "")
    if text.endswith("Parent"):
        return "Parent"
    if text.endswith("Child"):
        return "Child"
    return ""


def relationship_identity(row):
    parent_table = str(row.get("Parent Table Logical ID") or "")
    parent_relationship = str(row.get("Parent Relationship ID") or "")
    if parent_table and parent_relationship:
        return (str(row.get("Parent App Logical ID") or ""), parent_table, parent_relationship)
    return ("", "", str(row.get("Relationship Logical ID") or ""))


def distinct_relationships(rows):
    chosen = {}
    order = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = relationship_identity(row)
        if key not in chosen:
            order.append(key)
            chosen[key] = row
        elif relationship_side(row.get("Relationship Type")) == "Child" and \
                relationship_side(chosen[key].get("Relationship Type")) != "Child":
            chosen[key] = row
    return [chosen[key] for key in order]


def _resolve_table_identity(app_logical_id, table_logical_id, qbl_resources, identifier_index=None, table_schema=None):
    table_name = ""
    table_alias = ""
    table_id = ""

    if isinstance(qbl_resources, dict):
        app_block = qbl_resources.get("Resources", {}).get(app_logical_id, {})
        table_block = app_block.get("Tables", {}).get(table_logical_id, {}) if isinstance(app_block, dict) else {}
        props = PropertyExtractor(table_block) if isinstance(table_block, dict) else None
        if props:
            table_name = props.name("")
            table_alias = props.get("AliasHint", "")

    if identifier_index and table_schema and app_logical_id and table_logical_id:
        alias = SafeExtractor.get_nested(identifier_index, app_logical_id, "tables", table_logical_id, "id", default="")
        if alias:
            parsed_schema = TableResolver._parse_table_schema(table_schema)
            for table_entry in parsed_schema:
                if isinstance(table_entry, dict) and table_entry.get("alias") == alias:
                    table_id = str(table_entry.get("id", ""))
                    if not table_name:
                        table_name = table_entry.get("name", "")
                    if not table_alias:
                        table_alias = alias
                    break

    return {
        "table_name": table_name,
        "table_alias": table_alias,
        "table_id": table_id,
    }


def _find_reference_fields(child_table_data, relationship_keys):
    if not isinstance(child_table_data, dict):
        return []

    keys = {k for k in relationship_keys if isinstance(k, str) and k}
    if not keys:
        return []

    fields = child_table_data.get("Fields", {})
    exact_matches = []
    prefix_matches = []
    for field_key, field_data in fields.items():
        if not isinstance(field_data, dict):
            continue
        field_props = PropertyExtractor(field_data)
        field_type = field_props.type()
        referenced_relationship = ""

        if field_type == "QB::Field::Reference":
            referenced_relationship = field_props.safe_get("Reference", "Relationship", "Relationship")
        elif field_type == "QB::Field::Lookup":
            referenced_relationship = field_props.safe_get("Lookup", "Relationship", "Relationship")

        if not referenced_relationship:
            continue

        match = {
            "logical_id": field_key,
            "id": field_props.id(),
            "name": field_props.label(),
            "type": field_type,
            "relationship": referenced_relationship,
        }
        if referenced_relationship in keys:
            exact_matches.append(match)
        elif any(referenced_relationship.startswith(k + "_") for k in keys):
            prefix_matches.append(match)

    matches = exact_matches or prefix_matches

    matches.sort(key=lambda m: 0 if m["type"] == "QB::Field::Reference" else 1)
    return matches


def _find_cross_app_child_for_parent(qbl_resources, parent_app_key, parent_table_key,
                                    parent_relationship_key, cross_app_only=True):
    resources = qbl_resources.get("Resources", {}) if isinstance(qbl_resources, dict) else {}
    for child_app_key, child_app_value in resources.items():
        if not isinstance(child_app_value, dict):
            continue
        tables = child_app_value.get("Tables", {})
        for child_table_key, child_table_value in tables.items():
            if not isinstance(child_table_value, dict):
                continue
            relationships = child_table_value.get("Relationships", {})
            for child_relationship_key, child_relationship_value in relationships.items():
                if not isinstance(child_relationship_value, dict):
                    continue
                rel_type = child_relationship_value.get("Type", "")
                if cross_app_only:
                    if "CrossAppChild" not in rel_type:
                        continue
                elif "Child" not in rel_type:
                    continue
                parent_ref = child_relationship_value.get("Properties", {}).get("Parent", {})
                if not isinstance(parent_ref, dict):
                    continue
                app_matches = (
                    parent_ref.get("App") == parent_app_key
                    if "App" in parent_ref
                    else child_app_key == parent_app_key
                )
                if (
                    app_matches
                    and parent_ref.get("Table") == parent_table_key
                    and parent_ref.get("Relationship") == parent_relationship_key
                ):
                    return {
                        "child_app_key": child_app_key,
                        "child_table_key": child_table_key,
                        "child_table_value": child_table_value,
                        "child_relationship_key": child_relationship_key,
                    }
    return {}


def parse_relationship(app_key, app_value, relationship_key, relationship_value, table_schema=None, identifier_index=None, table_key=None, qbl_resources=None):
    
    if isinstance(relationship_value, str):
        return create_empty_relationship_record(app_key, relationship_key, "Cross-App (String)")

    properties = relationship_value.get("Properties", {})
    if isinstance(properties, dict):
        parent = properties.get("Parent", {})
        if isinstance(parent, dict) and parent.get("__bad_ref__"):
            return create_empty_relationship_record(app_key, relationship_key, "Bad Reference")

    if isinstance(table_schema, str):
        table_schema = json.loads(table_schema)

    if not isinstance(qbl_resources, dict):
        qbl_resources = {"Resources": {app_key: app_value}}

    rel_props = PropertyExtractor(relationship_value)

    relationship_type = rel_props.type()
    parent_relationship = rel_props.get("Parent", {})

    child_app_logical = app_key
    child_table_logical = table_key or ""
    if not child_table_logical:
        for candidate_table_key, candidate_table_value in app_value.get("Tables", {}).items():
            relationships = candidate_table_value.get("Relationships", {})
            if relationship_key in relationships:
                child_table_logical = candidate_table_key
                break

    parent_app_logical = app_key
    parent_table_logical = parent_relationship.get("Table", "")
    parent_relationship_id = parent_relationship.get("Relationship", "")
    reference_relationship_keys = [relationship_key]
    counterpart_relationship = parent_relationship_id

    child_table_data = app_value.get("Tables", {}).get(child_table_logical, {})

    if "CrossAppChild" in relationship_type:
        parent_app_logical = parent_relationship.get("App", "") or app_key
        parent_table_logical = parent_relationship.get("Table", "")
        parent_relationship_id = parent_relationship.get("Relationship", "")
        counterpart_relationship = parent_relationship_id

    elif "CrossAppParent" in relationship_type:
        parent_app_logical = app_key
        parent_table_logical = child_table_logical
        parent_relationship_id = relationship_key
        counterpart_relationship = ""
        link = _find_cross_app_child_for_parent(
            qbl_resources,
            parent_app_logical,
            parent_table_logical,
            relationship_key,
        )
        if link:
            child_app_logical = link.get("child_app_key", child_app_logical)
            child_table_logical = link.get("child_table_key", child_table_logical)
            child_table_data = link.get("child_table_value", child_table_data)
            child_relationship_key = link.get("child_relationship_key", "")
            if child_relationship_key:
                reference_relationship_keys = [child_relationship_key]
                counterpart_relationship = child_relationship_key

    elif relationship_type.endswith("::Parent"):
        parent_app_logical = app_key
        parent_table_logical = child_table_logical
        parent_relationship_id = relationship_key
        child_table_logical = ""
        child_table_data = {}
        counterpart_relationship = ""
        link = _find_cross_app_child_for_parent(
            qbl_resources,
            parent_app_logical,
            parent_table_logical,
            relationship_key,
            cross_app_only=False,
        )
        if link:
            child_app_logical = link.get("child_app_key", child_app_logical)
            child_table_logical = link.get("child_table_key", "")
            child_table_data = link.get("child_table_value", {})
            child_relationship_key = link.get("child_relationship_key", "")
            if child_relationship_key:
                reference_relationship_keys = [child_relationship_key]
                counterpart_relationship = child_relationship_key

    parent_table_info = _resolve_table_identity(
        parent_app_logical,
        parent_table_logical,
        qbl_resources,
        identifier_index=identifier_index,
        table_schema=table_schema,
    )
    child_table_info = _resolve_table_identity(
        child_app_logical,
        child_table_logical,
        qbl_resources,
        identifier_index=identifier_index,
        table_schema=table_schema,
    )

    reference_fields = _find_reference_fields(child_table_data, reference_relationship_keys)
    primary_ref_field = reference_fields[0] if reference_fields else {}

    cross_app = bool(rel_props.get("CrossApp", False) or ("CrossApp" in relationship_type))

    return {
        "App Logical ID": app_key,
        "Parent App Logical ID": parent_app_logical,
        "Child App Logical ID": child_app_logical,
        "Relationship Logical ID": relationship_key,
        "Parent Table Logical ID": parent_table_logical,
        "Parent Table Name": parent_table_info.get("table_name", ""),
        "Parent Table Alias": parent_table_info.get("table_alias", ""),
        "Child Table Logical ID": child_table_logical,
        "Child Table Name": child_table_info.get("table_name", ""),
        "Child Table Alias": child_table_info.get("table_alias", ""),
        "Reference Field Logical ID": primary_ref_field.get("logical_id", ""),
        "Reference Field ID": primary_ref_field.get("id", ""),
        "Reference Field Name": primary_ref_field.get("name", ""),
        "Reference Field Type": primary_ref_field.get("type", ""),
        "Relationship Type": relationship_type,
        "Cross App": cross_app,
        "Parent Relationship ID": parent_relationship_id,
        "Total Reference Fields": len(reference_fields),
        "Relationship Side": relationship_side(relationship_type),
        "Counterpart Relationship Logical ID": counterpart_relationship,
    }


