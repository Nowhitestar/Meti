import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core.manifest import Manifest, Target
from providers.wechat_article.provider import WeChatArticleProvider


@pytest.fixture
def sample_manifest(tmp_path):
    return Manifest(
        schema_version="0.2",
        type="longform",
        title="A reasonable title",
        body="# Hello\n\nBody text.",
        mode="dry-run",
        targets=[Target(name="wechat-article")],
        cover=str(tmp_path / "cover.png"),
        summary="一句话摘要",
        tags=["test"],
    )


def test_validate_passes(sample_manifest, tmp_path):
    cover = Path(sample_manifest.cover)
    cover.write_bytes(b"png-bytes")
    p = WeChatArticleProvider()
    res = p.validate(sample_manifest, sample_manifest.targets[0])
    assert all(v.severity.value != "error" for v in res.violations)


def test_validate_fails_when_no_cover(sample_manifest):
    sample_manifest.cover = None
    p = WeChatArticleProvider()
    res = p.validate(sample_manifest, sample_manifest.targets[0])
    assert any(v.code == "WECHAT_COVER_REQUIRED" for v in res.violations)


def test_prepare_writes_payload(sample_manifest, tmp_path):
    cover = Path(sample_manifest.cover)
    cover.write_bytes(b"png-bytes")
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    p = WeChatArticleProvider()
    out = p.prepare(sample_manifest, sample_manifest.targets[0], run_dir)
    assert out.payload_path.exists()
    payload = json.loads(out.payload_path.read_text())
    assert payload["title"] == "A reasonable title"
    assert payload["cover"].endswith("cover.png")
    assert "html" in payload
    assert "content" in payload


def test_execute_dry_run_writes_pseudo_draft(sample_manifest, tmp_path):
    cover = Path(sample_manifest.cover)
    cover.write_bytes(b"png")
    run_dir = tmp_path / "run2"
    (run_dir / "packs" / "wechat-article").mkdir(parents=True)
    p = WeChatArticleProvider()
    p.prepare(sample_manifest, sample_manifest.targets[0], run_dir)

    res = p.execute(run_dir, sample_manifest.targets[0], mode="dry-run", credentials={})
    assert res.status == "ok"
    assert res.mode_actual == "dry-run"
    assert res.external_id is None


def test_execute_draft_calls_api(sample_manifest, tmp_path):
    cover = Path(sample_manifest.cover)
    cover.write_bytes(b"png")
    run_dir = tmp_path / "run3"
    (run_dir / "packs" / "wechat-article").mkdir(parents=True)
    p = WeChatArticleProvider()
    p.prepare(sample_manifest, sample_manifest.targets[0], run_dir)

    creds = {"WECHAT_APP_ID": "wx", "WECHAT_APP_SECRET": "s"}
    with (
        patch(
            "providers.wechat_article.internal.wechat_api.get_access_token",
            return_value="tok-123",
        ),
        patch(
            "providers.wechat_article.internal.wechat_api.upload_thumb",
            return_value="thumb-id-1",
        ),
        patch(
            "providers.wechat_article.internal.wechat_api.add_draft",
            return_value="draft-id-9",
        ),
    ):
        res = p.execute(run_dir, sample_manifest.targets[0], mode="draft", credentials=creds)

    assert res.status == "ok"
    assert res.mode_actual == "draft-platform"
    assert res.external_id == "draft-id-9"


def test_execute_publish_refused(sample_manifest, tmp_path):
    cover = Path(sample_manifest.cover)
    cover.write_bytes(b"png")
    run_dir = tmp_path / "run4"
    (run_dir / "packs" / "wechat-article").mkdir(parents=True)
    p = WeChatArticleProvider()
    p.prepare(sample_manifest, sample_manifest.targets[0], run_dir)

    with pytest.raises(NotImplementedError, match="publish"):
        p.execute(run_dir, sample_manifest.targets[0], mode="publish", credentials={"a": "b"})
