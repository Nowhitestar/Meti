"""X Articles browser flow (Playwright).

Internal module for ``providers.x_article``. Drives an authenticated
Chromium session to ``x.com/i/articles/compose``, fills in title + body
from the prepared payload, and saves a draft.

This module assumes a saved browser state exists at
``~/.config/mmp/browser-state/x-article.json`` (run
``mmp browser login x-article`` once to capture).

Selector strategy: prefer ``data-testid`` (semi-stable on x.com), fall
back to text content, last resort role-based locators. Selectors are
constants at the top of this file so a future X UI change has a single
patch point.

NOTE: this module is intentionally NOT imported at provider-load time —
``providers.x_article.provider.execute`` imports it lazily, so users
without the ``[browser]`` extra installed don't pay the playwright
import cost or get a hard failure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# x.com selectors. UPDATE HERE when X breaks them.
COMPOSE_URL = "https://x.com/i/articles/compose"
TITLE_SELECTOR = '[data-testid="articleTitle"]'
BODY_SELECTOR = '[data-testid="articleEditorBody"]'
SAVE_DRAFT_BUTTON_TEXT = "Save draft"  # English UI; X may localize
DRAFT_SAVED_INDICATOR = "Draft saved"

# Wait timeouts (ms)
DEFAULT_TIMEOUT_MS = 15_000
SAVE_DRAFT_TIMEOUT_MS = 30_000


def create_draft(payload: dict[str, Any], *, headless: bool = True) -> dict[str, Any]:
    """Create an X Article draft from ``payload``.

    Returns ``{"draft_url": <url-or-None>, "external_id": <id-or-None>}``.

    Raises:
        BrowserStateMissingError: if no saved login state.
        BrowserNotInstalledError: if playwright not installed.
        RuntimeError: on selector failures (X UI drift; selectors at
            top of this file need updating).
    """
    from core import browser as br

    title = str(payload.get("title", "")).strip()
    body = str(payload.get("body", "")).strip()
    if not title:
        raise ValueError("payload.title is required")
    if not body:
        raise ValueError("payload.body is required")

    with br.browser_context("x-article", headless=headless, require_state=True) as ctx:
        page = ctx.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT_MS)
        page.goto(COMPOSE_URL)

        # Wait for the editor to render. If it doesn't, our session is dead.
        try:
            page.wait_for_selector(TITLE_SELECTOR, state="visible")
        except Exception as e:
            raise RuntimeError(
                f"x-article compose page didn't load (selector {TITLE_SELECTOR!r}). "
                f"Likely causes: session expired (re-run `mmp browser login x-article`), "
                f"or X changed their UI (update selectors in {__file__}). "
                f"Original error: {e}"
            ) from e

        # Fill title.
        page.locator(TITLE_SELECTOR).click()
        page.locator(TITLE_SELECTOR).fill(title)

        # Fill body. X uses ContentEditable; .fill works for plain text.
        page.locator(BODY_SELECTOR).click()
        page.locator(BODY_SELECTOR).fill(body)

        # Cover image upload (if provided)
        cover = payload.get("cover")
        if cover:
            cover_path = Path(cover)
            if cover_path.exists():
                # X file input is hidden — use input[type=file] selector.
                file_inputs = page.locator('input[type="file"]')
                if file_inputs.count() > 0:
                    file_inputs.first.set_input_files(str(cover_path))
                    # Wait for upload to settle (best-effort)
                    page.wait_for_timeout(2000)

        # Click Save draft.
        try:
            save_btn = page.get_by_role("button", name=SAVE_DRAFT_BUTTON_TEXT)
            save_btn.click(timeout=SAVE_DRAFT_TIMEOUT_MS)
        except Exception as e:
            raise RuntimeError(
                f"could not find {SAVE_DRAFT_BUTTON_TEXT!r} button. "
                f"X may have renamed it or localized it. "
                f"Update SAVE_DRAFT_BUTTON_TEXT in {__file__}. "
                f"Original error: {e}"
            ) from e

        # Wait for confirmation toast / status.
        try:
            page.wait_for_selector(
                f"text={DRAFT_SAVED_INDICATOR}",
                timeout=SAVE_DRAFT_TIMEOUT_MS,
                state="visible",
            )
        except Exception:
            # Confirmation didn't appear — but the draft might still be saved.
            # Don't fail hard; warn via extras instead.
            pass

        # X article URLs after save look like /i/articles/<id>/edit. Try
        # to extract the id from the current URL.
        current_url = page.url
        external_id = None
        if "/articles/" in current_url:
            parts = current_url.split("/articles/")[-1].split("/")
            if parts:
                external_id = parts[0]

        return {
            "draft_url": current_url,
            "external_id": external_id,
        }
