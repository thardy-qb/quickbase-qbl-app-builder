from __future__ import annotations

import re
import subprocess
import sys
from typing import List, Optional, Tuple


_REALM_KEY = "realm"

_LOOKUP_TIMEOUT = 10

_LEGACY_USERNAME = "token"


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _is_macos() -> bool:
    return sys.platform == "darwin"


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def _run(argv: List[str]) -> Optional[str]:
    try:
        completed = subprocess.run(argv, capture_output=True, timeout=_LOOKUP_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.decode("utf-8", "replace").strip()
    return value or None


def _probe(argv: List[str]) -> bool:
    try:
        completed = subprocess.run(argv, capture_output=True, timeout=_LOOKUP_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _macos_token(service: str, account: str) -> Optional[str]:
    value = _run(["security", "find-generic-password",
                  "-s", service, "-a", account, "-w"])
    if value:
        return value
    return _run(["security", "find-generic-password", "-s", service, "-w"])


def _macos_exists(service: str, account: str) -> bool:
    if _probe(["security", "find-generic-password", "-s", service, "-a", account]):
        return True
    return _probe(["security", "find-generic-password", "-s", service])


_MACOS_REALM = re.compile(r'"icmt"<blob>="(?:' + _REALM_KEY + r'=)?([^"]*)"')


def _macos_describe(service: str, account: str) -> Tuple[bool, Optional[str]]:
    for argv in (["security", "find-generic-password", "-s", service, "-a", account],
                 ["security", "find-generic-password", "-s", service]):
        listing = _run(argv)
        if listing is not None:
            match = _MACOS_REALM.search(listing)
            return True, (match.group(1) if match else None)
    return False, None


_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2


def _windows_api():
    try:
        import ctypes
        from ctypes import wintypes
    except (ImportError, ValueError):
        return None

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD),
                    ("dwHighDateTime", wintypes.DWORD)]

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    try:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    except (AttributeError, OSError):
        return None

    advapi32.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   ctypes.POINTER(ctypes.POINTER(CREDENTIALW))]
    advapi32.CredReadW.restype = wintypes.BOOL
    advapi32.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
    advapi32.CredWriteW.restype = wintypes.BOOL
    advapi32.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    advapi32.CredDeleteW.restype = wintypes.BOOL
    advapi32.CredFree.argtypes = [ctypes.c_void_p]
    advapi32.CredFree.restype = None
    return advapi32, CREDENTIALW


def _windows_token(service: str, account: str) -> Optional[str]:
    import ctypes

    loaded = _windows_api()
    if loaded is None:
        return None
    advapi32, CREDENTIALW = loaded

    pointer = ctypes.POINTER(CREDENTIALW)()
    if not advapi32.CredReadW(service, _CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
        return None
    try:
        credential = pointer.contents
        size = int(credential.CredentialBlobSize)
        if size <= 0:
            return None
        raw = ctypes.string_at(credential.CredentialBlob, size)
    finally:
        advapi32.CredFree(pointer)

    for encoding in ("utf-16-le", "utf-8"):
        try:
            value = raw.decode(encoding).strip("\x00").strip()
        except UnicodeDecodeError:
            continue
        if value:
            return value
    return None


def _windows_exists(service: str, account: str) -> bool:
    import ctypes

    loaded = _windows_api()
    if loaded is None:
        return False
    advapi32, CREDENTIALW = loaded

    pointer = ctypes.POINTER(CREDENTIALW)()
    if not advapi32.CredReadW(service, _CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
        return False
    try:
        return int(pointer.contents.CredentialBlobSize) > 0
    finally:
        advapi32.CredFree(pointer)


def _realm_from_username(username: Optional[str],
                         account: str = _LEGACY_USERNAME) -> Optional[str]:
    value = (username or "").strip()
    if not value or value.lower() in (account.lower(), _LEGACY_USERNAME):
        return None
    return value


def _windows_describe(service: str, account: str) -> Tuple[bool, Optional[str]]:
    import ctypes

    loaded = _windows_api()
    if loaded is None:
        return False, None
    advapi32, CREDENTIALW = loaded

    pointer = ctypes.POINTER(CREDENTIALW)()
    if not advapi32.CredReadW(service, _CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
        return False, None
    try:
        credential = pointer.contents
        if int(credential.CredentialBlobSize) <= 0:
            return False, None
        return True, _realm_from_username(credential.UserName, account)
    finally:
        advapi32.CredFree(pointer)


def _windows_store(service: str, account: str, secret: str, realm: str) -> bool:
    import ctypes

    loaded = _windows_api()
    if loaded is None:
        return False
    advapi32, CREDENTIALW = loaded

    blob = secret.encode("utf-16-le")
    blob_buffer = ctypes.create_string_buffer(blob, len(blob))

    credential = CREDENTIALW()
    credential.Flags = 0
    credential.Type = _CRED_TYPE_GENERIC
    credential.TargetName = service
    credential.Comment = "Stored by the QBL Skills"
    credential.CredentialBlobSize = len(blob)
    credential.CredentialBlob = ctypes.cast(blob_buffer, ctypes.POINTER(ctypes.c_char))
    credential.Persist = _CRED_PERSIST_LOCAL_MACHINE
    credential.AttributeCount = 0
    credential.Attributes = None
    credential.TargetAlias = None
    credential.UserName = realm
    return bool(advapi32.CredWriteW(ctypes.byref(credential), 0))


def _windows_delete(service: str) -> bool:
    loaded = _windows_api()
    if loaded is None:
        return False
    advapi32, _ = loaded
    return bool(advapi32.CredDeleteW(service, _CRED_TYPE_GENERIC, 0))


def _linux_token(service: str, account: str) -> Optional[str]:
    return _run(["secret-tool", "lookup", "service", service, "account", account])


def _linux_exists(service: str, account: str) -> bool:
    return _probe(["secret-tool", "lookup", "service", service, "account", account])


def _linux_describe(service: str, account: str) -> Tuple[bool, Optional[str]]:
    try:
        completed = subprocess.run(
            ["secret-tool", "search", "service", service, "account", account],
            capture_output=True, timeout=_LOOKUP_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return False, None
    if completed.returncode != 0:
        return False, None
    present, realm = False, None
    for line in completed.stdout.splitlines():
        if line.startswith(b"attribute.service = "):
            present = True
        elif line.startswith(b"attribute." + _REALM_KEY.encode() + b" = "):
            realm = line.split(b" = ", 1)[1].decode("utf-8", "replace").strip()
    return present, realm


def _linux_store(service: str, account: str, secret: str, realm: str) -> bool:
    _probe(["secret-tool", "clear", "service", service, "account", account])
    try:
        completed = subprocess.run(
            ["secret-tool", "store", f"--label={service} ({realm})",
             "service", service, "account", account, _REALM_KEY, realm],
            input=secret.encode("utf-8"), capture_output=True,
            timeout=_LOOKUP_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def store_name() -> str:
    if _is_macos():
        return "macOS keychain"
    if _is_windows():
        return "Windows Credential Manager"
    if _is_linux():
        return "Secret Service (secret-tool)"
    return ""


def read_secret(service: str, account: str) -> Optional[str]:
    try:
        if _is_macos():
            return _macos_token(service, account)
        if _is_windows():
            return _windows_token(service, account)
        if _is_linux():
            return _linux_token(service, account)
    except Exception:
        return None
    return None


def exists(service: str, account: str) -> bool:
    try:
        if _is_macos():
            return _macos_exists(service, account)
        if _is_windows():
            return _windows_exists(service, account)
        if _is_linux():
            return _linux_exists(service, account)
    except Exception:
        return False
    return False


def describe(service: str, account: str) -> Tuple[bool, Optional[str]]:
    try:
        if _is_macos():
            return _macos_describe(service, account)
        if _is_windows():
            return _windows_describe(service, account)
        if _is_linux():
            return _linux_describe(service, account)
    except Exception:
        return False, None
    return False, None


def _macos_quote(value: str) -> Optional[str]:
    if any(ch in value for ch in '"\\') or any(ord(ch) < 0x20 or ord(ch) == 0x7F
                                               for ch in value):
        return None
    return f'"{value}"'


def _macos_store(service: str, account: str, secret: str, realm: str) -> bool:
    parts = [_macos_quote(value) for value in
             (service, account, f"{_REALM_KEY}={realm}", secret)]
    if any(part is None for part in parts):
        return False
    quoted_service, quoted_account, quoted_comment, quoted_secret = parts
    line = (f"add-generic-password -U -s {quoted_service} -a {quoted_account} "
            f"-j {quoted_comment} -w {quoted_secret}\n")
    try:
        completed = subprocess.run(["security", "-i"], input=line.encode("utf-8"),
                                   capture_output=True, timeout=_LOOKUP_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def write(service: str, account: str, secret: str, realm: str) -> bool:
    if not secret or not secret.strip():
        return False
    secret = secret.strip()
    if _is_macos():
        return _macos_store(service, account, secret, realm)
    if _is_windows():
        return _windows_store(service, account, secret, realm)
    if _is_linux():
        return _linux_store(service, account, secret, realm)
    return False


def delete(service: str, account: str) -> bool:
    if _is_macos():
        removed = _probe(["security", "delete-generic-password",
                          "-s", service, "-a", account])
        return removed or _probe(["security", "delete-generic-password",
                                  "-s", service])
    if _is_windows():
        return _windows_delete(service)
    if _is_linux():
        return _probe(["secret-tool", "clear", "service", service, "account", account])
    return False


__all__ = [
    "delete",
    "describe",
    "exists",
    "read_secret",
    "store_name",
    "write",
]
