import json
from unittest.mock import patch

import pytest

from core.manifest import Manifest, Target
from providers.xiaohongshu.provider import XiaohongshuProvider


@pytest.fixture
def img_manifest(tmp_path):
    img1 = tmp_path / "01.png"
    img2 = tmp_path / "02.png"
    img1.write_bytes(b"png1")
    img2.write_bytes(b"png2")
    return Manifest(
        schema_version="0.2",
        type="image-post",
        title="短标题",
        body="这是一段不超过 1000 字的图文 caption。",
        mode="dry-run",
        targets=[Target(name="xiaohongshu")],
        images=[str(img1), str(img2)],
        tags=["AI", "创业"],
    )


def test_validate_passes(img_manifest):
    p = XiaohongshuProvider()
    res = p.validate(img_manifest, img_manifest.targets[0])
    assert all(v.severity.value != "error" for v in res.violations)


def test_validate_title_too_long(img_manifest):
    img_manifest.title = "这个标题肯定超过了二十个字符的小红书限制确实如此非常长"
    p = XiaohongshuProvider()
    res = p.validate(img_manifest, img_manifest.targets[0])
    assert any(v.code == "TITLE_TOO_LONG" for v in res.violations)


def test_validate_no_images(img_manifest):
    img_manifest.images = []
    p = XiaohongshuProvider()
    res = p.validate(img_manifest, img_manifest.targets[0])
    assert any(v.code == "IMAGE_COUNT_BELOW_MIN" for v in res.violations)


def test_prepare_writes_payload(img_manifest, tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    p = XiaohongshuProvider()
    out = p.prepare(img_manifest, img_manifest.targets[0], run_dir)
    assert out.payload_path.exists()
    payload = json.loads(out.payload_path.read_text())
    assert payload["title"] == "短标题"
    assert len(payload["images"]) == 2
    assert payload["tags"] == ["AI", "创业"]


def test_execute_dry_run(img_manifest, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "xiaohongshu").mkdir(parents=True)
    p = XiaohongshuProvider()
    p.prepare(img_manifest, img_manifest.targets[0], run_dir)
    res = p.execute(run_dir, img_manifest.targets[0], mode="dry-run", credentials={})
    assert res.status == "ok"
    assert res.mode_actual == "dry-run"


def test_execute_draft_invokes_local_script(img_manifest, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "xiaohongshu").mkdir(parents=True)
    p = XiaohongshuProvider()
    p.prepare(img_manifest, img_manifest.targets[0], run_dir)

    with patch(
        "providers.xiaohongshu.provider._invoke_local_draft",
        return_value={"draft_id": "xhs_local_abc"},
    ) as mock:
        res = p.execute(
            run_dir,
            img_manifest.targets[0],
            mode="draft",
            credentials={"XHS_COOKIE_PATH": "/tmp/x"},
        )
    mock.assert_called_once()
    assert res.status == "ok"
    assert res.mode_actual == "draft-local"
    assert res.external_id == "xhs_local_abc"


def test_execute_publish_refused(img_manifest, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "xiaohongshu").mkdir(parents=True)
    p = XiaohongshuProvider()
    p.prepare(img_manifest, img_manifest.targets[0], run_dir)
    with pytest.raises(NotImplementedError, match="publish"):
        p.execute(
            run_dir,
            img_manifest.targets[0],
            mode="publish",
            credentials={"XHS_COOKIE_PATH": "x"},
        )
