"""DEPRECATED in v0.2. Use `mmp publish <manifest>`.

Logic moved to providers/wechat_article/, providers/x_article/, providers/substack/.
This shim will be removed in v0.3.
"""

from __future__ import annotations

import sys
import warnings


def main() -> int:
    warnings.warn(
        "prepare_longform.py is deprecated; use `python3 scripts/mmp.py publish <manifest>`",
        DeprecationWarning,
        stacklevel=2,
    )
    print(
        "DEPRECATED. Run `python3 scripts/mmp.py publish <manifest>` instead.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
