import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def _run(*args, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "meti.py"), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_dump_context_returns_json(tmp_path):
    p = _run(
        "wizard",
        "--dump-context",
        env_extra={
            "METI_RUNS_DIR": str(tmp_path / "runs"),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        },
    )
    assert p.returncode == 0
    data = json.loads(p.stdout)
    assert "providers" in data
    assert "accounts" in data
    assert "settings" in data


def test_dump_context_filters_by_type(tmp_path):
    p = _run(
        "wizard",
        "--dump-context",
        "--type",
        "longform",
        env_extra={
            "METI_RUNS_DIR": str(tmp_path / "runs"),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        },
    )
    assert p.returncode == 0
    data = json.loads(p.stdout)
    for prov in data["providers"]:
        assert "longform" in prov["media_types"]


def test_commit_writes_run_dir(tmp_path):
    src = tmp_path / "m.yaml"
    src.write_text(
        'schema_version: "0.2"\n'
        "type: longform\n"
        'title: "X"\n'
        'body: "hi"\n'
        "mode: dry-run\n"
        "targets: [wechat-article]\n",
        encoding="utf-8",
    )
    p = _run(
        "wizard",
        "--commit",
        str(src),
        env_extra={
            "METI_RUNS_DIR": str(tmp_path / "runs"),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        },
    )
    assert p.returncode == 0, p.stderr
    assert "RUN_DIR" in p.stdout
    runs = list((tmp_path / "runs").iterdir())
    assert len(runs) == 1
    assert (runs[0] / "manifest.yaml").exists()
    assert (runs[0] / "manifest.lock.json").exists()
