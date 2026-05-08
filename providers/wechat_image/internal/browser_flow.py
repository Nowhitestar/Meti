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
import re
import time
from pathlib import Path
from typing import Any

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
PAGE_LOAD_WAIT_S = 5.0
UPLOAD_WAIT_S = 10.0  # per image; MP processes each on the server side
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

# Click the body ProseMirror that's NOT the title's ProseMirror twin and
# NOT a hidden "reprint" editor. We pick the visible one whose
# placeholder is empty (MP uses placeholder for title, blank for body).
_JS_FOCUS_BODY = """(() => {
  const editors = Array.from(document.querySelectorAll('.ProseMirror'));
  const visible = editors.filter(e => e.offsetParent);
  // The body editor is the visible ProseMirror whose data-placeholder
  // is NOT the title placeholder. Title PM has placeholder
  // "请在这里输入标题"; body PM has none.
  const body = visible.find(e => {
    const ph = e.getAttribute('data-placeholder') || e.getAttribute('placeholder') || '';
    return !ph.includes('标题');
  }) || visible[visible.length - 1];
  if (!body) return JSON.stringify({focused: false, count: visible.length});
  body.focus();
  // Move caret to end so `type` keystrokes append rather than prepend.
  const sel = window.getSelection();
  const range = document.createRange();
  range.selectNodeContents(body);
  range.collapse(false);
  sel.removeAllRanges();
  sel.addRange(range);
  return JSON.stringify({focused: true, currentText: (body.innerText || '').slice(0, 60)});
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

    Returns ``{"draft_url": <url>, "external_id": <appmsgid>, "tab_id": <id>}``.

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

    # 1. Open MP root in a fresh tab to discover the session token.
    tab = br.tab_new(MP_HOME_URL)
    time.sleep(PAGE_LOAD_WAIT_S)
    home_url = br.get_url(tab=tab)
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
    br.open_url(editor_url, tab=tab)
    time.sleep(PAGE_LOAD_WAIT_S)

    ready_raw = br.evaluate(_JS_EDITOR_READY, tab=tab)
    ready = _parse_eval(ready_raw)
    if not ready.get("ready"):
        raise RuntimeError(
            f"贴图 editor failed to load (no `{TITLE_SELECTOR}` found). "
            f"State: {ready}. MP may have drifted UI; update selectors in "
            f"{__file__}."
        )

    appmsgid = ready.get("appmsgid")

    # 3. Upload each image in order.
    for idx, image_path in enumerate(images):
        _upload_one_image(image_path, idx, tab=tab)

    # 4. Set title via execCommand('insertText') for React dirty-state.
    if title:
        title_raw = br.evaluate(_js_set_title(title), tab=tab)
        title_res = _parse_eval(title_raw)
        if not title_res.get("ok"):
            raise RuntimeError(
                f"贴图: failed to set title via {TITLE_SELECTOR!r}: "
                f"{title_res.get('reason', title_res)}"
            )

    # 5. Type caption (if any). Body is a ProseMirror; focus it via JS,
    # then dispatch insertText.
    if caption:
        focus_raw = br.evaluate(_JS_FOCUS_BODY, tab=tab)
        focus = _parse_eval(focus_raw)
        if not focus.get("focused"):
            raise RuntimeError(
                "贴图: could not focus body editor (.ProseMirror). "
                f"Editor count: {focus.get('count')}. Update _JS_FOCUS_BODY "
                f"in {__file__}."
            )
        try:
            br.evaluate(_js_dispatch_text(caption), tab=tab)
        except Exception as e:
            raise RuntimeError(f"贴图: could not insert caption into body editor: {e}") from e

    # 6. Click "保存为草稿". This persists the draft server-side so it
    # syncs to user's other devices. We do NOT click "发表" / Publish —
    # the user reviews + ships from their own browser.
    save_raw = br.evaluate(_JS_CLICK_SAVE, tab=tab)
    save = _parse_eval(save_raw)
    if not save.get("clicked"):
        raise RuntimeError(
            f"贴图: failed to click '{SAVE_BUTTON_TEXT}' button: {save.get('reason', 'unknown')}"
        )
    time.sleep(SAVE_WAIT_S)

    # 7. Re-extract appmsgid (MP rewrites URL on save success).
    final_url = br.get_url(tab=tab)
    final_id = _extract_appmsgid(final_url) or appmsgid
    if not final_id:
        latest_raw = br.evaluate(_JS_GET_APPMSGID, tab=tab)
        latest = _parse_eval(latest_raw)
        final_id = latest.get("appmsgid")
        final_url = latest.get("url", final_url)
    if not final_id:
        raise RuntimeError(
            f"贴图 save did not produce an appmsgid; URL: {final_url}. "
            "Save may have failed silently — check the editor in Chrome."
        )

    return {
        "draft_url": final_url,
        "external_id": str(final_id),
        "tab_id": tab,
    }


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
    if isinstance(raw, str):
        try:
            return json.loads(raw)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            return envelope
    return envelope


def _extract_appmsgid(url: str) -> str | None:
    m = APPMSGID_RE.search(url or "")
    return m.group(1) if m else None


def _upload_one_image(image_path: str, idx: int, *, tab: str | None = None) -> None:
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
    raw = br.evaluate(js, tab=tab)
    parsed = _parse_eval(raw)
    if not parsed.get("ok"):
        result = parsed.get("result") or {}
        body = result.get("body") or {}
        err = body.get("base_resp", {}).get("err_msg") or result.get("parseError")
        raise RuntimeError(f"贴图 image upload #{idx} ({p.name}) failed: {err or parsed}")
    # MP needs a moment to paint the uploaded image into the editor;
    # subsequent images can race if we don't pause.
    time.sleep(UPLOAD_WAIT_S * 0.5)


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
