from abc import ABC, abstractmethod

class BaseVersionHandler(ABC):
    
    def __init__(self, table_schema=None, identifier_index=None):
        self.table_schema = table_schema
        self.identifier_index = identifier_index
    
    @abstractmethod
    def get_version(self):
        pass
    
    @abstractmethod
    def get_supported_entities(self):
        pass
    
    @abstractmethod
    def parse_qbl(self, qbl_data):
        pass
    
