"""Platform rules for X Articles.

Approximate (X Articles are evolving):
- title <=70 chars practical
- body <=25000 chars
- cover optional
"""

from __future__ import annotations

from core.rules import PlatformRules

X_ARTICLE_RULES = PlatformRules(
    title_max=70,
    body_max=25000,
)
