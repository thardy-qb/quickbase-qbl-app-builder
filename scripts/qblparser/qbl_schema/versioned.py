from __future__ import annotations

from typing import Dict, NamedTuple, Optional, Tuple

from .schema_types import SCHEMA_TYPES


def version_key(version) -> Optional[Tuple[int, ...]]:
    if isinstance(version, bool) or version is None:
        return None
    text = format(version, "g") if isinstance(version, (int, float)) else str(version).strip()
    try:
        return tuple(int(part) for part in text.split("."))
    except ValueError:
        return None


def _introduced_pipeline_steps() -> Dict[str, str]:
    introduced = {}
    for qbl_type, facts in SCHEMA_TYPES.items():
        if not qbl_type.startswith("QB::PipelineStep::"):
            continue
        versions = facts.get("versions") or ()
        if versions and min(versions) == 15:
            introduced[qbl_type] = "0.15"
    return introduced


INTRODUCED_TYPES: Dict[str, str] = _introduced_pipeline_steps()

INTRODUCED_PROPERTIES: Dict[Tuple[str, str], str] = {
    ("QB::Application", "CustomAppMessages"): "0.15",
}


class RenamedProperty(NamedTuple):

    path: str
    before: str
    after: str
    since: str
    required: Tuple[str, ...]

    def name_at(self, version) -> str:
        key = version_key(version)
        return self.after if key is not None and key >= version_key(self.since) else self.before


RENAMED_NESTED: Dict[str, Tuple[RenamedProperty, ...]] = {
    "QB::Chart::Scatter3D": (
        RenamedProperty(path="DataDetails", before="XAxis", after="ZAxis",
                        since="0.15", required=("Source",)),
    ),
}


def without_renamed(nested_required: Dict[str, Dict[str, list]]) -> Dict[str, Dict[str, list]]:
    result = {qbl_type: {path: list(names) for path, names in paths.items()}
              for qbl_type, paths in nested_required.items()}
    for qbl_type, renames in RENAMED_NESTED.items():
        paths = result.get(qbl_type)
        if not paths:
            continue
        for rename in renames:
            names = paths.get(rename.path)
            if names is not None:
                paths[rename.path] = [n for n in names if n not in (rename.before, rename.after)]
            for name in (rename.before, rename.after):
                paths.pop(f"{rename.path}.{name}", None)
    return result
