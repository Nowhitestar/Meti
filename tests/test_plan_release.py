from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "plan_release.py"


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("plan_release", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["plan_release"] = module
    spec.loader.exec_module(module)
    return module


def test_routine_changes_do_not_trigger_auto_release() -> None:
    plan_release = load_module()

    plan = plan_release.select_release_plan(
        "0.5.1",
        [
            "fix(cli): handle empty drafts",
            "docs: clarify install path",
            "chore: update dev tooling",
        ],
        latest_tag="v0.5.1",
    )

    assert plan.should_release is False
    assert plan.version == "0.5.1"
    assert plan.bump == "none"


def test_feature_commit_triggers_minor_release() -> None:
    plan_release = load_module()

    plan = plan_release.select_release_plan(
        "0.5.1",
        ["feat(release): install by version"],
        latest_tag="v0.5.1",
    )

    assert plan.should_release is True
    assert plan.version == "0.6.0"
    assert plan.tag == "v0.6.0"
    assert plan.bump == "minor"


def test_breaking_commit_triggers_major_release() -> None:
    plan_release = load_module()

    plan = plan_release.select_release_plan(
        "0.5.1",
        ["feat(cli)!: change manifest contract"],
        latest_tag="v0.5.1",
    )

    assert plan.should_release is True
    assert plan.version == "1.0.0"
    assert plan.bump == "major"


def test_release_marker_can_force_patch_release() -> None:
    plan_release = load_module()

    plan = plan_release.select_release_plan(
        "0.5.1",
        [
            "fix(installer): make checksum errors clearer\n\n  release: patch",
            "docs: refresh examples",
        ],
        latest_tag="v0.5.1",
    )

    assert plan.should_release is True
    assert plan.version == "0.5.2"
    assert plan.bump == "patch"


def test_manual_force_bump_overrides_commit_messages() -> None:
    plan_release = load_module()

    plan = plan_release.select_release_plan(
        "0.5.1",
        ["docs: refresh examples"],
        force_bump="minor",
        latest_tag="v0.5.1",
    )

    assert plan.should_release is True
    assert plan.version == "0.6.0"
    assert plan.reason == "Manual minor release requested."


def test_manual_exact_version_must_move_forward() -> None:
    plan_release = load_module()

    plan = plan_release.select_release_plan(
        "0.5.1",
        [],
        explicit_version="0.7.0",
        latest_tag="v0.5.1",
    )

    assert plan.should_release is True
    assert plan.version == "0.7.0"
    assert plan.bump == "exact"

    with pytest.raises(ValueError):
        plan_release.select_release_plan(
            "0.5.1",
            [],
            explicit_version="0.5.1",
            latest_tag="v0.5.1",
        )
