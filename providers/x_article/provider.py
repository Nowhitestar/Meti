"""X Articles provider.

Two execute paths:
- **Browser flow** (preferred, v0.3.1+): if Playwright is installed AND a
  saved browser session exists (run ``meti browser login x-article`` once),
  drives Chromium to create a real draft on x.com/i/articles. Returns
  ``mode_actual="draft-platform"`` with the article ID as ``external_id``.
- **Stub fallback**: if either prerequisite is missing, writes a
  ``TODO-connector.md`` to the pack dir and returns ``mode_actual="stub"``.
  Multi-target manifests still progress; the user is prompted to either
  install the browser extra or follow the manual steps.
"""

from __future__ import annotations

import json
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
from providers.x_article.rules import X_ARTICLE_RULES


class XArticleProvider(Provider):
    name = "x-article"
    display_name = "X Articles"
    media_types = ["longform"]
    capabilities = {"draft": True, "publish": False, "schedule": False}
    # Browser-flow provider: no API credentials. Auth is via saved
    # browser state captured by `meti browser login x-article`.
    required_credentials: list[CredentialSpec] = []
    platform_rules = X_ARTICLE_RULES
    browser_login_url = "https://x.com/i/flow/login"

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
            raise NotImplementedError("x-article publish path not enabled in v0.3")
        if mode == "dry-run":
            return ExecutionResult(status="ok", mode_actual="dry-run", external_id=None)

        # mode == draft. Try OpenCLI-driven browser flow; fall back to stub
        # if the bridge isn't connected (extension missing, Chrome not running).
        from core import browser as br

        pack_dir = run_dir / "packs" / self.name
        payload_path = pack_dir / "payload.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))

        if not br.is_connected():
            self._write_stub(pack_dir, reason="bridge-not-connected")
            return ExecutionResult(
                status="ok",
                mode_actual="stub",
                external_id=None,
                extras={
                    "connector_status": "bridge-not-connected",
                    "remediation": "install OpenCLI Chrome extension + open Chrome; "
                    "see docs/browser-connectors.md",
                },
            )

        from providers.x_article.internal.browser_flow import create_draft

        try:
            result = create_draft(payload)
        except br.BrowserNotConnectedError as exc:
            self._write_stub(pack_dir, reason="bridge-not-connected")
            raise ProviderExecutionError(
                target=self.name,
                step="browser_bridge",
                upstream=exc,
                retryable=True,
            ) from exc
        except br.BrowserNotInstalledError as exc:
            self._write_stub(pack_dir, reason="opencli-not-installed")
            raise ProviderExecutionError(
                target=self.name,
                step="browser_bridge",
                upstream=exc,
                retryable=False,
            ) from exc
        except Exception as exc:
            raise ProviderExecutionError(
                target=self.name,
                step="browser_draft",
                upstream=exc,
                retryable=True,
            ) from exc

        return ExecutionResult(
            status="ok",
            mode_actual="draft-platform",
            external_id=result.get("external_id"),
            draft_url=result.get("draft_url"),
            extras={"connector_status": "browser-ok"},
        )

    def health_check(self, credentials: dict[str, str]) -> HealthStatus:
        from core import browser as br

        return HealthStatus.ok if br.is_connected() else HealthStatus.failed

    @staticmethod
    def _write_stub(pack_dir: Path, *, reason: str) -> None:
        (pack_dir / "TODO-connector.md").write_text(
            f"# x-article browser connector skipped (reason: {reason})\n\n"
            "Payload is ready at `payload.json`. To complete the draft:\n\n"
            "**Option A (recommended): set up the OpenCLI Browser Bridge**\n\n"
            "1. Install Node.js 21+: `brew install node` (macOS)\n"
            "2. Install the Chrome extension:\n"
            "   https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk\n"
            "3. Make sure you're logged in to X in Chrome\n"
            "4. Verify: `meti browser status`\n"
            "5. Retry: `meti resume <this-run-dir>`\n\n"
            "Setup details: docs/browser-connectors.md\n\n"
            "**Option B: manually create the draft**\n\n"
            "1. Open https://x.com/i/articles/compose in a logged-in browser\n"
            "2. Paste title from payload.title\n"
            "3. Paste body from content.md\n"
            "4. Set cover from payload.cover (if present)\n"
            "5. Save Draft\n",
            encoding="utf-8",
        )
