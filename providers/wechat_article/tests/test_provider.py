import json
from pathlib import Path

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
