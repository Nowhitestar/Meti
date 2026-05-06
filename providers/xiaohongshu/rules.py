"""Platform rules for Xiaohongshu image posts.

Sources (current MCP docs):
- title <= 20 chars
- body (caption) <= 1000 chars
- images 1..9
- tags max 10 (soft warning above)
"""

from __future__ import annotations

from core.rules import PlatformRules

XHS_RULES = PlatformRules(
    title_max=20,
    body_max=1000,
    image_count_min=1,
    image_count_max=9,
    tag_max=10,
)
