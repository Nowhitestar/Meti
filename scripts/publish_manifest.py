"""DEPRECATED in v0.2. Use `mmp validate <manifest>`.

Logic moved to core/manifest.py + core/cli.py validate command.
This shim will be removed in v0.3.
"""

from __future__ import annotations

import sys
import warnings


def main() -> int:
    warnings.warn(
        "publish_manifest.py is deprecated; use `python3 scripts/mmp.py validate <manifest>`",
        DeprecationWarning,
        stacklevel=2,
    )
    print(
        "DEPRECATED. Run `python3 scripts/mmp.py validate <manifest>` instead.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
