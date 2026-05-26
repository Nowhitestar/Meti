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


# Compose URL. ``/compose/post`` opens the same modal as the home-feed
# composer but from a stable URL we can navigate to directly.
COMPOSE_POST_URL = "https://x.com/compose/post"

# Per-tweet textarea. <n> is the 0-based tweet index in the thread.
# Scoped to the compose modal — bare `[data-testid="tweetTextarea_0"]`
# matches the home-feed inline composer too, raising selector_ambiguous.
TEXTAREA_TEMPLATE = '[role="dialog"] [data-testid="tweetTextarea_{n}"]'

# "Add another tweet" button. Sits under the *last* composer; clicking
# it appends a new tweet textarea and bumps the index.
# Scoped to the compose modal for the same reason as TEXTAREA_TEMPLATE —
# the home-feed inline composer also exposes an addButton, and opencli
# click silently picks the first match.
ADD_BUTTON_CANDIDATES = [
    '[role="dialog"] [data-testid="addButton"]',
    '[role="dialog"] button[aria-label="Add post"]',
    '[role="dialog"] button[aria-label="添加帖子"]',
]

# After the modal opens, X redirects login-less sessions here.
LOGIN_PATH_FRAGMENTS = ("/i/flow/login", "/login")

PAGE_LOAD_WAIT_S = 3.0
POST_CLICK_WAIT_S = 1.5
# X's compose modal lazy-renders the "Add post" button after the first
# textarea has non-empty content — 0.8s isn't enough on slower DOMs to
# let React commit and reveal addButton. 2.5s gives it room.
TYPE_SETTLE_WAIT_S = 2.5


def _redact_url(url: str) -> str:
    if not url:
        return url
    for marker in ("?", "#"):
        if marker in url:
            return url.split(marker, 1)[0] + marker + "…"
    return url


def _preflight_browser() -> None:
    from core import browser as br

    diag = br.diagnose(platform_url=COMPOSE_POST_URL)
    if not diag.ready:
        raise BrowserFlowError(
            diag.message,
            error_code=diag.code,
            error_kind="browser_readiness",
            recoverable=diag.recoverable,
            manual_recovery="; ".join(diag.next_actions),
            details={"browser_diagnostic": diag.to_dict()},
        )


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

    _preflight_browser()

    # 1. Open a dedicated tab for the thread compose. Each browser-flow
    # provider gets its own tab so concurrent runs don't trample.
    tab = br.tab_new(COMPOSE_POST_URL)
    time.sleep(PAGE_LOAD_WAIT_S)

    current_url = br.get_url(tab=tab)
    if any(frag in current_url for frag in LOGIN_PATH_FRAGMENTS):
        raise BrowserFlowError(
            "X redirected to login. Your Chrome's X session is logged out. "
            "Log in to X in Chrome, then retry. "
            f"Current URL: {_redact_url(current_url)}",
            error_code="platform_login_required",
            error_kind="browser_readiness",
            manual_recovery="Log in to X in Chrome, then run `meti resume <run-dir>`.",
            details={"current_url": _redact_url(current_url)},
        )

    # 2. Type tweet #1 into the first textarea via OpenCLI `type`
    # (native CDP keyboard) — the only insertion path that reliably
    # commits to X's Draft.js editor state. `fill` (wholesale set +
    # verify) reports verified but the Draft.js state stays empty,
    # which means addButton never lazy-renders and the thread can't
    # advance. See post.js in @jackwener/opencli for the same finding.
    first_sel = TEXTAREA_TEMPLATE.format(n=0)
    try:
        br.type_text(first_sel, tweets[0], tab=tab)
    except Exception as e:
        raise BrowserFlowError(
            f"x compose/post: first tweet textarea not found ({first_sel!r}). "
            f"X may have changed the testid scheme. Update TEXTAREA_TEMPLATE in "
            f"{__file__}. Original: {e}",
            error_code="selector_drift",
            error_kind="recoverable",
            manual_recovery="Inspect the X compose modal and update TEXTAREA_TEMPLATE.",
            details={"selector": first_sel, "last_error": str(e)},
        ) from e
    time.sleep(TYPE_SETTLE_WAIT_S)

    # 3. For each subsequent tweet: a11y-activate the *last* "+" button
    # then type into the new textarea.
    #
    # Why a11y instead of click: X's "Add post" button rejects
    # programmatic clicks (both opencli `click` and JS `element.click()`
    # trip an anti-automation guard that resets the composer). Focusing
    # the button and pressing Enter is the keyboard-accessibility path
    # — X has to honor it, otherwise screen-reader users couldn't
    # compose threads. We always target the *last* addButton because
    # each spawn appends a new one below the freshest textarea.
    focus_last_add_js = (
        "(() => {"
        " const btns = document.querySelectorAll("
        "  '[role=\"dialog\"] [data-testid=\"addButton\"]'"
        " );"
        " const btn = btns[btns.length - 1];"
        " if (!btn) return JSON.stringify({ok: false, reason: 'no_add_button'});"
        " btn.focus();"
        " return JSON.stringify({ok: document.activeElement === btn});"
        "})()"
    )

    for idx in range(1, len(tweets)):
        focus_result = br.evaluate(focus_last_add_js, tab=tab)
        # OpenCLI `eval` returns the JSON string in `result`; check for failure.
        focus_payload = (focus_result or {}).get("result", "")
        if "no_add_button" in str(focus_payload):
            raise BrowserFlowError(
                f"x compose/post: 'Add post' button not found before tweet #{idx + 1}. "
                f"X may have lazy-rendered it elsewhere or you're not in thread mode. "
                f"Update focus_last_add_js in {__file__}.",
                error_code="thread_add_button_missing",
                error_kind="review_needed",
                manual_recovery="Inspect the open X compose modal. If tweet #1 is present, continue the thread manually; otherwise retry after rebinding.",
                details={"tweet_index": idx, "focus_result": str(focus_payload)},
            )
        try:
            br.keys("Enter", tab=tab)
        except Exception as e:
            raise BrowserFlowError(
                f"x compose/post: Enter on focused addButton failed before tweet #{idx + 1}. "
                f"Original: {e}",
                error_code="thread_add_button_activation_failed",
                error_kind="review_needed",
                manual_recovery="Inspect the open X compose modal. Continue the thread manually if the previous tweets are visible.",
                details={"tweet_index": idx, "last_error": str(e)},
            ) from e
        time.sleep(POST_CLICK_WAIT_S)

        next_sel = TEXTAREA_TEMPLATE.format(n=idx)
        try:
            br.type_text(next_sel, tweets[idx], tab=tab)
        except Exception as e:
            raise BrowserFlowError(
                f"x compose/post: tweet #{idx + 1} textarea not found ({next_sel!r}). "
                f"Focus+Enter on addButton may not have spawned a new composer. "
                f"Original: {e}",
                error_code="partial_thread_needs_review",
                error_kind="review_needed",
                manual_recovery="Inspect the open X compose modal. Some tweets may already be filled; continue manually or retry after rebinding.",
                details={"tweet_index": idx, "selector": next_sel, "last_error": str(e)},
            ) from e
        time.sleep(TYPE_SETTLE_WAIT_S)

    # 4. Leave the modal open. The user clicks "Post all" themselves.
    final_url = br.get_url(tab=tab)
    return {
        "draft_url": final_url,
        "external_id": None,
        "review_needed": True,
        "manual_recovery": "Review the open X compose modal and click Post all yourself when ready.",
    }


# Kept as a small surface for tests — the URL pattern check is one of
# the few things we can unit-test without mocking the entire bridge.
_LOGIN_RE = re.compile("|".join(re.escape(f) for f in LOGIN_PATH_FRAGMENTS))


def _is_login_redirect(url: str) -> bool:
    return bool(_LOGIN_RE.search(url or ""))
