"""Unit tests for xiaohongshu.internal.browser_flow."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from providers.xiaohongshu.internal import browser_flow as bf


@pytest.fixture
def fake_image(tmp_path):
    p = tmp_path / "shot.jpg"
    p.write_bytes(b"\xff\xd8\xff\xd9")
    return p


def _eval_envelope(value: object) -> dict:
    return {"_raw": json.dumps(value)}


def test_create_draft_happy_path_autosave(fake_image):
    eval_returns = iter([
        _eval_envelope({"fileInputFound": True, "fileInputCount": 1}),
        _eval_envelope({"ok": True, "chunks": 1}),
        _eval_envelope({"ok": True, "uploaded": 1, "expected": 1}),
        _eval_envelope({"ok": True, "value": "短标题"}),
        _eval_envelope({"ok": True, "length": 12}),
        _eval_envelope({"clicked": False, "reason": "no save button found"}),
    ])
    final_url = "https://creator.xiaohongshu.com/publish/publish?target=image&draft=local"
    with (
        patch("core.browser.open_url"),
        patch("core.browser.get_url", side_effect=[bf.EDITOR_URL, final_url]),
        patch("core.browser.stage_text_payload", return_value="payload-key"),
        patch("core.browser.evaluate", side_effect=lambda *_a, **_k: next(eval_returns)),
        patch("time.sleep"),
    ):
        result = bf.create_draft({"title": "短标题", "caption": "正文", "images": [str(fake_image)], "tags": ["AI"]})
    assert result["draft_url"] == final_url
    assert result["save_clicked"] is False


def test_create_draft_login_required(fake_image):
    with (
        patch("core.browser.open_url"),
        patch("core.browser.get_url", return_value="https://creator.xiaohongshu.com/login?foo=secret"),
        patch("time.sleep"),
    ):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.create_draft({"title": "t", "caption": "c", "images": [str(fake_image)]})
    assert exc.value.error_code == "platform_login_required"
    assert "?…" in exc.value.details["current_url"]


def test_create_draft_no_image_input(fake_image):
    with (
        patch("core.browser.open_url"),
        patch("core.browser.get_url", return_value=bf.EDITOR_URL),
        patch("core.browser.evaluate", return_value=_eval_envelope({"fileInputFound": False})),
        patch("time.sleep"),
    ):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.create_draft({"title": "t", "caption": "c", "images": [str(fake_image)]})
    assert exc.value.error_code == "upload_selector_missing"


def test_create_draft_partial_upload_needs_review(fake_image):
    eval_returns = iter([
        _eval_envelope({"fileInputFound": True}),
        _eval_envelope({"ok": True, "chunks": 1}),
        _eval_envelope({"ok": True, "uploaded": 1, "expected": 2}),
    ])
    with (
        patch("core.browser.open_url"),
        patch("core.browser.get_url", return_value=bf.EDITOR_URL),
        patch("core.browser.stage_text_payload", return_value="payload-key"),
        patch("core.browser.evaluate", side_effect=lambda *_a, **_k: next(eval_returns)),
        patch("time.sleep"),
    ):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.create_draft({"title": "t", "caption": "c", "images": [str(fake_image), str(fake_image)]})
    assert exc.value.error_code == "partial_upload_needs_review"
    assert exc.value.error_kind == "review_needed"


def test_create_draft_save_button_failure(fake_image):
    eval_returns = iter([
        _eval_envelope({"fileInputFound": True}),
        _eval_envelope({"ok": True, "chunks": 1}),
        _eval_envelope({"ok": True, "uploaded": 1, "expected": 1}),
        _eval_envelope({"ok": True, "value": "t"}),
        _eval_envelope({"ok": True, "length": 1}),
        _eval_envelope({"clicked": False, "reason": "save button disabled"}),
    ])
    with (
        patch("core.browser.open_url"),
        patch("core.browser.get_url", return_value=bf.EDITOR_URL),
        patch("core.browser.stage_text_payload", return_value="payload-key"),
        patch("core.browser.evaluate", side_effect=lambda *_a, **_k: next(eval_returns)),
        patch("time.sleep"),
    ):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.create_draft({"title": "t", "caption": "c", "images": [str(fake_image)]})
    assert exc.value.error_code == "save_button_unavailable"
