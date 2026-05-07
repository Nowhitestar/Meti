"""Console entry point for the `meti` command.

Bridges from `pip install`'s `[project.scripts]` to the actual CLI logic
in `scripts/meti.py`. Single-purpose: import + call.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    """Entry point used by [project.scripts]."""
    # Ensure repo root is on sys.path so `scripts/meti.py` can be loaded.
    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root))

    # Import scripts/meti.py via importlib (it's not a regular package member).
    import importlib.util

    cli_path = repo_root / "scripts" / "meti.py"
    spec = importlib.util.spec_from_file_location("_meti_cli", cli_path)
    if not spec or not spec.loader:
        print("ERROR: cannot load scripts/meti.py", file=sys.stderr)
        return 2
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main()


if __name__ == "__main__":
    sys.exit(main())
