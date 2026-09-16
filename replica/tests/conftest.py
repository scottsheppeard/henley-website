"""Test fixtures for the replica export.

The 2026-09-09 capture is the fixture set: real Elementor pages as WordPress
served them, immutable, so every rule is tested against the markup it has to
handle rather than a hand-written approximation of it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPLICA_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = REPLICA_DIR.parent
CAPTURE = REPO_ROOT / "source/live-capture-2026-09-09/pages"

sys.path.insert(0, str(REPLICA_DIR))


@pytest.fixture(scope="session")
def capture():
    def read(slug: str) -> str:
        return (CAPTURE / f"{slug}.html").read_text(encoding="utf-8")
    return read


@pytest.fixture(scope="session")
def form_html() -> str:
    return (REPLICA_DIR / "form.html").read_text(encoding="utf-8")
