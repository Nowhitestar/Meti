"""Integration tests for `mmp resume <run-dir>`.

v0.3 P1a: target-level resume. Re-runs prepare+execute for any target
whose previous status != ok.
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
        [sys.executable, str(ROOT / "scripts" / "mmp.py"), *args],
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
        env_extra={"MMP_RUNS_DIR": str(tmp_path / "runs")},
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
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    # Run resume
    p = _run_mmp(
        "resume",
        str(rd),
        env_extra={"MMP_RUNS_DIR": str(tmp_path / "runs")},
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


def test_resume_target_filter_only_reruns_chosen(tmp_path):
    """`mmp resume <dir> --target X` should only touch target X."""
    p = _run_mmp(
        "publish",
        str(FIXTURE),
        env_extra={"MMP_RUNS_DIR": str(tmp_path / "runs")},
    )
    assert p.returncode == 0
    rd = next((tmp_path / "runs").iterdir())

    # Mark all 3 as failed
    result_path = rd / "result.json"
    result = json.loads(result_path.read_text())
    for t in result["targets"]:
        t["status"] = "failed"
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    # Resume only x-article
    p = _run_mmp(
        "resume",
        str(rd),
        "--target",
        "x-article",
        env_extra={"MMP_RUNS_DIR": str(tmp_path / "runs")},
    )
    assert p.returncode == 0, p.stderr

    log = (rd / "publish-log.md").read_text()
    # Only x-article should appear in RESUME_RETRY/EXECUTE_OK after the
    # RESUME_START line. wechat-article and substack should NOT have new
    # log entries from the resume.
    resume_section = log.split("RESUME_START")[-1]
    assert "target=x-article" in resume_section
    # wechat-article and substack didn't get retried (target filter)
    # The earlier RUN/TARGET sections will mention them, but the resume
    # section should not.
    assert "RESUME_RETRY  target=wechat-article" not in resume_section
    assert "RESUME_RETRY  target=substack" not in resume_section


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
