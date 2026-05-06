"""Provider abstract base class + registry.

Discovery rules:
  - bundled_dir: scan <bundled_dir>/*/provider.yaml
  - user_dir:    scan <user_dir>/*/provider.yaml
  - User provider with same `name` overrides bundled, but only when
    discover(trust_user=True) — otherwise warn and skip.

Two names per provider:
  - directory name: snake_case (Python module path)
  - provider.yaml `name`: kebab-case (manifest target name)
"""

from __future__ import annotations

import importlib.util
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from core.errors import ProviderNotFoundError
from core.rules import PlatformRules, Violation


class HealthStatus(str, Enum):
    ok = "ok"
    failed = "failed"
    unknown = "unknown"


@dataclass
class CredentialSpec:
    key: str
    description: str = ""
    secret: bool = True
    setup_hint: str = ""


@dataclass
class ValidationResult:
    violations: list[Violation] = field(default_factory=list)


@dataclass
class PreparedPayload:
    pack_dir: Path
    payload_path: Path
    extras: dict[str, Path] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    status: str  # "ok" | "failed" | "skipped" | "partial"
    mode_actual: str  # "dry-run" | "stub" | "draft-local" | "draft-platform" | "published"
    external_id: str | None = None
    draft_url: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderInfo:
    name: str
    display_name: str
    media_types: list[str]
    capabilities: dict[str, bool]
    required_credentials: list[CredentialSpec]
    source: str  # "bundled" | "user"


class Provider(ABC):
    name: str
    display_name: str
    media_types: list[str]
    capabilities: dict[str, bool]
    required_credentials: list[CredentialSpec]
    platform_rules: PlatformRules

    # Optional. Set this on providers that authenticate via a browser session
    # (saved cookies/storage). When set, `mmp browser login <name>` will open
    # this URL in a headed browser and save state via core.browser.
    # Example: "https://x.com/i/flow/login"
    browser_login_url: str | None = None

    @abstractmethod
    def validate(self, manifest: Any, target: Any) -> ValidationResult | None: ...

    @abstractmethod
    def prepare(self, manifest: Any, target: Any, run_dir: Path) -> PreparedPayload | None: ...

    @abstractmethod
    def execute(
        self,
        run_dir: Path,
        target: Any,
        mode: str,
        credentials: dict[str, str],
    ) -> ExecutionResult | None: ...

    def health_check(self, credentials: dict[str, str]) -> HealthStatus:
        return HealthStatus.unknown


class ProviderRegistry:
    def __init__(self, bundled_dir: Path | None = None, user_dir: Path | None = None) -> None:
        self._bundled_dir = bundled_dir or _default_bundled_dir()
        self._user_dir = user_dir
        self._providers: dict[str, Provider] = {}
        self._info: dict[str, ProviderInfo] = {}

    def discover(self, trust_user: bool = False) -> None:
        """Scan bundled and (optionally) user provider directories.

        ``trust_user`` is the POST-confirmation gate, not a bypass.
        Pass True only after the user has explicitly confirmed loading
        each user-installed provider (typically via SKILL.md prompt
        and a write to ``settings.toml.providers.trusted_user_providers``).
        Tests pass True directly to exercise the override path.
        """
        self._providers.clear()
        self._info.clear()
        # bundled first
        if self._bundled_dir and self._bundled_dir.exists():
            for d in sorted(self._bundled_dir.iterdir()):
                if d.is_dir() and (d / "provider.yaml").exists():
                    self._load_provider(d, source="bundled")
        # then user (overrides if trusted)
        if trust_user and self._user_dir and self._user_dir.exists():
            for d in sorted(self._user_dir.iterdir()):
                if d.is_dir() and (d / "provider.yaml").exists():
                    self._load_provider(d, source="user")

    def resolve(self, name: str) -> Provider:
        if name not in self._providers:
            raise ProviderNotFoundError(f"provider not registered: {name}")
        return self._providers[name]

    def list(self, media_type: str | None = None) -> list[ProviderInfo]:
        infos = list(self._info.values())
        if media_type:
            infos = [i for i in infos if media_type in i.media_types]
        return infos

    def _load_provider(self, pdir: Path, source: str) -> None:
        meta = yaml.safe_load((pdir / "provider.yaml").read_text(encoding="utf-8"))
        name = meta["name"]
        entry = meta["entry"]  # e.g. "provider:FakeProvider"
        module_file, class_name = entry.split(":", 1)
        module_path = pdir / f"{module_file}.py"
        if not module_path.exists():
            raise FileNotFoundError(f"provider entry module not found: {module_path}")

        mod_name = f"_mmp_provider_{pdir.name}"
        spec = importlib.util.spec_from_file_location(
            mod_name, module_path, submodule_search_locations=[str(pdir)]
        )
        if not spec or not spec.loader:
            raise FileNotFoundError(f"cannot create import spec for provider at {module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        cls = getattr(module, class_name)
        instance = cls()

        creds = [CredentialSpec(**c) for c in (meta.get("required_credentials") or [])]
        info = ProviderInfo(
            name=name,
            display_name=meta.get("display_name", name),
            media_types=list(meta.get("media_types") or []),
            capabilities=dict(meta.get("capabilities") or {}),
            required_credentials=creds,
            source=source,
        )
        self._providers[name] = instance
        self._info[name] = info


def _default_bundled_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "providers"
