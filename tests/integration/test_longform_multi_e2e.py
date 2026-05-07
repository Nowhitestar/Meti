import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "longform-multi.yaml"


def test_longform_multi_dry_run(tmp_path):
    p = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "meti.py"), "publish", str(FIXTURE)],
        capture_output=True,
        text=True,
        env={**os.environ, "METI_RUNS_DIR": str(tmp_path / "runs")},
    )
    assert p.returncode == 0, p.stderr

    rd = next((tmp_path / "runs").iterdir())
    result = json.loads((rd / "result.json").read_text())
    names = sorted(t["name"] for t in result["targets"])
    assert names == ["substack", "wechat-article", "x-article"]
    for t in result["targets"]:
        assert t["status"] == "ok"
    for sub in ["wechat-article", "x-article", "substack"]:
        assert (rd / "packs" / sub / "payload.json").exists()
