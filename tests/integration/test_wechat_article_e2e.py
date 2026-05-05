import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "wechat-article-e2e.yaml"


def test_publish_dry_run_creates_run_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MMP_RUNS_DIR", str(tmp_path / "runs"))

    p = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mmp.py"), "publish", str(FIXTURE)],
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "MMP_RUNS_DIR": str(tmp_path / "runs")},
    )
    assert p.returncode == 0, p.stderr

    runs = list((tmp_path / "runs").iterdir())
    assert len(runs) == 1
    rd = runs[0]
    assert (rd / "manifest.lock.json").exists()
    assert (rd / "result.json").exists()
    assert (rd / "publish-log.md").exists()
    assert (rd / "packs" / "wechat-article" / "payload.json").exists()

    result = json.loads((rd / "result.json").read_text())
    assert result["mode"] == "dry-run"
    assert len(result["targets"]) == 1
    t = result["targets"][0]
    assert t["name"] == "wechat-article"
    assert t["status"] == "ok"
    assert t["mode_actual"] == "dry-run"


def test_validate_subcommand(tmp_path):
    p = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mmp.py"), "validate", str(FIXTURE)],
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stderr
    assert "OK" in p.stdout
