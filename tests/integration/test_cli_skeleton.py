import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def _run(*args, env=None):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mmp.py"), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_no_args_prints_help():
    p = _run()
    assert p.returncode != 0
    assert "usage" in (p.stdout + p.stderr).lower()


def test_help_lists_subcommands():
    p = _run("--help")
    out = p.stdout + p.stderr
    for cmd in ["validate", "publish", "setup", "list", "resume", "doctor"]:
        assert cmd in out
