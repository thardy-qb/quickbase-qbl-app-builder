#!/usr/bin/env python3
"""Report whether a token is stored on this machine, and for which realm.

    python3 scripts/check_token.py
    python3 scripts/check_token.py --format json

This reports presence only. It does not read the secret, does not call
Quickbase, and never prints the token. Storing a token is `store_token.py`,
which the user runs in a terminal.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import qb_common  # noqa: E402,F401
import qb_auth  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        info = qb_auth.status()
    except Exception as exc:  # noqa: BLE001
        info = {"present": False, "store": "", "realm_host": "", "realm_recorded": False,
                "error": f"the credential store could not be queried: {exc}"}
    lines = []
    if info["present"]:
        lines.append(f"token present in: {info['store']}")
        lines.append(f"realm: {info['realm_host'] or '(none recorded)'}")
        if not info["realm_host"]:
            lines.append("store it again with scripts/store_token.py to record the realm")
    else:
        lines.append(info.get("error") or "no token is stored on this machine")
        lines.append("run `python3 scripts/store_token.py` yourself in a terminal, "
                     "or use an installed Claude extension (see SKILL.md)")
    qb_common.emit(info, lines, args.format)
    return qb_common.EXIT_OK if info["present"] and info["realm_host"] else qb_common.EXIT_FINDINGS


if __name__ == "__main__":
    raise SystemExit(qb_common.run_guarded(main))
