import json

from core.run import Run, derive_run_summary, derive_target_action, should_resume_target, slugify


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
    assert data["schema_version"] == 2
    assert data["status"] == "ok"
    assert data["next_action"] == "none"
    assert data["resume_targets"] == []
    assert data["review_targets"] == []
    assert "needs_resume" not in data
    assert data["mode"] == "draft"
    assert data["targets"][0]["name"] == "wechat-article"
    assert data["targets"][0]["status"] == "ok"
    assert data["targets"][0]["next_action"] == "none"
    assert data["targets"][0]["external_id"] == "m_123"


def test_log_append(tmp_path, monkeypatch):
    monkeypatch.setenv("METI_RUNS_DIR", str(tmp_path / "runs"))
    r = Run.create(title="X", meti_version="0.2.0", host="cc", mode="draft")
    r.log("RUN_START", run_id=r.run_id)
    r.log("PREPARE_OK", target="wechat-article")
    text = (r.dir / "publish-log.md").read_text()
    assert "RUN_START" in text
    assert "PREPARE_OK" in text


def test_log_sanitizes_nested_values(tmp_path, monkeypatch):
    monkeypatch.setenv("METI_RUNS_DIR", str(tmp_path / "runs"))
    r = Run.create(title="X", meti_version="0.2.0", host="cc", mode="draft")
    r.log(
        "DIAG",
        current_url="https://example.test/callback?code=abc&safe=1",
        extras={"next": ["https://example.test/?session=secret"]},
    )
    text = (r.dir / "publish-log.md").read_text()
    assert "abc" not in text
    assert "secret" not in text
    assert "code=[REDACTED]" in text
    assert "session=[REDACTED]" in text


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
    monkeypatch.setenv("METI_RUNS_DIR", str(tmp_path / "runs"))
    r = Run.create(title="Empty", meti_version="0.2.0", host="cc", mode="dry-run")
    r.finalize()
    log = (r.dir / "publish-log.md").read_text()
    assert "RUN_DONE" in log
    assert "overall=empty" in log
    data = json.loads((r.dir / "result.json").read_text())
    assert data["schema_version"] == 2
    assert data["status"] == "empty"
    assert data["next_action"] == "none"
    assert data["resume_targets"] == []
    assert data["review_targets"] == []
    assert "needs_resume" not in data
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
    assert statuses["x-article"]["next_action"] == "review"
    assert statuses["substack"]["status"] == "failed"
    assert statuses["substack"]["error_code"] == "partial"
    assert statuses["substack"]["next_action"] == "review"
    assert statuses["wechat-image"]["mode_actual"] == "failed-needs-review"
    assert statuses["wechat-image"]["error_code"] == "missing_draft_evidence"
    assert statuses["wechat-image"]["next_action"] == "review"


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
    assert target["next_action"] == "review"
    assert "secret" not in target["draft_url"]
    assert "topsecret" not in target["extras"]["current_url"]
    assert target["extras"]["nested"] == ["https://e.test/?secret=[REDACTED]"]


def test_target_action_derivation_precedence():
    assert derive_target_action({"status": "ok"}) == "none"
    assert (
        derive_target_action(
            {"name": "substack", "status": "failed", "mode_actual": "failed-needs-review"}
        )
        == "review"
    )
    assert (
        derive_target_action(
            {
                "name": "substack",
                "status": "failed",
                "error_kind": "review_needed",
                "recoverable": True,
            }
        )
        == "review"
    )
    assert not should_resume_target(
        {"status": "failed", "error_kind": "review_needed", "recoverable": True}
    )
    assert not should_resume_target(
        {"status": "partial", "recoverable": True, "next_action": "review"}
    )
    assert not should_resume_target(
        {
            "status": "failed",
            "recoverable": True,
            "next_action": "resume",
            "error_kind": "review_needed",
        }
    )
    assert should_resume_target({"status": "partial", "recoverable": True})
    assert (
        derive_target_action({"status": "failed", "error": "validation: bad title"}) == "fix_input"
    )
    assert derive_target_action({"status": "failed"}) == "review"


def test_run_summary_derivation():
    assert derive_run_summary([]) == {
        "status": "empty",
        "next_action": "none",
        "resume_targets": [],
        "review_targets": [],
    }
    assert derive_run_summary([{"name": "wechat", "status": "ok"}]) == {
        "status": "ok",
        "next_action": "none",
        "resume_targets": [],
        "review_targets": [],
    }
    assert derive_run_summary(
        [
            {"name": "wechat", "status": "ok"},
            {"name": "x", "status": "partial", "recoverable": True},
            {"name": "substack", "status": "failed", "error_kind": "review_needed"},
        ]
    ) == {
        "status": "partial",
        "next_action": "resume",
        "resume_targets": ["x"],
        "review_targets": ["substack"],
    }
    assert derive_run_summary([{"name": "x", "status": "failed"}]) == {
        "status": "failed",
        "next_action": "review",
        "resume_targets": [],
        "review_targets": ["x"],
    }
    assert derive_run_summary(
        [{"name": "wechat", "status": "failed", "error_code": "mode_not_supported"}]
    ) == {
        "status": "failed",
        "next_action": "fix_input",
        "resume_targets": [],
        "review_targets": [],
    }
