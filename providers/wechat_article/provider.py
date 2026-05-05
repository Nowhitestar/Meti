"""WeChat Official Account article provider."""

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
        payload_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (pack_dir / "content.md").write_text(body_md, encoding="utf-8")

        return PreparedPayload(pack_dir=pack_dir, payload_path=payload_path)

    def execute(
        self,
        run_dir: Path,
        target: Any,
        mode: str,
        credentials: dict[str, str],
    ) -> ExecutionResult:
        # Implemented in next task
        raise NotImplementedError("Task 13")

    def health_check(self, credentials: dict[str, str]) -> HealthStatus:
        # Implemented in next task
        return HealthStatus.unknown
