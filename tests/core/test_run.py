import json

from core.run import Run, slugify


def test_slugify_basic():
    assert slugify("Hello World") == "hello-world"
    # Non-ASCII gets stripped; "AI 创业的三个误区" → "ai" only
    assert slugify("AI 创业的三个误区") == "ai"
    assert len(slugify("a" * 100)) <= 40
    assert slugify("") == "untitled"
    assert slugify("!!!") == "untitled"


def test_run_create_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("METI_RUNS_DIR", str(tmp_path / "runs"))
    r = Run.create(title="Hello", meti_version="0.2.0", host="claude-code", mode="draft")
    assert r.dir.exists()
    assert (r.dir / "packs").exists()
    assert (r.dir / "checkpoints").exists()
    assert (r.dir / "artifacts").exists()
    assert "hello" in r.dir.name


def test_result_serialization(tmp_path, monkeypatch):
    monkeypatch.setenv("METI_RUNS_DIR", str(tmp_path / "runs"))
    r = Run.create(title="X", meti_version="0.2.0", host="cc", mode="draft")
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
    monkeypatch.setenv("METI_RUNS_DIR", str(tmp_path / "runs"))
    r = Run.create(title="X", meti_version="0.2.0", host="cc", mode="draft")
    r.log("RUN_START", run_id=r.run_id)
    r.log("PREPARE_OK", target="wechat-article")
    text = (r.dir / "publish-log.md").read_text()
    assert "RUN_START" in text
    assert "PREPARE_OK" in text


def test_checkpoint_write_read(tmp_path, monkeypatch):
    monkeypatch.setenv("METI_RUNS_DIR", str(tmp_path / "runs"))
    r = Run.create(title="X", meti_version="0.2.0", host="cc", mode="draft")
    r.checkpoint("wechat-article", step="thumb_uploaded", external_ids={"thumb_id": "t1"})
    cp = r.read_checkpoint("wechat-article")
    assert cp["step"] == "thumb_uploaded"
    assert cp["external_ids"]["thumb_id"] == "t1"


def test_resume_loads_existing_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("METI_RUNS_DIR", str(tmp_path / "runs"))
    r = Run.create(title="Y", meti_version="0.2.0", host="cc", mode="draft")
    r.checkpoint("x-article", step="prepared")
    run_dir = r.dir

    r2 = Run.from_dir(run_dir)
    assert r2.run_id == r.run_id
    assert r2.read_checkpoint("x-article")["step"] == "prepared"


def test_run_create_avoids_collision(tmp_path, monkeypatch):
    monkeypatch.setenv("METI_RUNS_DIR", str(tmp_path / "runs"))
    r1 = Run.create(title="Same", meti_version="0.2.0", host="cc", mode="draft")
    r2 = Run.create(title="Same", meti_version="0.2.0", host="cc", mode="draft")
    assert r1.dir != r2.dir
    assert r1.run_id != r2.run_id
    # Second one should have a -2 suffix
    assert r2.run_id.endswith("-2")


def test_finalize_with_no_targets(tmp_path, monkeypatch):
    import json

    monkeypatch.setenv("METI_RUNS_DIR", str(tmp_path / "runs"))
    r = Run.create(title="Empty", meti_version="0.2.0", host="cc", mode="dry-run")
    r.finalize()
    log = (r.dir / "publish-log.md").read_text()
    assert "RUN_DONE" in log
    assert "overall=empty" in log
    data = json.loads((r.dir / "result.json").read_text())
    assert data["targets"] == []


def test_run_classifies_stub_partial_and_missing_draft_evidence_as_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("METI_RUNS_DIR", str(tmp_path / "runs"))
    r = Run.create(title="Review", meti_version="0.2.0", host="cc", mode="draft")
    r.add_target_result(name="x-article", account="default", status="ok", mode_actual="stub")
    r.add_target_result(name="substack", account="default", status="ok", mode_actual="partial")
    r.add_target_result(
        name="wechat-image",
        account="default",
        status="ok",
        mode_actual="draft-platform",
    )
    r.finalize()
    data = json.loads((r.dir / "result.json").read_text())
    statuses = {t["name"]: t for t in data["targets"]}
    assert statuses["x-article"]["status"] == "failed"
    assert statuses["x-article"]["error_code"] == "stub"
    assert statuses["substack"]["status"] == "failed"
    assert statuses["substack"]["error_code"] == "partial"
    assert statuses["wechat-image"]["mode_actual"] == "failed-needs-review"
    assert statuses["wechat-image"]["error_code"] == "missing_draft_evidence"


def test_result_json_preserves_structured_fields_and_redacts_token_urls(tmp_path, monkeypatch):
    monkeypatch.setenv("METI_RUNS_DIR", str(tmp_path / "runs"))
    r = Run.create(title="Secret", meti_version="0.2.0", host="cc", mode="draft")
    r.add_target_result(
        name="x-article",
        account="default",
        status="failed",
        mode_actual="failed-needs-review",
        draft_url="https://x.com/draft/1?token=secret&safe=1#frag",
        error="needs review",
        error_code="platform_login_required",
        error_kind="browser_readiness",
        recoverable=True,
        manual_recovery="Log in and resume",
        extras={
            "current_url": "https://x.com/login?auth=topsecret",
            "nested": ["https://e.test/?secret=s"],
        },
    )
    r.finalize()
    target = json.loads((r.dir / "result.json").read_text())["targets"][0]
    assert target["error_code"] == "platform_login_required"
    assert target["error_kind"] == "browser_readiness"
    assert target["recoverable"] is True
    assert target["manual_recovery"] == "Log in and resume"
    assert "secret" not in target["draft_url"]
    assert "topsecret" not in target["extras"]["current_url"]
    assert target["extras"]["nested"] == ["https://e.test/?secret=REDACTED"]
