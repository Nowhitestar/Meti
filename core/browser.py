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

This module wraps ``opencli browser`` subcommands as a Python class so
mmp providers can drive automation without caring about the underlying
backend. The OpenCLI binary is invoked via ``npx`` so users don't need
a separate global install.

Setup
-----
1. Install Node.js >= 21
2. Install the Chrome extension:
   https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk
3. Verify with ``mmp browser status``

State / sessions
----------------
Unlike the previous Playwright design, mmp does NOT store any browser
state. Login state lives in the user's own Chrome profile, exactly as
they would expect. ``mmp browser login`` is therefore a no-op pointer
to the provider's actual login URL — open it in Chrome, log in
normally, mmp can drive Chrome for you afterward.

Error model
-----------
- ``BrowserNotInstalledError`` (MMPError): OpenCLI not on PATH and npx
  fetch failed. Install Node.js + retry, or install opencli globally.
- ``BrowserNotConnectedError`` (MMPError): OpenCLI is callable but
  reports the Browser Bridge extension is not connected (extension not
  installed / disabled / Chrome not running).
- ``BrowserCommandError`` (MMPError): an opencli command exited
  non-zero with stderr that didn't match a known pattern.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from core.errors import MMPError

# OpenCLI npm package used at v0.3.1 release. Pinning lets us evolve the
# backend without breaking users; bump in tandem with provider updates.
_OPENCLI_PKG = "@jackwener/opencli"


class BrowserNotInstalledError(MMPError):
    """OpenCLI binary not callable. Install Node.js >= 21 and retry."""


class BrowserNotConnectedError(MMPError):
    """OpenCLI reports the Chrome extension is not connected."""


class BrowserCommandError(MMPError):
    """An opencli browser subcommand failed unexpectedly."""


def _opencli_argv() -> list[str]:
    """Return the argv prefix that invokes opencli.

    Prefer a globally-installed ``opencli`` binary; fall back to ``npx``
    against the pinned package. ``npx`` adds ~3-4s to first call (cache
    warm-up) but works without a global install.
    """
    if shutil.which("opencli"):
        return ["opencli"]
    if shutil.which("npx"):
        return ["npx", "-y", _OPENCLI_PKG]
    raise BrowserNotInstalledError(
        "neither `opencli` nor `npx` is on PATH. Install Node.js >= 21:\n"
        "  brew install node          # macOS\n"
        "  apt install nodejs npm     # ubuntu\n"
        "Then mmp will use `npx @jackwener/opencli ...` automatically."
    )


def _run(args: list[str], *, check: bool = True, timeout: float = 120.0) -> dict[str, Any]:
    """Invoke ``opencli browser <args>`` and return parsed JSON output.

    OpenCLI commands emit JSON envelopes on stdout when they succeed.
    Diagnostic / status messages go to stderr. We surface stderr in
    raised errors so callers see what went wrong.
    """
    argv = _opencli_argv() + ["browser"] + args
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as e:  # pragma: no cover
        raise BrowserNotInstalledError(str(e)) from e

    stderr = (proc.stderr or "").strip()
    stdout = (proc.stdout or "").strip()

    if proc.returncode != 0:
        if "extension not connected" in stderr.lower():
            raise BrowserNotConnectedError(
                "OpenCLI Browser Bridge extension is not connected.\n"
                "1. Install: https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk\n"
                "2. Make sure Chrome is open and the extension is enabled\n"
                "3. Try: `npx @jackwener/opencli doctor`"
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
        # Some commands (state, extract) emit non-JSON; return as text.
        return {"_raw": stdout}


# ---------------------------------------------------------------------------
# Public API — primitive wrappers
# ---------------------------------------------------------------------------


def doctor() -> dict[str, Any]:
    """Run ``opencli doctor`` and return its diagnostic output.

    Useful when ``mmp browser status`` is called: surfaces extension
    connectivity, daemon status, Chrome detection, etc.
    """
    argv = _opencli_argv() + ["doctor"]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    return {
        "ok": proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def state(tab: str | None = None) -> dict[str, Any]:
    """Return current page URL, title, and interactive-element refs.

    NOTE: opencli's ``browser state`` emits text (not JSON), so the
    returned dict will be ``{"_raw": "<text>"}``. For structured access,
    prefer ``get_url()`` and ``get_title()`` below.
    """
    args = ["state"]
    if tab:
        args += ["--tab", tab]
    return _run(args)


def get_url(tab: str | None = None) -> str:
    """Return the plain URL of the active automation tab."""
    args = ["get", "url"]
    if tab:
        args += ["--tab", tab]
    raw = _run(args)
    # `browser get url` returns the URL on stdout; _run wraps non-JSON
    # output as {"_raw": "..."}. Strip whitespace.
    if "_raw" in raw:
        return str(raw["_raw"]).strip()
    if "value" in raw:
        return str(raw["value"]).strip()
    return ""


def get_title(tab: str | None = None) -> str:
    """Return the page title."""
    args = ["get", "title"]
    if tab:
        args += ["--tab", tab]
    raw = _run(args)
    if "_raw" in raw:
        return str(raw["_raw"]).strip()
    if "value" in raw:
        return str(raw["value"]).strip()
    return ""


def open_url(url: str) -> dict[str, Any]:
    """Open ``url`` in the automation window. Returns the tab target id."""
    return _run(["open", url])


def click(target: str, tab: str | None = None) -> dict[str, Any]:
    """Click element by numeric ref or CSS selector."""
    args = ["click", target]
    if tab:
        args += ["--tab", tab]
    return _run(args)


def type_text(target: str, text: str, tab: str | None = None) -> dict[str, Any]:
    """Click ``target`` and type ``text`` into it."""
    args = ["type", target, text]
    if tab:
        args += ["--tab", tab]
    return _run(args)


def wait(kind: str, value: str | None = None, tab: str | None = None) -> dict[str, Any]:
    """Wait for a condition. ``kind`` is selector/text/time/xhr."""
    args = ["wait", kind]
    if value is not None:
        args.append(value)
    if tab:
        args += ["--tab", tab]
    return _run(args)


def evaluate(js: str, tab: str | None = None) -> dict[str, Any]:
    """Run JS in page context, return result envelope."""
    args = ["eval", js]
    if tab:
        args += ["--tab", tab]
    return _run(args)


def screenshot(path: str, tab: str | None = None) -> dict[str, Any]:
    """Capture a screenshot to ``path``."""
    args = ["screenshot", path]
    if tab:
        args += ["--tab", tab]
    return _run(args)


def find(selector: str, tab: str | None = None) -> dict[str, Any]:
    """Find DOM elements matching CSS ``selector``."""
    args = ["find", "--selector", selector]
    if tab:
        args += ["--tab", tab]
    return _run(args)


def is_connected() -> bool:
    """Quick health check — True iff opencli + extension are responsive."""
    try:
        state()
        return True
    except (BrowserNotInstalledError, BrowserNotConnectedError):
        return False
    except BrowserCommandError:
        return False
