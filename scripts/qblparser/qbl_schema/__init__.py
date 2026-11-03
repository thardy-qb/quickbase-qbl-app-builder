from .v2_forms import FORM_ELEMENTS_SCHEMA
from .v2_form_rules import FORM_RULE_SCHEMA
from .legacy_forms import LEGACY_FORM_SCHEMA
from .legacy_dynamic_form_rules import LEGACY_DYNAMIC_FORM_RULES_SCHEMA
from .relationships import RELATIONSHIPS_SCHEMA
from .roles import ROLES_SCHEMA
from .reports import REPORT_SCHEMA
from .applications import APPLICATION_SCHEMA
from .charts import CHART_SCHEMA
from .dashboards import DASHBOARD_SCHEMA
from .field_properties import FIELD_PROPERTIES_SCHEMA
from .formula_fields import FORMULA_FIELD_SCHEMA
from .pipelines import PIPELINE_SCHEMA
from .tables import TABLES_SCHEMA
from .custom_emails import CUSTOM_EMAIL_SCHEMA, NESTED_DOCUMENTED_PROPERTIES
from .document_templates import DOCUMENT_TEMPLATE_SCHEMA
from .connected_tables import CONNECTED_TABLE_SCHEMA
from .pages import PAGES_SCHEMA
from .platform_requirements import PLATFORM_REQUIRED, REQUIRES_NODE_ID
from .nested import KEYED_PATHS, NESTED_REQUIRED
from .versioned import without_renamed

from .property_profiles import PROPERTY_PROFILES
from .schema_types import (
    SCHEMA_ENUMS,
    SCHEMA_REQUIRED,
    SCHEMA_REQUIRES_NODE_ID,
    SCHEMA_TYPES,
)
from .aliases import TYPE_ALIASES, canonical_type
from .schema_rules import (
    NODE_ID_NOT_ENFORCED,
    PLATFORM_PERMITS,
    PLATFORM_REJECTS,
    node_id_is_enforced,
)
from dataclasses import replace as _replace

from .model import PropertySpec, ResourceSpec, build_registry, derive_qbl_schema

def _base_copy(schema):
    copied = {}
    for qbl_type, entry in schema.items():
        new_entry = dict(entry)
        for key in ("required", "optional"):
            if key in new_entry:
                new_entry[key] = list(new_entry[key])
        copied[qbl_type] = new_entry
    return copied


BASE_SCHEMA = {}
for _module_schema in (
    FORM_ELEMENTS_SCHEMA,
    FORM_RULE_SCHEMA,
    LEGACY_FORM_SCHEMA,
    LEGACY_DYNAMIC_FORM_RULES_SCHEMA,
    RELATIONSHIPS_SCHEMA,
    ROLES_SCHEMA,
    REPORT_SCHEMA,
    APPLICATION_SCHEMA,
    CHART_SCHEMA,
    DASHBOARD_SCHEMA,
    FIELD_PROPERTIES_SCHEMA,
    FORMULA_FIELD_SCHEMA,
    PIPELINE_SCHEMA,
    TABLES_SCHEMA,
    CUSTOM_EMAIL_SCHEMA,
    DOCUMENT_TEMPLATE_SCHEMA,
    CONNECTED_TABLE_SCHEMA,
    PAGES_SCHEMA,
):
    BASE_SCHEMA.update(_base_copy(_module_schema))

COMMON_FIELD_PROPERTIES = ("DefaultColumnWidth",)


def _apply_common_field_properties(schema):
    for resource_type, definition in schema.items():
        if not resource_type.startswith("QB::Field::") or resource_type.endswith("Block"):
            continue
        optional = definition.get("optional")
        if not isinstance(optional, list):
            continue
        for prop in COMMON_FIELD_PROPERTIES:
            if prop not in optional and prop not in definition.get("required", []):
                optional.append(prop)


FORM_ELEMENT_LABEL_PROPERTY = "Label"


def _apply_form_element_label(schema):
    for resource_type, definition in schema.items():
        if not resource_type.startswith("QB::Form::Element::"):
            continue
        if not resource_type.endswith("Field"):
            continue
        optional = definition.get("optional")
        if not isinstance(optional, list):
            continue
        if (FORM_ELEMENT_LABEL_PROPERTY not in optional
                and FORM_ELEMENT_LABEL_PROPERTY not in definition.get("required", [])):
            optional.append(FORM_ELEMENT_LABEL_PROPERTY)


def _fold_schema_definitions(curated):
    for qbl_type, facts in SCHEMA_TYPES.items():
        if qbl_type in PLATFORM_REJECTS:
            continue
        entry = curated.setdefault(qbl_type, {"required": [], "optional": []})
        required = list(entry.get("required") or ())
        optional = list(entry.get("optional") or ())
        for prop in SCHEMA_REQUIRED.get(qbl_type, ()):
            if prop not in required:
                required.append(prop)
        known = set(required)
        for prop in facts.get("properties", ()):
            if prop not in known and prop not in optional:
                optional.append(prop)
        entry["required"] = required
        entry["optional"] = [prop for prop in optional if prop not in known]


_fold_schema_definitions(BASE_SCHEMA)


for _qbl_type, _required in PLATFORM_REQUIRED.items():
    _entry = BASE_SCHEMA.setdefault(_qbl_type, {"required": [], "optional": []})
    _was = set(_entry.get("required", []))
    _entry["required"] = list(_required)
    _optional = [_prop for _prop in _entry.get("optional", []) if _prop not in set(_required)]
    for _prop in sorted(_was - set(_required)):
        if _prop not in _optional:
            _optional.append(_prop)
    _entry["optional"] = _optional

QBL_REGISTRY = build_registry(BASE_SCHEMA, PROPERTY_PROFILES)
REQUIRES_NODE_ID_ALL = tuple(sorted(
    set(REQUIRES_NODE_ID)
    | {t for t in SCHEMA_REQUIRES_NODE_ID if node_id_is_enforced(t)}
))
for _qbl_type in REQUIRES_NODE_ID_ALL:
    _spec = QBL_REGISTRY.get(_qbl_type)
    if _spec is not None:
        QBL_REGISTRY[_qbl_type] = _replace(_spec, requires_node_id=True)

QBL_SCHEMA = derive_qbl_schema(QBL_REGISTRY)


def _merge_alias_entries(schema, registry):
    for alias, canonical in TYPE_ALIASES.items():
        variant = schema.get(alias)
        target = schema.get(canonical)
        if target is None:
            continue
        if variant is not None:
            required = list(target.get("required") or ())
            known = set(required)
            optional = list(target.get("optional") or ())
            for prop in variant.get("optional") or ():
                if prop not in known and prop not in optional:
                    optional.append(prop)
            target["required"] = required
            target["optional"] = optional
        schema[alias] = schema[canonical]
        if canonical in registry:
            registry[alias] = registry[canonical]


_merge_alias_entries(QBL_SCHEMA, QBL_REGISTRY)

_apply_common_field_properties(QBL_SCHEMA)
_apply_form_element_label(QBL_SCHEMA)


def _apply_platform_permits(schema):
    for resource_type, permitted in PLATFORM_PERMITS.items():
        definition = schema.get(resource_type)
        if definition is None:
            continue
        optional = definition.setdefault("optional", [])
        for prop in permitted:
            if prop not in optional and prop not in definition.get("required", []):
                optional.append(prop)


_apply_platform_permits(QBL_SCHEMA)


def _nested_tree(paths, keyed):
    tree = {}
    for path, required in sorted(paths.items()):
        node = tree
        parts = path.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {}).setdefault("nested", {})
        node.setdefault(parts[-1], {})["required"] = list(required)
    for path, spec in (keyed or {}).items():
        node = tree
        parts = path.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {}).setdefault("nested", {})
        entry = node.setdefault(parts[-1], {})
        entry["keyed"] = {
            "required": list(spec.get("required", ())),
            "required_keys": list(spec.get("required_keys", ())),
        }
        entry.pop("required", None)
    return tree


for _qbl_type, _paths in without_renamed(NESTED_REQUIRED).items():
    _entry = QBL_SCHEMA.get(_qbl_type)
    if _entry is not None:
        _entry["nested"] = _nested_tree(_paths, KEYED_PATHS.get(_qbl_type))
for _qbl_type, _keyed in KEYED_PATHS.items():
    _entry = QBL_SCHEMA.get(_qbl_type)
    if _entry is not None and "nested" not in _entry:
        _entry["nested"] = _nested_tree({}, _keyed)


def get_resource_spec(qbl_type):
    return QBL_REGISTRY.get(qbl_type)
