"""Xiaohongshu (creator.xiaohongshu.com) browser flow (OpenCLI-backed).

Drives the user's real Chrome (via OpenCLI Browser Bridge) to create a
图文笔记 draft on the user's XHS Creator account. v0.4.1+ replaces the
older local-JSON ``draft.sh`` path because XHS's draft data is anchored
to the user's browser session — we MUST drive their actual session for
the draft to be reachable later.

High-level flow
---------------
1. Navigate the bound tab to
   ``https://creator.xiaohongshu.com/publish/publish?target=image``
   (direct URL — bypasses tab-switcher click; lands on "上传图文")
2. Inject each local image via ``DataTransfer`` into
   ``input.upload-input[type=file]`` — the same pattern that works
   for wechat-image's 贴图 editor. XHS's webuploader picks up the
   ``change`` event and POSTs to its CDN.
3. Wait for image-upload XHRs to complete (each image surfaces a
   thumbnail in the editor preview).
4. Type the title into the title input.
5. Type the caption (body) into the TipTap ProseMirror.
6. Optionally type ``#tag1 #tag2`` at the end of caption (XHS uses
   inline #hashtags rather than a separate tag field).
7. Click "存草稿" (save draft) — XHS persists drafts to a server-side
   "草稿箱" tied to the user's account, so this is what the user
   actually wants. We do NOT click "发布" / Publish — the user reviews
   and ships from their own browser.
8. Leave the bound tab on the editor URL.

Selectors are constants at the top — single patch point when XHS
drifts UI. Title / caption / save-button selectors are CANDIDATES
lists since the exact attributes often change.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
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
# Constants — patch points when XHS drifts UI.
# ---------------------------------------------------------------------------

# `?target=image` lands on the "上传图文" tab without a tab-click.
EDITOR_URL = "https://creator.xiaohongshu.com/publish/publish?target=image"

# File input for image upload. XHS swaps the input element after the
# first image is selected: the initial `input.upload-input` disappears
# and a different (hidden) input under `.top` takes over for adding
# more images. We probe candidates in order; first match with the right
# accept attribute wins.
FILE_INPUT_SELECTOR_CANDIDATES = [
    "input.upload-input[type=file]",
    'input[type=file][accept*="image"]',
    'input[type=file][accept*="jpg"][multiple]',
    'input[type=file][accept*="jpg"]',
    'input[type=file][accept*="png"]',
    'input[type=file]',
]

# After upload, the editor expands to show title + body + actions.
# Selectors are candidates; the first match wins. Update when XHS drifts.
TITLE_SELECTOR_CANDIDATES = [
    'input[placeholder*="标题"]',
    'textarea[placeholder*="标题"]',
    ".d-input.title",
    ".title-input input",
]
# Body editor is TipTap (.tiptap.ProseMirror) per earlier exploration.
BODY_SELECTOR_CANDIDATES = [
    "div.tiptap.ProseMirror",
    "div.ql-editor",  # in case XHS swaps to Quill
    '[contenteditable="true"][role="textbox"]',
]
# Save-draft button text-match. XHS uses "暂存离开" (lit. "save and
# leave") on the image-post editor; older / other surfaces may use
# "存草稿" or "保存".
SAVE_BUTTON_TEXTS = ["暂存离开", "存草稿", "保存", "Save", "Save Draft"]

PAGE_LOAD_WAIT_S = 2.0
UPLOAD_WAIT_S = 10.0  # XHR timeout budget; per-image post-upload settle is shorter
SAVE_WAIT_S = 4.0


# ---------------------------------------------------------------------------
# JS helpers — same DataTransfer pattern as wechat-image.
# ---------------------------------------------------------------------------

_JS_EDITOR_PROBE = """(() => {
  // Probe ANY file input (visible or not) accepting images.
  const fileInputs = Array.from(document.querySelectorAll('input[type=file]'))
    .filter(i => {
      const a = (i.accept || '').toLowerCase();
      return a.includes('jpg') || a.includes('jpeg') || a.includes('png') || a.includes('webp');
    });
  const tabs = Array.from(document.querySelectorAll('.creator-tab')).map(t => ({
    text: (t.textContent || '').trim(),
    active: t.classList.contains('active'),
  }));
  return JSON.stringify({
    url: location.href,
    fileInputFound: fileInputs.length > 0,
    fileInputCount: fileInputs.length,
    tabActive: tabs.find(t => t.active)?.text || null,
  });
})()"""


def _js_inject_image(b64_data: str, filename: str, mime: str) -> str:
    """Inject one image into XHS's upload-input via DataTransfer.

    Waits for the upload XHR (XHS's CDN endpoint, typically
    ``creator.xiaohongshu.com/api/...`` or ``cf.xiaohongshu.com``) and
    resolves once the response lands.
    """
    payload = {"b64": b64_data, "name": filename, "mime": mime}
    js = _JS_INJECT_IMAGE_TPL.replace("__PAYLOAD__", json.dumps(payload))
    js = js.replace("__CANDIDATES__", json.dumps(FILE_INPUT_SELECTOR_CANDIDATES))
    return js


_JS_INJECT_IMAGE_TPL = """(async () => {
  const payload = __PAYLOAD__;
  const raw = atob(payload.b64);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  const blob = new Blob([bytes], {type: payload.mime});
  const file = new File([blob], payload.name, {type: payload.mime});

  // XHS swaps the file input element after the first upload. Walk the
  // candidate selectors in order; reject inputs whose `accept` only
  // covers PDF/doc (XHS has a hidden `.file-relation-container` input
  // for those) — we want image inputs only.
  const cands = __CANDIDATES__;
  let target = null;
  for (const sel of cands) {
    const els = Array.from(document.querySelectorAll(sel));
    for (const el of els) {
      const accept = (el.accept || '').toLowerCase();
      if (!accept) continue;
      // Heuristic: if accept contains an image extension, accept it.
      if (accept.includes('image') || accept.includes('jpg') || accept.includes('jpeg') || accept.includes('png') || accept.includes('webp')) {
        target = el;
        break;
      }
    }
    if (target) break;
  }
  if (!target) return JSON.stringify({ok: false, error: 'no file input'});

  // Hook upload XHR to know when it lands. XHS CDN endpoints include
  // 'fileserver', 'cdn-api', or 'sns-img'.
  const uploadDone = new Promise((resolve) => {
    const origOpen = XMLHttpRequest.prototype.open;
    const origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function(method, url) {
      this.__mmpUrl = url;
      return origOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function() {
      if (this.__mmpUrl &&
          (this.__mmpUrl.includes('upload') ||
           this.__mmpUrl.includes('cdn') ||
           this.__mmpUrl.includes('fileserver') ||
           this.__mmpUrl.includes('sns-img'))) {
        const orig = this.onreadystatechange;
        this.onreadystatechange = function() {
          if (this.readyState === 4) {
            try {
              XMLHttpRequest.prototype.open = origOpen;
              XMLHttpRequest.prototype.send = origSend;
              resolve({status: this.status, url: this.__mmpUrl});
            } catch (e) {
              resolve({status: 0, error: String(e)});
            }
          }
          if (orig) try { orig.apply(this, arguments); } catch(e){}
        };
      }
      return origSend.apply(this, arguments);
    };
    setTimeout(() => resolve({timeout: true}), 30000);
  });

  try {
    const dt = new DataTransfer();
    dt.items.add(file);
    target.files = dt.files;
  } catch (e) {
    return JSON.stringify({ok: false, error: 'DataTransfer failed: ' + String(e)});
  }
  target.dispatchEvent(new Event('change', {bubbles: true}));

  const result = await uploadDone;
  return JSON.stringify({ok: !result.timeout && (result.status >= 200 && result.status < 300), result});
})()"""


def _js_set_title(text: str) -> str:
    """Set the XHS title via execCommand('insertText'). Try each candidate
    selector — first match wins."""
    safe_text = json.dumps(text)
    safe_cands = json.dumps(TITLE_SELECTOR_CANDIDATES)
    return f"""(() => {{
      const text = {safe_text};
      const cands = {safe_cands};
      let target = null;
      for (const sel of cands) {{
        const el = document.querySelector(sel);
        if (el && el.offsetParent) {{ target = el; break; }}
      }}
      if (!target) return JSON.stringify({{ok: false, reason: 'no title field'}});
      target.focus();
      // Some XHS title fields are <input>; for those `value` setter +
      // input event works. For contenteditable, use insertText.
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {{
        const setter = Object.getOwnPropertyDescriptor(
          target.tagName === 'INPUT'
            ? window.HTMLInputElement.prototype
            : window.HTMLTextAreaElement.prototype,
          'value'
        ).set;
        setter.call(target, text);
        target.dispatchEvent(new Event('input', {{bubbles: true}}));
        target.dispatchEvent(new Event('change', {{bubbles: true}}));
      }} else {{
        document.execCommand('insertText', false, text);
      }}
      return JSON.stringify({{ok: true, value: target.value || target.innerText.slice(0, 40)}});
    }})()"""


def _js_set_body(text: str) -> str:
    """Insert caption text into XHS's body ProseMirror via
    execCommand('insertText'). Tries each candidate selector."""
    safe_text = json.dumps(text)
    safe_cands = json.dumps(BODY_SELECTOR_CANDIDATES)
    return f"""(() => {{
      const text = {safe_text};
      const cands = {safe_cands};
      let target = null;
      for (const sel of cands) {{
        const els = Array.from(document.querySelectorAll(sel)).filter(e => e.offsetParent);
        if (els.length) {{ target = els[els.length - 1]; break; }}
      }}
      if (!target) return JSON.stringify({{ok: false, reason: 'no body editor'}});
      target.focus();
      // Move caret to end so insertText appends.
      const sel = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(target);
      range.collapse(false);
      sel.removeAllRanges();
      sel.addRange(range);
      document.execCommand('insertText', false, text);
      return JSON.stringify({{ok: true, length: target.innerText.length}});
    }})()"""


def _js_click_save() -> str:
    """Find a button whose text is one of SAVE_BUTTON_TEXTS and click it."""
    safe_texts = json.dumps(SAVE_BUTTON_TEXTS)
    return f"""(() => {{
      const texts = {safe_texts};
      const btns = Array.from(document.querySelectorAll('button, [role=button]'));
      const target = btns.find(b => {{
        const t = (b.textContent || '').trim();
        return texts.includes(t);
      }});
      if (!target) return JSON.stringify({{clicked: false, reason: 'no save button found'}});
      if (target.disabled) return JSON.stringify({{clicked: false, reason: 'save button disabled'}});
      target.click();
      return JSON.stringify({{clicked: true, text: target.textContent.trim()}});
    }})()"""


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------


def create_draft(payload: dict[str, Any]) -> dict[str, Any]:
    """Save a 图文笔记 draft on the user's Xiaohongshu Creator account.

    Returns ``{"draft_url": <url>, "external_id": None}`` — XHS doesn't
    surface a draft ID in the URL, so external_id is None. The user
    finds the draft via "草稿箱" in the Creator console.

    Args:
        payload: dict with ``title``, ``caption`` (or ``content``),
                 ``images`` (list of absolute paths), optional ``tags``

    Raises:
        BrowserNotConnectedError / BrowserNotBoundError / BrowserNotInstalledError
        RuntimeError: selector failures, login redirect, upload failures
        ValueError: missing required payload fields
    """
    from core import browser as br

    title = str(payload.get("title", "")).strip()
    caption = str(payload.get("caption") or payload.get("content") or "").strip()
    images = [str(p) for p in (payload.get("images") or [])]
    tags = [str(t).lstrip("#") for t in (payload.get("tags") or []) if t]

    if not images:
        raise ValueError("payload.images must contain at least one image path")
    if len(images) > 18:
        raise ValueError(f"XHS supports up to 18 images per note, got {len(images)}")

    # 1. Navigate the bound tab to the image-upload Creator page.
    br.open_url(EDITOR_URL)
    time.sleep(PAGE_LOAD_WAIT_S)

    # 2. Verify we landed on the editor (not redirected to login).
    cur = br.get_url()
    if "/login" in cur or "/sso" in cur or "passport" in cur:
        raise BrowserFlowError(
            "XHS Creator redirected to login. Log in to creator.xiaohongshu.com in Chrome, then retry.",
            error_code="platform_login_required",
            error_kind="browser_readiness",
            recoverable=True,
            manual_recovery="Log in to creator.xiaohongshu.com in Chrome, then run `meti resume <run-dir>`.",
            details={"current_url": _redact_url(cur)},
        )

    probe_raw = br.evaluate(_JS_EDITOR_PROBE)
    probe = _parse_eval(probe_raw)
    if not probe.get("fileInputFound"):
        raise BrowserFlowError(
            f"XHS editor: no image-accepting `<input type=file>` found. State: {probe}.",
            error_code="upload_selector_missing",
            error_kind="recoverable",
            recoverable=True,
            manual_recovery="Inspect the XHS Creator editor and update FILE_INPUT_SELECTOR_CANDIDATES.",
            details={"probe": probe},
        )

    # 3. Upload images in one browser-side selection. The payload is staged in
    # chunks first, so we avoid OpenCLI/npm argv limits while preserving the
    # fast multi-file DataTransfer path.
    _upload_images_batch(images)

    # 4. Set title.
    if title:
        title_raw = br.evaluate(_js_set_title(title))
        title_res = _parse_eval(title_raw)
        if not title_res.get("ok"):
            raise BrowserFlowError(
                f"XHS: failed to set title (tried selectors {TITLE_SELECTOR_CANDIDATES}): {title_res.get('reason', title_res)}",
                error_code="title_selector_missing",
                error_kind="recoverable",
                manual_recovery="Inspect the XHS title field selectors and retry.",
                details={"title": title_res},
            )

    # 5. Set caption + tags.
    body_text = caption
    if tags:
        # XHS uses inline #tags. Append to caption.
        body_text = (body_text + "\n\n" if body_text else "") + " ".join(f"#{t}" for t in tags)
    if body_text:
        body_raw = br.evaluate(_js_set_body(body_text))
        body_res = _parse_eval(body_raw)
        if not body_res.get("ok"):
            raise BrowserFlowError(
                f"XHS: failed to set caption (tried selectors {BODY_SELECTOR_CANDIDATES}): {body_res.get('reason', body_res)}",
                error_code="body_selector_missing",
                error_kind="recoverable",
                manual_recovery="Inspect the XHS body editor selectors and retry.",
                details={"body": body_res},
            )

    # 6. Click 存草稿 if XHS exposes the button. Current XHS Creator sometimes
    # autosaves image notes after title/body/images are filled and shows no
    # visible save-draft button; in that state the open editor itself is the
    # platform draft.
    save_raw = br.evaluate(_js_click_save())
    save = _parse_eval(save_raw)
    save_clicked = bool(save.get("clicked"))
    if save_clicked:
        _wait_for_js_condition(
            _JS_SAVE_SETTLED,
            timeout_s=SAVE_WAIT_S,
            interval_s=0.25,
        )
    elif save.get("reason") != "no save button found":
        raise BrowserFlowError(
            f"XHS: failed to click save-draft button (tried texts {SAVE_BUTTON_TEXTS}): {save.get('reason', save)}",
            error_code="save_button_unavailable",
            error_kind="recoverable",
            manual_recovery="Inspect the XHS editor; if autosaved, locate the note in drafts, otherwise retry after UI selectors are updated.",
            details={"save": save},
        )

    final_url = br.get_url()

    return {
        "draft_url": final_url,
        "external_id": None,  # XHS doesn't surface a draft id in URL
        "save_clicked": save_clicked,
        "save_state": save,
    }


# ---------------------------------------------------------------------------
# Internal helpers.
# ---------------------------------------------------------------------------


def _parse_eval(envelope: dict[str, Any]) -> dict[str, Any]:
    """Same shape as wechat-image's _parse_eval. opencli `eval` may
    return either a parsed dict directly or ``{"_raw": "<text>"}``."""
    if not envelope:
        return {}
    raw = envelope.get("_raw")
    if raw is None and isinstance(envelope.get("data"), str):
        raw = envelope.get("data")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {"_raw": raw}
        except json.JSONDecodeError:
            return envelope
    return envelope


def _upload_one_image(image_path: str, idx: int) -> None:
    """Inject one image and wait for upload XHR to acknowledge."""
    from core import browser as br

    p = Path(image_path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"image not found: {image_path}")

    mime, _ = mimetypes.guess_type(str(p))
    mime = mime or "image/jpeg"
    if not mime.startswith("image/"):
        raise ValueError(f"not an image (mime={mime!r}): {image_path}")
    # XHS Creator advertises 32 MB max per image.
    size = p.stat().st_size
    if size > 32 * 1024 * 1024:
        raise ValueError(
            f"image #{idx} ({p.name}) is {size / 1024 / 1024:.1f}MB; XHS rejects > 32MB"
        )

    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    js = _js_inject_image(b64, p.name, mime)
    raw = br.evaluate(js)
    parsed = _parse_eval(raw)
    if not parsed.get("ok"):
        raise RuntimeError(
            f"XHS image upload #{idx} ({p.name}) failed: {parsed.get('result', parsed)}"
        )
    # The JS injection already waits for XHS's upload XHR to finish. Keep only
    # a tiny paint-settle delay so the swapped file input/thumbnail DOM catches
    # up before the next file. The old 4s fixed sleep dominated 9-card runs.
    time.sleep(0.4)



def _upload_images_batch(image_paths: list[str]) -> None:
    """Inject all images at once and wait for XHS to acknowledge/render them."""
    from core import browser as br

    files: list[dict[str, str]] = []
    url_base = os.environ.get("METI_XHS_IMAGE_BASE_URL", "").rstrip("/")
    for idx, image_path in enumerate(image_paths):
        p = Path(image_path).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"image not found: {image_path}")
        mime, _ = mimetypes.guess_type(str(p))
        mime = mime or "image/jpeg"
        if not mime.startswith("image/"):
            raise ValueError(f"not an image (mime={mime!r}): {image_path}")
        size = p.stat().st_size
        if size > 32 * 1024 * 1024:
            raise ValueError(
                f"image #{idx} ({p.name}) is {size / 1024 / 1024:.1f}MB; XHS rejects > 32MB"
            )
        item = {"name": p.name, "mime": mime}
        if url_base:
            item["url"] = f"{url_base}/{p.name}"
        else:
            item["b64"] = base64.b64encode(p.read_bytes()).decode("ascii")
        files.append(item)

    payload = json.dumps({"files": files, "candidates": FILE_INPUT_SELECTOR_CANDIDATES})
    payload_key = br.stage_text_payload(payload, prefix="meti-xhs-upload")
    staged = _parse_eval(br.evaluate(_js_staged_payload_ready(payload_key, expected_min_chunks=1)))
    if not staged.get("ok"):
        raise BrowserFlowError(
            f"XHS chunk staging did not complete before upload: {staged}",
            error_code="chunk_staging_incomplete",
            error_kind="recoverable",
            manual_recovery="Retry the draft run; if it repeats, reduce image count/size or inspect OpenCLI eval output.",
            details={"staged": staged},
        )
    parsed = _parse_eval(br.evaluate(_js_inject_images(payload_key)))
    if not parsed.get("ok"):
        code = "upload_selector_missing" if "no file input" in str(parsed) else "upload_incomplete"
        raise BrowserFlowError(
            f"XHS batch image upload failed: {parsed}",
            error_code=code,
            error_kind="recoverable",
            manual_recovery="Inspect the XHS Creator editor and retry after upload controls are visible.",
            details={"upload": parsed},
        )
    if int(parsed.get("uploaded", 0)) < len(files):
        raise BrowserFlowError(
            f"XHS batch image upload incomplete: {parsed}",
            error_code="partial_upload_needs_review",
            error_kind="review_needed",
            manual_recovery="Inspect the current XHS editor tab; remove partial images or finish uploading manually before saving.",
            details={"upload": parsed},
        )



def _wait_for_js_condition(js: str, *, timeout_s: float = 10.0, interval_s: float = 0.25) -> dict[str, Any]:
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


def _redact_url(url: str) -> str:
    if not url:
        return url
    for marker in ("?", "#"):
        if marker in url:
            return url.split(marker, 1)[0] + marker + "…"
    return url


_JS_SAVE_SETTLED = r"""(() => {
  const text = document.body ? document.body.innerText : '';
  const busyText = /保存中|上传中|发布中|正在保存|loading/i.test(text);
  const busyNode = document.querySelector('.loading, .spinner, [class*=loading], [class*=spin]');
  return JSON.stringify({ready: !busyText && !busyNode, busyText, url: location.href});
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
  const cands = payload.candidates || [];
  const expected = files.length;
  if (!expected) return JSON.stringify({ok: false, error: 'no files', expected, uploaded: 0});

  const countImages = () => Array.from(document.querySelectorAll(
    '.upload-item, .image-item, .img-preview, .cover, img'
  )).filter(el => {
    const text = (el.textContent || '').toLowerCase();
    const src = (el.getAttribute && (el.getAttribute('src') || '')) || '';
    return !text.includes('avatar') && !src.includes('avatar');
  }).length;

  let target = null;
  for (const sel of cands) {
    const els = Array.from(document.querySelectorAll(sel));
    for (const el of els) {
      const accept = (el.accept || '').toLowerCase();
      if (accept.includes('jpg') || accept.includes('jpeg') || accept.includes('png') || accept.includes('webp') || accept.includes('image')) {
        target = el;
        break;
      }
    }
    if (target) break;
  }
  if (!target) return JSON.stringify({ok: false, error: 'no file input', expected, uploaded: 0});

  const before = countImages();
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
      const url = this.__mmpUrl || '';
      if (url.includes('upload') || url.includes('cdn') || url.includes('fileserver') || url.includes('sns-img')) {
        const orig = this.onreadystatechange;
        this.onreadystatechange = function() {
          if (this.readyState === 4) {
            if (this.status >= 200 && this.status < 300) completed += 1;
            if (completed >= expected) { restore(); resolve({completed, via: 'xhr'}); }
          }
          if (orig) try { orig.apply(this, arguments); } catch(e){}
        };
      }
      return origSend.apply(this, arguments);
    };
    const started = Date.now();
    const poll = () => {
      const rendered = Math.max(0, countImages() - before);
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
