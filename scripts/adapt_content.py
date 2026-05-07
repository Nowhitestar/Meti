"""DEPRECATED in v0.2. Use `meti publish <manifest>`.

Logic moved into core/runner.py + per-provider rules.
This shim will be removed in v0.3.
"""

from __future__ import annotations

import sys
import warnings


def main() -> int:
    warnings.warn(
        "adapt_content.py is deprecated; use `python3 scripts/meti.py publish <manifest>`",
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
