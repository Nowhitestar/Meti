# Plan 4 — Distribution + CI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the project installable as a Claude Code plugin AND continue to work as an OpenClaw skill from the same source tree, plus stand up CI that exercises all providers in dry-run.

**Architecture:** Add `.claude-plugin/plugin.json` for the CC marketplace; polish `SKILL.md` to be the canonical entry recognized by both hosts; consolidate user-facing docs from scattered `references/*.md` into a clean `docs/` set; ship `.github/workflows/ci.yml` with a 2-OS × 3-Python matrix that runs lint, typecheck, unit, and smoke (no real-account network).

**Tech Stack:** Same as previous plans + GitHub Actions.

**Spec reference:** `docs/superpowers/specs/2026-05-05-multi-media-publisher-redesign-design.md` §9 (Dual-Host Distribution), §11 (Testing & CI), §13 (Open Questions).

**Depends on:** Plans 1, 2, 3 complete.

---

## File Structure

**Created:**

```
.claude-plugin/plugin.json
.github/workflows/ci.yml
docs/architecture.md
docs/provider-contract.md
docs/credentials.md
docs/safety-policy.md             # promoted from references/publishing-policy.md
docs/manual-verification.md
CHANGELOG.md
```

**Modified:**

```
SKILL.md                          # final polish: dual-host description, version
README.md                         # full rewrite as install + quickstart
pyproject.toml                    # version 0.2.0
docs/HANDOFF.md                   # Plan 4 completion + handoff to v0.3
```

**Deleted (content moved to docs/ or providers/):**

```
references/candidate-skills.md    # archived to docs/legacy-research.md
references/image-post-mvp.md      # archived
references/phase2-audit.md        # archived
references/workflows.md           # superseded by docs/architecture.md
references/manifest-schema.md     # superseded by docs/architecture.md schema section
references/platform-map.md        # superseded by per-provider provider.yaml
references/publishing-policy.md   # promoted to docs/safety-policy.md
```

---

## Task 1: Promote `references/publishing-policy.md` → `docs/safety-policy.md`

**Files:**
- Move: `references/publishing-policy.md` → `docs/safety-policy.md`

- [ ] **Step 1: Move and refresh content**

```bash
git mv references/publishing-policy.md docs/safety-policy.md
```

Edit `docs/safety-policy.md` to ensure the v0.2 phrasing:

```markdown
# Safety & Approval Policy

multi-media-publisher will never circumvent platform safeguards or post
publicly without explicit confirmation in the active conversation.

## Defaults

- Manifest top-level `mode` defaults to `draft` if omitted by user.
- All providers ship with `capabilities.publish: false` in v0.2.
- The wizard's Stage 3 inserts an additional confirmation gate when any target
  has `mode: publish`.

## Hard rules

1. **No public publish without active confirmation.** Even if the user
   pre-authorized a publish in a prior conversation, ask again on this run.
2. **No bypass.** Never skip login flows, CAPTCHAs, platform reviews, or
   anti-abuse checks. If the browser hits an ambiguous state, stop and ask.
3. **No secret leakage.** Credentials never appear in:
   - `result.json`
   - `publish-log.md`
   - any git-tracked file
   - any printed output beyond `(received)` confirmation
4. **No CLI-arg secrets.** Pass through ENV or vault. CLI args are visible in
   `ps`.
5. **No silent failure.** A target that fails records `status: failed` with
   the upstream error message; the run does not pretend success.
6. **No batch surprise.** Publishing N targets is N explicit confirmations
   when at least one is `mode: publish`.

## Vault & key rotation

- Vault file: `~/.config/mmp/credentials.json.age` (mode 600).
- Vault key: `~/.config/mmp/age-key.txt` (mode 600).
- Rotate the vault key by:
  1. `mmp list accounts` to enumerate
  2. `mmp setup <provider> --account <a>` re-enters values
  3. delete the old vault file
  4. delete the old age-key
- ENV variables override vault for the current session; useful for CI.

## Third-party providers

- User-installed providers under `~/.config/mmp/providers/<name>/` are
  arbitrary Python. Loading is gated:
  - First load: `mmp` prompts the user "trust provider `<name>`? (y/n)"
  - On `y`, the name is added to `settings.toml.providers.trusted_user_providers`
  - On `n`, skip with a warning.
- v0.2 does not implement signature verification. Treat untrusted providers as
  unsafe.

## Reporting

If a provider is found to publish without confirmation or leak secrets,
treat as a P0 bug. Open an issue and disable the provider in `settings.toml`
until patched.
```

- [ ] **Step 2: Commit**

```bash
git add docs/safety-policy.md
git commit -m "docs: promote publishing-policy → docs/safety-policy.md (v0.2 phrasing)"
```

---

## Task 2: `docs/architecture.md`

**Files:**
- Create: `docs/architecture.md`

- [ ] **Step 1: Write architecture overview**

```markdown
# Architecture

This is the user-facing architecture summary. The full design spec lives at
`docs/superpowers/specs/2026-05-05-multi-media-publisher-redesign-design.md`.

## Three layers

```
Shell:       SKILL.md  +  .claude-plugin/plugin.json
              │
              ▼
Core:        core/    (host-agnostic Python)
              │
              ▼
Providers:   providers/<name>/  +  ~/.config/mmp/providers/<name>/
```

- **Shell** is what Claude Code or OpenClaw load to know this skill exists.
  It declares triggers and points at `scripts/mmp.py`.
- **Core** is `core/manifest.py`, `core/provider.py`, `core/credentials.py`,
  `core/run.py`, `core/rules.py`, `core/host.py`, `core/errors.py`,
  `core/wizard/`, `core/settings.py`. Nothing in core depends on a host.
- **Providers** ship one per platform: `providers/wechat_article/` etc.
  Each declares `provider.yaml` + `provider.py` + `rules.py`.

## Manifest schema (v0.2)

See `docs/provider-contract.md` for full field list and lock-file format.

```yaml
schema_version: "0.2"
type: image-post | longform | video-post
title: "..."
body: "inline or ./path.md"
mode: dry-run | draft | publish
language: zh-CN
defaults:           # optional
  account: default
  options: {}
targets:
  - <provider-name>                    # short form, inherits top mode
  - target: <provider-name>            # full form
    mode: draft
    account: lewis
    options:
      digest: "..."
assets:
  cover: ./cover.png
  images: []
  video: null
tags: []
metadata: {}
```

## Run lifecycle

```
mmp publish manifest.yaml
  → load + validate manifest
  → create runs/<ts>-<slug>/ + manifest.lock.json
  → for each target:
       provider.validate (lint platform rules)
       provider.prepare  (write packs/<target>/)
       provider.execute  (dry-run | draft | publish)
       record TARGET_DONE in publish-log.md
       checkpoint after key steps
  → finalize: write result.json
```

## Why this shape

- One manifest, many providers — adding a platform is one directory, not six edits.
- Core is host-agnostic — same code works in Claude Code, OpenClaw, or `python3 mmp.py`.
- draft-first — capabilities default to draft only; publish requires explicit opt-in.
- Vault is shared across hosts — `~/.config/mmp/` is a single source of truth.
```

- [ ] **Step 2: Commit**

```bash
git add docs/architecture.md
git commit -m "docs: add architecture.md user-facing overview"
```

---

## Task 3: `docs/provider-contract.md`

**Files:**
- Create: `docs/provider-contract.md`

- [ ] **Step 1: Write provider author guide**

```markdown
# Writing a Provider

A provider is a directory containing `provider.yaml` + a Python module that
implements the `Provider` ABC.

## Where it lives

- **Bundled** (first-party): `providers/<snake_name>/`
- **User** (third-party): `~/.config/mmp/providers/<snake_name>/`

The directory name uses snake_case (Python module name). The
`provider.yaml.name` is the kebab-case identifier referenced in manifests
and pack folders.

## Required files

```
<snake_name>/
├── __init__.py
├── provider.yaml
├── provider.py
├── rules.py        # optional: platform rules
└── tests/          # optional but encouraged
```

## `provider.yaml`

```yaml
name: my-platform                      # kebab-case; appears in manifests
display_name: My Platform              # human-readable
media_types: [longform]                # subset of {image-post, longform, video-post}
capabilities:
  draft: true
  publish: false
  schedule: false
required_credentials:
  - key: MYPLATFORM_TOKEN
    description: "API token"
    secret: true
    setup_hint: "Get one from https://..."
entry: provider:MyPlatformProvider     # python_module:ClassName, relative to the dir
schema_version: 1
```

## `provider.py`

Implement `Provider` from `core.provider`. Methods you must define:

```python
class MyPlatformProvider(Provider):
    name = "my-platform"
    display_name = "My Platform"
    media_types = ["longform"]
    capabilities = {"draft": True, "publish": False, "schedule": False}
    required_credentials = [...]       # CredentialSpec list
    platform_rules = MY_RULES          # PlatformRules instance

    def validate(self, manifest, target) -> ValidationResult: ...
    def prepare(self, manifest, target, run_dir) -> PreparedPayload: ...
    def execute(self, run_dir, target, mode, credentials) -> ExecutionResult: ...
    def health_check(self, credentials) -> HealthStatus: ...   # optional
```

### `validate(manifest, target) -> ValidationResult`

- Run `self.platform_rules.lint(manifest, self.name)` and wrap in
  `ValidationResult(violations=...)`.
- Optional: append your own checks beyond `PlatformRules`.

### `prepare(manifest, target, run_dir) -> PreparedPayload`

- Write `<run_dir>/packs/<self.name>/payload.json` with what your `execute`
  step needs.
- Optional: also write `content.md`, screenshots, browser-flow guides.
- Return a `PreparedPayload(pack_dir=..., payload_path=...)`.

### `execute(run_dir, target, mode, credentials) -> ExecutionResult`

- `mode` is one of `dry-run`, `draft`, `publish`.
- For `dry-run`, do nothing real; return
  `ExecutionResult(status="ok", mode_actual="dry-run")`.
- For `draft`, perform the platform-side draft action; return
  `ExecutionResult(status="ok", mode_actual="draft-platform" | "draft-local",
  external_id=...)`.
- For `publish`, raise `NotImplementedError` unless your provider explicitly
  supports it AND you have re-confirmed with the user.

Wrap upstream failures in `ProviderExecutionError(target=..., step=...,
upstream=exc, retryable=True/False)`. The framework writes a checkpoint and
allows `mmp resume`.

### `health_check(credentials) -> HealthStatus`

Return `HealthStatus.ok | failed | unknown`. Used by `mmp doctor` and the
wizard to surface "your token works" before a run starts.

## `rules.py`

```python
from core.rules import PlatformRules, Severity, Violation

def _custom_lint(manifest, target_name):
    # ...
    return [Violation(code="MY_CHECK", message="...", severity=Severity.warning)]

MY_RULES = PlatformRules(
    title_max=100,
    body_max=10000,
    cover_required=False,
    extra_lints=[_custom_lint],
)
```

## Trust model for user-installed providers

User providers under `~/.config/mmp/providers/` are not loaded automatically.
On first discovery, `mmp` prompts:

> Trust provider `my-platform` from `~/.config/mmp/providers/my_platform/`? (y/n)

A `y` adds the name to `settings.toml.providers.trusted_user_providers`.

## Testing

Put tests under `<your-dir>/tests/`. Pytest auto-discovers them when run from
the project root. The reference shape:

```python
import json
from core.manifest import Manifest, Target
from providers.my_platform.provider import MyPlatformProvider

def test_validate_passes():
    p = MyPlatformProvider()
    m = Manifest(...)
    res = p.validate(m, m.targets[0])
    assert all(v.severity.value != "error" for v in res.violations)
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/provider-contract.md
git commit -m "docs: add provider authoring guide"
```

---

## Task 4: `docs/credentials.md`

**Files:**
- Create: `docs/credentials.md`

- [ ] **Step 1: Write credentials guide**

```markdown
# Credentials & Vault

multi-media-publisher stores per-provider credentials in an age-encrypted
JSON file and never exposes them in result/log/output.

## File layout

```
~/.config/mmp/
├── credentials.json.age            # encrypted vault
├── age-key.txt                     # private key (chmod 600)
├── providers/                      # user-installed providers (this directory)
└── settings.toml                   # user preferences
```

## Adding credentials

```bash
mmp setup <provider> [--account <name>]
```

You'll be prompted for each `required_credentials` key declared in that
provider's `provider.yaml`. Secrets are read via `getpass` (no echo).

To list what's stored:

```bash
mmp list accounts
# wechat-article:default
# x-article:lewis
```

To delete an account:

```bash
mmp setup <provider> --account <name>
# (re-enter empty values to clear; future: explicit `mmp accounts rm`)
```

## Per-conversation override (ENV)

Any environment variable matching a `required_credentials.key` overrides the
vault for that one run:

```bash
WECHAT_APP_ID=wx... WECHAT_APP_SECRET=... mmp publish manifest.yaml
```

This is the recommended path for CI and one-off testing.

## Multiple accounts

A provider can have many accounts. Use `--account <name>` at setup, and
reference the account in the manifest:

```yaml
targets:
  - target: x-article
    mode: draft
    account: lewis
```

## Rotating

Compromised vault key:

```bash
rm ~/.config/mmp/credentials.json.age ~/.config/mmp/age-key.txt
mmp setup <each provider>   # re-enter all values
```

The new key is auto-generated on first `setup` after deletion.

## What never leaves the vault

- `result.json` (per-run summary)
- `publish-log.md` (per-run timeline)
- console output beyond `(received)` confirmations
- any git-tracked file in this repo

If you find a credential leaked into one of these, report as a P0 bug.

## Future (v0.3)

- macOS Keychain backend
- Linux secret-service backend
- Windows Credential Manager backend

The `Backend` ABC is already in place; switching is config-only once
implemented.
```

- [ ] **Step 2: Commit**

```bash
git add docs/credentials.md
git commit -m "docs: add credentials & vault user guide"
```

---

## Task 5: `docs/manual-verification.md`

**Files:**
- Create: `docs/manual-verification.md`

- [ ] **Step 1: Write manual-verification checklist**

```markdown
# Manual Verification Checklist

Real account testing is **not** in CI. Run these locally before tagging a
release.

## wechat-article

Prerequisites:
- WeChat Official Account with API access enabled
- IP whitelist includes your test machine
- AppID + AppSecret available

Steps:

```bash
mmp setup wechat-article
# Enter WECHAT_APP_ID and WECHAT_APP_SECRET when prompted
mmp doctor
# Expect: providers >= 5; accounts: wechat-article:default
mmp publish examples/longform.yaml --mode-override dry-run
# Expect: RUN_DIR <path>; result.json status=ok mode_actual=dry-run
mmp publish examples/longform.yaml --mode-override draft
# Expect: status=ok, mode_actual=draft-platform, external_id is a draft media_id
# Verify: log into mp.weixin.qq.com → 草稿箱 → see the new draft
```

Cleanup: delete the draft from the WeChat console.

## xiaohongshu

Prerequisites:
- xiaohongshu skill installed locally with `xhs-login` cookie captured
- `XHS_COOKIE_PATH` set in vault to that cookie file

```bash
mmp setup xiaohongshu
mmp publish examples/image-post.yaml --mode-override dry-run
mmp publish examples/image-post.yaml --mode-override draft
# Expect: result.json mode_actual=draft-local
# Verify: <draft_path> file exists and contains the payload
```

## wechat-image

```bash
mmp publish examples/image-post.yaml --mode-override draft
# Expect: <run-dir>/packs/wechat-image/browser-flow.md exists
# Verify: open the guide manually, confirm steps are accurate
```

## x-article

```bash
mmp publish examples/longform.yaml --mode-override draft
# Expect: result.json connector_status=not-implemented
# Manually follow the TODO-connector.md to create a draft
# Verify: x.com/i/articles → drafts shows the new entry
```

## substack

Same pattern as x-article.

## Cross-host check

Verify the same vault works from both hosts:

```bash
# In Claude Code:
python3 scripts/mmp.py list accounts
# In OpenClaw:
python3 scripts/mmp.py list accounts
# Both should show identical accounts.
```

## Sign-off

Tag a release only when:
- [ ] wechat-article real-draft round-trip green
- [ ] xiaohongshu local-draft round-trip green
- [ ] wechat-image guide is accurate
- [ ] x-article + substack TODO docs accurate
- [ ] Cross-host vault read consistent
```

- [ ] **Step 2: Commit**

```bash
git add docs/manual-verification.md
git commit -m "docs: add manual-verification checklist"
```

---

## Task 6: Archive Legacy `references/*.md`

**Files:**
- Move: `references/candidate-skills.md` → `docs/legacy-research.md`
- Delete: `references/image-post-mvp.md`, `references/phase2-audit.md`, `references/workflows.md`, `references/manifest-schema.md`, `references/platform-map.md`
- Delete: `references/` (if empty)

- [ ] **Step 1: Promote candidate-skills as legacy research note**

```bash
git mv references/candidate-skills.md docs/legacy-research.md
```

Prepend a header to `docs/legacy-research.md`:

```markdown
> Archived in v0.2. This file is the original ClawHub skill survey from v0.1
> planning. Kept for historical context; do not edit.

```

- [ ] **Step 2: Delete obsolete reference files**

```bash
git rm references/image-post-mvp.md references/phase2-audit.md \
       references/workflows.md references/manifest-schema.md \
       references/platform-map.md
rmdir references 2>/dev/null || true
```

(`rmdir` is best-effort; if other files remain, leave the directory.)

- [ ] **Step 3: Commit**

```bash
git add docs/legacy-research.md
git diff --cached --stat
git commit -m "docs: archive legacy references; drop superseded files"
```

---

## Task 7: `.claude-plugin/plugin.json`

**Files:**
- Create: `.claude-plugin/plugin.json`

- [ ] **Step 1: Create directory + manifest**

```bash
mkdir -p .claude-plugin
```

`.claude-plugin/plugin.json`:

```json
{
  "name": "multi-media-publisher",
  "version": "0.2.0",
  "description": "Cross-platform content publishing orchestration: 小红书 / 微信图文 / 微信公众号文章 / X Articles / Substack. Wizard-driven manifest creation, draft-first safety, encrypted credential vault.",
  "skills": ["./SKILL.md"],
  "scripts": {
    "publish": "scripts/mmp.py publish",
    "validate": "scripts/mmp.py validate",
    "setup": "scripts/mmp.py setup",
    "list": "scripts/mmp.py list",
    "resume": "scripts/mmp.py resume",
    "doctor": "scripts/mmp.py doctor",
    "wizard": "scripts/mmp.py wizard"
  },
  "homepage": "https://github.com/yxliao-lewis/multi-media-publisher",
  "license": "MIT",
  "keywords": [
    "publishing",
    "social-media",
    "xiaohongshu",
    "wechat",
    "x",
    "substack",
    "claude-code",
    "openclaw"
  ]
}
```

> **Note:** Update `homepage` if the GitHub repo name/owner differs.

- [ ] **Step 2: Commit**

```bash
git add .claude-plugin/plugin.json
git commit -m "feat: add Claude Code plugin manifest"
```

---

## Task 8: Final SKILL.md Polish

**Files:**
- Modify: `SKILL.md`

- [ ] **Step 1: Update version + cross-link to plugin.json**

Edit `SKILL.md` frontmatter:

```yaml
---
name: Multi-media Publisher
description: This skill should be used when the user asks to "多媒体发布", "多平台发布", "同步发布", "cross-post", "publish to multiple", "发到小红书和微信", "发布长文章到公众号/X/Substack", "新发布", "wizard", or wants one content package adapted and published/drafted across Xiaohongshu, WeChat image posts, WeChat Official Account articles, X Articles, Substack, or future video platforms.
version: 0.2.0
---
```

In the body, replace any reference to `Plan N` and replace the providers table with a stable v0.2 table (no Plan-X TODO callouts):

```markdown
## v0.2 supported providers

| Provider | Media | Mode support | Notes |
|---|---|---|---|
| `wechat-article` | longform | dry-run, draft | Real WeChat OA API; needs AppID/AppSecret |
| `xiaohongshu` | image-post (video planned) | dry-run, draft (local) | Uses xiaohongshu skill's `draft.sh` |
| `wechat-image` | image-post | dry-run, draft (browser-flow guide) | UI calibration TODO; guide-only path |
| `x-article` | longform | dry-run, draft (payload + TODO) | No connector yet; manual paste step |
| `substack` | longform | dry-run, draft (payload + TODO) | No connector yet; manual paste step |
```

Remove the "Plan 2", "Plan 3", "Plan 4" TODO markers.

- [ ] **Step 2: Commit**

```bash
git add SKILL.md
git commit -m "docs(skill): final v0.2.0 polish; remove plan-N markers"
```

---

## Task 9: README.md Rewrite

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace `README.md`**

```markdown
# multi-media-publisher

Publish one piece of content to many platforms — 小红书, 微信图文, 微信公众号
文章, X Articles, Substack — through one manifest, with draft-first safety
and an encrypted credential vault.

Works as a Claude Code plugin **and** an OpenClaw skill from the same source.

## Status

v0.2 — provider abstraction + 5 first-party providers + conversational
manifest wizard + age-encrypted vault. See [`docs/HANDOFF.md`](docs/HANDOFF.md).

## Install

### As a Claude Code plugin

```
/plugin install multi-media-publisher
```

(Or clone this repo and point Claude Code at the directory.)

### As an OpenClaw skill

Clone into your skills directory:

```bash
git clone https://github.com/yxliao-lewis/multi-media-publisher.git \
  ~/.openclaw/skills/multi-media-publisher
```

### Python deps

```bash
pip install -e ".[dev]"
```

Requires Python 3.10+.

## Quickstart

### Conversational wizard (recommended)

In Claude Code or OpenClaw, just say what you want:

> 帮我把这篇文章发到公众号、X 长文章、Substack 草稿。

Claude reads `core/wizard/*.md` and walks you through source extraction →
target selection → manifest assembly → draft.

### CLI

```bash
# Validate a manifest
mmp validate examples/longform.yaml

# Configure credentials for a provider
mmp setup wechat-article

# Run a publish (defaults to draft mode in the manifest)
mmp publish examples/longform.yaml

# List providers / accounts / runs
mmp list providers
mmp list accounts
mmp list runs

# Self-check
mmp doctor
```

## Safety

- Default `mode: draft`. Public publishing requires explicit `mode: publish`
  in the manifest **plus** an in-conversation confirmation.
- Credentials are stored in `~/.config/mmp/credentials.json.age` (age-encrypted).
- Secrets never appear in `result.json`, `publish-log.md`, or printed output.
- Full policy: [`docs/safety-policy.md`](docs/safety-policy.md).

## Architecture

- [`docs/architecture.md`](docs/architecture.md) — high-level overview
- [`docs/provider-contract.md`](docs/provider-contract.md) — write your own provider
- [`docs/credentials.md`](docs/credentials.md) — vault and ENV usage
- [`docs/manual-verification.md`](docs/manual-verification.md) — pre-release checklist
- [`docs/superpowers/specs/`](docs/superpowers/specs/) — full design spec

## Project layout

```
core/                    # host-agnostic Python (manifest, providers, vault, runs)
providers/               # bundled first-party providers
  wechat_article/
  xiaohongshu/
  wechat_image/
  x_article/
  substack/
scripts/mmp.py           # CLI entry
.claude-plugin/          # Claude Code plugin manifest
SKILL.md                 # OpenClaw + Claude Code skill manifest
docs/                    # user-facing docs
tests/                   # core tests + integration tests
```

## Contributing

- New provider? Read [`docs/provider-contract.md`](docs/provider-contract.md).
- Bug or design discussion? Open an issue.

## License

MIT.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README for v0.2 install + usage"
```

---

## Task 10: `pyproject.toml` Version Bump + CHANGELOG

**Files:**
- Modify: `pyproject.toml`
- Create: `CHANGELOG.md`

- [ ] **Step 1: Bump version**

In `pyproject.toml`:

```toml
[project]
name = "multi-media-publisher"
version = "0.2.0"
```

(Already 0.2.0 from Plan 1; double-check.)

- [ ] **Step 2: Create `CHANGELOG.md`**

```markdown
# Changelog

## 0.2.0 — 2026-05-XX

Major refactor: provider abstraction + dual-host distribution + wizard.

### Added

- `core/` host-agnostic Python: manifest schema, provider registry,
  credential vault (age-encrypted), run lifecycle, platform rules, settings,
  wizard fragments
- 5 bundled providers: `wechat-article`, `xiaohongshu`, `wechat-image`,
  `x-article`, `substack`
- `scripts/mmp.py` unified CLI: `validate`, `publish`, `setup`, `list`,
  `resume`, `doctor`, `wizard`
- `.claude-plugin/plugin.json` for Claude Code plugin marketplace
- 3-stage conversational wizard (source extraction → target selection →
  manifest assembly) + credential setup wizard
- Manifest schema v0.2: `schema_version`, full-form/short-form targets,
  `defaults` block, `dry-run` mode, account override per target
- Age-encrypted vault at `~/.config/mmp/credentials.json.age`
- GitHub Actions CI matrix (macOS + ubuntu × Python 3.10/3.11/3.12)
- User-facing docs: `architecture.md`, `provider-contract.md`,
  `credentials.md`, `safety-policy.md`, `manual-verification.md`

### Changed

- Default `mode` is `draft`; `publish` requires explicit confirmation
- Manifest fields normalized; lock-file `manifest.lock.json` written per run
- `runs/<ts>-<slug>/` is now self-contained: manifest, lock, packs, result,
  log, checkpoints, artifacts

### Deprecated

- `scripts/prepare_image_post.py`, `scripts/prepare_longform.py`,
  `scripts/execute_image_post.py`, `scripts/adapt_content.py`,
  `scripts/publish_manifest.py`, `scripts/wechat_api_draft.py` — kept as
  thin shims; removal in v0.3

### Removed

- Legacy `references/*.md` (moved to `docs/` or `providers/<name>/notes.md`)

## 0.1.0 — 2026-05 (pre-redesign)

- Initial OpenClaw skill: prepare/execute scripts, image-post + longform
  pipelines, WeChat API dry-run helper, local smoke test.
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml CHANGELOG.md
git commit -m "chore: bump 0.2.0 + CHANGELOG"
```

---

## Task 11: GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create CI workflow**

```bash
mkdir -p .github/workflows
```

`.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    name: ${{ matrix.os }} / py${{ matrix.python-version }}
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]
        python-version: ["3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
          cache-dependency-path: pyproject.toml

      - name: Install
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Lint (ruff)
        run: |
          python -m ruff check .
          python -m ruff format --check .

      - name: Typecheck (mypy)
        run: python -m mypy core providers

      - name: Unit tests
        run: python -m pytest -q

      - name: Smoke test
        env:
          # Provide ephemeral, fake home so smoke writes its vault into a
          # job-local dir (the smoke script also overrides XDG_CONFIG_HOME).
          HOME: ${{ runner.temp }}
        run: python scripts/test_local.py
```

- [ ] **Step 2: Verify YAML parses**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
Expected: no error.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: GitHub Actions matrix (ubuntu + macos × py3.10/3.11/3.12)"
```

---

## Task 12: Update `docs/HANDOFF.md` for v0.2 Completion

**Files:**
- Modify: `docs/HANDOFF.md`

- [ ] **Step 1: Append final status**

```markdown

### Plan 4 status (this commit range)

- `.claude-plugin/plugin.json` published — Claude Code plugin marketplace ready
- `SKILL.md` v0.2.0 final — dual-host description, no plan-N markers
- `README.md` rewritten as install + quickstart
- New docs: `architecture.md`, `provider-contract.md`, `credentials.md`,
  `safety-policy.md`, `manual-verification.md`
- `references/` archived; `legacy-research.md` retained for context
- `.github/workflows/ci.yml` — matrix CI (ubuntu+macos × py3.10/3.11/3.12)
- `CHANGELOG.md` — v0.2.0 release notes
- `pyproject.toml` — version 0.2.0

### v0.2 → v0.3 hand-off

The next milestone:

1. **Real-account verification** — work the `manual-verification.md` checklist
   for wechat-article, xiaohongshu, wechat-image
2. **x-article / substack connectors** — replace TODO-connector.md with real
   draft-creation logic (likely browser automation)
3. **Remove deprecation shims** — drop `scripts/prepare_*`, `scripts/execute_*`,
   `scripts/adapt_content.py`, `scripts/publish_manifest.py`, `scripts/wechat_api_draft.py`
4. **Keychain credential backend** — implement `KeychainBackend`; expose via
   `settings.toml.credentials.backend`
5. **Resume command** — implement `mmp resume <run-dir>` checkpoint replay
6. **Video-post providers** — `xiaohongshu_video`, `wechat_channel`, `douyin`,
   `bilibili`, `youtube_shorts`
7. **User-folder provider auto-trust + signing** — In v0.2 the
   `ProviderRegistry.discover()` defaults to `trust_user=False`, so providers
   in `~/.config/mmp/providers/` are detected (visible via `mmp list providers`
   would show them only if discovery is invoked with trust_user=True manually
   in Python) but not loaded by the CLI. v0.3 will:
     - Read `settings.toml.providers.trusted_user_providers`
     - Prompt the user on first-encounter of an untrusted user provider
     - Add chosen provider to the trusted list
     - Add optional signature verification (independent of trust prompt)

### v0.2 ship checklist

- [ ] All 4 plans' tasks completed and committed
- [ ] CI green on all matrix jobs
- [ ] `mmp doctor` clean on a fresh machine after `pip install -e .`
- [ ] Real-account verification (see `docs/manual-verification.md`) green
- [ ] Tag `v0.2.0`
- [ ] Submit to Claude Code plugin marketplace
```

- [ ] **Step 2: Commit**

```bash
git add docs/HANDOFF.md
git commit -m "docs(handoff): note Plan 4 completion + v0.3 roadmap"
```

---

## Task 13: Final Lint + Test + Tag

- [ ] **Step 1: Run full quality gate**

```bash
make test
```

Expected: lint + typecheck + unit + smoke all green.

- [ ] **Step 2: Verify CI YAML parses with GitHub's tooling (optional)**

If `act` is installed:

```bash
act -l
```

Expected: lists the `test` job. Skip if `act` is unavailable.

- [ ] **Step 3: Verify package install from clean env**

```bash
python3 -m venv /tmp/mmp-clean
/tmp/mmp-clean/bin/pip install -e ".[dev]"
/tmp/mmp-clean/bin/python -c "from core import manifest, provider, credentials, run; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 4: Cleanup any straggling diffs**

```bash
git status
git diff --cached --quiet || git commit -m "chore(plan-4): final cleanup"
```

- [ ] **Step 5: Tag (only if all checks above pass AND user is ready to release)**

```bash
git tag v0.2.0 -m "v0.2.0 — provider abstraction + dual-host + wizard"
git push origin v0.2.0
```

> **Skip Step 5 if** real-account verification (`docs/manual-verification.md`)
> hasn't been done yet. Tag only after green real-account dry-run+draft for at
> least `wechat-article` and `xiaohongshu`.

---

## Self-Review Checklist

- [ ] All 13 tasks committed
- [ ] `make test` green
- [ ] `.claude-plugin/plugin.json` exists with correct version
- [ ] `SKILL.md` no longer references "Plan N"
- [ ] `README.md` rewritten for install + quickstart
- [ ] `docs/architecture.md`, `docs/provider-contract.md`, `docs/credentials.md`,
      `docs/safety-policy.md`, `docs/manual-verification.md` all present
- [ ] `references/` directory empty or contains only files we explicitly kept
- [ ] `.github/workflows/ci.yml` parses
- [ ] `CHANGELOG.md` v0.2.0 entry complete
- [ ] Spec sections covered: §9 (dual-host), §11 (CI), §13 risks acknowledged
- [ ] Spec items deferred to v0.3: keychain backend, resume, video-post,
      provider signing, real X/Substack connectors

## Hand-off

v0.2 is feature-complete after this plan. The next steps live in
`docs/HANDOFF.md` under "v0.2 → v0.3 hand-off". The first action of v0.3 is
real-account verification per `docs/manual-verification.md`.
