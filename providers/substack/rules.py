"""Platform rules for Substack posts.

- title <=100 chars practical
- subtitle <=200 chars
- body <=50000 chars
- cover optional
"""

from __future__ import annotations

from core.rules import PlatformRules, Severity, Violation


def _subtitle_lint(manifest, target_name: str) -> list[Violation]:
    subtitle = (manifest.metadata or {}).get("subtitle") or ""
    if subtitle and len(subtitle) > 200:
        return [
            Violation(
                code="SUBSTACK_SUBTITLE_TOO_LONG",
                message=f"subtitle length {len(subtitle)} exceeds 200",
                target=target_name,
                field_path="metadata.subtitle",
                severity=Severity.warning,
            )
        ]
    return []


SUBSTACK_RULES = PlatformRules(
    title_max=100,
    body_max=50000,
    extra_lints=[_subtitle_lint],
)
