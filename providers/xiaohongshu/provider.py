"""Xiaohongshu provider — local draft via the xiaohongshu skill's draft.sh.

This v0.2 provider only knows the `draft-local` path (creates a local draft
file, no platform upload). Platform draft and publish are deferred.
"""

from __future__ import annotations

import json
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


def _invoke_local_draft(payload_path: Path, cookie_path: str) -> dict[str, Any]:
    """Call the xiaohongshu skill's draft.sh. Returns parsed JSON output."""
    candidates = [
        Path.home() / ".openclaw" / "skills" / "xiaohongshu" / "scripts" / "draft.sh",
        Path.home() / ".config" / "mmp" / "skills" / "xiaohongshu" / "scripts" / "draft.sh",
    ]
    script = next((c for c in candidates if c.exists()), None)
    if script is None:
        raise FileNotFoundError(
            "xiaohongshu draft.sh not found in expected locations: "
            + ", ".join(str(c) for c in candidates)
        )
    result = subprocess.run(
        [str(script), "--payload", str(payload_path), "--cookie", cookie_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"draft.sh failed: {result.stderr}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"draft_id": f"xhs_local_{abs(hash(result.stdout)) % 10**9}"}


class XiaohongshuProvider(Provider):
    name = "xiaohongshu"
    display_name = "小红书"
    media_types = ["image-post", "video-post"]
    capabilities = {"draft": True, "publish": False, "schedule": False}
    required_credentials = [
        CredentialSpec(
            key="XHS_COOKIE_PATH",
            description="Path to xiaohongshu cookies file",
            secret=False,
            setup_hint="Use xhs-login from the xiaohongshu skill",
        )
    ]
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

        cookie_path = credentials.get("XHS_COOKIE_PATH")
        if not cookie_path:
            raise ProviderExecutionError(
                target=self.name,
                step="auth",
                upstream=ValueError("missing XHS_COOKIE_PATH"),
                retryable=False,
            )

        payload_path = run_dir / "packs" / self.name / "payload.json"
        try:
            out = _invoke_local_draft(payload_path, cookie_path)
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
        cookie_path = credentials.get("XHS_COOKIE_PATH")
        if cookie_path and Path(cookie_path).exists():
            return HealthStatus.ok
        return HealthStatus.failed
