import json
from qblparser.utils.property_extractor import PropertyExtractor
from qblparser.utils.helpers import TableResolver, SafeExtractor


def parse_connected_table(
    ct_key,
    ct_value,
    identifier_index=None,
    table_schema=None,
    app_key="",
    connected_data=None,
    qbl_resources=None,
    **kwargs,
):
    if connected_data:
        context = _build_connected_context(
            app_key, ct_key, ct_value, connected_data, identifier_index, table_schema, qbl_resources
        )

        schedule = context["schedule"]
        ds_info = context["data_source_info"]

        return {
            "App Logical ID": context["app_key"],
            "Connected Table Logical ID": context["table_key"],
            "Connected Table Name": context["table_name"],
            "Connected Table ID": context["table_id"],
            "Table Alias": context["table_alias"],
            "Description": context["description"],
            "Connected?": "Yes" if context["connected"] else "No",
            "Update Mode": context["update_mode"],
            "Schedule Cron": schedule.get("CronTab", ""),
            "Notify On Failure": "Yes" if schedule.get("NotifyOnFailure") else "No",
            "Data Filter": context["data_filter"] or "None",
            "Field Map Count": context["field_map_count"],
            "Key Fields": ", ".join(context["key_field_names"]) or "None",
            "Data Source Logical ID": context["data_source_id"],
            "Data Source Type": ds_info.get("data_source_type", ""),
            "Data Source Owner": ds_info.get("owner", ""),
            "Connection Param/Id": ds_info.get("connection_id", ""),
            "Data Source Placeholder?": "Yes" if ds_info.get("is_placeholder") else "No",
            "Record Set Logical ID": context["record_set_id"],
            "Record Set External ID": ds_info.get("record_set_external_id", ""),
            "Record Set Type": ds_info.get("record_set_type", ""),
        }

    return _parse_legacy_connected_table(ct_key, ct_value, identifier_index, table_schema)


def parse_connected_table_fields(
    ct_key,
    ct_value,
    identifier_index=None,
    table_schema=None,
    app_key="",
    connected_data=None,
    qbl_resources=None,
    **kwargs,
):
    if connected_data:
        context = _build_connected_context(
            app_key, ct_key, ct_value, connected_data, identifier_index, table_schema, qbl_resources
        )

        records = []
        columns = context["record_set_columns"]
        table_fields = context["table_fields"]

        for idx, (field_logical_id, mapping) in enumerate(context["field_map"].items(), start=1):
            mapping = mapping or {}
            connected_column_id = mapping.get("ConnectedColumn", "")

            field_info = table_fields.get(field_logical_id, {})
            field_props = PropertyExtractor(field_info)

            column_info = columns.get(connected_column_id, {})
            column_props = SafeExtractor.get_dict(column_info, "Properties")

            records.append({
                "App Logical ID": context["app_key"],
                "Mapping #": idx,
                "Connected Table Logical ID": context["table_key"],
                "Connected Table Name": context["table_name"],
                "Connected Table ID": context["table_id"],
                "Table Field Logical ID": field_logical_id,
                "Table Field Name": field_props.label(""),
                "Table Field ID": field_info.get("Id", ""),
                "Table Field Type": field_info.get("Type", ""),
                "Connected Column Logical ID": connected_column_id,
                "Connected Column Name": column_props.get("Name", ""),
                "Connected Column ID": column_info.get("Id", ""),
                "Connected Column Type": column_info.get("Type", ""),
                "Record Set Logical ID": context["record_set_id"],
                "Record Set External ID": context["data_source_info"].get("record_set_external_id", ""),
            })

        return records

    return _parse_legacy_connected_table_fields(ct_key, ct_value, identifier_index, table_schema)


def parse_connected_table_matrix(
    qbl_data=None,
    identifier_index=None,
    table_schema=None,
    app_key="",
    connected_entries=None,
    qbl_resources=None,
):
    matrix_records = []
    qbl_resources = qbl_resources or qbl_data

    if connected_entries is None:
        connected_entries = _collect_connected_entries_from_qbl(qbl_data or {})

    for entry in connected_entries:
        try:
            context = _build_connected_context(
                entry.get("app_key", app_key),
                entry["table_key"],
                entry["table_value"],
                entry["connected_data"],
                identifier_index,
                table_schema,
                qbl_resources,
            )
        except Exception as exc:
            print(f"Error parsing connected table matrix for {entry['table_key']}: {exc}")
            continue

        ds_info = context["data_source_info"]

        matrix_records.append({
            "App Logical ID": context["app_key"],
            "Connected Table Logical ID": context["table_key"],
            "Connected Table Name": context["table_name"],
            "Connected Table ID": context["table_id"],
            "Table Alias": context["table_alias"],
            "Data Source Logical ID": context["data_source_id"],
            "Record Set Logical ID": context["record_set_id"],
            "Record Set External ID": ds_info.get("record_set_external_id", ""),
            "Data Source Owner": ds_info.get("owner", ""),
            "Data Source Placeholder?": "Yes" if ds_info.get("is_placeholder") else "No",
            "Field Map Count": context["field_map_count"],
            "Update Mode": context["update_mode"],
        })

    matrix_records.sort(key=lambda x: (x["Connected Table Name"], x["Connected Table Logical ID"]))

    return matrix_records


def _build_connected_context(app_key, table_key, table_value, connected_data, identifier_index, table_schema, qbl_resources):
    connected_data = connected_data or {}
    table_props = PropertyExtractor(table_value)

    table_info = TableResolver.resolve_complete_info(
        table_logical_id=table_key,
        identifier_index=identifier_index,
        table_schema=table_schema,
    ) if table_schema or identifier_index else {}

    table_name = table_props.name(table_info.get("table_name", ""))
    table_alias = table_props.get("AliasHint", table_info.get("table_alias", ""))

    data_source_ref = SafeExtractor.get_dict(connected_data, "DataSource")
    data_source_id = data_source_ref.get("DataSource", "")
    record_set_id = data_source_ref.get("RecordSet", "")

    ds_info = _resolve_data_source_metadata(
        data_source_id,
        record_set_id,
        qbl_resources or {},
    )
    record_set_columns = ds_info.pop("columns", {})

    field_map = SafeExtractor.get_dict(connected_data, "FieldMap")
    key_field_names = _resolve_key_field_names(connected_data.get("KeyFields", []), table_value.get("Fields", {}))

    return {
        "app_key": app_key or "",
        "table_key": table_key,
        "table_value": table_value,
        "table_name": table_name or "Connected Table",
        "table_id": table_info.get("table_id", ""),
        "table_alias": table_alias,
        "description": table_props.description(""),
        "connected": bool(connected_data.get("Connected", False)),
        "update_mode": connected_data.get("UpdateMode", ""),
        "schedule": SafeExtractor.get_dict(connected_data, "Schedule"),
        "data_filter": connected_data.get("DataFilter", ""),
        "field_map": field_map,
        "field_map_count": len(field_map),
        "key_field_names": key_field_names,
        "data_source_id": data_source_id,
        "record_set_id": record_set_id,
        "data_source_info": ds_info,
        "record_set_columns": record_set_columns,
        "table_fields": table_value.get("Fields", {}),
    }


def _resolve_data_source_metadata(data_source_id, record_set_id, qbl_resources):
    info = {
        "data_source_type": "",
        "owner": "",
        "is_placeholder": False,
        "connection_id": "",
        "record_set_type": "",
        "record_set_external_id": "",
        "columns": {},
    }

    external_resources = (qbl_resources or {}).get("ExternalResources", {})
    resource_entry = external_resources.get(data_source_id, {})

    if resource_entry:
        info["data_source_type"] = resource_entry.get("Type", "")
        props = SafeExtractor.get_dict(resource_entry, "Properties")
        info["owner"] = props.get("Owner", "")
        info["is_placeholder"] = props.get("IsPlaceholder", False)
        info["connection_id"] = _stringify_ref_value(props.get("ConnectionId", ""))

        recordsets = resource_entry.get("RecordSets", {})
        recordset_entry = recordsets.get(record_set_id, {})
        info["record_set_type"] = recordset_entry.get("Type", "")
        rs_props = SafeExtractor.get_dict(recordset_entry, "Properties")
        info["record_set_external_id"] = _stringify_ref_value(rs_props.get("ExternalSetId", ""))
        info["columns"] = recordset_entry.get("Columns", {})

    return info


def _stringify_ref_value(value):
    if isinstance(value, dict):
        if "Name" in value and len(value) == 1:
            return value["Name"]
        if "Field" in value and len(value) == 1:
            return value["Field"]
        if "Table" in value and len(value) == 1:
            return value["Table"]
        try:
            return json.dumps(value)
        except Exception:
            return str(value)
    if isinstance(value, (list, tuple)):
        return ", ".join(str(_stringify_ref_value(v)) for v in value)
    return value


def _resolve_key_field_names(key_field_refs, table_fields):
    names = []
    if not isinstance(key_field_refs, list):
        return names

    for entry in key_field_refs:
        field_logical_id = ""
        if isinstance(entry, dict):
            field_logical_id = entry.get("Field", "")
        elif isinstance(entry, str):
            field_logical_id = entry

        if not field_logical_id:
            continue

        field_info = table_fields.get(field_logical_id, {})
        field_props = PropertyExtractor(field_info)
        label = field_props.label("")
        names.append(label or field_logical_id)

    return names


def _collect_connected_entries_from_qbl(qbl_data):
    if not isinstance(qbl_data, dict):
        return []

    entries = []
    resources = qbl_data.get("Resources", {})

    for app_key, app_value in resources.items():
        if not isinstance(app_value, dict):
            continue
        tables = app_value.get("Tables", {})
        for table_key, table_value in tables.items():
            connected_data = table_value.get("Properties", {}).get("ConnectedData")
            if connected_data:
                entries.append({
                    "app_key": app_key,
                    "table_key": table_key,
                    "table_value": table_value,
                    "connected_data": connected_data,
                })

    return entries


def _parse_legacy_connected_table(ct_key, ct_value, identifier_index=None, table_schema=None):
    props = PropertyExtractor(ct_value)

    source_config = ct_value.get("SourceConfig", {})
    target_config = ct_value.get("TargetConfig", {})

    if not source_config:
        source_config = ct_value.get("Source", {})
    if not target_config:
        target_config = ct_value.get("Target", {})

    source_table_logical = ""
    target_table_logical = ""

    if isinstance(source_config, dict):
        source_table_logical = source_config.get("Table", source_config.get("TableId", ""))
    if isinstance(target_config, dict):
        target_table_logical = target_config.get("Table", target_config.get("TableId", ""))

    source_table_info = TableResolver.resolve_complete_info(
        table_logical_id=source_table_logical,
        identifier_index=identifier_index,
        table_schema=table_schema
    ) if source_table_logical else {}

    target_table_info = TableResolver.resolve_complete_info(
        table_logical_id=target_table_logical,
        identifier_index=identifier_index,
        table_schema=table_schema
    ) if target_table_logical else {}

    field_mappings = ct_value.get("FieldMappings", ct_value.get("Fields", []))
    field_mapping_count = len(field_mappings) if isinstance(field_mappings, list) else 0

    return {
        "App Logical ID": "",
        "Connected Table Logical ID": ct_key,
        "Connected Table Name": props.name("Unnamed Connected Table"),
        "Description": props.description(""),
        "Source Table Logical ID": source_table_info.get("table_logical_id", source_table_logical),
        "Source Table ID": source_table_info.get("table_id", ""),
        "Source Table Name": source_table_info.get("table_name", ""),
        "Target Table Logical ID": target_table_info.get("table_logical_id", target_table_logical),
        "Target Table ID": target_table_info.get("table_id", ""),
        "Target Table Name": target_table_info.get("table_name", ""),
        "Sync Direction": props.get("SyncDirection", "bidirectional"),
        "Enabled": "Yes" if props.get("Enabled", True) else "No",
        "Field Mapping Count": field_mapping_count,
    }


def _parse_legacy_connected_table_fields(ct_key, ct_value, identifier_index=None, table_schema=None):
    props = PropertyExtractor(ct_value)
    ct_name = props.name("Unnamed Connected Table")

    field_mappings = ct_value.get("FieldMappings", ct_value.get("Fields", []))
    if not isinstance(field_mappings, list):
        return []

    source_config = ct_value.get("SourceConfig", ct_value.get("Source", {}))
    target_config = ct_value.get("TargetConfig", ct_value.get("Target", {}))

    source_table_logical = ""
    target_table_logical = ""

    if isinstance(source_config, dict):
        source_table_logical = source_config.get("Table", source_config.get("TableId", ""))
    if isinstance(target_config, dict):
        target_table_logical = target_config.get("Table", target_config.get("TableId", ""))

    source_table_info = TableResolver.resolve_complete_info(
        table_logical_id=source_table_logical,
        identifier_index=identifier_index,
        table_schema=table_schema
    ) if source_table_logical else {}

    target_table_info = TableResolver.resolve_complete_info(
        table_logical_id=target_table_logical,
        identifier_index=identifier_index,
        table_schema=table_schema
    ) if target_table_logical else {}

    records = []
    for idx, field_mapping in enumerate(field_mappings):
        if not isinstance(field_mapping, dict):
            continue

        mapping_props = PropertyExtractor(field_mapping)
        source_field_logical = mapping_props.get("SourceField", mapping_props.get("Source", ""))
        target_field_logical = mapping_props.get("TargetField", mapping_props.get("Target", ""))

        source_field_info = _resolve_field_info(source_field_logical, source_table_logical, identifier_index)
        target_field_info = _resolve_field_info(target_field_logical, target_table_logical, identifier_index)

        records.append({
            "App Logical ID": "",
            "Mapping #": idx + 1,
            "Connected Table Logical ID": ct_key,
            "Connected Table Name": ct_name,
            "Source Table Logical ID": source_table_info.get("table_logical_id", source_table_logical),
            "Source Table ID": source_table_info.get("table_id", ""),
            "Source Table Name": source_table_info.get("table_name", ""),
            "Source Field Logical ID": source_field_logical,
            "Source Field ID": source_field_info.get("field_id", ""),
            "Source Field Label": source_field_info.get("field_label", ""),
            "Target Table Logical ID": target_table_info.get("table_logical_id", target_table_logical),
            "Target Table ID": target_table_info.get("table_id", ""),
            "Target Table Name": target_table_info.get("table_name", ""),
            "Target Field Logical ID": target_field_logical,
            "Target Field ID": target_field_info.get("field_id", ""),
            "Target Field Label": target_field_info.get("field_label", ""),
        })

    return records


def _resolve_field_info(field_logical_id, table_logical_id, identifier_index):
    field_info = {
        "field_id": "",
        "field_label": "",
    }

    if not field_logical_id or not table_logical_id or not identifier_index:
        return field_info

    try:
        for app_key, app_data in identifier_index.items():
            elements = SafeExtractor.get_nested(
                app_data, "tables", table_logical_id, "elements", default={}
            )
            field_data = SafeExtractor.get_dict(elements, field_logical_id)

            if field_data:
                field_info["field_id"] = str(field_data.get("id", ""))
                field_info["field_label"] = field_data.get("label", "")
                break

    except Exception as e:
        print(f"Error resolving field info for {field_logical_id}: {e}")

    return field_info


