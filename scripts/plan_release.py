#!/usr/bin/env python3
"""Decide whether CI should publish a Meti release."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.release import load_release_manifest  # noqa: E402

BUMP_ORDER = {"none": 0, "patch": 1, "minor": 2, "major": 3}
RELEASE_BUMPS = ("auto", "patch", "minor", "major")
SEMVER_RE = re.compile(r"^(?:v)?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
CONVENTIONAL_RE = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]+\))?(?P<breaking>!)?:")
BREAKING_RE = re.compile(r"(?im)^BREAKING[ -]CHANGE:")
RELEASE_OVERRIDE_RE = re.compile(
    r"(?im)(?:^\s*release:\s*(major|minor|patch)\b|\[release:\s*(major|minor|patch)\])"
)

Version = tuple[int, int, int]


@dataclass(frozen=True)
class ReleasePlan:
    """Serializable release decision consumed by GitHub Actions."""

    should_release: bool
    version: str
    tag: str
    bump: str
    latest_tag: str
    reason: str


def parse_version(version: str) -> Version:
    """Parse strict SemVer, allowing an optional leading v."""

    match = SEMVER_RE.match(version.strip())
    if not match:
        raise ValueError(f"{version} is not strict SemVer X.Y.Z")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def format_version(version: Version) -> str:
    """Format a SemVer tuple."""

    return ".".join(str(part) for part in version)


def bump_version(version: str, bump: str) -> str:
    """Return the next SemVer for a patch, minor, or major bump."""

    major, minor, patch = parse_version(version)
    if bump == "patch":
        return format_version((major, minor, patch + 1))
    if bump == "minor":
        return format_version((major, minor + 1, 0))
    if bump == "major":
        return format_version((major + 1, 0, 0))
    raise ValueError(f"unsupported release bump: {bump}")


def release_signal_from_message(message: str) -> str:
    """Return the release bump implied by one commit message."""

    override = RELEASE_OVERRIDE_RE.search(message)
    if override:
        return next(group for group in override.groups() if group)

    if BREAKING_RE.search(message):
        return "major"

    subject = message.strip().splitlines()[0] if message.strip() else ""
    conventional = CONVENTIONAL_RE.match(subject)
    if not conventional:
        return "none"
    if conventional.group("breaking"):
        return "major"
    if conventional.group("type") in {"feat", "perf"}:
        return "minor"
    return "none"


def highest_release_signal(messages: list[str]) -> tuple[str, list[str]]:
    """Return the strongest automatic release signal and matching subjects."""

    bump = "none"
    matches: list[str] = []
    for message in messages:
        signal = release_signal_from_message(message)
        if signal == "none":
            continue
        subject = message.strip().splitlines()[0]
        matches.append(f"{signal}: {subject}")
        if BUMP_ORDER[signal] > BUMP_ORDER[bump]:
            bump = signal
    return bump, matches


def select_release_plan(
    current_version: str,
    messages: list[str],
    *,
    force_bump: str = "auto",
    explicit_version: str = "",
    latest_tag: str = "",
) -> ReleasePlan:
    """Select the target release version from commit messages and overrides."""

    if force_bump not in RELEASE_BUMPS:
        raise ValueError(f"unsupported release bump: {force_bump}")

    current = parse_version(current_version)
    if explicit_version:
        target = parse_version(explicit_version)
        if target <= current:
            raise ValueError(
                f"explicit release version {explicit_version} must be greater than {current_version}"
            )
        version = format_version(target)
        return ReleasePlan(
            should_release=True,
            version=version,
            tag=f"v{version}",
            bump="exact",
            latest_tag=latest_tag,
            reason=f"Manual exact release version requested: {version}.",
        )

    if force_bump != "auto":
        version = bump_version(current_version, force_bump)
        return ReleasePlan(
            should_release=True,
            version=version,
            tag=f"v{version}",
            bump=force_bump,
            latest_tag=latest_tag,
            reason=f"Manual {force_bump} release requested.",
        )

    bump, matches = highest_release_signal(messages)
    if bump == "none":
        boundary = latest_tag or "the previous release"
        return ReleasePlan(
            should_release=False,
            version=current_version,
            tag=f"v{current_version}",
            bump="none",
            latest_tag=latest_tag,
            reason=f"No release-worthy commits since {boundary}.",
        )

    version = bump_version(current_version, bump)
    examples = "; ".join(matches[:3])
    suffix = "..." if len(matches) > 3 else ""
    return ReleasePlan(
        should_release=True,
        version=version,
        tag=f"v{version}",
        bump=bump,
        latest_tag=latest_tag,
        reason=f"Automatic {bump} release from {examples}{suffix}.",
    )


def _run_git(project_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def latest_semver_tag(project_root: Path) -> str:
    """Return the newest vX.Y.Z tag, or an empty string if none exists."""

    output = _run_git(
        project_root,
        ["tag", "--list", "v[0-9]*.[0-9]*.[0-9]*", "--sort=-v:refname"],
    )
    for tag in output.splitlines():
        try:
            parse_version(tag)
        except ValueError:
            continue
        return tag
    return ""


def commit_messages_since(project_root: Path, tag: str) -> list[str]:
    """Return commit messages after the release tag."""

    if not tag:
        return []
    output = _run_git(project_root, ["log", "--format=%B%x1e", f"{tag}..HEAD"])
    return [message.strip() for message in output.split("\x1e") if message.strip()]


def _write_github_output(plan: ReleasePlan, output_path: str) -> None:
    def safe(value: object) -> str:
        return str(value).replace("\n", " ").replace("\r", " ")

    lines = [
        f"should_release={str(plan.should_release).lower()}",
        f"version={safe(plan.version)}",
        f"tag={safe(plan.tag)}",
        f"bump={safe(plan.bump)}",
        f"latest_tag={safe(plan.latest_tag)}",
        f"reason={safe(plan.reason)}",
    ]
    with Path(output_path).open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=ROOT,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--force-bump",
        choices=RELEASE_BUMPS,
        default="auto",
        help="Force a patch/minor/major release instead of commit-message detection.",
    )
    parser.add_argument(
        "--version",
        default="",
        help="Publish an exact X.Y.Z version. Overrides --force-bump.",
    )
    parser.add_argument(
        "--github-output",
        action="store_true",
        help="Append release decision keys to GITHUB_OUTPUT.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    project_root = args.project_root.resolve()
    try:
        current_version = str(load_release_manifest(project_root)["version"])
        latest_tag = latest_semver_tag(project_root)
        messages = commit_messages_since(project_root, latest_tag)
        plan = select_release_plan(
            current_version,
            messages,
            force_bump=args.force_bump,
            explicit_version=args.version.strip(),
            latest_tag=latest_tag,
        )
    except (subprocess.CalledProcessError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(asdict(plan), indent=2))
    if args.github_output:
        output_path = os.environ.get("GITHUB_OUTPUT")
        if not output_path:
            print("ERROR: GITHUB_OUTPUT is not set", file=sys.stderr)
            return 1
        _write_github_output(plan, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
