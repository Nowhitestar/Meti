"""DEPRECATED in v0.2. Use `mmp publish <manifest> --mode-override draft`.

Logic moved to providers/xiaohongshu/ and providers/wechat_image/.
This shim will be removed in v0.3.
"""

from __future__ import annotations

import sys
import warnings


def main() -> int:
    warnings.warn(
        "execute_image_post.py is deprecated; use "
        "`python3 scripts/mmp.py publish <manifest> --mode-override draft`",
        DeprecationWarning,
        stacklevel=2,
    )
    print(
        "DEPRECATED. Run `python3 scripts/mmp.py publish <manifest> --mode-override draft` instead.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
