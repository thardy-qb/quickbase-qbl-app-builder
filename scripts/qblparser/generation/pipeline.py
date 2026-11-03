from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Sequence, Tuple

from qblparser.core import validate_qbl_document

from .compiler import compile_app
from .code_pages import review_code_pages
from .conformance import check_conformance
from .behaviour import check_behaviour
from .design import check_design
from .requirements import check_decisions, check_requirements


class QBLGenerationError(RuntimeError):

    def __init__(self, message: str, findings: List[Dict[str, Any]]):
        super().__init__(message)
        self.findings = findings


def _is_error(finding: Mapping[str, Any]) -> bool:
    return str(finding.get("Severity", "Error")).lower() != "warning"


def build_app(spec, *,
              extra_checks: Sequence[Callable[[str], List[Dict[str, Any]]]] = (),
              conformance_codes: Tuple[str, ...] = ("GEN001", "GEN003"),
              raise_on_error: bool = True,
              ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    document = compile_app(spec)
    findings: List[Dict[str, Any]] = []
    findings.extend(check_design(spec))
    findings.extend(check_requirements(spec, document))
    findings.extend(check_decisions(spec, document))
    findings.extend(review_code_pages(document, spec))
    findings.extend(validate_qbl_document(document))
    findings.extend(check_conformance(document, codes=conformance_codes))
    findings.extend(check_behaviour(document))

    if extra_checks:
        from qblparser.utils.qbl_yaml import dump_qbl_yaml
        import io

        buffer = io.StringIO()
        dump_qbl_yaml(document, buffer)
        text = buffer.getvalue()
        for check in extra_checks:
            try:
                findings.extend(check(text))
            except QBLGenerationError as error:
                raise QBLGenerationError(str(error), findings) from error

    errors = [f for f in findings if _is_error(f)]
    if errors and raise_on_error:
        summary = "; ".join(f"{f['Code']}: {f['Problem'][:120]}" for f in errors[:5])
        raise QBLGenerationError(
            f"{len(errors)} error(s) across {len(findings)} finding(s): {summary}",
            findings)
    return document, findings


__all__ = ["QBLGenerationError", "build_app"]
