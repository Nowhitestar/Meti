import json

import pytest

from core.manifest import Manifest, Target
from providers.x_article.provider import XArticleProvider


@pytest.fixture
def article(tmp_path):
    return Manifest(
        schema_version="0.2",
        type="longform",
        title="An X Article",
        body="# Heading\n\nBody.",
        mode="dry-run",
        targets=[Target(name="x-article")],
        summary="A summary",
        tags=["tech"],
    )


def test_validate(article):
    p = XArticleProvider()
    res = p.validate(article, article.targets[0])
    assert all(v.severity.value != "error" for v in res.violations)


def test_validate_title_too_long(article):
    article.title = "x" * 200
    p = XArticleProvider()
    res = p.validate(article, article.targets[0])
    assert any(v.code == "TITLE_TOO_LONG" for v in res.violations)


def test_prepare_writes_payload(article, tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    p = XArticleProvider()
    out = p.prepare(article, article.targets[0], run_dir)
    payload = json.loads(out.payload_path.read_text())
    assert payload["title"] == "An X Article"
    assert payload["body"].startswith("# Heading")


def test_execute_dry_run(article, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "x-article").mkdir(parents=True)
    p = XArticleProvider()
    p.prepare(article, article.targets[0], run_dir)
    res = p.execute(run_dir, article.targets[0], mode="dry-run", credentials={})
    assert res.mode_actual == "dry-run"


def test_execute_draft_returns_stub_when_no_browser_state(article, tmp_path, monkeypatch):
    """v0.3.1: browser flow tries to fire, falls back to stub when no
    saved browser state exists (the no-browser-state path).
    """
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    run_dir = tmp_path / "run"
    (run_dir / "packs" / "x-article").mkdir(parents=True)
    p = XArticleProvider()
    p.prepare(article, article.targets[0], run_dir)
    res = p.execute(
        run_dir,
        article.targets[0],
        mode="draft",
        credentials={},
    )
    assert res.mode_actual == "stub"
    assert res.extras.get("connector_status") == "no-browser-state"
    assert "remediation" in res.extras
    # TODO doc explains both options
    todo = (run_dir / "packs" / "x-article" / "TODO-connector.md").read_text()
    assert "mmp browser login x-article" in todo


def test_execute_draft_invokes_browser_flow_when_state_present(article, tmp_path, monkeypatch):
    """When state exists AND playwright is available, execute calls
    create_draft and returns mode_actual=draft-platform with the URL/id."""
    from unittest.mock import patch

    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    # Plant a fake state file
    state_dir = tmp_path / ".config" / "mmp" / "browser-state"
    state_dir.mkdir(parents=True)
    (state_dir / "x-article.json").write_text('{"cookies": [], "origins": []}')

    run_dir = tmp_path / "run"
    (run_dir / "packs" / "x-article").mkdir(parents=True)
    p = XArticleProvider()
    p.prepare(article, article.targets[0], run_dir)

    with patch(
        "providers.x_article.internal.browser_flow.create_draft",
        return_value={
            "draft_url": "https://x.com/i/articles/12345/edit",
            "external_id": "12345",
        },
    ) as mock_create:
        res = p.execute(run_dir, article.targets[0], mode="draft", credentials={})

    mock_create.assert_called_once()
    assert res.status == "ok"
    assert res.mode_actual == "draft-platform"
    assert res.external_id == "12345"
    assert res.draft_url == "https://x.com/i/articles/12345/edit"


def test_health_check_reflects_browser_state(article, tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    p = XArticleProvider()
    # No state → failed
    assert p.health_check({}).value == "failed"

    # Plant state → ok
    state_dir = tmp_path / ".config" / "mmp" / "browser-state"
    state_dir.mkdir(parents=True)
    (state_dir / "x-article.json").write_text("{}")
    assert p.health_check({}).value == "ok"


def test_browser_login_url_is_set():
    """browser_login_url is what `mmp browser login x-article` will navigate to."""
    p = XArticleProvider()
    assert p.browser_login_url == "https://x.com/i/flow/login"


def test_execute_publish_refused(article, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "x-article").mkdir(parents=True)
    p = XArticleProvider()
    p.prepare(article, article.targets[0], run_dir)
    with pytest.raises(NotImplementedError, match="publish"):
        p.execute(run_dir, article.targets[0], mode="publish", credentials={})
