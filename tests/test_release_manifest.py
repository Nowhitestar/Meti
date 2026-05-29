from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "core" / "release.py"
RELEASE_SCRIPT = ROOT / "scripts" / "release.py"


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("release", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["release"] = module
    spec.loader.exec_module(module)
    return module


def load_release_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("release_script", RELEASE_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["release_script"] = module
    spec.loader.exec_module(module)
    return module


def test_release_manifest_loads_and_validates_current_tree() -> None:
    release = load_module()

    manifest = release.load_release_manifest(ROOT)

    assert manifest["version"] == "0.4.3"
    assert manifest["tag"] == "v0.4.3"
    assert manifest["channel"] == "stable"
    assert release.validate_release_manifest(manifest) == []


def test_release_manifest_requires_strict_stable_artifact_contract(tmp_path: Path) -> None:
    release = load_module()
    manifest = release.load_release_manifest(ROOT)
    manifest["version"] = "0.4"
    manifest["tag"] = "v0.4"
    manifest["artifacts"] = [
        artifact for artifact in manifest["artifacts"] if artifact["kind"] != "wheel"
    ]
    manifest_path = tmp_path / "release.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    errors = release.validate_release_manifest(release.load_release_manifest(manifest_path))

    assert "version must be strict SemVer X.Y.Z" in errors
    assert any("wheel" in error for error in errors)


def test_prepare_dry_run_reports_all_public_version_surfaces(capsys: pytest.CaptureFixture[str]) -> None:
    release_script = load_release_script()
    before = (ROOT / "release.json").read_text(encoding="utf-8")

    exit_code = release_script.main(
        ["--project-root", str(ROOT), "prepare", "--version", "0.4.4", "--dry-run"]
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    for rel_path in (
        "release.json",
        "pyproject.toml",
        "SKILL.md",
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
        "CHANGELOG.md",
    ):
        assert rel_path in out
    assert (ROOT / "release.json").read_text(encoding="utf-8") == before


def test_publish_dry_run_reports_gate_artifacts_and_release_commands(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    release_script = load_release_script()

    def fail_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("dry-run must not call subprocess.run")

    monkeypatch.setattr(release_script.subprocess, "run", fail_run)

    exit_code = release_script.main(
        ["--project-root", str(ROOT), "publish", "--version", "0.4.3", "--dry-run"]
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "python3 scripts/check_release.py" in out
    assert "meti-claude-plugin-v0.4.3.zip" in out
    assert "SHA256SUMS" in out
    assert "git tag v0.4.3" in out
    assert "gh release create v0.4.3" in out


def test_release_script_rejects_invalid_stable_versions() -> None:
    release_script = load_release_script()

    with pytest.raises(ValueError):
        release_script.validate_target_version("0.4", {"channel": "stable"})
    with pytest.raises(ValueError):
        release_script.validate_target_version("0.4.4-dev", {"channel": "stable"})


def test_publish_commands_use_subprocess_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    release_script = load_release_script()
    artifacts = [
        tmp_path / "meti-0.4.3-py3-none-any.whl",
        tmp_path / "meti-0.4.3.tar.gz",
        tmp_path / "meti-claude-plugin-v0.4.3.zip",
        tmp_path / "meti-openclaw-skill-v0.4.3.zip",
        tmp_path / "release.json",
        tmp_path / "SHA256SUMS",
    ]
    calls: list[list[str]] = []

    def record_run(command: list[str], **_kwargs: object) -> None:
        calls.append(command)

    monkeypatch.setattr(release_script.subprocess, "run", record_run)

    release_script.run_commands(release_script.publish_commands("v0.4.3", artifacts), cwd=ROOT, dry_run=False)

    assert calls[0] == ["git", "tag", "v0.4.3"]
    assert calls[1][:4] == ["gh", "release", "create", "v0.4.3"]
