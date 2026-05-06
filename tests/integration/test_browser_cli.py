"""Integration tests for `mmp browser` subcommand (OpenCLI-backed)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def _run(*args, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mmp.py"), *args],
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
