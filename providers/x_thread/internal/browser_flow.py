"""X Thread browser flow (OpenCLI-backed).

Drives the user's real Chrome (via OpenCLI Browser Bridge) to:
1. Open ``x.com/compose/post`` (the thread-capable composer modal)
2. Type tweet #1 into the first composer textarea
3. For each remaining tweet: click the "Add post" / "+" button, then
   type into the newly-revealed textarea
4. Stop. Leave the modal open at the user's cursor — the user reviews
   the whole thread and clicks **Post all** themselves.

X has no thread *draft* concept (only single-tweet drafts), so the
"draft" we deliver here is "modal pre-filled, awaiting user confirm" —
analogous to x-article's autosave behavior.

Selector strategy
-----------------
Selectors are constants at the top. When X drifts, this is the single
patch point. We keep multiple candidates per role; first match wins.

X's compose modal exposes ``data-testid="tweetTextarea_<n>"`` on each
tweet's textarea where ``<n>`` is the 0-based index. The "Add post"
button below the last tweet has ``data-testid="addButton"`` (verified
across both EN and ZH UIs in 2025-2026). If X drifts these names,
update the constants below.
"""

from __future__ import annotations

import re
import time
from typing import Any

# Compose URL. ``/compose/post`` opens the same modal as the home-feed
# composer but from a stable URL we can navigate to directly.
COMPOSE_POST_URL = "https://x.com/compose/post"

# Per-tweet textarea. <n> is the 0-based tweet index in the thread.
TEXTAREA_TEMPLATE = '[data-testid="tweetTextarea_{n}"]'

# "Add another tweet" button. Sits under the *last* composer; clicking
# it appends a new tweet textarea and bumps the index.
ADD_BUTTON_CANDIDATES = [
    '[data-testid="addButton"]',
    'button[aria-label="Add post"]',
    'button[aria-label="添加帖子"]',
]

# After the modal opens, X redirects login-less sessions here.
LOGIN_PATH_FRAGMENTS = ("/i/flow/login", "/login")

PAGE_LOAD_WAIT_S = 3.0
POST_CLICK_WAIT_S = 1.5
TYPE_SETTLE_WAIT_S = 0.8


def _try_click_first_match(
    candidates: list[str], tab: str | None = None
) -> tuple[str | None, Exception | None]:
    """Try each selector in order; return (clicked_selector, last_error)."""
    from core import browser as br

    last_err: Exception | None = None
    for sel in candidates:
        try:
            br.click(sel, tab=tab)
            return sel, None
        except Exception as e:
            last_err = e
    return None, last_err


def compose_thread(payload: dict[str, Any]) -> dict[str, Any]:
    """Pre-fill an X thread in the user's bound Chrome workspace.

    Opens a fresh tab, navigates to the compose modal, fills each tweet
    in order, and leaves the modal open at the editor for user review.
    Does NOT click "Post all" — the human reviews and ships.

    Returns ``{"draft_url": <url>, "external_id": None}``. X assigns no
    pre-publish identifier for threads (unlike Articles), so external_id
    stays None and the URL is just the compose URL.

    Raises:
        BrowserNotConnectedError / BrowserNotBoundError / BrowserNotInstalledError:
            bridge issues — caller falls back / surfaces to user.
        RuntimeError: selector failures, login redirect, etc.
    """
    from core import browser as br

    tweets = list(payload.get("tweets") or [])
    if not tweets:
        raise ValueError("payload.tweets is empty — nothing to compose")

    # 1. Open a dedicated tab for the thread compose. Each browser-flow
    # provider gets its own tab so concurrent runs don't trample.
    tab = br.tab_new(COMPOSE_POST_URL)
    time.sleep(PAGE_LOAD_WAIT_S)

    current_url = br.get_url(tab=tab)
    if any(frag in current_url for frag in LOGIN_PATH_FRAGMENTS):
        raise RuntimeError(
            "X redirected to login. Your Chrome's X session is logged out. "
            "Log in to X in Chrome, then retry. "
            f"Current URL: {current_url}"
        )

    # 2. Type tweet #1 into the first textarea.
    first_sel = TEXTAREA_TEMPLATE.format(n=0)
    try:
        br.type_text(first_sel, tweets[0], tab=tab)
    except Exception as e:
        raise RuntimeError(
            f"x compose/post: first tweet textarea not found ({first_sel!r}). "
            f"X may have changed the testid scheme. Update TEXTAREA_TEMPLATE in "
            f"{__file__}. Original: {e}"
        ) from e
    time.sleep(TYPE_SETTLE_WAIT_S)

    # 3. For each subsequent tweet: click "+" then type into the new
    # textarea that just appeared.
    for idx in range(1, len(tweets)):
        clicked_sel, err = _try_click_first_match(ADD_BUTTON_CANDIDATES, tab=tab)
        if clicked_sel is None:
            raise RuntimeError(
                f"x compose/post: 'Add post' button not found before tweet #{idx + 1}. "
                f"Tried selectors: {ADD_BUTTON_CANDIDATES}. "
                f"Update ADD_BUTTON_CANDIDATES in {__file__}. "
                f"Last error: {err}"
            )
        time.sleep(POST_CLICK_WAIT_S)

        next_sel = TEXTAREA_TEMPLATE.format(n=idx)
        try:
            br.type_text(next_sel, tweets[idx], tab=tab)
        except Exception as e:
            raise RuntimeError(
                f"x compose/post: tweet #{idx + 1} textarea not found ({next_sel!r}). "
                f"Add button click may not have spawned a new composer. "
                f"Original: {e}"
            ) from e
        time.sleep(TYPE_SETTLE_WAIT_S)

    # 4. Leave the modal open. The user clicks "Post all" themselves.
    final_url = br.get_url(tab=tab)
    return {"draft_url": final_url, "external_id": None}


# Kept as a small surface for tests — the URL pattern check is one of
# the few things we can unit-test without mocking the entire bridge.
_LOGIN_RE = re.compile("|".join(re.escape(f) for f in LOGIN_PATH_FRAGMENTS))


def _is_login_redirect(url: str) -> bool:
    return bool(_LOGIN_RE.search(url or ""))
