"""Unit tests for wechat_image.internal.browser_flow."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from providers.wechat_image.internal import browser_flow as bf


@pytest.fixture
def fake_image(tmp_path):
    p = tmp_path / "shot.jpg"
    p.write_bytes(b"\xff\xd8\xff\xd9")
    return p


def _eval_envelope(value: object) -> dict:
    return {"_raw": json.dumps(value)}


def test_appmsgid_extraction():
    url = "https://mp.weixin.qq.com/cgi-bin/appmsg?action=edit&type=77&appmsgid=12345&token=999"
    assert bf._extract_appmsgid(url) == "12345"


def test_appmsgid_extraction_missing():
    assert bf._extract_appmsgid("https://mp.weixin.qq.com/cgi-bin/home") is None


def test_token_regex_captures_session():
    url = "https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN&token=999999999"
    m = bf.TOKEN_RE.search(url)
    assert m and m.group(1) == "999999999"


def test_create_draft_requires_at_least_one_image():
    with pytest.raises(ValueError, match="at least one image"):
        bf.create_draft({"title": "t", "caption": "c", "images": []})


def test_create_draft_caps_at_nine_images(fake_image):
    with pytest.raises(ValueError, match="up to 9 images"):
        bf.create_draft({"title": "t", "caption": "c", "images": [str(fake_image)] * 10})


def test_create_draft_login_redirect_raises(fake_image):
    with (
        patch("core.browser.tab_new", return_value="fake-tab"),
        patch("core.browser.open_url"),
        patch("core.browser.get_url", return_value="https://mp.weixin.qq.com/cgi-bin/loginpage"),
    ):
        with pytest.raises(RuntimeError, match="sign-in"):
            bf.create_draft({"title": "t", "caption": "c", "images": [str(fake_image)]})


def test_create_draft_no_token_raises(fake_image):
    with (
        patch("core.browser.tab_new", return_value="fake-tab"),
        patch("core.browser.open_url"),
        patch("core.browser.get_url", return_value="https://mp.weixin.qq.com/"),
    ):
        with pytest.raises(RuntimeError, match="token"):
            bf.create_draft({"title": "t", "caption": "c", "images": [str(fake_image)]})


def test_create_draft_editor_not_ready_structured(fake_image):
    home = "https://mp.weixin.qq.com/cgi-bin/home?token=999&lang=zh_CN"
    editor = "https://mp.weixin.qq.com/cgi-bin/appmsg?action=add&type=77&token=999&lang=zh_CN"
    with (
        patch("core.browser.tab_new", return_value="fake-tab"),
        patch("core.browser.open_url"),
        patch("core.browser.get_url", side_effect=[home, editor]),
        patch("core.browser.evaluate", return_value=_eval_envelope({"ready": False, "fileInputsCount": 0})),
        patch("time.sleep"),
    ):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.create_draft({"title": "t", "caption": "c", "images": [str(fake_image)]})
    assert exc.value.error_code == "selector_drift"


def test_create_draft_happy_path_multi_image(fake_image):
    home = "https://mp.weixin.qq.com/cgi-bin/home?token=999&lang=zh_CN"
    editor_after_alloc = "https://mp.weixin.qq.com/cgi-bin/appmsg?action=edit&type=77&appmsgid=42&token=999"
    final_url = "https://mp.weixin.qq.com/cgi-bin/appmsg?action=edit&type=77&appmsgid=42&token=999"
    eval_returns = iter([
        _eval_envelope({"ready": True, "titleVisible": True, "fileInputsCount": 3, "appmsgid": 42}),
        _eval_envelope({"ok": True, "chunks": 2}),
        _eval_envelope({"ok": True, "uploaded": 2, "expected": 2}),
        _eval_envelope({"ok": True, "value": "test title", "fallback": False}),
        _eval_envelope({"focused": True, "currentText": ""}),
        _eval_envelope({"inserted": True, "via": "execCommand"}),
        _eval_envelope({"clicked": True}),
        _eval_envelope({"ready": True, "appmsgid": "42"}),
    ])
    with (
        patch("core.browser.tab_new", return_value="fake-tab"),
        patch("core.browser.open_url"),
        patch("core.browser.get_url", side_effect=[home, editor_after_alloc, final_url]),
        patch("core.browser.stage_text_payload", return_value="payload-key"),
        patch("core.browser.evaluate", side_effect=lambda *_a, **_k: next(eval_returns)),
        patch("time.sleep"),
    ):
        result = bf.create_draft({"title": "test title", "caption": "test caption", "images": [str(fake_image), str(fake_image)]})
    assert result["external_id"] == "42"
    assert "appmsgid=42" in result["draft_url"]


def test_create_draft_missing_upload_input_structured(fake_image):
    home = "https://mp.weixin.qq.com/cgi-bin/home?token=999&lang=zh_CN"
    editor = "https://mp.weixin.qq.com/cgi-bin/appmsg?action=edit&type=77&appmsgid=42&token=999"
    with (
        patch("core.browser.tab_new", return_value="fake-tab"),
        patch("core.browser.open_url"),
        patch("core.browser.get_url", side_effect=[home, editor]),
        patch("core.browser.evaluate", return_value=_eval_envelope({"ready": True, "fileInputsCount": 0, "appmsgid": 42})),
        patch("time.sleep"),
    ):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.create_draft({"title": "t", "caption": "c", "images": [str(fake_image)]})
    assert exc.value.error_code == "upload_selector_missing"
    assert exc.value.recoverable is True


def test_create_draft_upload_count_mismatch_needs_review(fake_image):
    home = "https://mp.weixin.qq.com/cgi-bin/home?token=999&lang=zh_CN"
    editor = "https://mp.weixin.qq.com/cgi-bin/appmsg?action=edit&type=77&appmsgid=42&token=999"
    eval_returns = iter([
        _eval_envelope({"ready": True, "fileInputsCount": 3, "appmsgid": 42}),
        _eval_envelope({"ok": True, "chunks": 1}),
        _eval_envelope({"ok": True, "uploaded": 1, "expected": 2}),
    ])
    with (
        patch("core.browser.tab_new", return_value="fake-tab"),
        patch("core.browser.open_url"),
        patch("core.browser.get_url", side_effect=[home, editor]),
        patch("core.browser.stage_text_payload", return_value="payload-key"),
        patch("core.browser.evaluate", side_effect=lambda *_a, **_k: next(eval_returns)),
        patch("time.sleep"),
    ):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.create_draft({"title": "t", "caption": "c", "images": [str(fake_image), str(fake_image)]})
    assert exc.value.error_code == "partial_upload_needs_review"
    assert exc.value.error_kind == "review_needed"


def test_create_draft_save_timeout_requires_durable_evidence(fake_image):
    home = "https://mp.weixin.qq.com/cgi-bin/home?token=999&lang=zh_CN"
    editor = "https://mp.weixin.qq.com/cgi-bin/appmsg?action=edit&type=77&token=999"
    eval_returns = iter([
        _eval_envelope({"ready": True, "fileInputsCount": 3, "appmsgid": None}),
        _eval_envelope({"ok": True, "chunks": 1}),
        _eval_envelope({"ok": True, "uploaded": 1, "expected": 1}),
        _eval_envelope({"ok": True, "value": "t", "fallback": False}),
        _eval_envelope({"focused": True, "currentText": ""}),
        _eval_envelope({"inserted": True, "via": "execCommand"}),
        _eval_envelope({"clicked": True}),
        _eval_envelope({"ready": False}),
    ])
    with (
        patch("core.browser.tab_new", return_value="fake-tab"),
        patch("core.browser.open_url"),
        patch("core.browser.get_url", side_effect=[home, editor, editor]),
        patch("core.browser.stage_text_payload", return_value="payload-key"),
        patch("core.browser.evaluate", side_effect=lambda *_a, **_k: next(eval_returns)),
        patch("time.sleep"),
        patch("time.monotonic", side_effect=[0, 10]),
    ):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.create_draft({"title": "t", "caption": "c", "images": [str(fake_image)]})
    assert exc.value.error_code == "save_timeout_needs_review"
    assert exc.value.error_kind == "review_needed"


def test_image_too_large_rejected(tmp_path):
    huge = tmp_path / "huge.jpg"
    huge.write_bytes(b"\0" * (31 * 1024 * 1024))
    home = "https://mp.weixin.qq.com/cgi-bin/home?token=999&lang=zh_CN"
    editor = "https://mp.weixin.qq.com/cgi-bin/appmsg?action=edit&type=77&appmsgid=42&token=999"
    with (
        patch("core.browser.tab_new", return_value="fake-tab"),
        patch("core.browser.open_url"),
        patch("core.browser.get_url", side_effect=[home, editor]),
        patch("core.browser.evaluate", return_value=_eval_envelope({"ready": True, "fileInputsCount": 3, "appmsgid": 42})),
        patch("time.sleep"),
    ):
        with pytest.raises(ValueError, match="MP rejects"):
            bf.create_draft({"title": "t", "caption": "c", "images": [str(huge)]})


def test_image_not_found_raises(tmp_path):
    home = "https://mp.weixin.qq.com/cgi-bin/home?token=999&lang=zh_CN"
    editor = "https://mp.weixin.qq.com/cgi-bin/appmsg?action=edit&type=77&appmsgid=42&token=999"
    with (
        patch("core.browser.tab_new", return_value="fake-tab"),
        patch("core.browser.open_url"),
        patch("core.browser.get_url", side_effect=[home, editor]),
        patch("core.browser.evaluate", return_value=_eval_envelope({"ready": True, "fileInputsCount": 3, "appmsgid": 42})),
        patch("time.sleep"),
    ):
        with pytest.raises(FileNotFoundError):
            bf.create_draft({"title": "t", "caption": "c", "images": [str(tmp_path / "missing.png")]})
