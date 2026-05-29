from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "meti.py"), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_update_version_dry_run_prints_plan() -> None:
    proc = run_cli("update", "--version", "v0.4.3", "--dry-run")

    assert proc.returncode == 0
    assert "current version" in proc.stdout
    assert "target version" in proc.stdout
    assert "install path" in proc.stdout
    assert "scripts/install.sh" in proc.stdout
    assert "~/.config/meti" in proc.stdout


def test_update_latest_dry_run_reports_latest_stable() -> None:
    proc = run_cli("update", "--latest", "--dry-run")

    assert proc.returncode == 0
    assert "target version: latest stable" in proc.stdout
    assert "dry-run: no files will be modified" in proc.stdout


def test_update_rejects_invalid_version() -> None:
    proc = run_cli("update", "--version", "0.4.3", "--dry-run")

    assert proc.returncode == 2
    assert "--version must be vX.Y.Z" in proc.stderr


def test_install_script_help_and_dry_run(tmp_path: Path) -> None:
    installer = ROOT / "scripts" / "install.sh"

    assert os.access(installer, os.X_OK)
    help_proc = subprocess.run(
        [str(installer), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_proc.returncode == 0
    for flag in ("--version", "--latest", "--target", "--yes"):
        assert flag in help_proc.stdout

    dry_run = subprocess.run(
        [
            str(installer),
            "--version",
            "v0.4.3",
            "--target",
            str(tmp_path),
            "--dry-run",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert dry_run.returncode == 0
    assert "https://github.com/Nowhitestar/meti/releases/download/v0.4.3" in dry_run.stdout
    assert "meti-claude-plugin-v0.4.3.zip" in dry_run.stdout
    assert list(tmp_path.iterdir()) == []

    invalid = subprocess.run(
        [str(installer), "--version", "0.4.3", "--target", str(tmp_path), "--dry-run"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert invalid.returncode == 2
    assert "--version must be vX.Y.Z" in invalid.stderr
