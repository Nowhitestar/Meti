"""Substack provider — OpenCLI Browser Bridge connector.

Drives the user's real Chrome (where they're logged into Substack) to
create a post draft on their publication. See
``docs/browser-connectors.md`` for setup.

Two execute paths:
- **Browser flow** (preferred, v0.3.2+): if the OpenCLI Bridge is
  connected, navigates to ``<publication>.substack.com/publish/post``
  and saves a draft via Substack's autosave-on-type. Returns
  ``mode_actual="draft-platform"`` with the numeric draft ID as
  ``external_id``.
- **Stub fallback**: if the bridge isn't connected, writes a
  ``TODO-connector.md`` to the pack dir with manual steps and
  returns ``mode_actual="stub"``.

Publication URL discovery (in priority order):
1. Manifest target's ``options.publication_url``
2. ``SUBSTACK_PUBLICATION_URL`` env var
3. Stub mode with hint
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core.errors import ProviderExecutionError
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
    # Browser-flow provider: no API credentials. Auth is via the user's
    # logged-in Chrome session (driven via OpenCLI Browser Bridge).
    required_credentials: list[CredentialSpec] = []
    platform_rules = SUBSTACK_RULES
    browser_login_url = "https://substack.com/sign-in"

    def validate(self, manifest: Any, target: Any) -> ValidationResult:
        return ValidationResult(violations=self.platform_rules.lint(manifest, self.name))

    def prepare(self, manifest: Any, target: Any, run_dir: Path) -> PreparedPayload:
        pack_dir = run_dir / "packs" / self.name
        pack_dir.mkdir(parents=True, exist_ok=True)
        meta = manifest.metadata or {}
        payload = {
            "title": manifest.title,
            "subtitle": meta.get("subtitle") or manifest.summary,
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
            raise NotImplementedError("substack publish path not enabled in v0.3")
        if mode == "dry-run":
            return ExecutionResult(status="ok", mode_actual="dry-run", external_id=None)

        from core import browser as br

        pack_dir = run_dir / "packs" / self.name
        payload_path = pack_dir / "payload.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))

        # Resolve publication URL.
        publication_url = (
            (target.options or {}).get("publication_url")
            or os.environ.get("SUBSTACK_PUBLICATION_URL")
            or ""
        ).strip()

        if not publication_url:
            self._write_stub(pack_dir, reason="missing-publication-url")
            return ExecutionResult(
                status="ok",
                mode_actual="stub",
                external_id=None,
                extras={
                    "connector_status": "missing-publication-url",
                    "remediation": (
                        "Set the publication URL via manifest "
                        "`targets.options.publication_url: https://<you>.substack.com` "
                        "or env var `SUBSTACK_PUBLICATION_URL`."
                    ),
                },
            )

        bind_domain = urlparse(publication_url).netloc or None
        try:
            bound = br.ensure_bound(publication_url, domain=bind_domain)
            if bound is False:
                raise br.BrowserNotConnectedError("browser not connected")
        except br.BrowserNotConnectedError:
            self._write_stub(pack_dir, reason="bridge-not-connected")
            return ExecutionResult(
                status="ok",
                mode_actual="stub",
                external_id=None,
                extras={
                    "connector_status": "bridge-not-connected",
                    "remediation": (
                        "install OpenCLI Chrome extension + open Chrome; "
                        "see docs/browser-connectors.md"
                    ),
                },
            )
        except br.BrowserNotInstalledError as exc:
            self._write_stub(pack_dir, reason="opencli-not-installed")
            raise ProviderExecutionError(
                target=self.name,
                step="browser_bridge",
                upstream=exc,
                retryable=False,
            ) from exc

        from providers.substack.internal.browser_flow import create_draft

        try:
            result = create_draft(payload, publication_url=publication_url)
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
            f"# substack browser connector skipped (reason: {reason})\n\n"
            "Payload is ready at `payload.json`. To complete the draft:\n\n"
            "**Option A (recommended): set up the OpenCLI Browser Bridge**\n\n"
            "1. Install Node.js 21+: `brew install node` (macOS)\n"
            "2. Install the Chrome extension:\n"
            "   https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk\n"
            "3. Make sure you're logged in to Substack in Chrome\n"
            "4. Set publication URL — pick one:\n"
            "   - Add to manifest: `targets[i].options.publication_url: https://<you>.substack.com`\n"
            "   - Or env var: `export SUBSTACK_PUBLICATION_URL=https://<you>.substack.com`\n"
            "5. Verify: `meti browser status`\n"
            "6. Retry: `meti resume <this-run-dir>`\n\n"
            "Setup details: docs/browser-connectors.md\n\n"
            "**Option B: manually create the draft**\n\n"
            "1. Open https://<your-publication>.substack.com/publish/post in a logged-in browser\n"
            "2. Paste title from payload.title\n"
            "3. Paste subtitle from payload.subtitle (optional)\n"
            "4. Paste body from content.md\n"
            "5. Substack auto-saves; close the tab when done\n",
            encoding="utf-8",
        )
