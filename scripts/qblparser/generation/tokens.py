from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Tuple

FIELD_TOKEN = re.compile(r"\[\[fid:([^|\]]+)(?:\|([^\]]+))?\]\]")


class FieldTokenError(ValueError):
    pass


def _ids(document: Mapping[str, Any]) -> Tuple[Dict[Tuple[str, str], Any], Dict[str, str]]:
    ids: Dict[Tuple[str, str], Any] = {}
    names: Dict[str, str] = {}
    for app in (document.get("Resources") or {}).values():
        if not isinstance(app, Mapping) or app.get("Type") != "QB::Application":
            continue
        for key, table in (app.get("Tables") or {}).items():
            name = (table.get("Properties") or {}).get("Name")
            if not isinstance(name, str):
                continue
            names[key] = name
            for item in (table.get("Fields") or {}).values():
                label = (item.get("Properties") or {}).get("Label")
                if isinstance(label, str) and item.get("Id") is not None:
                    ids[(name, label)] = item["Id"]
    return ids, names


def resolve_field_tokens(document: MutableMapping[str, Any]) -> int:
    ids, names = _ids(document)
    tables = set(names.values())
    problems: List[str] = []
    count = 0

    def resolve(text: str, table: Optional[str], where: str) -> str:
        nonlocal count

        def replace(match: "re.Match[str]") -> str:
            nonlocal count
            first, second = match.group(1).strip(), match.group(2)
            if second is not None:
                key = (first, second.strip())
            elif table is not None:
                key = (table, first)
            else:
                problems.append(f"{match.group(0)} in {where} names no table; write "
                                f"[[fid:<table>|{first}]] outside a table")
                return match.group(0)
            if key in ids:
                count += 1
                return str(ids[key])
            if key[0] not in tables:
                close = difflib.get_close_matches(key[0], tables, n=1)
                hint = f"; did you mean '{close[0]}'?" if close else ""
                problems.append(f"{match.group(0)} in {where}: no table '{key[0]}'{hint}")
            else:
                labels = [label for (name, label) in ids if name == key[0]]
                close = difflib.get_close_matches(key[1], labels, n=1)
                hint = f"; did you mean '{close[0]}'?" if close else ""
                problems.append(f"{match.group(0)} in {where}: '{key[0]}' has no field "
                                f"'{key[1]}'{hint}")
            return match.group(0)

        return FIELD_TOKEN.sub(replace, text)

    def walk(node: Any, table: Optional[str], where: str) -> Any:
        if isinstance(node, str):
            return resolve(node, table, where) if "[[fid:" in node else node
        if isinstance(node, MutableMapping):
            for key in list(node.keys()):
                node[key] = walk(node[key], table, f"{where}.{key}")
            return node
        if isinstance(node, list):
            for index, value in enumerate(node):
                node[index] = walk(value, table, f"{where}[{index}]")
            return node
        return node

    for resource_key, resource in (document.get("Resources") or {}).items():
        if isinstance(resource, MutableMapping) and resource.get("Type") == "QB::Application":
            for key, value in list(resource.items()):
                if key == "Tables":
                    for table_key, table in (value or {}).items():
                        walk(table, names.get(table_key), f"{resource_key}.Tables.{table_key}")
                else:
                    resource[key] = walk(value, None, f"{resource_key}.{key}")
        else:
            walk(resource, None, str(resource_key))

    if problems:
        raise FieldTokenError("; ".join(problems))
    return count


__all__ = ["FIELD_TOKEN", "FieldTokenError", "resolve_field_tokens"]
