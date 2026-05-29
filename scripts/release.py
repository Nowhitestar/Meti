#!/usr/bin/env python3
"""Build and publish Meti release artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.release import load_release_manifest, validate_release_manifest  # noqa: E402
from scripts import check_release  # noqa: E402

SOURCE_DIRS = (
    "core",
    "providers",
    "scripts",
    "docs",
    "examples",
    ".claude-plugin",
)
SOURCE_FILES = (
    "pyproject.toml",
    "README.md",
    "SKILL.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "release.json",
)
CLAUDE_PLUGIN_FILES = SOURCE_FILES
OPENCLAW_SKILL_DIRS = ("core", "providers", "scripts", "docs", "examples")
OPENCLAW_SKILL_FILES = ("SKILL.md", "README.md", "CHANGELOG.md", "release.json")
STRICT_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def _artifact_map(manifest: dict[str, object]) -> dict[str, str]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("release.json artifacts must be a list")
    result: dict[str, str] = {}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        kind = artifact.get("kind")
        filename = artifact.get("filename")
        if isinstance(kind, str) and isinstance(filename, str):
            result[kind] = filename
    return result


def validate_target_version(version: str, manifest: dict[str, object]) -> None:
    if not STRICT_SEMVER_RE.match(version):
        raise ValueError(f"{version} is not strict SemVer X.Y.Z")
    if manifest.get("channel") == "stable" and version != version.strip("v"):
        raise ValueError("stable releases use bare X.Y.Z versions")


def artifact_filename(kind: str, version: str) -> str:
    tag = f"v{version}"
    names = {
        "wheel": f"meti-{version}-py3-none-any.whl",
        "sdist": f"meti-{version}.tar.gz",
        "claude-plugin-zip": f"meti-claude-plugin-{tag}.zip",
        "openclaw-skill-zip": f"meti-openclaw-skill-{tag}.zip",
        "checksums": "SHA256SUMS",
        "release-manifest": "release.json",
    }
    return names[kind]


def _updated_manifest(manifest: dict[str, object], version: str) -> dict[str, object]:
    updated = json.loads(json.dumps(manifest))
    updated["version"] = version
    updated["tag"] = f"v{version}"
    compatibility = updated.get("compatibility")
    if isinstance(compatibility, dict):
        for host in ("cli", "claude-plugin", "openclaw-skill"):
            compatibility[host] = f">={version} <1.0.0"
    artifacts = updated.get("artifacts")
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if isinstance(artifact, dict) and isinstance(artifact.get("kind"), str):
                artifact["filename"] = artifact_filename(str(artifact["kind"]), version)
    return updated


def _iter_release_files(
    project_root: Path,
    *,
    dirs: tuple[str, ...] = SOURCE_DIRS,
    files: tuple[str, ...] = SOURCE_FILES,
) -> list[tuple[Path, str]]:
    selected: list[tuple[Path, str]] = []
    for rel_file in files:
        path = project_root / rel_file
        if path.exists() and not check_release.path_is_denied(rel_file):
            selected.append((path, rel_file))

    for rel_dir in dirs:
        root = project_root / rel_dir
        if not root.exists():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            rel = path.relative_to(project_root).as_posix()
            if check_release.path_is_denied(rel):
                continue
            if any(part in {".git", "build", "dist"} for part in path.parts):
                continue
            if path.name.endswith(".egg-info"):
                continue
            selected.append((path, rel))
    return selected


def _write_zip(path: Path, files: list[tuple[Path, str]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source, arcname in files:
            archive.write(source, arcname)


def _write_sdist(path: Path, version: str, files: list[tuple[Path, str]]) -> None:
    prefix = f"meti-{version}"
    with tarfile.open(path, "w:gz") as archive:
        for source, arcname in files:
            archive.add(source, arcname=f"{prefix}/{arcname}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_checksums(output_dir: Path, artifacts: list[Path]) -> Path:
    checksums = output_dir / "SHA256SUMS"
    lines = [f"{_sha256(path)}  {path.name}" for path in artifacts]
    checksums.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return checksums


def _replace_project_version(text: str, version: str) -> str:
    return re.sub(r'(?m)^version = "([^"]+)"$', f'version = "{version}"', text, count=1)


def _replace_skill_version(text: str, version: str) -> str:
    return re.sub(r"(?m)^version:\s*[^\n]+$", f"version: {version}", text, count=1)


def _move_unreleased_to_version(text: str, version: str) -> str:
    heading = f"## {version}"
    if heading in text:
        return text
    marker = "## Unreleased"
    start = text.find(marker)
    if start == -1:
        return text.rstrip() + f"\n\n## {version} - {dt.date.today().isoformat()}\n\n- Release prepared.\n"
    body_start = start + len(marker)
    next_heading = text.find("\n## ", body_start)
    if next_heading == -1:
        next_heading = len(text)
    unreleased_body = text[body_start:next_heading].strip()
    version_body = unreleased_body or "- Release prepared."
    return (
        text[:start]
        + "## Unreleased\n\n"
        + f"## {version} - {dt.date.today().isoformat()}\n\n{version_body}\n\n"
        + text[next_heading:].lstrip("\n")
    )


def _validate_artifacts(paths: list[Path]) -> None:
    failures: list[str] = []
    for path in paths:
        if path.name.endswith((".whl", ".zip", ".tar.gz", ".tgz")):
            denied = check_release.scan_archive_path(path)
        else:
            denied = [path.name] if check_release.path_is_denied(path.name) else []
        if denied:
            failures.append(f"{path.name}: {', '.join(denied)}")
    if failures:
        raise RuntimeError("release bundle includes private paths: " + "; ".join(failures))


def release_output_dir(project_root: Path, tag: str) -> Path:
    return project_root / "dist" / "releases" / tag


def prepare_release(project_root: Path, version: str, *, dry_run: bool = False) -> list[str]:
    manifest_path = project_root / "release.json"
    manifest = load_release_manifest(manifest_path)
    validate_target_version(version, manifest)
    updated_manifest = _updated_manifest(manifest, version)
    errors = validate_release_manifest(updated_manifest)
    if errors:
        raise ValueError("invalid prepared release.json: " + "; ".join(errors))

    updates = [
        "release.json",
        "pyproject.toml",
        "SKILL.md",
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
        "CHANGELOG.md",
    ]
    if dry_run:
        return updates

    manifest_path.write_text(
        json.dumps(updated_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    pyproject = project_root / "pyproject.toml"
    pyproject.write_text(
        _replace_project_version(pyproject.read_text(encoding="utf-8"), version),
        encoding="utf-8",
    )

    skill = project_root / "SKILL.md"
    skill.write_text(_replace_skill_version(skill.read_text(encoding="utf-8"), version), encoding="utf-8")

    plugin_path = project_root / ".claude-plugin" / "plugin.json"
    plugin = json.loads(plugin_path.read_text(encoding="utf-8"))
    plugin["version"] = version
    plugin_path.write_text(json.dumps(plugin, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    marketplace_path = project_root / ".claude-plugin" / "marketplace.json"
    marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    marketplace["plugins"][0]["version"] = version
    marketplace_path.write_text(
        json.dumps(marketplace, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    changelog = project_root / "CHANGELOG.md"
    changelog.write_text(
        _move_unreleased_to_version(changelog.read_text(encoding="utf-8"), version),
        encoding="utf-8",
    )
    return updates


def build_release_bundle(project_root: Path, *, dry_run: bool = False) -> list[Path]:
    manifest = load_release_manifest(project_root)
    errors = validate_release_manifest(manifest)
    if errors:
        raise ValueError("invalid release.json: " + "; ".join(errors))

    version = str(manifest["version"])
    tag = str(manifest["tag"])
    artifact_names = _artifact_map(manifest)
    expected = [
        "wheel",
        "sdist",
        "claude-plugin-zip",
        "openclaw-skill-zip",
        "release-manifest",
        "checksums",
    ]
    missing = [kind for kind in expected if kind not in artifact_names]
    if missing:
        raise ValueError("release.json missing artifacts: " + ", ".join(missing))

    output_dir = release_output_dir(project_root, tag)
    planned = [output_dir / artifact_names[kind] for kind in expected]
    if dry_run:
        return planned

    output_dir.mkdir(parents=True, exist_ok=True)
    produced: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="meti-release-build-") as tmp:
        wheel = check_release.build_wheel(project_root, Path(tmp))
        wheel_dest = output_dir / artifact_names["wheel"]
        shutil.copy2(wheel, wheel_dest)
        produced.append(wheel_dest)

    source_files = _iter_release_files(project_root)
    sdist = output_dir / artifact_names["sdist"]
    _write_sdist(sdist, version, source_files)
    produced.append(sdist)

    claude_files = _iter_release_files(
        project_root,
        dirs=SOURCE_DIRS,
        files=CLAUDE_PLUGIN_FILES,
    )
    claude_zip = output_dir / artifact_names["claude-plugin-zip"]
    _write_zip(claude_zip, claude_files)
    produced.append(claude_zip)

    openclaw_files = _iter_release_files(
        project_root,
        dirs=OPENCLAW_SKILL_DIRS,
        files=OPENCLAW_SKILL_FILES,
    )
    openclaw_zip = output_dir / artifact_names["openclaw-skill-zip"]
    _write_zip(openclaw_zip, openclaw_files)
    produced.append(openclaw_zip)

    manifest_dest = output_dir / artifact_names["release-manifest"]
    manifest_dest.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    produced.append(manifest_dest)

    _validate_artifacts(produced)
    checksums = _write_checksums(output_dir, produced)
    return produced + [checksums]


def cmd_build(args: argparse.Namespace) -> int:
    artifacts = build_release_bundle(args.project_root.resolve(), dry_run=args.dry_run)
    heading = "DRY RUN release bundle" if args.dry_run else "Built release bundle"
    print(f"{heading}:")
    for artifact in artifacts:
        print(f"- {artifact}")
    return 0


def _release_gate_command() -> list[str]:
    return ["python3", "scripts/check_release.py"]


def publish_commands(tag: str, artifacts: list[Path]) -> list[list[str]]:
    artifact_args = [str(path) for path in artifacts if path.name != "SHA256SUMS"]
    artifact_args.append(str(next(path for path in artifacts if path.name == "SHA256SUMS")))
    return [
        ["git", "tag", tag],
        [
            "gh",
            "release",
            "create",
            tag,
            *artifact_args,
            "--title",
            tag,
            "--notes-file",
            "CHANGELOG.md",
        ],
    ]


def run_commands(commands: list[list[str]], *, cwd: Path, dry_run: bool) -> None:
    for command in commands:
        print("$ " + " ".join(command))
        if not dry_run:
            subprocess.run(command, cwd=cwd, check=True)


def _print_publish_plan(version: str, tag: str, artifacts: list[Path]) -> None:
    checksums = next(path for path in artifacts if path.name == "SHA256SUMS")
    print(f"target version: {version}")
    print(f"target tag: {tag}")
    print(f"changelog heading: ## {version}")
    print("release bundle artifacts:")
    for artifact in artifacts:
        print(f"- {artifact}")
    print(f"checksum file: {checksums}")


def cmd_prepare(args: argparse.Namespace) -> int:
    updates = prepare_release(args.project_root.resolve(), args.version, dry_run=args.dry_run)
    heading = "DRY RUN prepare updates" if args.dry_run else "Prepared release updates"
    print(f"{heading} for {args.version}:")
    for rel_path in updates:
        print(f"- {rel_path}")
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    project_root = args.project_root.resolve()
    manifest = load_release_manifest(project_root)
    validate_target_version(args.version, manifest)
    if manifest.get("version") != args.version:
        raise ValueError(
            f"release.json version is {manifest.get('version')}; run prepare --version {args.version} first"
        )
    tag = f"v{args.version}"
    gate_command = _release_gate_command()
    print("release gate command:")
    print("$ " + " ".join(gate_command))
    if not args.dry_run:
        subprocess.run(gate_command, cwd=project_root, check=True)

    artifacts = build_release_bundle(project_root, dry_run=args.dry_run)
    _print_publish_plan(args.version, tag, artifacts)
    commands = publish_commands(tag, artifacts)
    print("publish commands:")
    for command in commands:
        print("$ " + " ".join(command))

    if args.dry_run:
        return 0
    if not args.yes:
        answer = input(f"Publish GitHub Release {tag}? Type 'yes' to continue: ")
        if answer != "yes":
            print("Release publish cancelled.")
            return 1
    run_commands(commands, cwd=project_root, dry_run=False)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=ROOT,
        help=argparse.SUPPRESS,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="Build the complete release bundle.")
    build.add_argument("--dry-run", action="store_true", help="Print planned artifacts only.")
    build.set_defaults(func=cmd_build)
    prepare = subparsers.add_parser("prepare", help="Prepare a version bump.")
    prepare.add_argument("--version", required=True, help="Strict SemVer target version, e.g. 0.4.4.")
    prepare.add_argument("--dry-run", action="store_true", help="Print intended updates only.")
    prepare.set_defaults(func=cmd_prepare)
    publish = subparsers.add_parser("publish", help="Publish a confirmed GitHub Release.")
    publish.add_argument("--version", required=True, help="Strict SemVer target version, e.g. 0.4.4.")
    publish.add_argument("--dry-run", action="store_true", help="Print intended release actions only.")
    publish.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")
    publish.set_defaults(func=cmd_publish)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: command failed: {' '.join(exc.cmd)}", file=sys.stderr)
        return exc.returncode
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
