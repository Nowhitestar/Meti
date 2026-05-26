"""WeChat 贴图 (image post, ``type=77``) provider — OpenCLI Browser Bridge.

Drives the user's real Chrome (where they're logged into mp.weixin.qq.com)
to create a 贴图 draft. The 贴图 type is web-only — the public Open
Platform API exposes only article (图文) drafts which the
``wechat-article`` provider already covers. See
``docs/wechat-image-tietu-research.md`` for the reverse-engineering
notes that informed this implementation.

Two execute paths:

- **Browser flow** (preferred, v0.3.2+): if the OpenCLI Bridge is
  connected, opens the 贴图 editor on mp.weixin.qq.com, injects each
  image via the ``DataTransfer`` trick, types title + caption, then
  clicks the editor's own "保存为草稿" button. Returns
  ``mode_actual="draft-platform"`` with the numeric ``appmsgid`` as
  ``external_id``.
- **Stub fallback**: if the bridge isn't connected, writes a
  ``TODO-connector.md`` to the pack dir with manual setup steps and
  returns ``mode_actual="stub"``.
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
from providers.wechat_image.rules import WECHAT_IMAGE_RULES


class WeChatImageProvider(Provider):
    name = "wechat-image"
    display_name = "微信贴图"
    media_types = ["image-post"]
    capabilities = {"draft": True, "publish": False, "schedule": False}
    # Browser-flow provider: no API credentials. Auth is via the user's
    # logged-in Chrome session (driven via OpenCLI Browser Bridge).
    required_credentials: list[CredentialSpec] = []
    platform_rules = WECHAT_IMAGE_RULES
    browser_login_url = "https://mp.weixin.qq.com/"

    def validate(self, manifest: Any, target: Any) -> ValidationResult:
        return ValidationResult(violations=self.platform_rules.lint(manifest, self.name))

    def prepare(self, manifest: Any, target: Any, run_dir: Path) -> PreparedPayload:
        pack_dir = run_dir / "packs" / self.name
        pack_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "title": manifest.title,
            "caption": manifest.body,
            "images": list(manifest.images or []),
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
            raise NotImplementedError("wechat-image publish path not enabled in v0.3")
        if mode == "dry-run":
            return ExecutionResult(status="ok", mode_actual="dry-run", external_id=None)

        from core import browser as br

        pack_dir = run_dir / "packs" / self.name
        payload_path = pack_dir / "payload.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))

        if not br.is_connected():
            self._write_stub(pack_dir, reason="bridge-not-connected")
            return ExecutionResult(
                status="failed",
                mode_actual="stub",
                external_id=None,
                error_code="bridge_disconnected",
                error_kind="recoverable",
                recoverable=True,
                manual_recovery="Install/enable OpenCLI Browser Bridge, log in to mp.weixin.qq.com, then run `meti resume <run-dir>`.",
                extras={
                    "connector_status": "bridge-not-connected",
                    "remediation": (
                        "install OpenCLI Chrome extension + open Chrome; "
                        "see docs/browser-connectors.md"
                    ),
                },
            )

        # Auto-open a visible Chrome tab and bind it to bound:meti. This makes
        # the browser-flow visible and removes the manual "meti browser bind"
        # step from normal publish runs.
        br.ensure_bound(
            url="https://mp.weixin.qq.com/",
            domain="mp.weixin.qq.com",
        )

        from providers.wechat_image.internal.browser_flow import create_draft

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
            f"# wechat-image (贴图) browser connector skipped (reason: {reason})\n\n"
            "Payload is ready at `payload.json`. To complete the draft:\n\n"
            "**Option A (recommended): set up the OpenCLI Browser Bridge**\n\n"
            "1. Install Node.js 21+: `brew install node` (macOS)\n"
            "2. Install the Chrome extension:\n"
            "   https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk\n"
            "3. Make sure you're logged in to mp.weixin.qq.com in Chrome\n"
            "4. Verify: `meti browser status`\n"
            "5. Retry: `meti resume <this-run-dir>`\n\n"
            "Setup details: docs/browser-connectors.md\n\n"
            "**Option B: manually create the draft**\n\n"
            "1. Open https://mp.weixin.qq.com/ in your logged-in Chrome\n"
            "2. Top-right → 新的创作 → 贴图\n"
            "3. Upload images from payload.json (in order)\n"
            "4. Paste title from payload.title\n"
            "5. Paste caption from content.md\n"
            "6. 保存为草稿\n",
            encoding="utf-8",
        )
