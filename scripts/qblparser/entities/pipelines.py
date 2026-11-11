import re
import json
from urllib.parse import urlparse
from qblparser.utils.property_extractor import PropertyExtractor
from qblparser.utils.helpers import TableResolver, SafeExtractor
from qblparser.utils.qbl_tags import scalar_ref_value


NESTED_STEP_KEYS = ("Then", "Else", "Steps")


def iter_steps(steps):
    if not isinstance(steps, list):
        return
    for step in steps:
        if not isinstance(step, dict):
            continue
        yield step
        for nested_key in NESTED_STEP_KEYS:
            yield from iter_steps(step.get(nested_key))


def step_node(step, key, default=None):
    if not isinstance(step, dict):
        return default if default is not None else {}
    if key in step:
        return step[key]
    properties = step.get("Properties", {})
    if isinstance(properties, dict) and key in properties:
        return properties[key]
    return default if default is not None else {}


def iter_data_sources(inputs_meta):
    if not isinstance(inputs_meta, dict):
        return
    for key, value in inputs_meta.items():
        if not isinstance(value, dict):
            continue
        if "Fields" in value or "Table" in value:
            yield key, value

        data_sources = value.get("PipelineStep_DataSources", {})
        if not isinstance(data_sources, dict):
            continue
        for source_key, source in data_sources.items():
            if not isinstance(source, dict):
                continue
            properties = source.get("Properties", {})
            if isinstance(properties, dict):
                yield f"{key}.PipelineStep_DataSources.{source_key}", properties


def normalize_table_reference(value):
    if isinstance(value, str):
        return value if value.startswith("$Table_") else ""
    if isinstance(value, dict):
        inner = value.get("Table", "")
        if isinstance(inner, str) and inner.startswith("$Table_"):
            return inner
    return ""


def _pipeline_app_logical_id(pipeline_value, qbl_data):
    table_to_app_map = _build_table_to_app_map(qbl_data)
    if not table_to_app_map:
        return ""

    apps = set()
    for step in iter_steps(pipeline_value.get("Steps", [])):
        for _context, source in iter_data_sources(step_node(step, "InputsMeta")):
            table_logical_id = normalize_table_reference(source.get("Table"))
            app_key = table_to_app_map.get(table_logical_id)
            if app_key:
                apps.add(app_key)
    return apps.pop() if len(apps) == 1 else ""


def _channel_account_reference(step):
    props = PropertyExtractor(step)
    reference = props.get("PipelineChannelAccount", "")
    scalar = scalar_ref_value(reference)
    if scalar:
        return scalar
    if isinstance(reference, dict):
        value = reference.get("PipelineChannelAccount", "")
        return value if isinstance(value, str) else ""
    if isinstance(reference, str):
        return reference
    return ""


def _channel_accounts(qbl_data):
    accounts = {}
    resources = (qbl_data or {}).get("Resources", {}) if isinstance(qbl_data, dict) else {}
    for key, value in resources.items():
        if not isinstance(value, dict) or value.get("Type") != "QB::PipelineChannelAccount":
            continue
        props = PropertyExtractor(value)
        account_id = props.get("AccountId", "")
        if isinstance(account_id, dict):
            account_id = ""
        accounts[key] = {
            "channel": props.get("Channel", ""),
            "account_id": "" if account_id is None else str(account_id),
        }
    return accounts


_HTTP_INPUT_KEYS = ("Method", "Url", "Body", "Content_Type")

_MAX_TARGET_HOPS = 10


def iter_steps_with_depth(steps, depth=0):
    if not isinstance(steps, list):
        return
    for step in steps:
        if not isinstance(step, dict):
            continue
        yield step, depth
        for nested_key in NESTED_STEP_KEYS:
            yield from iter_steps_with_depth(step.get(nested_key), depth + 1)


def step_target_id(step):
    target = step_node(step, "Target")
    if not isinstance(target, dict) or target.get("Type") != "step-reference":
        return ""
    step_id = target.get("StepId")
    return "" if step_id is None else str(step_id)


def own_step_tables(step):
    tables = []
    for _context, source in iter_data_sources(step_node(step, "InputsMeta")):
        table_logical_id = normalize_table_reference(source.get("Table"))
        if table_logical_id and table_logical_id not in tables:
            tables.append(table_logical_id)
    return tables


def step_tables_by_id(pipeline_value):
    tables = {}
    for step in iter_steps(pipeline_value.get("Steps", []) if isinstance(pipeline_value, dict) else []):
        step_id = PropertyExtractor(step).get("Id", "")
        if step_id not in ("", None):
            tables[str(step_id)] = (own_step_tables(step), step_target_id(step))
    return tables


def resolved_step_tables(step, tables_by_id):
    own = own_step_tables(step)
    if own:
        return own, ""
    target = step_target_id(step)
    first_target = target
    seen = set()
    while target and target not in seen and len(seen) < _MAX_TARGET_HOPS:
        seen.add(target)
        tables, next_target = (tables_by_id or {}).get(target) or ([], "")
        if tables:
            return list(tables), first_target
        target = next_target
    return [], first_target


def _render_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        text = " ".join(value.split())
        return f'"{text}"'
    return json.dumps(value, sort_keys=True, default=str)


def render_filter_expression(filters):
    if not filters:
        return ""
    if isinstance(filters, list):
        expression = filters
    elif isinstance(filters, dict):
        if filters.get("Type") == "relational-expression":
            expression = [filters]
        else:
            expression = filters.get("Expression", [])
    else:
        return str(filters)
    if not isinstance(expression, list):
        return ""

    stack = []
    for term in expression:
        if not isinstance(term, dict):
            continue
        term_type = term.get("Type", "")
        if term_type == "logical-operator":
            operator = str(term.get("Operator", "AND")).upper()
            if len(stack) >= 2:
                right = stack.pop()
                left = stack.pop()
                stack.append(f"({left} {operator} {right})")
            continue
        if term_type == "composite-expression":
            nested = render_filter_expression(term)
            if nested:
                stack.append(f"({nested})")
            continue
        field = term.get("Field", "?")
        if isinstance(field, dict):
            field = field.get("Field", "?")
        operator = term.get("Operator", "?")
        if "Value" in term:
            stack.append(f"{field} {operator} {_render_value(term.get('Value'))}")
        else:
            stack.append(f"{field} {operator}")

    rendered = " AND ".join(stack)
    if rendered.startswith("(") and rendered.endswith(")") and len(stack) == 1:
        depth = 0
        for index, char in enumerate(rendered):
            depth += 1 if char == "(" else -1 if char == ")" else 0
            if depth == 0 and index < len(rendered) - 1:
                break
        else:
            rendered = rendered[1:-1]
    return rendered


def input_mappings(step):
    inputs = step_node(step, "Inputs")
    if not isinstance(inputs, dict):
        return []
    mappings = []
    for key, value in inputs.items():
        if key in _HTTP_INPUT_KEYS:
            continue
        if isinstance(value, str):
            text = value.strip()
        else:
            text = json.dumps(value, sort_keys=True, default=str)
        mappings.append((str(key), text))
    return mappings


def render_input_mappings(step):
    return "; ".join(f"{key} = {value}" for key, value in input_mappings(step))


def trigger_field_ids(step):
    fields = []
    for _context, source in iter_data_sources(step_node(step, "InputsMeta")):
        if source.get("Name") != "trigger_fields":
            continue
        for field_ref in source.get("Fields", []) or []:
            if isinstance(field_ref, dict):
                field = field_ref.get("Field", "")
                if isinstance(field, str) and field and field not in fields:
                    fields.append(field)
    return fields


def _trigger_on_all_fields(step):
    inputs_meta = step_node(step, "InputsMeta")
    if not isinstance(inputs_meta, dict):
        return ""
    for value in inputs_meta.values():
        if isinstance(value, dict):
            flag = (value.get("Properties") or {}).get("Trigger_On_All_Fields")
            if flag is not None:
                return "Yes" if flag else "No"
    return ""


def field_slug(label):
    return re.sub(r"[^a-z0-9]+", "_", str(label or "").casefold()).strip("_")


def _table_field_slugs(qbl_data, table_logical_id):
    slugs = {}
    if not isinstance(qbl_data, dict) or not table_logical_id:
        return slugs
    for app_key, app_value in (qbl_data.get("Resources", {}) or {}).items():
        if not isinstance(app_value, dict) or not app_key.startswith("$App_"):
            continue
        table = (app_value.get("Tables", {}) or {}).get(table_logical_id)
        if not isinstance(table, dict):
            continue
        for field_key, field_value in (table.get("Fields", {}) or {}).items():
            if not isinstance(field_value, dict):
                continue
            props = PropertyExtractor(field_value)
            slug = field_slug(props.label(""))
            if slug:
                slugs.setdefault(slug, field_key)
            if str(props.id("")) == "3":
                slugs["id"] = field_key
        break
    return slugs


def _filter_field_names(filters):
    names = []
    if isinstance(filters, dict):
        if filters.get("Type") == "relational-expression":
            field = filters.get("Field")
            if isinstance(field, str):
                names.append(field)
        for value in filters.values():
            if isinstance(value, (dict, list)):
                names.extend(_filter_field_names(value))
    elif isinstance(filters, list):
        for item in filters:
            names.extend(_filter_field_names(item))
    return names


def parse_pipeline(pipeline_key, pipeline_value, identifier_index=None, qbl_data=None):
    props = PropertyExtractor(pipeline_value)
    
    pipeline_name = props.name("Unnamed Pipeline")
    tags = props.get("Tags", [])
    owner = props.get("Owner", "")
    
    tags_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
    
    all_steps = list(iter_steps(pipeline_value.get("Steps", [])))

    channel_accounts = _channel_accounts(qbl_data)
    account_details = []
    for step in all_steps:
        reference = _channel_account_reference(step)
        if not reference:
            continue
        entry = channel_accounts.get(reference, {})
        channel = entry.get("channel", "")
        account_id = entry.get("account_id", "")
        label = f"{channel}:{account_id}" if channel and account_id else (channel or reference)
        if label not in account_details:
            account_details.append(label)

    accounts_summary = ", ".join(account_details) if account_details else "None"
    step_count = len(all_steps)
    
    action_count = 0
    
    for step in all_steps:
        step_props = PropertyExtractor(step)
        if step_props.get("SubType", "") == "action":
            action_count += 1
    
    action_summary = f"{action_count} actions" if action_count > 0 else "No actions"

    schedule = props.get("Crontab", "") or ""
    timezone = props.get("CrontabTimezone", "") or ""
    trigger = ""
    if schedule:
        trigger = f"Schedule {schedule}" + (f" ({timezone})" if timezone else "")
    else:
        table_names = _build_table_name_map(qbl_data)
        for step in all_steps:
            step_props = PropertyExtractor(step)
            if step_props.get("SubType", "") != "trigger":
                continue
            channel = step_props.get("Channel", {})
            selector = channel.get("Selector", "") if isinstance(channel, dict) else ""
            tables = [table_names.get(t, t) for t in own_step_tables(step)]
            trigger = " ".join(part for part in (selector, ", ".join(tables)) if part)
            trigger = trigger or step_props.get("Name", "")
            break

    return {
        "App Logical ID": _pipeline_app_logical_id(pipeline_value, qbl_data),
        "Pipeline Logical ID": pipeline_key,
        "Pipeline Name": pipeline_name,
        "Tags": tags_str,
        "Owner": owner,
        "Total Steps": step_count,
        "Actions": action_summary,
        "Accounts": accounts_summary,
        "Description": props.description("") or "",
        "Trigger": trigger,
        "Schedule": schedule,
        "Schedule Timezone": timezone,
    }

def parse_pipeline_steps(pipeline_key, pipeline_value, identifier_index=None, qbl_data=None):
    pipeline_props = PropertyExtractor(pipeline_value)
    pipeline_name = pipeline_props.name("Unnamed Pipeline")

    step_records = []
    channel_accounts = _channel_accounts(qbl_data)
    pipeline_app = _pipeline_app_logical_id(pipeline_value, qbl_data)

    step_type_mapping = {
        "pipe": "step",
        "branch": "if statement",
        "loop": "loop"
    }

    tables_by_id = step_tables_by_id(pipeline_value)
    table_names = _build_table_name_map(qbl_data)
    field_labels = _build_field_label_map(qbl_data)

    for step, depth in iter_steps_with_depth(pipeline_value.get("Steps", [])):
        step_props = PropertyExtractor(step)

        step_id = step_props.get("Id", "")
        step_name = step_props.get("Name", "Unnamed Step")
        step_type_raw = step_props.get("Type", "")
        step_subtype = step_props.get("SubType", "")
        account_reference = _channel_account_reference(step)
        account_id = (
            channel_accounts.get(account_reference, {}).get("account_id", "")
            or account_reference
        )

        step_type = step_type_mapping.get(step_type_raw, step_type_raw)

        node_type = str(step.get("Type") or "")
        channel_type = (node_type[len("QB::PipelineStep::"):]
                        if node_type.startswith("QB::PipelineStep::") else "")

        channel = step_props.get("Channel", {})
        channel_resource = ""
        channel_id = ""
        channel_selector = ""

        if isinstance(channel, dict):
            channel_resource = channel.get("Resource", "")
            channel_id = channel.get("Id", "")
            channel_selector = channel.get("Selector", "")

        inputs = step_node(step, "Inputs")
        http_method = ""
        http_url = ""
        http_body = ""
        content_type = ""

        if isinstance(inputs, dict):
            http_method = inputs.get("Method", "")
            http_url = inputs.get("Url", "")
            http_body = inputs.get("Body", "")
            content_type = inputs.get("Content_Type", "")

        inputs_meta = step_node(step, "InputsMeta")
        referenced_fields = []
        referenced_tables = []

        for _context, source in iter_data_sources(inputs_meta):
            fields = source.get("Fields", [])
            if isinstance(fields, list):
                for field_ref in fields:
                    if isinstance(field_ref, dict) and field_ref.get("Field"):
                        referenced_fields.append(field_ref.get("Field", ""))

            table_logical_id = normalize_table_reference(source.get("Table"))
            if table_logical_id:
                referenced_tables.append(table_logical_id)

        resolved_tables, target_step = resolved_step_tables(step, tables_by_id)
        target_step = step_target_id(step) or target_step
        if not referenced_tables and resolved_tables:
            referenced_tables = list(resolved_tables)
        table_source = "Target step" if (resolved_tables and not own_step_tables(step)) else (
            "Step data source" if resolved_tables else "")

        filters = step_node(step, "Filters")
        trigger_fields = trigger_field_ids(step)

        step_records.append({
            "App Logical ID": pipeline_app,
            "Pipeline Logical ID": pipeline_key,
            "Pipeline Name": pipeline_name,
            "Step ID": step_id,
            "Step Name": step_name,
            "Step Type": step_type,
            "Step SubType": step_subtype,
            "Account ID": account_id,
            "Channel Type": channel_type,
            "Channel Resource": channel_resource,
            "Channel ID": channel_id,
            "Channel Selector": channel_selector,
            "HTTP Method": http_method,
            "HTTP URL": http_url,
            "HTTP Body": http_body,
            "Content Type": content_type,
            "Referenced Fields": ", ".join(referenced_fields) if referenced_fields else "",
            "Referenced Tables": ", ".join(referenced_tables) if referenced_tables else "",
            "Field Count": len(referenced_fields),
            "Table Count": len(referenced_tables),
            "Step Depth": depth,
            "Target Step ID": target_step,
            "Table Logical ID": resolved_tables[0] if resolved_tables else "",
            "Table Name": ", ".join(table_names.get(t, t) for t in resolved_tables),
            "Table Source": table_source,
            "Filters": render_filter_expression(filters),
            "Input Mappings": render_input_mappings(step),
            "Trigger Fields": ", ".join(field_labels.get(f, f) for f in trigger_fields),
            "Trigger On All Fields": _trigger_on_all_fields(step),
        })

    return step_records

def parse_pipeline_table_matrix(pipeline_key, pipeline_value, identifier_index=None, table_schema=None, qbl_data=None):
    
    CONFIG = {
        "url_patterns": [
            {"pattern": r'tableId=([^&\s]+)', "name": "tableId"},
            {"pattern": r'table=([^&\s]+)', "name": "table"},
            {"pattern": r'dbid=([^&\s]+)', "name": "dbid"},
        ],
        
        "body_fields": [
            "to",
            "from",
            "table",
            "tableId",
            "dbid",
            "target",
            "source",
        ],
        
        "skip_patterns": [
            r'^\{\{.*\}\}$',
            r'^\{.*\}$',
            r'^[a-zA-Z_]+\.',
        ]
    }
    
    pipeline_props = PropertyExtractor(pipeline_value)
    pipeline_name = pipeline_props.name("Unnamed Pipeline")
    table_to_app_map = _build_table_to_app_map(qbl_data)
    table_name_map = _build_table_name_map(qbl_data)
    
    table_matrix = []
    tables_by_id = step_tables_by_id(pipeline_value)
    
    for step in iter_steps(pipeline_value.get("Steps", [])):
        step_props = PropertyExtractor(step)
        
        step_id = step_props.get("Id", "")
        step_name = step_props.get("Name", "Unnamed Step")
        
        native = _extract_native_step_references(
            pipeline_key, pipeline_name, step_id, step_name,
            step_props, identifier_index, table_schema, table_to_app_map, step,
            table_name_map
        )
        table_matrix.extend(native)

        if not native and step_props.get("Type", "") != "loop":
            tables, target = resolved_step_tables(step, tables_by_id)
            for table_logical_id in tables:
                table_info = TableResolver.resolve_complete_info(
                    table_logical_id=table_logical_id,
                    identifier_index=identifier_index,
                    table_schema=table_schema
                )
                table_matrix.append({
                    "App Logical ID": _resolve_app_logical_id(table_info, table_to_app_map),
                    "Pipeline Logical ID": pipeline_key,
                    "Pipeline Name": pipeline_name,
                    "Step ID": step_id,
                    "Step Name": step_name,
                    "Table Logical ID": table_info["table_logical_id"],
                    "Table ID": table_info["table_id"],
                    "Table Name": table_info["table_name"] or table_name_map.get(
                        table_logical_id, ""),
                    "Reference Type": "Target Step",
                    "Reference Context": f"Target.StepId={target} (the table step {target} works against)",
                })
        
        table_matrix.extend(
            _extract_http_request_references(
                pipeline_key, pipeline_name, step_id, step_name,
                step_props, CONFIG, identifier_index, table_schema, table_to_app_map, step,
                table_name_map
            )
        )
    
    table_matrix.sort(key=lambda x: (x["Pipeline Logical ID"], x["Step ID"]))
    
    return table_matrix


def _extract_native_step_references(pipeline_key, pipeline_name, step_id, step_name,
                                   step_props, identifier_index, table_schema, table_to_app_map=None,
                                   step=None, table_name_map=None):
    references = []
    seen = set()

    inputs_meta = step_node(step, "InputsMeta") if step is not None else step_props.get("InputsMeta", {})

    for context, source in iter_data_sources(inputs_meta):
        table_logical_id = normalize_table_reference(source.get("Table"))
        if not table_logical_id or table_logical_id in seen:
            continue
        seen.add(table_logical_id)

        table_info = TableResolver.resolve_complete_info(
            table_logical_id=table_logical_id,
            identifier_index=identifier_index,
            table_schema=table_schema
        )

        references.append({
            "App Logical ID": _resolve_app_logical_id(table_info, table_to_app_map),
            "Pipeline Logical ID": pipeline_key,
            "Pipeline Name": pipeline_name,
            "Step ID": step_id,
            "Step Name": step_name,
            "Table Logical ID": table_info["table_logical_id"],
            "Table ID": table_info["table_id"],
            "Table Name": table_info["table_name"] or (table_name_map or {}).get(
                table_logical_id, ""),
            "Reference Type": "Native Step",
            "Reference Context": f"{context}.Table (Native pipeline step data source reference)",
        })

    return references


def _extract_http_request_references(pipeline_key, pipeline_name, step_id, step_name,
                                   step_props, config, identifier_index, table_schema, table_to_app_map=None,
                                   step=None, table_name_map=None):
    references = []
    
    inputs = step_node(step, "Inputs") if step is not None else step_props.get("Inputs", {})
    if not isinstance(inputs, dict):
        return references
    
    http_method = inputs.get("Method", "")
    http_url = inputs.get("Url", "")
    http_body = inputs.get("Body", "")
    
    if "api.quickbase.com" not in http_url:
        return references
    
    references.extend(
        _extract_from_url(
            pipeline_key, pipeline_name, step_id, step_name,
            http_method, http_url, config, identifier_index, table_schema, table_to_app_map
        )
    )
    
    references.extend(
        _extract_from_body(
            pipeline_key, pipeline_name, step_id, step_name,
            http_method, http_url, http_body, config, identifier_index, table_schema, table_to_app_map
        )
    )
    
    return references


def _extract_from_url(pipeline_key, pipeline_name, step_id, step_name,
                     http_method, http_url, config, identifier_index, table_schema, table_to_app_map=None):
    references = []
    
    for url_config in config["url_patterns"]:
        pattern = url_config["pattern"]
        pattern_name = url_config["name"]
        
        matches = re.findall(pattern, http_url)
        
        for table_id in matches:
            if _should_skip_value(table_id, config["skip_patterns"]):
                continue
            
            table_info = TableResolver.resolve_complete_info(
                table_id=table_id,
                identifier_index=identifier_index,
                table_schema=table_schema
            )
            
            api_type = _determine_api_type_from_url(http_method, http_url)
            
            references.append({
                "App Logical ID": _resolve_app_logical_id(table_info, table_to_app_map),
                "Pipeline Logical ID": pipeline_key,
                "Pipeline Name": pipeline_name,
                "Step ID": step_id,
                "Step Name": step_name,
                "Table Logical ID": table_info["table_logical_id"],
                "Table ID": table_info["table_id"],
                "Table Name": table_info["table_name"],
                "Reference Type": f"QB API - {api_type}",
                "Reference Context": f'{http_method} {http_url} ({pattern_name}={table_id})',
            })
    
    return references


def _extract_from_body(pipeline_key, pipeline_name, step_id, step_name,
                      http_method, http_url, http_body, config, identifier_index, table_schema, table_to_app_map=None):
    references = []
    
    if not http_body:
        return references
    
    try:
        body_data = json.loads(http_body)
        if not isinstance(body_data, dict):
            return references
        
    except json.JSONDecodeError:
        return _extract_from_raw_body(
            pipeline_key, pipeline_name, step_id, step_name,
            http_method, http_url, http_body, config, identifier_index, table_schema, table_to_app_map
        )
    
    for field_name in config["body_fields"]:
        if field_name in body_data:
            table_id = body_data[field_name]
            
            if not isinstance(table_id, str) or _should_skip_value(table_id, config["skip_patterns"]):
                continue
            
            table_info = TableResolver.resolve_complete_info(
                table_id=table_id,
                identifier_index=identifier_index,
                table_schema=table_schema
            )
            
            api_type = _determine_api_type_from_url(http_method, http_url)
            
            references.append({
                "App Logical ID": _resolve_app_logical_id(table_info, table_to_app_map),
                "Pipeline Logical ID": pipeline_key,
                "Pipeline Name": pipeline_name,
                "Step ID": step_id,
                "Step Name": step_name,
                "Table Logical ID": table_info["table_logical_id"],
                "Table ID": table_info["table_id"],
                "Table Name": table_info["table_name"],
                "Reference Type": f"QB API - {api_type}",
                "Reference Context": f'{http_method} {http_url} ("{field_name}": "{table_id}")',
            })
    
    return references


def _extract_from_raw_body(pipeline_key, pipeline_name, step_id, step_name,
                          http_method, http_url, http_body, config, identifier_index, table_schema, table_to_app_map=None):
    references = []
    
    for field_name in config["body_fields"]:
        pattern = rf'"{field_name}":\s*"([^"]+)"'
        matches = re.findall(pattern, http_body)
        
        for table_id in matches:
            if _should_skip_value(table_id, config["skip_patterns"]):
                continue
            
            table_info = TableResolver.resolve_complete_info(
                table_id=table_id,
                identifier_index=identifier_index,
                table_schema=table_schema
            )
            
            api_type = _determine_api_type_from_url(http_method, http_url)
            
            references.append({
                "App Logical ID": _resolve_app_logical_id(table_info, table_to_app_map),
                "Pipeline Logical ID": pipeline_key,
                "Pipeline Name": pipeline_name,
                "Step ID": step_id,
                "Step Name": step_name,
                "Table Logical ID": table_info["table_logical_id"],
                "Table ID": table_info["table_id"],
                "Table Name": table_info["table_name"],
                "Reference Type": f"QB API - {api_type}",
                "Reference Context": f'{http_method} {http_url} ("{field_name}": "{table_id}")',
            })
    
    return references


def _should_skip_value(value, skip_patterns):
    for pattern in skip_patterns:
        if re.match(pattern, value):
            return True
    return False


def _determine_api_type_from_url(http_method, http_url):
    parsed_path = urlparse(http_url).path.lower()
    api_patterns = [
        {"pattern": r'/v1/records/query', "name": "Records Query"},
        {"pattern": r'/v1/records/delete', "name": "Records Delete"},
        {"pattern": r'/v1/records$', "name": "Records Upsert"},
        {"pattern": r'/v1/formulas/run', "name": "Run Formula"},
        {"pattern": r'/v1/audit', "name": "Audit Logs"},
        {"pattern": r'/v1/files\b', "name": "File Download/Upload"},
        {"pattern": r'/v1/files/delete', "name": "File Delete"},
        {"pattern": r'/v1/files/upload', "name": "File Upload"},
        {"pattern": r'/v1/doctemplates/\d+/generate', "name": "Generate Document Template"},
        {"pattern": r'/v1/doctemplates', "name": "Document Template API"},
        {"pattern": r'/v1/platformAnalytics', "name": "Platform Analytics"},
        {"pattern": r'/v1/reports/\d+/run', "name": "Report Run"},
        {"pattern": r'/v1/reports$', "name": "List Reports"},
        {"pattern": r'/v1/reports/\d+$', "name": "Get Report"},
        {"pattern": r'/v1/fields$', "name": "List Fields"},
        {"pattern": r'/v1/fields/\d+$', "name": "Get Field"},
        {"pattern": r'/v1/tables$', "name": "List Tables"},
        {"pattern": r'/v1/tables/\w+$', "name": "Get Table"},
        {"pattern": r'/v1/apps/\w+/tables', "name": "List Tables for App"},
        {"pattern": r'/v1/apps/\w+$', "name": "Get App"},
        {"pattern": r'^/v1/solutions$', "name": "Create Solution"},
        {"pattern": r'^/v1/solutions/[^/]+$', "name": "Update Solution"},
        {"pattern": r'^/v1/solutions/[^/]+/export$', "name": "Export Solution"},
        {"pattern": r'^/v1/solutions/[^/]+/changeset$', "name": "List Solution Changes"},
        {"pattern": r'^/v1/solutions/fromrecord$', "name": "Create Solution From Record"},
        {"pattern": r'^/v1/solutions/[^/]+/torecord$', "name": "Update Solution To Record"},
        {"pattern": r'^/v1/solutions/[^/]+/fromrecord/changeset$', "name": "Changeset From Record"},
        {"pattern": r'^/v1/solutions/public/[^/]+$', "name": "Get Public Solution"},
        {"pattern": r'^/v1/solutions/[^/]+/torecord/export$', "name": "Export Solution To Record"},
    ]
    
    for api_config in api_patterns:
        if re.search(api_config["pattern"], parsed_path):
            return api_config["name"]
    
    return "Generic API"

def parse_field_to_pipeline_matrix(qbl_data, identifier_index=None, table_schema=None):
    
    field_pipeline_matrix = []
    
    field_to_table_map = _build_field_to_table_mapping(qbl_data, identifier_index, table_schema)
    
    resources = qbl_data.get("Resources", {})
    
    for resource_key, resource_value in resources.items():
        if not resource_key.startswith("$Pipeline_"):
            continue
            
        try:
            pipeline_props = PropertyExtractor(resource_value)
            pipeline_name = pipeline_props.name("Unnamed Pipeline")
            
            tables_by_id = step_tables_by_id(resource_value)

            for step in iter_steps(resource_value.get("Steps", [])):
                step_props = PropertyExtractor(step)
                step_id = step_props.get("Id", "")
                step_name = step_props.get("Name", "Unnamed Step")
                
                field_references = _extract_field_references_from_step(step_props, step)
                field_references.extend(_slug_field_references(
                    step, step_props, tables_by_id, qbl_data, field_references))
                
                for field_ref in field_references:
                    field_logical_id = field_ref["field_logical_id"]
                    reference_context = field_ref["context"]
                    
                    referenced_table = field_ref.get("table_logical_id", "")
                    table_info = {}
                    if referenced_table:
                        table_info = field_to_table_map.get((referenced_table, field_logical_id), {})
                    if not table_info:
                        table_info = field_to_table_map.get(field_logical_id, {})
                    
                    if table_info:
                        field_pipeline_matrix.append({
                            "App Logical ID": table_info.get("app_logical_id", ""),
                            "Pipeline Logical ID": resource_key,
                            "Pipeline Name": pipeline_name,
                            "Step ID": step_id,
                            "Step Name": step_name,
                            "Table Logical ID": table_info.get("table_logical_id", ""),
                            "Table ID": table_info.get("table_id", ""),
                            "Table Name": table_info.get("table_name", ""),
                            "Field Logical ID": field_logical_id,
                            "Field ID": table_info.get("field_id", ""),
                            "Field Label": table_info.get("field_label", ""),
                            "Field Type": table_info.get("field_type", ""),
                            "Reference Context": reference_context,
                        })
                        
        except Exception as e:
            print(f"Error processing pipeline {resource_key} for field matrix: {e}")
            continue
    
    field_pipeline_matrix.sort(key=lambda x: (
        x["Pipeline Logical ID"],
        x["Step ID"],
        x["Table Name"],
        x["Field Label"]
    ))
    
    return field_pipeline_matrix


def _build_field_to_table_mapping(qbl_data, identifier_index, table_schema):
    
    field_mapping = {}
    
    resources = qbl_data.get("Resources", {})
    
    for app_key, app_value in resources.items():
        if not app_key.startswith("$App_"):
            continue
            
        tables = app_value.get("Tables", {})
        
        for table_key, table_value in tables.items():
            table_props = PropertyExtractor(table_value)
            table_name = table_props.name("Unknown Table")
            
            table_info = TableResolver.resolve_from_logical_id(table_key, identifier_index, table_schema, app_key)
            table_id = table_info.get("table_id", "")
            
            fields = table_value.get("Fields", {})
            
            for field_key, field_value in fields.items():
                field_props = PropertyExtractor(field_value)
                
                field_id = ""
                if field_key and table_key and identifier_index:
                    for id_map_app_key, app_data in identifier_index.items():
                        elements = SafeExtractor.get_nested(app_data, "tables", table_key, "elements", default={})
                        field_info = SafeExtractor.get_dict(elements, field_key)
                        if field_info.get("id"):
                            field_id = str(field_info.get("id"))
                            break
                
                entry = {
                    "app_logical_id": app_key,
                    "table_logical_id": table_key,
                    "table_id": table_id,
                    "table_name": table_name,
                    "field_id": field_id or "",
                    "field_label": field_props.label("Unnamed Field"),
                    "field_type": field_props.type().split("::")[-1] if "::" in field_props.type() else field_props.type(),
                }

                field_mapping[(table_key, field_key)] = entry
                field_mapping.setdefault(field_key, entry)
    
    return field_mapping

def _extract_field_references_from_step(step_props, step=None):
    import re
    import json
    
    field_references = []
    
    inputs_meta = step_node(step, "InputsMeta") if step is not None else step_props.get("InputsMeta", {})
    for context, source in iter_data_sources(inputs_meta):
        fields = source.get("Fields", [])
        if not isinstance(fields, list):
            continue
        for field_ref in fields:
            if not isinstance(field_ref, dict):
                continue
            field_logical_id = field_ref.get("Field", "")
            if isinstance(field_logical_id, str) and field_logical_id.startswith("$Field_"):
                field_references.append({
                    "field_logical_id": field_logical_id,
                    "table_logical_id": normalize_table_reference(field_ref.get("Table")),
                    "context": f"InputsMeta.{context}.Fields (Native step data source)"
                })
    
    inputs = step_node(step, "Inputs") if step is not None else step_props.get("Inputs", {})
    if isinstance(inputs, dict):
        http_method = inputs.get("Method", "")
        http_url = inputs.get("Url", "")
        http_body = inputs.get("Body", "")
        
        if "api.quickbase.com" in http_url and http_body:
            body_field_refs = _extract_field_refs_from_http_body(http_body, http_method, http_url)
            field_references.extend(body_field_refs)
    
    step_properties_to_check = ["Target", "Filters", "Conditions", "Outputs"]
    
    for prop_name in step_properties_to_check:
        prop_value = step_props.get(prop_name, {})
        if prop_value:
            prop_field_refs = _extract_field_refs_from_property(prop_value, prop_name)
            field_references.extend(prop_field_refs)
    
    return field_references


def _extract_field_refs_from_http_body(http_body, http_method, http_url):
    import re
    import json
    
    field_references = []
    
    if not http_body:
        return field_references
    
    try:
        body_data = json.loads(http_body)
        
        field_refs = _find_field_refs_in_json(body_data)
        
        for field_logical_id in field_refs:
            field_references.append({
                "field_logical_id": field_logical_id,
                "context": f"{http_method} {http_url} (HTTP request body - JSON field reference)"
            })
            
    except json.JSONDecodeError:
        field_pattern = r'\$Field_[A-Za-z0-9_]+'
        field_matches = re.findall(field_pattern, http_body)
        
        for field_logical_id in field_matches:
            field_references.append({
                "field_logical_id": field_logical_id,
                "context": f"{http_method} {http_url} (HTTP request body - raw text field reference)"
            })
    
    return field_references


def _find_field_refs_in_json(data, path=""):
    field_refs = []
    
    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            
            if isinstance(value, str) and value.startswith("$Field_"):
                field_refs.append(value)
            
            field_refs.extend(_find_field_refs_in_json(value, current_path))
            
    elif isinstance(data, list):
        for i, item in enumerate(data):
            current_path = f"{path}[{i}]" if path else f"[{i}]"
            field_refs.extend(_find_field_refs_in_json(item, current_path))
    
    elif isinstance(data, str) and data.startswith("$Field_"):
        field_refs.append(data)
    
    return field_refs


def _extract_field_refs_from_property(prop_value, prop_name):
    field_references = []
    
    field_refs = _find_field_refs_in_json(prop_value)
    
    for field_logical_id in field_refs:
        field_references.append({
            "field_logical_id": field_logical_id,
            "context": f"Step property: {prop_name}"
        })
    
    return field_references


def _slug_field_references(step, step_props, tables_by_id, qbl_data, existing):
    if step_props.get("Type", "") == "loop":
        return []
    tables, _target = resolved_step_tables(step, tables_by_id)
    if not tables:
        return []
    table_logical_id = tables[0]
    slugs = _table_field_slugs(qbl_data, table_logical_id)
    if not slugs:
        return []
    seen = {(ref.get("table_logical_id", ""), ref.get("field_logical_id", "")) for ref in existing}
    seen |= {("", ref.get("field_logical_id", "")) for ref in existing}
    added = []

    def add(slug, context):
        field_logical_id = slugs.get(field_slug(slug))
        if not field_logical_id:
            return
        if (table_logical_id, field_logical_id) in seen or ("", field_logical_id) in seen:
            return
        seen.add((table_logical_id, field_logical_id))
        added.append({
            "field_logical_id": field_logical_id,
            "table_logical_id": table_logical_id,
            "context": context,
        })

    for name in _filter_field_names(step_node(step, "Filters")):
        add(name, f"Filters.{name} (step filter condition)")
    for key, _value in input_mappings(step):
        add(key, f"Inputs.{key} (value the step writes)")
    return added


def _build_field_label_map(qbl_data):
    labels = {}
    if not isinstance(qbl_data, dict):
        return labels
    for app_key, app_value in (qbl_data.get("Resources", {}) or {}).items():
        if not isinstance(app_value, dict) or not app_key.startswith("$App_"):
            continue
        for table_value in (app_value.get("Tables", {}) or {}).values():
            if not isinstance(table_value, dict):
                continue
            for field_key, field_value in (table_value.get("Fields", {}) or {}).items():
                if isinstance(field_value, dict):
                    label = PropertyExtractor(field_value).label("")
                    if label:
                        labels.setdefault(field_key, label)
    return labels


def _build_table_to_app_map(qbl_data):
    table_to_app_map = {}
    if not isinstance(qbl_data, dict):
        return table_to_app_map
    resources = qbl_data.get("Resources", {})
    for app_key, app_value in resources.items():
        if not isinstance(app_value, dict) or not app_key.startswith("$App_"):
            continue
        for table_key in app_value.get("Tables", {}).keys():
            table_to_app_map[table_key] = app_key
    return table_to_app_map


def _build_table_name_map(qbl_data):
    names = {}
    if not isinstance(qbl_data, dict):
        return names
    for app_key, app_value in (qbl_data.get("Resources", {}) or {}).items():
        if not isinstance(app_value, dict) or not app_key.startswith("$App_"):
            continue
        for table_key, table_value in (app_value.get("Tables", {}) or {}).items():
            if isinstance(table_value, dict):
                name = PropertyExtractor(table_value).name("")
                if name:
                    names[table_key] = name
    return names


def _resolve_app_logical_id(table_info, table_to_app_map):
    if not isinstance(table_info, dict):
        return ""
    table_logical_id = table_info.get("table_logical_id", "")
    if not table_logical_id or not isinstance(table_to_app_map, dict):
        return ""
    return table_to_app_map.get(table_logical_id, "")

