"""Platform rules for WeChat image posts (图文内容, not OA articles).

Approximate limits (refine when browser flow lands):
- title up to ~64 chars
- caption up to ~600 chars
- images 1..9
"""

from __future__ import annotations

from core.rules import PlatformRules

WECHAT_IMAGE_RULES = PlatformRules(
    title_max=64,
    body_max=600,
    image_count_min=1,
    image_count_max=9,
)
