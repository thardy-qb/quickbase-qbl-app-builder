from .v07 import QBLv07Handler
from qblparser.parsing_registry import PARSING_REGISTRY


def parse_pages(qbl_data, identifier_index):
    pages = []
    resources = qbl_data.get("Resources", {})

    for resource_key, resource_value in resources.items():
        if not resource_key.startswith("$App_"):
            continue

        pages_section = resource_value.get("Pages", {})
        if not pages_section:
            continue

        for page_key, page_value in pages_section.get("Resources", {}).items():
            if not page_key.startswith("$Page_"):
                continue
            try:
                pages.append(
                    PARSING_REGISTRY["page"](
                        page_key, page_value, identifier_index, resource_key, pages_section
                    )
                )
            except Exception as e:
                print(f"Error parsing page {page_key}: {e}")
                continue

    return pages


def parse_guides(qbl_data, identifier_index):
    guides = []
    resources = qbl_data.get("Resources", {})

    for resource_key, resource_value in resources.items():
        if not resource_key.startswith("$App_"):
            continue
        if not isinstance(resource_value, dict):
            continue

        guides_section = resource_value.get("Guides", {})
        if not isinstance(guides_section, dict):
            continue

        for guide_key, guide_value in guides_section.items():
            if not guide_key.startswith("$AppGuide_"):
                continue
            if not isinstance(guide_value, dict):
                continue
            try:
                guides.append(
                    PARSING_REGISTRY["guide"](
                        guide_key, guide_value, identifier_index, resource_key
                    )
                )
            except Exception as e:
                print(f"Error parsing guide {guide_key}: {e}")
                continue

    return guides


def parse_page_widgets(qbl_data, identifier_index):
    widgets = []
    resources = qbl_data.get("Resources", {})

    for resource_key, resource_value in resources.items():
        if not resource_key.startswith("$App_") or not isinstance(resource_value, dict):
            continue
        pages_section = resource_value.get("Pages", {})
        if not isinstance(pages_section, dict):
            continue
        for page_key, page_value in (pages_section.get("Resources") or {}).items():
            if not page_key.startswith("$Page_") or not isinstance(page_value, dict):
                continue
            try:
                widgets.extend(
                    PARSING_REGISTRY["page_widget"](page_key, page_value, resource_key)
                )
            except Exception as e:
                print(f"Error parsing widgets for page {page_key}: {e}")
                continue

    return widgets


class QBLv011Handler(QBLv07Handler):
    
    
    def get_version(self):
        return "0.11"
    
    def get_supported_entities(self):
        entities = super().get_supported_entities()
        entities.extend(["pages", "guides", "page_widgets"])
        return entities
    
    def parse_qbl(self, qbl_data):
        parsed_entities = super().parse_qbl(qbl_data)
        
        parsed_entities["pages"] = self._parse_pages(qbl_data)
        parsed_entities["guides"] = self._parse_guides(qbl_data)
        parsed_entities["page_widgets"] = self._parse_page_widgets(qbl_data)
        
        return parsed_entities
    
    def _parse_pages(self, qbl_data):
        return parse_pages(qbl_data, self.identifier_index)

    def _parse_guides(self, qbl_data):
        return parse_guides(qbl_data, self.identifier_index)

    def _parse_page_widgets(self, qbl_data):
        return parse_page_widgets(qbl_data, self.identifier_index)
