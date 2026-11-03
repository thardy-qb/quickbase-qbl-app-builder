from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .compiler import _table_alias
from .spec import FieldSpec, RelationshipSpec

COUNTER_LABEL = "Row Counter"


def counter_field(label: str = COUNTER_LABEL) -> FieldSpec:
    return FieldSpec(label, "Numeric::Formula", formula="1",
                     comments="Counted by duplicate checks: SumValues refuses Record ID#.")


def unique_together(fields: Sequence[str], message: str, *,
                    when: Optional[str] = None, counter: str = COUNTER_LABEL) -> str:
    if not fields:
        raise ValueError("unique_together needs at least one field")
    clauses = [f'"{{[[fid:{label}]].EX.\'" & ToText([{label}]) & "\'}}"' for label in fields]
    query = ' & "AND" & '.join(clauses)
    query += ' & "AND{3.XEX.\'" & ToText([Record ID#]) & "\'}"'
    test = f"SumValues(GetRecords({query}), [[fid:{counter}]]) > 0"
    if when:
        test = f"({when}) and {test}"
    return f"If({test}, {_quote(message)})"


def api_url(action: str, values: Sequence[Tuple[str, str]], *, table: Optional[str] = None,
            record: Optional[str] = "[Record ID#]", then: str = "back",
            condition: Optional[str] = None) -> str:
    if action not in ("edit", "add", "form"):
        raise ValueError("action is edit, add or form")
    target = f"[{_table_alias(table)}]" if table else "Dbid()"
    if action in ("add", "form") and not table:
        raise ValueError(f"a {action} button needs the table it adds to")
    api = {"edit": "API_EditRecord", "add": "API_AddRecord", "form": "nwr"}[action]
    parts = [f'URLRoot() & "db/" & {target} & "?a={api}"']
    if action == "edit":
        parts.append(f'"&rid=" & {record or "[Record ID#]"}')
    for label, expression in values:
        token = f"[[fid:{table}|{label}]]" if table else f"[[fid:{label}]]"
        parts.append(f'"&_fid_{token}=" & URLEncode({expression})')
    if then == "back":
        back = 'URLRoot() & "db/" & Dbid() & "?a=dr&rid=" & [Record ID#]'
        parts.append(f'"&{"z" if action == "form" else "rdr"}=" & URLEncode({back})')
    elif then != "stay":
        raise ValueError("then is back or stay")
    formula = " & ".join(parts)
    return f'If({condition}, {formula}, "")' if condition else formula


def settings_lookups(settings_table: str, table: str, fields: Sequence[str], *,
                     prefix: str = "Setting ", reference_label: Optional[str] = None
                     ) -> Tuple[RelationshipSpec, List[FieldSpec]]:
    relationship = RelationshipSpec(
        settings_table, table, reference_label=reference_label,
        embed_on_parent=False, reference_properties={"DefaultValue": 1})
    lookups = [FieldSpec(f"{prefix}{label}", "Lookup", lookup_table=settings_table,
                         lookup_field=label, lookup_via=reference_label,
                         comments=f"From the settings record (record 1 of {settings_table}).")
               for label in fields]
    return relationship, lookups


def _quote(text: str) -> str:
    return '"' + text.replace('"', '\\"') + '"'


__all__ = ["COUNTER_LABEL", "api_url", "counter_field", "settings_lookups",
           "unique_together"]
