"""Run lifecycle: directory creation, checkpoints, result.json, publish-log.md."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import host

_RESULT_SCHEMA_VERSION = 2
_SENSITIVE_QUERY_KEYS = frozenset(
    {"token", "access_token", "auth", "code", "state", "session", "key", "secret"}
)
_SENSITIVE_QUERY_PATTERN = "|".join(sorted(re.escape(k) for k in _SENSITIVE_QUERY_KEYS))
_SENSITIVE_QUERY_RE = re.compile(
    rf"([?&](?:{_SENSITIVE_QUERY_PATTERN})=)[^&#]*",
    flags=re.I,
)

RUN_STATUSES = frozenset({"ok", "partial", "failed", "empty"})
TARGET_STATUSES = frozenset({"ok", "failed", "skipped", "partial"})
NEXT_ACTIONS = frozenset({"none", "resume", "review", "fix_input"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _now_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _redact_url(url: str | None) -> str | None:
    if not url:
        return url
    return _SENSITIVE_QUERY_RE.sub(r"\1[REDACTED]", url)


def sanitize_artifact_value(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_url(value)
    if isinstance(value, list):
        return [sanitize_artifact_value(v) for v in value]
    if isinstance(value, tuple):
        return [sanitize_artifact_value(v) for v in value]
    if isinstance(value, dict):
        return {k: sanitize_artifact_value(v) for k, v in value.items()}
    return value


def _target_get(target: Any, key: str, default: Any = None) -> Any:
    if isinstance(target, dict):
        return target.get(key, default)
    return getattr(target, key, default)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes"}
    return bool(value)


def derive_target_action(target: Any) -> str:
    status = str(_target_get(target, "status", "") or "").lower()
    existing_action = str(_target_get(target, "next_action", "") or "").lower()
    if status == "ok":
        return "none"

    mode_actual = str(_target_get(target, "mode_actual", "") or "").lower()
    error_kind = str(_target_get(target, "error_kind", "") or "").lower()
    error_code = str(_target_get(target, "error_code", "") or "").lower()
    error = str(_target_get(target, "error", "") or "").lower()
    recoverable = _truthy(_target_get(target, "recoverable", False))

    if error_kind == "review_needed" or mode_actual == "failed-needs-review":
        return "review"
    if (
        error_kind in {"validation", "capability", "config", "credential", "credentials"}
        or error_code in {"mode_not_supported", "missing_credentials", "missing_credential"}
        or error.startswith(("validation:", "capability:", "config:", "credential:"))
    ):
        return "fix_input"
    if existing_action in NEXT_ACTIONS - {"none"}:
        return existing_action
    if recoverable and status in {"failed", "partial", "skipped"}:
        return "resume"
    if status in {"failed", "partial", "skipped"}:
        return "review"
    return "none"


def should_resume_target(target: Any) -> bool:
    return derive_target_action(target) == "resume"


def derive_run_summary(targets: list[Any]) -> dict[str, Any]:
    if not targets:
        return {
            "status": "empty",
            "next_action": "none",
            "resume_targets": [],
            "review_targets": [],
        }

    statuses = [str(_target_get(t, "status", "") or "").lower() for t in targets]
    if all(status == "ok" for status in statuses):
        run_status = "ok"
    elif any(status == "ok" for status in statuses):
        run_status = "partial"
    else:
        run_status = "failed"

    resume_targets = [
        _target_get(t, "name")
        for t in targets
        if _target_get(t, "name") and derive_target_action(t) == "resume"
    ]
    review_targets = [
        _target_get(t, "name")
        for t in targets
        if _target_get(t, "name") and derive_target_action(t) == "review"
    ]
    has_fix_input = any(derive_target_action(t) == "fix_input" for t in targets)

    if resume_targets:
        next_action = "resume"
    elif review_targets:
        next_action = "review"
    elif has_fix_input:
        next_action = "fix_input"
    else:
        next_action = "none"

    return {
        "status": run_status,
        "next_action": next_action,
        "resume_targets": resume_targets,
        "review_targets": review_targets,
    }


def _format_log_value(value: Any) -> str:
    value = sanitize_artifact_value(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


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
    error_code: str | None = None
    error_kind: str | None = None
    recoverable: bool = False
    manual_recovery: str | None = None
    next_action: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)
    violations: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Run:
    run_id: str
    dir: Path
    mode: str
    meti_version: str
    host: str
    started_at: str = field(default_factory=_now_iso)
    completed_at: str | None = None
    targets: list[_TargetResult] = field(default_factory=list)

    @classmethod
    def create(cls, title: str, meti_version: str, host: str, mode: str) -> Run:
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
        run = cls(run_id=rid, dir=d, mode=mode, meti_version=meti_version, host=host)
        run.log("RUN_START", run_id=rid, mode=mode)
        return run

    @classmethod
    def from_dir(cls, run_dir: Path) -> Run:
        # Reconstruct minimal state from disk (used for resume).
        rid = run_dir.name
        mode = "draft"
        # Try result.json if present
        rp = run_dir / "result.json"
        if rp.exists():
            data = json.loads(rp.read_text(encoding="utf-8"))
            mode = data.get("mode", mode)
        return cls(run_id=rid, dir=run_dir, mode=mode, meti_version="?", host="?")

    def add_target_result(
        self,
        name: str,
        account: str,
        status: str,
        mode_actual: str,
        external_id: str | None = None,
        draft_url: str | None = None,
        error: str | None = None,
        error_code: str | None = None,
        error_kind: str | None = None,
        recoverable: bool = False,
        manual_recovery: str | None = None,
        next_action: str | None = None,
        extras: dict[str, Any] | None = None,
        violations: list[dict[str, Any]] | None = None,
    ) -> None:
        if status == "ok" and mode_actual in {"stub", "partial", "failed-needs-review"}:
            status = "failed"
            error_code = error_code or mode_actual.replace("-", "_")
            error_kind = error_kind or "review_needed"
            recoverable = True
            error = error or "target requires manual review; not a confirmed platform draft"
        if status == "ok" and mode_actual == "draft-platform" and not (external_id or draft_url):
            status = "failed"
            mode_actual = "failed-needs-review"
            error_code = error_code or "missing_draft_evidence"
            error_kind = error_kind or "review_needed"
            recoverable = True
            error = error or "platform draft did not include durable draft evidence"
        self.targets.append(
            _TargetResult(
                name=name,
                account=account,
                status=status,
                mode_actual=mode_actual,
                external_id=external_id,
                draft_url=sanitize_artifact_value(draft_url),
                completed_at=_now_iso(),
                error=sanitize_artifact_value(error),
                error_code=error_code,
                error_kind=error_kind,
                recoverable=recoverable,
                manual_recovery=sanitize_artifact_value(manual_recovery),
                next_action=next_action,
                extras=sanitize_artifact_value(extras or {}),
                violations=sanitize_artifact_value(violations or []),
            )
        )

    def log(self, event: str, **kwargs: Any) -> None:
        line_parts = [_now_iso(), event]
        for k, v in kwargs.items():
            line_parts.append(f"{k}={_format_log_value(v)}")
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
        payload = sanitize_artifact_value(payload)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def read_checkpoint(self, target: str) -> dict[str, Any] | None:
        path = self.dir / "checkpoints" / f"{target}.checkpoint.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def finalize(self) -> None:
        self.completed_at = _now_iso()
        targets = []
        for target in self.targets:
            payload = sanitize_artifact_value(asdict(target))
            payload["next_action"] = derive_target_action(payload)
            if payload["next_action"] is None:
                payload["next_action"] = "none"
            targets.append(payload)
        summary = derive_run_summary(targets)
        result = {
            "run_id": self.run_id,
            "schema_version": _RESULT_SCHEMA_VERSION,
            **summary,
            "manifest_path": "manifest.yaml",
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "mode": self.mode,
            "host": self.host,
            "meti_version": self.meti_version,
            "targets": targets,
        }
        result = sanitize_artifact_value(result)
        (self.dir / "result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self.log("RUN_DONE", overall=summary["status"], next_action=summary["next_action"])


def host_runs_dir() -> Path:
    d = host.runs_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d
