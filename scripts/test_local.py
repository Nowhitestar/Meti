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
    fixtures = [
        ROOT / "tests" / "fixtures" / "wechat-article-e2e.yaml",
        ROOT / "tests" / "fixtures" / "image-post-multi.yaml",
        ROOT / "tests" / "fixtures" / "longform-multi.yaml",
    ]
    with tempfile.TemporaryDirectory(prefix="mmp-smoke-") as tmp:
        tmp_path = Path(tmp)
        runs_dir = tmp_path / "runs"
        env_extra = {
            "MMP_RUNS_DIR": str(runs_dir),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        }

        for fix in fixtures:
            p = _run_mmp("validate", str(fix), env_extra=env_extra)
            assert p.returncode == 0, f"validate failed for {fix}:\n{p.stderr}"

            p = _run_mmp("publish", str(fix), env_extra=env_extra)
            assert p.returncode == 0, f"publish dry-run failed for {fix}:\n{p.stderr}"

        # doctor + list
        p = _run_mmp("doctor", env_extra=env_extra)
        assert p.returncode == 0
        p = _run_mmp("list", "providers", env_extra=env_extra)
        assert p.returncode == 0
        for prov in ("wechat-article", "xiaohongshu", "wechat-image", "x-article", "substack"):
            assert prov in p.stdout, f"{prov} missing from list"

        runs = sorted((runs_dir).iterdir())
        print(json.dumps({"ok": True, "tmp": str(tmp_path), "runs": [str(r) for r in runs]}, indent=2))
        return 0


if __name__ == "__main__":
    sys.exit(main())
