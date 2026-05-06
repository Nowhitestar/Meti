import json

import pytest

from core.manifest import Manifest, Target
from providers.substack.provider import SubstackProvider


@pytest.fixture
def article():
    return Manifest(
        schema_version="0.2",
        type="longform",
        title="A Substack Post",
        body="Body text here.",
        mode="dry-run",
        targets=[Target(name="substack")],
        metadata={"subtitle": "An optional subtitle"},
    )


def test_validate_passes(article):
    p = SubstackProvider()
    res = p.validate(article, article.targets[0])
    assert all(v.severity.value != "error" for v in res.violations)


def test_validate_subtitle_too_long(article):
    article.metadata["subtitle"] = "x" * 250
    p = SubstackProvider()
    res = p.validate(article, article.targets[0])
    codes = [v.code for v in res.violations]
    assert "SUBSTACK_SUBTITLE_TOO_LONG" in codes


def test_prepare_writes_payload(article, tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    p = SubstackProvider()
    out = p.prepare(article, article.targets[0], run_dir)
    payload = json.loads(out.payload_path.read_text())
    assert payload["title"] == "A Substack Post"
    assert payload["subtitle"] == "An optional subtitle"


def test_execute_draft_returns_stub(article, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "substack").mkdir(parents=True)
    p = SubstackProvider()
    p.prepare(article, article.targets[0], run_dir)
    res = p.execute(
        run_dir,
        article.targets[0],
        mode="draft",
        credentials={"SUBSTACK_SESSION_COOKIE": "stub"},
    )
    assert res.mode_actual == "stub"
    assert res.extras.get("connector_status") == "not-implemented"


def test_execute_publish_refused(article, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "substack").mkdir(parents=True)
    p = SubstackProvider()
    p.prepare(article, article.targets[0], run_dir)
    with pytest.raises(NotImplementedError, match="publish"):
        p.execute(run_dir, article.targets[0], mode="publish", credentials={})
