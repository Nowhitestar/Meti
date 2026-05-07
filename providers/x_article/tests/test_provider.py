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


def test_execute_draft_returns_stub_when_bridge_disconnected(article, tmp_path):
    """When the OpenCLI Browser Bridge is not connected (no extension /
    Chrome closed), execute falls back to stub mode and writes
    TODO-connector.md instead of failing."""
    from unittest.mock import patch

    run_dir = tmp_path / "run"
    (run_dir / "packs" / "x-article").mkdir(parents=True)
    p = XArticleProvider()
    p.prepare(article, article.targets[0], run_dir)

    with patch("core.browser.is_connected", return_value=False):
        res = p.execute(run_dir, article.targets[0], mode="draft", credentials={})

    assert res.mode_actual == "stub"
    assert res.extras["connector_status"] == "bridge-not-connected"
    assert "remediation" in res.extras
    todo = (run_dir / "packs" / "x-article" / "TODO-connector.md").read_text()
    assert "OpenCLI" in todo
    assert "chrome extension" in todo.lower()


def test_execute_draft_invokes_browser_flow_when_bridge_connected(article, tmp_path):
    """When the bridge is connected, execute calls create_draft and
    returns mode_actual=draft-platform with the URL / id."""
    from unittest.mock import patch

    run_dir = tmp_path / "run"
    (run_dir / "packs" / "x-article").mkdir(parents=True)
    p = XArticleProvider()
    p.prepare(article, article.targets[0], run_dir)

    with (
        patch("core.browser.is_connected", return_value=True),
        patch(
            "providers.x_article.internal.browser_flow.create_draft",
            return_value={
                "draft_url": "https://x.com/i/articles/12345/edit",
                "external_id": "12345",
            },
        ) as mock_create,
    ):
        res = p.execute(run_dir, article.targets[0], mode="draft", credentials={})

    mock_create.assert_called_once()
    assert res.status == "ok"
    assert res.mode_actual == "draft-platform"
    assert res.external_id == "12345"
    assert res.draft_url == "https://x.com/i/articles/12345/edit"


def test_health_check_reflects_bridge_connectivity(article):
    from unittest.mock import patch

    p = XArticleProvider()
    with patch("core.browser.is_connected", return_value=False):
        assert p.health_check({}).value == "failed"
    with patch("core.browser.is_connected", return_value=True):
        assert p.health_check({}).value == "ok"


def test_browser_login_url_is_set():
    """browser_login_url is what `meti browser login x-article` will navigate to."""
    p = XArticleProvider()
    assert p.browser_login_url == "https://x.com/i/flow/login"


def test_execute_publish_refused(article, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "x-article").mkdir(parents=True)
    p = XArticleProvider()
    p.prepare(article, article.targets[0], run_dir)
    with pytest.raises(NotImplementedError, match="publish"):
        p.execute(run_dir, article.targets[0], mode="publish", credentials={})
