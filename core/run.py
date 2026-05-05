"""Run lifecycle: directory creation, checkpoints, result.json, publish-log.md."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import host


_RESULT_SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _now_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def slugify(text: str, max_len: int = 40) -> str:
    """ASCII-friendly lowercase slug.

    Non-ASCII characters are dropped (NOT transliterated). Whitespace and
    underscores collapse to hyphens. Empty / non-word input becomes
    'untitled'. Max length truncates trailing hyphens.
    """
    s = (text or "").lower().strip()
    # Drop non-ASCII
    s = s.encode("ascii", "ignore").decode("ascii")
    # Strip non-(word/whitespace/hyphen)
    s = re.sub(r"[^\w\s-]+", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if not s:
        s = "untitled"
    return s[:max_len].rstrip("-")


@dataclass
class _TargetResult:
    name: str
    account: str
    status: str
    mode_actual: str
    external_id: str | None = None
    draft_url: str | None = None
    started_at: str = field(default_factory=_now_iso)
    completed_at: str | None = None
    error: str | None = None
    violations: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Run:
    run_id: str
    dir: Path
    mode: str
    mmp_version: str
    host: str
    started_at: str = field(default_factory=_now_iso)
    completed_at: str | None = None
    targets: list[_TargetResult] = field(default_factory=list)

    @classmethod
    def create(cls, title: str, mmp_version: str, host: str, mode: str) -> "Run":
        base_rid = f"{_now_id()}-{slugify(title)}"
        runs_root = host_runs_dir()
        # Resolve collision by appending -2, -3, ... if the base_rid dir already exists.
        rid = base_rid
        n = 1
        while (runs_root / rid).exists():
            n += 1
            rid = f"{base_rid}-{n}"
        d = runs_root / rid
        d.mkdir(parents=True)
        for sub in ("packs", "checkpoints", "artifacts"):
            (d / sub).mkdir()
        run = cls(run_id=rid, dir=d, mode=mode, mmp_version=mmp_version, host=host)
        run.log("RUN_START", run_id=rid, mode=mode)
        return run

    @classmethod
    def from_dir(cls, run_dir: Path) -> "Run":
        # Reconstruct minimal state from disk (used for resume).
        rid = run_dir.name
        mode = "draft"
        # Try result.json if present
        rp = run_dir / "result.json"
        if rp.exists():
            data = json.loads(rp.read_text(encoding="utf-8"))
            mode = data.get("mode", mode)
        return cls(run_id=rid, dir=run_dir, mode=mode, mmp_version="?", host="?")

    def add_target_result(
        self,
        name: str,
        account: str,
        status: str,
        mode_actual: str,
        external_id: str | None = None,
        draft_url: str | None = None,
        error: str | None = None,
        violations: list[dict[str, Any]] | None = None,
    ) -> None:
        self.targets.append(
            _TargetResult(
                name=name,
                account=account,
                status=status,
                mode_actual=mode_actual,
                external_id=external_id,
                draft_url=draft_url,
                completed_at=_now_iso(),
                error=error,
                violations=violations or [],
            )
        )

    def log(self, event: str, **kwargs: Any) -> None:
        line_parts = [_now_iso(), event]
        for k, v in kwargs.items():
            line_parts.append(f"{k}={v}")
        line = "  ".join(line_parts)
        log_path = self.dir / "publish-log.md"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def checkpoint(self, target: str, step: str, **extras: Any) -> None:
        cp_dir = self.dir / "checkpoints"
        cp_dir.mkdir(exist_ok=True)
        path = cp_dir / f"{target}.checkpoint.json"
        payload = {
            "target": target,
            "step": step,
            "started_at": _now_iso(),
            "external_ids": extras.pop("external_ids", {}),
            "next_step": extras.pop("next_step", None),
            **extras,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def read_checkpoint(self, target: str) -> dict[str, Any] | None:
        path = self.dir / "checkpoints" / f"{target}.checkpoint.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def finalize(self) -> None:
        self.completed_at = _now_iso()
        result = {
            "run_id": self.run_id,
            "schema_version": _RESULT_SCHEMA_VERSION,
            "manifest_path": "manifest.yaml",
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "mode": self.mode,
            "host": self.host,
            "mmp_version": self.mmp_version,
            "targets": [asdict(t) for t in self.targets],
        }
        (self.dir / "result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if not self.targets:
            overall = "empty"
        elif all(t.status == "ok" for t in self.targets):
            overall = "ok"
        else:
            overall = "partial"
        self.log("RUN_DONE", overall=overall)


def host_runs_dir() -> Path:
    d = host.runs_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d
