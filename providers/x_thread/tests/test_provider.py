import json

import pytest

from core.manifest import Manifest, Target
from providers.x_thread.internal.browser_flow import _is_login_redirect
from providers.x_thread.provider import XThreadProvider
from providers.x_thread.rules import TWEET_MAX, split_thread


@pytest.fixture
def thread():
    body = "First tweet.\n\n---\n\nSecond tweet.\n\n---\n\nThird tweet."
    return Manifest(
        schema_version="0.2",
        type="thread",
        title="A Thread",
        body=body,
        mode="dry-run",
        targets=[Target(name="x-thread")],
    )


# ---- split_thread ---------------------------------------------------------


def test_split_thread_basic():
    body = "a\n---\nb\n---\nc"
    assert split_thread(body) == ["a", "b", "c"]


def test_split_thread_strips_whitespace_and_blank_lines():
    body = "  one  \n\n---\n\n  two  \n\n---\n\n   "
    assert split_thread(body) == ["one", "two"]


def test_split_thread_separator_must_be_alone_on_line():
    # `---` inline (e.g. "em — em") must NOT split.
    body = "tweet with --- inside\n---\nnext tweet"
    assert split_thread(body) == ["tweet with --- inside", "next tweet"]


def test_split_thread_empty_body():
    assert split_thread("") == []
    assert split_thread("   \n  \n") == []


# ---- validate -------------------------------------------------------------


def test_validate_passes(thread):
    p = XThreadProvider()
    res = p.validate(thread, thread.targets[0])
    assert all(v.severity.value != "error" for v in res.violations)


def test_validate_empty_thread_flagged():
    p = XThreadProvider()
    m = Manifest(
        schema_version="0.2",
        type="thread",
        title="t",
        body="",
        mode="dry-run",
        targets=[Target(name="x-thread")],
    )
    res = p.validate(m, m.targets[0])
    assert any(v.code == "THREAD_EMPTY" for v in res.violations)


def test_validate_tweet_too_long():
    p = XThreadProvider()
    m = Manifest(
        schema_version="0.2",
        type="thread",
        title="t",
        body="x" * (TWEET_MAX + 1),
        mode="dry-run",
        targets=[Target(name="x-thread")],
    )
    res = p.validate(m, m.targets[0])
    assert any(v.code == "TWEET_TOO_LONG" for v in res.violations)


def test_validate_thread_too_long():
    p = XThreadProvider()
    body = "\n---\n".join([f"tweet {i}" for i in range(30)])
    m = Manifest(
        schema_version="0.2",
        type="thread",
        title="t",
        body=body,
        mode="dry-run",
        targets=[Target(name="x-thread")],
    )
    res = p.validate(m, m.targets[0])
    assert any(v.code == "THREAD_TOO_LONG" for v in res.violations)


# ---- prepare --------------------------------------------------------------


def test_prepare_writes_payload_and_thread_md(thread, tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    p = XThreadProvider()
    out = p.prepare(thread, thread.targets[0], run_dir)
    payload = json.loads(out.payload_path.read_text())
    assert payload["tweets"] == ["First tweet.", "Second tweet.", "Third tweet."]
    assert (out.pack_dir / "thread.md").read_text() == thread.body


# ---- execute --------------------------------------------------------------


def test_execute_dry_run(thread, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "x-thread").mkdir(parents=True)
    p = XThreadProvider()
    p.prepare(thread, thread.targets[0], run_dir)
    res = p.execute(run_dir, thread.targets[0], mode="dry-run", credentials={})
    assert res.mode_actual == "dry-run"


def test_execute_draft_returns_stub_when_bridge_disconnected(thread, tmp_path):
    from unittest.mock import patch

    run_dir = tmp_path / "run"
    (run_dir / "packs" / "x-thread").mkdir(parents=True)
    p = XThreadProvider()
    p.prepare(thread, thread.targets[0], run_dir)

    with patch("core.browser.ensure_bound", return_value=False):
        res = p.execute(run_dir, thread.targets[0], mode="draft", credentials={})

    assert res.status == "failed"
    assert res.mode_actual == "stub"
    assert res.error_code == "bridge_disconnected"
    assert res.extras["connector_status"] == "bridge-not-connected"
    todo = (run_dir / "packs" / "x-thread" / "TODO-connector.md").read_text()
    assert "OpenCLI" in todo
    assert "Add post" in todo


def test_execute_draft_invokes_browser_flow_when_bridge_connected(thread, tmp_path):
    from unittest.mock import patch

    run_dir = tmp_path / "run"
    (run_dir / "packs" / "x-thread").mkdir(parents=True)
    p = XThreadProvider()
    p.prepare(thread, thread.targets[0], run_dir)

    with (
        patch("core.browser.ensure_bound", return_value=True),
        patch(
            "providers.x_thread.internal.browser_flow.compose_thread",
            return_value={
                "draft_url": "https://x.com/compose/post",
                "external_id": None,
                "review_needed": True,
                "manual_recovery": "review manually",
            },
        ) as mock_compose,
    ):
        res = p.execute(run_dir, thread.targets[0], mode="draft", credentials={})

    mock_compose.assert_called_once()
    assert res.status == "failed"
    assert res.mode_actual == "failed-needs-review"
    assert res.error_code == "thread_requires_review"
    assert res.external_id is None
    assert res.draft_url == "https://x.com/compose/post"
    assert res.extras["tweet_count"] == 3
    assert res.extras["connector_status"] == "browser-review-needed"


def test_execute_publish_refused(thread, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "x-thread").mkdir(parents=True)
    p = XThreadProvider()
    p.prepare(thread, thread.targets[0], run_dir)
    with pytest.raises(NotImplementedError, match="publish"):
        p.execute(run_dir, thread.targets[0], mode="publish", credentials={})


def test_health_check_reflects_bridge_connectivity():
    from unittest.mock import patch

    p = XThreadProvider()
    with patch("core.browser.is_connected", return_value=False):
        assert p.health_check({}).value == "failed"
    with patch("core.browser.is_connected", return_value=True):
        assert p.health_check({}).value == "ok"


def test_browser_login_url_is_set():
    p = XThreadProvider()
    assert p.browser_login_url == "https://x.com/i/flow/login"


# ---- internal helpers -----------------------------------------------------


def test_login_redirect_detection():
    assert _is_login_redirect("https://x.com/i/flow/login?redirect=...") is True
    assert _is_login_redirect("https://x.com/login") is True
    assert _is_login_redirect("https://x.com/compose/post") is False
    assert _is_login_redirect("") is False
