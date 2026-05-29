from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_release.py"


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_release", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_release"] = module
    spec.loader.exec_module(module)
    return module


def write_minimal_project(root: Path, *, version: str = "0.4.3") -> None:
    (root / ".claude-plugin").mkdir(exist_ok=True)
    (root / "docs").mkdir(exist_ok=True)
    (root / "scripts").mkdir(exist_ok=True)
    (root / "release.json").write_text(
        json.dumps(
            {
                "version": version,
                "tag": f"v{version}",
                "channel": "stable",
                "semver_policy": "strict",
                "compatibility": {
                    "python": ">=3.10",
                    "cli": f">={version} <1.0.0",
                    "claude-plugin": f">={version} <1.0.0",
                    "openclaw-skill": f">={version} <1.0.0",
                },
                "artifacts": [
                    {"kind": "wheel", "filename": f"meti-{version}-py3-none-any.whl"},
                    {"kind": "sdist", "filename": f"meti-{version}.tar.gz"},
                    {
                        "kind": "claude-plugin-zip",
                        "filename": f"meti-claude-plugin-v{version}.zip",
                    },
                    {
                        "kind": "openclaw-skill-zip",
                        "filename": f"meti-openclaw-skill-v{version}.zip",
                    },
                    {"kind": "checksums", "filename": "SHA256SUMS"},
                    {"kind": "release-manifest", "filename": "release.json"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "meti"\nversion = "{version}"\n',
        encoding="utf-8",
    )
    (root / "SKILL.md").write_text(
        f"---\nname: Multi-media Publisher\nversion: {version}\n---\n",
        encoding="utf-8",
    )
    (root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps(
            {
                "name": "meti",
                "version": version,
                "description": "Draft-first publishing",
                "author": {"name": "Lewis Liao"},
                "homepage": "https://liao.uno/meti",
                "repository": "https://github.com/Nowhitestar/meti",
                "license": "MIT",
                "keywords": ["publishing"],
            }
        ),
        encoding="utf-8",
    )
    (root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "$schema": "https://json.schemastore.org/claude-code-marketplace",
                "name": "meti",
                "owner": {"name": "Lewis Liao"},
                "description": "Draft-first publishing",
                "plugins": [
                    {
                        "name": "meti",
                        "source": ".",
                        "description": "Draft-first publishing",
                        "version": version,
                        "author": {"name": "Lewis Liao"},
                        "homepage": "https://liao.uno/meti",
                        "repository": "https://github.com/Nowhitestar/meti",
                        "license": "MIT",
                        "category": "publishing",
                        "tags": ["publishing"],
                        "keywords": ["publishing"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "Claude Code marketplace submission is pending\n"
        "/plugin install meti\n"
        "meti update --version vX.Y.Z\n",
        encoding="utf-8",
    )
    (root / "CONTRIBUTING.md").write_text(
        "Prefer reinstall\n"
        "python scripts/check_release.py\n"
        "release.json\n"
        "scripts/release.py\n"
        "meti update --version vX.Y.Z\n",
        encoding="utf-8",
    )
    (root / "docs" / "distribution.md").write_text(
        "git clone https://github.com/Nowhitestar/meti.git ~/.openclaw/skills/meti\n"
        "Prefer reinstall\n"
        "python scripts/check_release.py\n"
        "scripts/install.sh --version vX.Y.Z\n"
        "meti update --version vX.Y.Z\n"
        "~/.config/meti/credentials.json.age\n",
        encoding="utf-8",
    )
    (root / "docs" / "marketplace-submission.md").write_text(
        "Short description\nLong description\nPrivacy\nSafety\nVerification\n"
        "explicit confirmation\n",
        encoding="utf-8",
    )
    (root / ".gitignore").write_text(
        "\n".join(
            [
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
                ".planning/",
                "docs/HANDOFF.md",
                "docs/legacy-research.md",
                "*.local.md",
                "private/",
            ]
        ),
        encoding="utf-8",
    )


def test_load_versions_reads_all_surfaces(tmp_path: Path) -> None:
    check_release = load_module()
    write_minimal_project(tmp_path)

    versions = check_release.load_versions(tmp_path)

    assert versions["release"] == "0.4.3"
    assert versions["pyproject"] == "0.4.3"
    assert versions["skill"] == "0.4.3"
    assert versions["plugin"] == "0.4.3"
    assert versions["marketplace"] == "0.4.3"


def test_version_sync_reports_skill_drift(tmp_path: Path) -> None:
    check_release = load_module()
    write_minimal_project(tmp_path)
    (tmp_path / "SKILL.md").write_text(
        "---\nname: Multi-media Publisher\nversion: 9.9.9\n---\n",
        encoding="utf-8",
    )

    result = check_release.check_version_sync(tmp_path)

    assert not result.ok
    assert "SKILL.md" in result.message


def test_version_sync_reports_pyproject_drift_from_release_manifest(tmp_path: Path) -> None:
    check_release = load_module()
    write_minimal_project(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "meti"\nversion = "9.9.9"\n',
        encoding="utf-8",
    )

    result = check_release.check_version_sync(tmp_path)

    assert not result.ok
    assert "release.json" in result.message
    assert "pyproject.toml" in result.message


def test_metadata_requires_keywords_and_marketplace_tags(tmp_path: Path) -> None:
    check_release = load_module()
    write_minimal_project(tmp_path)

    plugin_path = tmp_path / ".claude-plugin" / "plugin.json"
    plugin = json.loads(plugin_path.read_text(encoding="utf-8"))
    plugin["keywords"] = []
    plugin_path.write_text(json.dumps(plugin), encoding="utf-8")
    result = check_release.check_metadata(tmp_path)
    assert not result.ok
    assert ".claude-plugin/plugin.json" in result.message

    write_minimal_project(tmp_path)
    marketplace_path = tmp_path / ".claude-plugin" / "marketplace.json"
    marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    marketplace["plugins"][0].pop("tags")
    marketplace_path.write_text(json.dumps(marketplace), encoding="utf-8")
    result = check_release.check_metadata(tmp_path)
    assert not result.ok
    assert ".claude-plugin/marketplace.json" in result.message


def test_private_path_denylist() -> None:
    check_release = load_module()

    assert check_release.path_is_denied(".planning/ROADMAP.md")
    assert check_release.path_is_denied("runs/20260507-001255-mmp/result.json")
    assert check_release.path_is_denied(".env.production")
    assert check_release.path_is_denied("docs/.DS_Store")
    assert check_release.path_is_denied("docs/HANDOFF.md")
    assert not check_release.path_is_denied("README.md")


def test_archive_hygiene_rejects_private_members() -> None:
    check_release = load_module()

    assert check_release.scan_archive_members([".planning/STATE.md"])
    assert not check_release.scan_archive_members(["core/__init__.py"])


def test_bundle_scan_rejects_private_planning_zip_member(tmp_path: Path) -> None:
    check_release = load_module()
    archive = tmp_path / "meti-claude-plugin-v0.4.3.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(".planning/STATE.md", "{}")

    failures = check_release.scan_release_bundle_for_private_paths(tmp_path)

    assert failures[archive.name] == [".planning/STATE.md"]


def test_bundle_scan_rejects_private_runs_zip_member(tmp_path: Path) -> None:
    check_release = load_module()
    archive = tmp_path / "meti-openclaw-skill-v0.4.3.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("runs/example/result.json", "{}")

    failures = check_release.scan_release_bundle_for_private_paths(tmp_path)

    assert failures[archive.name] == ["runs/example/result.json"]


def test_docs_install_reports_missing_required_strings(tmp_path: Path) -> None:
    check_release = load_module()
    write_minimal_project(tmp_path)
    distribution = tmp_path / "docs" / "distribution.md"
    distribution.write_text("python scripts/check_release.py\n", encoding="utf-8")

    result = check_release.check_docs_install(tmp_path)

    assert not result.ok
    assert "Prefer reinstall" in result.message


def test_cli_selected_checks_are_non_mutating(tmp_path: Path) -> None:
    check_release = load_module()
    write_minimal_project(tmp_path)
    skill = tmp_path / "SKILL.md"
    before = skill.read_text(encoding="utf-8")

    exit_code = check_release.main(
        ["--project-root", str(tmp_path), "--check", "version-sync", "--check", "metadata"]
    )

    assert exit_code == 0
    assert skill.read_text(encoding="utf-8") == before


def test_docs_install_requires_marketplace_confirmation_boundary(tmp_path: Path) -> None:
    check_release = load_module()
    write_minimal_project(tmp_path)
    submission = tmp_path / "docs" / "marketplace-submission.md"
    submission.write_text(
        "Short description\nLong description\nPrivacy\nSafety\nVerification\n",
        encoding="utf-8",
    )

    result = check_release.check_docs_install(tmp_path)

    assert not result.ok
    assert "explicit confirmation" in result.message
