"""Substack provider — payload-only stub.

A real connector (substack-autopilot or generic browser) is not shipped in
v0.2. Behavior parallels x_article: payload + TODO marker + dry-run-like
result.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.provider import (
    CredentialSpec,
    ExecutionResult,
    HealthStatus,
    PreparedPayload,
    Provider,
    ValidationResult,
)
from providers.substack.rules import SUBSTACK_RULES


class SubstackProvider(Provider):
    name = "substack"
    display_name = "Substack"
    media_types = ["longform"]
    capabilities = {"draft": True, "publish": False, "schedule": False}
    required_credentials = [
        CredentialSpec(
            key="SUBSTACK_SESSION_COOKIE",
            description="Substack session cookie",
            secret=True,
        )
    ]
    platform_rules = SUBSTACK_RULES

    def validate(self, manifest: Any, target: Any) -> ValidationResult:
        return ValidationResult(violations=self.platform_rules.lint(manifest, self.name))

    def prepare(self, manifest: Any, target: Any, run_dir: Path) -> PreparedPayload:
        pack_dir = run_dir / "packs" / self.name
        pack_dir.mkdir(parents=True, exist_ok=True)
        meta = manifest.metadata or {}
        payload = {
            "title": manifest.title,
            "subtitle": meta.get("subtitle"),
            "body": manifest.body,
            "cover": manifest.cover,
            "tags": list(manifest.tags or []),
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
            raise NotImplementedError("substack publish path not enabled in v0.2")
        if mode == "dry-run":
            return ExecutionResult(status="ok", mode_actual="dry-run", external_id=None)

        pack_dir = run_dir / "packs" / self.name
        (pack_dir / "TODO-connector.md").write_text(
            "# substack connector not implemented in v0.2\n\n"
            "Payload is ready at `payload.json`. To complete:\n"
            "1. Open https://substack.com/dashboard in a logged-in browser\n"
            "2. Click 'New post'\n"
            "3. Paste title and subtitle from payload\n"
            "4. Paste body from content.md\n"
            "5. Set cover from payload.cover (if present)\n"
            "6. Save Draft\n",
            encoding="utf-8",
        )
        return ExecutionResult(
            status="ok",
            mode_actual="dry-run",
            external_id=None,
            extras={"connector_status": "not-implemented"},
        )

    def health_check(self, credentials: dict[str, str]) -> HealthStatus:
        return HealthStatus.unknown
