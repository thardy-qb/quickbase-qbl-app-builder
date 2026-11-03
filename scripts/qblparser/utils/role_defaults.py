from __future__ import annotations

from typing import Any, Iterable


def extract_logical_reference(value: Any, accepted_prefixes: Iterable[str]) -> str:
    prefixes = tuple(accepted_prefixes)

    if isinstance(value, str):
        return value if value.startswith(prefixes) else ""

    if not isinstance(value, dict):
        return ""

    if value.get("__ref__") is True:
        return extract_logical_reference(value.get("value", ""), prefixes)

    for nested_value in value.values():
        resolved = extract_logical_reference(nested_value, prefixes)
        if resolved:
            return resolved

    return ""


def resolve_role_default_reference(role_value: Any, everyone_value: Any, accepted_prefixes: Iterable[str]) -> str:
    value = everyone_value if role_value == "Default" else role_value
    if value is None:
        return ""
    return extract_logical_reference(value, accepted_prefixes)


def collect_role_default_references(role_defaults: Any, accepted_prefixes: Iterable[str], setting_keys: Iterable[str] | None = None) -> set[str]:
    if not isinstance(role_defaults, dict):
        return set()

    everyone_defaults = role_defaults.get("Everyone", {})
    assigned_ids = set()

    if setting_keys:
        if isinstance(everyone_defaults, dict):
            for setting_key in setting_keys:
                everyone_ref = extract_logical_reference(everyone_defaults.get(setting_key), accepted_prefixes)
                if everyone_ref:
                    assigned_ids.add(everyone_ref)

        for role_key, role_settings in role_defaults.items():
            if role_key == "Everyone" or not isinstance(role_settings, dict):
                continue

            for setting_key in setting_keys:
                resolved = resolve_role_default_reference(
                    role_settings.get(setting_key),
                    everyone_defaults.get(setting_key) if isinstance(everyone_defaults, dict) else None,
                    accepted_prefixes,
                )
                if resolved:
                    assigned_ids.add(resolved)

        return assigned_ids

    everyone_ref = extract_logical_reference(everyone_defaults, accepted_prefixes)
    if everyone_ref:
        assigned_ids.add(everyone_ref)

    for role_key, role_value in role_defaults.items():
        if role_key == "Everyone":
            continue
        resolved = resolve_role_default_reference(role_value, everyone_defaults, accepted_prefixes)
        if resolved:
            assigned_ids.add(resolved)

    return assigned_ids
