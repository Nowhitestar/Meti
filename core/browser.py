"""Browser automation backend — wraps the OpenCLI Browser Bridge.

Background
----------
Earlier versions of this module used Playwright with a fresh Chromium
instance. That ran into two problems:

1. Sites with anti-automation defenses (Google OAuth, Cloudflare, etc.)
   detect Playwright's flags and block login. Users couldn't sign in to
   X / Substack via the fresh Chromium.
2. CDP attach to user's real Chrome required ``--remote-debugging-port``
   plus ``--remote-allow-origins``, which most users don't have set up
   and is friction to configure.

OpenCLI (https://github.com/jackwener/opencli) solves both via a Chrome
extension + local daemon. The user installs the extension once into
their normal Chrome (where they're already logged in to everything),
and any tool can drive that Chrome via the ``opencli browser`` CLI.

Bound workspaces (v0.4.1+)
--------------------------
By default OpenCLI drives a separate "automation window" that's NOT the
user's visible Chrome window. That made meti's actions invisible — the
user couldn't see drafts being prepared, and tabs sometimes vanished
behind other windows.

v0.4.1 fixes this by binding meti to the user's *current* Chrome window:

  $ meti browser bind        # one-shot — attaches bound:meti to the
                             # currently-active Chrome tab/window

After binding, every subsequent meti operation runs against that bound
workspace — i.e. inside the user's visible Chrome. New tabs spawned by
providers appear right next to the user's other tabs.

This module exposes:

- ``bind() / unbind()`` — workspace lifecycle
- ``tab_new(url=None) -> str`` — create a new tab in the bound workspace,
  returns its target id (each browser-flow provider gets its own tab so
  they don't trample one another)
- ``tab_list() / tab_select() / tab_close()``
- the existing primitives (``open_url``, ``click``, ``type_text``,
  ``evaluate``, etc.) — all now route through ``--workspace bound:meti``

Error model
-----------
- ``BrowserNotInstalledError``: OpenCLI not on PATH.
- ``BrowserNotConnectedError``: OpenCLI is callable but the Chrome
  extension is not connected.
- ``BrowserNotBoundError``: bound:meti workspace doesn't exist yet —
  user needs to run ``meti browser bind``.
- ``BrowserCommandError``: catch-all for unrecognized opencli failures.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from core.errors import MetiError

# OpenCLI npm package used at v0.4.1. Pinning lets us evolve the
# backend without breaking users; bump in tandem with provider updates.
_OPENCLI_PKG = "@jackwener/opencli"

# Bound-workspace name. Single workspace shared by every meti session
# on a given machine — there's no reason to multiplex.
WORKSPACE = "bound:meti"


class BrowserNotInstalledError(MetiError):
    """OpenCLI binary not callable. Install Node.js >= 21 and retry."""


class BrowserNotConnectedError(MetiError):
    """OpenCLI reports the Chrome extension is not connected."""


class BrowserNotBoundError(MetiError):
    """``bound:meti`` workspace doesn't exist — user must run
    ``meti browser bind`` from a Chrome tab they want meti to use."""


class BrowserCommandError(MetiError):
    """An opencli browser subcommand failed unexpectedly."""


def _opencli_argv() -> list[str]:
    """Return the argv prefix that invokes opencli."""
    if shutil.which("opencli"):
        return ["opencli"]
    if shutil.which("npx"):
        return ["npx", "-y", _OPENCLI_PKG]
    raise BrowserNotInstalledError(
        "neither `opencli` nor `npx` is on PATH. Install Node.js >= 21:\n"
        "  brew install node          # macOS\n"
        "  apt install nodejs npm     # ubuntu\n"
        "Then meti will use `npx @jackwener/opencli ...` automatically."
    )


def _run(
    args: list[str],
    *,
    check: bool = True,
    timeout: float = 120.0,
    workspace: str | None = WORKSPACE,
) -> dict[str, Any]:
    """Invoke ``opencli browser <args>`` and return parsed JSON output.

    Adds ``--workspace bound:meti`` automatically. Pass ``workspace=None``
    to skip — only used by ``bind()`` and a few diagnostics that need to
    operate before the bound workspace exists.
    """
    full_args = list(args)
    if workspace is not None and "--workspace" not in full_args:
        full_args = ["--workspace", workspace] + full_args
    argv = _opencli_argv() + ["browser"] + full_args
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as e:  # pragma: no cover
        raise BrowserNotInstalledError(str(e)) from e

    stderr = (proc.stderr or "").strip()
    stdout = (proc.stdout or "").strip()

    if proc.returncode != 0:
        low = stderr.lower()
        if "extension not connected" in low or "extension is not connected" in low:
            raise BrowserNotConnectedError(
                "OpenCLI Browser Bridge extension is not connected.\n"
                "1. Install: https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk\n"
                "2. Make sure Chrome is open and the extension is enabled\n"
                "3. Try: `npx @jackwener/opencli doctor`"
            )
        if (
            workspace
            and workspace.startswith("bound:")
            and ("not bound" in low or "no such workspace" in low or "workspace not found" in low)
        ):
            raise BrowserNotBoundError(
                f"meti is not bound to a Chrome tab yet (workspace `{workspace}`).\n"
                "1. Open Chrome and switch to the tab you want meti to use\n"
                "2. Run: meti browser bind\n"
                "Then retry."
            )
        if check:
            raise BrowserCommandError(
                f"opencli browser {' '.join(args)} failed (exit {proc.returncode})\n"
                f"stderr: {stderr}\n"
                f"stdout: {stdout[:500]}"
            )

    if not stdout:
        return {}
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {"_raw": stdout}


# ---------------------------------------------------------------------------
# Workspace lifecycle
# ---------------------------------------------------------------------------


def bind(*, domain: str | None = None, path_prefix: str | None = None) -> dict[str, Any]:
    """Bind the ``bound:meti`` workspace to the current Chrome tab/window.

    The user must have Chrome focused on the tab they want meti to drive
    when this is called. Optional ``domain`` / ``path_prefix`` filters
    let the user constrain which tab is acceptable to bind (used by
    automation scripts that want to fail loudly rather than bind to the
    wrong tab).

    Idempotent: calling bind() when already bound rebinds to whatever
    is currently focused.
    """
    args = ["bind", "--workspace", WORKSPACE]
    if domain:
        args += ["--domain", domain]
    if path_prefix:
        args += ["--path-prefix", path_prefix]
    return _run(args, workspace=None)


def unbind() -> dict[str, Any]:
    """Detach ``bound:meti`` without closing the user's tab."""
    return _run(["unbind", "--workspace", WORKSPACE], workspace=None, check=False)


def is_bound() -> bool:
    """True iff bound:meti workspace exists and is reachable."""
    try:
        tab_list()
        return True
    except (BrowserNotInstalledError, BrowserNotConnectedError, BrowserNotBoundError):
        return False
    except BrowserCommandError:
        return False


def require_bound() -> None:
    """Raise BrowserNotBoundError if not bound. Call this at the top of
    flows that depend on the bound workspace existing."""
    if not is_bound():
        raise BrowserNotBoundError(
            "meti is not bound to a Chrome tab yet.\n"
            "1. Open Chrome and switch to the tab you want meti to use\n"
            "2. Run: meti browser bind\n"
            "Then retry."
        )


# ---------------------------------------------------------------------------
# Tab management
# ---------------------------------------------------------------------------


def tab_list() -> list[dict[str, Any]]:
    """List tabs in the bound workspace."""
    raw = _run(["tab", "list"])
    if isinstance(raw, list):
        return raw
    if "_raw" in raw:
        try:
            parsed = json.loads(raw["_raw"])
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def tab_new(url: str | None = None) -> str:
    """Create a new tab in the bound workspace and return its target id.

    Each browser-flow provider should call ``tab_new()`` early so its
    work is isolated from other providers' tabs. The returned id is
    passed via ``tab=`` to subsequent operations.
    """
    args = ["tab", "new"]
    if url:
        args.append(url)
    raw = _run(args)
    # `tab new` prints the new tab's target id. Could be a plain string
    # or a JSON envelope depending on opencli version.
    if isinstance(raw, dict):
        for key in ("page", "targetId", "id", "tabId"):
            v = raw.get(key)
            if isinstance(v, str) and v:
                return v
        rawval = raw.get("_raw")
        if isinstance(rawval, str) and rawval.strip():
            return rawval.strip()
    raise BrowserCommandError(f"unexpected `tab new` output: {raw!r}")


def tab_select(target_id: str) -> dict[str, Any]:
    """Make ``target_id`` the default tab in the bound workspace."""
    return _run(["tab", "select", target_id])


def tab_close(target_id: str) -> dict[str, Any]:
    """Close a tab by target id (use sparingly — meti's contract is to
    leave the user's tabs open after a publish run)."""
    return _run(["tab", "close", target_id])


# ---------------------------------------------------------------------------
# Page-level primitives — all accept ``tab=<target_id>`` to operate
# on a specific tab in the bound workspace.
# ---------------------------------------------------------------------------


def doctor() -> dict[str, Any]:
    """Run ``opencli doctor`` and return its diagnostic output."""
    argv = _opencli_argv() + ["doctor"]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    return {
        "ok": proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def state(tab: str | None = None) -> dict[str, Any]:
    args = ["state"]
    if tab:
        args += ["--tab", tab]
    return _run(args)


def get_url(tab: str | None = None) -> str:
    args = ["get", "url"]
    if tab:
        args += ["--tab", tab]
    raw = _run(args)
    if "_raw" in raw:
        return str(raw["_raw"]).strip()
    if "value" in raw:
        return str(raw["value"]).strip()
    return ""


def get_title(tab: str | None = None) -> str:
    args = ["get", "title"]
    if tab:
        args += ["--tab", tab]
    raw = _run(args)
    if "_raw" in raw:
        return str(raw["_raw"]).strip()
    if "value" in raw:
        return str(raw["value"]).strip()
    return ""


def open_url(url: str, tab: str | None = None) -> dict[str, Any]:
    """Navigate ``tab`` (or the bound workspace's active tab) to ``url``.

    NB: ``opencli browser open`` opens in the workspace's active tab when
    no ``--tab`` is given. To create a fresh tab, use ``tab_new(url)``.
    """
    args = ["open", url]
    if tab:
        args += ["--tab", tab]
    return _run(args)


def click(target: str, tab: str | None = None) -> dict[str, Any]:
    args = ["click", target]
    if tab:
        args += ["--tab", tab]
    return _run(args)


def type_text(target: str, text: str, tab: str | None = None) -> dict[str, Any]:
    args = ["type", target, text]
    if tab:
        args += ["--tab", tab]
    return _run(args)


def fill(target: str, text: str, tab: str | None = None) -> dict[str, Any]:
    """Set input/textarea/contenteditable text exactly and verify the
    final value (opencli `fill` — added v1.0.5+). Use when you want the
    value replaced wholesale rather than appended."""
    args = ["fill", target, text]
    if tab:
        args += ["--tab", tab]
    return _run(args)


def keys(key: str, tab: str | None = None) -> dict[str, Any]:
    """Press a single keyboard key (e.g. ``Enter``, ``Escape``,
    ``cmd+v``)."""
    args = ["keys", key]
    if tab:
        args += ["--tab", tab]
    return _run(args)


def wait(kind: str, value: str | None = None, tab: str | None = None) -> dict[str, Any]:
    args = ["wait", kind]
    if value is not None:
        args.append(value)
    if tab:
        args += ["--tab", tab]
    return _run(args)


def evaluate(js: str, tab: str | None = None) -> dict[str, Any]:
    args = ["eval", js]
    if tab:
        args += ["--tab", tab]
    return _run(args)


def screenshot(path: str, tab: str | None = None) -> dict[str, Any]:
    args = ["screenshot", path]
    if tab:
        args += ["--tab", tab]
    return _run(args)


def find(selector: str, tab: str | None = None) -> dict[str, Any]:
    args = ["find", "--selector", selector]
    if tab:
        args += ["--tab", tab]
    return _run(args)


def is_connected() -> bool:
    """True iff opencli + extension are responsive (does NOT require
    bound:meti to exist — use ``is_bound()`` for that)."""
    try:
        # `tab list` on a non-bound workspace returns either an empty
        # list or fails with "not bound" — both confirm the bridge.
        _run(["tab", "list"], workspace=None, check=False)
        return True
    except (BrowserNotInstalledError, BrowserNotConnectedError):
        return False
