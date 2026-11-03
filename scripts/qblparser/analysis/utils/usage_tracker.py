class UsageTracker:
    
    def __init__(self):
        self._target_app = ""
        self._source_app = ""
        self._source_table = ""

    def set_target_app(self, app_key: str):
        self._target_app = str(app_key or "")

    def set_source_app(self, app_key: str):
        self._source_app = str(app_key or "")

    def set_source_table(self, table_key):
        self._source_table = str(table_key or "")

    def clear_context(self):
        self._target_app = ""
        self._source_app = ""
        self._source_table = ""

    def resolve_usage_keys(self, usage_dict, item_ref, table_key=None):
        if not item_ref or not isinstance(item_ref, str):
            return []

        if item_ref.startswith("$Role_"):
            return [item_ref] if item_ref in usage_dict else []

        scope = str(table_key or self._source_table or "")
        if scope:
            qualified = (scope, item_ref)
            if qualified in usage_dict:
                return [qualified]

        if item_ref in usage_dict:
            return [item_ref]

        return [key for key in usage_dict if isinstance(key, tuple) and key[1] == item_ref]
    
    def mark_used_if_exists(self, usage_dict, item_ref, usage_category, table_key=None):
        if not item_ref or not isinstance(item_ref, str):
            return False
        if not (item_ref.startswith("$Field_") or item_ref.startswith("$Role_")):
            return False

        keys = self.resolve_usage_keys(usage_dict, item_ref, table_key)
        if not keys:
            return False

        for key in keys:
            entry = usage_dict[key]
            entry[usage_category] = True
            usage_counts = entry.get("__counts__")
            if isinstance(usage_counts, dict):
                usage_counts[usage_category] = int(usage_counts.get(usage_category, 0)) + 1
                if (
                    self._target_app
                    and self._source_app
                    and self._target_app != self._source_app
                    and "Cross-App References" in entry
                ):
                    entry["Cross-App References"] = True
                    usage_counts["Cross-App References"] = int(
                        usage_counts.get("Cross-App References", 0)
                    ) + 1
        return True
    
    def get_usage_categories(self):
        return [
            "Used in Reports",
            "Used in Report Dynamic Filters",
            "Used in Forms", 
            "Used in Form Rules",
            "Used in Custom Data Rules",
            "Referenced in Formulas",
            "Used in Relationships",
            "Used in Dashboards",
            "Used in Charts",
            "Used in Field Properties",
            "Used in Permissions",
            "Cross-App References"
        ]
    
    def get_role_usage_categories(self):
        return [
            "Used in Form Rules",
            "Used in Table Permissions", 
            "Used in Field Permissions",
            "Used in Report Permissions",
            "Used in Default Forms",
            "Used in Custom Access Rules",
            "Referenced in Formulas",
            "Used in Dashboard Permissions",
            "Used in Pipeline Rules",
            "Cross-App References"
        ]
    
    def initialize_field_usage(self, fields):
        usage_categories = {category: False for category in self.get_usage_categories()}
        usage_counts = {category: 0 for category in self.get_usage_categories()}
        
        return {
            field_key: {**usage_categories.copy(), "__counts__": usage_counts.copy()}
            for field_key in fields
        }
    
    def initialize_role_usage(self, roles):
        usage_categories = {category: False for category in self.get_role_usage_categories()}
        
        return {
            role_key: usage_categories.copy() 
            for role_key in roles
        }
    
    def get_usage_summary(self, usage_dict):
        total_items = len(usage_dict)
        if total_items == 0:
            return {"total_items": 0, "unused_items": 0, "usage_by_category": {}}
        
        unused_count = 0
        if usage_dict:
            first_key = next(iter(usage_dict))
            if first_key.startswith("$Role_"):
                categories = self.get_role_usage_categories()
            else:
                categories = self.get_usage_categories()
        else:
            categories = []
        
        category_counts = {category: 0 for category in categories}
        
        for item_key, usage in usage_dict.items():
            category_values = [usage.get(category, False) for category in categories]
            if not any(category_values):
                unused_count += 1
            
            for category in categories:
                is_used = usage.get(category, False)
                if is_used and category in category_counts:
                    category_counts[category] += 1
        
        return {
            "total_items": total_items,
            "unused_items": unused_count,
            "unused_percentage": (unused_count / total_items) * 100,
            "usage_by_category": category_counts
        }
