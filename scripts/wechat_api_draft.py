"""DEPRECATED: this CLI moved to `providers/wechat_article/internal/wechat_api.py`.

It remains as a thin wrapper for backward compatibility with v0.1 scripts.
Will be removed in v0.3.
"""

from __future__ import annotations

import sys
import warnings


def main() -> int:
    warnings.warn(
        "scripts/wechat_api_draft.py is deprecated; use `meti publish` or "
        "`providers.wechat_article.internal.wechat_api`",
        DeprecationWarning,
        stacklevel=2,
    )
    print(
        "DEPRECATED. Use `python3 scripts/meti.py publish <manifest>` instead.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
