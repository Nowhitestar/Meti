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
import time
from pathlib import Path
from typing import Any

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
    'input[type=file][accept*="jpg"][multiple]',
    'input[type=file][accept*="jpg"]',
    'input[type=file][accept*="png"]',
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

PAGE_LOAD_WAIT_S = 5.0
UPLOAD_WAIT_S = 10.0  # per image; XHS server processes each
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
      if (accept.includes('jpg') || accept.includes('jpeg') || accept.includes('png') || accept.includes('webp')) {
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
        raise RuntimeError(
            "XHS Creator redirected to login. Log in to "
            "creator.xiaohongshu.com in Chrome, then retry. "
            f"Current URL: {cur}"
        )

    probe_raw = br.evaluate(_JS_EDITOR_PROBE)
    probe = _parse_eval(probe_raw)
    if not probe.get("fileInputFound"):
        raise RuntimeError(
            f"XHS editor: no image-accepting `<input type=file>` found. "
            f"Tried selectors: {FILE_INPUT_SELECTOR_CANDIDATES}. "
            f"State: {probe}. XHS may have changed UI; update "
            f"FILE_INPUT_SELECTOR_CANDIDATES in {__file__}."
        )

    # 3. Upload each image.
    for idx, image_path in enumerate(images):
        _upload_one_image(image_path, idx)

    # 4. Set title.
    if title:
        title_raw = br.evaluate(_js_set_title(title))
        title_res = _parse_eval(title_raw)
        if not title_res.get("ok"):
            raise RuntimeError(
                f"XHS: failed to set title (tried selectors "
                f"{TITLE_SELECTOR_CANDIDATES}): "
                f"{title_res.get('reason', title_res)}"
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
            raise RuntimeError(
                f"XHS: failed to set caption (tried selectors "
                f"{BODY_SELECTOR_CANDIDATES}): "
                f"{body_res.get('reason', body_res)}"
            )

    # 6. Click 存草稿 — XHS persists draft to server-side 草稿箱.
    save_raw = br.evaluate(_js_click_save())
    save = _parse_eval(save_raw)
    if not save.get("clicked"):
        raise RuntimeError(
            f"XHS: failed to click save-draft button (tried texts "
            f"{SAVE_BUTTON_TEXTS}): {save.get('reason', save)}"
        )
    time.sleep(SAVE_WAIT_S)

    final_url = br.get_url()

    return {
        "draft_url": final_url,
        "external_id": None,  # XHS doesn't surface a draft id in URL
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
    # Let XHS render the thumbnail before next upload.
    time.sleep(UPLOAD_WAIT_S * 0.4)
