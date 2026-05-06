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

    Returns ``{"draft_url": <url>, "external_id": <draft-id>}`` where
    ``draft-id`` is the numeric ID X assigns to the article in its URL.

    Raises:
        BrowserNotConnectedError / BrowserNotInstalledError: bridge issues
        RuntimeError: selector failures, login redirect, etc.
    """
    from core import browser as br

    title = str(payload.get("title", "")).strip()
    body = str(payload.get("body", "")).strip()
    if not body:
        raise ValueError("payload.body is required")

    # 1. Open drafts list.
    br.open_url(COMPOSE_ARTICLES_URL)
    time.sleep(PAGE_LOAD_WAIT_S)

    current_url = br.get_url()
    if "i/flow/login" in current_url:
        raise RuntimeError(
            "X redirected to login. Your Chrome's X session is logged out. "
            "Log in to X in Chrome, then retry. "
            f"Current URL: {current_url}"
        )

    # 2. Click "Write" button. With existing drafts the button looks
    # different; we fall back through known shapes.
    clicked_sel, err = _try_click_first_match(WRITE_BUTTON_CANDIDATES)
    if clicked_sel is None:
        raise RuntimeError(
            "x compose/articles: 'Write new' button not found. "
            f"Tried selectors: {WRITE_BUTTON_CANDIDATES}. "
            f"Update WRITE_BUTTON_CANDIDATES in {__file__}. "
            f"Last error: {err}"
        )

    time.sleep(POST_CLICK_WAIT_S)

    # 3. Capture draft ID from URL.
    edit_url = br.get_url()
    m = EDIT_URL_PATTERN.search(edit_url)
    draft_id: str | None = None
    if m:
        draft_id = m.group(1)
    else:
        # Editor may have loaded but URL hasn't updated yet — try once more.
        time.sleep(POST_CLICK_WAIT_S)
        edit_url = br.get_url()
        m = EDIT_URL_PATTERN.search(edit_url)
        if m:
            draft_id = m.group(1)
        else:
            raise RuntimeError(
                f"x compose/articles: clicked Write but URL didn't move to "
                f"/edit/<id>. Current URL: {edit_url!r}. "
                f"X may have changed the create flow."
            )

    # 4. Type title (if provided).
    if title:
        used_sel, err = _try_type_first_match(TITLE_SELECTOR_CANDIDATES, title)
        if used_sel is None:
            raise RuntimeError(
                "x compose/articles: title field not found. "
                f"Tried selectors: {TITLE_SELECTOR_CANDIDATES}. "
                f"Update TITLE_SELECTOR_CANDIDATES in {__file__}. "
                f"Last error: {err}"
            )

    # 5. Type body.
    try:
        br.type_text(BODY_SELECTOR, body)
    except Exception as e:
        raise RuntimeError(
            f"x compose/articles: body composer not found ({BODY_SELECTOR!r}). "
            f"Update selector in {__file__}. Original: {e}"
        ) from e

    # 6. Let autosave land.
    time.sleep(AUTOSAVE_WAIT_S)

    return {
        "draft_url": edit_url,
        "external_id": draft_id,
    }
