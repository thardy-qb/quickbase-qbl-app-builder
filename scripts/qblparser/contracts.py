from __future__ import annotations

from typing import Any, Dict, List, TypedDict


ParsedRow = Dict[str, Any]

ParsedCollection = List[ParsedRow]

ParsedData = Dict[str, ParsedCollection]


class QBLIssue(TypedDict, total=False):

    LogicalID: str
    Path: str
    Type: str
    Problem: str
    Code: str
    Severity: str
