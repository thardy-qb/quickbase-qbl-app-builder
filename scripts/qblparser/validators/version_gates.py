from __future__ import annotations

from typing import Any, Iterator, List, Mapping, Tuple

from qblparser.contracts import QBLIssue
from qblparser.qbl_schema.versioned import (
    INTRODUCED_PROPERTIES,
    INTRODUCED_TYPES,
    RENAMED_NESTED,
    version_key,
)

from .base_validator import schema_issue


def _iter_typed_nodes(qbl: Mapping[str, Any]) -> Iterator[Tuple[str, str, Mapping[str, Any], str]]:

    def walk(node: Any, logical_id: str, path: str):
        if isinstance(node, Mapping):
            qbl_type = node.get("Type")
            if isinstance(qbl_type, str) and qbl_type.startswith("QB::"):
                yield logical_id, qbl_type, node, path
            for key, value in node.items():
                child_id = key if isinstance(key, str) and key.startswith("$") else logical_id
                child_path = f"{path} > {key}" if path else str(key)
                yield from walk(value, child_id, child_path)
        elif isinstance(node, list):
            for index, item in enumerate(node):
                yield from walk(item, logical_id, f"{path}[{index}]")

    for section in ("Resources", "ExternalResources"):
        resources = qbl.get(section)
        if isinstance(resources, Mapping):
            for key, value in resources.items():
                yield from walk(value, str(key), str(key))


def validate_version_gates(qbl: Any, version: Any) -> List[QBLIssue]:
    key = version_key(version)
    if key is None or not isinstance(qbl, Mapping):
        return []

    issues: List[QBLIssue] = []
    for logical_id, qbl_type, node, path in _iter_typed_nodes(qbl):
        introduced = INTRODUCED_TYPES.get(qbl_type)
        if introduced and key < version_key(introduced):
            issues.append(schema_issue(
                "SCH010", logical_id, path, qbl_type,
                f"'{qbl_type}' was added in QBL {introduced}; at {version} the "
                f"platform answers NodeRemoved, a warning, and the pipeline deploys "
                f"without this step",
            ))

        properties = node.get("Properties")
        if not isinstance(properties, Mapping):
            continue

        for prop in properties:
            introduced = INTRODUCED_PROPERTIES.get((qbl_type, str(prop)))
            if introduced and key < version_key(introduced):
                issues.append(schema_issue(
                    "SCH011", logical_id, path, qbl_type,
                    f"'{prop}' was added in QBL {introduced}; at {version} the "
                    f"platform answers ExtraProperty, a warning, and the setting "
                    f"is not applied",
                ))

        for rename in RENAMED_NESTED.get(qbl_type, ()):
            container = properties.get(rename.path)
            if not isinstance(container, Mapping):
                continue
            wanted = rename.name_at(version)
            other = rename.before if wanted == rename.after else rename.after
            if wanted not in container:
                problem = f"Missing required property '{rename.path}.{wanted}'"
                if other in container:
                    problem += (
                        f": '{other}' is the name before QBL {rename.since}"
                        if other == rename.before else
                        f": '{other}' is the name from QBL {rename.since}"
                    )
                    problem += (f", and a document declaring {version} needs "
                                f"'{wanted}' - the platform ignores the other name")
                issues.append(schema_issue("SCH005", logical_id, path, qbl_type, problem))
                continue
            body = container.get(wanted)
            if not isinstance(body, Mapping):
                continue
            for required in rename.required:
                if required not in body:
                    issues.append(schema_issue(
                        "SCH005", logical_id, path, qbl_type,
                        f"Missing required property '{rename.path}.{wanted}.{required}'",
                    ))
    return issues
