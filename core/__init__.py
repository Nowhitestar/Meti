"""meti core package.

Single source of truth for the package version: pulled from
``pyproject.toml`` via ``importlib.metadata`` at runtime so we never
need to update version strings in two places.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("meti")
except PackageNotFoundError:
    # Editable / dev tree without `pip install -e .` run yet.
    __version__ = "0.0.0+local"

__all__ = ["__version__"]
