"""X Articles browser flow (OpenCLI-backed).

Drives the user's real Chrome (via OpenCLI Browser Bridge) to:
1. Navigate to ``x.com/compose/articles`` (drafts list)
2. Click "Write" / "撰写" → X allocates a new draft and routes to
   ``x.com/compose/articles/edit/<draft-id>``
3. Type the title into the article title textarea
4. Type the body into the article composer
5. X auto-saves on type — when we leave, the draft is persisted

The draft ID lives in the URL after step 2; that's what we return as
``external_id``.

Caveats
-------
- X Articles requires Premium / Premium+. Free users get redirected.
  The provider's stub fallback covers the not-Premium case.
- This connector targets X's **Chinese UI** (Lewis's account) — title
  selector uses ``placeholder="添加标题"``. For English UI, the
  placeholder is ``"Add a title"``. We try multiple candidates.
- X does NOT have a separate "Save Draft" button on the article
  composer — autosave fires while you type. We sleep briefly after
  typing to let autosave land.

Selector strategy
-----------------
Selectors are constants at the top. When X drifts UI, this file is the
single patch point.
"""

from __future__ import annotations

import re
import time
from typing import Any


class BrowserFlowError(RuntimeError):
    """Structured provider-local browser-flow failure."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        error_kind: str = "browser_flow",
        recoverable: bool = True,
        manual_recovery: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.error_code = error_code
        self.error_kind = error_kind
        self.recoverable = recoverable
        self.manual_recovery = manual_recovery
        self.details = details or {}
        super().__init__(message)


# X Articles entry URLs.
COMPOSE_ARTICLES_URL = "https://x.com/compose/articles"
EDIT_URL_PATTERN = re.compile(r"/compose/articles/edit/(\d+)")

# Drafts list "Write a new article" button. The empty-state shape is
# what Lewis currently sees; for users with existing drafts there may
# be a different create button. Add fallbacks as discovered.
WRITE_BUTTON_CANDIDATES = [
    '[data-testid="empty_state_button_text"]',
    'button[aria-label="create"]',
]

# Article editor fields. Title is a `<textarea>`, body is a
# contenteditable div.
TITLE_SELECTOR_CANDIDATES = [
    'textarea[placeholder="添加标题"]',
    'textarea[placeholder="Add a title"]',
    'textarea[name="文章标题"]',
    'textarea[name="Article title"]',
]
BODY_SELECTOR = '[data-testid="composer"]'

PAGE_LOAD_WAIT_S = 3.0
POST_CLICK_WAIT_S = 3.0
AUTOSAVE_WAIT_S = 4.0


def _redact_url(url: str) -> str:
    if not url:
        return url
    for marker in ("?", "#"):
        if marker in url:
            return url.split(marker, 1)[0] + marker + "…"
    return url


def _preflight_browser() -> None:
    from core import browser as br

    diag = br.diagnose(platform_url=COMPOSE_ARTICLES_URL)
    if not diag.ready:
        raise BrowserFlowError(
            diag.message,
            error_code=diag.code,
            error_kind="browser_readiness",
            recoverable=diag.recoverable,
            manual_recovery="; ".join(diag.next_actions),
            details={"browser_diagnostic": diag.to_dict()},
        )


def _wait_for_draft_url() -> tuple[str, str]:
    from core import browser as br

    last_url = ""
    for _ in range(3):
        last_url = br.get_url()
        m = EDIT_URL_PATTERN.search(last_url)
        if m:
            return last_url, m.group(1)
        time.sleep(POST_CLICK_WAIT_S)
    raise BrowserFlowError(
        "x compose/articles: clicked Write but URL didn't move to /edit/<id>.",
        error_code="autosave_timeout_needs_review",
        error_kind="review_needed",
        recoverable=True,
        manual_recovery="Inspect the current X Articles editor tab. If a draft is open, copy its URL, otherwise retry after rebinding with `meti browser bind`.",
        details={"current_url": _redact_url(last_url)},
    )


def _try_click_first_match(candidates: list[str]) -> tuple[str | None, Exception | None]:
    """Try each selector in order; return (clicked_selector, last_error)."""
    from core import browser as br

    last_err: Exception | None = None
    for sel in candidates:
        try:
            br.click(sel)
            return sel, None
        except Exception as e:
            last_err = e
    return None, last_err


def _try_type_first_match(candidates: list[str], text: str) -> tuple[str | None, Exception | None]:
    """Try each selector in order to type text; return (used_selector, last_error)."""
    from core import browser as br

    last_err: Exception | None = None
    for sel in candidates:
        try:
            br.type_text(sel, text)
            return sel, None
        except Exception as e:
            last_err = e
    return None, last_err


def create_draft(payload: dict[str, Any]) -> dict[str, Any]:
    """Save an X Article as a draft on the user's account.

    Opens a fresh tab in meti's bound Chrome workspace, drives that tab
    only, and leaves it open at the editor URL when done. X auto-saves
    while we type, so no explicit save click is needed; the draft is
    persistent on the platform once we've typed in it.

    Returns ``{"draft_url": <url>, "external_id": <draft-id>}``
    where ``draft-id`` is the numeric ID X assigns to the article in its URL.

    Raises:
        BrowserNotConnectedError / BrowserNotBoundError / BrowserNotInstalledError:
            bridge issues — caller should fall back / surface to user.
        RuntimeError: selector failures, login redirect, etc.
    """
    from core import browser as br

    title = str(payload.get("title", "")).strip()
    body = str(payload.get("body", "")).strip()
    if not body:
        raise ValueError("payload.body is required")

    # 0. Validate OpenCLI/Chrome/bound workspace state before writing into
    # any potentially stale bound:meti tab.
    _preflight_browser()

    # 1. Navigate the bound tab to X compose. Sequential single-tab
    # design — meti drives one tab through each provider in turn.
    br.open_url(COMPOSE_ARTICLES_URL)
    time.sleep(PAGE_LOAD_WAIT_S)

    current_url = br.get_url()
    if "i/flow/login" in current_url:
        raise BrowserFlowError(
            "X redirected to login. Your Chrome's X session is logged out. "
            "Log in to X in Chrome, then retry. "
            f"Current URL: {_redact_url(current_url)}",
            error_code="platform_login_required",
            error_kind="browser_readiness",
            manual_recovery="Log in to X in Chrome, then run `meti resume <run-dir>`.",
            details={"current_url": _redact_url(current_url)},
        )
    if "subscribe" in current_url.lower() or "premium" in current_url.lower():
        raise BrowserFlowError(
            "X Articles appears gated by Premium or account capability.",
            error_code="capability_gated",
            error_kind="capability_gating",
            recoverable=False,
            manual_recovery="Confirm the account has X Premium/Articles access, or remove the x-article target.",
            details={"current_url": _redact_url(current_url)},
        )

    # 2. Click "Write" button. With existing drafts the button looks
    # different; we fall back through known shapes.
    clicked_sel, err = _try_click_first_match(WRITE_BUTTON_CANDIDATES)
    if clicked_sel is None:
        raise BrowserFlowError(
            "x compose/articles: 'Write new' button not found. "
            f"Tried selectors: {WRITE_BUTTON_CANDIDATES}. "
            f"Update WRITE_BUTTON_CANDIDATES in {__file__}. "
            f"Last error: {err}",
            error_code="selector_drift",
            error_kind="recoverable",
            manual_recovery="Inspect the X Articles compose page and update WRITE_BUTTON_CANDIDATES.",
            details={"selectors": WRITE_BUTTON_CANDIDATES, "last_error": str(err)},
        )

    time.sleep(POST_CLICK_WAIT_S)

    # 3. Capture draft ID from URL.
    edit_url, draft_id = _wait_for_draft_url()

    # 4. Type title (if provided).
    if title:
        used_sel, err = _try_type_first_match(TITLE_SELECTOR_CANDIDATES, title)
        if used_sel is None:
            raise BrowserFlowError(
                "x compose/articles: title field not found. "
                f"Tried selectors: {TITLE_SELECTOR_CANDIDATES}. "
                f"Update TITLE_SELECTOR_CANDIDATES in {__file__}. "
                f"Last error: {err}",
                error_code="selector_drift",
                error_kind="recoverable",
                manual_recovery="Inspect the X Articles editor and update TITLE_SELECTOR_CANDIDATES.",
                details={"selectors": TITLE_SELECTOR_CANDIDATES, "last_error": str(err)},
            )

    # 5. Type body.
    try:
        br.type_text(BODY_SELECTOR, body)
    except Exception as e:
        raise BrowserFlowError(
            f"x compose/articles: body composer not found ({BODY_SELECTOR!r}). "
            f"Update selector in {__file__}. Original: {e}",
            error_code="selector_drift",
            error_kind="recoverable",
            manual_recovery="Inspect the X Articles editor and update BODY_SELECTOR.",
            details={"selector": BODY_SELECTOR, "last_error": str(e)},
        ) from e

    # 6. Let autosave land. We don't click any "Save Draft" button —
    # the user reviews + clicks "Publish" themselves in their browser.
    time.sleep(AUTOSAVE_WAIT_S)

    # Re-read after the autosave window so durable evidence reflects the final
    # editor location and stale-tab issues surface before success.
    final_url = br.get_url()
    final_match = EDIT_URL_PATTERN.search(final_url)
    if not final_match:
        raise BrowserFlowError(
            "X Articles autosave did not leave a durable draft/editor URL.",
            error_code="autosave_timeout_needs_review",
            error_kind="review_needed",
            manual_recovery="Inspect the current X Articles tab; if the draft exists, copy its editor URL, otherwise retry after rebinding.",
            details={"current_url": _redact_url(final_url)},
        )

    return {"draft_url": final_url, "external_id": final_match.group(1) or draft_id}
