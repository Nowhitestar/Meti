"""Manifest schema, loading, normalization, and validation.

A manifest is the user-facing YAML; once loaded it becomes a Manifest dataclass.
The lock-form (manifest.lock.json) is the normalized version emitted by
to_lock_dict for downstream tools.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from core.errors import ManifestError

VALID_TYPES = {"image-post", "longform", "video-post"}
VALID_MODES = {"dry-run", "draft", "publish"}
SCHEMA_VERSION = "0.2"


@dataclass
class Target:
    name: str
    mode: str = "dry-run"
    account: str = "default"
    options: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mode": self.mode,
            "account": self.account,
            "options": dict(self.options),
        }


@dataclass
class Manifest:
    schema_version: str
    type: str
    title: str
    body: str
    mode: str
    targets: list[Target]
    summary: str | None = None
    language: str = "zh-CN"
    cover: str | None = None
    images: list[str] = field(default_factory=list)
    video: str | None = None
    tags: list[str] = field(default_factory=list)
    cta: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    source_path: Path | None = None  # not serialized; for relative-path resolution

    def to_lock_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "type": self.type,
            "title": self.title,
            "body": self.body,
            "summary": self.summary,
            "mode": self.mode,
            "language": self.language,
            "cover": self.cover,
            "images": list(self.images),
            "video": self.video,
            "tags": list(self.tags),
            "cta": self.cta,
            "metadata": dict(self.metadata),
            "targets": [t.to_dict() for t in self.targets],
        }


def load_manifest(path: str | Path) -> Manifest:
    p = Path(path).resolve()
    if not p.exists():
        raise ManifestError(f"manifest not found: {p}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ManifestError(f"invalid YAML in manifest {p}: {e}") from e
    if not isinstance(raw, dict):
        raise ManifestError(f"manifest must be a YAML mapping at top level: {p}")
    return _from_dict(raw, base_dir=p.parent, source=p)


def _from_dict(raw: dict[str, Any], base_dir: Path, source: Path) -> Manifest:
    for required in ("schema_version", "type", "title", "body", "mode", "targets"):
        if required not in raw:
            raise ManifestError(f"manifest missing required field: {required}")

    sv = str(raw["schema_version"])
    if sv != SCHEMA_VERSION:
        raise ManifestError(f"unsupported schema_version {sv}; expected {SCHEMA_VERSION}")

    type_ = raw["type"]
    if type_ not in VALID_TYPES:
        raise ManifestError(f"invalid type {type_!r}; must be one of {sorted(VALID_TYPES)}")

    mode = raw["mode"]
    if mode not in VALID_MODES:
        raise ManifestError(f"invalid mode {mode!r}; must be one of {sorted(VALID_MODES)}")

    body_field = raw["body"]
    body = _resolve_inline_or_path(body_field, base_dir)

    defaults = raw.get("defaults") or {}
    if not isinstance(defaults, dict):
        raise ManifestError("defaults must be a mapping")
    default_account = defaults.get("account", "default")
    default_options = defaults.get("options", {}) or {}

    raw_targets = raw["targets"]
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ManifestError("targets must be a non-empty list")
    targets = [_parse_target(t, mode, default_account, default_options) for t in raw_targets]

    assets = raw.get("assets") or {}
    cover = assets.get("cover")
    images = list(assets.get("images") or [])
    video = assets.get("video")

    return Manifest(
        schema_version=sv,
        type=type_,
        title=str(raw["title"]),
        body=body,
        mode=mode,
        targets=targets,
        summary=raw.get("summary"),
        language=raw.get("language", "zh-CN"),
        cover=cover,
        images=images,
        video=video,
        tags=list(raw.get("tags") or []),
        cta=raw.get("cta"),
        metadata=dict(raw.get("metadata") or {}),
        source_path=source,
    )


def _resolve_inline_or_path(value: Any, base_dir: Path) -> str:
    if not isinstance(value, str):
        raise ManifestError("body must be a string (inline) or path string")
    s = value.strip()
    # Explicit path: ./ or ../ prefix => MUST resolve, error if missing.
    if s.startswith("./") or s.startswith("../"):
        candidate = (base_dir / s).resolve()
        if not candidate.exists():
            raise ManifestError(f"body path not found: {candidate} (from {value!r})")
        return candidate.read_text(encoding="utf-8")
    # Heuristic: .md suffix without explicit prefix => path if exists, else inline.
    if s.endswith(".md"):
        candidate = (base_dir / s).resolve()
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    return value


def _parse_target(
    raw: Any,
    top_mode: str,
    default_account: str,
    default_options: dict[str, Any],
) -> Target:
    if isinstance(raw, str):
        return Target(
            name=raw,
            mode=top_mode,
            account=default_account,
            options=dict(default_options),
        )
    if isinstance(raw, dict):
        if "target" not in raw:
            raise ManifestError(f"target object missing 'target' key: {raw}")
        merged_options = dict(default_options)
        merged_options.update(raw.get("options") or {})
        m = raw.get("mode", top_mode)
        if m not in VALID_MODES:
            raise ManifestError(f"invalid target mode {m!r}")
        return Target(
            name=raw["target"],
            mode=m,
            account=raw.get("account", default_account),
            options=merged_options,
        )
    raise ManifestError(f"target must be string or mapping, got {type(raw).__name__}")


def write_lock(manifest: Manifest, run_dir: Path) -> Path:
    lock_path = run_dir / "manifest.lock.json"
    lock_path.write_text(
        json.dumps(manifest.to_lock_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return lock_path
