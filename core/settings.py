"""Settings persistence at ~/.config/mmp/settings.toml.

Defaults are returned when the file is missing; save() writes back the full
settings object.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    # tomli is only installed on py3.10 (see pyproject.toml conditional dep);
    # mypy on py3.11+ can't resolve the import and we don't want it to.
    import tomli as tomllib  # type: ignore[import-not-found]

import tomli_w

from core import host


@dataclass
class Settings:
    default_mode: str = "draft"
    wizard_enabled: bool = True
    auto_save_manifest: bool = True
    trusted_user_providers: list[str] = field(default_factory=list)


def load() -> Settings:
    p = host.settings_path()
    if not p.exists():
        return Settings()
    with p.open("rb") as f:
        data = tomllib.load(f)
    wiz = data.get("wizard", {})
    providers = data.get("providers", {})
    return Settings(
        default_mode=data.get("default_mode", "draft"),
        wizard_enabled=wiz.get("enabled", True),
        auto_save_manifest=wiz.get("auto_save_manifest", True),
        trusted_user_providers=list(providers.get("trusted_user_providers", [])),
    )


def save(s: Settings) -> Path:
    p = host.settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "default_mode": s.default_mode,
        "wizard": {
            "enabled": s.wizard_enabled,
            "auto_save_manifest": s.auto_save_manifest,
        },
        "providers": {
            "trusted_user_providers": list(s.trusted_user_providers),
        },
    }
    with p.open("wb") as f:
        tomli_w.dump(payload, f)
    return p
