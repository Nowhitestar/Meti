"""X Thread provider — drives x.com/compose/post via OpenCLI Browser Bridge.

Two execute paths (mirrors x-article's contract):

- **Browser flow**: when the bridge is connected, drives the bound Chrome
  workspace to open X's thread composer, fills each tweet in order, and
  *stops before clicking "Post all"* — the user reviews and ships from
  their own browser. Returns ``mode_actual="draft-platform"``.
- **Stub fallback**: if the bridge isn't connected, writes a
  ``TODO-connector.md`` next to the prepared payload and returns
  ``mode_actual="stub"``. Multi-target manifests still progress.

X has no first-class "thread draft" — leaving the modal mid-compose is the
closest analogue, and matches what x-article does with article autosave.
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
from providers.x_thread.rules import X_THREAD_RULES, split_thread


class XThreadProvider(Provider):
    name = "x-thread"
    display_name = "X Thread"
    media_types = ["thread"]
    capabilities = {"draft": True, "publish": False, "schedule": False}
    # Browser-flow provider: no API credentials. Auth is via the user's
    # logged-in Chrome session (driven via OpenCLI Browser Bridge).
    required_credentials: list[CredentialSpec] = []
    platform_rules = X_THREAD_RULES
    browser_login_url = "https://x.com/i/flow/login"

    def validate(self, manifest: Any, target: Any) -> ValidationResult:
        return ValidationResult(violations=self.platform_rules.lint(manifest, self.name))

    def prepare(self, manifest: Any, target: Any, run_dir: Path) -> PreparedPayload:
        pack_dir = run_dir / "packs" / self.name
        pack_dir.mkdir(parents=True, exist_ok=True)
        tweets = split_thread(manifest.body or "")
        payload = {
            "tweets": tweets,
            "mode": target.mode,
            "options": dict(target.options or {}),
        }
        payload_path = pack_dir / "payload.json"
        payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        (pack_dir / "thread.md").write_text(manifest.body or "", encoding="utf-8")
        return PreparedPayload(pack_dir=pack_dir, payload_path=payload_path)

    def execute(
        self,
        run_dir: Path,
        target: Any,
        mode: str,
        credentials: dict[str, str],
    ) -> ExecutionResult:
        if mode == "publish":
            raise NotImplementedError("x-thread publish path not enabled")
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
                        "Install OpenCLI Chrome extension + open Chrome; "
                        "see docs/browser-connectors.md"
                    ),
                },
            )

        from providers.x_thread.internal.browser_flow import compose_thread

        try:
            result = compose_thread(payload)
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
                step="browser_compose",
                upstream=exc,
                retryable=True,
            ) from exc

        return ExecutionResult(
            status="ok",
            mode_actual="draft-platform",
            external_id=result.get("external_id"),
            draft_url=result.get("draft_url"),
            extras={
                "connector_status": "browser-ok",
                "tweet_count": len(payload.get("tweets") or []),
            },
        )

    def health_check(self, credentials: dict[str, str]) -> HealthStatus:
        from core import browser as br

        return HealthStatus.ok if br.is_connected() else HealthStatus.failed

    @staticmethod
    def _write_stub(pack_dir: Path, *, reason: str) -> None:
        (pack_dir / "TODO-connector.md").write_text(
            f"# x-thread browser connector skipped (reason: {reason})\n\n"
            "Tweets are ready at `payload.json` (field `tweets[]`) and the\n"
            "raw separator-delimited source is at `thread.md`.\n\n"
            "**Option A (recommended): set up the OpenCLI Browser Bridge**\n\n"
            "1. Install Node.js 21+: `brew install node` (macOS)\n"
            "2. Install the Chrome extension:\n"
            "   https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk\n"
            "3. Make sure you're logged in to X in Chrome\n"
            "4. Open Chrome to a regular tab, then run: `meti browser bind`\n"
            "5. Retry: `meti resume <this-run-dir>`\n\n"
            "Setup details: docs/browser-connectors.md\n\n"
            "**Option B: post the thread manually**\n\n"
            "1. Open https://x.com/compose/post in a logged-in browser\n"
            "2. Paste tweet #1 from `payload.tweets[0]`\n"
            "3. Click the `+` (Add post) button under the composer to add\n"
            "   each subsequent tweet\n"
            "4. Repeat for each entry in `payload.tweets[]`\n"
            "5. Review the whole thread, then click **Post all** yourself\n",
            encoding="utf-8",
        )
