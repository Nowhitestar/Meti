"""DEPRECATED in v0.2. Use `meti publish <manifest>`.

Logic moved to providers/xiaohongshu/ and providers/wechat_image/.
This shim will be removed in v0.3.
"""

from __future__ import annotations

import sys
import warnings


def main() -> int:
    warnings.warn(
        "prepare_image_post.py is deprecated; use `python3 scripts/meti.py publish <manifest>`",
        DeprecationWarning,
        stacklevel=2,
    )
    print(
        "DEPRECATED. Run `python3 scripts/meti.py publish <manifest>` instead.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
