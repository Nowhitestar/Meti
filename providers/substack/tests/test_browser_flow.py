"""Unit tests for substack.internal.browser_flow."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.browser import BrowserDiagnostic
from providers.substack.internal import browser_flow as bf


def _ready_diag() -> BrowserDiagnostic:
    return BrowserDiagnostic(code="ready", message="ok", recoverable=False)


def test_create_draft_happy_path_returns_draft_url_and_id():
    urls = iter([
        "https://lewis.substack.com/publish/post/77777",
        "https://lewis.substack.com/publish/post/77777",
    ])
    with (
        patch("core.browser.diagnose", return_value=_ready_diag()),
        patch("core.browser.open_url") as open_url,
        patch("core.browser.get_url", side_effect=lambda: next(urls)),
        patch("core.browser.type_text") as type_text,
        patch("time.sleep"),
    ):
        result = bf.create_draft(
            {"title": "Title", "subtitle": "Sub", "body": "Body"},
            publication_url="https://lewis.substack.com",
        )
    open_url.assert_called_once_with("https://lewis.substack.com/publish/post")
    assert type_text.call_count == 3
    assert result == {
        "draft_url": "https://lewis.substack.com/publish/post/77777",
        "external_id": "77777",
    }


def test_create_draft_preflight_failure_is_structured():
    diag = BrowserDiagnostic(
        code="workspace_not_bound",
        message="not bound",
        recoverable=True,
        next_actions=["bind"],
    )
    with patch("core.browser.diagnose", return_value=diag):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.create_draft({"body": "Body"}, publication_url="https://lewis.substack.com")
    assert exc.value.error_code == "workspace_not_bound"
    assert exc.value.error_kind == "browser_readiness"


def test_create_draft_login_redirect_is_structured():
    with (
        patch("core.browser.diagnose", return_value=_ready_diag()),
        patch("core.browser.open_url"),
        patch("core.browser.get_url", return_value="https://substack.com/sign-in?next=secret"),
        patch("time.sleep"),
    ):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.create_draft({"body": "Body"}, publication_url="https://lewis.substack.com")
    assert exc.value.error_code == "platform_login_required"
    assert exc.value.details["current_url"] == "https://substack.com/sign-in?…"


def test_create_draft_missing_publication_or_no_draft_url_needs_review():
    with (
        patch("core.browser.diagnose", return_value=_ready_diag()),
        patch("core.browser.open_url"),
        patch("core.browser.get_url", return_value="https://substack.com/home"),
        patch("time.sleep"),
    ):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.create_draft({"body": "Body"}, publication_url="https://lewis.substack.com")
    assert exc.value.error_code == "draft_url_missing"
    assert exc.value.error_kind == "review_needed"


def test_create_draft_title_selector_drift_is_structured():
    with (
        patch("core.browser.diagnose", return_value=_ready_diag()),
        patch("core.browser.open_url"),
        patch("core.browser.get_url", return_value="https://lewis.substack.com/publish/post/77777"),
        patch("core.browser.type_text", side_effect=RuntimeError("missing")),
        patch("time.sleep"),
    ):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.create_draft({"title": "Title", "body": "Body"}, publication_url="https://lewis.substack.com")
    assert exc.value.error_code == "selector_drift"


def test_create_draft_final_url_lost_after_autosave_needs_review():
    urls = iter([
        "https://lewis.substack.com/publish/post/77777",
        "https://lewis.substack.com/publish/post",
    ])
    with (
        patch("core.browser.diagnose", return_value=_ready_diag()),
        patch("core.browser.open_url"),
        patch("core.browser.get_url", side_effect=lambda: next(urls)),
        patch("core.browser.type_text"),
        patch("time.sleep"),
    ):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.create_draft({"body": "Body"}, publication_url="https://lewis.substack.com")
    assert exc.value.error_code == "autosave_timeout_needs_review"
    assert exc.value.error_kind == "review_needed"
