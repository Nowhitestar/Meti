"""Unit tests for x_thread.internal.browser_flow."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.browser import BrowserDiagnostic
from providers.x_thread.internal import browser_flow as bf


def _ready_diag() -> BrowserDiagnostic:
    return BrowserDiagnostic(code="ready", message="ok", recoverable=False)


def test_compose_thread_happy_path_prefills_without_posting():
    typed = []
    with (
        patch("core.browser.diagnose", return_value=_ready_diag()),
        patch("core.browser.tab_new", return_value="tab-1") as tab_new,
        patch("core.browser.get_url", return_value=bf.COMPOSE_POST_URL),
        patch(
            "core.browser.type_text",
            side_effect=lambda sel, text, tab=None: typed.append((sel, text, tab)),
        ),
        patch("core.browser.evaluate", return_value={"result": '{"ok": true}'}),
        patch("core.browser.keys") as keys,
        patch("time.sleep"),
    ):
        result = bf.compose_thread({"tweets": ["one", "two"]})
    tab_new.assert_called_once_with(bf.COMPOSE_POST_URL)
    keys.assert_called_once_with("Enter", tab="tab-1")
    assert typed == [
        (bf.TEXTAREA_TEMPLATE.format(n=0), "one", "tab-1"),
        (bf.TEXTAREA_TEMPLATE.format(n=1), "two", "tab-1"),
    ]
    assert result["draft_url"] == bf.COMPOSE_POST_URL
    assert result["review_needed"] is True


def test_compose_thread_preflight_failure_is_structured():
    diag = BrowserDiagnostic(
        code="bound_tab_missing",
        message="missing",
        recoverable=True,
        next_actions=["bind"],
    )
    with patch("core.browser.diagnose", return_value=diag):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.compose_thread({"tweets": ["one"]})
    assert exc.value.error_code == "bound_tab_missing"
    assert exc.value.error_kind == "browser_readiness"


def test_compose_thread_login_redirect_is_structured():
    with (
        patch("core.browser.diagnose", return_value=_ready_diag()),
        patch("core.browser.tab_new", return_value="tab-1"),
        patch("core.browser.get_url", return_value="https://x.com/i/flow/login?state=secret"),
        patch("time.sleep"),
    ):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.compose_thread({"tweets": ["one"]})
    assert exc.value.error_code == "platform_login_required"
    assert exc.value.details["current_url"] == "https://x.com/i/flow/login?…"


def test_compose_thread_first_textarea_selector_drift():
    with (
        patch("core.browser.diagnose", return_value=_ready_diag()),
        patch("core.browser.tab_new", return_value="tab-1"),
        patch("core.browser.get_url", return_value=bf.COMPOSE_POST_URL),
        patch("core.browser.type_text", side_effect=RuntimeError("missing")),
        patch("time.sleep"),
    ):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.compose_thread({"tweets": ["one"]})
    assert exc.value.error_code == "selector_drift"


def test_compose_thread_missing_add_button_needs_review():
    with (
        patch("core.browser.diagnose", return_value=_ready_diag()),
        patch("core.browser.tab_new", return_value="tab-1"),
        patch("core.browser.get_url", return_value=bf.COMPOSE_POST_URL),
        patch("core.browser.type_text"),
        patch(
            "core.browser.evaluate",
            return_value={"result": '{"ok": false, "reason": "no_add_button"}'},
        ),
        patch("time.sleep"),
    ):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.compose_thread({"tweets": ["one", "two"]})
    assert exc.value.error_code == "thread_add_button_missing"
    assert exc.value.error_kind == "review_needed"


def test_compose_thread_subsequent_textarea_missing_needs_review():
    calls = {"n": 0}

    def type_side_effect(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("missing second")

    with (
        patch("core.browser.diagnose", return_value=_ready_diag()),
        patch("core.browser.tab_new", return_value="tab-1"),
        patch("core.browser.get_url", return_value=bf.COMPOSE_POST_URL),
        patch("core.browser.type_text", side_effect=type_side_effect),
        patch("core.browser.evaluate", return_value={"result": '{"ok": true}'}),
        patch("core.browser.keys"),
        patch("time.sleep"),
    ):
        with pytest.raises(bf.BrowserFlowError) as exc:
            bf.compose_thread({"tweets": ["one", "two"]})
    assert exc.value.error_code == "partial_thread_needs_review"
    assert exc.value.error_kind == "review_needed"
