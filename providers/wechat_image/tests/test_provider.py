import json

import pytest

from core.manifest import Manifest, Target
from providers.wechat_image.provider import WeChatImageProvider


@pytest.fixture
def img_manifest(tmp_path):
    img = tmp_path / "01.png"
    img.write_bytes(b"png")
    return Manifest(
        schema_version="0.2",
        type="image-post",
        title="短",
        body="caption text",
        mode="dry-run",
        targets=[Target(name="wechat-image")],
        images=[str(img)],
    )


def test_validate(img_manifest):
    p = WeChatImageProvider()
    res = p.validate(img_manifest, img_manifest.targets[0])
    assert all(v.severity.value != "error" for v in res.violations)


def test_prepare_writes_payload(img_manifest, tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    p = WeChatImageProvider()
    out = p.prepare(img_manifest, img_manifest.targets[0], run_dir)
    assert out.payload_path.exists()
    payload = json.loads(out.payload_path.read_text())
    assert payload["title"] == "短"
    assert payload["caption"] == "caption text"


def test_execute_draft_writes_browser_flow_guide(img_manifest, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "wechat-image").mkdir(parents=True)
    p = WeChatImageProvider()
    p.prepare(img_manifest, img_manifest.targets[0], run_dir)
    res = p.execute(run_dir, img_manifest.targets[0], mode="draft", credentials={})
    guide = run_dir / "packs" / "wechat-image" / "browser-flow.md"
    assert guide.exists()
    assert "mp.weixin.qq.com" in guide.read_text()
    assert res.status == "ok"
    assert res.mode_actual == "draft-local"


def test_execute_dry_run_skips_guide(img_manifest, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "wechat-image").mkdir(parents=True)
    p = WeChatImageProvider()
    p.prepare(img_manifest, img_manifest.targets[0], run_dir)
    res = p.execute(run_dir, img_manifest.targets[0], mode="dry-run", credentials={})
    assert res.mode_actual == "dry-run"


def test_execute_publish_refused(img_manifest, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "wechat-image").mkdir(parents=True)
    p = WeChatImageProvider()
    p.prepare(img_manifest, img_manifest.targets[0], run_dir)
    with pytest.raises(NotImplementedError, match="publish"):
        p.execute(run_dir, img_manifest.targets[0], mode="publish", credentials={})
