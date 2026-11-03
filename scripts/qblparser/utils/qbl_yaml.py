import re

import yaml

from .qbl_tags import (
    QBLTaggedMapping,
    QBLTaggedScalar,
    QBLTaggedSequence,
    make_scalar_bad_ref,
    make_scalar_ref,
    tag_of,
)


VALUE_TAG = "tag:yaml.org,2002:value"

PARAMETERS_KEY = "Parameters"


BOOLEAN_TAG = "tag:yaml.org,2002:bool"
BOOLEAN_PATTERN = re.compile(r"^(?:true|false)$")


def _use_yaml_12_booleans(cls):
    cls.yaml_implicit_resolvers = {
        first: [(tag, regexp) for tag, regexp in resolvers if tag != BOOLEAN_TAG]
        for first, resolvers in cls.yaml_implicit_resolvers.items()
    }
    cls.add_implicit_resolver(BOOLEAN_TAG, BOOLEAN_PATTERN, list("tf"))
    return cls


class QBLSafeLoader(yaml.SafeLoader):
    pass


_use_yaml_12_booleans(QBLSafeLoader)


def _unknown_tag_constructor(loader, tag_suffix, node):
    if isinstance(node, yaml.MappingNode):
        mapping = QBLTaggedMapping(loader.construct_mapping(node))
        return mapping.with_tag(tag_suffix)

    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
        if tag_suffix == "BadRef":
            return make_scalar_bad_ref(value)
        if tag_suffix == "Ref":
            return make_scalar_ref(value)
        return QBLTaggedScalar(value, tag_suffix)

    if isinstance(node, yaml.SequenceNode):
        sequence = QBLTaggedSequence(loader.construct_sequence(node))
        return sequence.with_tag(tag_suffix)

    return None


def _yaml_value_constructor(loader, node):
    return loader.construct_scalar(node)


QBLSafeLoader.add_multi_constructor("!", _unknown_tag_constructor)
QBLSafeLoader.add_constructor(VALUE_TAG, _yaml_value_constructor)


_SEQUENCE_ENTRY = re.compile(r"^(\s*)-(?: |$)")
_MAPPING_KEY = re.compile(r"^(\s*)[^\s#-][^:]*:\s*$")


class QBLDocument(dict):

    indent_sequences = False
    parameter_overrides = None

    def __reduce__(self):
        return (
            _rebuild_document,
            (dict(self), self.indent_sequences, self.parameter_overrides),
        )

    def copy(self) -> "QBLDocument":
        return _rebuild_document(
            dict(self), self.indent_sequences, self.parameter_overrides
        )


def _rebuild_document(data, indent_sequences, parameter_overrides=None):
    document = QBLDocument(data)
    document.indent_sequences = indent_sequences
    document.parameter_overrides = parameter_overrides
    return document


def detect_sequence_indent(text):
    indented = flush = 0
    key_indent = None

    for line in text.splitlines():
        key = _MAPPING_KEY.match(line)
        if key:
            key_indent = len(key.group(1))
            continue

        entry = _SEQUENCE_ENTRY.match(line)
        if not entry or key_indent is None:
            continue

        entry_indent = len(entry.group(1))
        if entry_indent > key_indent:
            indented += 1
        elif entry_indent == key_indent:
            flush += 1
        key_indent = None

    return indented > flush


def _split_parameter_documents(documents):
    if not documents:
        return None, None

    primary, trailing = documents[0], documents[1:]
    if not trailing:
        return primary, None

    overrides = {}
    for position, document in enumerate(trailing, start=2):
        if document is None:
            continue
        if not isinstance(document, dict) or set(document) - {PARAMETERS_KEY}:
            raise ValueError(
                f"document {position} of the YAML stream is not a QBL "
                f"'{PARAMETERS_KEY}' block; only a trailing "
                f"'{PARAMETERS_KEY}' document is defined by QBL"
            )
        values = document.get(PARAMETERS_KEY)
        if values is None:
            continue
        if not isinstance(values, dict):
            raise ValueError(
                f"'{PARAMETERS_KEY}' in document {position} of the YAML stream "
                "must be a mapping of parameter name to value"
            )
        overrides.update(values)

    return primary, overrides


def load_qbl_yaml(source):
    if not isinstance(source, str):
        source = source.read()

    data, overrides = _split_parameter_documents(
        list(yaml.load_all(source, Loader=QBLSafeLoader))
    )
    if not isinstance(data, dict):
        return data
    return _rebuild_document(data, detect_sequence_indent(source), overrides)


class QBLDumper(yaml.SafeDumper):

    def ignore_aliases(self, data):
        return True

    def represent_mapping(self, tag, mapping, flow_style=None):
        node = super().represent_mapping(tag, mapping, flow_style=flow_style)
        for key_node, value_node in node.value:
            if (
                getattr(key_node, "value", None) in BLOCK_STYLE_PROPERTIES
                and value_node.tag == "tag:yaml.org,2002:str"
                and value_node.value
                and value_node.value != SENTINEL_VALUE
            ):
                value_node.style = "|"
        return node

    def choose_scalar_style(self):
        style = super().choose_scalar_style()
        if style == "'" and self.event.style == "" and self.analysis and self.analysis.allow_block_plain:
            return ""
        return style


def _represent_tagged_mapping(dumper, data):
    tag = tag_of(data)
    if not tag:
        return dumper.represent_dict(dict(data))

    if tag == "Ref" and data.get("__ref__") is True:
        return dumper.represent_scalar("!Ref", str(data.get("value", "")), style="")
    if tag == "BadRef" and data.get("__bad_ref__") is True:
        return dumper.represent_scalar("!BadRef", str(data.get("message", "")), style='"')

    return dumper.represent_mapping(f"!{tag}", dict(data))


def _represent_tagged_sequence(dumper, data):
    tag = tag_of(data)
    if not tag:
        return dumper.represent_list(list(data))
    return dumper.represent_sequence(f"!{tag}", list(data))


def _represent_tagged_scalar(dumper, data):
    tag = tag_of(data)
    if not tag:
        return dumper.represent_str(str(data))
    return dumper.represent_scalar(f"!{tag}", str(data))


SENTINEL_VALUE = "Default"

BLOCK_STYLE_PROPERTIES = frozenset({
    "ColorFormula",
    "Content",
    "Criteria",
    "CustomAccessCriteria",
    "Formula",
    "Query",
    "RawCode",
})


def _represent_str(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


def _represent_none(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:null", "")


_use_yaml_12_booleans(QBLDumper)

QBLDumper.add_representer(str, _represent_str)
QBLDumper.add_representer(type(None), _represent_none)
QBLDumper.add_representer(QBLTaggedMapping, _represent_tagged_mapping)
QBLDumper.add_representer(QBLTaggedSequence, _represent_tagged_sequence)
QBLDumper.add_representer(QBLTaggedScalar, _represent_tagged_scalar)


def _represent_document(dumper, data):
    return dumper.represent_dict(dict(data))


QBLDumper.add_representer(QBLDocument, _represent_document)


_NUMERIC_VERSION = re.compile(r"^\d+\.\d+$")


class _VersionScalar(str):
    pass


def _represent_version(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:float", str(data), style="")


QBLDumper.add_representer(_VersionScalar, _represent_version)


def _normalize_version_for_emit(qbl_data):
    if not isinstance(qbl_data, dict):
        return qbl_data
    version = qbl_data.get("Version")
    if not isinstance(version, str) or not _NUMERIC_VERSION.match(version):
        return qbl_data
    normalized = dict(qbl_data)
    normalized["Version"] = _VersionScalar(version)
    return normalized


class QBLIndentedDumper(QBLDumper):

    def expect_block_sequence(self):
        self.increase_indent(flow=False, indentless=False)
        self.state = self.expect_first_block_sequence_item


def dump_qbl_yaml(qbl_data, stream=None, *, width=1_000_000, indent_sequences=None):
    if indent_sequences is None:
        indent_sequences = getattr(qbl_data, "indent_sequences", False)

    documents = [_normalize_version_for_emit(qbl_data)]
    overrides = getattr(qbl_data, "parameter_overrides", None)
    if overrides is not None:
        documents.append({PARAMETERS_KEY: overrides})

    return yaml.dump_all(
        documents,
        stream,
        Dumper=QBLIndentedDumper if indent_sequences else QBLDumper,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=width,
    )
