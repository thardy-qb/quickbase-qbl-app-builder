#!/usr/bin/env python3
"""Where this Skill's Quickbase user token comes from, and the one way it is used.

The only token source is the operating system's credential store: the macOS
Keychain, Windows Credential Manager, or the Linux Secret Service. There is no
environment variable, no file, no command-line argument and no standard-input
path, and nothing here accepts a token pasted into a conversation.

Exactly one function takes a token as an argument, `store_credentials`, and its
only caller is `store_token.py`, which reads the token with `getpass` on a
terminal. Everything else reads the secret from the credential store, once per
HTTP request, immediately before the request, and puts it in a header. It is
never logged, returned in a report, or written to a file.

No platform puts the token in a command's arguments, where other processes
could read it. On macOS `security add-generic-password` is fed through
`security -i` on standard input. On Windows the store is called in-process. On
Linux `secret-tool` reads the token from standard input. A token containing a
double quote, a backslash or a control character is refused on macOS rather
than altered.

The realm is stored with the token in the same entry, because a user token works
only in the realm it was created in. Any realm is accepted.
"""

from __future__ import annotations

import re
from typing import Any, Dict, NamedTuple, Optional

SERVICE = "quickbase-qbl-builder"
ACCOUNT = "user-token"
DEFAULT_DOMAIN = "quickbase.com"

_LABEL = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")


class AuthError(RuntimeError):
    """No usable credential. Never carries the token or the text it was given."""


class Realm(NamedTuple):
    label: str
    host: str


def normalize_realm(text: Any) -> Realm:
    """`myrealm` or `myrealm.quickbase.com` -> `Realm("myrealm", "myrealm.quickbase.com")`.

    A bare label becomes `<label>.quickbase.com`. A dotted name is taken as a
    full hostname and kept as given. Both are validated as hostnames: letters,
    digits and hyphens in each label, no scheme, path, port, whitespace or control
    character (not even leading or trailing). The error never repeats the input,
    because the text at a realm prompt is sometimes the token pasted in the wrong
    place.
    """
    if not isinstance(text, str):
        raise AuthError("the realm must be text")
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise AuthError("a realm holds no whitespace or control characters")
    value = text.lower()
    if not value:
        raise AuthError("no realm was given")
    labels = value.split(".")
    if len(value) > 253 or not all(_LABEL.fullmatch(label) for label in labels):
        raise AuthError("that is not a valid realm: use a name such as `myrealm` or a "
                        "hostname such as `myrealm.quickbase.com`")
    if len(labels) == 1:
        return Realm(value, f"{value}.{DEFAULT_DOMAIN}")
    return Realm(labels[0], value)


def _keystore():
    """The credential-store module, imported when first needed."""
    from qblparser.utils import keystore

    return keystore


def store_name() -> str:
    return _keystore().store_name()


def status() -> Dict[str, Any]:
    """Presence, store and realm. Never reads the secret."""
    keystore = _keystore()
    present, realm = keystore.describe(SERVICE, ACCOUNT)
    host = ""
    if present and realm:
        try:
            host = normalize_realm(realm).host
        except AuthError:
            host = ""
    return {"present": bool(present), "store": keystore.store_name(),
            "realm_host": host, "realm_recorded": bool(host)}


def stored_realm_host() -> str:
    """The realm host stored with the token, or an `AuthError` that says what to do."""
    info = status()
    if not info["present"]:
        raise AuthError(
            "no Quickbase user token is stored on this machine. Run "
            "`python3 scripts/store_token.py` yourself in a terminal; it prompts for "
            "the realm and the token. Do not paste a token into the conversation.")
    if not info["realm_host"]:
        raise AuthError(
            "a token is stored but no realm was recorded with it. Run "
            "`python3 scripts/store_token.py` again to store the realm with the token.")
    return info["realm_host"]


def request_headers(realm_host: str, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Headers for one Solutions API request, with the secret read now.

    Called once per request, by the code about to send it. The secret is held
    in a local variable for the length of this call and placed in the
    `Authorization` header; the caller must not keep or print the result.
    """
    secret = _keystore().read_secret(SERVICE, ACCOUNT)
    if not secret:
        raise AuthError("the stored token could not be read from this machine's "
                        "credential store. Store it again with "
                        "`python3 scripts/store_token.py`.")
    headers = {"Authorization": f"QB-USER-TOKEN {secret}",
               "QB-Realm-Hostname": realm_host}
    if extra:
        headers.update(extra)
    return headers


def store_credentials(realm_text: str, secret: str) -> Realm:
    """Write the realm and token to the credential store. Fed by `getpass` only."""
    realm = normalize_realm(realm_text)
    if not isinstance(secret, str) or not secret.strip():
        raise AuthError("no token was entered")
    if not _keystore().write(SERVICE, ACCOUNT, secret, realm.host):
        raise AuthError("could not write to this machine's credential store")
    return realm


def remove_credentials() -> bool:
    keystore = _keystore()
    if not keystore.exists(SERVICE, ACCOUNT):
        return True
    return bool(keystore.delete(SERVICE, ACCOUNT))
