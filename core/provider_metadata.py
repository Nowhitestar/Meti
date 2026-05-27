"""Static provider manifest discovery.

This module parses ``provider.yaml`` files without importing provider Python.
Use it for trust decisions, listings, and metadata checks that must be safe for
untrusted user-provider directories.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REQUIRED_MANIFEST_KEYS = (
    "name",
    "display_name",
    "media_types",
    "capabilities",
    "required_credentials",
    "entry",
    "schema_version",
)


@dataclass(frozen=True)
class ProviderManifest:
    name: str
    display_name: str
    media_types: list[str]
    capabilities: dict[str, bool]
    required_credentials: list[dict[str, Any]]
    entry: str
    schema_version: int
    path: Path
    source: str

    @property
    def module_name(self) -> str:
        return self.entry.split(":", 1)[0]

    @property
    def class_name(self) -> str:
        return self.entry.split(":", 1)[1]


def load_provider_manifest(provider_dir: Path, source: str) -> ProviderManifest:
    """Load provider.yaml from a provider directory without importing provider code."""

    manifest_path = provider_dir / "provider.yaml"
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{manifest_path}: provider.yaml must be a mapping")

    missing = [key for key in REQUIRED_MANIFEST_KEYS if key not in raw]
    if missing:
        raise ValueError(f"{manifest_path}: missing required key {missing[0]}")

    entry = str(raw["entry"])
    if ":" not in entry:
        raise ValueError(f"{manifest_path}: entry must use module:ClassName")

    return ProviderManifest(
        name=str(raw["name"]),
        display_name=str(raw["display_name"]),
        media_types=list(raw["media_types"] or []),
        capabilities=dict(raw["capabilities"] or {}),
        required_credentials=list(raw["required_credentials"] or []),
        entry=entry,
        schema_version=int(raw["schema_version"]),
        path=provider_dir,
        source=source,
    )


def discover_provider_manifests(root: Path, source: str) -> list[ProviderManifest]:
    """Return static manifests under root sorted by provider directory name."""

    if not root.exists():
        return []
    manifests: list[ProviderManifest] = []
    for provider_dir in sorted(root.iterdir()):
        if provider_dir.is_dir() and (provider_dir / "provider.yaml").exists():
            manifests.append(load_provider_manifest(provider_dir, source=source))
    return manifests
