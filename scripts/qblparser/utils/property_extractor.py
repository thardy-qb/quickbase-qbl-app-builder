class PropertyExtractor:
    
    def __init__(self, entity_data):
        self.entity_data = entity_data or {}
        self.properties = self.entity_data.get("Properties", {})
    
    def name(self, default="Unnamed Entity"):
        return self.properties.get("Name", default)
    
    def label(self, default=""):
        return self.properties.get("Label", default)
    
    def description(self, default=""):
        return self.properties.get("Description", default)
    
    def id(self, default="N/A"):
        return self.entity_data.get("Id", default)
    
    def type(self, default="Unknown"):
        return self.entity_data.get("Type", default)
    
    def is_required(self, default=False):
        return self.properties.get("IsRequired", default)
    
    def is_unique(self, default=False):
        return self.properties.get("IsUnique", default)
    
    def is_auditable(self, default=False):
        return self.properties.get("IsAuditable", default)
    
    def is_searchable(self, default=False):
        return self.properties.get("IsSearchable", default)
    
    def help_text(self, default=""):
        return self.properties.get("HelpText", default)
    
    def comments(self, default=""):
        return self.properties.get("Comments", default)
    
    def formula(self, default=""):
        return self.properties.get("Formula", default)
    
    def allowed_in_reports(self, default=""):
        return self.properties.get("AllowedInReports", default)
    
    def default_value(self, default=""):
        return self.properties.get("DefaultValue", default)
    
    def max_length(self, default=""):
        return self.properties.get("MaxLength", default)
    
    def get(self, key, default=None):
        return self.properties.get(key, default)
    
    def safe_get(self, *keys, default=""):
        current = self.properties
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key, {})
            else:
                return default
        return current if current != {} else default
    
    def get_nested(self, nested_key, property_key, default=""):
        nested_obj = self.properties.get(nested_key, {})
        if isinstance(nested_obj, dict):
            return nested_obj.get(property_key, default)
        return default
