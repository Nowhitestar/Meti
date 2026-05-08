"""Platform rules for X (Twitter) threads.

Thread body convention: tweets are separated by a line containing only
``---`` (CommonMark hr). Leading/trailing whitespace per tweet is stripped;
empty segments are dropped. The same parser is used by ``provider.prepare``
and the lint extra below so they can't drift.

Hard caps used here:
- per-tweet length: 280 chars (free / non-Premium baseline; meti targets
  the strictest tier so threads still post for everyone)
- thread length: 25 tweets (X's compose UI caps thread length around here;
  longer threads are usually a sign the content should be a longform article)
- minimum thread length: 1 tweet (zero is a manifest error caught upstream,
  but we surface a clearer message)
"""

from __future__ import annotations

import re
from typing import Any

from core.rules import PlatformRules, Severity, Violation

TWEET_MAX = 280
THREAD_MAX = 25
THREAD_MIN = 1

# Splits on a line that is exactly `---` (optionally surrounded by
# whitespace). DOTALL not needed — we operate on the body text directly.
_SEPARATOR_RE = re.compile(r"(?m)^\s*---\s*$")


def split_thread(body: str) -> list[str]:
    """Split a thread body into tweets.

    Convention: tweets are separated by a line containing only ``---``.
    Whitespace around each tweet is stripped; empty segments are filtered
    out so trailing separators don't introduce blank tweets.
    """
    if not body:
        return []
    parts = _SEPARATOR_RE.split(body)
    return [p.strip() for p in parts if p and p.strip()]


def _thread_lint(manifest: Any, target_name: str) -> list[Violation]:
    body = getattr(manifest, "body", "") or ""
    tweets = split_thread(body)

    violations: list[Violation] = []

    if len(tweets) < THREAD_MIN:
        violations.append(
            Violation(
                code="THREAD_EMPTY",
                message="thread body must contain at least one tweet (separate with `---`)",
                target=target_name,
                field_path="body",
            )
        )
    if len(tweets) > THREAD_MAX:
        violations.append(
            Violation(
                code="THREAD_TOO_LONG",
                message=f"thread has {len(tweets)} tweets; max {THREAD_MAX}",
                target=target_name,
                field_path="body",
            )
        )

    for idx, tweet in enumerate(tweets):
        if len(tweet) > TWEET_MAX:
            violations.append(
                Violation(
                    code="TWEET_TOO_LONG",
                    message=(
                        f"tweet #{idx + 1} length {len(tweet)} exceeds {TWEET_MAX} "
                        "(non-Premium cap)"
                    ),
                    severity=Severity.error,
                    target=target_name,
                    field_path=f"body[{idx}]",
                )
            )

    return violations


X_THREAD_RULES = PlatformRules(
    extra_lints=[_thread_lint],
)
