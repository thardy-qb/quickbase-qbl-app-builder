from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Mapping, Optional, Tuple


@dataclass(frozen=True)
class PropertySpec:

    name: str
    kinds: Tuple[str, ...] = ()

    enum: Optional[Tuple[str, ...]] = None

    ref_targets: Tuple[str, ...] = ()

    required_in_practice: bool = False

    kind_checkable: bool = False

    @property
    def is_reference(self) -> bool:
        return "reference" in self.kinds


@dataclass(frozen=True)
class ResourceSpec:

    qbl_type: str
    required: Tuple[str, ...] = ()
    optional: Tuple[str, ...] = ()
    properties: Mapping[str, PropertySpec] = field(default_factory=dict)
    containers: Tuple[str, ...] = ()

    logical_id_prefixes: Tuple[str, ...] = ()

    child_containers: Tuple[str, ...] = ()

    requires_node_id: bool = False

    open_properties: bool = False

    def legacy_entry(self) -> Dict[str, object]:
        entry: Dict[str, object] = {
            "required": list(self.required),
            "optional": list(self.optional),
        }
        if self.open_properties:
            entry["open"] = True
        return entry


def spec_from_legacy(qbl_type: str, entry: Mapping[str, Iterable[str]]) -> ResourceSpec:
    return ResourceSpec(
        qbl_type=qbl_type,
        required=tuple(entry.get("required", ()) or ()),
        optional=tuple(entry.get("optional", ()) or ()),
    )


def merge_specs(curated: ResourceSpec, reference: ResourceSpec) -> ResourceSpec:
    known = set(curated.required) | set(curated.optional)
    added = tuple(sorted(name for name in reference.properties if name not in known))

    return ResourceSpec(
        qbl_type=curated.qbl_type,
        required=curated.required,
        optional=curated.optional + added,
        properties=reference.properties or curated.properties,
        containers=reference.containers or curated.containers,
        logical_id_prefixes=reference.logical_id_prefixes or curated.logical_id_prefixes,
        child_containers=reference.child_containers or curated.child_containers,
        open_properties=curated.open_properties or reference.open_properties,
        requires_node_id=curated.requires_node_id or reference.requires_node_id,
    )


def build_registry(
    curated: Mapping[str, Mapping[str, Iterable[str]]],
    reference: Mapping[str, ResourceSpec],
) -> Dict[str, ResourceSpec]:
    registry: Dict[str, ResourceSpec] = {}

    for qbl_type, entry in curated.items():
        spec = spec_from_legacy(qbl_type, entry)
        reference_spec = reference.get(qbl_type)
        registry[qbl_type] = merge_specs(spec, reference_spec) if reference_spec else spec

    for qbl_type, reference_spec in reference.items():
        if qbl_type not in registry:
            registry[qbl_type] = reference_spec

    return registry


def derive_qbl_schema(registry: Mapping[str, ResourceSpec]) -> Dict[str, Dict[str, list]]:
    return {qbl_type: spec.legacy_entry() for qbl_type, spec in registry.items()}
