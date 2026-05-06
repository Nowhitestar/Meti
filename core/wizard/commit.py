"""Commit a validated manifest from the wizard into a fresh run dir."""

from __future__ import annotations

from pathlib import Path

from core.manifest import load_manifest, write_lock
from core.run import Run


def commit_manifest(src_path: str | Path) -> Path:
    src = Path(src_path).resolve()
    manifest = load_manifest(src)

    run = Run.create(
        title=manifest.title,
        mmp_version="0.2.0",
        host="wizard",
        mode=manifest.mode,
    )
    target_path = run.dir / "manifest.yaml"
    target_path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    write_lock(manifest, run.dir)
    run.log("WIZARD_COMMIT", source=str(src))
    return run.dir
