from .v07 import QBLv07Handler
from .v09 import QBLv09Handler
from .v11 import QBLv011Handler
from .v12 import QBLv012Handler
from .v14 import QBLv014Handler
from .v15 import QBLv015Handler

VERSION_HANDLERS = {
    "0.7": QBLv07Handler,
    "0.9": QBLv09Handler,
    "0.11": QBLv011Handler,
    "0.12": QBLv012Handler,
    "0.14": QBLv014Handler,
    "0.15": QBLv015Handler,
}

DEFAULT_QBL_VERSION = "0.12"


def normalize_qbl_version(version):
    if version is None:
        return DEFAULT_QBL_VERSION
    if isinstance(version, str):
        return version.strip() or DEFAULT_QBL_VERSION
    if isinstance(version, (int, float)):
        return format(version, "g")
    return str(version)


def _version_key(version):
    parts = str(version).split(".")
    try:
        return tuple(int(part) for part in parts)
    except ValueError:
        return None


def resolve_version(version):
    version = normalize_qbl_version(version)
    if version in VERSION_HANDLERS:
        return version, []

    requested = _version_key(version)
    supported = sorted(
        ((_version_key(name), name) for name in VERSION_HANDLERS),
        key=lambda item: item[0],
    )

    if requested is None:
        raise ValueError(
            f"Unsupported QBL version: {version!r}. Supported versions are "
            + ", ".join(name for _, name in supported)
        )

    older = [name for key, name in supported if key <= requested]
    if not older:
        oldest = supported[0][1]
        raise ValueError(
            f"QBL version {version} is older than {oldest}, the oldest version this "
            f"package implements. Note that YAML reads an unquoted `Version: 0.10` as "
            f"the number 0.1, so a version that looks too old may just have lost a "
            f"trailing zero; quote it or pass qbl_version explicitly."
        )

    resolved = older[-1]
    return resolved, [
        f"QBL version {version} has no dedicated handler; parsed with the {resolved} "
        f"handler. Objects added after {resolved} are not parsed."
    ]


def get_version_handler(version, table_schema=None, identifier_index=None):
    resolved, _notes = resolve_version(version)
    return VERSION_HANDLERS[resolved](table_schema, identifier_index)


def detect_qbl_version(qbl_data):
    return detect_qbl_version_with_notes(qbl_data)[0]


def detect_qbl_version_with_notes(qbl_data):
    solution = qbl_data.get("Solution", {}) if isinstance(qbl_data, dict) else {}
    version = solution.get("Version") if isinstance(solution, dict) else None
    if version is None and isinstance(qbl_data, dict):
        version = qbl_data.get("Version")

    if version is None:
        return DEFAULT_QBL_VERSION, [
            f"Document declares no Version; assumed {DEFAULT_QBL_VERSION}, the "
            f"platform's default export version."
        ]
    return normalize_qbl_version(version), []
