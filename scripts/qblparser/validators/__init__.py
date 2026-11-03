from .core import validate_qbl_resources
from .formulas import validate_qbl_formulas
from .references import validate_qbl_references
from .remediation import REMEDIATION, remediation_for
from .structure import validate_qbl_structure
from .values import validate_qbl_values


def validate_qbl_document(qbl):
    issues = list(validate_qbl_resources(qbl))
    issues.extend(validate_qbl_references(qbl))
    issues.extend(validate_qbl_values(qbl))
    issues.extend(validate_qbl_structure(qbl))
    issues.extend(validate_qbl_formulas(qbl))
    return issues


__all__ = [
    'REMEDIATION',
    'remediation_for',
    'validate_qbl_resources',
    'validate_qbl_references',
    'validate_qbl_values',
    'validate_qbl_structure',
    'validate_qbl_formulas',
    'validate_qbl_document',
]
