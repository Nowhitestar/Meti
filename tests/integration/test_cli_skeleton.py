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


def test_validate_rejects_unsupported_mode(tmp_path):
    """mode=publish on a provider with capabilities.publish=false should fail validate."""
    src = tmp_path / "m.yaml"
    src.write_text(
        'schema_version: "0.2"\n'
        "type: longform\n"
        'title: "X"\n'
        'body: "hi"\n'
        "mode: publish\n"
        "targets: [wechat-article]\n",
        encoding="utf-8",
    )
    p = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mmp.py"), "validate", str(src)],
        capture_output=True,
        text=True,
    )
    assert p.returncode == 2
    assert "MODE_NOT_SUPPORTED" in p.stderr
