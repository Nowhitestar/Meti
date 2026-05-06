"""X Articles provider — payload-only stub.

A real connector (likely the `x-articles` skill or browser automation) is not
shipped in v0.2. `execute` writes a TODO marker into the run dir and returns
mode_actual=dry-run, so multi-target manifests can still progress past this
target without failing the run.
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
from providers.x_article.rules import X_ARTICLE_RULES


class XArticleProvider(Provider):
    name = "x-article"
    display_name = "X Articles"
    media_types = ["longform"]
    capabilities = {"draft": True, "publish": False, "schedule": False}
    required_credentials = [
        CredentialSpec(
            key="X_AUTH_TOKEN",
            description="X (Twitter) auth token",
            secret=True,
        )
    ]
    platform_rules = X_ARTICLE_RULES

    def validate(self, manifest: Any, target: Any) -> ValidationResult:
        return ValidationResult(violations=self.platform_rules.lint(manifest, self.name))

    def prepare(self, manifest: Any, target: Any, run_dir: Path) -> PreparedPayload:
        pack_dir = run_dir / "packs" / self.name
        pack_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "title": manifest.title,
            "body": manifest.body,
            "summary": manifest.summary,
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
            raise NotImplementedError("x-article publish path not enabled in v0.2")
        if mode == "dry-run":
            return ExecutionResult(status="ok", mode_actual="dry-run", external_id=None)

        # mode == draft, no real connector yet
        pack_dir = run_dir / "packs" / self.name
        (pack_dir / "TODO-connector.md").write_text(
            "# x-article connector not implemented in v0.2\n\n"
            "Payload is ready at `payload.json`. To complete the draft:\n"
            "1. Open https://x.com/i/articles/compose in a logged-in browser\n"
            "2. Paste title from payload.title\n"
            "3. Paste body from content.md\n"
            "4. Set cover from payload.cover (if present)\n"
            "5. Save Draft\n",
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
