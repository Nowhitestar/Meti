"""WeChat Official Account article provider."""

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
from providers.wechat_article.rules import WECHAT_ARTICLE_RULES


def _markdown_to_html(md: str) -> str:
    """Minimal MD->HTML for WeChat draft API smoke. Not a full renderer."""
    out_lines: list[str] = []
    for line in md.splitlines():
        if line.startswith("# "):
            out_lines.append(f"<h1>{line[2:].strip()}</h1>")
        elif line.startswith("## "):
            out_lines.append(f"<h2>{line[3:].strip()}</h2>")
        elif line.startswith("### "):
            out_lines.append(f"<h3>{line[4:].strip()}</h3>")
        elif not line.strip():
            out_lines.append("")
        else:
            out_lines.append(f"<p>{line}</p>")
    return "\n".join(out_lines)


class WeChatArticleProvider(Provider):
    name = "wechat-article"
    display_name = "微信公众号文章"
    media_types = ["longform"]
    capabilities = {"draft": True, "publish": False, "schedule": False}
    required_credentials = [
        CredentialSpec(
            key="WECHAT_APP_ID",
            description="WeChat Official Account AppID",
            secret=False,
            setup_hint="From mp.weixin.qq.com → 设置与开发 → 基本配置",
        ),
        CredentialSpec(
            key="WECHAT_APP_SECRET",
            description="WeChat Official Account AppSecret",
            secret=True,
            setup_hint="Same page as AppID; reset if forgotten",
        ),
    ]
    platform_rules = WECHAT_ARTICLE_RULES

    def validate(self, manifest: Any, target: Any) -> ValidationResult:
        violations = self.platform_rules.lint(manifest, target_name=self.name)
        return ValidationResult(violations=violations)

    def prepare(self, manifest: Any, target: Any, run_dir: Path) -> PreparedPayload:
        pack_dir = run_dir / "packs" / self.name
        pack_dir.mkdir(parents=True, exist_ok=True)

        digest = (manifest.metadata or {}).get("digest") or (manifest.summary or "")
        body_md = manifest.body or ""
        body_html = _markdown_to_html(body_md)

        payload = {
            "title": manifest.title,
            "content": body_md,
            "html": body_html,
            "digest": digest,
            "tags": list(manifest.tags or []),
            "cover": str(manifest.cover) if manifest.cover else None,
            "mode": target.mode,
            "options": dict(target.options or {}),
        }
        payload_path = pack_dir / "payload.json"
        payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        (pack_dir / "content.md").write_text(body_md, encoding="utf-8")

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
                "wechat-article publish path not enabled in v0.2; use mode=draft"
            )

        if mode == "dry-run":
            return ExecutionResult(status="ok", mode_actual="dry-run", external_id=None)

        # mode == "draft"
        from providers.wechat_article.internal import wechat_api  # local import: optional dep

        payload_path = run_dir / "packs" / self.name / "payload.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))

        app_id = credentials.get("WECHAT_APP_ID")
        app_secret = credentials.get("WECHAT_APP_SECRET")
        if not app_id or not app_secret:
            raise ProviderExecutionError(
                target=self.name,
                step="auth",
                upstream=ValueError("missing WECHAT_APP_ID or WECHAT_APP_SECRET"),
                retryable=False,
            )

        try:
            token = wechat_api.get_access_token(app_id, app_secret)
        except Exception as exc:
            raise ProviderExecutionError(
                target=self.name, step="get_token", upstream=exc, retryable=True
            ) from exc

        try:
            thumb_media_id = wechat_api.upload_thumb(token, Path(payload["cover"]))
        except Exception as exc:
            raise ProviderExecutionError(
                target=self.name, step="upload_thumb", upstream=exc, retryable=True
            ) from exc

        article = {
            "title": payload["title"],
            "thumb_media_id": thumb_media_id,
            "content": payload["html"],
            "digest": payload["digest"],
            "show_cover_pic": 1,
            "need_open_comment": 0,
            "only_fans_can_comment": 0,
        }

        try:
            draft_id = wechat_api.add_draft(token, [article])
        except Exception as exc:
            raise ProviderExecutionError(
                target=self.name, step="add_draft", upstream=exc, retryable=True
            ) from exc

        return ExecutionResult(
            status="ok",
            mode_actual="draft-platform",
            external_id=draft_id,
            extras={"thumb_media_id": thumb_media_id},
        )

    def health_check(self, credentials: dict[str, str]) -> HealthStatus:
        from providers.wechat_article.internal import wechat_api

        app_id = credentials.get("WECHAT_APP_ID")
        app_secret = credentials.get("WECHAT_APP_SECRET")
        if not (app_id and app_secret):
            return HealthStatus.failed
        try:
            wechat_api.get_access_token(app_id, app_secret)
            return HealthStatus.ok
        except Exception:
            return HealthStatus.failed
