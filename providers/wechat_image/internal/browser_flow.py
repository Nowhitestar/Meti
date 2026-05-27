"""WeChat MP 贴图 (image post, ``type=77``) browser flow (OpenCLI-backed).

Drives the user's real Chrome (via OpenCLI Browser Bridge) to create a
"贴图" draft on ``mp.weixin.qq.com``. The 贴图 post type is web-only —
the public Open Platform API exposes only the article (图文) draft type
which the ``wechat-article`` provider already covers.

High-level flow
---------------
1. Hit ``mp.weixin.qq.com`` → MP redirects to ``cgi-bin/home`` and
   appends the session ``token`` to the URL. We extract the token.
2. Navigate to the 贴图 editor:
   ``cgi-bin/appmsg?action=add&type=77&token=<TOKEN>&lang=zh_CN``
   MP allocates a fresh ``appmsgid`` and rewrites the URL.
3. For each image in the payload: read the bytes, base64-encode, ship
   into page context via ``eval``, reconstruct as a ``Blob``/``File``,
   inject via ``DataTransfer`` into the editor's ``<input type=file>``,
   dispatch a ``change`` event. MP's webuploader then POSTs the file
   to ``cgi-bin/filetransfer`` and inserts the resulting CDN URL.
4. Type the title into ``textarea.js_article_title`` (real keyboard,
   so React dirty state catches up).
5. Type the caption into the body ProseMirror.
6. Click the editor's "保存为草稿" button. MP's own save logic runs
   end-to-end (which is the whole point — the page handles
   ``fingerprint`` generation, the ``req`` JSON blob construction,
   collaboration locks, etc.).
7. Read the resulting ``appmsgid`` from the URL.

Why DOM-driven and not a direct API POST
-----------------------------------------
The save endpoint (``operate_appmsg?sub=update&type=77``) takes a
``fingerprint`` form field that's a 32-char MD5 generated inside MP's
seajs modules — not exposed to plain ``$.ajax`` callers. Reverse-
engineering the generator is brittle. Driving the editor's own save
button avoids the problem entirely. See
``docs/wechat-image-tietu-research.md`` for full reverse-engineering
notes and endpoint shapes.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import time
from pathlib import Path
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


# ---------------------------------------------------------------------------
# Constants — patch points when MP drifts UI / URL shape.
# ---------------------------------------------------------------------------

MP_HOME_URL = "https://mp.weixin.qq.com/"

# MP rewrites the URL on auth-redirect to include `token=<session>`.
TOKEN_RE = re.compile(r"[?&]token=(\d+)")

# MP rewrites the URL once a fresh draft has been allocated.
APPMSGID_RE = re.compile(r"[?&]appmsgid=(\d+)")

# Fresh-draft creation URL for 贴图. Confirmed empirically by clicking
# "新的创作 → 贴图" in MP's Creator UI: MP routes to ``appmsg_edit_v2``
# with ``type=10&createType=8&isNew=1``. (Note: ``type=77`` only
# indexes the 贴图 list view; draft creation uses ``type=10``
# disambiguated by ``createType=8``.) MP allocates the appmsgid on the
# first save and rewrites the URL.
EDITOR_URL_TPL = (
    "https://mp.weixin.qq.com/cgi-bin/appmsg"
    "?t=media/appmsg_edit_v2&action=edit&isNew=1&type=10&createType=8"
    "&token={token}&lang=zh_CN"
)

# Selectors. Constants for easy patching when MP changes UI.
TITLE_SELECTOR = "textarea.js_article_title"
SAVE_BUTTON_TEXT = "保存为草稿"

# Waits — MP's editor loads progressively, and webuploader is async.
PAGE_LOAD_WAIT_S = 2.0
UPLOAD_WAIT_S = 10.0  # XHR timeout budget; per-image post-upload settle is shorter
SAVE_WAIT_S = 5.0


# ---------------------------------------------------------------------------
# JS snippets injected via opencli `browser eval`.
# ---------------------------------------------------------------------------

# Probe used right after page load to confirm the editor is interactive.
_JS_EDITOR_READY = """(() => {
  const t = document.querySelector('textarea.js_article_title');
  const fileInputs = document.querySelectorAll('input[type=file]');
  return JSON.stringify({
    ready: !!t,
    titleVisible: !!(t && t.offsetParent),
    fileInputsCount: fileInputs.length,
    url: location.href,
    appmsgid: (window.wx && wx.cgiData && wx.cgiData.app_id) || null,
  });
})()"""

# Extract the appmsgid the page knows about. Used after save lands.
_JS_GET_APPMSGID = """(() => {
  const fromGlobal = (window.wx && wx.cgiData && wx.cgiData.app_id) || null;
  return JSON.stringify({appmsgid: fromGlobal, url: location.href});
})()"""

# Focus the WeChat 贴图 "description" ProseMirror. MP currently renders
# several ProseMirror instances: image body, description (placeholder:
# "填写描述信息，让大家了解更多内容"), and sometimes a full article body
# placeholder ("从这里开始写正文"). For 贴图 posts the publishable caption is
# the description editor, not the generic body editor.
_JS_FOCUS_BODY = """(() => {
  const editors = Array.from(document.querySelectorAll('.ProseMirror'));
  const visible = editors.filter(e => e.offsetParent);
  const textOf = e => (e.innerText || e.textContent || '').trim();
  const attrOf = e => [
    e.getAttribute('data-placeholder') || '',
    e.getAttribute('placeholder') || '',
    e.getAttribute('aria-label') || '',
  ].join(' ');
  let body = visible.find(e => {
    const s = (textOf(e) + ' ' + attrOf(e));
    return s.includes('填写描述信息') || s.includes('了解更多内容');
  });
  if (!body) {
    body = visible.find(e => {
      const s = (textOf(e) + ' ' + attrOf(e));
      return !s.includes('标题') && !s.includes('从这里开始写正文');
    }) || visible[visible.length - 1];
  }
  if (!body) return JSON.stringify({focused: false, count: visible.length});
  body.focus();
  const sel = window.getSelection();
  const range = document.createRange();
  range.selectNodeContents(body);
  range.collapse(false);
  sel.removeAllRanges();
  sel.addRange(range);
  return JSON.stringify({focused: true, currentText: (body.innerText || '').slice(0, 80), count: visible.length});
})()"""

# Click the "保存为草稿" button by text-match. Returns whether it
# was found+clicked.
_JS_CLICK_SAVE = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find(
    b => (b.textContent || '').trim() === '保存为草稿'
  );
  if (!btn) return JSON.stringify({clicked: false, reason: 'button not found'});
  if (btn.disabled) return JSON.stringify({clicked: false, reason: 'button disabled'});
  btn.click();
  return JSON.stringify({clicked: true});
})()"""


def _js_inject_image(b64_data: str, filename: str, mime: str) -> str:
    """Build the JS snippet that injects a base64-encoded image into MP's
    image ``<input type=file>`` and triggers webuploader.

    The snippet returns once webuploader's POST to /cgi-bin/filetransfer
    completes (success or failure), so the Python side can wait
    deterministically.
    """
    payload = {"b64": b64_data, "name": filename, "mime": mime}
    return _JS_INJECT_IMAGE_TPL.replace("__PAYLOAD__", json.dumps(payload))


# ProseMirror image upload: MP's 贴图 editor doesn't have a visible
# `<input type=file>` per se — webuploader wraps it inside a hidden
# div. We probe for ANY file-accepting input and use the first one that
# accepts images. This mirrors what clicking "+" in the UI would
# trigger.
_JS_INJECT_IMAGE_TPL = """(async () => {
  const payload = __PAYLOAD__;
  // Decode base64 to bytes
  const raw = atob(payload.b64);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  const blob = new Blob([bytes], {type: payload.mime});
  const file = new File([blob], payload.name, {type: payload.mime});

  // Pick the right file input. The 贴图 editor contains multiple
  // hidden `<input type=file>` elements: one is leftover from the
  // "新的创作" dropdown menu (parent class `tpl_dropdown_menu_item`
  // — for the regular article cover picker), the other belongs to
  // 贴图's own webuploader. Skip the dropdown leftover.
  const allInputs = Array.from(document.querySelectorAll('input[type=file]'));
  const imageInputs = allInputs.filter(i => (i.accept || '').includes('image'));
  const target = imageInputs.find(i => {
    let p = i.parentElement;
    while (p && p !== document.body) {
      const c = (p.className || '').toString();
      if (c.includes('tpl_dropdown_menu_item') || c.includes('weui-desktop-dropdown')) return false;
      p = p.parentElement;
    }
    return true;
  }) || imageInputs[imageInputs.length - 1] || allInputs[0];
  if (!target) return JSON.stringify({ok: false, error: 'no file input found'});

  // Hook the upload XHR before triggering, so we can deterministically
  // know when the upload completes.
  const uploadDone = new Promise((resolve) => {
    const origOpen = XMLHttpRequest.prototype.open;
    const origSend = XMLHttpRequest.prototype.send;
    let myXhr = null;
    XMLHttpRequest.prototype.open = function(method, url) {
      this.__mmpUrl = url;
      return origOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function() {
      if (this.__mmpUrl && this.__mmpUrl.includes('filetransfer') && this.__mmpUrl.includes('upload_material')) {
        myXhr = this;
        const orig = this.onreadystatechange;
        this.onreadystatechange = function() {
          if (this.readyState === 4) {
            try {
              XMLHttpRequest.prototype.open = origOpen;
              XMLHttpRequest.prototype.send = origSend;
              const r = JSON.parse(this.responseText);
              resolve({status: this.status, body: r});
            } catch(e) {
              resolve({status: this.status, body: null, parseError: String(e)});
            }
          }
          if (orig) try { orig.apply(this, arguments); } catch(e){}
        };
      }
      return origSend.apply(this, arguments);
    };
    // Failsafe: time out after 30s.
    setTimeout(() => resolve({timeout: true}), 30000);
  });

  // Inject file via DataTransfer.
  try {
    const dt = new DataTransfer();
    dt.items.add(file);
    target.files = dt.files;
  } catch (e) {
    return JSON.stringify({ok: false, error: 'DataTransfer failed: ' + String(e)});
  }
  target.dispatchEvent(new Event('change', {bubbles: true}));

  const result = await uploadDone;
  return JSON.stringify({ok: !result.timeout && result.status === 200, result});
})()"""


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------


def create_draft(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a 贴图 draft on the user's WeChat OA.

    Opens a fresh tab in meti's bound Chrome workspace, drives that tab
    only, and clicks 保存为草稿 (per-platform: this DOES persist the
    draft server-side, which is fine and useful — WeChat MP drafts sync
    cross-device, so user gets it on phone too).

    Returns ``{"draft_url": <url>, "external_id": <appmsgid>}``.

    Args:
        payload: dict with ``title``, ``caption`` (or ``body``),
                 ``images`` (list of absolute paths)

    Raises:
        BrowserNotConnectedError / BrowserNotBoundError / BrowserNotInstalledError
        RuntimeError: selector failures, login redirect, upload failures
        ValueError: missing required payload fields
    """
    from core import browser as br

    title = str(payload.get("title", "")).strip()
    caption = str(payload.get("caption") or payload.get("body") or "").strip()
    images = [str(p) for p in (payload.get("images") or [])]

    if not images:
        raise ValueError("payload.images must contain at least one image path")
    if len(images) > 9:
        raise ValueError(f"贴图 supports up to 9 images, got {len(images)}")

    # 1. Navigate the bound tab to MP root to discover the session
    # token. Sequential single-tab design.
    br.open_url(MP_HOME_URL)
    time.sleep(PAGE_LOAD_WAIT_S)
    home_url = br.get_url()
    if "/sign" in home_url or "login" in home_url.lower():
        raise RuntimeError(
            "MP redirected to sign-in. Your Chrome's MP session is logged out. "
            "Log in to mp.weixin.qq.com in Chrome, then retry. "
            f"Current URL: {home_url}"
        )
    m = TOKEN_RE.search(home_url)
    if not m:
        raise RuntimeError(
            "could not find `token=...` in MP home URL — login may have "
            f"failed or MP changed routing. URL: {home_url}"
        )
    token = m.group(1)

    # 2. Navigate same tab to 贴图 editor (action=add allocates a fresh draft).
    editor_url = EDITOR_URL_TPL.format(token=token)
    br.open_url(editor_url)
    time.sleep(PAGE_LOAD_WAIT_S)

    ready_raw = br.evaluate(_JS_EDITOR_READY)
    ready = _parse_eval(ready_raw)
    if not ready.get("ready"):
        raise BrowserFlowError(
            f"贴图 editor failed to load (no `{TITLE_SELECTOR}` found). "
            f"State: {ready}. MP may have drifted UI; update selectors in "
            f"{__file__}.",
            error_code="selector_drift",
            error_kind="recoverable",
            manual_recovery="Inspect the current MP editor tab and update TITLE_SELECTOR / editor probes.",
            details={"probe": ready},
        )
    if int(ready.get("fileInputsCount") or 0) <= 0:
        raise BrowserFlowError(
            "贴图 editor loaded but no upload input was found.",
            error_code="upload_selector_missing",
            error_kind="recoverable",
            manual_recovery="Inspect the current MP editor tab and update the file input selector logic.",
            details={"probe": ready},
        )

    appmsgid = ready.get("appmsgid")

    # 3. Upload images in one browser-side selection. The payload is staged in
    # chunks first, so we avoid OpenCLI/npm argv limits while preserving the
    # fast multi-file DataTransfer path.
    _upload_images_batch(images)

    # 4. Set title via execCommand('insertText') for React dirty-state.
    if title:
        title_raw = br.evaluate(_js_set_title(title))
        title_res = _parse_eval(title_raw)
        if not title_res.get("ok"):
            raise RuntimeError(
                f"贴图: failed to set title via {TITLE_SELECTOR!r}: "
                f"{title_res.get('reason', title_res)}"
            )

    # 5. Type caption (if any). Body is a ProseMirror; focus it via JS,
    # then dispatch insertText.
    if caption:
        focus_raw = br.evaluate(_JS_FOCUS_BODY)
        focus = _parse_eval(focus_raw)
        if not focus.get("focused"):
            raise RuntimeError(
                "贴图: could not focus body editor (.ProseMirror). "
                f"Editor count: {focus.get('count')}. Update _JS_FOCUS_BODY "
                f"in {__file__}."
            )
        try:
            br.evaluate(_js_dispatch_text(caption))
        except Exception as e:
            raise RuntimeError(f"贴图: could not insert caption into body editor: {e}") from e

    # 6. Click "保存为草稿". This persists the draft server-side so it
    # syncs to user's other devices. We do NOT click "发表" / Publish —
    # the user reviews + ships from their own browser.
    save_raw = br.evaluate(_JS_CLICK_SAVE)
    save = _parse_eval(save_raw)
    if not save.get("clicked"):
        raise RuntimeError(
            f"贴图: failed to click '{SAVE_BUTTON_TEXT}' button: {save.get('reason', 'unknown')}"
        )
    try:
        _wait_for_js_condition(
            _JS_SAVE_SETTLED,
            timeout_s=SAVE_WAIT_S,
            interval_s=0.25,
        )
    except RuntimeError as exc:
        # MP sometimes leaves permanent elements with `loading` in their class
        # names, or otherwise misses our transient-settled probe, even after it
        # has saved and allocated an appmsgid. Treat a post-save appmsgid as
        # sufficient evidence and verify below via URL/global extraction.
        current_url = br.get_url()
        if not (_extract_appmsgid(current_url) or appmsgid):
            raise BrowserFlowError(
                "贴图 save timed out before durable draft evidence appeared.",
                error_code="save_timeout_needs_review",
                error_kind="review_needed",
                recoverable=True,
                manual_recovery="Inspect the current MP editor tab; if the draft saved, resume after confirming it appears in drafts.",
                details={"url": _redact_url(current_url)},
            ) from exc

    # 7. Re-extract appmsgid (MP rewrites URL on save success).
    final_url = br.get_url()
    final_id = _extract_appmsgid(final_url) or appmsgid
    if not final_id:
        latest_raw = br.evaluate(_JS_GET_APPMSGID)
        latest = _parse_eval(latest_raw)
        final_id = latest.get("appmsgid")
        final_url = latest.get("url", final_url)
    if not final_id:
        raise RuntimeError(
            f"贴图 save did not produce an appmsgid; URL: {final_url}. "
            "Save may have failed silently — check the editor in Chrome."
        )

    return {"draft_url": final_url, "external_id": str(final_id)}


# ---------------------------------------------------------------------------
# Internal helpers.
# ---------------------------------------------------------------------------


def _parse_eval(envelope: dict[str, Any]) -> dict[str, Any]:
    """Normalize the dict that ``core.browser.evaluate`` returns.

    ``core.browser._run`` returns either:

    - The parsed JSON object directly (if opencli's stdout was valid
      JSON, which is what our ``JSON.stringify(...)`` JS produces) — in
      this case the dict already has the JS-side fields like ``ready``,
      ``ok``, etc.
    - ``{"_raw": "<text>"}`` if stdout wasn't JSON-parseable. We try
      to parse the raw text as JSON ourselves; if that also fails,
      return the original envelope.

    Critically: do NOT unwrap legitimate top-level keys like ``result``
    or ``value`` — those are real JS return values, not envelope keys.
    """
    if not envelope:
        return {}
    raw = envelope.get("_raw")
    if raw is None and isinstance(envelope.get("data"), str):
        raw = envelope.get("data")
    if isinstance(raw, str):
        try:
            return json.loads(raw)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            return envelope
    return envelope


def _extract_appmsgid(url: str) -> str | None:
    m = APPMSGID_RE.search(url or "")
    return m.group(1) if m else None


def _redact_url(url: str) -> str:
    if not url:
        return url
    for marker in ("?", "#"):
        if marker in url:
            return url.split(marker, 1)[0] + marker + "…"
    return url


def _upload_one_image(image_path: str, idx: int) -> None:
    """Inject a single image and wait for MP to upload + acknowledge."""
    from core import browser as br

    p = Path(image_path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"image not found: {image_path}")

    mime, _ = mimetypes.guess_type(str(p))
    mime = mime or "image/jpeg"
    if not mime.startswith("image/"):
        raise ValueError(f"not an image (mime={mime!r}): {image_path}")

    # 30 MB hard cap mirrors MP's own UI behavior.
    size = p.stat().st_size
    if size > 30 * 1024 * 1024:
        raise ValueError(
            f"image #{idx} ({p.name}) is {size / 1024 / 1024:.1f}MB; MP rejects > 30MB"
        )

    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    js = _js_inject_image(b64, p.name, mime)
    raw = br.evaluate(js)
    parsed = _parse_eval(raw)
    if not parsed.get("ok"):
        result = parsed.get("result") or {}
        body = result.get("body") or {}
        err = body.get("base_resp", {}).get("err_msg") or result.get("parseError")
        raise RuntimeError(f"贴图 image upload #{idx} ({p.name}) failed: {err or parsed}")
    # The JS injection already waits for MP's upload XHR. Keep only a short
    # paint-settle delay; the old 5s fixed wait made 9-card runs ~45s slower.
    time.sleep(0.5)


def _upload_images_batch(image_paths: list[str]) -> None:
    """Inject all images at once and wait for MP to acknowledge/render them."""
    from core import browser as br

    files: list[dict[str, str]] = []
    url_base = os.environ.get("METI_IMAGE_BASE_URL", "").rstrip("/")
    for idx, image_path in enumerate(image_paths):
        p = Path(image_path).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"image not found: {image_path}")
        mime, _ = mimetypes.guess_type(str(p))
        mime = mime or "image/jpeg"
        if not mime.startswith("image/"):
            raise ValueError(f"not an image (mime={mime!r}): {image_path}")
        size = p.stat().st_size
        if size > 30 * 1024 * 1024:
            raise ValueError(
                f"image #{idx} ({p.name}) is {size / 1024 / 1024:.1f}MB; MP rejects > 30MB"
            )
        item = {"name": p.name, "mime": mime}
        if url_base:
            item["url"] = f"{url_base}/{p.name}"
        else:
            item["b64"] = base64.b64encode(p.read_bytes()).decode("ascii")
        files.append(item)

    payload = json.dumps({"files": files})
    payload_key = br.stage_text_payload(payload, prefix="meti-wechat-upload")
    staged = _parse_eval(br.evaluate(_js_staged_payload_ready(payload_key, expected_min_chunks=1)))
    if not staged.get("ok"):
        raise BrowserFlowError(
            f"贴图 chunk staging did not complete before upload: {staged}",
            error_code="chunk_staging_incomplete",
            error_kind="recoverable",
            manual_recovery="Retry the draft run; if it repeats, reduce image count/size or inspect OpenCLI eval output.",
            details={"staged": staged},
        )
    parsed = _parse_eval(br.evaluate(_js_inject_images(payload_key)))
    if not parsed.get("ok"):
        code = "upload_selector_missing" if "no file input" in str(parsed) else "upload_incomplete"
        raise BrowserFlowError(
            f"贴图 batch image upload failed: {parsed}",
            error_code=code,
            error_kind="recoverable",
            manual_recovery="Inspect the current MP editor tab and retry after confirming upload controls are visible.",
            details={"upload": parsed},
        )
    if int(parsed.get("uploaded", 0)) < len(files):
        raise BrowserFlowError(
            f"贴图 batch image upload incomplete: {parsed}",
            error_code="partial_upload_needs_review",
            error_kind="review_needed",
            manual_recovery="Inspect the current MP editor tab; remove partial images or finish uploading manually before saving.",
            details={"upload": parsed},
        )


def _js_set_title(text: str) -> str:
    """JS that sets the 贴图 title textarea via ``execCommand('insertText')``.

    Strategy:
    1. Find ``textarea.js_article_title`` and focus it
    2. Select all existing content (in case of a partial draft)
    3. ``execCommand('insertText', text)`` — fires beforeinput/input
       events that MP's React dirty tracker registers
    4. Verify the textarea's ``value`` matches what we set; fall back
       to a direct ``value`` setter + ``input``/``change`` events if
       execCommand silently no-op'd
    """
    safe = json.dumps(text)
    return f"""(() => {{
      const text = {safe};
      const ta = document.querySelector('textarea.js_article_title');
      if (!ta) return JSON.stringify({{ok: false, reason: 'title textarea not found'}});
      ta.focus();
      ta.setSelectionRange(0, ta.value.length);
      let usedFallback = false;
      try {{ document.execCommand('insertText', false, text); }} catch (e) {{}}
      if (ta.value !== text) {{
        // Fallback for browsers/editors that ignore execCommand.
        const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
        setter.call(ta, text);
        ta.dispatchEvent(new Event('input', {{bubbles: true}}));
        ta.dispatchEvent(new Event('change', {{bubbles: true}}));
        usedFallback = true;
      }}
      return JSON.stringify({{ok: ta.value === text, value: ta.value, fallback: usedFallback}});
    }})()"""


def _js_dispatch_text(text: str) -> str:
    """JS that inserts ``text`` into the currently focused contenteditable.

    Uses ``document.execCommand('insertText')`` which ProseMirror handles
    via its `beforeinput` listener — equivalent to a real paste. Fallback
    path also dispatches an `input` event for editors that ignore
    execCommand.
    """
    safe = json.dumps(text)
    return f"""(() => {{
      const text = {safe};
      const ok = document.execCommand && document.execCommand('insertText', false, text);
      if (ok) return JSON.stringify({{inserted: true, via: 'execCommand'}});
      // Fallback: dispatch beforeinput + input events on the focused element.
      const el = document.activeElement;
      if (!el) return JSON.stringify({{inserted: false, reason: 'no active element'}});
      const evt = new InputEvent('beforeinput', {{
        inputType: 'insertText', data: text, bubbles: true, cancelable: true
      }});
      el.dispatchEvent(evt);
      return JSON.stringify({{inserted: !evt.defaultPrevented, via: 'beforeinput'}});
    }})()"""


def _wait_for_js_condition(
    js: str, *, timeout_s: float = 10.0, interval_s: float = 0.25
) -> dict[str, Any]:
    """Poll a JS probe until it returns ``{"ready": true}``."""
    from core import browser as br

    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] = {}
    while True:
        last = _parse_eval(br.evaluate(js))
        if last.get("ready"):
            return last
        if time.monotonic() >= deadline:
            raise RuntimeError(f"timed out waiting for browser condition: {last}")
        time.sleep(interval_s)


def _js_inject_images(payload_key: str) -> str:
    return _JS_INJECT_IMAGES_TPL.replace("__PAYLOAD_KEY__", json.dumps(payload_key))


def _js_staged_payload_ready(payload_key: str, *, expected_min_chunks: int) -> str:
    return f"""(() => {{
      const key = {json.dumps(payload_key)};
      const chunks = (window.__METI_CHUNK_PAYLOADS || {{}})[key];
      const count = Array.isArray(chunks) ? chunks.length : 0;
      return JSON.stringify({{ok: count >= {int(expected_min_chunks)}, key, chunks: count}});
    }})()"""


_JS_SAVE_SETTLED = r"""(() => {
  const fromGlobal = (window.wx && wx.cgiData && wx.cgiData.app_id) || null;
  const text = document.body ? document.body.innerText : '';
  const busyText = /保存中|上传中|正在保存|loading/i.test(text);
  const hasId = !!fromGlobal || /[?&]appmsgid=\d+/.test(location.href);
  const savedText = /历史版本|手动保存|保存成功/.test(text);
  return JSON.stringify({ready: hasId && (!busyText || savedText), appmsgid: fromGlobal, url: location.href});
})()"""


_JS_INJECT_IMAGES_TPL = """(async () => {
  const payloadKey = __PAYLOAD_KEY__;
  const store = window.__METI_CHUNK_PAYLOADS || {};
  const chunks = store[payloadKey];
  if (!Array.isArray(chunks)) return JSON.stringify({ok: false, error: 'missing staged payload', expected: 0, uploaded: 0});
  let payload;
  try { payload = JSON.parse(chunks.join('')); }
  catch (e) { return JSON.stringify({ok: false, error: 'invalid staged payload: ' + String(e), expected: 0, uploaded: 0}); }
  delete store[payloadKey];
  const files = payload.files || [];
  const expected = files.length;
  if (!expected) return JSON.stringify({ok: false, error: 'no files', expected, uploaded: 0});

  const countBodyImages = () => Array.from(document.querySelectorAll('.ProseMirror img, .js_editor img, img')).length;
  const allInputs = Array.from(document.querySelectorAll('input[type=file]'));
  const imageInputs = allInputs.filter(i => (i.accept || '').includes('image'));
  const target = imageInputs.find(i => {
    let p = i.parentElement;
    while (p && p !== document.body) {
      const c = (p.className || '').toString();
      if (c.includes('tpl_dropdown_menu_item') || c.includes('weui-desktop-dropdown')) return false;
      p = p.parentElement;
    }
    return true;
  }) || imageInputs[imageInputs.length - 1] || allInputs[0];
  if (!target) return JSON.stringify({ok: false, error: 'no file input found', expected, uploaded: 0});

  const before = countBodyImages();
  let completed = 0;
  const uploadDone = new Promise((resolve) => {
    const origOpen = XMLHttpRequest.prototype.open;
    const origSend = XMLHttpRequest.prototype.send;
    const restore = () => { XMLHttpRequest.prototype.open = origOpen; XMLHttpRequest.prototype.send = origSend; };
    XMLHttpRequest.prototype.open = function(method, url) {
      this.__mmpUrl = String(url || '');
      return origOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function() {
      if ((this.__mmpUrl || '').includes('filetransfer') && (this.__mmpUrl || '').includes('upload_material')) {
        const orig = this.onreadystatechange;
        this.onreadystatechange = function() {
          if (this.readyState === 4) {
            try {
              const body = JSON.parse(this.responseText || '{}');
              const err = body.base_resp && body.base_resp.ret;
              if (this.status === 200 && (!err || err === 0)) completed += 1;
            } catch(e) {
              if (this.status === 200) completed += 1;
            }
            if (completed >= expected) { restore(); resolve({completed, via: 'xhr'}); }
          }
          if (orig) try { orig.apply(this, arguments); } catch(e){}
        };
      }
      return origSend.apply(this, arguments);
    };
    const started = Date.now();
    const poll = () => {
      const rendered = Math.max(0, countBodyImages() - before);
      if (rendered >= expected) { restore(); resolve({completed: Math.max(completed, rendered), rendered, via: 'dom'}); return; }
      if (Date.now() - started > 45000) { restore(); resolve({timeout: true, completed, rendered}); return; }
      setTimeout(poll, 300);
    };
    setTimeout(poll, 300);
  });

  try {
    const dt = new DataTransfer();
    for (const item of files) {
      let blob;
      if (item.url) {
        const resp = await fetch(item.url, {cache: 'no-store'});
        if (!resp.ok) throw new Error('fetch failed ' + resp.status + ' ' + item.url);
        blob = await resp.blob();
      } else {
        const raw = atob(item.b64);
        const bytes = new Uint8Array(raw.length);
        for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
        blob = new Blob([bytes], {type: item.mime});
      }
      dt.items.add(new File([blob], item.name, {type: item.mime}));
    }
    target.files = dt.files;
  } catch (e) {
    return JSON.stringify({ok: false, error: 'DataTransfer failed: ' + String(e), expected, uploaded: 0});
  }
  target.dispatchEvent(new Event('change', {bubbles: true}));

  const result = await uploadDone;
  const uploaded = result.completed || result.rendered || 0;
  return JSON.stringify({ok: !result.timeout && uploaded >= expected, uploaded, expected, result});
})()"""
