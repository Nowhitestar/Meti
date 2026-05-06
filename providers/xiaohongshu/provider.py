"""Xiaohongshu provider — local draft via the xiaohongshu skill's draft.sh.

This v0.2 provider only knows the `draft-local` path: it shells out to the
local xiaohongshu skill's `draft.sh`, which writes a JSON draft file to
``~/.xiaohongshu/drafts/`` (or ``XHS_DRAFT_DIR``). No platform upload, no API
call, no cookie required.

Platform draft and publish are deferred to v0.3.

draft.sh contract (verified empirically against the real script):
- Input: a single positional argument that is a JSON string with fields
  ``title``, ``content``, ``images`` (absolute paths), ``tags``, optional ``video``.
- Output: human-readable lines on stdout, starting with
  ``✓ 已创建本地草稿: <abs path to draft json>``.
- Side effect: a draft JSON file at ``$XHS_DRAFT_DIR/<ts>-<slug>.json``.

Discovery candidates (in order; first match wins):
1. ``$XHS_DRAFT_SH`` env var (full path to draft.sh)
2. ``~/.openclaw/workspace/skills/xiaohongshu/scripts/draft.sh`` (workspace install)
3. ``~/.openclaw/skills/xiaohongshu/scripts/draft.sh`` (legacy install)
4. ``~/.config/mmp/skills/xiaohongshu/scripts/draft.sh`` (mmp-managed install)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from core.errors import ProviderExecutionError
from core.provider import (
    CredentialSpec,
    ExecutionResult,
    HealthStatus,
    PreparedPayload,
    Provider,
    ValidationResult,
)
from providers.xiaohongshu.rules import XHS_RULES

_DRAFT_PATH_RE = re.compile(r"已创建本地草稿:\s*(.+)")


def _locate_draft_sh() -> Path | None:
    env = os.environ.get("XHS_DRAFT_SH", "").strip()
    if env:
        p = Path(env).expanduser()
        return p if p.exists() else None
    candidates = [
        Path.home() / ".openclaw" / "workspace" / "skills" / "xiaohongshu" / "scripts" / "draft.sh",
        Path.home() / ".openclaw" / "skills" / "xiaohongshu" / "scripts" / "draft.sh",
        Path.home() / ".config" / "mmp" / "skills" / "xiaohongshu" / "scripts" / "draft.sh",
    ]
    return next((c for c in candidates if c.exists()), None)


def _build_xhs_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Reshape mmp's payload.json into the JSON draft.sh expects."""
    out: dict[str, Any] = {
        "title": payload.get("title", ""),
        "content": payload.get("caption", "") or payload.get("content", ""),
        "images": list(payload.get("images") or []),
        "tags": list(payload.get("tags") or []),
    }
    video = payload.get("video")
    if video:
        out["video"] = video
    return out


def _invoke_local_draft(payload: dict[str, Any]) -> dict[str, Any]:
    """Call the xiaohongshu skill's draft.sh with a JSON string arg.

    Returns ``{"draft_id": str, "draft_path": str}``.
    """
    script = _locate_draft_sh()
    if script is None:
        raise FileNotFoundError(
            "xiaohongshu draft.sh not found. Set XHS_DRAFT_SH env var or install "
            "the xiaohongshu skill at one of the standard locations."
        )

    xhs_json = json.dumps(_build_xhs_payload(payload), ensure_ascii=False)
    result = subprocess.run(
        [str(script), xhs_json],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"draft.sh failed (exit {result.returncode}): {result.stderr.strip()}")

    # Parse stdout for the draft path line. Format:
    #   ✓ 已创建本地草稿: /path/to/draft.json
    draft_path: str | None = None
    for line in result.stdout.splitlines():
        m = _DRAFT_PATH_RE.search(line)
        if m:
            draft_path = m.group(1).strip()
            break
    if draft_path is None:
        raise RuntimeError(f"draft.sh did not report a draft path. stdout was:\n{result.stdout}")

    # draft_id = the file's basename without extension
    draft_id = Path(draft_path).stem
    return {"draft_id": draft_id, "draft_path": draft_path}


class XiaohongshuProvider(Provider):
    name = "xiaohongshu"
    display_name = "小红书"
    media_types = ["image-post", "video-post"]
    capabilities = {"draft": True, "publish": False, "schedule": False}
    # Local draft path needs no credentials. XHS_COOKIE_PATH listed for v0.3
    # platform-draft / publish flow; not required by current `draft-local`.
    required_credentials: list[CredentialSpec] = []
    platform_rules = XHS_RULES

    def validate(self, manifest: Any, target: Any) -> ValidationResult:
        return ValidationResult(violations=self.platform_rules.lint(manifest, self.name))

    def prepare(self, manifest: Any, target: Any, run_dir: Path) -> PreparedPayload:
        pack_dir = run_dir / "packs" / self.name
        pack_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "title": manifest.title,
            "caption": manifest.body,
            "images": list(manifest.images or []),
            "tags": list(manifest.tags or []),
            "cta": manifest.cta,
            "mode": target.mode,
            "options": dict(target.options or {}),
        }
        payload_path = pack_dir / "payload.json"
        payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        (pack_dir / "content.md").write_text(manifest.body or "", encoding="utf-8")
        return PreparedPayload(pack_dir=pack_dir, payload_path=payload_path)

    def execute(
        self,
        run_dir: Path,
        target: Any,
        mode: str,
        credentials: dict[str, str],
    ) -> ExecutionResult:
        if mode == "publish":
            raise NotImplementedError(
                "xiaohongshu publish path not enabled in v0.2; use mode=draft"
            )
        if mode == "dry-run":
            return ExecutionResult(status="ok", mode_actual="dry-run", external_id=None)

        # mode == draft → invoke local draft.sh, no creds needed
        payload_path = run_dir / "packs" / self.name / "payload.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        try:
            out = _invoke_local_draft(payload)
        except Exception as exc:
            raise ProviderExecutionError(
                target=self.name, step="local_draft", upstream=exc, retryable=True
            ) from exc

        return ExecutionResult(
            status="ok",
            mode_actual="draft-local",
            external_id=out.get("draft_id"),
            extras={"draft_path": out.get("draft_path")},
        )

    def health_check(self, credentials: dict[str, str]) -> HealthStatus:
        # Local draft only needs draft.sh present; no creds.
        return HealthStatus.ok if _locate_draft_sh() is not None else HealthStatus.failed
