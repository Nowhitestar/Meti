"""Platform rules for WeChat Official Account articles.

Sources:
- 微信公众号文章正文长度上限 ~20000 中文字符
- 标题最多 64 字符
- 摘要最多 120 字符
- 必须有封面图（thumb_media_id）
"""

from __future__ import annotations

from core.rules import PlatformRules, Severity, Violation


def _digest_lint(manifest, target_name: str) -> list[Violation]:
    digest = (manifest.metadata or {}).get("digest") or (manifest.summary or "")
    if digest and len(digest) > 120:
        return [
            Violation(
                code="WECHAT_DIGEST_TOO_LONG",
                message=f"digest length {len(digest)} exceeds 120 chars",
                target=target_name,
                field_path="metadata.digest",
                severity=Severity.warning,
            )
        ]
    return []


def _cover_lint(manifest, target_name: str) -> list[Violation]:
    if not getattr(manifest, "cover", None):
        return [
            Violation(
                code="WECHAT_COVER_REQUIRED",
                message="WeChat article requires a cover image (assets.cover)",
                target=target_name,
                field_path="assets.cover",
                severity=Severity.error,
            )
        ]
    return []


WECHAT_ARTICLE_RULES = PlatformRules(
    title_max=64,
    body_max=20000,
    cover_required=True,
    extra_lints=[_digest_lint, _cover_lint],
)
