from __future__ import annotations

from typing import Any, Dict, FrozenSet, Mapping

from .qbl_tags import QBLTaggedMapping, QBLTaggedSequence, tag_of


VAR_TAG = "Var"
PARAMETER_DEFINITIONS_KEY = "ParameterDefinitions"


def build_parameter_map(qbl_data: Mapping[str, Any]) -> Dict[str, Any]:
    definitions = qbl_data.get(PARAMETER_DEFINITIONS_KEY, {}) if isinstance(qbl_data, Mapping) else {}

    parameters: Dict[str, Any] = {}
    if isinstance(definitions, Mapping):
        for name, definition in definitions.items():
            if isinstance(definition, Mapping) and "Value" in definition:
                parameters[str(name)] = definition["Value"]

    overrides = getattr(qbl_data, "parameter_overrides", None)
    if isinstance(overrides, Mapping):
        for name, value in overrides.items():
            parameters[str(name)] = value

    return parameters


def _is_var_reference(node: Any) -> bool:
    return isinstance(node, Mapping) and tag_of(node) == VAR_TAG and "Name" in node


def _rebuild_like(original: Any, contents: Any) -> Any:
    tag = tag_of(original)
    if tag is None:
        return contents
    if isinstance(contents, dict):
        return QBLTaggedMapping(contents).with_tag(tag)
    if isinstance(contents, list):
        return QBLTaggedSequence(contents).with_tag(tag)
    return contents


def resolve_parameters(
    node: Any,
    parameters: Mapping[str, Any],
    _resolving: FrozenSet[str] = frozenset(),
) -> Any:
    if not parameters:
        return node

    if _is_var_reference(node):
        name = str(node.get("Name", ""))
        if name in _resolving:
            return node
        if name in parameters:
            return resolve_parameters(parameters[name], parameters, _resolving | {name})
        return node

    if isinstance(node, Mapping):
        resolved = {
            key: resolve_parameters(value, parameters, _resolving)
            for key, value in node.items()
        }
        if all(resolved[key] is node[key] for key in node):
            return node
        return _rebuild_like(node, resolved)

    if isinstance(node, (list, tuple)):
        resolved_items = [
            resolve_parameters(item, parameters, _resolving) for item in node
        ]
        if all(new is old for new, old in zip(resolved_items, node)):
            return node
        return _rebuild_like(node, resolved_items)

    return node


def resolve_document(qbl_data: Mapping[str, Any]) -> Any:
    return resolve_parameters(qbl_data, build_parameter_map(qbl_data))
