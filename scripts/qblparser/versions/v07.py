from .base import BaseVersionHandler
from qblparser.parsing_registry import PARSING_REGISTRY
from qblparser.analysis.usage_coordinator import UsageCoordinator
from qblparser.entities.fields import enhance_field_metadata_with_usage
from qblparser.analysis.analyzers.role_analyzer import RoleAnalyzer
from qblparser.utils.helpers import ElementTraverser, FieldExtractor
from qblparser.utils.property_extractor import PropertyExtractor
from qblparser.utils.role_defaults import collect_role_default_references
from qblparser.utils.qbl_tags import scalar_ref_value


REPORT_LIKE_PREFIXES = ("$Report_", "$Chart_")


class QBLv07Handler(BaseVersionHandler):
    
    def __init__(self, table_schema=None, identifier_index=None):
        super().__init__(table_schema)
        self.identifier_index = identifier_index
        self.usage_coordinator = UsageCoordinator()
        self._report_usage = {
            "legacy_forms": set(),
            "v2_forms": set(),
            "dashboards": set(),
        }
    
    def get_version(self):
        return "0.7"
    
    def get_supported_entities(self):
        return [
            "tables", "fields", "forms", "reports", 
            "dashboards", "relationships", "permissions"
        ]
    
    def parse_qbl(self, qbl_data):
        resources = qbl_data.get("Resources", {})
        self._resources = resources
        
        results = self._initialize_result_collections()
        
        for app_key, app_value in resources.items():
            if not app_key.startswith("$App_"):
                continue
            
            try:
                self._parse_application_tables(app_key, app_value, results)
                self._parse_application_dashboards(app_key, app_value, results)
                self._parse_application_roles(app_key, app_value, results)

                self._analyze_field_usage(app_key, app_value, results)
                self._analyze_role_usage(app_key, app_value, results)
                
            except Exception as e:
                print(f"Error parsing application {app_key}: {e}")
                continue

        self._apply_report_usage(results)
        return results
    
    def _initialize_result_collections(self):
        return {
            "permissions": [],
            "roles": [],
            "tables": [],
            "fields": [],
            "field_role_matrix": [],
            "dashboards": [],
            "reports": [],
            "report_dashboard_matrix": [],
            "report_permissions": [],
            "report_field_matrix": [],
            "forms": [],
            "field_form_matrix": [],
            "rules": [],
            "role_form_rule_matrix": [],
            "relationships": [],
            "charts": [],
            "report_groups": [],
        }
    
    def _parse_application_roles(self, app_key, app_value, results):
        try:
            roles = PARSING_REGISTRY["roles"](app_key, app_value, self.identifier_index)
            results["roles"].extend(roles)
            
            field_role_matrix = PARSING_REGISTRY["field_role_matrix"](app_key, app_value, self.identifier_index)
            results["field_role_matrix"].extend(field_role_matrix)
            
        except Exception as e:
            print(f"Error parsing roles for app {app_key}: {e}")
    
    def _parse_application_tables(self, app_key, app_value, results):
        tables = app_value.get("Tables", {})
        
        for table_key, table_value in tables.items():
            try:
                results["tables"].append(
                    PARSING_REGISTRY["table"](table_key, table_value, self.identifier_index, self.table_schema, app_key)
                )
                
                results["permissions"].extend(
                    PARSING_REGISTRY["permissions"](
                        table_key,
                        table_value,
                        self.identifier_index,
                        self.table_schema,
                        app_key,
                        app_value,
                    )
                )
                
                self._parse_table_fields(app_key, app_value, table_key, table_value, results)
                self._parse_table_reports(app_key, table_key, table_value, results)
                self._parse_table_charts(app_key, table_key, table_value, results)
                self._parse_table_report_groups(app_key, table_key, table_value, results)
                self._parse_table_forms(app_key, table_key, table_value, results)
                self._parse_table_relationships(app_key, app_value, table_key, table_value, results)
                
            except Exception as e:
                print(f"Error parsing table {table_key}: {e}")
                continue
    
    def _parse_table_fields(self, app_key, app_value, table_key, table_value, results):
        fields = table_value.get("Fields", {})
        table_props = table_value.get("Properties", {})
        table_name = table_props.get("Name", "Unknown Table")
        
        field_metadata = PARSING_REGISTRY["field_metadata"](
            table_name, fields, table_key, self.table_schema, app_key, app_value, self.identifier_index,
            {"Resources": self._resources}
        )
        results["fields"].extend(field_metadata)
    
    def _parse_table_reports(self, app_key, table_key, table_value, results):
        table_props = table_value.get("Properties", {})
        table_name = table_props.get("Name", "Unknown Table")
        fields = table_value.get("Fields", {})

        table_reports = table_value.get("Reports", {})
        for report_key, report_value in table_reports.items():
            if self._is_report_group(report_key, report_value) or self._is_chart(report_key, report_value):
                continue
            try:
                report_row = PARSING_REGISTRY["report"](
                    table_name, report_value, table_key, report_key, self.identifier_index, app_key, self.table_schema
                )
                report_row["Object"] = "Report"
                results["reports"].append(report_row)
                results["report_field_matrix"].extend(
                    PARSING_REGISTRY["report_field_matrix"](
                        table_name, report_value, fields, table_key, report_key, self.identifier_index, app_key, self.table_schema
                    )
                )
                results["report_permissions"].extend(
                    PARSING_REGISTRY["report_permissions"](
                        table_name, report_key, report_value, table_key, self.identifier_index, app_key, self.table_schema
                    )
                )
            except Exception as e:
                print(f"Error parsing report {report_key}: {e}")
    
    @staticmethod
    def _is_chart(report_key, report_value):
        node_type = report_value.get("Type", "") if isinstance(report_value, dict) else ""
        return report_key.startswith("$Chart_") or str(node_type).startswith("QB::Chart")

    @staticmethod
    def _is_report_group(report_key, report_value):
        node_type = report_value.get("Type", "") if isinstance(report_value, dict) else ""
        return report_key.startswith("$ReportGroup_") or str(node_type) in (
            "QB::ReportGroup",
            "QB::Report::Group",
        )

    def _parse_table_charts(self, app_key, table_key, table_value, results):
        table_name = table_value.get("Properties", {}).get("Name", "Unknown Table")
        charts = table_value.get("Charts", {})
        if not isinstance(charts, dict):
            return

        fields = table_value.get("Fields", {})

        for chart_key, chart_value in charts.items():
            if not isinstance(chart_value, dict):
                continue
            try:
                chart_row = PARSING_REGISTRY["report"](
                    table_name, chart_value, table_key, chart_key,
                    self.identifier_index, app_key, self.table_schema,
                )
                chart_row["Object"] = "Chart"
                results["charts"].append(chart_row)
                results["report_field_matrix"].extend(
                    PARSING_REGISTRY["report_field_matrix"](
                        table_name, chart_value, fields, table_key, chart_key,
                        self.identifier_index, app_key, self.table_schema,
                    )
                )
                results["report_permissions"].extend(
                    PARSING_REGISTRY["report_permissions"](
                        table_name, chart_key, chart_value, table_key,
                        self.identifier_index, app_key, self.table_schema,
                    )
                )
            except Exception as e:
                print(f"Error parsing chart {chart_key}: {e}")

    def _parse_table_report_groups(self, app_key, table_key, table_value, results):
        table_name = table_value.get("Properties", {}).get("Name", "Unknown Table")
        groups = table_value.get("ReportGroups", {})
        if not isinstance(groups, dict):
            return

        for group_key, group_value in groups.items():
            if not isinstance(group_value, dict):
                continue
            results["report_groups"].append(
                self._parse_report_group(
                    app_key, table_key, table_name, group_key, group_value
                )
            )

    def _parse_report_group(self, app_key, table_key, table_name, group_key, group_value):
        props = group_value.get("Properties", {}) if isinstance(group_value, dict) else {}
        members = [
            member
            for member in (self._extract_report_ref_value(entry) for entry in props.get("Reports", []) or [])
            if member
        ]
        return {
            "App Logical ID": app_key or "",
            "Table Logical ID": table_key or "",
            "Table Name": table_name,
            "Report Group Logical ID": group_key,
            "Report Group Name": props.get("Name", ""),
            "Report Count": len(members),
            "Reports": ", ".join(members),
        }

    def _parse_table_forms(self, app_key, table_key, table_value, results):
        table_props = table_value.get("Properties", {})
        table_name = table_props.get("Name", "Unknown Table")
        fields = table_value.get("Fields", {})
        
        field_id_lookup = {}
        for field_key, field_value in fields.items():
            props = PropertyExtractor(field_value)
            field_id_lookup[field_key] = {
                "Id": props.id("N/A"),
                "Type": props.type("Unknown"),
                "Label": props.label("") or props.name("")
            }
        
        table_forms = table_value.get("Forms", {}).get("Resources", {})
        for form_key, form_value in table_forms.items():
            try:
                report_refs = self._collect_report_refs_from_form(form_key, form_value, fields)
                if report_refs:
                    bucket = "v2_forms" if form_key.startswith("$FormV2_") else "legacy_forms"
                    self._report_usage[bucket].update(report_refs)

                results["forms"].append(
                    PARSING_REGISTRY["form"](
                        table_name,
                        form_key,
                        form_value,
                        table_key,
                        self.table_schema,
                        self.identifier_index,
                        app_key,
                        table_value.get("Forms", {}),
                    )
                )
                
                self._parse_form_rules(app_key, table_name, form_key, form_value, table_key, results,
                                       table_fields=table_value.get("Fields", {}))
                
                field_node = form_value.copy()
                if form_key.startswith("$FormV2_"):
                    field_node["Elements"] = form_value.get("Layout", {})
                
                results["field_form_matrix"].extend(
                    PARSING_REGISTRY["field_form_matrix"](
                        table_name, form_key, field_node, field_id_lookup, table_key, self.table_schema, self.identifier_index, app_key
                    )
                )

                results["role_form_rule_matrix"].extend(
                    PARSING_REGISTRY["role_form_rule_matrix"](
                        table_name, form_key, form_value, table_key, self.table_schema, self.identifier_index, app_key
                    )
                )
                
            except Exception as e:
                print(f"Error parsing form {form_key}: {e}")
    
    def _parse_form_rules(self, app_key, table_name, form_key, form_value, table_key, results,
                          table_fields=None):
        form_name = form_value["Properties"].get("Name", "Unnamed Form")
        is_form_v2 = form_key.startswith("$FormV2_")
        rules_node = form_value.get("Rules", {} if is_form_v2 else [])
        
        if is_form_v2 and isinstance(rules_node, dict):
            for rule_key, rule_value in rules_node.items():
                if isinstance(rule_value, dict):
                    try:
                        results["rules"].append(
                            PARSING_REGISTRY["rule"](
                                table_name, form_name, rule_key, rule_value, form_key, table_key,
                                self.table_schema, form_value, self.identifier_index, app_key,
                                table_fields=table_fields,
                            )
                        )
                    except Exception as e:
                        print(f"Error parsing FormV2 rule {rule_key}: {e}")
                        
        elif not is_form_v2 and isinstance(rules_node, list):
            for rule_index, rule_value in enumerate(rules_node):
                if isinstance(rule_value, dict):
                    try:
                        results["rules"].append(
                            PARSING_REGISTRY["rule"](
                                table_name, form_name, f"Rule_{rule_index}", rule_value, form_key, table_key,
                                self.table_schema, form_value, self.identifier_index, app_key,
                                table_fields=table_fields,
                            )
                        )
                    except Exception as e:
                        print(f"Error parsing legacy rule {rule_index}: {e}")
    
    def _parse_table_relationships(self, app_key, app_value, table_key, table_value, results):
        table_relationships = table_value.get("Relationships", {})
        for relationship_key, relationship_value in table_relationships.items():
            try:
                results["relationships"].append(
                    PARSING_REGISTRY["relationship"](
                        app_key,
                        app_value,
                        relationship_key,
                        relationship_value,
                        self.table_schema,
                        self.identifier_index,
                        table_key=table_key,
                        qbl_resources={"Resources": self._resources},
                    )
                )
            except Exception as e:
                print(f"Error parsing relationship {relationship_key}: {e}")
    
    def _parse_application_dashboards(self, app_key, app_value, results):
        try:
            pages = app_value.get("Pages", {})
            if isinstance(pages, dict) and "Resources" in pages:
                dashboards_root = pages["Resources"]
            else:
                dashboards_root = pages
            assigned_dashboard_ids = collect_role_default_references(
                pages.get("Properties", {}).get("RoleDefaults", {}) if isinstance(pages, dict) else {},
                ("$Dashboard_",),
            )

            for dashboard_key, dashboard_value in dashboards_root.items():
                if not dashboard_key.startswith("$Dashboard_"):
                    continue

                self._parse_single_dashboard(app_key, dashboard_key, dashboard_value, results, assigned_dashboard_ids)
                
        except Exception as e:
            print(f"Error parsing dashboards for app {app_key}: {e}")
    
    def _parse_single_dashboard(self, app_key, dashboard_key, dashboard_value, results, assigned_dashboard_ids=None):
        try:
            dashboard_name = dashboard_value.get("Properties", {}).get("Name", dashboard_key)
            tabs = dashboard_value.get("Tabs", {})
            dashboard_role_permissions = dashboard_value.get("Properties", {}).get("RolePermissions", {})
            mapped_to_role_permissions = "Yes" if isinstance(dashboard_role_permissions, dict) and bool(dashboard_role_permissions) else "No"
            assigned_to_role_homepage = "Yes" if dashboard_key in (assigned_dashboard_ids or set()) else "No"
            
            for tab_key, tab_value in tabs.items():
                tab_name = tab_value.get("Properties", {}).get("Name", tab_key)
                widgets = tab_value.get("Widgets", {})
                
                for widget_key, widget_value in widgets.items():
                    self._parse_dashboard_widget(
                        app_key,
                        dashboard_key,
                        dashboard_name,
                        tab_key,
                        tab_name,
                        widget_key,
                        widget_value,
                        results,
                        assigned_to_role_homepage,
                        mapped_to_role_permissions,
                    )
                    
        except Exception as e:
            print(f"Error parsing dashboard {dashboard_key}: {e}")
    
    def _parse_dashboard_widget(self, app_key, dashboard_key, dashboard_name, tab_key, tab_name, widget_key, widget_value, results,
                                assigned_to_role_homepage="No", mapped_to_role_permissions="No"):
        props = widget_value.get("Properties", {})
        widget_type = widget_value.get("Type", "")
        
        target_table = self._extract_widget_target_table(props)
        target_report = self._extract_widget_target_report(props)
        
        results["dashboards"].append({
            "App Logical ID": app_key or "",
            "Dashboard Logical ID": dashboard_key,
            "Dashboard Name": dashboard_name,
            "Assigned to Role Homepage": assigned_to_role_homepage,
            "Mapped to Role Permissions": mapped_to_role_permissions,
            "Used by Roles": "Yes" if "Yes" in (assigned_to_role_homepage, mapped_to_role_permissions) else "No",
            "Tab Logical ID": tab_key,
            "Tab Name": tab_name,
            "Widget Logical ID": widget_key,
            "Widget Type": widget_type,
            "Widget Text": props.get("Text", props.get("Title", "")),
            "Widget Title": props.get("Title", ""),
            "Widget ShowTitle": props.get("ShowTitle", ""),
            "Widget BackgroundColor": props.get("BackgroundColor", ""),
            "Widget X": props.get("X", ""),
            "Widget Y": props.get("Y", ""),
            "Widget Width": props.get("Width", ""),
            "Widget Height": props.get("Height", ""),
            "Target Table": target_table,
            "Target Report": target_report,
            "Target Page": props.get("Page", {}).get("Dashboard", "") if isinstance(props.get("Page"), dict) else "",
            "Target App": props.get("App", ""),
            "NonDashboardPageId": props.get("NonDashboardPageId", ""),
            "AfterSaveAction": props.get("AfterSaveAction", ""),
            "AfterSaveGoTo": props.get("AfterSaveGoTo", ""),
            "Link": props.get("Link", ""),
            "SearchType": props.get("SearchType", ""),
            "SearchTarget": props.get("SearchTarget", ""),
            "ResultsView": props.get("ResultsView", ""),
            "HintText": props.get("HintText", ""),
            "KpiType": props.get("KpiType", ""),
            "IncludesDelta": props.get("IncludesDelta", ""),
            "ShowTarget": props.get("ShowTarget", ""),
            "Scale": props.get("Scale", ""),
            "DecimalPlaces": props.get("DecimalPlaces", ""),
            "TextColor": props.get("TextColor", ""),
        })

        if target_report:
            if isinstance(target_report, str) and target_report.startswith(REPORT_LIKE_PREFIXES):
                self._report_usage["dashboards"].add(target_report)
            results["report_dashboard_matrix"].append({
                "App Logical ID": app_key or "",
                "Dashboard Logical ID": dashboard_key,
                "Dashboard Name": dashboard_name,
                "Tab Logical ID": tab_key,
                "Widget Logical ID": widget_key,
                "Report Reference": target_report,
            })

    def _apply_report_usage(self, results):
        legacy_forms = self._report_usage["legacy_forms"]
        v2_forms = self._report_usage["v2_forms"]
        dashboards = self._report_usage["dashboards"]

        for report in list(results.get("reports", [])) + list(results.get("charts", [])):
            report_key = report.get("Report Logical ID", "")
            used_in_forms = report_key in legacy_forms or report_key in v2_forms
            report["Used in Forms"] = "Yes" if used_in_forms else "No"
            report["Used in Dashboards"] = "Yes" if report_key in dashboards else "No"

    def _collect_report_refs_from_form(self, form_key, form_value, fields):
        report_refs = set()

        def process_element(element_key, element_value, parent_path, depth):
            element_type = element_value.get("Type", "")
            if not isinstance(element_type, str) or "::Report" not in element_type:
                return None

            props = element_value.get("Properties", {})
            report_ref = self._extract_report_reference(props, fields)
            if not report_ref:
                report_ref = self._extract_report_ref_value(element_value.get("Report"))
            if report_ref:
                report_refs.add(report_ref)
            return None

        traverser = ElementTraverser(process_element)

        if form_key.startswith("$FormV2_"):
            nodes = []
            layout = form_value.get("Layout")
            if isinstance(layout, dict) and layout:
                nodes.append(layout)
            pages = form_value.get("Pages")
            if isinstance(pages, dict) and pages:
                nodes.append(pages)
            pinned = form_value.get("PinnedSection")
            if isinstance(pinned, dict) and pinned:
                nodes.append({"PinnedSection": pinned})
            if not nodes:
                nodes.append(form_value.get("Elements", form_value))

            for node in nodes:
                traverser.traverse(node)
        else:
            elements = form_value.get("Elements", {})
            traverser.traverse(elements)

        return report_refs

    def _extract_report_reference(self, props, fields):
        report_ref = self._extract_report_ref_value(props.get("Report"))
        if report_ref:
            return report_ref

        embedded = props.get("EmbeddedView")
        if isinstance(embedded, dict):
            report_ref = self._extract_report_ref_value(embedded.get("TargetReport"))
            if report_ref:
                return report_ref

        link_field_ref = FieldExtractor.from_reference(props.get("ReportLinkField"))
        if not link_field_ref:
            return ""

        field_def = fields.get(link_field_ref, {})
        if not isinstance(field_def, dict):
            return ""

        field_props = PropertyExtractor(field_def)
        target = field_props.get("Target")
        return self._extract_report_ref_value(target)

    def _extract_report_ref_value(self, report_ref):
        scalar = scalar_ref_value(report_ref)
        if scalar:
            report_ref = scalar
        if isinstance(report_ref, str):
            return report_ref if report_ref.startswith(REPORT_LIKE_PREFIXES) else ""
        if isinstance(report_ref, dict):
            for key in ("Report", "Chart"):
                nested = self._extract_report_ref_value(report_ref.get(key))
                if nested:
                    return nested
        return ""

    def _extract_widget_target_table(self, props):
        for candidate in (props.get("Table"), props.get("Report"),
                          props.get("SearchReport")):
            scalar = scalar_ref_value(candidate)
            if scalar and scalar.startswith("$Table_"):
                return scalar
            if isinstance(candidate, dict):
                table = candidate.get("Table")
                if isinstance(table, str) and table:
                    return table
                if isinstance(table, dict) and table.get("Table"):
                    return table["Table"]
            elif isinstance(candidate, str) and candidate.startswith("$Table_"):
                return candidate

        search_fields = props.get("SearchFields")
        if isinstance(search_fields, dict):
            table = search_fields.get("Table")
            if isinstance(table, dict) and table.get("Table"):
                return table["Table"]
            if isinstance(table, str) and table:
                return table

        return ""

    def _extract_widget_target_report(self, props):
        for key in ("Report", "SearchReport"):
            candidate = props.get(key)

            scalar = scalar_ref_value(candidate)
            if scalar:
                return scalar
            if isinstance(candidate, dict):
                target = candidate.get("Chart") or candidate.get("Report")
                if target:
                    return target
            elif isinstance(candidate, str) and candidate:
                return candidate
        return ""
    
    def _analyze_field_usage(self, app_key, app_value, results):
        try:
            all_fields = {}
            for table_key, table_value in app_value.get("Tables", {}).items():
                for field_key, field_value in (table_value.get("Fields", {}) or {}).items():
                    all_fields[(table_key, field_key)] = field_value
            
            if not all_fields:
                return
            
            field_usage = self.usage_coordinator.tracker.initialize_field_usage(all_fields)
            
            field_usage = self.usage_coordinator.analyze_comprehensive_usage(
                app_key, app_value, all_fields, field_usage
            )

            app_field_keys = {field_key for _table_key, field_key in all_fields}
            target_indexes = []
            target_rows = []
            for idx, field_row in enumerate(results["fields"]):
                row_app = field_row.get("App Logical ID", "")
                row_field_key = field_row.get("Field Logical ID", "")
                belongs_to_current_app = (row_app == app_key) if row_app else (row_field_key in app_field_keys)
                if belongs_to_current_app:
                    target_indexes.append(idx)
                    target_rows.append(field_row)

            if target_rows:
                enhanced_rows = enhance_field_metadata_with_usage(target_rows, field_usage)
                for idx, enhanced_row in zip(target_indexes, enhanced_rows):
                    results["fields"][idx] = enhanced_row
            
        except Exception as e:
            print(f"Error analyzing field usage for app {app_key}: {e}")

    def _analyze_role_usage(self, app_key, app_value, results):
        try:
            all_roles = app_value.get("Roles", {})
            
            if not all_roles:
                return
            
            role_usage = self.usage_coordinator.tracker.initialize_role_usage(all_roles)
            
            role_usage = self.usage_coordinator.analyze_comprehensive_usage(
                app_key, app_value, all_roles, role_usage, analyzer_type="roles"
            )

            from qblparser.entities.roles import enhance_role_metadata_with_usage
            app_role_keys = set(all_roles.keys())
            target_indexes = []
            target_rows = []
            for idx, role_row in enumerate(results["roles"]):
                row_app = role_row.get("App Logical ID", "")
                row_role_key = role_row.get("Role Logical ID", "")
                belongs_to_current_app = (row_app == app_key) if row_app else (row_role_key in app_role_keys)
                if belongs_to_current_app:
                    target_indexes.append(idx)
                    target_rows.append(role_row)

            if target_rows:
                enhanced_rows = enhance_role_metadata_with_usage(target_rows, role_usage)
                for idx, enhanced_row in zip(target_indexes, enhanced_rows):
                    results["roles"][idx] = enhanced_row
            
        except Exception as e:
            print(f"Error analyzing role usage for app {app_key}: {e}")
