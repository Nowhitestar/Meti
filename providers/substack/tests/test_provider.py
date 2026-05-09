import json
from unittest.mock import patch

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


def test_execute_draft_stub_when_no_publication_url(article, tmp_path, monkeypatch):
    """No publication_url in manifest options + no SUBSTACK_PUBLICATION_URL
    env → stub mode with clear remediation."""
    monkeypatch.delenv("SUBSTACK_PUBLICATION_URL", raising=False)

    run_dir = tmp_path / "run"
    (run_dir / "packs" / "substack").mkdir(parents=True)
    p = SubstackProvider()
    p.prepare(article, article.targets[0], run_dir)
    res = p.execute(run_dir, article.targets[0], mode="draft", credentials={})
    assert res.mode_actual == "stub"
    assert res.extras["connector_status"] == "missing-publication-url"
    assert "publication_url" in res.extras["remediation"]


def test_execute_draft_stub_when_bridge_disconnected(article, tmp_path, monkeypatch):
    """publication_url is set but bridge is not connected → stub."""
    monkeypatch.setenv("SUBSTACK_PUBLICATION_URL", "https://lewis.substack.com")

    run_dir = tmp_path / "run"
    (run_dir / "packs" / "substack").mkdir(parents=True)
    p = SubstackProvider()
    p.prepare(article, article.targets[0], run_dir)

    with patch("core.browser.ensure_bound", return_value=False):
        res = p.execute(run_dir, article.targets[0], mode="draft", credentials={})

    assert res.mode_actual == "stub"
    assert res.extras["connector_status"] == "bridge-not-connected"


def test_execute_draft_uses_publication_url_from_target_options(article, tmp_path, monkeypatch):
    """Manifest target.options.publication_url takes priority over env."""
    monkeypatch.setenv("SUBSTACK_PUBLICATION_URL", "https://env-fallback.substack.com")
    article.targets[0].options = {"publication_url": "https://manifest.substack.com"}

    run_dir = tmp_path / "run"
    (run_dir / "packs" / "substack").mkdir(parents=True)
    p = SubstackProvider()
    p.prepare(article, article.targets[0], run_dir)

    with (
        patch("core.browser.ensure_bound", return_value=True),
        patch(
            "providers.substack.internal.browser_flow.create_draft",
            return_value={
                "draft_url": "https://manifest.substack.com/publish/post/12345",
                "external_id": "12345",
            },
        ) as mock_create,
    ):
        res = p.execute(run_dir, article.targets[0], mode="draft", credentials={})

    # Confirm we passed the manifest URL, not the env URL.
    args, kwargs = mock_create.call_args
    assert kwargs["publication_url"] == "https://manifest.substack.com"
    assert res.mode_actual == "draft-platform"
    assert res.external_id == "12345"


def test_execute_draft_invokes_browser_flow(article, tmp_path, monkeypatch):
    monkeypatch.setenv("SUBSTACK_PUBLICATION_URL", "https://lewis.substack.com")
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "substack").mkdir(parents=True)
    p = SubstackProvider()
    p.prepare(article, article.targets[0], run_dir)

    with (
        patch("core.browser.ensure_bound", return_value=True),
        patch(
            "providers.substack.internal.browser_flow.create_draft",
            return_value={
                "draft_url": "https://lewis.substack.com/publish/post/77777",
                "external_id": "77777",
            },
        ),
    ):
        res = p.execute(run_dir, article.targets[0], mode="draft", credentials={})

    assert res.status == "ok"
    assert res.mode_actual == "draft-platform"
    assert res.external_id == "77777"
    assert res.draft_url == "https://lewis.substack.com/publish/post/77777"


def test_health_check_reflects_bridge(article):
    p = SubstackProvider()
    with patch("core.browser.is_connected", return_value=False):
        assert p.health_check({}).value == "failed"
    with patch("core.browser.is_connected", return_value=True):
        assert p.health_check({}).value == "ok"


def test_browser_login_url_is_set():
    p = SubstackProvider()
    assert p.browser_login_url == "https://substack.com/sign-in"


def test_execute_publish_refused(article, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "substack").mkdir(parents=True)
    p = SubstackProvider()
    p.prepare(article, article.targets[0], run_dir)
    with pytest.raises(NotImplementedError, match="publish"):
        p.execute(run_dir, article.targets[0], mode="publish", credentials={})
