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
import os
import platform
import shutil
import subprocess
import time
import uuid
from pathlib import Path
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


def _node_major_for_npx(npx_path: str) -> int | None:
    """Return the sibling node major version for an npx binary, if known."""
    node = Path(npx_path).with_name("node")
    if not node.exists():
        return None
    try:
        proc = subprocess.run(
            [str(node), "--version"], capture_output=True, text=True, timeout=5
        )
    except Exception:
        return None
    version = (proc.stdout or proc.stderr or "").strip().lstrip("v")
    try:
        return int(version.split(".", 1)[0])
    except (ValueError, IndexError):
        return None


def _npx_candidates() -> list[str]:
    """Candidate npx binaries, preferring Node >= 21.

    The user's shell PATH may put an old nvm Node first. OpenCLI currently
    requires Node >= 21, so blindly using `shutil.which("npx")` can make
    `meti browser status` look connected while every real browser command
    crashes inside undici. Prefer explicit modern Homebrew / nvm installs.
    """
    candidates: list[str] = []
    first = shutil.which("npx")
    if first:
        candidates.append(first)
    candidates.extend(
        [
            "/opt/homebrew/bin/npx",
            "/usr/local/bin/npx",
        ]
    )
    nvm = Path.home() / ".nvm" / "versions" / "node"
    if nvm.exists():
        for npx in sorted(nvm.glob("v*/bin/npx"), reverse=True):
            candidates.append(str(npx))
    seen: set[str] = set()
    uniq: list[str] = []
    for c in candidates:
        if c not in seen and Path(c).exists():
            seen.add(c)
            uniq.append(c)
    return uniq


def _opencli_argv() -> list[str]:
    """Return the argv prefix that invokes opencli.

    Prefer a verified Node>=21 `npx` even if an `opencli` binary exists: the
    installed binary may be a shim that resolves through the user's older PATH
    Node (Node 20 breaks current OpenCLI/undici). Fall back to `opencli` only
    when no modern npx is available.
    """
    modern: list[str] = []
    fallback: list[str] = []
    for npx in _npx_candidates():
        major = _node_major_for_npx(npx)
        if major is not None and major >= 21:
            modern.append(npx)
        else:
            fallback.append(npx)
    if modern:
        npx = modern[0]
        bindir = str(Path(npx).parent)
        env_path = f"PATH={bindir}:{os.environ.get('PATH', '')}"
        return ["/usr/bin/env", env_path, npx, "-y", _OPENCLI_PKG]

    opencli = shutil.which("opencli")
    if opencli:
        return [opencli]

    if fallback:
        raise BrowserNotInstalledError(
            "OpenCLI requires Node.js >= 21, but the first available npx uses "
            "an older Node. Install/activate a modern Node or put it earlier on PATH.\n"
            f"Checked: {', '.join(fallback)}"
        )
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
    workspace: str | None = None,
) -> dict[str, Any]:
    """Invoke ``opencli browser <args>`` and return parsed JSON output.

    Default workspace is whatever opencli picks (``browser:default`` —
    its automation Chrome window). Pass ``workspace="bound:meti"`` for
    operations that need the user's bound tab (used by ``bind()`` and
    a few advanced flows). Most provider work uses the default.
    """
    full_args = list(args)
    # OpenCLI v1.7+ changed browser session selection from
    # `browser --workspace <name> <cmd>` to `browser <session> <cmd>`.
    # Keep the Meti API stable by translating `workspace` here.
    session = workspace or "default"
    argv = _opencli_argv() + ["browser", session] + full_args
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
    constrain which tab is acceptable to bind.
    """
    args = ["bind"]
    # OpenCLI v1.7 positional-session bind has no --domain/--path-prefix filters.
    # The caller already opens the desired URL before binding, so ignore filters here.
    return _run(args, workspace=WORKSPACE)


def _open_chrome_tab(url: str) -> None:
    """Open a new visible tab in the user's real Chrome and focus it."""
    if platform.system() == "Darwin":
        subprocess.run(["open", "-a", "Google Chrome", url], check=False, timeout=10)
        time.sleep(1.5)
        return
    # Linux fallback: xdg-open focuses the default browser if available.
    opener = shutil.which("xdg-open") or shutil.which("google-chrome") or shutil.which("chromium")
    if opener:
        subprocess.run([opener, url], check=False, timeout=10)
        time.sleep(1.5)


def auto_bind(
    url: str = "about:blank",
    *,
    domain: str | None = None,
    path_prefix: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Ensure ``bound:meti`` exists by opening a visible Chrome tab and binding it.

    This is intentionally user-visible: Meti opens a real Chrome tab, then
    asks OpenCLI to bind the current active tab to the workspace. Providers
    can call this before browser-flow execution so publish runs do not stop
    with "run meti browser bind".
    """
    if not force and is_bound():
        return {"status": "already-bound"}
    _open_chrome_tab(url)
    return bind(domain=domain, path_prefix=path_prefix)


def ensure_bound(
    url: str = "about:blank",
    *,
    domain: str | None = None,
    path_prefix: str | None = None,
) -> bool:
    """Auto-bind if needed, returning True or raising a clear bridge error."""
    if is_bound():
        return True
    auto_bind(url=url, domain=domain, path_prefix=path_prefix, force=True)
    return True


def unbind() -> dict[str, Any]:
    """Detach ``bound:meti`` without closing the user's tab."""
    return _run(["unbind"], workspace=WORKSPACE, check=False)


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
    """Raise BrowserNotBoundError if bound:meti doesn't exist.

    Most publish flows should prefer ``ensure_bound(...)`` so Meti opens
    a visible tab automatically. Keep this strict helper for diagnostics.
    """
    if not is_bound():
        raise BrowserNotBoundError(
            "meti is not bound to a Chrome tab yet.\n"
            "Meti can usually auto-bind; otherwise open Chrome and run: meti browser bind\n"
            "Then retry."
        )


# ---------------------------------------------------------------------------
# Tab management
# ---------------------------------------------------------------------------


def tab_list() -> list[dict[str, Any]]:
    """List tabs in the bound workspace."""
    raw = _run(["tab", "list"], workspace=WORKSPACE)
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
    raw = _run(args, workspace=WORKSPACE)
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
    return _run(["tab", "select", target_id], workspace=WORKSPACE)


def tab_close(target_id: str) -> dict[str, Any]:
    """Close a tab by target id (use sparingly — meti's contract is to
    leave the user's tabs open after a publish run)."""
    return _run(["tab", "close", target_id], workspace=WORKSPACE)


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
    return _run(args, workspace=WORKSPACE)


def get_url(tab: str | None = None) -> str:
    args = ["get", "url"]
    if tab:
        args += ["--tab", tab]
    raw = _run(args, workspace=WORKSPACE)
    if "_raw" in raw:
        return str(raw["_raw"]).strip()
    if "value" in raw:
        return str(raw["value"]).strip()
    return ""


def get_title(tab: str | None = None) -> str:
    args = ["get", "title"]
    if tab:
        args += ["--tab", tab]
    raw = _run(args, workspace=WORKSPACE)
    if "_raw" in raw:
        return str(raw["_raw"]).strip()
    if "value" in raw:
        return str(raw["value"]).strip()
    return ""


def open_url(url: str, tab: str | None = None) -> dict[str, Any]:
    """Navigate the automation tab to ``url``.

    By default this hits OpenCLI's ``browser:default`` automation
    workspace — opencli will spawn a fresh tab in your Chrome on first
    call, then reuse it across provider runs. Each provider in a
    sequential publish navigates the same tab through to its editor.

    Advanced: if you've run ``meti browser bind``, you can pin meti to
    a specific Chrome tab. In that case ``open_url`` is wrapped with
    ``--allow-navigate-bound`` (see core.browser.WORKSPACE).
    """
    args = ["open", url]
    if tab:
        args += ["--tab", tab]
    return _run(args, workspace=WORKSPACE)


def click(target: str, tab: str | None = None) -> dict[str, Any]:
    args = ["click", target]
    if tab:
        args += ["--tab", tab]
    return _run(args, workspace=WORKSPACE)


def type_text(target: str, text: str, tab: str | None = None) -> dict[str, Any]:
    args = ["type", target, text]
    if tab:
        args += ["--tab", tab]
    return _run(args, workspace=WORKSPACE)


def fill(target: str, text: str, tab: str | None = None) -> dict[str, Any]:
    """Set input/textarea/contenteditable text exactly and verify the
    final value (opencli `fill` — added v1.0.5+). Use when you want the
    value replaced wholesale rather than appended."""
    args = ["fill", target, text]
    if tab:
        args += ["--tab", tab]
    return _run(args, workspace=WORKSPACE)


def keys(key: str, tab: str | None = None) -> dict[str, Any]:
    """Press a single keyboard key (e.g. ``Enter``, ``Escape``,
    ``cmd+v``)."""
    args = ["keys", key]
    if tab:
        args += ["--tab", tab]
    return _run(args, workspace=WORKSPACE)


def wait(kind: str, value: str | None = None, tab: str | None = None) -> dict[str, Any]:
    args = ["wait", kind]
    if value is not None:
        args.append(value)
    if tab:
        args += ["--tab", tab]
    return _run(args, workspace=WORKSPACE)


def evaluate(js: str, tab: str | None = None) -> dict[str, Any]:
    args = ["eval", js]
    if tab:
        args += ["--tab", tab]
    return _run(args, workspace=WORKSPACE)


def stage_text_payload(
    payload: str,
    *,
    prefix: str = "meti",
    chunk_chars: int = 180_000,
    tab: str | None = None,
) -> str:
    """Stage a large text payload in the browser page via small eval chunks.

    OpenCLI eval arguments go through argv/npm; multi-megabyte base64 blobs can
    hit OS argv limits or crash Node's argument handling. This helper sends the
    payload in bounded chunks, stores it under ``window.__METI_CHUNK_PAYLOADS``,
    and returns the page-side key for a later short eval to consume.
    """
    if chunk_chars <= 0:
        raise ValueError("chunk_chars must be positive")
    key = f"{prefix}-{uuid.uuid4().hex}"
    key_json = json.dumps(key)
    evaluate(
        f"(() => {{ window.__METI_CHUNK_PAYLOADS = window.__METI_CHUNK_PAYLOADS || {{}}; "
        f"window.__METI_CHUNK_PAYLOADS[{key_json}] = []; return JSON.stringify({{ok:true,key:{key_json}}}); }})()",
        tab=tab,
    )
    for offset in range(0, len(payload), chunk_chars):
        chunk = payload[offset : offset + chunk_chars]
        chunk_json = json.dumps(chunk)
        evaluate(
            f"(() => {{ const store = window.__METI_CHUNK_PAYLOADS || (window.__METI_CHUNK_PAYLOADS = {{}}); "
            f"(store[{key_json}] || (store[{key_json}] = [])).push({chunk_json}); "
            f"return JSON.stringify({{ok:true,key:{key_json},chunks:store[{key_json}].length}}); }})()",
            tab=tab,
        )
    return key


def screenshot(path: str, tab: str | None = None) -> dict[str, Any]:
    args = ["screenshot", path]
    if tab:
        args += ["--tab", tab]
    return _run(args, workspace=WORKSPACE)


def find(selector: str, tab: str | None = None) -> dict[str, Any]:
    args = ["find", "--selector", selector]
    if tab:
        args += ["--tab", tab]
    return _run(args, workspace=WORKSPACE)


def is_connected() -> bool:
    """True iff opencli + extension are actually responsive.

    This must be a real check. Older code used check=False around
    `tab list`, which turned Node/OpenCLI crashes into false positives.
    """
    try:
        result = doctor()
    except BrowserNotInstalledError:
        return False
    if not result.get("ok"):
        return False
    try:
        _run(["tab", "list"], workspace=None, check=True, timeout=30)
        return True
    except BrowserCommandError:
        return False
    except BrowserNotConnectedError:
        return False
