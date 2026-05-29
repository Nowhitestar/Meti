"""Release manifest helpers for Meti.

This module intentionally avoids provider imports and credential reads. It only
parses the checked-in release manifest used by release tooling.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

RELEASE_MANIFEST = "release.json"
REQUIRED_ARTIFACT_KINDS = {
    "wheel",
    "sdist",
    "claude-plugin-zip",
    "openclaw-skill-zip",
    "checksums",
    "release-manifest",
}
REQUIRED_HOSTS = {"cli", "claude-plugin", "openclaw-skill"}
STRICT_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def load_release_manifest(path: str | Path = RELEASE_MANIFEST) -> dict[str, Any]:
    """Load a release manifest from a file or project directory."""

    manifest_path = Path(path)
    if manifest_path.is_dir():
        manifest_path = manifest_path / RELEASE_MANIFEST
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def validate_release_manifest(manifest: Mapping[str, Any]) -> list[str]:
    """Return validation errors for the canonical release manifest."""

    errors: list[str] = []
    version = manifest.get("version")
    tag = manifest.get("tag")
    channel = manifest.get("channel")
    semver_policy = manifest.get("semver_policy")

    if not isinstance(version, str) or not STRICT_SEMVER_RE.match(version):
        errors.append("version must be strict SemVer X.Y.Z")
    if isinstance(version, str) and tag != f"v{version}":
        errors.append("tag must equal v<version>")
    if channel != "stable":
        errors.append("channel must be stable")
    if semver_policy != "strict":
        errors.append("semver_policy must be strict")

    compatibility = manifest.get("compatibility")
    if not isinstance(compatibility, dict):
        errors.append("compatibility must be an object")
    else:
        if compatibility.get("python") != ">=3.10":
            errors.append("compatibility.python must be >=3.10")
        for host in sorted(REQUIRED_HOSTS):
            if not isinstance(compatibility.get(host), str) or not compatibility.get(host):
                errors.append(f"compatibility.{host} must be set")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("artifacts must be a non-empty list")
    else:
        seen: set[str] = set()
        for index, artifact in enumerate(artifacts):
            if not isinstance(artifact, dict):
                errors.append(f"artifacts[{index}] must be an object")
                continue
            kind = artifact.get("kind")
            filename = artifact.get("filename")
            if not isinstance(kind, str) or not kind:
                errors.append(f"artifacts[{index}].kind must be set")
            else:
                seen.add(kind)
            if not isinstance(filename, str) or not filename:
                errors.append(f"artifacts[{index}].filename must be set")
        missing = sorted(REQUIRED_ARTIFACT_KINDS - seen)
        if missing:
            errors.append(f"artifacts missing kinds: {', '.join(missing)}")

    return errors
