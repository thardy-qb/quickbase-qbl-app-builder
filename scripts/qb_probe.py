#!/usr/bin/env python3
"""Localise a create that hangs, or fails with a message that names nothing.

Some creates answer "failure in creating one of the resources" without saying
which, and some never answer. Reading the document for the cause does not work:
a hang means "this document", not "this kind of node". What works is a ladder
of complete applications built from the same spec:

    rung 0   the floor: tables, fields, relationships, forms and roles
    rung n   the floor plus the first n families, in dependency order

Each rung is a whole application that goes through the document-level gates
and is then created. The first rung that fails names the family. Inside that
family the items are halved: create the floor plus the families that passed
plus the first half of the failing family's items, and keep halving toward the
smallest prefix that still fails. The number of creates is bounded.

`create` is passed in, so the ladder can be built and walked without a network.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple

# (family name, level, attributes on that level's spec). Dependency order: a
# family only refers to families before it or to the floor.
FAMILIES: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("reports", "table", ("reports",)),
    ("role access", "table", ("role_permissions", "role_forms", "report_form_overrides")),
    ("charts", "table", ("charts",)),
    ("emails", "table", ("emails",)),
    ("document templates", "table", ("document_templates",)),
    ("legacy forms", "table", ("legacy_form",)),
    ("variables", "app", ("variables",)),
    ("pages", "app", ("pages", "role_home_pages")),
    ("connected tables", "app", ("connected_tables",)),
    ("guides", "app", ("guides",)),
    ("dashboards", "app", ("dashboards",)),
    ("home widgets", "app", ("home_widgets",)),
    ("pipelines", "app", ("pipelines",)),
)

Locator = Tuple[Optional[int], str, Any]  # (table index or None, attribute, index/key/None)


@dataclass
class Rung:
    number: int
    family: str
    label: str
    included: FrozenSet[Locator]
    spec: Any
    note: str = ""


@dataclass
class RungResult:
    number: int
    label: str
    status: str            # created | failed | skipped-offline | skipped-compile | not-run
    detail: str = ""
    outcome: str = ""


def _describe(spec: Any, locator: Locator) -> str:
    table_index, attribute, key = locator
    holder = spec if table_index is None else spec.tables[table_index]
    value = getattr(holder, attribute)
    item = value if key is None else value[key]
    if isinstance(value, dict):
        name = str(key)
    else:
        name = str(getattr(item, "name", None) or getattr(item, "title", None) or key or "")
    where = f"{holder.name}: " if table_index is not None else ""
    return f"{where}{attribute} '{name}'" if name else f"{where}{attribute}"


def family_items(spec: Any, family: str) -> List[Locator]:
    """Every item of one family, as locators into `spec`."""
    for name, level, attributes in FAMILIES:
        if name != family:
            continue
        found: List[Locator] = []
        holders = ([(None, spec)] if level == "app"
                   else list(enumerate(spec.tables)))
        for index, holder in holders:
            for attribute in attributes:
                value = getattr(holder, attribute, None)
                if value is None:
                    continue
                if isinstance(value, dict):
                    found.extend((index, attribute, key) for key in value)
                elif isinstance(value, (list, tuple)):
                    found.extend((index, attribute, i) for i in range(len(value)))
                else:
                    found.append((index, attribute, None))
        return found
    raise KeyError(family)


def all_family_items(spec: Any) -> Dict[str, List[Locator]]:
    return {name: family_items(spec, name) for name, _, _ in FAMILIES}


def _empty_like(value: Any) -> Any:
    if isinstance(value, dict):
        return {}
    if isinstance(value, list):
        return []
    return None


def prune(spec: Any, keep: FrozenSet[Locator]) -> Any:
    """A copy of `spec` holding only the family items in `keep`.

    Requirements and decisions are dropped: a rung is a fragment, and the gate
    that traces criteria to artefacts would only report what the fragment
    leaves out.
    """
    work = copy.deepcopy(spec)
    originals = all_family_items(spec)
    for items in originals.values():
        grouped: Dict[Tuple[Optional[int], str], List[Any]] = {}
        for table_index, attribute, key in items:
            grouped.setdefault((table_index, attribute), []).append(key)
        for (table_index, attribute), keys in grouped.items():
            holder = work if table_index is None else work.tables[table_index]
            value = getattr(holder, attribute)
            kept = [key for key in keys if (table_index, attribute, key) in keep]
            if isinstance(value, dict):
                setattr(holder, attribute, {k: v for k, v in value.items() if k in kept})
            elif isinstance(value, list):
                setattr(holder, attribute, [v for i, v in enumerate(value) if i in kept])
            else:
                setattr(holder, attribute, value if kept else None)
    work.requirements = []
    work.decisions = []
    return work


def build_ladder(spec: Any, stamp: str) -> List[Rung]:
    """The floor, then one cumulative rung per family that has items."""
    rungs: List[Rung] = []
    included: FrozenSet[Locator] = frozenset()
    floor = prune(spec, included)
    floor.name = f"QBL probe {stamp} rung 0: floor"
    rungs.append(Rung(0, "floor", "floor", included, floor))
    for name, items in all_family_items(spec).items():
        if not items:
            continue
        included = included | frozenset(items)
        number = len(rungs)
        rung_spec = prune(spec, included)
        rung_spec.name = f"QBL probe {stamp} rung {number}: {name}"
        rungs.append(Rung(number, name, name, included, rung_spec))
    return rungs


CreateFn = Callable[[Any, str, str], Any]   # (document, app name, label) -> Outcome-like
GateFn = Callable[[Any], Dict[str, Any]]


@dataclass
class ProbeReport:
    results: List[RungResult] = field(default_factory=list)
    creates: int = 0
    stopped: str = ""
    localised_family: str = ""
    localised_items: List[str] = field(default_factory=list)
    exact: bool = False
    floor_failed: bool = False

    def lines(self) -> List[str]:
        out = ["PROBE", ""]
        for result in self.results:
            out.append(f"  rung {result.number:<3} {result.status:16} {result.label}"
                       + (f"  - {result.detail}" if result.detail else ""))
        out.append("")
        out.append(f"  {self.creates} create(s) made.")
        if self.floor_failed:
            out.append("  The floor itself fails: tables, fields, relationships, forms or "
                       "roles. Nothing above it was tried.")
        elif self.localised_family:
            what = "; ".join(self.localised_items) or "(the whole family)"
            out.append(f"  Localised to {self.localised_family}: {what}"
                       + ("" if self.exact else "  (narrowed, not to a single item: budget ran out)"))
        elif self.stopped:
            out.append(f"  Not localised: {self.stopped}")
        else:
            out.append("  Every rung created. The failure is not in a family this ladder "
                       "splits (application-level properties, or a field-level cause); "
                       "re-create the full document once more before assuming it failed.")
        return out


def run_probe(spec: Any, *, stamp: str, create: CreateFn, gates: GateFn,
              compile_fn: Callable[[Any], Any], max_creates: int = 12) -> ProbeReport:
    """Walk the ladder, then halve inside the first failing family."""
    report = ProbeReport()
    rungs = build_ladder(spec, stamp)
    originals = all_family_items(spec)
    passed: FrozenSet[Locator] = frozenset()
    counter = {"n": len(rungs) - 1}

    def attempt(rung_spec: Any, label: str, number: int) -> str:
        """`created`, `failed`, or a skip status; counts creates."""
        try:
            document = compile_fn(rung_spec)
        except Exception as exc:  # noqa: BLE001
            report.results.append(RungResult(number, label, "skipped-compile", str(exc)[:160]))
            return "skipped-compile"
        gated = gates(document)
        if not gated["passed"]:
            report.results.append(RungResult(
                number, label, "skipped-offline",
                f"{gated['errors']} error(s) in the offline gates; not created"))
            return "skipped-offline"
        if report.creates >= max_creates:
            report.stopped = f"the limit of {max_creates} creates was reached"
            report.results.append(RungResult(number, label, "not-run", "create limit reached"))
            return "not-run"
        outcome = create(document, rung_spec.name, label)
        report.creates += 1
        if outcome.clean:
            report.results.append(RungResult(number, label, "created", outcome=outcome.outcome))
            return "created"
        detail = outcome.detail or "; ".join(
            f.get("Problem", "")[:100] for f in outcome.findings[:2])
        report.results.append(RungResult(number, label, "failed", detail[:200], outcome.outcome))
        return "failed"

    for rung in rungs:
        status = attempt(rung.spec, rung.label, rung.number)
        if status == "created":
            passed = rung.included
            continue
        if status == "not-run":
            return report
        if status != "failed":
            continue  # skipped: the next rung is built without it only if it re-includes it
        if rung.number == 0:
            report.floor_failed = True
            return report
        _halve(spec, rung, passed, originals[rung.family], report, attempt, counter,
               stamp, max_creates)
        return report
    return report


def _halve(spec, rung, passed, items, report, attempt, counter, stamp, max_creates) -> None:
    report.localised_family = rung.family
    low, high = 0, len(items)
    while high - low > 1 and report.creates < max_creates:
        middle = (low + high) // 2
        counter["n"] += 1
        number = counter["n"]
        keep = passed | frozenset(items[:middle])
        label = f"{rung.family} (first {middle} of {len(items)})"
        rung_spec = prune(spec, keep)
        rung_spec.name = f"QBL probe {stamp} rung {number}: {label}"
        status = attempt(rung_spec, label, number)
        if status == "created":
            low = middle
        elif status == "failed":
            high = middle
        else:
            break
    report.localised_items = [_describe(spec, locator) for locator in items[low:high]]
    report.exact = (high - low) == 1
    if not report.exact and not report.stopped:
        report.stopped = ""
