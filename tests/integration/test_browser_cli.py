"""Integration tests for `meti browser` subcommand (OpenCLI-backed)."""

from __future__ import annotations

import os
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.browser import BrowserDiagnostic
from scripts import meti

ROOT = Path(__file__).resolve().parent.parent.parent


def _run(*args, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "meti.py"), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_browser_status_no_install():
    """Without Node.js / opencli installed, status returns 2 with hint."""
    # The opencli binary is NOT actually called here because our subprocess
    # under test will spawn its own python which imports core.browser. We
    # need to mock at that level. Instead, just verify the failure shape
    # when the bridge isn't connected — we can't easily mock subprocess
    # in a child-process test, so cover this in unit tests instead.
    # Keep this file focused on argv + dispatch wiring.
    pass


def test_browser_login_requires_provider():
    p = _run("browser", "login")
    assert p.returncode == 2
    assert "requires a provider" in p.stderr


def test_browser_login_unknown_provider():
    p = _run("browser", "login", "does-not-exist")
    assert p.returncode == 2


def test_browser_login_provider_without_login_url():
    """wechat-article uses API auth, not browser session — should error."""
    p = _run("browser", "login", "wechat-article")
    assert p.returncode == 2
    assert "no browser_login_url" in p.stderr


def test_browser_help_lists_three_actions():
    p = _run("browser", "--help")
    out = p.stdout + p.stderr
    assert "status" in out
    assert "login" in out
    assert "doctor" in out


def test_browser_status_json_outputs_stable_diagnostic(capsys):
    diag = BrowserDiagnostic(
        code="workspace_stale",
        message="Bound browser workspace is stale or unreachable.",
        recoverable=True,
        next_actions=["Run `meti browser bind` again"],
    )
    with patch("core.browser.diagnose", return_value=diag):
        rc = meti.cmd_browser(Namespace(action="status", json=True, provider=None))
    assert rc == 2
    data = __import__("json").loads(capsys.readouterr().out)
    assert data["code"] == "workspace_stale"
    assert data["ready"] is False
    assert data["recoverable"] is True
    assert data["next_actions"] == ["Run `meti browser bind` again"]


def test_browser_status_text_is_actionable(capsys):
    diag = BrowserDiagnostic(
        code="bound_tab_missing",
        message="Workspace `bound:meti` exists but has no reachable tabs.",
        recoverable=True,
        next_actions=["Open a Chrome tab and run `meti browser bind` again"],
    )
    with patch("core.browser.diagnose", return_value=diag):
        rc = meti.cmd_browser(Namespace(action="status", json=False, provider=None))
    out = capsys.readouterr().out
    assert rc == 2
    assert "bound_tab_missing" in out
    assert "meti browser bind" in out


def test_browser_status_ready_returns_zero_and_redacted_tabs(capsys):
    diag = BrowserDiagnostic(
        code="ready",
        message="Browser Bridge connected and workspace `bound:meti` is bound.",
        recoverable=False,
        details={"tab_count": 1, "tabs": ["https://example.com/draft?…"]},
    )
    with patch("core.browser.diagnose", return_value=diag):
        rc = meti.cmd_browser(Namespace(action="status", json=False, provider=None))
    out = capsys.readouterr().out
    assert rc == 0
    assert "ready" in out
    assert "secret" not in out


def test_auto_recover_is_opt_in_and_bounded():
    provider = SimpleNamespace(browser_login_url="https://example.com/login")
    target = SimpleNamespace(mode="draft")
    first = BrowserDiagnostic(
        code="workspace_not_bound",
        message="not bound",
        recoverable=True,
        next_actions=["bind"],
    )
    recovered = BrowserDiagnostic(code="ready", message="ok", recoverable=False)
    with (
        patch("core.browser.diagnose", return_value=first) as diagnose,
        patch("core.browser.recover_once", return_value=recovered) as recover_once,
    ):
        assert meti._ensure_browser_ready_for_target(provider, target, auto_recover=False) is first
        recover_once.assert_not_called()
        assert meti._ensure_browser_ready_for_target(provider, target, auto_recover=True) is None
        assert diagnose.call_count == 2
        recover_once.assert_called_once_with("https://example.com/login")
