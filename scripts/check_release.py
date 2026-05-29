#!/usr/bin/env python3
"""Release readiness checks for Meti distribution artifacts."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback.
    import tomli as tomllib  # type: ignore[no-redef]


VERSION_FILES = {
    "release": Path("release.json"),
    "pyproject": Path("pyproject.toml"),
    "skill": Path("SKILL.md"),
    "plugin": Path(".claude-plugin/plugin.json"),
    "marketplace": Path(".claude-plugin/marketplace.json"),
}

DENIED_DIR_PREFIXES = (
    ".planning",
    "runs",
    ".claude",
    ".openclaw",
    ".mcp",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "__pycache__",
    "private",
    "docs/superpowers",
)

DENIED_EXACT_PATHS = {
    "docs/HANDOFF.md",
    "docs/legacy-research.md",
    "age-key.txt",
    "credentials.json",
    "credentials.json.age",
}

DENIED_PATH_PATTERNS = (
    ".env",
    ".env.*",
    ".DS_Store",
    "*.age",
    "*.local.md",
    "*.pyc",
    "*.log",
)

REQUIRED_GITIGNORE_ENTRIES = (
    "dist/",
    "runs/",
    ".env",
    ".env.*",
    "*.log",
    "*.age",
    "age-key.txt",
    "credentials.json",
    "credentials.json.age",
    ".claude/",
    ".openclaw/",
    ".mcp/",
    ".planning/",
    "docs/HANDOFF.md",
    "docs/legacy-research.md",
    "*.local.md",
    "private/",
)

PLUGIN_REQUIRED_FIELDS = (
    "name",
    "version",
    "description",
    "author.name",
    "homepage",
    "repository",
    "license",
    "keywords",
)

MARKETPLACE_REQUIRED_FIELDS = (
    "$schema",
    "name",
    "owner.name",
    "description",
    "plugins",
)

MARKETPLACE_PLUGIN_REQUIRED_FIELDS = (
    "name",
    "source",
    "description",
    "version",
    "author.name",
    "homepage",
    "repository",
    "license",
    "category",
    "tags",
    "keywords",
)

DOCS_REQUIRED_STRINGS = {
    "README.md": (
        "Claude Code marketplace submission is pending",
        "/plugin install meti",
        "meti update --version vX.Y.Z",
    ),
    "CONTRIBUTING.md": (
        "Prefer reinstall",
        "python scripts/check_release.py",
        "release.json",
        "scripts/release.py",
        "meti update --version vX.Y.Z",
    ),
    "docs/distribution.md": (
        "git clone https://github.com/Nowhitestar/meti.git ~/.openclaw/skills/meti",
        "Prefer reinstall",
        "python scripts/check_release.py",
        "scripts/install.sh --version vX.Y.Z",
        "meti update --version vX.Y.Z",
        "~/.config/meti/credentials.json.age",
    ),
    "docs/marketplace-submission.md": (
        "Short description",
        "Long description",
        "Privacy",
        "Safety",
        "Verification",
        "explicit confirmation",
    ),
}


@dataclass(frozen=True)
class CheckResult:
    """Small result object for a named release check."""

    name: str
    ok: bool
    message: str


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _nested_value(data: Any, dotted: str) -> Any:
    current = data
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return True


def _missing_fields(data: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    return [field for field in fields if not _is_non_empty(_nested_value(data, field))]


def _normalize_path(path: str | Path) -> str:
    normalized = str(path).replace(os.sep, "/").replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")


def _skill_frontmatter_version(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path} does not start with YAML frontmatter")
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        if stripped.startswith("version:"):
            return stripped.split(":", 1)[1].strip().strip("'\"")
    raise ValueError(f"{path} frontmatter has no version")


def load_versions(project_root: Path) -> dict[str, str]:
    """Load all public distribution version surfaces."""

    root = project_root.resolve()
    release = _read_json(root / VERSION_FILES["release"])
    pyproject = tomllib.loads((root / VERSION_FILES["pyproject"]).read_text(encoding="utf-8"))
    plugin = _read_json(root / VERSION_FILES["plugin"])
    marketplace = _read_json(root / VERSION_FILES["marketplace"])
    try:
        marketplace_version = marketplace["plugins"][0]["version"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(".claude-plugin/marketplace.json plugins[0].version missing") from exc
    return {
        "release": str(release["version"]),
        "pyproject": str(pyproject["project"]["version"]),
        "skill": _skill_frontmatter_version(root / VERSION_FILES["skill"]),
        "plugin": str(plugin["version"]),
        "marketplace": str(marketplace_version),
    }


def check_version_sync(project_root: Path) -> CheckResult:
    try:
        versions = load_versions(project_root)
    except Exception as exc:
        return CheckResult("version-sync", False, str(exc))

    canonical = versions["release"]
    drift = [
        f"{VERSION_FILES[name]}={version}"
        for name, version in versions.items()
        if name != "release" and version != canonical
    ]
    if drift:
        return CheckResult(
            "version-sync",
            False,
            f"release.json={canonical}; drift: {', '.join(drift)}",
        )
    surfaces = ", ".join(f"{name}={version}" for name, version in versions.items())
    return CheckResult("version-sync", True, surfaces)


def check_plugin_metadata(project_root: Path) -> CheckResult:
    path = project_root / VERSION_FILES["plugin"]
    try:
        data = _read_json(path)
    except Exception as exc:
        return CheckResult("metadata", False, f"{path}: {exc}")
    missing = _missing_fields(data, PLUGIN_REQUIRED_FIELDS)
    if missing:
        return CheckResult(
            "metadata",
            False,
            f"{VERSION_FILES['plugin']} missing required fields: {', '.join(missing)}",
        )
    return CheckResult("metadata", True, f"{VERSION_FILES['plugin']} ok")


def check_marketplace_metadata(project_root: Path) -> CheckResult:
    path = project_root / VERSION_FILES["marketplace"]
    try:
        data = _read_json(path)
    except Exception as exc:
        return CheckResult("metadata", False, f"{path}: {exc}")

    missing = _missing_fields(data, MARKETPLACE_REQUIRED_FIELDS)
    plugins = data.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        missing.append("plugins[0]")
        plugins = []

    plugin_missing: list[str] = []
    if plugins:
        first = plugins[0]
        if not isinstance(first, dict):
            plugin_missing.append("plugins[0]")
        else:
            plugin_missing = _missing_fields(first, MARKETPLACE_PLUGIN_REQUIRED_FIELDS)

    messages: list[str] = []
    if missing:
        messages.append(f"top-level missing: {', '.join(missing)}")
    if plugin_missing:
        messages.append(f"plugins[0] missing: {', '.join(plugin_missing)}")
    if messages:
        return CheckResult(
            "metadata", False, f"{VERSION_FILES['marketplace']} {'; '.join(messages)}"
        )
    return CheckResult("metadata", True, f"{VERSION_FILES['marketplace']} ok")


def check_metadata(project_root: Path) -> CheckResult:
    plugin_result = check_plugin_metadata(project_root)
    marketplace_result = check_marketplace_metadata(project_root)
    if plugin_result.ok and marketplace_result.ok:
        return CheckResult(
            "metadata",
            True,
            f"{plugin_result.message}; {marketplace_result.message}",
        )
    messages = [result.message for result in (plugin_result, marketplace_result) if not result.ok]
    return CheckResult("metadata", False, "; ".join(messages))


def path_is_denied(path: str | Path) -> bool:
    """Return True when a repo or archive path is private/local-only."""

    normalized = _normalize_path(path)
    if not normalized:
        return False

    if normalized in DENIED_EXACT_PATHS:
        return True

    parts = normalized.split("/")
    for prefix in DENIED_DIR_PREFIXES:
        if normalized == prefix or normalized.startswith(f"{prefix}/"):
            return True
        if "/" not in prefix and prefix in parts:
            return True

    basename = parts[-1]
    return any(fnmatch.fnmatch(basename, pattern) for pattern in DENIED_PATH_PATTERNS)


def denied_paths(paths: list[str]) -> list[str]:
    return sorted(path for path in paths if path_is_denied(path))


def _git_tracked_files(project_root: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _check_gitignore(project_root: Path) -> list[str]:
    gitignore = project_root / ".gitignore"
    if not gitignore.exists():
        return list(REQUIRED_GITIGNORE_ENTRIES)
    entries = {
        line.strip()
        for line in gitignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    return [entry for entry in REQUIRED_GITIGNORE_ENTRIES if entry not in entries]


def _copy_release_source(project_root: Path, destination: Path) -> Path:
    def ignore(src: str, names: list[str]) -> set[str]:
        src_path = Path(src)
        ignored: set[str] = set()
        for name in names:
            path = src_path / name
            try:
                rel_path = path.relative_to(project_root)
            except ValueError:
                rel_path = Path(name)
            rel = _normalize_path(rel_path)
            if (
                path_is_denied(rel)
                or name in {".git", "build", "dist"}
                or name.endswith(".egg-info")
            ):
                ignored.add(name)
        return ignored

    shutil.copytree(project_root, destination, ignore=ignore)
    return destination


def check_private_paths(project_root: Path) -> CheckResult:
    tracked_denied = denied_paths(_git_tracked_files(project_root))
    missing_ignores = _check_gitignore(project_root)
    messages: list[str] = []
    if tracked_denied:
        messages.append(f"tracked private paths: {', '.join(tracked_denied)}")
    if missing_ignores:
        messages.append(f".gitignore missing: {', '.join(missing_ignores)}")
    if messages:
        return CheckResult("private-paths", False, "; ".join(messages))
    return CheckResult("private-paths", True, "tracked files and .gitignore private-path rules ok")


def _python_can_build(candidate: Path) -> bool:
    proc = subprocess.run(
        [
            str(candidate),
            "-c",
            (
                "import importlib.util, sys; "
                "ok = sys.version_info >= (3, 10) "
                "and importlib.util.find_spec('pip') "
                "and importlib.util.find_spec('setuptools') "
                "and importlib.util.find_spec('wheel'); "
                "raise SystemExit(0 if ok else 1)"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def _build_python_candidates() -> list[Path]:
    candidates: list[Path] = [Path(sys.executable)]
    for raw in (
        shutil.which("python"),
        shutil.which("python3"),
        "/opt/anaconda3/bin/python",
        "/opt/homebrew/opt/python@3.12/bin/python3.12",
        "/opt/homebrew/opt/python@3.11/bin/python3.11",
        "/opt/homebrew/opt/python@3.10/bin/python3.10",
        "/usr/local/bin/python3",
        "/usr/bin/python3",
    ):
        if raw:
            candidates.append(Path(raw))

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen or not candidate.exists():
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _python_can_smoke(candidate: Path) -> bool:
    proc = subprocess.run(
        [
            str(candidate),
            "-c",
            (
                "import importlib.util, sys; "
                "ok = sys.version_info >= (3, 10) "
                "and importlib.util.find_spec('yaml') "
                "and importlib.util.find_spec('pyrage'); "
                "raise SystemExit(0 if ok else 1)"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def _smoke_python() -> Path | None:
    for candidate in _build_python_candidates():
        if _python_can_smoke(candidate):
            return candidate
    return None


def build_wheel(project_root: Path, wheel_dir: Path) -> Path:
    """Build one wheel into wheel_dir and return its path."""

    source_root = _copy_release_source(project_root, wheel_dir / "source")
    errors: list[str] = []
    for idx, python in enumerate(_build_python_candidates(), start=1):
        if not _python_can_build(python):
            errors.append(f"{python}: missing Python >=3.10, pip, setuptools, or wheel")
            continue
        attempt_dir = wheel_dir / f"attempt-{idx}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            str(python),
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(attempt_dir),
        ]
        proc = subprocess.run(
            cmd,
            cwd=source_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        if proc.returncode != 0:
            output = (proc.stdout + "\n" + proc.stderr).strip()
            errors.append(f"{' '.join(cmd)} failed:\n{output}")
            continue
        wheels = sorted(attempt_dir.glob("*.whl"))
        if len(wheels) != 1:
            errors.append(f"{python}: expected exactly one wheel, found {len(wheels)}")
            continue
        return wheels[0]

    raise RuntimeError(
        "wheel build failed for all local Python candidates:\n" + "\n\n".join(errors)
    )


def scan_archive_members(members: list[str]) -> list[str]:
    return denied_paths(members)


def archive_member_names(archive_path: Path) -> list[str]:
    """Read member names from supported release archives."""

    name = archive_path.name
    if name.endswith((".whl", ".zip")):
        with zipfile.ZipFile(archive_path) as archive:
            return archive.namelist()
    if name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(archive_path, "r:gz") as archive:
            return archive.getnames()
    return []


def scan_archive_path(archive_path: Path) -> list[str]:
    return scan_archive_members(archive_member_names(archive_path))


def scan_wheel_for_private_paths(wheel_path: Path) -> list[str]:
    return scan_archive_path(wheel_path)


def wheel_has_console_script_target(wheel_path: Path) -> bool:
    with zipfile.ZipFile(wheel_path) as archive:
        return "scripts/meti.py" in archive.namelist()


def scan_release_bundle_for_private_paths(bundle_dir: Path) -> dict[str, list[str]]:
    """Scan every release bundle artifact for denied paths."""

    denied_by_artifact: dict[str, list[str]] = {}
    if not bundle_dir.exists():
        return denied_by_artifact

    for path in sorted(bundle_dir.iterdir()):
        if path.name == "SHA256SUMS":
            continue
        if path.is_dir():
            continue
        denied: list[str]
        if path.name.endswith((".whl", ".zip", ".tar.gz", ".tgz")):
            denied = scan_archive_path(path)
        else:
            denied = [path.name] if path_is_denied(path.name) else []
        if denied:
            denied_by_artifact[path.name] = denied
    return denied_by_artifact


def check_artifact_hygiene(project_root: Path) -> CheckResult:
    try:
        with tempfile.TemporaryDirectory(prefix="meti-release-wheel-") as tmp:
            wheel = build_wheel(project_root, Path(tmp))
            denied = scan_wheel_for_private_paths(wheel)
            has_console_target = wheel_has_console_script_target(wheel)
    except Exception as exc:
        return CheckResult("artifacts", False, str(exc))
    if denied:
        return CheckResult("artifacts", False, f"wheel includes private paths: {', '.join(denied)}")
    if not has_console_target:
        return CheckResult("artifacts", False, "wheel missing scripts/meti.py console target")

    release_root = project_root / "dist" / "releases"
    bundle_failures: dict[str, list[str]] = {}
    if release_root.exists():
        for bundle_dir in sorted(path for path in release_root.iterdir() if path.is_dir()):
            for artifact, paths in scan_release_bundle_for_private_paths(bundle_dir).items():
                bundle_failures[f"{bundle_dir.name}/{artifact}"] = paths
    if bundle_failures:
        details = "; ".join(
            f"{artifact}: {', '.join(paths)}" for artifact, paths in bundle_failures.items()
        )
        return CheckResult("artifacts", False, f"release bundle includes private paths: {details}")
    return CheckResult(
        "artifacts",
        True,
        "wheel and release bundle artifact private-path scans ok",
    )


def check_docs_install(project_root: Path) -> CheckResult:
    missing: list[str] = []
    for rel_path, needles in DOCS_REQUIRED_STRINGS.items():
        path = project_root / rel_path
        if not path.exists():
            missing.append(f"{rel_path}: file missing")
            continue
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle not in text:
                missing.append(f"{rel_path}: missing {needle!r}")
    if missing:
        return CheckResult("docs-install", False, "; ".join(missing))
    return CheckResult("docs-install", True, "distribution docs contain required install text")


def check_smoke(project_root: Path) -> CheckResult:
    script = project_root / "scripts" / "test_local.py"
    if not script.exists():
        return CheckResult("smoke", False, "scripts/test_local.py missing")
    python = _smoke_python()
    if python is None:
        return CheckResult("smoke", False, "no local Python has yaml and pyrage installed")
    try:
        with tempfile.TemporaryDirectory(prefix="meti-release-smoke-") as tmp:
            tmp_path = Path(tmp)
            env = dict(os.environ)
            env.update(
                {
                    "METI_RUNS_DIR": str(tmp_path / "runs"),
                    "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
                }
            )
            proc = subprocess.run(
                [str(python), str(script)],
                cwd=project_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=180,
            )
    except Exception as exc:
        return CheckResult("smoke", False, str(exc))

    if proc.returncode != 0:
        output = (proc.stdout + "\n" + proc.stderr).strip()
        return CheckResult("smoke", False, output)
    return CheckResult("smoke", True, "scripts/test_local.py passed with isolated state")


CHECKS = {
    "version-sync": check_version_sync,
    "metadata": check_metadata,
    "private-paths": check_private_paths,
    "artifacts": check_artifact_hygiene,
    "docs-install": check_docs_install,
    "smoke": check_smoke,
}


def run_checks(project_root: Path, selected: list[str] | None = None) -> list[CheckResult]:
    names = selected or list(CHECKS)
    return [CHECKS[name](project_root) for name in names]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="append",
        choices=sorted(CHECKS),
        help="Run only this named check. Can be repeated.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    results = run_checks(args.project_root.resolve(), args.check)
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        print(f"{status} {result.name} - {result.message}")
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
