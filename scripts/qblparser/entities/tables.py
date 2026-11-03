from qblparser.utils.helpers import TableResolver
from qblparser.utils.property_extractor import PropertyExtractor
from typing import List, Dict, Any

def parse_table(table_key, table_value, identifier_index, table_schema=None, app_key=""):
    
    props = PropertyExtractor(table_value)
    table_name = props.name("Unknown Table")
    table_alias = props.get("AliasHint", "")

    table_info = TableResolver.resolve_from_logical_id(table_key, identifier_index, table_schema, app_key)
    table_id = table_info.get("table_id", "")
    schema_entry = TableResolver.get_schema_entry(
        table_schema,
        table_id=table_id,
        table_alias=table_alias,
        table_name=table_name,
    )
    if schema_entry and not table_id:
        table_id = str(schema_entry.get("id", "")).strip()
    
    table_data = {
        "App Logical ID": app_key or "",
        "Table Logical ID": table_key,
        "Table ID": table_id or None,
        "Table Name": table_name,
        "Table Alias": table_alias,
        "updated": schema_entry.get("updated", ""),
        "keyFieldId": schema_entry.get("keyFieldId", ""),
        "sizeLimit": schema_entry.get("sizeLimit", ""),
        "spaceUsed": schema_entry.get("spaceUsed", ""),
        "spaceRemaining": schema_entry.get("spaceRemaining", ""),
        "Custom Data Rule": props.safe_get("CustomDataRules", "Formula", default="N/A"),
        "Custom Data Rule Enabled?": "TRUE" if props.safe_get("CustomDataRules", "TurnedOn") else "FALSE",
        "Table Description": props.description("N/A"),
    }

    return table_data


