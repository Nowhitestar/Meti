"""Unit tests for x_article.internal.browser_flow."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.browser import BrowserDiagnostic
from providers.x_article.internal import browser_flow as bf


def _ready_diag() -> BrowserDiagnostic:
    return BrowserDiagnostic(code="ready", message="ok", recoverable=False)


def test_create_draft_happy_path_returns_durable_evidence():
    urls = iter(
        [
            "https://x.com/compose/articles",
            "https://x.com/compose/articles/edit/12345",
            "https://x.com/compose/articles/edit/12345",
        ]
    )
    with (
        patch("core.browser.diagnose", return_value=_ready_diag()),
        patch("core.browser.open_url"),
        patch("core.browser.get_url", side_effect=lambda: next(urls)),
        patch("core.browser.click"),
        patch("core.browser.type_text"),
        patch("time.sleep"),
    ):
        result = bf.create_draft({"title": "Title", "body": "Body"})
    assert result == {
        "draft_url": "https://x.com/compose/articles/edit/12345",
        "external_id": "12345",
    }


def test_create_draft_preflight_failure_is_structured():
    diag = BrowserDiagnostic(
        code="workspace_stale",
        message="stale",
        recoverable=True,
        next_actions=["bind again"],
    )
    with patch("core.browser.diagnose", return_value=diag):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.create_draft({"title": "Title", "body": "Body"})
    assert exc.value.error_code == "workspace_stale"
    assert exc.value.error_kind == "browser_readiness"
    assert exc.value.manual_recovery == "bind again"


def test_create_draft_login_redirect_is_structured():
    with (
        patch("core.browser.diagnose", return_value=_ready_diag()),
        patch("core.browser.open_url"),
        patch("core.browser.get_url", return_value="https://x.com/i/flow/login?state=secret"),
        patch("time.sleep"),
    ):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.create_draft({"title": "Title", "body": "Body"})
    assert exc.value.error_code == "platform_login_required"
    assert exc.value.details["current_url"] == "https://x.com/i/flow/login?…"


def test_create_draft_premium_gate_is_structured():
    with (
        patch("core.browser.diagnose", return_value=_ready_diag()),
        patch("core.browser.open_url"),
        patch("core.browser.get_url", return_value="https://x.com/i/premium_sign_up"),
        patch("time.sleep"),
    ):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.create_draft({"title": "Title", "body": "Body"})
    assert exc.value.error_code == "capability_gated"
    assert exc.value.recoverable is False


def test_create_draft_write_button_selector_drift():
    with (
        patch("core.browser.diagnose", return_value=_ready_diag()),
        patch("core.browser.open_url"),
        patch("core.browser.get_url", return_value="https://x.com/compose/articles"),
        patch("core.browser.click", side_effect=RuntimeError("missing")),
        patch("time.sleep"),
    ):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.create_draft({"title": "Title", "body": "Body"})
    assert exc.value.error_code == "selector_drift"


def test_create_draft_autosave_timeout_needs_review():
    urls = iter(
        [
            "https://x.com/compose/articles",
            "https://x.com/compose/articles/edit/12345",
            "https://x.com/compose/articles",
        ]
    )
    with (
        patch("core.browser.diagnose", return_value=_ready_diag()),
        patch("core.browser.open_url"),
        patch("core.browser.get_url", side_effect=lambda: next(urls)),
        patch("core.browser.click"),
        patch("core.browser.type_text"),
        patch("time.sleep"),
    ):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.create_draft({"title": "Title", "body": "Body"})
    assert exc.value.error_code == "autosave_timeout_needs_review"
    assert exc.value.error_kind == "review_needed"
