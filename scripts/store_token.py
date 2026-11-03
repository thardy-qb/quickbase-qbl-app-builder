#!/usr/bin/env python3
"""Store, or remove, the Quickbase user token this Skill uses.

    python3 scripts/store_token.py            # prompt for realm and token
    python3 scripts/store_token.py --remove   # delete the stored token
    python3 scripts/store_token.py --where    # store and realm, never the token

Run it yourself in a terminal. It prompts for the realm and then for the token,
twice, with `getpass`, so nothing is echoed and the token never reaches this
script's own arguments, a shell history or a transcript. It is handed to the
credential store on standard input (macOS `security -i`, Linux `secret-tool`)
or in-process (Windows), never as a command argument. It refuses to run without a
terminal: an agent cannot answer the prompts, and a token read from a pipe has
been handled by whatever wrote the pipe.

The token goes to the macOS Keychain, Windows Credential Manager or the Linux
Secret Service, with the realm stored beside it.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import qb_common  # noqa: E402,F401  (puts the QBL library on sys.path)
import qb_auth  # noqa: E402


def _where() -> int:
    info = qb_auth.status()
    if not info["present"]:
        print("token found in: nothing on this machine")
        return 1
    print(f"token found in: {info['store']}")
    print(f"realm:          {info['realm_host'] or '(none recorded)'}")
    return 0 if info["realm_host"] else 1


def _remove() -> int:
    if qb_auth.remove_credentials():
        print("removed the stored token (or none was stored)")
        return 0
    print("could not remove the stored token", file=sys.stderr)
    return 1


def _store() -> int:
    if not sys.stdin.isatty():
        print("store_token.py needs a terminal: it prompts for the token so that the "
              "secret is not in this script's arguments or a shell history.\n\n"
              "Run it yourself in a terminal.", file=sys.stderr)
        return 2
    try:
        realm = qb_auth.normalize_realm(
            input("Realm the token was created in (e.g. myrealm or "
                  "myrealm.quickbase.com): "))
    except qb_auth.AuthError as exc:
        print(f"{exc}; nothing was stored", file=sys.stderr)
        return 2
    print(f"\nPaste your Quickbase user token for https://{realm.host}.")
    print("Nothing will appear as you type. Press Return when done.\n")
    secret = getpass.getpass("Quickbase user token: ")
    if not secret.strip():
        print("no token entered; nothing was stored", file=sys.stderr)
        return 2
    if secret != getpass.getpass("Confirm the token: "):
        print("the two entries did not match; nothing was stored", file=sys.stderr)
        return 2
    try:
        qb_auth.store_credentials(realm.host, secret)
    except qb_auth.AuthError as exc:
        print(f"{exc}", file=sys.stderr)
        return 1
    info = qb_auth.status()
    print(f"\nstored in: {info['store']}")
    print(f"service:   {qb_auth.SERVICE}")
    print(f"account:   {qb_auth.ACCOUNT}")
    print(f"realm:     {info['realm_host']}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Store the Quickbase user token used by this Skill.",
        epilog="Run this yourself in a terminal; it prompts for the realm and token.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--remove", action="store_true", help="delete the stored token")
    group.add_argument("--where", action="store_true",
                       help="name the store and realm, never the token")
    args = parser.parse_args(argv)
    try:
        if args.where:
            return _where()
        if args.remove:
            return _remove()
        return _store()
    except qb_auth.AuthError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
