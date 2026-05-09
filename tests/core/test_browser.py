"""Unit tests for core.browser (OpenCLI-backed).

We mock subprocess.run so tests don't require opencli or a Chrome
extension to be installed. Real-browser tests (that actually drive
Chrome) live in providers/<name>/tests/ behind feature flags.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from core import browser as br
from core.browser import (
    BrowserCommandError,
    BrowserNotConnectedError,
    BrowserNotInstalledError,
    is_connected,
    open_url,
    state,
)


def _mock_run(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Returns a CompletedProcess-shaped object for subprocess.run mocks."""

    class _CP:
        def __init__(self) -> None:
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

    return _CP()


def test_state_returns_parsed_json():
    """`browser state` emits JSON; we parse and return as dict."""
    with (
        patch("core.browser.shutil.which", return_value="/usr/bin/opencli"),
        patch("core.browser.subprocess.run") as mock_run,
    ):
        mock_run.return_value = _mock_run(
            stdout=json.dumps({"url": "https://x.com", "title": "X"}),
            returncode=0,
        )
        result = state()
        assert result == {"url": "https://x.com", "title": "X"}


def test_state_falls_back_to_modern_npx_when_opencli_missing():
    """If `opencli` not on PATH, use a Node>=21 npx for OpenCLI."""
    with (
        patch(
            "core.browser.shutil.which",
            side_effect=lambda c: "/usr/bin/npx" if c == "npx" else None,
        ),
        patch("core.browser._node_major_for_npx", return_value=24),
        patch("core.browser.subprocess.run") as mock_run,
    ):
        mock_run.return_value = _mock_run(stdout="{}", returncode=0)
        state()
        argv = mock_run.call_args[0][0]
        assert argv[0] == "/usr/bin/env"
        assert argv[1].startswith("PATH=")
        assert any(arg.endswith("/npx") or arg == "npx" for arg in argv)
        assert "-y" in argv
        assert "@jackwener/opencli" in argv
        assert "browser" in argv
        assert "state" in argv


def test_no_opencli_no_npx_raises_install_hint():
    with (
        patch("core.browser.shutil.which", return_value=None),
        patch("core.browser.Path.exists", return_value=False),
    ):
        with pytest.raises(BrowserNotInstalledError, match="Node.js"):
            state()


def test_extension_not_connected_raises_specific_error():
    """When opencli reports `extension not connected`, raise the typed
    BrowserNotConnectedError with the install link."""
    with (
        patch("core.browser.shutil.which", return_value="/usr/bin/opencli"),
        patch("core.browser.subprocess.run") as mock_run,
    ):
        mock_run.return_value = _mock_run(
            stdout="",
            stderr="✖  Browser Bridge extension not connected",
            returncode=1,
        )
        with pytest.raises(BrowserNotConnectedError, match="not connected"):
            state()


def test_other_failure_raises_command_error():
    with (
        patch("core.browser.shutil.which", return_value="/usr/bin/opencli"),
        patch("core.browser.subprocess.run") as mock_run,
    ):
        mock_run.return_value = _mock_run(
            stdout="",
            stderr="some other error",
            returncode=2,
        )
        with pytest.raises(BrowserCommandError, match="exit 2"):
            state()


def test_open_url_invocation():
    with (
        patch("core.browser.shutil.which", return_value="/usr/bin/opencli"),
        patch("core.browser.subprocess.run") as mock_run,
    ):
        mock_run.return_value = _mock_run(
            stdout=json.dumps({"target": "tab-1"}),
            returncode=0,
        )
        result = open_url("https://example.com")
        argv = mock_run.call_args[0][0]
        # Browser-flow navigation uses the visible bound workspace and must
        # explicitly allow navigating that user-bound tab.
        assert argv[-3:] == ["open", "https://example.com", "--allow-navigate-bound"]
        assert "--workspace" in argv
        assert "bound:meti" in argv
        assert result == {"target": "tab-1"}


def test_type_text_argv():
    """`browser type <target> <text>` should pass exactly two trailing args."""
    with (
        patch("core.browser.shutil.which", return_value="/usr/bin/opencli"),
        patch("core.browser.subprocess.run") as mock_run,
    ):
        mock_run.return_value = _mock_run(stdout="{}", returncode=0)
        br.type_text("[1]", "hello world")
        argv = mock_run.call_args[0][0]
        assert "type" in argv
        assert "[1]" in argv
        assert "hello world" in argv


def test_is_connected_true_when_state_succeeds():
    with (
        patch("core.browser.shutil.which", return_value="/usr/bin/opencli"),
        patch("core.browser.subprocess.run") as mock_run,
    ):
        mock_run.return_value = _mock_run(stdout="{}", returncode=0)
        assert is_connected() is True


def test_is_connected_false_when_extension_not_connected():
    with (
        patch("core.browser.shutil.which", return_value="/usr/bin/opencli"),
        patch("core.browser.subprocess.run") as mock_run,
    ):
        mock_run.return_value = _mock_run(
            stderr="✖  Browser Bridge extension not connected",
            returncode=1,
        )
        assert is_connected() is False


def test_is_connected_false_when_no_opencli():
    with (
        patch("core.browser.shutil.which", return_value=None),
        patch("core.browser.Path.exists", return_value=False),
    ):
        assert is_connected() is False


def test_tab_arg_threads_through():
    with (
        patch("core.browser.shutil.which", return_value="/usr/bin/opencli"),
        patch("core.browser.subprocess.run") as mock_run,
    ):
        mock_run.return_value = _mock_run(stdout="{}", returncode=0)
        state(tab="abc-123")
        argv = mock_run.call_args[0][0]
        assert "--tab" in argv
        assert "abc-123" in argv


def test_non_json_stdout_returned_as_raw():
    """`extract` and similar emit non-JSON; should return {'_raw': ...}."""
    with (
        patch("core.browser.shutil.which", return_value="/usr/bin/opencli"),
        patch("core.browser.subprocess.run") as mock_run,
    ):
        mock_run.return_value = _mock_run(
            stdout="some plain text output\nmultiple lines",
            returncode=0,
        )
        result = state()
        assert result["_raw"] == "some plain text output\nmultiple lines"
