import json
from unittest.mock import patch

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
    assert payload["images"] == [str(tmp_path / "01.png")]


def test_execute_dry_run_skips_browser(img_manifest, tmp_path):
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


def test_execute_draft_stub_when_bridge_disconnected(img_manifest, tmp_path):
    """No bridge → stub mode, write TODO-connector.md, no exception."""
    run_dir = tmp_path / "run"
    pack_dir = run_dir / "packs" / "wechat-image"
    pack_dir.mkdir(parents=True)
    p = WeChatImageProvider()
    p.prepare(img_manifest, img_manifest.targets[0], run_dir)

    with patch("core.browser.is_connected", return_value=False):
        res = p.execute(run_dir, img_manifest.targets[0], mode="draft", credentials={})

    assert res.status == "failed"
    assert res.mode_actual == "stub"
    assert res.error_code == "bridge_disconnected"
    assert res.recoverable is True
    assert res.extras["connector_status"] == "bridge-not-connected"
    todo = pack_dir / "TODO-connector.md"
    assert todo.exists()
    assert "贴图" in todo.read_text()


def test_execute_draft_invokes_browser_flow(img_manifest, tmp_path):
    """Bridge connected → call browser_flow.create_draft, surface results."""
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "wechat-image").mkdir(parents=True)
    p = WeChatImageProvider()
    p.prepare(img_manifest, img_manifest.targets[0], run_dir)

    with (
        patch("core.browser.is_connected", return_value=True),
        patch("core.browser.ensure_bound") as ensure_bound,
        patch(
            "providers.wechat_image.internal.browser_flow.create_draft",
            return_value={
                "draft_url": "https://mp.weixin.qq.com/cgi-bin/appmsg?action=edit&type=77&appmsgid=42",
                "external_id": "42",
            },
        ),
    ):
        res = p.execute(run_dir, img_manifest.targets[0], mode="draft", credentials={})

    assert res.status == "ok"
    assert res.mode_actual == "draft-platform"
    assert res.external_id == "42"
    assert res.draft_url and "appmsgid=42" in res.draft_url
    assert res.extras["connector_status"] == "browser-ok"
    ensure_bound.assert_called_once_with(
        url="https://mp.weixin.qq.com/",
        domain="mp.weixin.qq.com",
    )


def test_health_check_reflects_bridge():
    p = WeChatImageProvider()
    with patch("core.browser.is_connected", return_value=False):
        assert p.health_check({}).value == "failed"
    with patch("core.browser.is_connected", return_value=True):
        assert p.health_check({}).value == "ok"


def test_browser_login_url_set():
    p = WeChatImageProvider()
    assert p.browser_login_url == "https://mp.weixin.qq.com/"
