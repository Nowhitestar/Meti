"""Unit tests for wechat_image.internal.browser_flow.

These tests mock ``core.browser.*`` so they exercise the flow logic
(URL construction, error paths, payload validation) without driving a
real Chrome. End-to-end verification is in
``docs/wechat-image-tietu-research.md`` and is run manually against a
real account.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from providers.wechat_image.internal import browser_flow as bf


@pytest.fixture
def fake_image(tmp_path):
    p = tmp_path / "shot.jpg"
    # 1x1 jpeg-ish bytes (just to satisfy is_file + read).
    p.write_bytes(b"\xff\xd8\xff\xd9")  # SOI + EOI
    return p


def _eval_envelope(value: object) -> dict:
    """Wrap a Python value the way opencli's `eval` would return it
    after our JS does `JSON.stringify(...)`."""
    return {"_raw": json.dumps(value)}


def test_appmsgid_extraction():
    url = "https://mp.weixin.qq.com/cgi-bin/appmsg?action=edit&type=77&appmsgid=12345&token=999"
    assert bf._extract_appmsgid(url) == "12345"


def test_appmsgid_extraction_missing():
    assert bf._extract_appmsgid("https://mp.weixin.qq.com/cgi-bin/home") is None


def test_token_regex_captures_session():
    url = "https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN&token=<MP_TOKEN>"
    m = bf.TOKEN_RE.search(url)
    assert m and m.group(1) == "<MP_TOKEN>"


def test_create_draft_requires_at_least_one_image():
    with pytest.raises(ValueError, match="at least one image"):
        bf.create_draft({"title": "t", "caption": "c", "images": []})


def test_create_draft_caps_at_nine_images(fake_image):
    paths = [str(fake_image)] * 10
    with pytest.raises(ValueError, match="up to 9 images"):
        bf.create_draft({"title": "t", "caption": "c", "images": paths})


def test_create_draft_login_redirect_raises(fake_image):
    """If MP redirects to sign-in, surface a clear RuntimeError."""
    with (
        patch("core.browser.open_url"),
        patch(
            "core.browser.get_url",
            return_value="https://mp.weixin.qq.com/cgi-bin/sign?",
        ),
    ):
        with pytest.raises(RuntimeError, match="sign-in"):
            bf.create_draft({"title": "t", "caption": "c", "images": [str(fake_image)]})


def test_create_draft_no_token_raises(fake_image):
    """If MP home URL has no token=..., surface a clear RuntimeError."""
    with (
        patch("core.browser.open_url"),
        patch("core.browser.get_url", return_value="https://mp.weixin.qq.com/"),
    ):
        with pytest.raises(RuntimeError, match="token"):
            bf.create_draft({"title": "t", "caption": "c", "images": [str(fake_image)]})


def test_create_draft_editor_not_ready_raises(fake_image):
    """If the editor's title selector is missing, surface a clear error."""
    home = "https://mp.weixin.qq.com/cgi-bin/home?token=999&lang=zh_CN"
    editor = "https://mp.weixin.qq.com/cgi-bin/appmsg?action=add&type=77&token=999&lang=zh_CN"
    with (
        patch("core.browser.open_url"),
        patch("core.browser.get_url", side_effect=[home, editor]),
        patch(
            "core.browser.evaluate",
            return_value=_eval_envelope({"ready": False, "fileInputsCount": 0}),
        ),
    ):
        with pytest.raises(RuntimeError, match="failed to load"):
            bf.create_draft({"title": "t", "caption": "c", "images": [str(fake_image)]})


def test_create_draft_happy_path(fake_image):
    """End-to-end happy path with all browser ops mocked.

    Verifies that on success we extract ``appmsgid`` from the final URL
    and return it as ``external_id``.
    """
    home = "https://mp.weixin.qq.com/cgi-bin/home?token=999&lang=zh_CN"
    editor_after_alloc = (
        "https://mp.weixin.qq.com/cgi-bin/appmsg?action=edit&type=77&appmsgid=42&token=999"
    )
    final_url = "https://mp.weixin.qq.com/cgi-bin/appmsg?action=edit&type=77&appmsgid=42&token=999"

    eval_returns = iter(
        [
            # 1. _JS_EDITOR_READY
            _eval_envelope(
                {"ready": True, "titleVisible": True, "fileInputsCount": 3, "appmsgid": 42}
            ),
            # 2. _js_inject_image (per image)
            _eval_envelope(
                {
                    "ok": True,
                    "result": {
                        "status": 200,
                        "body": {
                            "base_resp": {"ret": 0},
                            "content": "<MP_FILE_ID>",
                            "cdn_url": "https://mmbiz.qpic.cn/...",
                        },
                    },
                }
            ),
            # 3. _js_set_title
            _eval_envelope({"ok": True, "value": "test title", "fallback": False}),
            # 4. _JS_FOCUS_BODY
            _eval_envelope({"focused": True, "currentText": ""}),
            # 5. _js_dispatch_text
            _eval_envelope({"inserted": True, "via": "execCommand"}),
            # 6. _JS_CLICK_SAVE
            _eval_envelope({"clicked": True}),
        ]
    )

    with (
        patch("core.browser.open_url"),
        patch(
            "core.browser.get_url",
            side_effect=[home, editor_after_alloc, final_url],
        ),
        patch("core.browser.evaluate", side_effect=lambda *_a, **_k: next(eval_returns)),
        patch("time.sleep"),  # skip waits
    ):
        result = bf.create_draft(
            {
                "title": "test title",
                "caption": "test caption",
                "images": [str(fake_image)],
            }
        )

    assert result["external_id"] == "42"
    assert "appmsgid=42" in result["draft_url"]


def test_create_draft_image_upload_failure(fake_image):
    """Upload XHR failure should surface as RuntimeError."""
    home = "https://mp.weixin.qq.com/cgi-bin/home?token=999&lang=zh_CN"
    editor = "https://mp.weixin.qq.com/cgi-bin/appmsg?action=edit&type=77&appmsgid=42&token=999"
    eval_returns = iter(
        [
            _eval_envelope({"ready": True, "fileInputsCount": 3, "appmsgid": 42}),
            _eval_envelope(
                {
                    "ok": False,
                    "result": {
                        "status": 200,
                        "body": {"base_resp": {"ret": -1, "err_msg": "image too large"}},
                    },
                }
            ),
        ]
    )
    with (
        patch("core.browser.open_url"),
        patch("core.browser.get_url", side_effect=[home, editor]),
        patch("core.browser.evaluate", side_effect=lambda *_a, **_k: next(eval_returns)),
        patch("time.sleep"),
    ):
        with pytest.raises(RuntimeError, match="image upload"):
            bf.create_draft({"title": "t", "caption": "c", "images": [str(fake_image)]})


def test_image_too_large_rejected(tmp_path):
    """Files over 30MB should be rejected before the upload XHR even fires."""
    huge = tmp_path / "huge.jpg"
    huge.write_bytes(b"\0" * (31 * 1024 * 1024))
    home = "https://mp.weixin.qq.com/cgi-bin/home?token=999&lang=zh_CN"
    editor = "https://mp.weixin.qq.com/cgi-bin/appmsg?action=edit&type=77&appmsgid=42&token=999"

    with (
        patch("core.browser.open_url"),
        patch("core.browser.get_url", side_effect=[home, editor]),
        patch(
            "core.browser.evaluate",
            return_value=_eval_envelope({"ready": True, "fileInputsCount": 3, "appmsgid": 42}),
        ),
        patch("time.sleep"),
    ):
        with pytest.raises(ValueError, match="MP rejects"):
            bf.create_draft({"title": "t", "caption": "c", "images": [str(huge)]})


def test_image_not_found_raises(tmp_path):
    home = "https://mp.weixin.qq.com/cgi-bin/home?token=999&lang=zh_CN"
    editor = "https://mp.weixin.qq.com/cgi-bin/appmsg?action=edit&type=77&appmsgid=42&token=999"
    with (
        patch("core.browser.open_url"),
        patch("core.browser.get_url", side_effect=[home, editor]),
        patch(
            "core.browser.evaluate",
            return_value=_eval_envelope({"ready": True, "fileInputsCount": 3, "appmsgid": 42}),
        ),
        patch("time.sleep"),
    ):
        with pytest.raises(FileNotFoundError):
            bf.create_draft(
                {
                    "title": "t",
                    "caption": "c",
                    "images": [str(tmp_path / "missing.png")],
                }
            )
