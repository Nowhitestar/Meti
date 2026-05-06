"""Integration tests for `mmp browser` subcommand."""

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


def test_status_empty_when_no_states(tmp_path):
    p = _run(
        "browser",
        "status",
        env_extra={"XDG_CONFIG_HOME": str(tmp_path / "xdg")},
    )
    assert p.returncode == 0
    assert "no saved browser states" in p.stdout


def test_status_lists_existing_states(tmp_path):
    state_dir = tmp_path / "xdg" / "mmp" / "browser-state"
    state_dir.mkdir(parents=True)
    (state_dir / "x-article.json").write_text("{}")
    (state_dir / "substack.json").write_text("{}")

    p = _run(
        "browser",
        "status",
        env_extra={"XDG_CONFIG_HOME": str(tmp_path / "xdg")},
    )
    assert p.returncode == 0
    assert "x-article" in p.stdout
    assert "substack" in p.stdout


def test_logout_removes_state(tmp_path):
    state_dir = tmp_path / "xdg" / "mmp" / "browser-state"
    state_dir.mkdir(parents=True)
    state_file = state_dir / "x-article.json"
    state_file.write_text("{}")

    p = _run(
        "browser",
        "logout",
        "x-article",
        env_extra={"XDG_CONFIG_HOME": str(tmp_path / "xdg")},
    )
    assert p.returncode == 0
    assert "removed" in p.stdout
    assert not state_file.exists()


def test_logout_no_op_when_missing(tmp_path):
    p = _run(
        "browser",
        "logout",
        "x-article",
        env_extra={"XDG_CONFIG_HOME": str(tmp_path / "xdg")},
    )
    assert p.returncode == 0
    assert "no saved state" in p.stdout


def test_login_requires_provider_with_browser_login_url(tmp_path):
    """wechat-article doesn't have browser_login_url → error."""
    p = _run(
        "browser",
        "login",
        "wechat-article",
        env_extra={"XDG_CONFIG_HOME": str(tmp_path / "xdg")},
    )
    assert p.returncode == 2
    assert "no browser_login_url" in p.stderr


def test_login_provider_not_found(tmp_path):
    p = _run(
        "browser",
        "login",
        "does-not-exist",
        env_extra={"XDG_CONFIG_HOME": str(tmp_path / "xdg")},
    )
    assert p.returncode == 2


def test_login_without_provider_arg_errors():
    p = _run("browser", "login")
    assert p.returncode == 2
    assert "requires a provider" in p.stderr
