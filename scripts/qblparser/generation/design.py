from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List

from qblparser.generation.spec import AppSpec, TableRolePermissionSpec

FULL_ACCESS = TableRolePermissionSpec(
    can_add=True, can_delete=True, can_save_common_reports=True,
    can_edit_field_properties=True, view_records="Always", modify_records="Always")

DEFAULT_ROLE_NAMES = ("viewer", "participant", "administrator")

YEAR = r"(?:19|20)\d{2}"
YEAR_TOKEN = re.compile(
    rf"(?<![A-Za-z0-9]){YEAR}(?:\s*-\s*(?:{YEAR}|present))?(?![A-Za-z0-9])",
    re.IGNORECASE)

TRAILING_NUMBER = re.compile(r"^(.*?\D)\s*(\d{1,2})$")

NUMBER_THRESHOLD = 3


def _finding(code: str, table: str, problem: str, fix: str) -> Dict[str, Any]:
    return {
        "Code": code,
        "Severity": "Warning",
        "Problem": problem,
        "Location": f"$Table_{re.sub(r'[^A-Za-z0-9]+', '_', table).strip('_')}",
        "Fix": fix,
    }


def _plain(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def check_design(spec: AppSpec) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []

    for table in spec.tables:
        labels = [f.label for f in table.fields]

        by_stem: Dict[str, List[str]] = defaultdict(list)
        for label in labels:
            if YEAR_TOKEN.search(label):
                stem = re.sub(r"\s+", " ", YEAR_TOKEN.sub("{year}", label)).strip()
                by_stem[stem].append(label)
        undated = {_plain(label) for label in labels if not YEAR_TOKEN.search(label)}
        series = {stem: group for stem, group in by_stem.items()
                  if len(group) >= 2 or _plain(stem.replace("{year}", "")) in undated}
        dated = [label for group in series.values() for label in group]
        if series:
            stems = sorted(series.items(), key=lambda item: (-len(item[1]), item[0]))
            shown = ", ".join(f"'{stem}' x{len(group)}" for stem, group in stems[:6])
            more = f", and {len(stems) - 6} more" if len(stems) > 6 else ""
            findings.append(_finding(
                "DSN001", table.name,
                f"'{table.name}' has {len(dated)} fields whose labels carry a year "
                f"({shown}{more}). A year in a field label is a row in disguise: "
                f"every new year needs new fields, formulas and reports, and "
                f"nothing can total by year because the year is not a value.",
                f"Model the series as a child table of '{table.name}' with a Year "
                f"field - and a field for whatever else the labels vary by, such "
                f"as a committee or a gift-versus-raised kind - holding one record "
                f"per combination. Rollups and summary reports then give each "
                f"total the separate fields were holding. Keep a dated label only "
                f"where it is one fact rather than a series."))

        by_prefix: Dict[str, List[str]] = defaultdict(list)
        for label in labels:
            match = TRAILING_NUMBER.match(label)
            if match:
                by_prefix[match.group(1).strip().lower()].append(label)
        for prefix, group in sorted(by_prefix.items()):
            base = next((label for label in labels
                         if label.strip().lower() == prefix), None)
            members = group + ([base] if base else [])
            if len(members) >= NUMBER_THRESHOLD:
                findings.append(_finding(
                    "DSN002", table.name,
                    f"'{table.name}' numbers {len(members)} fields that hold the "
                    f"same thing: {', '.join(sorted(members))}. Numbered siblings "
                    f"are a list with a fixed length, and the next one needs a new "
                    f"field.",
                    f"Model them as a child table of '{table.name}' with one record "
                    f"per entry, or confirm the count really is fixed."))

        required = [f.label for f in table.fields if f.required]
        if required:
            findings.append(_finding(
                "DSN003", table.name,
                f"'{table.name}' requires {len(required)} field(s): "
                f"{', '.join(required)}. A required field refuses to save any record "
                f"without a value - new ones, existing ones being edited, and ones "
                f"brought in by an import.",
                "Keep a field required only where the requirements say the value "
                "is mandatory, or something they asked for cannot work without it, "
                "and record the reason in its comments. Otherwise leave it optional "
                "and list it as an assumption to confirm."))

        helped = [f.label for f in table.fields if f.help_text]
        if helped:
            findings.append(_finding(
                "DSN004", table.name,
                f"'{table.name}' shows help text on {len(helped)} field(s): "
                f"{', '.join(helped)}. Help text is shown to every end user who "
                f"hovers over the field.",
                "Keep only wording the requirements asked for. Builder notes, "
                "examples and reasons belong in the field's comments, where a "
                "suggested help text can be offered without being shown."))

    for rel in spec.relationships:
        label = rel.reference_label
        if label and not label.startswith("Related "):
            findings.append(_finding(
                "DSN005", rel.child,
                f"'{rel.child}' names its reference to '{rel.parent}' '{label}'. "
                f"Reference fields are named 'Related <parent record name>', or "
                f"'Related <role>' where the parent plays more than one, so a "
                f"child's parents read the same way everywhere.",
                f"Rename it 'Related {label}', or 'Related <{rel.parent} record "
                f"name>' if the role adds nothing, and update the forms and "
                f"reports that name it."))

    findings.extend(_role_findings(spec))
    return findings


def _role_findings(spec: AppSpec) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    filled = DEFAULT_ROLE_NAMES if spec.default_roles else ()
    for role in spec.roles:
        key = role.name.casefold()
        if key in filled or role.disable_access:
            continue
        missing = [t.name for t in spec.tables if role.name not in t.role_permissions]
        if missing:
            findings.append(_finding(
                "DSN006", missing[0],
                f"Role '{role.name}' has no permissions on {len(missing)} table(s): "
                f"{', '.join(missing)}. A role a table does not list cannot view, "
                f"add or edit anything in it.",
                f"Give '{role.name}' a permission on each table it should use - "
                f"view-only where it should only read - and leave a table out only "
                f"where the requirements say this role must not see it."))

    for table in spec.tables:
        for role_name, entry in table.role_permissions.items():
            if role_name.casefold() == "administrator" and entry != FULL_ACCESS:
                findings.append(_finding(
                    "DSN007", table.name,
                    f"The Administrator role has less than full access to "
                    f"'{table.name}'. Administrators are expected to view, add, "
                    f"edit and delete every record in every table.",
                    "Remove the entry so Administrator keeps full access, or "
                    "confirm the requirements restrict it - and if they do, put "
                    "the restriction on a new role rather than on Administrator."))
    return findings


__all__ = ["check_design", "DSN_CODES"]

DSN_CODES = ("DSN001", "DSN002", "DSN003", "DSN004", "DSN005", "DSN006",
             "DSN007")
