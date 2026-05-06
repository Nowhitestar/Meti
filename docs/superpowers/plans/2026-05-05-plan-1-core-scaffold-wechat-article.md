# Plan 1 — Core Scaffold + wechat_article Migration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the v0.2 architecture (`core/` + `providers/` + `scripts/mmp.py`) and migrate the first real provider (`wechat_article`) end-to-end to validate the abstractions.

**Architecture:** Three-layer Shell / Core / Providers. Core is host-agnostic Python (manifest schema, provider registry, credential vault, run lifecycle, platform rules). First-party provider `wechat_article` lives in `providers/wechat_article/` and exercises the full lifecycle (validate → prepare → execute → result/log). Old `scripts/wechat_api_draft.py` becomes `providers/wechat_article/internal/wechat_api.py`.

**Tech Stack:** Python 3.10+, pytest, pyyaml, pyrage (age encryption), argparse (stdlib), dataclasses (stdlib). No PyPI publish.

**Spec reference:** `docs/superpowers/specs/2026-05-05-multi-media-publisher-redesign-design.md` §3, §4, §5, §6, §8, §10.1 (wechat_article row).

---

## File Structure

**Created in this plan:**

```
pyproject.toml                                   # dev tooling config (ruff/mypy/pytest)
core/__init__.py
core/errors.py                                   # MMPError hierarchy
core/host.py                                     # XDG paths + host detection
core/rules.py                                    # PlatformRules + Violation
core/manifest.py                                 # Manifest schema + validate + lock
core/credentials.py                              # CredentialStore + age FileBackend + EnvBackend
core/provider.py                                 # Provider ABC + ProviderRegistry
core/run.py                                      # Run lifecycle + result + log + checkpoint
providers/__init__.py
providers/wechat_article/__init__.py
providers/wechat_article/provider.yaml
providers/wechat_article/provider.py
providers/wechat_article/rules.py
providers/wechat_article/internal/__init__.py
providers/wechat_article/internal/wechat_api.py  # moved from scripts/wechat_api_draft.py
providers/wechat_article/tests/__init__.py
providers/wechat_article/tests/test_provider.py
scripts/mmp.py                                   # CLI entry: validate/publish/setup/list/resume/doctor
tests/__init__.py
tests/core/__init__.py
tests/core/test_errors.py
tests/core/test_host.py
tests/core/test_rules.py
tests/core/test_manifest.py
tests/core/test_credentials.py
tests/core/test_provider.py
tests/core/test_run.py
tests/integration/__init__.py
tests/integration/test_wechat_article_e2e.py
tests/fixtures/longform-wechat.yaml              # minimal valid manifest fixture
tests/fixtures/longform-wechat.body.md
```

**Modified:**

```
.gitignore                                       # add runs/, ~/.config/mmp/ refs (mostly tests)
Makefile                                         # add lint, typecheck, test targets
SKILL.md                                         # update entry to scripts/mmp.py; basic v0.2 description
README.md                                        # brief v0.2 update
docs/HANDOFF.md                                  # status note pointing to spec + this plan
scripts/test_local.py                            # extend smoke to call new mmp.py
```

**Deprecated (kept but marked):**

```
scripts/wechat_api_draft.py                      # thin wrapper calling new provider; deprecated
scripts/publish_manifest.py                      # thin wrapper for `mmp validate`; deprecated
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Modify: `.gitignore`
- Create dirs: `core/`, `providers/`, `tests/core/`, `tests/integration/`, `tests/fixtures/`

- [ ] **Step 1: Create directory skeleton**

```bash
mkdir -p core providers tests/core tests/integration tests/fixtures
touch core/__init__.py providers/__init__.py tests/__init__.py tests/core/__init__.py tests/integration/__init__.py
```

- [ ] **Step 2: Write `pyproject.toml`**

Create `pyproject.toml`:

```toml
[project]
name = "multi-media-publisher"
version = "0.2.0"
description = "Cross-platform content publishing orchestration."
requires-python = ">=3.10"
dependencies = [
    "pyyaml>=6.0",
    "pyrage>=1.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "pytest-cov>=4.1",
    "ruff>=0.4",
    "mypy>=1.8",
    "types-PyYAML",
]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.10"
strict = false
warn_unused_ignores = true
warn_redundant_casts = true
disallow_untyped_defs = true
files = ["core"]

[tool.pytest.ini_options]
testpaths = ["tests", "providers"]
python_files = ["test_*.py"]
addopts = "-q --strict-markers"
```

- [ ] **Step 3: Update `.gitignore`**

Append to `.gitignore`:

```
# v0.2 additions
runs/
.coverage
.pytest_cache/
.mypy_cache/
.ruff_cache/
__pycache__/
*.pyc
```

- [ ] **Step 4: Verify Python and install dev deps**

Run: `python3 --version && python3 -m pip install -e ".[dev]"`
Expected: Python 3.10+; pip install completes.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore core/ providers/ tests/
git commit -m "chore: v0.2 project scaffolding"
```

---

## Task 2: `core/errors.py` — Exception Hierarchy

**Files:**
- Create: `core/errors.py`
- Test: `tests/core/test_errors.py`

- [ ] **Step 1: Write failing test**

`tests/core/test_errors.py`:

```python
import pytest
from core.errors import (
    MMPError,
    ManifestError,
    ProviderNotFoundError,
    MissingCredentialError,
    PlatformRuleViolation,
    ProviderExecutionError,
)


def test_hierarchy():
    assert issubclass(ManifestError, MMPError)
    assert issubclass(ProviderNotFoundError, MMPError)
    assert issubclass(MissingCredentialError, MMPError)
    assert issubclass(PlatformRuleViolation, MMPError)
    assert issubclass(ProviderExecutionError, MMPError)


def test_provider_execution_error_carries_metadata():
    upstream = ValueError("boom")
    err = ProviderExecutionError(
        target="wechat-article",
        step="upload_thumb",
        upstream=upstream,
        retryable=True,
    )
    assert err.target == "wechat-article"
    assert err.step == "upload_thumb"
    assert err.upstream is upstream
    assert err.retryable is True


def test_missing_credential_error_carries_provider_and_keys():
    err = MissingCredentialError(provider="wechat-article", keys=["WECHAT_APP_ID"])
    assert err.provider == "wechat-article"
    assert err.keys == ["WECHAT_APP_ID"]
```

- [ ] **Step 2: Run test (should fail)**

Run: `pytest tests/core/test_errors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.errors'`.

- [ ] **Step 3: Implement `core/errors.py`**

```python
"""Exception hierarchy for multi-media-publisher core."""

from __future__ import annotations


class MMPError(Exception):
    """Base class for all multi-media-publisher errors."""


class ManifestError(MMPError):
    """Manifest schema or validation failure."""


class ProviderNotFoundError(MMPError):
    """Requested provider not registered."""


class MissingCredentialError(MMPError):
    """Required credentials not available in vault or ENV."""

    def __init__(self, provider: str, keys: list[str]) -> None:
        self.provider = provider
        self.keys = keys
        super().__init__(f"missing credentials for {provider}: {keys}")


class PlatformRuleViolation(MMPError):
    """Manifest violates a provider's platform rules at error severity."""


class ProviderExecutionError(MMPError):
    """Provider.execute raised; carries enough metadata for resume."""

    def __init__(
        self,
        target: str,
        step: str,
        upstream: Exception | None = None,
        retryable: bool = False,
    ) -> None:
        self.target = target
        self.step = step
        self.upstream = upstream
        self.retryable = retryable
        msg = f"{target} failed at {step}: {upstream}"
        super().__init__(msg)
```

- [ ] **Step 4: Run test (should pass)**

Run: `pytest tests/core/test_errors.py -v`
Expected: PASS — 3 passed.

- [ ] **Step 5: Commit**

```bash
git add core/errors.py tests/core/test_errors.py
git commit -m "feat(core): add MMPError exception hierarchy"
```

---

## Task 3: `core/host.py` — Path Resolution & Host Detection

**Files:**
- Create: `core/host.py`
- Test: `tests/core/test_host.py`

- [ ] **Step 1: Write failing test**

`tests/core/test_host.py`:

```python
import os
from pathlib import Path

import pytest

from core import host


def test_user_data_dir_default(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    p = host.user_data_dir()
    assert p == tmp_path / ".config" / "mmp"


def test_user_data_dir_xdg_override(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    p = host.user_data_dir()
    assert p == tmp_path / "xdg" / "mmp"


def test_vault_paths(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert host.vault_path() == tmp_path / ".config" / "mmp" / "credentials.json.age"
    assert host.vault_key_path() == tmp_path / ".config" / "mmp" / "age-key.txt"


def test_runs_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("MMP_RUNS_DIR", str(tmp_path / "runs"))
    assert host.runs_dir() == tmp_path / "runs"


def test_detect_host_returns_string():
    h = host.detect_host()
    assert h in {"claude-code", "openclaw", "unknown"}


def test_user_providers_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert host.user_providers_dir() == tmp_path / ".config" / "mmp" / "providers"


def test_settings_path(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert host.settings_path() == tmp_path / ".config" / "mmp" / "settings.toml"
```

- [ ] **Step 2: Run test (should fail)**

Run: `pytest tests/core/test_host.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `core/host.py`**

```python
"""Host environment detection and XDG-compliant path resolution.

Single source of truth for any filesystem path that depends on user environment.
Pure functions: no mutation, no I/O beyond os.environ reads.
"""

from __future__ import annotations

import os
from pathlib import Path


_APP = "mmp"


def user_data_dir() -> Path:
    """Resolve user config root: $XDG_CONFIG_HOME/mmp or ~/.config/mmp."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / _APP


def vault_path() -> Path:
    return user_data_dir() / "credentials.json.age"


def vault_key_path() -> Path:
    return user_data_dir() / "age-key.txt"


def user_providers_dir() -> Path:
    return user_data_dir() / "providers"


def settings_path() -> Path:
    return user_data_dir() / "settings.toml"


def runs_dir() -> Path:
    """Where run dirs are written. ENV override > skill-relative default."""
    env = os.environ.get("MMP_RUNS_DIR")
    if env:
        return Path(env)
    # default: <skill_root>/runs
    return Path(__file__).resolve().parent.parent / "runs"


def detect_host() -> str:
    """Best-effort host detection. Used only for telemetry in result.json."""
    if os.environ.get("CLAUDE_CODE_VERSION") or os.environ.get("CLAUDECODE"):
        return "claude-code"
    if os.environ.get("OPENCLAW_VERSION") or Path.home().joinpath(".openclaw").exists():
        return "openclaw"
    return "unknown"
```

- [ ] **Step 4: Run test (should pass)**

Run: `pytest tests/core/test_host.py -v`
Expected: PASS — 7 passed.

- [ ] **Step 5: Commit**

```bash
git add core/host.py tests/core/test_host.py
git commit -m "feat(core): add host module for XDG paths and host detection"
```

---

## Task 4: `core/rules.py` — PlatformRules & Violation

**Files:**
- Create: `core/rules.py`
- Test: `tests/core/test_rules.py`

- [ ] **Step 1: Write failing test**

`tests/core/test_rules.py`:

```python
from core.rules import PlatformRules, Severity, Violation


def test_violation_default_severity_error():
    v = Violation(code="TITLE_TOO_LONG", message="title exceeds 20")
    assert v.severity == Severity.error


def test_lint_title_max(simple_manifest):
    rules = PlatformRules(title_max=10)
    m = simple_manifest(title="this title is way too long for the platform")
    violations = rules.lint(m, target_name="xiaohongshu")
    assert any(v.code == "TITLE_TOO_LONG" for v in violations)


def test_lint_image_count_min(simple_manifest):
    rules = PlatformRules(image_count_min=3)
    m = simple_manifest(images=["a.png"])
    violations = rules.lint(m, target_name="xiaohongshu")
    assert any(v.code == "IMAGE_COUNT_BELOW_MIN" for v in violations)


def test_lint_passes_when_within_limits(simple_manifest):
    rules = PlatformRules(title_max=20, image_count_min=1, image_count_max=9)
    m = simple_manifest(title="short", images=["a.png", "b.png"])
    violations = rules.lint(m, target_name="xiaohongshu")
    assert violations == []


def test_extra_lints_invoked(simple_manifest):
    def custom(m, target_name):
        return [Violation(code="CUSTOM", message="x", severity=Severity.warning)]

    rules = PlatformRules(extra_lints=[custom])
    m = simple_manifest()
    violations = rules.lint(m, target_name="any")
    assert any(v.code == "CUSTOM" for v in violations)
```

Add fixture `tests/conftest.py`:

```python
"""Shared pytest fixtures for core tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest


@pytest.fixture
def simple_manifest():
    """Returns a builder that produces a minimal Manifest-shaped object.

    The real Manifest class arrives in Task 5; this stub matches its surface
    for rule-lint testing only. Once Task 5 lands, this fixture is replaced
    by importing the real class.
    """
    from core.manifest import Manifest, Target  # available after Task 5

    def build(
        title: str = "hello",
        body: str = "body",
        images: list[str] | None = None,
        tags: list[str] | None = None,
        type_: str = "image-post",
    ) -> Manifest:
        return Manifest(
            schema_version="0.2",
            type=type_,
            title=title,
            body=body,
            mode="dry-run",
            targets=[Target(name="xiaohongshu")],
            images=images or [],
            tags=tags or [],
        )

    return build
```

> **Note:** `tests/conftest.py` references `core.manifest.Manifest` which arrives in Task 5. Tests in Task 4 only test `PlatformRules` directly without the fixture for the simplest cases. Defer fixture-using tests until Task 5 lands; for now the rule tests below avoid the fixture.

Replace `tests/core/test_rules.py` with the fixture-free form for Task 4 ONLY:

```python
from types import SimpleNamespace

from core.rules import PlatformRules, Severity, Violation


def _stub_manifest(**overrides):
    base = dict(title="hello", body="body", images=[], tags=[])
    base.update(overrides)
    return SimpleNamespace(**base)


def test_violation_default_severity_error():
    v = Violation(code="X", message="x")
    assert v.severity == Severity.error


def test_lint_title_max():
    rules = PlatformRules(title_max=10)
    m = _stub_manifest(title="this is too long for the limit")
    vs = rules.lint(m, target_name="xhs")
    assert any(v.code == "TITLE_TOO_LONG" for v in vs)


def test_lint_image_count_min():
    rules = PlatformRules(image_count_min=3)
    m = _stub_manifest(images=["a.png"])
    vs = rules.lint(m, target_name="xhs")
    assert any(v.code == "IMAGE_COUNT_BELOW_MIN" for v in vs)


def test_lint_image_count_max():
    rules = PlatformRules(image_count_max=2)
    m = _stub_manifest(images=["a.png", "b.png", "c.png"])
    vs = rules.lint(m, target_name="xhs")
    assert any(v.code == "IMAGE_COUNT_ABOVE_MAX" for v in vs)


def test_lint_clean_passes():
    rules = PlatformRules(title_max=20, image_count_min=1, image_count_max=9)
    m = _stub_manifest(title="short", images=["a.png"])
    assert rules.lint(m, target_name="xhs") == []


def test_extra_lints_invoked():
    def custom(m, target_name):
        return [Violation(code="CUSTOM", message="x", severity=Severity.warning)]

    rules = PlatformRules(extra_lints=[custom])
    m = _stub_manifest()
    vs = rules.lint(m, target_name="any")
    assert any(v.code == "CUSTOM" for v in vs)
```

- [ ] **Step 2: Run test (should fail)**

Run: `pytest tests/core/test_rules.py -v`
Expected: FAIL — `ModuleNotFoundError: core.rules`.

- [ ] **Step 3: Implement `core/rules.py`**

```python
"""Platform rules-as-code: declarative per-platform constraints + lint."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol


class Severity(str, Enum):
    error = "error"
    warning = "warning"
    info = "info"


@dataclass
class Violation:
    code: str
    message: str
    severity: Severity = Severity.error
    target: str | None = None
    field_path: str | None = None


class _ManifestLike(Protocol):
    title: str
    body: str
    images: list[str]
    tags: list[str]


LintFn = Callable[[Any, str], list[Violation]]


@dataclass
class PlatformRules:
    title_max: int | None = None
    body_max: int | None = None
    image_count_min: int | None = None
    image_count_max: int | None = None
    image_aspect_ratios: list[str] | None = None
    tag_max: int | None = None
    cover_required: bool = False
    cover_aspect_ratios: list[str] | None = None
    extra_lints: list[LintFn] = field(default_factory=list)

    def lint(self, manifest: _ManifestLike, target_name: str) -> list[Violation]:
        violations: list[Violation] = []

        title = getattr(manifest, "title", "") or ""
        body = getattr(manifest, "body", "") or ""
        images = getattr(manifest, "images", []) or []
        tags = getattr(manifest, "tags", []) or []

        if self.title_max is not None and len(title) > self.title_max:
            violations.append(
                Violation(
                    code="TITLE_TOO_LONG",
                    message=f"title length {len(title)} exceeds {self.title_max}",
                    target=target_name,
                    field_path="title",
                )
            )
        if self.body_max is not None and len(body) > self.body_max:
            violations.append(
                Violation(
                    code="BODY_TOO_LONG",
                    message=f"body length {len(body)} exceeds {self.body_max}",
                    target=target_name,
                    field_path="body",
                )
            )
        if self.image_count_min is not None and len(images) < self.image_count_min:
            violations.append(
                Violation(
                    code="IMAGE_COUNT_BELOW_MIN",
                    message=f"image count {len(images)} below min {self.image_count_min}",
                    target=target_name,
                    field_path="assets.images",
                )
            )
        if self.image_count_max is not None and len(images) > self.image_count_max:
            violations.append(
                Violation(
                    code="IMAGE_COUNT_ABOVE_MAX",
                    message=f"image count {len(images)} above max {self.image_count_max}",
                    target=target_name,
                    field_path="assets.images",
                )
            )
        if self.tag_max is not None and len(tags) > self.tag_max:
            violations.append(
                Violation(
                    code="TAG_COUNT_ABOVE_MAX",
                    message=f"tag count {len(tags)} above max {self.tag_max}",
                    target=target_name,
                    field_path="tags",
                )
            )

        for fn in self.extra_lints:
            violations.extend(fn(manifest, target_name))

        return violations
```

- [ ] **Step 4: Run test (should pass)**

Run: `pytest tests/core/test_rules.py -v`
Expected: PASS — 6 passed.

- [ ] **Step 5: Commit**

```bash
git add core/rules.py tests/core/test_rules.py
git commit -m "feat(core): add PlatformRules + Violation"
```

---

## Task 5: `core/manifest.py` — Schema, Target Normalization, Validation, Lock

**Files:**
- Create: `core/manifest.py`
- Test: `tests/core/test_manifest.py`
- Create: `tests/fixtures/longform-wechat.yaml`
- Create: `tests/fixtures/longform-wechat.body.md`

- [ ] **Step 1: Create fixture files**

`tests/fixtures/longform-wechat.body.md`:

```markdown
# Hello

Some body text.
```

`tests/fixtures/longform-wechat.yaml`:

```yaml
schema_version: "0.2"
type: longform
title: "Test Article"
body: ./longform-wechat.body.md
mode: dry-run
language: zh-CN
targets:
  - wechat-article
  - target: x-article
    mode: draft
    account: lewis
assets:
  cover: ./cover.png
tags:
  - test
```

- [ ] **Step 2: Write failing test**

`tests/core/test_manifest.py`:

```python
from pathlib import Path

import pytest

from core.errors import ManifestError
from core.manifest import Manifest, Target, load_manifest


FIXTURE = Path(__file__).parent.parent / "fixtures" / "longform-wechat.yaml"


def test_load_minimal(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(
        'schema_version: "0.2"\n'
        "type: image-post\n"
        'title: "Hi"\n'
        'body: "inline content"\n'
        "mode: dry-run\n"
        "targets:\n"
        "  - xiaohongshu\n"
    )
    m = load_manifest(p)
    assert m.schema_version == "0.2"
    assert m.type == "image-post"
    assert m.title == "Hi"
    assert m.body == "inline content"
    assert m.mode == "dry-run"
    assert len(m.targets) == 1
    assert m.targets[0].name == "xiaohongshu"
    assert m.targets[0].mode == "dry-run"  # inherits top-level
    assert m.targets[0].account == "default"


def test_load_fixture_full_form():
    m = load_manifest(FIXTURE)
    assert m.type == "longform"
    assert m.title == "Test Article"
    # body got resolved from path
    assert m.body.startswith("# Hello")
    assert m.tags == ["test"]
    assert len(m.targets) == 2

    t1 = m.targets[0]
    assert t1.name == "wechat-article"
    assert t1.mode == "dry-run"  # inherited
    assert t1.account == "default"

    t2 = m.targets[1]
    assert t2.name == "x-article"
    assert t2.mode == "draft"  # explicit override
    assert t2.account == "lewis"


def test_missing_required_field_raises(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text("schema_version: '0.2'\ntype: longform\nmode: dry-run\ntargets: [foo]\n")
    with pytest.raises(ManifestError, match="title"):
        load_manifest(p)


def test_invalid_mode_raises(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(
        'schema_version: "0.2"\ntype: longform\ntitle: x\nbody: x\n'
        'mode: nuke\ntargets: [wechat-article]\n'
    )
    with pytest.raises(ManifestError, match="mode"):
        load_manifest(p)


def test_invalid_type_raises(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(
        'schema_version: "0.2"\ntype: weird\ntitle: x\nbody: x\n'
        'mode: dry-run\ntargets: [wechat-article]\n'
    )
    with pytest.raises(ManifestError, match="type"):
        load_manifest(p)


def test_to_lock_dict_normalized():
    m = load_manifest(FIXTURE)
    lock = m.to_lock_dict()
    assert lock["schema_version"] == "0.2"
    assert lock["mode"] == "dry-run"
    # targets always full-form in lock
    assert all(isinstance(t, dict) for t in lock["targets"])
    assert lock["targets"][0]["name"] == "wechat-article"
    assert lock["targets"][0]["mode"] == "dry-run"
    assert lock["targets"][0]["account"] == "default"


def test_target_short_form_inherits_top_mode(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(
        'schema_version: "0.2"\ntype: longform\ntitle: x\nbody: x\n'
        'mode: draft\ntargets: [wechat-article, x-article]\n'
    )
    m = load_manifest(p)
    assert all(t.mode == "draft" for t in m.targets)


def test_defaults_block_applied(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(
        'schema_version: "0.2"\ntype: longform\ntitle: x\nbody: x\n'
        'mode: dry-run\ndefaults:\n  account: lewis\n  options:\n    digest: hi\n'
        'targets:\n  - wechat-article\n'
    )
    m = load_manifest(p)
    assert m.targets[0].account == "lewis"
    assert m.targets[0].options == {"digest": "hi"}
```

- [ ] **Step 3: Run test (should fail)**

Run: `pytest tests/core/test_manifest.py -v`
Expected: FAIL — `ModuleNotFoundError: core.manifest`.

- [ ] **Step 4: Implement `core/manifest.py`**

```python
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
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
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
    if s.startswith("./") or s.startswith("../") or s.endswith(".md"):
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
```

- [ ] **Step 5: Run test (should pass)**

Run: `pytest tests/core/test_manifest.py -v`
Expected: PASS — 8 passed.

- [ ] **Step 6: Commit**

```bash
git add core/manifest.py tests/core/test_manifest.py tests/fixtures/
git commit -m "feat(core): add Manifest schema, loading, normalization"
```

---

## Task 6: `core/credentials.py` — CredentialStore + age FileBackend + EnvBackend

**Files:**
- Create: `core/credentials.py`
- Test: `tests/core/test_credentials.py`

- [ ] **Step 1: Write failing test**

`tests/core/test_credentials.py`:

```python
import json
import os
from pathlib import Path

import pytest

from core.credentials import CredentialStore, EnvBackend, FileBackend
from core.errors import MissingCredentialError


@pytest.fixture
def isolated_vault(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("MMP_VAULT_KEY", raising=False)
    return tmp_path


def test_env_vault_key_overrides_file(monkeypatch, tmp_path):
    """MMP_VAULT_KEY ENV is the canonical source when set; file is fallback."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    # generate a key out-of-band
    import pyrage
    identity = pyrage.x25519.Identity.generate()
    monkeypatch.setenv("MMP_VAULT_KEY", str(identity))

    backend = FileBackend()
    store = CredentialStore(backend=backend)
    store.set("p", "default", {"K": "v"})

    # Key file should NOT have been created when ENV is set
    assert not (tmp_path / ".config" / "mmp" / "age-key.txt").exists()

    # And we can still read back
    assert store.get("p", "default") == {"K": "v"}


def test_file_backend_roundtrip(isolated_vault):
    backend = FileBackend()
    store = CredentialStore(backend=backend)
    store.set("wechat-article", "default", {"WECHAT_APP_ID": "wx", "WECHAT_APP_SECRET": "s"})

    out = store.get("wechat-article", "default")
    assert out == {"WECHAT_APP_ID": "wx", "WECHAT_APP_SECRET": "s"}


def test_file_backend_persists_encrypted(isolated_vault):
    backend = FileBackend()
    store = CredentialStore(backend=backend)
    store.set("wechat-article", "default", {"WECHAT_APP_ID": "wx"})

    vault_file = isolated_vault / ".config" / "mmp" / "credentials.json.age"
    assert vault_file.exists()
    raw = vault_file.read_bytes()
    assert b"WECHAT_APP_ID" not in raw  # encrypted, not visible


def test_get_missing_raises(isolated_vault):
    store = CredentialStore(backend=FileBackend())
    with pytest.raises(MissingCredentialError):
        store.get("wechat-article", "default")


def test_env_overrides_vault(isolated_vault, monkeypatch):
    store = CredentialStore(backend=FileBackend())
    store.set("wechat-article", "default", {"WECHAT_APP_ID": "from_vault"})
    monkeypatch.setenv("WECHAT_APP_ID", "from_env")

    out = store.get("wechat-article", "default")
    assert out["WECHAT_APP_ID"] == "from_env"


def test_list_accounts(isolated_vault):
    store = CredentialStore(backend=FileBackend())
    store.set("wechat-article", "default", {"K": "v"})
    store.set("wechat-article", "lewis", {"K": "v2"})
    store.set("xiaohongshu", "default", {"K": "v3"})

    assert sorted(store.list_accounts("wechat-article")) == ["default", "lewis"]
    assert sorted(store.list_accounts(None)) == [
        "wechat-article:default",
        "wechat-article:lewis",
        "xiaohongshu:default",
    ]


def test_delete(isolated_vault):
    store = CredentialStore(backend=FileBackend())
    store.set("wechat-article", "default", {"K": "v"})
    store.delete("wechat-article", "default")
    with pytest.raises(MissingCredentialError):
        store.get("wechat-article", "default")


def test_env_only_backend(monkeypatch):
    monkeypatch.setenv("WECHAT_APP_ID", "ww")
    monkeypatch.setenv("WECHAT_APP_SECRET", "ss")
    store = CredentialStore(backend=EnvBackend())
    out = store.get("wechat-article", "default")
    assert out == {"WECHAT_APP_ID": "ww", "WECHAT_APP_SECRET": "ss"}


def test_required_keys_filtering(isolated_vault):
    store = CredentialStore(backend=FileBackend())
    store.set("wechat-article", "default", {"WECHAT_APP_ID": "wx", "EXTRA": "x"})
    out = store.get("wechat-article", "default", required_keys=["WECHAT_APP_ID"])
    assert out == {"WECHAT_APP_ID": "wx"}
```

- [ ] **Step 2: Run test (should fail)**

Run: `pytest tests/core/test_credentials.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `core/credentials.py`**

```python
"""Credential vault: encrypted file backend (age) + ENV backend.

Vault layout (decrypted JSON):
  {
    "version": 1,
    "accounts": {
        "<provider>:<account>": {"KEY": "value", ...},
        ...
    }
  }
"""

from __future__ import annotations

import json
import os
import secrets
from abc import ABC, abstractmethod
from pathlib import Path

import pyrage

from core import host
from core.errors import MissingCredentialError


_VAULT_VERSION = 1


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _read_or_create_key(key_path: Path) -> tuple[pyrage.x25519.Identity, str]:
    """Return (identity, recipient_string).

    Priority:
      1. ENV MMP_VAULT_KEY (canonical for CI / one-shot use)
      2. existing key file at key_path
      3. generate a new key file (first use)
    """
    env_key = os.environ.get("MMP_VAULT_KEY", "").strip()
    if env_key:
        identity = pyrage.x25519.Identity.from_str(env_key)
        return identity, str(identity.to_public())
    if not key_path.exists():
        identity = pyrage.x25519.Identity.generate()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text(str(identity), encoding="utf-8")
        os.chmod(key_path, 0o600)
        return identity, str(identity.to_public())
    text = key_path.read_text(encoding="utf-8").strip()
    identity = pyrage.x25519.Identity.from_str(text)
    return identity, str(identity.to_public())


class Backend(ABC):
    @abstractmethod
    def read_all(self) -> dict[str, dict[str, str]]: ...

    @abstractmethod
    def write_all(self, accounts: dict[str, dict[str, str]]) -> None: ...


class FileBackend(Backend):
    """Age-encrypted JSON vault at host.vault_path()."""

    def __init__(self) -> None:
        self._vault = host.vault_path()
        self._key = host.vault_key_path()

    def read_all(self) -> dict[str, dict[str, str]]:
        if not self._vault.exists():
            return {}
        identity, _ = _read_or_create_key(self._key)
        ciphertext = self._vault.read_bytes()
        plaintext = pyrage.decrypt(ciphertext, [identity])
        data = json.loads(plaintext.decode("utf-8"))
        if not isinstance(data, dict):
            return {}
        return data.get("accounts", {})

    def write_all(self, accounts: dict[str, dict[str, str]]) -> None:
        _ensure_dir(self._vault.parent)
        identity, recipient_str = _read_or_create_key(self._key)
        recipient = pyrage.x25519.Recipient.from_str(recipient_str)
        body = json.dumps(
            {"version": _VAULT_VERSION, "accounts": accounts}, ensure_ascii=False
        ).encode("utf-8")
        ciphertext = pyrage.encrypt(body, [recipient])
        self._vault.write_bytes(ciphertext)
        os.chmod(self._vault, 0o600)


class EnvBackend(Backend):
    """Read-only backend that pulls from os.environ. Used in CI."""

    def read_all(self) -> dict[str, dict[str, str]]:
        return {}

    def write_all(self, accounts: dict[str, dict[str, str]]) -> None:
        raise NotImplementedError("EnvBackend is read-only")


class CredentialStore:
    """Vault facade. ENV always overrides vault."""

    def __init__(self, backend: Backend | None = None) -> None:
        self._backend: Backend = backend or FileBackend()

    def set(self, provider: str, account: str, values: dict[str, str]) -> None:
        all_ = self._backend.read_all()
        all_[f"{provider}:{account}"] = dict(values)
        self._backend.write_all(all_)

    def get(
        self,
        provider: str,
        account: str = "default",
        required_keys: list[str] | None = None,
    ) -> dict[str, str]:
        key = f"{provider}:{account}"
        all_ = self._backend.read_all()
        vault_values = dict(all_.get(key, {}))

        # ENV override: any matching key in os.environ wins
        merged = dict(vault_values)
        for k in list(merged.keys()):
            if k in os.environ:
                merged[k] = os.environ[k]

        # Also pick up env-only keys when required_keys is given
        if required_keys:
            for k in required_keys:
                if k not in merged and k in os.environ:
                    merged[k] = os.environ[k]
            missing = [k for k in required_keys if k not in merged]
            if missing:
                raise MissingCredentialError(provider=provider, keys=missing)
            return {k: merged[k] for k in required_keys}

        if not merged:
            raise MissingCredentialError(provider=provider, keys=["*"])
        return merged

    def list_accounts(self, provider: str | None = None) -> list[str]:
        all_ = self._backend.read_all()
        if provider is None:
            return sorted(all_.keys())
        prefix = f"{provider}:"
        return [k.removeprefix(prefix) for k in sorted(all_.keys()) if k.startswith(prefix)]

    def delete(self, provider: str, account: str) -> None:
        all_ = self._backend.read_all()
        all_.pop(f"{provider}:{account}", None)
        self._backend.write_all(all_)
```

- [ ] **Step 4: Run test (should pass)**

Run: `pytest tests/core/test_credentials.py -v`
Expected: PASS — 9 passed.

- [ ] **Step 5: Commit**

```bash
git add core/credentials.py tests/core/test_credentials.py
git commit -m "feat(core): add CredentialStore with age FileBackend + EnvBackend"
```

---

## Task 7: `core/provider.py` — Provider ABC + Registry

**Files:**
- Create: `core/provider.py`
- Test: `tests/core/test_provider.py`

- [ ] **Step 1: Write failing test**

`tests/core/test_provider.py`:

```python
from pathlib import Path

import pytest
import yaml

from core.errors import ProviderNotFoundError
from core.provider import (
    CredentialSpec,
    PreparedPayload,
    Provider,
    ProviderRegistry,
    ExecutionResult,
    HealthStatus,
    ValidationResult,
)
from core.rules import PlatformRules


def _write_provider_dir(root: Path, name: str, snake: str, body: str | None = None) -> Path:
    """Write a fake provider package to disk and return its dir."""
    pdir = root / snake
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "__init__.py").write_text("")
    (pdir / "provider.yaml").write_text(
        yaml.safe_dump(
            {
                "name": name,
                "display_name": name,
                "media_types": ["longform"],
                "capabilities": {"draft": True, "publish": False, "schedule": False},
                "required_credentials": [
                    {"key": "FAKE_KEY", "description": "x", "secret": True}
                ],
                "entry": "provider:FakeProvider",
                "schema_version": 1,
            }
        ),
        encoding="utf-8",
    )
    pdir_body = body or '''
from core.provider import Provider
from core.rules import PlatformRules


class FakeProvider(Provider):
    name = "{name}"
    display_name = "{name}"
    media_types = ["longform"]
    capabilities = {{"draft": True, "publish": False, "schedule": False}}
    required_credentials = []
    platform_rules = PlatformRules()

    def validate(self, manifest, target):
        return None

    def prepare(self, manifest, target, run_dir):
        return None

    def execute(self, run_dir, target, mode, credentials):
        return None
'''.format(name=name)
    (pdir / "provider.py").write_text(pdir_body)
    return pdir


def test_registry_discovers_bundled(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_provider_dir(bundled, name="fake-one", snake="fake_one")

    reg = ProviderRegistry(bundled_dir=bundled, user_dir=tmp_path / "no_user")
    reg.discover()

    info = reg.list()
    assert any(i.name == "fake-one" for i in info)


def test_registry_resolve_by_kebab_name(tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_provider_dir(bundled, name="fake-two", snake="fake_two")

    reg = ProviderRegistry(bundled_dir=bundled, user_dir=tmp_path / "no_user")
    reg.discover()

    p = reg.resolve("fake-two")
    assert p.name == "fake-two"


def test_resolve_missing_raises(tmp_path):
    reg = ProviderRegistry(bundled_dir=tmp_path / "empty", user_dir=tmp_path / "empty2")
    reg.discover()
    with pytest.raises(ProviderNotFoundError):
        reg.resolve("does-not-exist")


def test_user_provider_overrides_bundled(tmp_path):
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    bundled.mkdir()
    user.mkdir()

    _write_provider_dir(bundled, name="dup", snake="dup_b")
    _write_provider_dir(
        user,
        name="dup",
        snake="dup_u",
        body=(
            "from core.provider import Provider\n"
            "from core.rules import PlatformRules\n"
            "class FakeProvider(Provider):\n"
            "    name = 'dup'\n"
            "    display_name = 'user-version'\n"
            "    media_types = ['longform']\n"
            "    capabilities = {'draft': True, 'publish': False, 'schedule': False}\n"
            "    required_credentials = []\n"
            "    platform_rules = PlatformRules()\n"
            "    def validate(self, m, t): return None\n"
            "    def prepare(self, m, t, r): return None\n"
            "    def execute(self, r, t, m, c): return None\n"
        ),
    )

    reg = ProviderRegistry(bundled_dir=bundled, user_dir=user)
    reg.discover(trust_user=True)

    p = reg.resolve("dup")
    assert p.display_name == "user-version"


def test_filter_by_media_type(tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_provider_dir(bundled, name="lf-only", snake="lf_only")

    reg = ProviderRegistry(bundled_dir=bundled, user_dir=tmp_path / "x")
    reg.discover()

    longform = reg.list(media_type="longform")
    assert any(i.name == "lf-only" for i in longform)

    images = reg.list(media_type="image-post")
    assert all(i.name != "lf-only" for i in images)
```

- [ ] **Step 2: Run test (should fail)**

Run: `pytest tests/core/test_provider.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `core/provider.py`**

```python
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
from core.rules import PlatformRules


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
    violations: list = field(default_factory=list)


@dataclass
class PreparedPayload:
    pack_dir: Path
    payload_path: Path
    extras: dict[str, Path] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    status: str  # "ok" | "failed" | "skipped" | "partial"
    mode_actual: str  # "dry-run" | "draft-local" | "draft-platform" | "published"
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
        assert spec and spec.loader
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
```

- [ ] **Step 4: Run test (should pass)**

Run: `pytest tests/core/test_provider.py -v`
Expected: PASS — 5 passed.

- [ ] **Step 5: Commit**

```bash
git add core/provider.py tests/core/test_provider.py
git commit -m "feat(core): add Provider ABC and ProviderRegistry"
```

---

## Task 8: `core/run.py` — Run Lifecycle, result.json, publish-log.md

**Files:**
- Create: `core/run.py`
- Test: `tests/core/test_run.py`

- [ ] **Step 1: Write failing test**

`tests/core/test_run.py`:

```python
import json
from pathlib import Path

import pytest

from core.run import Run, slugify


def test_slugify_basic():
    assert slugify("Hello World") == "hello-world"
    assert slugify("AI 创业的三个误区").startswith("ai-")
    assert slugify("a" * 100).__len__() <= 40


def test_run_create_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MMP_RUNS_DIR", str(tmp_path / "runs"))
    r = Run.create(title="Hello", mmp_version="0.2.0", host="claude-code", mode="draft")
    assert r.dir.exists()
    assert (r.dir / "packs").exists()
    assert (r.dir / "checkpoints").exists()
    assert (r.dir / "artifacts").exists()
    assert "hello" in r.dir.name


def test_result_serialization(tmp_path, monkeypatch):
    monkeypatch.setenv("MMP_RUNS_DIR", str(tmp_path / "runs"))
    r = Run.create(title="X", mmp_version="0.2.0", host="cc", mode="draft")
    r.add_target_result(
        name="wechat-article",
        account="default",
        status="ok",
        mode_actual="draft-platform",
        external_id="m_123",
        draft_url=None,
    )
    r.finalize()
    data = json.loads((r.dir / "result.json").read_text())
    assert data["mode"] == "draft"
    assert data["targets"][0]["name"] == "wechat-article"
    assert data["targets"][0]["status"] == "ok"
    assert data["targets"][0]["external_id"] == "m_123"


def test_log_append(tmp_path, monkeypatch):
    monkeypatch.setenv("MMP_RUNS_DIR", str(tmp_path / "runs"))
    r = Run.create(title="X", mmp_version="0.2.0", host="cc", mode="draft")
    r.log("RUN_START", run_id=r.run_id)
    r.log("PREPARE_OK", target="wechat-article")
    text = (r.dir / "publish-log.md").read_text()
    assert "RUN_START" in text
    assert "PREPARE_OK" in text


def test_checkpoint_write_read(tmp_path, monkeypatch):
    monkeypatch.setenv("MMP_RUNS_DIR", str(tmp_path / "runs"))
    r = Run.create(title="X", mmp_version="0.2.0", host="cc", mode="draft")
    r.checkpoint("wechat-article", step="thumb_uploaded", external_ids={"thumb_id": "t1"})
    cp = r.read_checkpoint("wechat-article")
    assert cp["step"] == "thumb_uploaded"
    assert cp["external_ids"]["thumb_id"] == "t1"


def test_resume_loads_existing_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MMP_RUNS_DIR", str(tmp_path / "runs"))
    r = Run.create(title="Y", mmp_version="0.2.0", host="cc", mode="draft")
    r.checkpoint("x-article", step="prepared")
    run_dir = r.dir

    r2 = Run.from_dir(run_dir)
    assert r2.run_id == r.run_id
    assert r2.read_checkpoint("x-article")["step"] == "prepared"
```

- [ ] **Step 2: Run test (should fail)**

Run: `pytest tests/core/test_run.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `core/run.py`**

```python
"""Run lifecycle: directory creation, checkpoints, result.json, publish-log.md."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import host


_RESULT_SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _now_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def slugify(text: str, max_len: int = 40) -> str:
    """ASCII-friendly lowercase slug. Non-ASCII collapse to hyphens; preserves
    ASCII alphanumerics."""
    s = (text or "").lower().strip()
    s = re.sub(r"[^\w\s-]+", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if not s:
        s = "untitled"
    return s[:max_len].rstrip("-")


@dataclass
class _TargetResult:
    name: str
    account: str
    status: str
    mode_actual: str
    external_id: str | None = None
    draft_url: str | None = None
    started_at: str = field(default_factory=_now_iso)
    completed_at: str | None = None
    error: str | None = None
    violations: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Run:
    run_id: str
    dir: Path
    mode: str
    mmp_version: str
    host: str
    started_at: str = field(default_factory=_now_iso)
    completed_at: str | None = None
    targets: list[_TargetResult] = field(default_factory=list)

    @classmethod
    def create(cls, title: str, mmp_version: str, host: str, mode: str) -> "Run":
        rid = f"{_now_id()}-{slugify(title)}"
        d = host_runs_dir() / rid
        d.mkdir(parents=True, exist_ok=True)
        for sub in ("packs", "checkpoints", "artifacts"):
            (d / sub).mkdir(exist_ok=True)
        run = cls(run_id=rid, dir=d, mode=mode, mmp_version=mmp_version, host=host)
        run.log("RUN_START", run_id=rid, mode=mode)
        return run

    @classmethod
    def from_dir(cls, run_dir: Path) -> "Run":
        # Reconstruct minimal state from disk (used for resume).
        rid = run_dir.name
        mode = "draft"
        # Try result.json if present
        rp = run_dir / "result.json"
        if rp.exists():
            data = json.loads(rp.read_text(encoding="utf-8"))
            mode = data.get("mode", mode)
        return cls(run_id=rid, dir=run_dir, mode=mode, mmp_version="?", host="?")

    def add_target_result(
        self,
        name: str,
        account: str,
        status: str,
        mode_actual: str,
        external_id: str | None = None,
        draft_url: str | None = None,
        error: str | None = None,
        violations: list[dict[str, Any]] | None = None,
    ) -> None:
        self.targets.append(
            _TargetResult(
                name=name,
                account=account,
                status=status,
                mode_actual=mode_actual,
                external_id=external_id,
                draft_url=draft_url,
                completed_at=_now_iso(),
                error=error,
                violations=violations or [],
            )
        )

    def log(self, event: str, **kwargs: Any) -> None:
        line_parts = [_now_iso(), event]
        for k, v in kwargs.items():
            line_parts.append(f"{k}={v}")
        line = "  ".join(line_parts)
        log_path = self.dir / "publish-log.md"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def checkpoint(self, target: str, step: str, **extras: Any) -> None:
        cp_dir = self.dir / "checkpoints"
        cp_dir.mkdir(exist_ok=True)
        path = cp_dir / f"{target}.checkpoint.json"
        payload = {
            "target": target,
            "step": step,
            "started_at": _now_iso(),
            "external_ids": extras.pop("external_ids", {}),
            "next_step": extras.pop("next_step", None),
            **extras,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def read_checkpoint(self, target: str) -> dict[str, Any] | None:
        path = self.dir / "checkpoints" / f"{target}.checkpoint.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def finalize(self) -> None:
        self.completed_at = _now_iso()
        result = {
            "run_id": self.run_id,
            "schema_version": _RESULT_SCHEMA_VERSION,
            "manifest_path": "manifest.yaml",
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "mode": self.mode,
            "host": self.host,
            "mmp_version": self.mmp_version,
            "targets": [t.__dict__ for t in self.targets],
        }
        (self.dir / "result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        overall = "ok" if all(t.status == "ok" for t in self.targets) else "partial"
        self.log("RUN_DONE", overall=overall)


def host_runs_dir() -> Path:
    d = host.runs_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d
```

- [ ] **Step 4: Run test (should pass)**

Run: `pytest tests/core/test_run.py -v`
Expected: PASS — 6 passed.

- [ ] **Step 5: Commit**

```bash
git add core/run.py tests/core/test_run.py
git commit -m "feat(core): add Run lifecycle with result/log/checkpoint"
```

---

## Task 9: `providers/wechat_article` Scaffold

**Files:**
- Create: `providers/wechat_article/__init__.py`
- Create: `providers/wechat_article/provider.yaml`
- Create: `providers/wechat_article/internal/__init__.py`
- Create: `providers/wechat_article/tests/__init__.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p providers/wechat_article/internal providers/wechat_article/tests
touch providers/wechat_article/__init__.py
touch providers/wechat_article/internal/__init__.py
touch providers/wechat_article/tests/__init__.py
```

- [ ] **Step 2: Write `providers/wechat_article/provider.yaml`**

```yaml
name: wechat-article
display_name: 微信公众号文章
media_types:
  - longform
capabilities:
  draft: true
  publish: false
  schedule: false
required_credentials:
  - key: WECHAT_APP_ID
    description: "WeChat Official Account AppID"
    secret: false
    setup_hint: "From mp.weixin.qq.com → 设置与开发 → 基本配置"
  - key: WECHAT_APP_SECRET
    description: "WeChat Official Account AppSecret"
    secret: true
    setup_hint: "Same page as AppID; reset if forgotten"
entry: provider:WeChatArticleProvider
schema_version: 1
```

- [ ] **Step 3: Commit**

```bash
git add providers/wechat_article/__init__.py providers/wechat_article/provider.yaml \
        providers/wechat_article/internal/__init__.py providers/wechat_article/tests/__init__.py
git commit -m "feat(providers): scaffold wechat_article provider"
```

---

## Task 10: Move WeChat API Helper to Provider Internal

**Files:**
- Create: `providers/wechat_article/internal/wechat_api.py` (move from `scripts/wechat_api_draft.py`)
- Modify: `scripts/wechat_api_draft.py` (becomes thin wrapper, deprecated)

- [ ] **Step 1: Read existing `scripts/wechat_api_draft.py`**

Run: `wc -l scripts/wechat_api_draft.py`
Expected: ~280 lines (per HANDOFF section 8871 bytes).

- [ ] **Step 2: Move file**

```bash
git mv scripts/wechat_api_draft.py providers/wechat_article/internal/wechat_api.py
```

- [ ] **Step 3: Refactor module to expose pure functions**

Edit `providers/wechat_article/internal/wechat_api.py`:
- Remove `if __name__ == "__main__":` block and argparse usage
- Keep public functions as a clean Python API:
  - `get_access_token(app_id: str, app_secret: str) -> str`
  - `upload_thumb(token: str, image_path: Path) -> str`  (returns media_id)
  - `add_draft(token: str, articles: list[dict]) -> str`  (returns media_id)
  - `draft_from_payload(payload: dict, credentials: dict, dry_run: bool) -> dict`
- Keep `requests` as-is (already a dep transitively); add to `pyproject.toml` if missing

If `requests` not in deps, update `pyproject.toml`:
```toml
dependencies = [
    "pyyaml>=6.0",
    "pyrage>=1.1",
    "requests>=2.31",
]
```

- [ ] **Step 4: Add new `scripts/wechat_api_draft.py` as deprecation shim**

```python
"""DEPRECATED: this CLI moved to `providers/wechat_article/internal/wechat_api.py`.

It remains as a thin wrapper for backward compatibility with v0.1 scripts.
Will be removed in v0.3.
"""

from __future__ import annotations

import sys
import warnings


def main() -> int:
    warnings.warn(
        "scripts/wechat_api_draft.py is deprecated; use `mmp publish` or "
        "`providers.wechat_article.internal.wechat_api`",
        DeprecationWarning,
        stacklevel=2,
    )
    print(
        "DEPRECATED. Use `python3 scripts/mmp.py publish <manifest>` instead.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Verify import works**

Run: `python3 -c "from providers.wechat_article.internal import wechat_api; print(wechat_api.__name__)"`
Expected: prints `providers.wechat_article.internal.wechat_api` with no error.

- [ ] **Step 6: Commit**

```bash
git add scripts/wechat_api_draft.py providers/wechat_article/internal/wechat_api.py pyproject.toml
git commit -m "refactor(wechat_article): move API helper to provider internal"
```

---

## Task 11: `providers/wechat_article/rules.py`

**Files:**
- Create: `providers/wechat_article/rules.py`
- Test: extend `providers/wechat_article/tests/test_provider.py` (next task)

- [ ] **Step 1: Implement rules**

```python
"""Platform rules for WeChat Official Account articles.

Sources:
- 微信公众号文章正文长度上限 ~20000 中文字符
- 标题最多 64 字符
- 摘要最多 120 字符
- 必须有封面图（thumb_media_id）
"""

from __future__ import annotations

from core.rules import PlatformRules, Severity, Violation


def _digest_lint(manifest, target_name: str) -> list[Violation]:
    digest = (manifest.metadata or {}).get("digest") or (manifest.summary or "")
    if digest and len(digest) > 120:
        return [
            Violation(
                code="WECHAT_DIGEST_TOO_LONG",
                message=f"digest length {len(digest)} exceeds 120 chars",
                target=target_name,
                field_path="metadata.digest",
                severity=Severity.warning,
            )
        ]
    return []


def _cover_lint(manifest, target_name: str) -> list[Violation]:
    if not getattr(manifest, "cover", None):
        return [
            Violation(
                code="WECHAT_COVER_REQUIRED",
                message="WeChat article requires a cover image (assets.cover)",
                target=target_name,
                field_path="assets.cover",
                severity=Severity.error,
            )
        ]
    return []


WECHAT_ARTICLE_RULES = PlatformRules(
    title_max=64,
    body_max=20000,
    cover_required=True,
    extra_lints=[_digest_lint, _cover_lint],
)
```

- [ ] **Step 2: Commit**

```bash
git add providers/wechat_article/rules.py
git commit -m "feat(wechat_article): add platform rules"
```

---

## Task 12: `providers/wechat_article/provider.py` — Validate + Prepare

**Files:**
- Create: `providers/wechat_article/provider.py`
- Test: `providers/wechat_article/tests/test_provider.py`

- [ ] **Step 1: Write failing test**

`providers/wechat_article/tests/test_provider.py`:

```python
import json
from pathlib import Path

import pytest

from core.manifest import Manifest, Target
from providers.wechat_article.provider import WeChatArticleProvider


@pytest.fixture
def sample_manifest(tmp_path):
    return Manifest(
        schema_version="0.2",
        type="longform",
        title="A reasonable title",
        body="# Hello\n\nBody text.",
        mode="dry-run",
        targets=[Target(name="wechat-article")],
        cover=str(tmp_path / "cover.png"),
        summary="一句话摘要",
        tags=["test"],
    )


def test_validate_passes(sample_manifest, tmp_path):
    cover = Path(sample_manifest.cover)
    cover.write_bytes(b"png-bytes")
    p = WeChatArticleProvider()
    res = p.validate(sample_manifest, sample_manifest.targets[0])
    assert all(v.severity.value != "error" for v in res.violations)


def test_validate_fails_when_no_cover(sample_manifest):
    sample_manifest.cover = None
    p = WeChatArticleProvider()
    res = p.validate(sample_manifest, sample_manifest.targets[0])
    assert any(v.code == "WECHAT_COVER_REQUIRED" for v in res.violations)


def test_prepare_writes_payload(sample_manifest, tmp_path):
    cover = Path(sample_manifest.cover)
    cover.write_bytes(b"png-bytes")
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    p = WeChatArticleProvider()
    out = p.prepare(sample_manifest, sample_manifest.targets[0], run_dir)
    assert out.payload_path.exists()
    payload = json.loads(out.payload_path.read_text())
    assert payload["title"] == "A reasonable title"
    assert payload["cover"].endswith("cover.png")
    assert "html" in payload
    assert "content" in payload
```

- [ ] **Step 2: Run test (should fail)**

Run: `pytest providers/wechat_article/tests/test_provider.py -v`
Expected: FAIL — module/class not defined.

- [ ] **Step 3: Implement provider validate + prepare**

`providers/wechat_article/provider.py`:

```python
"""WeChat Official Account article provider."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.errors import ProviderExecutionError
from core.provider import (
    CredentialSpec,
    ExecutionResult,
    HealthStatus,
    PreparedPayload,
    Provider,
    ValidationResult,
)
from core.rules import Severity

from providers.wechat_article.rules import WECHAT_ARTICLE_RULES


def _markdown_to_html(md: str) -> str:
    """Minimal MD→HTML for WeChat draft API smoke. Not a full renderer."""
    out_lines: list[str] = []
    for line in md.splitlines():
        if line.startswith("# "):
            out_lines.append(f"<h1>{line[2:].strip()}</h1>")
        elif line.startswith("## "):
            out_lines.append(f"<h2>{line[3:].strip()}</h2>")
        elif line.startswith("### "):
            out_lines.append(f"<h3>{line[4:].strip()}</h3>")
        elif not line.strip():
            out_lines.append("")
        else:
            out_lines.append(f"<p>{line}</p>")
    return "\n".join(out_lines)


class WeChatArticleProvider(Provider):
    name = "wechat-article"
    display_name = "微信公众号文章"
    media_types = ["longform"]
    capabilities = {"draft": True, "publish": False, "schedule": False}
    required_credentials = [
        CredentialSpec(
            key="WECHAT_APP_ID",
            description="WeChat Official Account AppID",
            secret=False,
            setup_hint="From mp.weixin.qq.com → 设置与开发 → 基本配置",
        ),
        CredentialSpec(
            key="WECHAT_APP_SECRET",
            description="WeChat Official Account AppSecret",
            secret=True,
            setup_hint="Same page as AppID; reset if forgotten",
        ),
    ]
    platform_rules = WECHAT_ARTICLE_RULES

    def validate(self, manifest: Any, target: Any) -> ValidationResult:
        violations = self.platform_rules.lint(manifest, target_name=self.name)
        return ValidationResult(violations=violations)

    def prepare(self, manifest: Any, target: Any, run_dir: Path) -> PreparedPayload:
        pack_dir = run_dir / "packs" / self.name
        pack_dir.mkdir(parents=True, exist_ok=True)

        digest = (manifest.metadata or {}).get("digest") or (manifest.summary or "")
        body_md = manifest.body or ""
        body_html = _markdown_to_html(body_md)

        payload = {
            "title": manifest.title,
            "content": body_md,
            "html": body_html,
            "digest": digest,
            "tags": list(manifest.tags or []),
            "cover": str(manifest.cover) if manifest.cover else None,
            "mode": target.mode,
            "options": dict(target.options or {}),
        }
        payload_path = pack_dir / "payload.json"
        payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        (pack_dir / "content.md").write_text(body_md, encoding="utf-8")

        return PreparedPayload(pack_dir=pack_dir, payload_path=payload_path)

    def execute(
        self,
        run_dir: Path,
        target: Any,
        mode: str,
        credentials: dict[str, str],
    ) -> ExecutionResult:
        # Implemented in next task
        raise NotImplementedError("Task 13")

    def health_check(self, credentials: dict[str, str]) -> HealthStatus:
        # Implemented in next task
        return HealthStatus.unknown
```

- [ ] **Step 4: Run test (should pass)**

Run: `pytest providers/wechat_article/tests/test_provider.py -v`
Expected: PASS — 3 passed.

- [ ] **Step 5: Commit**

```bash
git add providers/wechat_article/provider.py providers/wechat_article/tests/test_provider.py
git commit -m "feat(wechat_article): implement validate + prepare"
```

---

## Task 13: `wechat_article` Provider Execute (dry-run + draft) + health_check

**Files:**
- Modify: `providers/wechat_article/provider.py`
- Test: extend `providers/wechat_article/tests/test_provider.py`

- [ ] **Step 1: Write failing tests**

Append to `providers/wechat_article/tests/test_provider.py`:

```python
from unittest.mock import patch


def test_execute_dry_run_writes_pseudo_draft(sample_manifest, tmp_path):
    cover = Path(sample_manifest.cover)
    cover.write_bytes(b"png")
    run_dir = tmp_path / "run2"
    (run_dir / "packs" / "wechat-article").mkdir(parents=True)
    p = WeChatArticleProvider()
    p.prepare(sample_manifest, sample_manifest.targets[0], run_dir)

    res = p.execute(run_dir, sample_manifest.targets[0], mode="dry-run", credentials={})
    assert res.status == "ok"
    assert res.mode_actual == "dry-run"
    assert res.external_id is None


def test_execute_draft_calls_api(sample_manifest, tmp_path):
    cover = Path(sample_manifest.cover)
    cover.write_bytes(b"png")
    run_dir = tmp_path / "run3"
    (run_dir / "packs" / "wechat-article").mkdir(parents=True)
    p = WeChatArticleProvider()
    p.prepare(sample_manifest, sample_manifest.targets[0], run_dir)

    creds = {"WECHAT_APP_ID": "wx", "WECHAT_APP_SECRET": "s"}
    with patch(
        "providers.wechat_article.internal.wechat_api.get_access_token",
        return_value="tok-123",
    ), patch(
        "providers.wechat_article.internal.wechat_api.upload_thumb",
        return_value="thumb-id-1",
    ), patch(
        "providers.wechat_article.internal.wechat_api.add_draft",
        return_value="draft-id-9",
    ):
        res = p.execute(run_dir, sample_manifest.targets[0], mode="draft", credentials=creds)

    assert res.status == "ok"
    assert res.mode_actual == "draft-platform"
    assert res.external_id == "draft-id-9"


def test_execute_publish_refused(sample_manifest, tmp_path):
    cover = Path(sample_manifest.cover)
    cover.write_bytes(b"png")
    run_dir = tmp_path / "run4"
    (run_dir / "packs" / "wechat-article").mkdir(parents=True)
    p = WeChatArticleProvider()
    p.prepare(sample_manifest, sample_manifest.targets[0], run_dir)

    with pytest.raises(NotImplementedError, match="publish"):
        p.execute(run_dir, sample_manifest.targets[0], mode="publish", credentials={"a": "b"})
```

- [ ] **Step 2: Run tests (should fail)**

Run: `pytest providers/wechat_article/tests/test_provider.py -v`
Expected: FAIL — execute raises NotImplementedError("Task 13") for dry-run.

- [ ] **Step 3: Replace `execute` and `health_check` in provider.py**

In `providers/wechat_article/provider.py`, replace the `execute` and `health_check` methods:

```python
    def execute(
        self,
        run_dir: Path,
        target: Any,
        mode: str,
        credentials: dict[str, str],
    ) -> ExecutionResult:
        if mode == "publish":
            raise NotImplementedError(
                "wechat-article publish path not enabled in v0.2; use mode=draft"
            )

        if mode == "dry-run":
            return ExecutionResult(status="ok", mode_actual="dry-run", external_id=None)

        # mode == "draft"
        from providers.wechat_article.internal import wechat_api  # local import: optional dep

        payload_path = run_dir / "packs" / self.name / "payload.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))

        app_id = credentials.get("WECHAT_APP_ID")
        app_secret = credentials.get("WECHAT_APP_SECRET")
        if not app_id or not app_secret:
            raise ProviderExecutionError(
                target=self.name,
                step="auth",
                upstream=ValueError("missing WECHAT_APP_ID or WECHAT_APP_SECRET"),
                retryable=False,
            )

        try:
            token = wechat_api.get_access_token(app_id, app_secret)
        except Exception as exc:
            raise ProviderExecutionError(
                target=self.name, step="get_token", upstream=exc, retryable=True
            ) from exc

        try:
            thumb_media_id = wechat_api.upload_thumb(token, Path(payload["cover"]))
        except Exception as exc:
            raise ProviderExecutionError(
                target=self.name, step="upload_thumb", upstream=exc, retryable=True
            ) from exc

        article = {
            "title": payload["title"],
            "thumb_media_id": thumb_media_id,
            "content": payload["html"],
            "digest": payload["digest"],
            "show_cover_pic": 1,
            "need_open_comment": 0,
            "only_fans_can_comment": 0,
        }

        try:
            draft_id = wechat_api.add_draft(token, [article])
        except Exception as exc:
            raise ProviderExecutionError(
                target=self.name, step="add_draft", upstream=exc, retryable=True
            ) from exc

        return ExecutionResult(
            status="ok",
            mode_actual="draft-platform",
            external_id=draft_id,
            extras={"thumb_media_id": thumb_media_id},
        )

    def health_check(self, credentials: dict[str, str]) -> HealthStatus:
        from providers.wechat_article.internal import wechat_api

        app_id = credentials.get("WECHAT_APP_ID")
        app_secret = credentials.get("WECHAT_APP_SECRET")
        if not (app_id and app_secret):
            return HealthStatus.failed
        try:
            wechat_api.get_access_token(app_id, app_secret)
            return HealthStatus.ok
        except Exception:
            return HealthStatus.failed
```

- [ ] **Step 4: Run tests (should pass)**

Run: `pytest providers/wechat_article/tests/test_provider.py -v`
Expected: PASS — 6 passed (3 original + 3 new).

- [ ] **Step 5: Commit**

```bash
git add providers/wechat_article/provider.py providers/wechat_article/tests/test_provider.py
git commit -m "feat(wechat_article): implement execute + health_check"
```

---

## Task 14: `scripts/mmp.py` — CLI Skeleton + dispatch

**Files:**
- Create: `scripts/mmp.py`
- Test: `tests/integration/test_cli_skeleton.py`

- [ ] **Step 1: Write failing test**

`tests/integration/test_cli_skeleton.py`:

```python
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def _run(*args, env=None):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mmp.py"), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_no_args_prints_help():
    p = _run()
    assert p.returncode != 0
    assert "usage" in (p.stdout + p.stderr).lower()


def test_help_lists_subcommands():
    p = _run("--help")
    out = p.stdout + p.stderr
    for cmd in ["validate", "publish", "setup", "list", "resume", "doctor"]:
        assert cmd in out
```

- [ ] **Step 2: Run test (should fail)**

Run: `pytest tests/integration/test_cli_skeleton.py -v`
Expected: FAIL — file not found.

- [ ] **Step 3: Implement `scripts/mmp.py`**

```python
#!/usr/bin/env python3
"""multi-media-publisher unified CLI entry.

Subcommands: validate, publish, setup, list, resume, doctor, wizard.
The wizard subcommand is implemented in Plan 2.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mmp", description="multi-media-publisher CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub_validate = sub.add_parser("validate", help="Validate a manifest without executing")
    sub_validate.add_argument("manifest", help="Path to manifest.yaml")

    sub_publish = sub.add_parser("publish", help="Run prepare+execute for a manifest")
    sub_publish.add_argument("manifest", help="Path to manifest.yaml")
    sub_publish.add_argument(
        "--mode-override",
        choices=["dry-run", "draft", "publish"],
        default=None,
        help="Override manifest top-level mode (CAUTION with publish)",
    )

    sub_setup = sub.add_parser("setup", help="Configure credentials for a provider")
    sub_setup.add_argument("provider", help="Provider name (e.g. wechat-article)")
    sub_setup.add_argument("--account", default="default")

    sub_list = sub.add_parser("list", help="List providers / accounts / runs")
    sub_list.add_argument("kind", choices=["providers", "accounts", "runs"])

    sub_resume = sub.add_parser("resume", help="Resume a previously failed run")
    sub_resume.add_argument("run_dir")
    sub_resume.add_argument("--target", default=None)

    sub_doctor = sub.add_parser("doctor", help="Self-check: vault, providers, health")

    sub_wizard = sub.add_parser("wizard", help="Conversational manifest wizard (Plan 2)")
    sub_wizard.add_argument("--type", choices=["image-post", "longform", "video-post"])
    sub_wizard.add_argument("--targets", default=None, help="Comma-separated target names")

    return p


def cmd_validate(args: argparse.Namespace) -> int:
    from core.manifest import load_manifest
    from core.provider import ProviderRegistry
    from core.errors import MMPError

    try:
        m = load_manifest(args.manifest)
        reg = ProviderRegistry()
        reg.discover()
        all_violations = []
        for t in m.targets:
            provider = reg.resolve(t.name)
            res = provider.validate(m, t)
            if res:
                all_violations.extend(res.violations)
        errs = [v for v in all_violations if v.severity.value == "error"]
        warns = [v for v in all_violations if v.severity.value == "warning"]
        for v in errs:
            print(f"ERROR  {v.target}  {v.code}  {v.message}", file=sys.stderr)
        for v in warns:
            print(f"WARN   {v.target}  {v.code}  {v.message}", file=sys.stderr)
        if errs:
            return 2
        print(f"OK  {len(m.targets)} targets validated.")
        return 0
    except MMPError as e:
        print(f"ERROR  {e}", file=sys.stderr)
        return 2


def cmd_publish(args: argparse.Namespace) -> int:
    from core.manifest import load_manifest, write_lock
    from core.provider import ProviderRegistry
    from core.credentials import CredentialStore
    from core.run import Run
    from core.errors import MMPError

    try:
        m = load_manifest(args.manifest)
        if args.mode_override:
            m.mode = args.mode_override
            for t in m.targets:
                t.mode = args.mode_override

        reg = ProviderRegistry()
        reg.discover()
        store = CredentialStore()

        run = Run.create(title=m.title, mmp_version="0.2.0", host="cli", mode=m.mode)
        # copy manifest.yaml
        Path(run.dir / "manifest.yaml").write_text(
            Path(args.manifest).read_text(encoding="utf-8"), encoding="utf-8"
        )
        write_lock(m, run.dir)

        for t in m.targets:
            run.log("TARGET_START", target=t.name, account=t.account)
            try:
                provider = reg.resolve(t.name)
                v_res = provider.validate(m, t)
                errs = [
                    v for v in (v_res.violations if v_res else [])
                    if v.severity.value == "error"
                ]
                if errs:
                    run.add_target_result(
                        name=t.name,
                        account=t.account,
                        status="failed",
                        mode_actual="dry-run",
                        error=f"validation: {[v.code for v in errs]}",
                        violations=[v.__dict__ for v in errs],
                    )
                    run.log("VALIDATE_FAIL", target=t.name, codes=[v.code for v in errs])
                    continue

                provider.prepare(m, t, run.dir)
                run.log("PREPARE_OK", target=t.name)

                creds = {}
                if t.mode != "dry-run":
                    required = [c.key for c in provider.required_credentials]
                    creds = store.get(t.name, t.account, required_keys=required)

                exec_res = provider.execute(run.dir, t, t.mode, creds)
                run.add_target_result(
                    name=t.name,
                    account=t.account,
                    status=exec_res.status,
                    mode_actual=exec_res.mode_actual,
                    external_id=exec_res.external_id,
                    draft_url=exec_res.draft_url,
                )
                run.log(
                    "EXECUTE_OK",
                    target=t.name,
                    mode_actual=exec_res.mode_actual,
                    external_id=exec_res.external_id,
                )
            except Exception as exc:
                run.add_target_result(
                    name=t.name,
                    account=t.account,
                    status="failed",
                    mode_actual=t.mode,
                    error=str(exc),
                )
                run.log("TARGET_FAIL", target=t.name, error=str(exc))

        run.finalize()
        print(f"RUN_DIR  {run.dir}")
        return 0
    except MMPError as e:
        print(f"ERROR  {e}", file=sys.stderr)
        return 2


def cmd_setup(args: argparse.Namespace) -> int:
    from core.credentials import CredentialStore
    from core.provider import ProviderRegistry

    reg = ProviderRegistry()
    reg.discover()
    try:
        provider = reg.resolve(args.provider)
    except Exception as e:
        print(f"ERROR  {e}", file=sys.stderr)
        return 2

    store = CredentialStore()
    values: dict[str, str] = {}
    print(f"Configure {args.provider} (account: {args.account}). Press Enter to skip a key.")
    for spec in provider.required_credentials:
        prompt = f"  {spec.key}"
        if spec.description:
            prompt += f" ({spec.description})"
        prompt += ": "
        if spec.secret:
            import getpass
            v = getpass.getpass(prompt)
        else:
            v = input(prompt)
        if v:
            values[spec.key] = v
    if values:
        store.set(args.provider, args.account, values)
        print(f"OK  saved {len(values)} keys to vault.")
    else:
        print("nothing to save.")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    if args.kind == "providers":
        from core.provider import ProviderRegistry
        reg = ProviderRegistry()
        reg.discover()
        for info in reg.list():
            caps = ",".join(k for k, v in info.capabilities.items() if v)
            print(f"  {info.name}  ({info.source})  media={info.media_types}  caps={caps}")
    elif args.kind == "accounts":
        from core.credentials import CredentialStore
        store = CredentialStore()
        for acc in store.list_accounts():
            print(f"  {acc}")
    elif args.kind == "runs":
        from core import host as h
        rd = h.runs_dir()
        if rd.exists():
            for d in sorted(rd.iterdir()):
                if d.is_dir():
                    print(f"  {d.name}")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    print("resume not implemented in Plan 1; coming soon.", file=sys.stderr)
    return 1


def cmd_doctor(args: argparse.Namespace) -> int:
    from core import host as h
    from core.provider import ProviderRegistry
    from core.credentials import CredentialStore

    print(f"host: {h.detect_host()}")
    print(f"vault: {h.vault_path()}  exists={h.vault_path().exists()}")
    reg = ProviderRegistry()
    reg.discover()
    print(f"providers: {len(reg.list())}")
    store = CredentialStore()
    print(f"accounts: {len(store.list_accounts())}")
    return 0


def cmd_wizard(args: argparse.Namespace) -> int:
    print("wizard subcommand will be implemented in Plan 2.", file=sys.stderr)
    return 1


_DISPATCH = {
    "validate": cmd_validate,
    "publish": cmd_publish,
    "setup": cmd_setup,
    "list": cmd_list,
    "resume": cmd_resume,
    "doctor": cmd_doctor,
    "wizard": cmd_wizard,
}


def main(argv: list[str] | None = None) -> int:
    p = _build_parser()
    args = p.parse_args(argv)
    return _DISPATCH[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Make executable & run test**

```bash
chmod +x scripts/mmp.py
pytest tests/integration/test_cli_skeleton.py -v
```

Expected: PASS — 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/mmp.py tests/integration/test_cli_skeleton.py
git commit -m "feat(cli): add mmp.py with validate/publish/setup/list/resume/doctor"
```

---

## Task 15: Integration Test — wechat_article End-to-End (dry-run)

**Files:**
- Create: `tests/integration/test_wechat_article_e2e.py`
- Create: `tests/fixtures/wechat-article-e2e.yaml`
- Create: `tests/fixtures/wechat-article-e2e.body.md`
- Create: `tests/fixtures/wechat-article-cover.png` (any tiny PNG)

- [ ] **Step 1: Create fixtures**

`tests/fixtures/wechat-article-e2e.body.md`:

```markdown
# AI Agent 不是工具

而是一种新的组织形态。

## 一

正文段落。
```

`tests/fixtures/wechat-article-e2e.yaml`:

```yaml
schema_version: "0.2"
type: longform
title: "AI Agent 不是工具"
body: ./wechat-article-e2e.body.md
mode: dry-run
language: zh-CN
targets:
  - wechat-article
assets:
  cover: ./wechat-article-cover.png
summary: "一句话摘要 测试"
tags:
  - AI
metadata:
  digest: "用作公众号文章摘要的字段"
```

Create cover PNG:

```bash
python3 -c "import struct; open('tests/fixtures/wechat-article-cover.png','wb').write(bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108020000009077533de0000000016352474200aece1ce90000000c4944415478da6300010000050001a5f645400000000049454e44ae426082'))"
```

- [ ] **Step 2: Write integration test**

`tests/integration/test_wechat_article_e2e.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "wechat-article-e2e.yaml"


def test_publish_dry_run_creates_run_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MMP_RUNS_DIR", str(tmp_path / "runs"))

    p = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mmp.py"), "publish", str(FIXTURE)],
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "MMP_RUNS_DIR": str(tmp_path / "runs")},
    )
    assert p.returncode == 0, p.stderr

    runs = list((tmp_path / "runs").iterdir())
    assert len(runs) == 1
    rd = runs[0]
    assert (rd / "manifest.lock.json").exists()
    assert (rd / "result.json").exists()
    assert (rd / "publish-log.md").exists()
    assert (rd / "packs" / "wechat-article" / "payload.json").exists()

    result = json.loads((rd / "result.json").read_text())
    assert result["mode"] == "dry-run"
    assert len(result["targets"]) == 1
    t = result["targets"][0]
    assert t["name"] == "wechat-article"
    assert t["status"] == "ok"
    assert t["mode_actual"] == "dry-run"


def test_validate_subcommand(tmp_path):
    p = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mmp.py"), "validate", str(FIXTURE)],
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stderr
    assert "OK" in p.stdout
```

- [ ] **Step 3: Run integration test**

Run: `pytest tests/integration/test_wechat_article_e2e.py -v`
Expected: PASS — 2 passed.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_wechat_article_e2e.py tests/fixtures/
git commit -m "test(integration): wechat_article dry-run end-to-end"
```

---

## Task 16: Update Makefile + Smoke Test

**Files:**
- Modify: `Makefile`
- Modify: `scripts/test_local.py`

- [ ] **Step 1: Read existing Makefile**

Run: `cat Makefile`
Expected: existing `test:` target invoking `scripts/test_local.py`.

- [ ] **Step 2: Replace Makefile**

```makefile
.PHONY: test lint typecheck unit smoke clean

test: lint typecheck unit smoke

unit:
	python3 -m pytest -q

lint:
	python3 -m ruff check .

typecheck:
	python3 -m mypy core

smoke:
	python3 scripts/test_local.py

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache __pycache__
	find . -name "__pycache__" -type d -exec rm -rf {} +
	find . -name "*.pyc" -delete
```

- [ ] **Step 3: Update `scripts/test_local.py`**

Replace `scripts/test_local.py` with:

```python
#!/usr/bin/env python3
"""Local smoke test for multi-media-publisher v0.2.

Runs a few CLI flows in a tmp dir and asserts shape. Does NOT call any
external network.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "wechat-article-e2e.yaml"


def _run_mmp(*args, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mmp.py"), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mmp-smoke-") as tmp:
        tmp_path = Path(tmp)
        runs_dir = tmp_path / "runs"
        env_extra = {
            "MMP_RUNS_DIR": str(runs_dir),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        }

        # 1. validate
        p = _run_mmp("validate", str(FIXTURE), env_extra=env_extra)
        assert p.returncode == 0, f"validate failed:\n{p.stderr}"

        # 2. publish dry-run
        p = _run_mmp("publish", str(FIXTURE), env_extra=env_extra)
        assert p.returncode == 0, f"publish dry-run failed:\n{p.stderr}"
        runs = list(runs_dir.iterdir())
        assert len(runs) == 1
        rd = runs[0]
        result = json.loads((rd / "result.json").read_text())
        assert result["targets"][0]["status"] == "ok"
        assert result["targets"][0]["mode_actual"] == "dry-run"

        # 3. doctor
        p = _run_mmp("doctor", env_extra=env_extra)
        assert p.returncode == 0, f"doctor failed:\n{p.stderr}"

        # 4. list
        p = _run_mmp("list", "providers", env_extra=env_extra)
        assert p.returncode == 0
        assert "wechat-article" in p.stdout

        print(json.dumps({"ok": True, "tmp": str(tmp_path), "run": str(rd)}, indent=2))
        return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run smoke**

Run: `make smoke`
Expected: prints `{"ok": true, ...}` and exit 0.

- [ ] **Step 5: Run full test target**

Run: `make test`
Expected: lint + typecheck + unit + smoke all pass.

- [ ] **Step 6: Commit**

```bash
git add Makefile scripts/test_local.py
git commit -m "build: Makefile with lint/typecheck/unit/smoke; rewrite smoke for v0.2 CLI"
```

---

## Task 17: Update SKILL.md to v0.2

**Files:**
- Modify: `SKILL.md`

- [ ] **Step 1: Replace SKILL.md**

```markdown
---
name: Multi-media Publisher
description: This skill should be used when the user asks to "多媒体发布", "多平台发布", "同步发布小红书和微信图文", "发微信图文和小红书", "发布长文章到公众号/X/Substack", "cross-post", "publish everywhere", or wants one content package adapted and published/drafted across Xiaohongshu, WeChat image posts, WeChat Official Account articles, X Articles/Twitter, Substack, or future video platforms.
version: 0.2.0
---

# Multi-media Publisher / 多媒体发布

Cross-platform content publishing orchestration. Routes one source content
package to multiple platform providers via a unified manifest, draft-first
safety policy, and per-platform rules.

## When to use

- User wants to publish/draft the same content across multiple platforms
- User wants to add a new platform/provider
- User needs to validate a manifest, set up credentials, or inspect runs

## Entry point

All operations go through `scripts/mmp.py`:

```bash
python3 scripts/mmp.py <subcommand> [args]
```

Subcommands:

- `validate <manifest.yaml>` — validate without executing
- `publish <manifest.yaml> [--mode-override ...]` — prepare + execute
- `setup <provider> [--account NAME]` — configure credentials
- `list providers|accounts|runs` — inspect state
- `resume <run-dir> [--target NAME]` — recover failed run
- `doctor` — self-check
- `wizard [--type ... --targets ...]` — conversational manifest builder (Plan 2)

## Default mode = draft

Every run defaults to `mode: draft`. Public publishing requires explicit
top-level `mode: publish` AND a second confirmation in conversation.

## v0.2 supported providers

| Provider | Media | Modes |
|---|---|---|
| `wechat-article` | longform | dry-run, draft (Plan 1) |
| `xiaohongshu` | image-post | (Plan 3) |
| `wechat-image` | image-post | (Plan 3) |
| `x-article` | longform | (Plan 3) |
| `substack` | longform | (Plan 3) |

## Safety rules

1. Never publish publicly without explicit confirmation
2. Never bypass login, CAPTCHA, platform review, or anti-abuse safeguards
3. Treat all credentials as secrets; never print them
4. If browser automation reaches an ambiguous screen, stop and ask
5. Read `docs/safety-policy.md` (was `references/publishing-policy.md`)

## Architecture

See `docs/superpowers/specs/2026-05-05-multi-media-publisher-redesign-design.md`
for the full architecture spec. In short:

- **Shell**: this SKILL.md + `.claude-plugin/plugin.json` (Plan 4)
- **Core**: `core/` — host-agnostic Python (manifest, provider registry, vault, run lifecycle)
- **Providers**: `providers/<name>/` (bundled) + `~/.config/mmp/providers/<name>/` (user)

## Quickstart

```bash
# 1. Validate
python3 scripts/mmp.py validate examples/longform.yaml

# 2. Configure WeChat credentials
python3 scripts/mmp.py setup wechat-article

# 3. Dry-run
python3 scripts/mmp.py publish examples/longform.yaml --mode-override dry-run

# 4. Inspect runs
python3 scripts/mmp.py list runs
```

## Bundled resources

- `core/` — manifest, provider, credentials, run, rules, host, errors
- `providers/wechat_article/` — first-party WeChat OA article provider
- `examples/longform.yaml` — sample manifest
- `docs/HANDOFF.md` — historical state notes
- `docs/superpowers/specs/2026-05-05-multi-media-publisher-redesign-design.md` — v0.2 design spec
- `docs/superpowers/plans/2026-05-05-plan-*.md` — v0.2 implementation plans
```

- [ ] **Step 2: Commit**

```bash
git add SKILL.md
git commit -m "docs: rewrite SKILL.md for v0.2 architecture"
```

---

## Task 18: Update HANDOFF.md & README.md

**Files:**
- Modify: `docs/HANDOFF.md`
- Modify: `README.md`

- [ ] **Step 1: Append status block to HANDOFF.md**

Append to `docs/HANDOFF.md`:

```markdown

---

## v0.2 Redesign — In Progress

Active spec: `docs/superpowers/specs/2026-05-05-multi-media-publisher-redesign-design.md`
Plans: `docs/superpowers/plans/2026-05-05-plan-{1,2,3,4}-*.md`

### Plan 1 status (this commit range)

- Core architecture: `core/` modules in place (manifest, provider, credentials, run, rules, host, errors)
- First provider migrated: `wechat_article` (validate + prepare + execute draft + health_check)
- CLI: `scripts/mmp.py` with validate/publish/setup/list/resume/doctor
- Tests: unit + integration; `make test` covers lint + typecheck + unit + smoke
- Old scripts: `wechat_api_draft.py` deprecated (shim only)

### Open items after Plan 1

- Wizard subcommand: stub only; implemented in Plan 2
- Remaining providers (xiaohongshu / wechat_image / x_article / substack): Plan 3
- Plugin marketplace prep + CI: Plan 4
- Real WeChat account verification: see `docs/manual-verification.md` (Plan 4)
```

- [ ] **Step 2: Update README.md**

Replace `README.md`:

```markdown
# Multi-media Publisher / 多媒体发布

统一调度多平台内容发布的 OpenClaw skill / Claude Code plugin。

## 现状（v0.2 进行中）

- 架构：`core/` + `providers/<name>/` + `scripts/mmp.py`
- 已迁移：`wechat-article` 全链路（validate/prepare/execute draft）
- 进行中：`wizard`（Plan 2）、其他 4 个 provider（Plan 3）、CC plugin + CI（Plan 4）

详见：

- 设计：[docs/superpowers/specs/2026-05-05-multi-media-publisher-redesign-design.md](docs/superpowers/specs/2026-05-05-multi-media-publisher-redesign-design.md)
- 计划：[docs/superpowers/plans/](docs/superpowers/plans/)
- 交接：[docs/HANDOFF.md](docs/HANDOFF.md)
- Skill：[SKILL.md](SKILL.md)

## 安装

```bash
python3 -m pip install -e ".[dev]"
```

## 用法

```bash
# 校验
python3 scripts/mmp.py validate examples/longform.yaml

# 配置凭证
python3 scripts/mmp.py setup wechat-article

# 发布（默认 draft 模式）
python3 scripts/mmp.py publish examples/longform.yaml

# 自检
python3 scripts/mmp.py doctor

# 测试
make test
```

## 安全策略

- 默认 `draft` 模式
- 公开发布要求显式 `publish` 模式 + 对话二次确认
- 凭证存于 age 加密的 `~/.config/mmp/credentials.json.age`
- 详见 `docs/safety-policy.md`
```

- [ ] **Step 3: Commit**

```bash
git add docs/HANDOFF.md README.md
git commit -m "docs: update HANDOFF and README for v0.2 plan-1 progress"
```

---

## Task 19: Final Lint & Typecheck Pass

- [ ] **Step 1: Run ruff**

Run: `python3 -m ruff check .`
Expected: 0 issues. Fix any reported.

- [ ] **Step 2: Run ruff format check**

Run: `python3 -m ruff format --check .`
Expected: 0 changes needed. If reformatting needed, run `ruff format .` and commit.

- [ ] **Step 3: Run mypy**

Run: `python3 -m mypy core`
Expected: 0 errors. Fix any reported by adding type hints.

- [ ] **Step 4: Run full test**

Run: `make test`
Expected: all green.

- [ ] **Step 5: Commit any cleanup**

```bash
git add -A
git status
# only commit if files changed
git diff --cached --quiet || git commit -m "chore: lint/typecheck cleanup"
```

---

## Self-Review Checklist

Before declaring Plan 1 done:

- [ ] All tasks 1–19 committed
- [ ] `make test` green
- [ ] `python3 scripts/mmp.py doctor` shows ≥1 provider
- [ ] `python3 scripts/mmp.py publish tests/fixtures/wechat-article-e2e.yaml` produces a run dir with `result.json` status=ok
- [ ] Spec sections covered: §3 (architecture), §4 (provider contract), §5 (manifest), §6 (vault), §8 (run lifecycle), §10.1 (wechat_article migration)
- [ ] Spec sections deferred to later plans: §7 (wizard → Plan 2), §10.1 remaining providers (Plan 3), §9 (dual-host plugin) + §11 (CI) → Plan 4

## Hand-off to Plan 2

Plan 2 (Wizard Flow) reads:

- `core.wizard` package skeleton needed
- `scripts/mmp.py wizard` currently stub returning exit 1
- SKILL.md `wizard` reference in subcommands list

Plan 2 starts after Plan 1 self-review passes.
