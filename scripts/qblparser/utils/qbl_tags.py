from __future__ import annotations

from typing import Any, Optional


class QBLTagged:

    qbl_tag: Optional[str] = None

    def with_tag(self, tag: Optional[str]):
        self.qbl_tag = tag
        return self


class QBLTaggedMapping(QBLTagged, dict):

    def __reduce__(self):
        return (_rebuild_mapping, (dict(self), self.qbl_tag))

    def copy(self) -> "QBLTaggedMapping":
        return _rebuild_mapping(dict(self), self.qbl_tag)


class QBLTaggedSequence(QBLTagged, list):

    def __reduce__(self):
        return (_rebuild_sequence, (list(self), self.qbl_tag))

    def copy(self) -> "QBLTaggedSequence":
        return _rebuild_sequence(list(self), self.qbl_tag)


class QBLTaggedScalar(QBLTagged, str):

    def __new__(cls, value: str = "", tag: Optional[str] = None):
        instance = super().__new__(cls, value)
        instance.qbl_tag = tag
        return instance

    def __reduce__(self):
        return (QBLTaggedScalar, (str(self), self.qbl_tag))


def _rebuild_mapping(data: dict, tag: Optional[str]) -> QBLTaggedMapping:
    node = QBLTaggedMapping(data)
    node.qbl_tag = tag
    return node


def _rebuild_sequence(data: list, tag: Optional[str]) -> QBLTaggedSequence:
    node = QBLTaggedSequence(data)
    node.qbl_tag = tag
    return node


REF_MARKER = "__ref__"
BAD_REF_MARKER = "__bad_ref__"


def make_scalar_ref(value: str) -> QBLTaggedMapping:
    return _rebuild_mapping({REF_MARKER: True, "value": value}, "Ref")


def make_scalar_bad_ref(message: str) -> QBLTaggedMapping:
    return _rebuild_mapping({BAD_REF_MARKER: True, "message": message}, "BadRef")


def tag_of(node: Any) -> Optional[str]:
    return getattr(node, "qbl_tag", None)


def is_scalar_ref(node: Any) -> bool:
    return isinstance(node, dict) and node.get(REF_MARKER) is True


def is_bad_ref(node: Any) -> bool:
    return isinstance(node, dict) and node.get(BAD_REF_MARKER) is True


def scalar_ref_value(node: Any) -> str:
    if not is_scalar_ref(node):
        return ""
    value = node.get("value", "")
    return value if isinstance(value, str) else ""
