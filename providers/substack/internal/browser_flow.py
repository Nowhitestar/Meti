"""Substack post browser flow (OpenCLI-backed).

Drives the user's real Chrome (via OpenCLI Browser Bridge) to:
1. Navigate to ``<publication>.substack.com/publish/post`` — Substack
   auto-allocates a draft and routes to ``/publish/post/<draft-id>``
2. Type title into ``[data-testid="post-title"]``
3. (Optional) Type subtitle into ``[placeholder="Add a subtitle…"]``
4. Type body into ``[data-testid="editor"]`` (contenteditable)
5. Substack auto-saves on type — when we leave, the draft is persisted

The draft ID lives in the URL after step 1; that's what we return as
``external_id``.

Publication URL
---------------
Each Substack writer has a unique publication subdomain (e.g.
``lewisxbt.substack.com``). The provider gets this from the manifest
target's ``options.publication_url`` field, OR falls back to the env
var ``SUBSTACK_PUBLICATION_URL``.

If neither is set, we error early with a clear message — there's no
universal `substack.com/publish/post` URL that works for arbitrary
users (it redirects to "Discover Substack Newsletters" if you don't
own a publication).

Caveats
-------
- Requires the user to own a Substack publication (free is fine).
- If the user is logged in to Substack but doesn't own the
  publication URL provided, Substack will redirect or 404; we surface
  that as a `RuntimeError` with the actual URL we landed on.
- Selectors target Substack's English UI; subtitle placeholder
  uses `…` (Unicode ellipsis) not `...`.
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

# URL pattern after Substack auto-allocates a draft.
EDIT_URL_PATTERN = re.compile(r"/publish/post/(\d+)")

# Selectors. Constants for easy patching when Substack changes UI.
TITLE_SELECTOR = '[data-testid="post-title"]'
SUBTITLE_SELECTOR_CANDIDATES = [
    'input[placeholder="Add a subtitle…"]',
    'input[placeholder="Add a subtitle..."]',  # fallback if Substack flattens ellipsis
]
BODY_SELECTOR = '[data-testid="editor"]'

PAGE_LOAD_WAIT_S = 4.0
AUTOSAVE_WAIT_S = 4.0


def _publish_url(publication_url: str) -> str:
    """Build the post-create URL from a publication base URL."""
    base = publication_url.rstrip("/")
    return f"{base}/publish/post"


def _redact_url(url: str) -> str:
    if not url:
        return url
    for marker in ("?", "#"):
        if marker in url:
            return url.split(marker, 1)[0] + marker + "…"
    return url


def _preflight_browser(publication_url: str) -> None:
    from core import browser as br

    diag = br.diagnose(platform_url=_publish_url(publication_url))
    if not diag.ready:
        raise BrowserFlowError(
            diag.message,
            error_code=diag.code,
            error_kind="browser_readiness",
            recoverable=diag.recoverable,
            manual_recovery="; ".join(diag.next_actions),
            details={"browser_diagnostic": diag.to_dict()},
        )


def create_draft(
    payload: dict[str, Any],
    publication_url: str,
) -> dict[str, Any]:
    """Save a Substack post as a draft on the user's publication.

    Opens a fresh tab in meti's bound Chrome workspace, drives that tab
    only, and leaves it open at the editor URL when done. Substack auto-
    saves while we type; we do NOT click any Publish button — the user
    reviews and ships from their own browser.

    Returns ``{"draft_url": <url>, "external_id": <draft-id>}``.

    Args:
        payload: dict with ``title``, ``subtitle`` (optional), ``body``
        publication_url: e.g. ``https://lewisxbt.substack.com``

    Raises:
        BrowserNotConnectedError / BrowserNotBoundError / BrowserNotInstalledError
        RuntimeError: selector failures, login redirect, missing publication
    """
    from core import browser as br

    title = str(payload.get("title", "")).strip()
    subtitle = str(payload.get("subtitle") or payload.get("summary") or "").strip()
    body = str(payload.get("body", "")).strip()
    if not body:
        raise ValueError("payload.body is required")
    if not publication_url:
        raise ValueError(
            "publication_url is required (the user's Substack base URL, "
            "e.g. https://lewisxbt.substack.com). Provide via "
            "manifest target options.publication_url or "
            "SUBSTACK_PUBLICATION_URL env var."
        )

    _preflight_browser(publication_url)

    # 1. Navigate the bound tab to Substack's post composer. Substack
    # auto-allocates a draft and routes us to /publish/post/<id>.
    br.open_url(_publish_url(publication_url))
    time.sleep(PAGE_LOAD_WAIT_S)

    edit_url = br.get_url()
    if "/sign-in" in edit_url or "/sign-up" in edit_url:
        raise BrowserFlowError(
            "Substack redirected to sign-in. Your Chrome's Substack "
            "session is logged out. Log in to Substack in Chrome, "
            f"then retry. Current URL: {_redact_url(edit_url)}",
            error_code="platform_login_required",
            error_kind="browser_readiness",
            manual_recovery="Log in to Substack in Chrome, then run `meti resume <run-dir>`.",
            details={"current_url": _redact_url(edit_url)},
        )

    m = EDIT_URL_PATTERN.search(edit_url)
    draft_id: str | None = None
    if m:
        draft_id = m.group(1)
    else:
        # Substack hadn't allocated a draft yet — give it one more chance.
        time.sleep(PAGE_LOAD_WAIT_S)
        edit_url = br.get_url()
        m = EDIT_URL_PATTERN.search(edit_url)
        if m:
            draft_id = m.group(1)
        else:
            raise BrowserFlowError(
                f"Substack didn't route to /publish/post/<id>. "
                f"Current URL: {_redact_url(edit_url)!r}. Possible causes: not the owner "
                f"of {publication_url}, publication doesn't exist, or "
                f"Substack changed the create flow.",
                error_code="draft_url_missing",
                error_kind="review_needed",
                manual_recovery="Inspect the current Substack tab. If a post editor is open, copy its draft URL; otherwise verify publication_url and retry.",
                details={"current_url": _redact_url(edit_url), "publication_url": publication_url},
            )

    # 2. Type title.
    if title:
        try:
            br.type_text(TITLE_SELECTOR, title)
        except Exception as e:
            raise BrowserFlowError(
                f"substack: title field not found ({TITLE_SELECTOR!r}). "
                f"Update TITLE_SELECTOR in {__file__}. Original: {e}",
                error_code="selector_drift",
                error_kind="recoverable",
                manual_recovery="Inspect the Substack editor and update TITLE_SELECTOR.",
                details={"selector": TITLE_SELECTOR, "last_error": str(e)},
            ) from e

    # 3. Type subtitle (if provided).
    if subtitle:
        for sel in SUBTITLE_SELECTOR_CANDIDATES:
            try:
                br.type_text(sel, subtitle)
                break
            except Exception:
                # Subtitle is optional — try next candidate; if all fail
                # we silently skip (Substack works without subtitle).
                continue

    # 4. Type body.
    try:
        br.type_text(BODY_SELECTOR, body)
    except Exception as e:
        raise BrowserFlowError(
            f"substack: body editor not found ({BODY_SELECTOR!r}). "
            f"Update BODY_SELECTOR in {__file__}. Original: {e}",
            error_code="selector_drift",
            error_kind="recoverable",
            manual_recovery="Inspect the Substack editor and update BODY_SELECTOR.",
            details={"selector": BODY_SELECTOR, "last_error": str(e)},
        ) from e

    # 5. Let autosave land. We don't click any Publish button — user
    # reviews + clicks "Publish" themselves.
    time.sleep(AUTOSAVE_WAIT_S)

    final_url = br.get_url()
    final_match = EDIT_URL_PATTERN.search(final_url)
    if not final_match:
        raise BrowserFlowError(
            "Substack autosave did not leave a durable draft/editor URL.",
            error_code="autosave_timeout_needs_review",
            error_kind="review_needed",
            manual_recovery="Inspect the current Substack editor tab; if the draft exists, copy its URL, otherwise retry after rebinding.",
            details={"current_url": _redact_url(final_url)},
        )

    return {"draft_url": final_url, "external_id": final_match.group(1) or draft_id}
