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


def test_execute_draft_returns_stub(article, tmp_path):
    """v0.2: no real X connector. Draft falls back to stub result with TODO note."""
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "x-article").mkdir(parents=True)
    p = XArticleProvider()
    p.prepare(article, article.targets[0], run_dir)
    res = p.execute(
        run_dir,
        article.targets[0],
        mode="draft",
        credentials={"X_AUTH_TOKEN": "stub"},
    )
    assert res.mode_actual == "stub"
    assert res.extras.get("connector_status") == "not-implemented"


def test_execute_publish_refused(article, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "x-article").mkdir(parents=True)
    p = XArticleProvider()
    p.prepare(article, article.targets[0], run_dir)
    with pytest.raises(NotImplementedError, match="publish"):
        p.execute(run_dir, article.targets[0], mode="publish", credentials={})
