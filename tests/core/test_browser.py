"""Unit tests for core.browser.

These tests do NOT require playwright to be installed. Tests that exercise
real browser behavior live in providers/<name>/tests/ and are gated on
playwright being importable + a valid login state.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from core import browser
from core.browser import (
    BrowserNotInstalledError,
    BrowserStateMissingError,
    delete_state,
    state_exists,
    state_path,
)


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_state_path_under_user_data_dir(isolated):
    p = state_path("x-article")
    assert p == isolated / ".config" / "mmp" / "browser-state" / "x-article.json"


def test_state_exists_false_initially(isolated):
    assert state_exists("x-article") is False


def test_state_exists_true_after_create(isolated):
    p = state_path("x-article")
    p.parent.mkdir(parents=True)
    p.write_text("{}")
    assert state_exists("x-article") is True


def test_delete_state_removes_file(isolated):
    p = state_path("x-article")
    p.parent.mkdir(parents=True)
    p.write_text("{}")
    assert delete_state("x-article") is True
    assert not p.exists()


def test_delete_state_no_op_when_missing(isolated):
    assert delete_state("x-article") is False


def test_browser_context_missing_state_raises(isolated):
    """Without saved state, browser_context should refuse rather than
    silently launch a fresh (logged-out) browser."""
    with pytest.raises(BrowserStateMissingError, match="x-article"):
        with browser.browser_context("x-article", require_state=True):
            pass


def test_browser_context_playwright_missing_raises_install_hint(isolated):
    """If playwright isn't importable, surface BrowserNotInstalledError
    with the install command in the message."""
    # Pretend playwright import fails
    with patch("core.browser._import_playwright") as mock_import:
        mock_import.side_effect = BrowserNotInstalledError(
            "playwright is not installed. To enable browser-based providers:\n"
            '  pip install -e ".[browser]"\n'
            "  playwright install chromium"
        )
        with pytest.raises(BrowserNotInstalledError, match="playwright install"):
            with browser.browser_context("x-article", require_state=False):
                pass


def test_save_state_writes_chmod_600(isolated):
    """save_state should chmod the file 600 (sensitive: cookies)."""
    import os

    # Build a fake BrowserContext that just dumps to the requested path
    class _FakeCtx:
        def storage_state(self, path: str) -> None:
            with open(path, "w") as f:
                json.dump({"cookies": [], "origins": []}, f)

    p = browser.save_state(_FakeCtx(), "x-article")
    assert p.exists()
    mode = oct(p.stat().st_mode)[-3:]
    assert mode == "600"

    # And the content round-trips
    data = json.loads(p.read_text())
    assert "cookies" in data
    # Cleanup permissions check
    os.chmod(p, 0o600)


def test_state_path_separate_per_provider(isolated):
    a = state_path("x-article")
    b = state_path("substack")
    assert a != b
    assert a.parent == b.parent
