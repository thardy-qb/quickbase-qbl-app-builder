#!/usr/bin/env python3
"""Fixture hygiene: examples use reserved example domains and placeholder hosts."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCANNED = {".py", ".md", ".yaml", ".yml", ".json", ".txt"}
SKIPPED_DIRS = {"__pycache__", ".pytest_cache", "build", "dist", ".git", "tests"}
ALLOWED_EMAIL_DOMAINS = {"example.com", "example.org", "example.net"}
ALLOWED_HOSTS = {"quickbase.com", "www.quickbase.com", "api.quickbase.com",
                 "help.quickbase.com", "developer.quickbase.com",
                 "example.quickbase.com", "myrealm.quickbase.com"}
EMAIL = re.compile(r"[\w.+-]+@([\w-]+\.[A-Za-z]{2,})")
QUICKBASE_HOST = re.compile(r"\b([\w-]+(?:\.[\w-]+)*\.quickbase\.com)\b", re.I)
REALM_DBID_URL = re.compile(r"https?://[\w.-]+/db/b[a-z0-9]{8}", re.I)


def _files():
    for path in sorted(SKILL_ROOT.rglob("*")):
        if path.is_file() and path.suffix in SCANNED and not any(
                part in SKIPPED_DIRS for part in path.relative_to(SKILL_ROOT).parts):
            yield path


class FixtureHygieneTests(unittest.TestCase):
    def test_examples_use_reserved_domains_and_placeholder_hosts(self):
        hits = set()
        for path in _files():
            text = path.read_text(encoding="utf-8", errors="ignore")
            hits |= {m.group(0) for m in EMAIL.finditer(text)
                     if m.group(1).lower() not in ALLOWED_EMAIL_DOMAINS}
            hits |= {m.group(1) for m in QUICKBASE_HOST.finditer(text)
                     if m.group(1).lower() not in ALLOWED_HOSTS}
        self.assertFalse(hits, str(sorted(hits)))

    def test_examples_use_placeholder_dbids_in_urls(self):
        hits = set()
        for path in _files():
            hits |= set(REALM_DBID_URL.findall(path.read_text(encoding="utf-8", errors="ignore")))
        self.assertFalse(hits, str(sorted(hits)))


if __name__ == "__main__":
    unittest.main()
