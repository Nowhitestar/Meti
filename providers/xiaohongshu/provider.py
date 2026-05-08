"""Xiaohongshu provider — drives Creator Studio via OpenCLI Browser Bridge.

v0.4.1+ replaces the older local-JSON ``draft.sh`` path because XHS's
draft data is anchored to the user's actual browser session — meti has
to drive that session for the draft to be reachable later. See
``docs/browser-connectors.md`` for setup.

Flow:
- ``meti browser bind`` (one-time, points meti at your Chrome tab)
- ``meti publish ...`` — for the xiaohongshu target, meti navigates the
  bound tab to ``creator.xiaohongshu.com/publish/publish?target=image``,
  injects images via ``DataTransfer``, types title + caption, clicks
  存草稿. The draft lands in your XHS account's 草稿箱 (server-side).

Stub fallback: if the bridge isn't connected, the provider writes a
``TODO-connector.md`` and returns ``mode_actual="stub"``. The previous
``draft.sh`` local-JSON path is removed.
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
from providers.xiaohongshu.rules import XHS_RULES


class XiaohongshuProvider(Provider):
    name = "xiaohongshu"
    display_name = "小红书"
    media_types = ["image-post", "video-post"]
    capabilities = {"draft": True, "publish": False, "schedule": False}
    # Browser-flow provider: no API credentials. Auth via the user's
    # logged-in Chrome session (driven via OpenCLI Browser Bridge).
    required_credentials: list[CredentialSpec] = []
    platform_rules = XHS_RULES
    browser_login_url = "https://creator.xiaohongshu.com/login"

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
            raise NotImplementedError("xiaohongshu publish path not enabled in v0.4")
        if mode == "dry-run":
            return ExecutionResult(status="ok", mode_actual="dry-run", external_id=None)

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
                    "remediation": (
                        "Install OpenCLI Chrome extension + run `meti browser bind`; "
                        "see docs/browser-connectors.md"
                    ),
                },
            )
        if not br.is_bound():
            self._write_stub(pack_dir, reason="bridge-not-bound")
            return ExecutionResult(
                status="ok",
                mode_actual="stub",
                external_id=None,
                extras={
                    "connector_status": "bridge-not-bound",
                    "remediation": (
                        "Run `meti browser bind` from a Chrome tab you want meti "
                        "to drive, then re-run publish."
                    ),
                },
            )

        from providers.xiaohongshu.internal.browser_flow import create_draft

        try:
            result = create_draft(payload)
        except br.BrowserNotBoundError as exc:
            self._write_stub(pack_dir, reason="bridge-not-bound")
            raise ProviderExecutionError(
                target=self.name,
                step="browser_bridge",
                upstream=exc,
                retryable=True,
            ) from exc
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
            f"# xiaohongshu browser connector skipped (reason: {reason})\n\n"
            "Payload is ready at `payload.json`. To complete the draft:\n\n"
            "**Option A (recommended): set up the OpenCLI Browser Bridge**\n\n"
            "1. Install Node.js 21+: `brew install node` (macOS)\n"
            "2. Install the Chrome extension:\n"
            "   https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk\n"
            "3. Make sure you're logged in to creator.xiaohongshu.com in Chrome\n"
            "4. Open Chrome to a regular tab, then run: `meti browser bind`\n"
            "5. Retry: `meti resume <this-run-dir>`\n\n"
            "Setup details: docs/browser-connectors.md\n\n"
            "**Option B: manually create the draft**\n\n"
            "1. Open https://creator.xiaohongshu.com/publish/publish?target=image\n"
            "2. Upload images from `payload.json`'s `images[]`\n"
            "3. Paste title from `payload.title`\n"
            "4. Paste caption from `content.md`\n"
            "5. Click 存草稿\n",
            encoding="utf-8",
        )
