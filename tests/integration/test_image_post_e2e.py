import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "image-post-multi.yaml"


def test_image_post_dry_run_both_targets(tmp_path):
    p = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "meti.py"), "publish", str(FIXTURE)],
        capture_output=True,
        text=True,
        env={**os.environ, "METI_RUNS_DIR": str(tmp_path / "runs")},
    )
    assert p.returncode == 0, p.stderr

    runs = list((tmp_path / "runs").iterdir())
    rd = runs[0]
    result = json.loads((rd / "result.json").read_text())
    names = [t["name"] for t in result["targets"]]
    assert "xiaohongshu" in names
    assert "wechat-image" in names
    for t in result["targets"]:
        assert t["status"] == "ok"
        assert t["mode_actual"] == "dry-run"

    assert (rd / "packs" / "xiaohongshu" / "payload.json").exists()
    assert (rd / "packs" / "wechat-image" / "payload.json").exists()
