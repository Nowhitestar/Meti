#!/usr/bin/env python3
"""Local smoke test for multi-media-publisher v0.2.

Runs a few CLI flows in a tmp dir and asserts shape. Does NOT call any
external network.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "wechat-article-e2e.yaml"


def _run_mmp(*args, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mmp.py"), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mmp-smoke-") as tmp:
        tmp_path = Path(tmp)
        runs_dir = tmp_path / "runs"
        env_extra = {
            "MMP_RUNS_DIR": str(runs_dir),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        }

        # 1. validate
        p = _run_mmp("validate", str(FIXTURE), env_extra=env_extra)
        assert p.returncode == 0, f"validate failed:\n{p.stderr}"

        # 2. publish dry-run
        p = _run_mmp("publish", str(FIXTURE), env_extra=env_extra)
        assert p.returncode == 0, f"publish dry-run failed:\n{p.stderr}"
        runs = list(runs_dir.iterdir())
        assert len(runs) == 1
        rd = runs[0]
        result = json.loads((rd / "result.json").read_text())
        assert result["targets"][0]["status"] == "ok"
        assert result["targets"][0]["mode_actual"] == "dry-run"

        # 3. doctor
        p = _run_mmp("doctor", env_extra=env_extra)
        assert p.returncode == 0, f"doctor failed:\n{p.stderr}"

        # 4. list
        p = _run_mmp("list", "providers", env_extra=env_extra)
        assert p.returncode == 0
        assert "wechat-article" in p.stdout

        print(json.dumps({"ok": True, "tmp": str(tmp_path), "run": str(rd)}, indent=2))
        return 0


if __name__ == "__main__":
    sys.exit(main())
