from .registry import get_validator
from .base_validator import (
    BaseValidator,
    normalize_issue,
    schema_issue,
    validate_generic,
    print_unexpected_properties,
)
from qblparser.contracts import QBLIssue


def _version_scope(qbl) -> list[QBLIssue]:
    from qblparser.qbl_schema.platform_requirements import SUPPORTED_SCHEMA_VERSIONS

    from qblparser.core import detect_qbl_version

    version = detect_qbl_version(qbl) if isinstance(qbl, dict) else None
    if not version or version in SUPPORTED_SCHEMA_VERSIONS:
        return []

    return [schema_issue(
        "SCH008", "", "", "",
        f"Document declares Version {version}; property requirements "
        f"describe QBL {' and '.join(SUPPORTED_SCHEMA_VERSIONS)} and may not apply",
        severity="warning",
    )]


def _version_gates(qbl) -> list[QBLIssue]:
    from .version_gates import validate_version_gates

    from qblparser.core import detect_qbl_version

    if not isinstance(qbl, dict):
        return []
    return validate_version_gates(qbl, detect_qbl_version(qbl))


def validate_qbl_resources(qbl, *, emit_summary=False) -> list[QBLIssue]:
    issues = _version_scope(qbl)
    issues.extend(_version_gates(qbl))
    resources = qbl.get("Resources", {})

    validator = BaseValidator()

    for resource_key, resource_value in resources.items():
        if not isinstance(resource_value, dict):
            continue

        resource_type = resource_value.get("Type")
        
        if resource_type == "QB::Application":
            context = validator.create_context(resource_key, resource_key)
            issues.extend(validate_resource(resource_value, context))
            
            issues.extend(validate_application_resources(resource_key, resource_value, validator))

        elif resource_type == "QB::Pipeline":
            context = validator.create_context(resource_key, resource_key)
            issues.extend(validate_resource(resource_value, context))
            
            issues.extend(validate_pipeline_resources(resource_key, resource_value, validator))

    issues.extend(validate_external_resources(qbl, validator))

    if emit_summary:
        print(f"Total issues found: {len(issues)}")
        print_unexpected_properties(issues)

    return [normalize_issue(issue) for issue in issues]

def validate_resource(resource, context):
    r_type = resource.get("Type")


    issues = _check_node_id(resource, context, r_type)

    validator_func = get_validator(r_type)
    if validator_func:
        return issues + validator_func(resource, context)
    
    return issues + validate_generic(resource, context)


PAGE_ID_TYPES = ("QB::HomePage", "QB::RichTextPage", "QB::CodePage")
PAGE_ID_MINIMUM = 2
FORMV2_ID_MINIMUM = 10
LEGACY_FORM_SOLE_LOW_ID = 2
DOCUMENT_TEMPLATE_ID_MINIMUM = 1


def _id_range_violation(r_type, node_id):
    if r_type in PAGE_ID_TYPES:
        if node_id < PAGE_ID_MINIMUM:
            return f"{PAGE_ID_MINIMUM} or greater"
    elif r_type == "QB::FormV2":
        if node_id < FORMV2_ID_MINIMUM:
            return f"{FORMV2_ID_MINIMUM} or greater"
    elif r_type == "QB::Form":
        if node_id != LEGACY_FORM_SOLE_LOW_ID and node_id < FORMV2_ID_MINIMUM:
            return f"exactly {LEGACY_FORM_SOLE_LOW_ID}, or {FORMV2_ID_MINIMUM} or greater"
    elif r_type == "QB::DocumentTemplate":
        if node_id < DOCUMENT_TEMPLATE_ID_MINIMUM:
            return f"{DOCUMENT_TEMPLATE_ID_MINIMUM} or greater"
    return None


def _check_node_id(resource, context, r_type):
    from qblparser.qbl_schema import get_resource_spec

    spec = get_resource_spec(r_type)
    if not spec or not spec.requires_node_id or not isinstance(resource, dict):
        return []

    def issue(problem):
        return [schema_issue(
            "SCH007", context.get("LogicalID", ""), context.get("Path", ""),
            r_type, problem,
        )]

    node_id = resource.get("Id")
    if node_id is None or (isinstance(node_id, str) and not node_id.strip()):
        return issue("Missing required node-level property 'Id'")

    if isinstance(node_id, bool) or not isinstance(node_id, int):
        return issue(f"Node-level 'Id' should be an integer, got {node_id!r}")

    expected = _id_range_violation(r_type, node_id)
    if expected:
        return issue(
            f"Node-level 'Id' on {r_type} should be {expected}, got {node_id}"
        )

    return []


def validate_external_resources(qbl, validator):
    external = qbl.get("ExternalResources")
    if not isinstance(external, dict):
        return []

    issues = []
    for source_key, source_value in external.items():
        if not isinstance(source_value, dict):
            continue

        source_path = f"ExternalResources > {source_key}"
        issues.extend(validate_resource(
            source_value, validator.create_context(source_key, source_path)
        ))

        record_sets = source_value.get("RecordSets")
        if not isinstance(record_sets, dict):
            continue

        for set_key, set_value in record_sets.items():
            if not isinstance(set_value, dict):
                continue

            set_path = f"{source_path} > RecordSets > {set_key}"
            issues.extend(validate_resource(
                set_value, validator.create_context(set_key, set_path)
            ))

            columns = set_value.get("Columns")
            if not isinstance(columns, dict):
                continue

            for column_key, column_value in columns.items():
                if not isinstance(column_value, dict):
                    continue
                issues.extend(validate_resource(
                    column_value,
                    validator.create_context(
                        column_key, f"{set_path} > Columns > {column_key}"
                    ),
                ))

    return issues


HOME_PAGE_SECTIONS = ("MainSection", "Sidebar")


def validate_home_page_sections(app_key, page_key, page_value, validator):
    issues = []

    for section in HOME_PAGE_SECTIONS:
        rows = page_value.get(section)
        if not isinstance(rows, dict):
            continue

        for row_key, row_value in rows.items():
            if not isinstance(row_value, dict):
                continue

            row_path = f"{app_key} > Pages > Resources > {page_key} > {section} > {row_key}"
            issues.extend(validate_resource(
                row_value, validator.create_context(row_key, row_path, rule_id=row_key)
            ))

            widgets = row_value.get("Widgets")
            if not isinstance(widgets, dict):
                continue

            for widget_key, widget_value in widgets.items():
                if not isinstance(widget_value, dict):
                    continue
                issues.extend(_validate_widget(
                    widget_key, widget_value,
                    f"{row_path} > Widgets > {widget_key}", validator,
                ))

    return issues


def _validate_widget(widget_key, widget_value, path, validator):
    issues = list(validate_resource(
        widget_value, validator.create_context(widget_key, path, rule_id=widget_key)
    ))

    for child_container, children in widget_value.items():
        if child_container == "Properties" or not isinstance(children, dict):
            continue
        for child_key, child_value in children.items():
            if not isinstance(child_value, dict) or "Type" not in child_value:
                continue
            issues.extend(_validate_widget(
                child_key, child_value,
                f"{path} > {child_container} > {child_key}", validator,
            ))

    return issues


def validate_application_resources(app_key, app_value, validator):
    issues = []
    
    variables = app_value.get("Variables", {})
    for var_key, var_value in variables.items():
        if isinstance(var_value, dict):
            context = validator.create_context(var_key, f"{app_key} > Variables > {var_key}")
            issues.extend(validate_resource(var_value, context))

    roles = app_value.get("Roles", {})
    for role_key, role_value in roles.items():
        if isinstance(role_value, dict):
            context = validator.create_context(
                role_key, 
                f"{app_key} > Roles > {role_key}"
            )
            issues.extend(validate_resource(role_value, context))
            
            issues.extend(validate_role_nested_properties(role_key, role_value, validator, app_key))

    guides = app_value.get("Guides", {})
    if isinstance(guides, dict):
        for guide_key, guide_value in guides.items():
            if isinstance(guide_value, dict):
                context = validator.create_context(
                    guide_key,
                    f"{app_key} > Guides > {guide_key}",
                    rule_id=guide_key
                )
                issues.extend(validate_resource(guide_value, context))

    pages = app_value.get("Pages", {})
    page_resources = pages.get("Resources", {}) if isinstance(pages, dict) else {}

    for dash_key, dash_value in page_resources.items():
        if not isinstance(dash_value, dict):
            continue

        dash_context = validator.create_context(
            dash_key,
            f"{app_key} > Pages > Resources > {dash_key}",
            rule_id=dash_key
        )
        issues.extend(validate_resource(dash_value, dash_context))

        issues.extend(validate_home_page_sections(
            app_key, dash_key, dash_value, validator
        ))

        if dash_value.get("Type") != "QB::Dashboard":
            continue

        for tab_key, tab_value in dash_value.get("Tabs", {}).items():
            if isinstance(tab_value, dict):
                tab_path = f"{app_key} > Pages > Resources > {dash_key} > Tabs > {tab_key}"
                tab_context = validator.create_context(tab_key, tab_path, rule_id=tab_key)
                issues.extend(validate_resource(tab_value, tab_context))

                for container in ("Widgets", "Filters"):
                    nodes = tab_value.get(container, {})
                    if not isinstance(nodes, dict):
                        continue
                    for node_key, node_value in nodes.items():
                        if not isinstance(node_value, dict):
                            continue
                        node_context = validator.create_context(
                            node_key,
                            f"{tab_path} > {container} > {node_key}",
                            rule_id=node_key,
                        )
                        issues.extend(validate_resource(node_value, node_context))

    tables = app_value.get("Tables", {})
    for table_key, table_value in tables.items():
        if isinstance(table_value, dict):
            issues.extend(validate_table_resources(app_key, table_key, table_value, validator))

    return issues


def validate_role_nested_properties(role_key, role_value, validator, app_key):
    issues = []
    
    app_ui = role_value.get("Properties", {}).get("AppUI", {})
    if isinstance(app_ui, dict) and app_ui:
        app_ui_context = validator.create_context(
            f"{role_key}_AppUI",
            f"{app_key} > Roles > {role_key} > AppUI"
        )
        app_ui_resource = {"Type": "QB::Role::AppUI", "Properties": app_ui}
        issues.extend(validate_resource(app_ui_resource, app_ui_context))
    
    table_ui = role_value.get("Properties", {}).get("TableUI", {})
    if isinstance(table_ui, dict) and table_ui:
        table_ui_context = validator.create_context(
            f"{role_key}_TableUI", 
            f"{app_key} > Roles > {role_key} > TableUI"
        )
        table_ui_resource = {"Type": "QB::Role::TableUI", "Properties": table_ui}
        issues.extend(validate_resource(table_ui_resource, table_ui_context))
    
    return issues


def validate_table_resources(app_key, table_key, table_value, validator):
    issues = []
    
    if isinstance(table_value, dict):
        table_context = validator.create_context(
            table_key,
            f"{app_key} > Tables > {table_key}",
            table_id=table_key
        )
        
        table_issues = validate_resource(table_value, table_context)
        issues.extend(table_issues)
        
        table_properties = table_value.get("Properties", {})
        
        custom_rules = table_properties.get("CustomDataRules", {})
        if isinstance(custom_rules, dict) and custom_rules:
            rules_context = validator.create_context(
                f"{table_key}_CustomDataRules",
                f"{app_key} > Tables > {table_key} > CustomDataRules"
            )
            rules_resource = {"Type": "QB::Table::CustomDataRules", "Properties": custom_rules}
            issues.extend(validate_resource(rules_resource, rules_context))
        
        role_perms = table_properties.get("RolePermissions", {})
        if isinstance(role_perms, dict) and role_perms:
            perms_context = validator.create_context(
                f"{table_key}_RolePermissions",
                f"{app_key} > Tables > {table_key} > RolePermissions"
            )
            perms_resource = {"Type": "QB::Table::RolePermissions", "Properties": role_perms}
            issues.extend(validate_resource(perms_resource, perms_context))
    
    fields = table_value.get("Fields", {})
    for field_key, field_value in fields.items():
        if isinstance(field_value, dict):
            context = validator.create_context(
                field_key,
                f"{app_key} > Tables > {table_key} > Fields > {field_key}",
                table_id=table_key,
                rule_id=field_key
            )
            issues.extend(validate_resource(field_value, context))

    forms = table_value.get("Forms", {}).get("Resources", {})
    for form_key, form_value in forms.items():
        if isinstance(form_value, dict):
            form_context = validator.create_context(
                form_key,
                f"{app_key} > Tables > {table_key} > Forms > {form_key}",
                table_id=table_key,
                form_id=form_key
            )
            issues.extend(validate_resource(form_value, form_context))

            issues.extend(validate_form_layout(app_key, table_key, form_key, form_value, validator))

            issues.extend(validate_form_rules(app_key, table_key, form_key, form_value, validator))

    for container in ("Reports", "Charts"):
        nodes = table_value.get(container, {})
        if not isinstance(nodes, dict):
            continue
        for node_key, node_value in nodes.items():
            if not isinstance(node_value, dict):
                continue
            path = f"{app_key} > Tables > {table_key} > {container} > {node_key}"
            context = validator.create_context(
                node_key, path, table_id=table_key, rule_id=node_key
            )
            issues.extend(validate_resource(node_value, context))
            issues.extend(validate_nested_resources(
                node_value, path, validator, table_id=table_key, rule_id=node_key
            ))

    report_groups = table_value.get("ReportGroups", {})
    for group_key, group_value in (report_groups if isinstance(report_groups, dict) else {}).items():
        if isinstance(group_value, dict):
            context = validator.create_context(
                group_key,
                f"{app_key} > Tables > {table_key} > ReportGroups > {group_key}",
                table_id=table_key,
                rule_id=group_key
            )
            issues.extend(validate_resource(group_value, context))

    relationships = table_value.get("Relationships", {})
    for rel_key, rel_value in relationships.items():
        if isinstance(rel_value, dict):
            context = validator.create_context(
                rel_key,
                f"{app_key} > Tables > {table_key} > Relationships > {rel_key}",
                table_id=table_key,
                rule_id=rel_key
            )
            issues.extend(validate_resource(rel_value, context))

    emails = table_value.get("Emails", {})
    if isinstance(emails, dict):
        for email_key, email_value in emails.items():
            if isinstance(email_value, dict):
                context = validator.create_context(
                    email_key,
                    f"{app_key} > Tables > {table_key} > Emails > {email_key}",
                    table_id=table_key,
                    rule_id=email_key
                )
                issues.extend(validate_resource(email_value, context))

    document_templates = table_value.get("DocumentTemplates", {})
    if isinstance(document_templates, dict):
        for dt_key, dt_value in document_templates.items():
            if isinstance(dt_value, dict):
                context = validator.create_context(
                    dt_key,
                    f"{app_key} > Tables > {table_key} > DocumentTemplates > {dt_key}",
                    table_id=table_key,
                    rule_id=dt_key
                )
                issues.extend(validate_resource(dt_value, context))

    return issues


_FORM_CONTAINERS_HANDLED_ELSEWHERE = ("Rules",)


_NODE_OWN_KEYS = ("Type", "Properties", "Id")


def validate_nested_resources(node, base_path, validator, *, skip=(), **context_fields):
    issues = []

    def walk(current, path):
        if isinstance(current, dict):
            if isinstance(current.get("Type"), str):
                context = validator.create_context(
                    path.rsplit(" > ", 1)[-1], path, **context_fields
                )
                issues.extend(validate_resource(current, context))
            for key, value in current.items():
                if key in _NODE_OWN_KEYS:
                    continue
                walk(value, f"{path} > {key}")
        elif isinstance(current, list):
            for index, item in enumerate(current):
                walk(item, f"{path}[{index}]")

    if not isinstance(node, dict):
        return issues

    for key, value in node.items():
        if key in _NODE_OWN_KEYS or key in skip:
            continue
        walk(value, f"{base_path} > {key}")

    return issues


def validate_form_layout(app_key, table_key, form_key, form_value, validator):
    if not str(form_value.get("Type", "")).startswith("QB::FormV2"):
        return []

    return validate_nested_resources(
        form_value,
        f"{app_key} > Tables > {table_key} > Forms > {form_key}",
        validator,
        skip=_FORM_CONTAINERS_HANDLED_ELSEWHERE,
        table_id=table_key,
        form_id=form_key,
    )


def validate_form_rules(app_key, table_key, form_key, form_value, validator):
    issues = []
    
    is_form_v2 = form_key.startswith("$FormV2_")
    rules_node = form_value.get("Rules", {} if is_form_v2 else [])

    if is_form_v2 and isinstance(rules_node, dict):
        for rule_key, rule_value in rules_node.items():
            if isinstance(rule_value, dict):
                context = validator.create_context(
                    rule_key,
                    f"{app_key} > Tables > {table_key} > Forms > {form_key} > Rules > {rule_key}",
                    table_id=table_key,
                    form_id=form_key,
                    rule_id=rule_key
                )
                issues.extend(validate_resource(rule_value, context))

    elif not is_form_v2 and isinstance(rules_node, list):
        for rule_index, rule_value in enumerate(rules_node):
            if isinstance(rule_value, dict):
                rule_logical_id = f"Rule_{rule_index}"
                context = validator.create_context(
                    rule_logical_id,
                    f"{app_key} > Tables > {table_key} > Forms > {form_key} > Rules[{rule_index}]",
                    table_id=table_key,
                    form_id=form_key,
                    rule_id=rule_logical_id
                )
                issues.extend(validate_resource(rule_value, context))

    return issues


def validate_pipeline_resources(pipeline_key, pipeline_value, validator):
    issues = []
    
    accounts = pipeline_value.get("Accounts", [])
    if isinstance(accounts, list):
        for account_idx, account in enumerate(accounts):
            if isinstance(account, dict):
                context = validator.create_context(
                    f"{pipeline_key}_Account_{account_idx}",
                    f"{pipeline_key} > Accounts[{account_idx}]"
                )
                issues.extend(validate_resource(account, context))
    
    steps = pipeline_value.get("Steps", [])
    if isinstance(steps, list):
        for step_idx, step in enumerate(steps):
            if isinstance(step, dict):
                context = validator.create_context(
                    f"{pipeline_key}_Step_{step_idx}",
                    f"{pipeline_key} > Steps[{step_idx}]"
                )
                issues.extend(validate_resource(step, context))

    return issues
