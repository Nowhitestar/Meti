"""Integration tests for `meti resume <run-dir>`.

Resume retries only targets whose run contract says `next_action=resume`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "longform-multi.yaml"


def _run_mmp(*args, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "meti.py"), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_resume_skips_ok_targets_reruns_failed(tmp_path):
    """If wechat-article was ok and x-article was failed, resume should
    skip wechat-article and rerun x-article (which is a stub → 'stub')."""
    # First, create a fresh run dir with dry-run (everything ok)
    p = _run_mmp(
        "publish",
        str(FIXTURE),
        env_extra={"METI_RUNS_DIR": str(tmp_path / "runs")},
    )
    assert p.returncode == 0, p.stderr
    runs = list((tmp_path / "runs").iterdir())
    rd = runs[0]

    # Manually rewrite result.json to mark x-article as failed
    result_path = rd / "result.json"
    result = json.loads(result_path.read_text())
    for t in result["targets"]:
        if t["name"] == "x-article":
            t["status"] = "failed"
            t["error"] = "simulated transient failure"
            t["recoverable"] = True
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    # Run resume
    p = _run_mmp(
        "resume",
        str(rd),
        env_extra={"METI_RUNS_DIR": str(tmp_path / "runs")},
    )
    assert p.returncode == 0, p.stderr

    # Result.json should show:
    # - wechat-article: status ok, carried from previous (mode_actual=dry-run)
    # - x-article: status ok, mode_actual=dry-run (re-ran successfully)
    # - substack: was ok before, carried
    new_result = json.loads(result_path.read_text())
    by_name = {t["name"]: t for t in new_result["targets"]}
    assert by_name["wechat-article"]["status"] == "ok"
    assert by_name["x-article"]["status"] == "ok"
    assert by_name["substack"]["status"] == "ok"

    # publish-log.md must show RESUME_START + RESUME_SKIP for ok ones +
    # RESUME_RETRY for x-article
    log = (rd / "publish-log.md").read_text()
    assert "RESUME_START" in log
    assert "RESUME_SKIP" in log
    assert "target=wechat-article" in log
    assert "RESUME_RETRY" in log
    assert "target=x-article" in log
    assert "reason=next-action-resume" in log


def test_resume_target_filter_only_reruns_chosen(tmp_path):
    """`meti resume <dir> --target X` should only touch target X."""
    p = _run_mmp(
        "publish",
        str(FIXTURE),
        env_extra={"METI_RUNS_DIR": str(tmp_path / "runs")},
    )
    assert p.returncode == 0
    rd = next((tmp_path / "runs").iterdir())

    # Mark all 3 as failed
    result_path = rd / "result.json"
    result = json.loads(result_path.read_text())
    for t in result["targets"]:
        t["status"] = "failed"
        t["recoverable"] = True
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    # Resume only x-article
    p = _run_mmp(
        "resume",
        str(rd),
        "--target",
        "x-article",
        env_extra={"METI_RUNS_DIR": str(tmp_path / "runs")},
    )
    assert p.returncode == 0, p.stderr

    log = (rd / "publish-log.md").read_text()
    # Only x-article should appear in RESUME_RETRY/EXECUTE_OK after the
    # RESUME_START line. wechat-article and substack should NOT have new
    # log entries from the resume.
    resume_section = log.split("RESUME_START")[-1]
    assert "target=x-article" in resume_section
    # wechat-article and substack are carried forward by target filter,
    # but they are not retried.
    assert "RESUME_SKIP  target=wechat-article  reason=target-filter" in resume_section
    assert "RESUME_SKIP  target=substack  reason=target-filter" in resume_section
    assert "RESUME_RETRY  target=wechat-article" not in resume_section
    assert "RESUME_RETRY  target=substack" not in resume_section


def test_resume_retries_partial_and_skips_review_needed_targets(tmp_path):
    p = _run_mmp(
        "publish",
        str(FIXTURE),
        env_extra={"METI_RUNS_DIR": str(tmp_path / "runs")},
    )
    assert p.returncode == 0, p.stderr
    rd = next((tmp_path / "runs").iterdir())

    result_path = rd / "result.json"
    result = json.loads(result_path.read_text())
    for t in result["targets"]:
        if t["name"] == "x-article":
            t["status"] = "partial"
            t["mode_actual"] = "partial"
            t["error_code"] = "selector_drift"
            t["error_kind"] = "recoverable"
            t["recoverable"] = True
        if t["name"] == "substack":
            t["status"] = "failed"
            t["mode_actual"] = "failed-needs-review"
            t["error_code"] = "autosave_timeout_needs_review"
            t["error_kind"] = "review_needed"
            t["recoverable"] = True
            t["manual_recovery"] = "Inspect the open editor tab before retrying."
            t["extras"] = {"current_url": "https://substack.com/p/edit?state=secret"}
            t["violations"] = [{"code": "NEEDS_REVIEW"}]
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    p = _run_mmp(
        "resume",
        str(rd),
        env_extra={"METI_RUNS_DIR": str(tmp_path / "runs")},
    )
    assert p.returncode == 0, p.stderr

    log = (rd / "publish-log.md").read_text()
    resume_section = log.split("RESUME_START")[-1]
    assert "RESUME_SKIP  target=wechat-article" in resume_section
    assert "RESUME_RETRY  target=x-article" in resume_section
    assert "RESUME_RETRY  target=substack" not in resume_section
    assert "RESUME_SKIP  target=substack  reason=next-action-review" in resume_section

    resumed = json.loads(result_path.read_text())
    by_name = {t["name"]: t for t in resumed["targets"]}
    assert by_name["substack"]["status"] == "failed"
    assert by_name["substack"]["next_action"] == "review"
    assert by_name["substack"]["recoverable"] is True
    assert by_name["substack"]["error_code"] == "autosave_timeout_needs_review"
    assert by_name["substack"]["error_kind"] == "review_needed"
    assert by_name["substack"]["manual_recovery"] == "Inspect the open editor tab before retrying."
    assert by_name["substack"]["extras"]["current_url"] == (
        "https://substack.com/p/edit?state=[REDACTED]"
    )
    assert by_name["substack"]["violations"] == [{"code": "NEEDS_REVIEW"}]


def test_resume_target_filter_does_not_force_review_target(tmp_path):
    p = _run_mmp(
        "publish",
        str(FIXTURE),
        env_extra={"METI_RUNS_DIR": str(tmp_path / "runs")},
    )
    assert p.returncode == 0, p.stderr
    rd = next((tmp_path / "runs").iterdir())

    result_path = rd / "result.json"
    result = json.loads(result_path.read_text())
    for t in result["targets"]:
        if t["name"] == "substack":
            t["status"] = "failed"
            t["mode_actual"] = "failed-needs-review"
            t["error_kind"] = "review_needed"
            t["recoverable"] = True
            t["next_action"] = "review"
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    p = _run_mmp(
        "resume",
        str(rd),
        "--target",
        "substack",
        env_extra={"METI_RUNS_DIR": str(tmp_path / "runs")},
    )
    assert p.returncode == 0, p.stderr

    resume_section = (rd / "publish-log.md").read_text().split("RESUME_START")[-1]
    assert "RESUME_RETRY  target=substack" not in resume_section
    assert "RESUME_SKIP  target=substack  reason=next-action-review" in resume_section


def test_resume_missing_run_dir_errors(tmp_path):
    p = _run_mmp(
        "resume",
        str(tmp_path / "does-not-exist"),
    )
    assert p.returncode == 2
    assert "not found" in p.stderr


def test_resume_run_dir_without_result_json_errors(tmp_path):
    """A run dir without result.json (e.g. created but never finalized)
    can't be resumed by the v0.3 baseline."""
    rd = tmp_path / "incomplete"
    rd.mkdir()
    (rd / "manifest.yaml").write_text("dummy")
    p = _run_mmp(
        "resume",
        str(rd),
    )
    assert p.returncode == 2
    assert "missing manifest.yaml or result.json" in p.stderr
