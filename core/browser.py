"""Browser session manager backed by Playwright (optional dependency).

Used by providers that need real browser automation (x-article, substack).
Install with::

    pip install -e ".[browser]"
    playwright install chromium

Without Playwright installed, any caller gets a ``BrowserNotInstalledError``
with install instructions. The rest of mmp keeps working — only providers
that explicitly opt into browser flows are affected.

Session state (cookies + localStorage) for each provider is persisted at
``~/.config/mmp/browser-state/<provider>.json`` (chmod 600). The state
file is treated as sensitive: don't commit it, don't share it.

The contract this module exposes:

- ``state_path(provider)`` / ``state_exists(provider)`` — check whether
  a saved login exists
- ``browser_context(provider, headless=True, require_state=True)`` —
  context manager yielding a logged-in BrowserContext
- ``login_interactive(provider, login_url, ready_indicator=None)`` —
  headed flow, user logs in once, state is saved
- ``save_state(ctx, provider)`` — persist a BrowserContext's storage

Error model: every public function may raise ``BrowserNotInstalledError``
(playwright not installed) or ``BrowserStateMissingError`` (no saved
login for that provider yet). Both are subclasses of ``MMPError``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core import host
from core.errors import MMPError

if TYPE_CHECKING:  # pragma: no cover
    from playwright.sync_api import BrowserContext


class BrowserNotInstalledError(MMPError):
    """Playwright is not importable. Most likely user hasn't installed
    the optional ``browser`` extra and/or hasn't run
    ``playwright install chromium``."""


class BrowserStateMissingError(MMPError):
    """No saved login state for the requested provider. User should run
    ``mmp browser login <provider>`` first."""


def _state_dir() -> Path:
    return host.user_data_dir() / "browser-state"


def state_path(provider: str) -> Path:
    return _state_dir() / f"{provider}.json"


def state_exists(provider: str) -> bool:
    return state_path(provider).exists()


def _import_playwright() -> Any:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:  # pragma: no cover
        raise BrowserNotInstalledError(
            "playwright is not installed. To enable browser-based providers:\n"
            '  pip install -e ".[browser]"\n'
            "  playwright install chromium"
        ) from e
    return sync_playwright


@contextmanager
def browser_context(
    provider: str,
    *,
    headless: bool = True,
    require_state: bool = True,
    user_agent: str | None = None,
) -> Iterator[BrowserContext]:
    """Open a Chromium ``BrowserContext`` for ``provider``.

    Loads saved storage state if present. If ``require_state`` is True
    and no state exists, raises ``BrowserStateMissingError`` with a hint.

    Yields the BrowserContext. The browser process is closed on exit
    even if the caller raises.
    """
    # Fail-fast on missing state before paying the playwright import cost.
    state_p = state_path(provider)
    if require_state and not state_p.exists():
        raise BrowserStateMissingError(
            f"no saved browser state for {provider!r} at {state_p}.\n"
            f"Run `mmp browser login {provider}` once to capture a session."
        )

    sp = _import_playwright()
    with sp() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            ctx_kwargs: dict[str, Any] = {}
            if state_p.exists():
                ctx_kwargs["storage_state"] = str(state_p)
            if user_agent:
                ctx_kwargs["user_agent"] = user_agent
            ctx = browser.new_context(**ctx_kwargs)
            try:
                yield ctx
            finally:
                ctx.close()
        finally:
            browser.close()


def save_state(ctx: BrowserContext, provider: str) -> Path:
    """Persist ``ctx``'s cookies and localStorage for later headless use.

    Chmod 600. Caller is responsible for not sharing the file.
    """
    p = state_path(provider)
    p.parent.mkdir(parents=True, exist_ok=True)
    ctx.storage_state(path=str(p))
    os.chmod(p, 0o600)
    return p


def login_interactive(
    provider: str,
    login_url: str,
    confirmation_prompt: str | None = None,
) -> Path:
    """Open a headed browser at ``login_url`` so the user can log in.

    After the user logs in, they press Enter on the CLI to confirm,
    and we persist storage state. Returns the path the state was saved to.

    ``confirmation_prompt`` overrides the default prompt — useful when a
    provider needs the user to do something extra (e.g. accept a TOS).

    Raises ``BrowserNotInstalledError`` if Playwright isn't available.
    """
    sp = _import_playwright()
    with sp() as p:
        browser = p.chromium.launch(headless=False)
        try:
            ctx = browser.new_context()
            page = ctx.new_page()
            page.goto(login_url)
            print()
            print(f"[mmp browser login] Opened {login_url} in a browser.")
            print(
                "Log in normally. When you're on a logged-in page (the home "
                "feed, dashboard, etc), come back here and press Enter."
            )
            prompt = confirmation_prompt or "> Press Enter when logged in: "
            input(prompt)
            saved = save_state(ctx, provider)
            ctx.close()
        finally:
            browser.close()
    print(f"\n✓ Saved browser state for {provider!r} to {saved}")
    return saved


def delete_state(provider: str) -> bool:
    """Remove saved state for ``provider``. Returns True if removed."""
    p = state_path(provider)
    if p.exists():
        p.unlink()
        return True
    return False
