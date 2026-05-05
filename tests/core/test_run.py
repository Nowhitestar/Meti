import json
from pathlib import Path

import pytest

from core.run import Run, slugify


def test_slugify_basic():
    assert slugify("Hello World") == "hello-world"
    assert slugify("AI 创业的三个误区").startswith("ai-")
    assert slugify("a" * 100).__len__() <= 40


def test_run_create_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MMP_RUNS_DIR", str(tmp_path / "runs"))
    r = Run.create(title="Hello", mmp_version="0.2.0", host="claude-code", mode="draft")
    assert r.dir.exists()
    assert (r.dir / "packs").exists()
    assert (r.dir / "checkpoints").exists()
    assert (r.dir / "artifacts").exists()
    assert "hello" in r.dir.name


def test_result_serialization(tmp_path, monkeypatch):
    monkeypatch.setenv("MMP_RUNS_DIR", str(tmp_path / "runs"))
    r = Run.create(title="X", mmp_version="0.2.0", host="cc", mode="draft")
    r.add_target_result(
        name="wechat-article",
        account="default",
        status="ok",
        mode_actual="draft-platform",
        external_id="m_123",
        draft_url=None,
    )
    r.finalize()
    data = json.loads((r.dir / "result.json").read_text())
    assert data["mode"] == "draft"
    assert data["targets"][0]["name"] == "wechat-article"
    assert data["targets"][0]["status"] == "ok"
    assert data["targets"][0]["external_id"] == "m_123"


def test_log_append(tmp_path, monkeypatch):
    monkeypatch.setenv("MMP_RUNS_DIR", str(tmp_path / "runs"))
    r = Run.create(title="X", mmp_version="0.2.0", host="cc", mode="draft")
    r.log("RUN_START", run_id=r.run_id)
    r.log("PREPARE_OK", target="wechat-article")
    text = (r.dir / "publish-log.md").read_text()
    assert "RUN_START" in text
    assert "PREPARE_OK" in text


def test_checkpoint_write_read(tmp_path, monkeypatch):
    monkeypatch.setenv("MMP_RUNS_DIR", str(tmp_path / "runs"))
    r = Run.create(title="X", mmp_version="0.2.0", host="cc", mode="draft")
    r.checkpoint("wechat-article", step="thumb_uploaded", external_ids={"thumb_id": "t1"})
    cp = r.read_checkpoint("wechat-article")
    assert cp["step"] == "thumb_uploaded"
    assert cp["external_ids"]["thumb_id"] == "t1"


def test_resume_loads_existing_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MMP_RUNS_DIR", str(tmp_path / "runs"))
    r = Run.create(title="Y", mmp_version="0.2.0", host="cc", mode="draft")
    r.checkpoint("x-article", step="prepared")
    run_dir = r.dir

    r2 = Run.from_dir(run_dir)
    assert r2.run_id == r.run_id
    assert r2.read_checkpoint("x-article")["step"] == "prepared"
