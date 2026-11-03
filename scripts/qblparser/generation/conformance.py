from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

from qblparser.qbl_schema import property_profiles
from qblparser.qbl_schema.type_support import SUPPORTED_TYPES

from .merge import iter_resources


CREATABLE_TYPES = frozenset({
    "QB::Chart::Area3D",
    "QB::Chart::AreaSpline",
    "QB::Chart::Bar3D",
    "QB::Chart::Heatmap",
    "QB::Chart::ProgressBar",
    "QB::Chart::Scatter3D",
    "QB::Chart::Spline",
    "QB::Chart::StackedBar3D",
    "QB::Chart::Streamgraph",
    "QB::Chart::VariwideBar",
    *(f"QB::Report::{family}::{kind}"
      for family in ("Formula", "SummaryFormula")
      for kind in ("DateTime", "EmailAddress", "ListUsers", "MultiSelectText",
                   "NumericCurrency", "NumericRating", "PhoneNumber",
                   "TimeOfDay", "User")),
    *(f"QB::Report::SummaryFormula::{kind}"
      for kind in ("Checkbox", "Date", "Duration", "URL")),
    "QB::FormRule::Condition::FieldChange",
    "QB::FormRule::Condition::FieldIncludes",
    "QB::FormRule::Trigger::FieldIncludes",
})

def _create_established_domains() -> Dict[tuple, Iterable[str]]:
    from .compiler import KNOWN_TABLE_ICONS

    return {("QB::Table", "TableIconName"): KNOWN_TABLE_ICONS}


def _issue(code: str, severity: str, problem: str, path: str) -> Dict[str, Any]:
    return {"Code": code, "Severity": severity, "Problem": problem,
            "Location": path}


def _unsupported_types(document: Mapping[str, Any]) -> List[Dict[str, Any]]:
    issues = []
    for path, node in iter_resources(document):
        qbl_type = node.get("Type")
        if not isinstance(qbl_type, str) or not qbl_type.startswith("QB::"):
            continue
        if qbl_type in SUPPORTED_TYPES or qbl_type in CREATABLE_TYPES:
            continue
        issues.append(_issue(
            "GEN001", "Error",
            f"{qbl_type} is not a type this generator supports, so nothing "
            f"establishes that Quickbase can create it. QB::Chart::Donut was "
            f"in exactly this position and cannot be created: the create "
            f"times out with no diagnostic. Use a supported type.",
            str(path)))
    return issues


def _missing_universals(document: Mapping[str, Any]) -> List[Dict[str, Any]]:
    issues = []
    for path, node in iter_resources(document):
        qbl_type = node.get("Type")
        spec = property_profiles.PROPERTY_PROFILES.get(qbl_type)
        if spec is None:
            continue
        present = set((node.get("Properties") or {}).keys())
        for name, prop in sorted(spec.properties.items()):
            if prop.required_in_practice and name not in present:
                issues.append(_issue(
                    "GEN002", "Warning",
                    f"{qbl_type} carries {name} in every reference instance and "
                    f"this one does not. Often harmless - an export writes "
                    f"every property whether it was set or not - but this is "
                    f"the shape the SearchTable failure took.",
                    str(path)))
    return issues


def _bad_values(document: Mapping[str, Any]) -> List[Dict[str, Any]]:
    domains = _create_established_domains()
    issues = []
    for path, node in iter_resources(document):
        qbl_type = node.get("Type")
        for name, value in ((node.get("Properties") or {})).items():
            domain = domains.get((qbl_type, name))
            if domain is None or value is None:
                continue
            if value not in domain:
                issues.append(_issue(
                    "GEN003", "Error",
                    f"{qbl_type}.{name} is {value!r}, which is not a value the "
                    f"platform is known to accept. It will not be rejected - it "
                    f"will be silently replaced, and the application will "
                    f"deploy looking correct and be wrong.",
                    str(path)))
    return issues


CHECKS = (_unsupported_types, _missing_universals, _bad_values)


def check_conformance(document: Mapping[str, Any], *,
                      codes: Iterable[str] = ("GEN001", "GEN002", "GEN003"),
                      ) -> List[Dict[str, Any]]:
    wanted = set(codes)
    issues: List[Dict[str, Any]] = []
    for check in CHECKS:
        issues.extend(i for i in check(document) if i["Code"] in wanted)
    return issues


__all__ = ["CREATABLE_TYPES", "check_conformance"]
