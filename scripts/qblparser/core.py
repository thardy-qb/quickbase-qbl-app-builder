from __future__ import annotations

import json
import io
from dataclasses import dataclass
from pathlib import Path
from contextlib import redirect_stdout
from typing import Any, Callable, Dict, List, Mapping, Optional, Union

from .analysis.cross_reference_usage import apply_cross_reference_usage
from .schema import ENTITY_COLLECTIONS, ENTITY_DESCRIPTIONS, normalize_parsed_data
from .contracts import QBLIssue, ParsedCollection, ParsedData
from .utils.parameters import resolve_document
from .utils.qbl_yaml import load_qbl_yaml
from .validators import validate_qbl_document, validate_qbl_resources
from .versions import (
    DEFAULT_QBL_VERSION,
    VERSION_HANDLERS,
    detect_qbl_version_with_notes,
    get_version_handler,
    normalize_qbl_version,
    resolve_version,
)


PathLike = Union[str, Path]
SUPPORTED_QBL_VERSIONS = tuple(VERSION_HANDLERS.keys())


class QBLParseError(RuntimeError):
    pass


VALIDATE_SCHEMA = "schema"
VALIDATE_ALL = "all"

_VALIDATORS = {
    VALIDATE_SCHEMA: validate_qbl_resources,
    "resources": validate_qbl_resources,
    VALIDATE_ALL: validate_qbl_document,
    "full": validate_qbl_document,
    "document": validate_qbl_document,
}


def resolve_validator(validate: Any) -> Optional[Callable[[Any], List[QBLIssue]]]:
    if validate is None or validate is False:
        return None
    if validate is True:
        return validate_qbl_resources

    validator = _VALIDATORS.get(str(validate).strip().lower())
    if validator is None:
        raise ValueError(
            f"Unknown validate value {validate!r}. Use False, True "
            f"(schema layer only), or {VALIDATE_ALL!r} (all three layers)."
        )
    return validator


@dataclass(frozen=True)
class QBLParserOptions:

    qbl_version: Optional[str] = None
    app_id: str = ""
    table_schema: Any = None
    identifier_index: Optional[Dict[str, Any]] = None
    capture_warnings: bool = True
    strict: bool = False
    validate: Any = False


@dataclass
class QBLParseResult:

    qbl_data: Dict[str, Any]
    parsed_data: ParsedData
    qbl_version: str
    app_id: str = ""
    table_schema: Any = None
    identifier_index: Optional[Dict[str, Any]] = None
    source_path: str = ""
    warnings: Optional[List[str]] = None
    issues: Optional[List[QBLIssue]] = None

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []
        if self.issues is None:
            self.issues = []

    def entity_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for entity_name, rows in self.parsed_data.items():
            if isinstance(rows, (list, tuple, dict, set)):
                counts[entity_name] = len(rows)
            else:
                counts[entity_name] = 0
        return counts

    def as_dict(self, include_qbl_data: bool = False) -> Dict[str, Any]:
        payload = {
            "parsed_data": self.parsed_data,
            "qbl_version": self.qbl_version,
            "app_id": self.app_id,
            "entity_counts": self.entity_counts(),
            "source_path": self.source_path,
        }
        if include_qbl_data:
            payload["qbl_data"] = self.qbl_data
        if self.warnings:
            payload["warnings"] = list(self.warnings)
        if self.issues:
            payload["issues"] = list(self.issues)
            payload["issue_counts"] = self.issue_counts()
        return payload

    def issue_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for issue in self.issues:
            issue_type = str(issue.get("Type", "Unknown"))
            counts[issue_type] = counts.get(issue_type, 0) + 1
        return counts

    def entity_names(self) -> List[str]:
        ordered = [name for name in ENTITY_COLLECTIONS if name in self.parsed_data]
        extras = sorted(name for name in self.parsed_data if name not in ENTITY_COLLECTIONS)
        return ordered + extras

    def get_entities(self, name: str, *, required: bool = False) -> ParsedCollection:
        if name not in self.parsed_data:
            if required:
                raise KeyError(f"Parsed entity collection '{name}' is not available.")
            return []
        rows = self.parsed_data.get(name)
        if rows is None:
            return []
        if not isinstance(rows, list):
            if required:
                raise TypeError(f"Parsed entity collection '{name}' is not a list.")
            return []
        return rows


def _capture_stdout_warnings(parser_call: Callable[[], Dict[str, Any]]) -> tuple[Dict[str, Any], List[str]]:
    stream = io.StringIO()
    with redirect_stdout(stream):
        parsed_data = parser_call()
    warnings = [line.strip() for line in stream.getvalue().splitlines() if line.strip()]
    return parsed_data, warnings


def detect_qbl_version(qbl_data: Mapping[str, Any]) -> str:
    return detect_qbl_version_with_notes(qbl_data)[0]


def _ensure_mapping(value: Any, *, label: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{label} must parse to a mapping/dictionary.")
    return value


def _shallow_copy_document(qbl_data: Any) -> Any:
    if hasattr(qbl_data, "parameter_overrides") and hasattr(qbl_data, "copy"):
        return qbl_data.copy()
    if isinstance(qbl_data, Mapping):
        return dict(qbl_data)
    return qbl_data


def load_qbl_string(source: str) -> Dict[str, Any]:
    return _ensure_mapping(load_qbl_yaml(source), label="QBL YAML")


def load_qbl_file(path: PathLike) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return _ensure_mapping(load_qbl_yaml(handle), label=f"QBL file '{path}'")


def load_table_schema_file(path: PathLike) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_qbl_data(
    qbl_data: Mapping[str, Any],
    qbl_version: Optional[Any] = None,
    app_id: str = "",
    table_schema: Any = None,
    identifier_index: Optional[Dict[str, Any]] = None,
    source_path: str = "",
    capture_warnings: bool = True,
    strict: bool = False,
    validate: Any = False,
) -> QBLParseResult:
    qbl_mapping = _ensure_mapping(_shallow_copy_document(qbl_data), label="QBL data")

    if qbl_version is not None:
        declared_version, version_notes = normalize_qbl_version(qbl_version), []
    else:
        declared_version, version_notes = detect_qbl_version_with_notes(qbl_mapping)

    resolved_version, resolution_notes = resolve_version(declared_version)
    version_notes = version_notes + resolution_notes
    version_handler = get_version_handler(resolved_version, table_schema, identifier_index)

    parse_input = resolve_document(qbl_mapping)

    if capture_warnings:
        parsed_data, warnings = _capture_stdout_warnings(lambda: version_handler.parse_qbl(parse_input))
    else:
        parsed_data = version_handler.parse_qbl(parse_input)
        warnings = []

    warnings = version_notes + warnings

    parsed_data = apply_cross_reference_usage(parsed_data)
    parsed_data = normalize_parsed_data(parsed_data)
    validator = resolve_validator(validate)
    issues: List[QBLIssue] = validator(parse_input) if validator else []

    if strict and warnings:
        raise QBLParseError("QBL parsing emitted warnings: " + "; ".join(warnings))

    errors = [issue for issue in issues if issue.get("Severity", "error") == "error"]
    if strict and errors:
        raise QBLParseError(
            f"QBL validation found {len(errors)} errors "
            f"({len(issues) - len(errors)} warnings)."
        )

    return QBLParseResult(
        qbl_data=qbl_mapping,
        parsed_data=parsed_data,
        qbl_version=declared_version,
        app_id=app_id or "",
        table_schema=table_schema,
        identifier_index=identifier_index,
        source_path=source_path,
        warnings=warnings,
        issues=issues,
    )


def parse_qbl(
    qbl_data: Mapping[str, Any],
    qbl_version: Optional[Any] = None,
    app_id: str = "",
    table_schema: Any = None,
    identifier_index: Optional[Dict[str, Any]] = None,
    capture_warnings: bool = False,
) -> ParsedData:
    return parse_qbl_data(
        qbl_data,
        qbl_version,
        app_id,
        table_schema,
        identifier_index,
        capture_warnings=capture_warnings,
    ).parsed_data


def parse_qbl_string(
    source: str,
    qbl_version: Optional[Any] = None,
    app_id: str = "",
    table_schema: Any = None,
    identifier_index: Optional[Dict[str, Any]] = None,
    capture_warnings: bool = True,
    strict: bool = False,
    validate: Any = False,
) -> QBLParseResult:
    qbl_data = load_qbl_string(source)
    return parse_qbl_data(
        qbl_data,
        qbl_version,
        app_id,
        table_schema,
        identifier_index,
        capture_warnings=capture_warnings,
        strict=strict,
        validate=validate,
    )


def parse_qbl_file(
    path: PathLike,
    qbl_version: Optional[Any] = None,
    app_id: str = "",
    table_schema: Any = None,
    identifier_index: Optional[Dict[str, Any]] = None,
    table_schema_file: Optional[PathLike] = None,
    capture_warnings: bool = True,
    strict: bool = False,
    validate: Any = False,
) -> QBLParseResult:
    resolved_table_schema = (
        load_table_schema_file(table_schema_file)
        if table_schema_file and table_schema is None
        else table_schema
    )
    qbl_data = load_qbl_file(path)
    return parse_qbl_data(
        qbl_data,
        qbl_version=qbl_version,
        app_id=app_id,
        table_schema=resolved_table_schema,
        identifier_index=identifier_index,
        source_path=str(path),
        capture_warnings=capture_warnings,
        strict=strict,
        validate=validate,
    )


class QBLParser:

    def __init__(
        self,
        *,
        qbl_version: Optional[Any] = None,
        app_id: str = "",
        table_schema: Any = None,
        identifier_index: Optional[Dict[str, Any]] = None,
        capture_warnings: bool = True,
        strict: bool = False,
        validate: Any = False,
    ) -> None:
        self.options = QBLParserOptions(
            qbl_version=normalize_qbl_version(qbl_version) if qbl_version is not None else None,
            app_id=app_id or "",
            table_schema=table_schema,
            identifier_index=identifier_index,
            capture_warnings=capture_warnings,
            strict=strict,
            validate=validate,
        )

    @classmethod
    def from_files(
        cls,
        *,
        qbl_version: Optional[Any] = None,
        app_id: str = "",
        table_schema_file: Optional[PathLike] = None,
        identifier_index: Optional[Dict[str, Any]] = None,
        capture_warnings: bool = True,
        strict: bool = False,
        validate: Any = False,
    ) -> "QBLParser":
        table_schema = load_table_schema_file(table_schema_file) if table_schema_file else None
        return cls(
            qbl_version=qbl_version,
            app_id=app_id,
            table_schema=table_schema,
            identifier_index=identifier_index,
            capture_warnings=capture_warnings,
            strict=strict,
            validate=validate,
        )

    def parse(
        self,
        qbl_data: Mapping[str, Any],
        *,
        qbl_version: Optional[Any] = None,
        app_id: Optional[str] = None,
        table_schema: Any = None,
        identifier_index: Optional[Dict[str, Any]] = None,
        source_path: str = "",
        capture_warnings: Optional[bool] = None,
        strict: Optional[bool] = None,
        validate: Any = None,
    ) -> QBLParseResult:
        return parse_qbl_data(
            qbl_data,
            qbl_version=qbl_version if qbl_version is not None else self.options.qbl_version,
            app_id=self.options.app_id if app_id is None else app_id,
            table_schema=self.options.table_schema if table_schema is None else table_schema,
            identifier_index=self.options.identifier_index if identifier_index is None else identifier_index,
            source_path=source_path,
            capture_warnings=self.options.capture_warnings if capture_warnings is None else capture_warnings,
            strict=self.options.strict if strict is None else strict,
            validate=self.options.validate if validate is None else validate,
        )

    def parse_string(self, source: str, **overrides: Any) -> QBLParseResult:
        return self.parse(load_qbl_string(source), **overrides)

    def parse_file(self, path: PathLike, **overrides: Any) -> QBLParseResult:
        overrides.setdefault("source_path", str(path))
        return self.parse(load_qbl_file(path), **overrides)
