# Plan 2 — Wizard Flow

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hand-written manifest YAML with a 3-stage Claude-driven conversational wizard (source extraction → target selection → manifest assembly), plus a setup-credentials sub-flow.

**Architecture:** The wizard is split between **markdown prompt fragments** (read by Claude during conversation) and a **thin Python helper layer** (dumps current registry/credential context as JSON for Claude; commits validated manifests to disk). Claude is the actual driver; Python supplies state and validation.

**Tech Stack:** Python 3.10+ (stdlib `tomllib` + `tomli_w` for settings), pytest. No new external deps.

**Spec reference:** `docs/superpowers/specs/2026-05-05-multi-media-publisher-redesign-design.md` §7 (Wizard Flow), §6.4 (Setup wizard).

**Depends on:** Plan 1 complete (`core/` + `providers/wechat_article/` + `scripts/mmp.py` skeleton with `wizard` stub).

---

## File Structure

**Created in this plan:**

```
core/wizard/__init__.py
core/wizard/source_extraction.md
core/wizard/target_selection.md
core/wizard/manifest_assembly.md
core/wizard/credential_setup.md
core/wizard/loader.py                 # render prompt fragments with context vars
core/wizard/context.py                # build runtime context (providers/accounts/settings)
core/wizard/commit.py                 # validate and write a draft manifest
core/settings.py                      # read/write ~/.config/mmp/settings.toml
tests/core/test_settings.py
tests/core/test_wizard_context.py
tests/core/test_wizard_loader.py
tests/core/test_wizard_commit.py
tests/integration/test_wizard_cli.py
```

**Modified:**

```
scripts/mmp.py                         # wire up wizard subcommand; route setup through credential_setup
SKILL.md                               # add wizard triggers + "how Claude runs the wizard" section
pyproject.toml                         # add tomli_w to deps
docs/HANDOFF.md                        # Plan 2 status note
```

---

## Task 1: `core/settings.py` — settings.toml read/write

**Files:**
- Create: `core/settings.py`
- Test: `tests/core/test_settings.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add `tomli_w` to dependencies**

Edit `pyproject.toml`, in `[project] dependencies`:

```toml
dependencies = [
    "pyyaml>=6.0",
    "pyrage>=1.1",
    "requests>=2.31",
    "tomli_w>=1.0",
]
```

- [ ] **Step 2: Write failing test**

`tests/core/test_settings.py`:

```python
import pytest

from core import settings


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_default_when_missing(isolated):
    s = settings.load()
    assert s.default_mode == "draft"
    assert s.wizard_enabled is True
    assert s.auto_save_manifest is True
    assert s.trusted_user_providers == []


def test_set_and_reload(isolated):
    s = settings.load()
    s.default_mode = "dry-run"
    s.trusted_user_providers = ["my-thing"]
    settings.save(s)

    s2 = settings.load()
    assert s2.default_mode == "dry-run"
    assert s2.trusted_user_providers == ["my-thing"]


def test_settings_file_path(isolated):
    s = settings.load()
    settings.save(s)
    assert (isolated / ".config" / "mmp" / "settings.toml").exists()
```

- [ ] **Step 3: Run test (should fail)**

Run: `pytest tests/core/test_settings.py -v`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement `core/settings.py`**

```python
"""Settings persistence at ~/.config/mmp/settings.toml.

Defaults are returned when the file is missing; save() writes back the full
settings object.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

import tomli_w

from core import host


@dataclass
class Settings:
    default_mode: str = "draft"
    wizard_enabled: bool = True
    auto_save_manifest: bool = True
    trusted_user_providers: list[str] = field(default_factory=list)


def load() -> Settings:
    p = host.settings_path()
    if not p.exists():
        return Settings()
    with p.open("rb") as f:
        data = tomllib.load(f)
    wiz = data.get("wizard", {})
    providers = data.get("providers", {})
    return Settings(
        default_mode=data.get("default_mode", "draft"),
        wizard_enabled=wiz.get("enabled", True),
        auto_save_manifest=wiz.get("auto_save_manifest", True),
        trusted_user_providers=list(providers.get("trusted_user_providers", [])),
    )


def save(s: Settings) -> Path:
    p = host.settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "default_mode": s.default_mode,
        "wizard": {
            "enabled": s.wizard_enabled,
            "auto_save_manifest": s.auto_save_manifest,
        },
        "providers": {
            "trusted_user_providers": list(s.trusted_user_providers),
        },
    }
    with p.open("wb") as f:
        tomli_w.dump(payload, f)
    return p
```

- [ ] **Step 5: Run test (should pass)**

Run: `pytest tests/core/test_settings.py -v`
Expected: PASS — 3 passed.

- [ ] **Step 6: Commit**

```bash
git add core/settings.py tests/core/test_settings.py pyproject.toml
git commit -m "feat(core): add settings.toml read/write"
```

---

## Task 2: `core/wizard/` Skeleton + `loader.py`

**Files:**
- Create: `core/wizard/__init__.py`
- Create: `core/wizard/loader.py`
- Test: `tests/core/test_wizard_loader.py`

- [ ] **Step 1: Create directory + init**

```bash
mkdir -p core/wizard
touch core/wizard/__init__.py
```

- [ ] **Step 2: Write failing test**

`tests/core/test_wizard_loader.py`:

```python
from pathlib import Path

import pytest

from core.wizard.loader import list_stages, render


def test_list_stages():
    stages = list_stages()
    assert "source_extraction" in stages
    assert "target_selection" in stages
    assert "manifest_assembly" in stages
    assert "credential_setup" in stages


def test_render_basic_substitution(tmp_path):
    # write a tiny test prompt to a temp dir and render it
    test_prompt = tmp_path / "demo.md"
    test_prompt.write_text("Hello, {{name}}!\n", encoding="utf-8")
    out = render(test_prompt, name="World")
    assert out.strip() == "Hello, World!"


def test_render_missing_var_raises(tmp_path):
    test_prompt = tmp_path / "x.md"
    test_prompt.write_text("Hello {{missing}}", encoding="utf-8")
    with pytest.raises(KeyError):
        render(test_prompt)


def test_render_real_stage_returns_text():
    text = render("source_extraction")
    assert len(text) > 0
    assert isinstance(text, str)
```

- [ ] **Step 3: Run test (should fail)**

Run: `pytest tests/core/test_wizard_loader.py -v`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement `core/wizard/loader.py`**

```python
"""Load and render markdown prompt fragments for the wizard.

Templating: tiny {{var}} substitution, KeyError on missing var. Not Jinja —
prompts should stay simple and human-editable.
"""

from __future__ import annotations

import re
from pathlib import Path

_STAGES = ["source_extraction", "target_selection", "manifest_assembly", "credential_setup"]
_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_FRAGMENT_DIR = Path(__file__).resolve().parent


def list_stages() -> list[str]:
    return list(_STAGES)


def render(stage_or_path: str | Path, **vars: object) -> str:
    if isinstance(stage_or_path, Path):
        path = stage_or_path
    else:
        path = _FRAGMENT_DIR / f"{stage_or_path}.md"
    text = path.read_text(encoding="utf-8")

    def _sub(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in vars:
            raise KeyError(f"missing wizard variable: {key}")
        return str(vars[key])

    return _PLACEHOLDER.sub(_sub, text)
```

- [ ] **Step 5: Add placeholder fragments (to satisfy `list_stages` real-load test)**

Create empty placeholder files (real content arrives in Tasks 4–7):

```bash
for f in source_extraction target_selection manifest_assembly credential_setup; do
  echo "<!-- wizard: $f (placeholder, replaced in subsequent tasks) -->" > "core/wizard/$f.md"
done
```

- [ ] **Step 6: Run test (should pass)**

Run: `pytest tests/core/test_wizard_loader.py -v`
Expected: PASS — 4 passed.

- [ ] **Step 7: Commit**

```bash
git add core/wizard/__init__.py core/wizard/loader.py core/wizard/*.md tests/core/test_wizard_loader.py
git commit -m "feat(wizard): add loader + stage placeholders"
```

---

## Task 3: `core/wizard/context.py` — Build Runtime Context for Claude

**Files:**
- Create: `core/wizard/context.py`
- Test: `tests/core/test_wizard_context.py`

- [ ] **Step 1: Write failing test**

`tests/core/test_wizard_context.py`:

```python
import json
from pathlib import Path

import pytest
import yaml

from core.wizard.context import build_context


def _write_provider(root: Path, name: str, snake: str, media_types: list[str]) -> None:
    pdir = root / snake
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "__init__.py").write_text("")
    (pdir / "provider.yaml").write_text(
        yaml.safe_dump(
            {
                "name": name,
                "display_name": name,
                "media_types": media_types,
                "capabilities": {"draft": True, "publish": False, "schedule": False},
                "required_credentials": [],
                "entry": "provider:P",
                "schema_version": 1,
            }
        ),
        encoding="utf-8",
    )
    (pdir / "provider.py").write_text(
        "from core.provider import Provider\n"
        "from core.rules import PlatformRules\n"
        "class P(Provider):\n"
        f"    name = '{name}'\n"
        f"    display_name = '{name}'\n"
        f"    media_types = {media_types}\n"
        "    capabilities = {'draft': True, 'publish': False, 'schedule': False}\n"
        "    required_credentials = []\n"
        "    platform_rules = PlatformRules()\n"
        "    def validate(self, m, t): return None\n"
        "    def prepare(self, m, t, r): return None\n"
        "    def execute(self, r, t, m, c): return None\n"
    )


def test_context_lists_providers(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_provider(bundled, name="lf-only", snake="lf_only", media_types=["longform"])
    _write_provider(bundled, name="img-only", snake="img_only", media_types=["image-post"])

    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    ctx = build_context(bundled_dir=bundled)
    assert any(p["name"] == "lf-only" for p in ctx["providers"])
    assert any(p["name"] == "img-only" for p in ctx["providers"])


def test_context_filters_by_type(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_provider(bundled, name="lf-only", snake="lf_only", media_types=["longform"])
    _write_provider(bundled, name="img-only", snake="img_only", media_types=["image-post"])

    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    ctx = build_context(bundled_dir=bundled, media_type="longform")
    names = [p["name"] for p in ctx["providers"]]
    assert "lf-only" in names
    assert "img-only" not in names


def test_context_includes_accounts_and_settings(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    ctx = build_context(bundled_dir=tmp_path / "empty")
    assert "accounts" in ctx
    assert "settings" in ctx
    assert ctx["settings"]["default_mode"] == "draft"


def test_context_marks_credential_status(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    pdir = bundled / "needy"
    pdir.mkdir()
    (pdir / "__init__.py").write_text("")
    (pdir / "provider.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "needy",
                "display_name": "needy",
                "media_types": ["longform"],
                "capabilities": {"draft": True, "publish": False, "schedule": False},
                "required_credentials": [{"key": "FOO", "description": "foo", "secret": True}],
                "entry": "provider:P",
                "schema_version": 1,
            }
        ),
        encoding="utf-8",
    )
    (pdir / "provider.py").write_text(
        "from core.provider import Provider\n"
        "from core.rules import PlatformRules\n"
        "class P(Provider):\n"
        "    name='needy'\n    display_name='needy'\n    media_types=['longform']\n"
        "    capabilities={'draft': True, 'publish': False, 'schedule': False}\n"
        "    required_credentials=[]\n    platform_rules=PlatformRules()\n"
        "    def validate(self,m,t): return None\n"
        "    def prepare(self,m,t,r): return None\n"
        "    def execute(self,r,t,m,c): return None\n"
    )
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    ctx = build_context(bundled_dir=bundled)
    p = next(p for p in ctx["providers"] if p["name"] == "needy")
    assert p["credential_status"] == "missing"
```

- [ ] **Step 2: Run test (should fail)**

Run: `pytest tests/core/test_wizard_context.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `core/wizard/context.py`**

```python
"""Build a JSON context object describing current wizard state.

Claude reads this (via `mmp wizard --dump-context`) to know which providers
are available, which accounts have credentials, and what the user's settings
say. The context is the bridge between Python state and Claude conversation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import settings as settings_mod
from core.credentials import CredentialStore
from core.errors import MissingCredentialError
from core.provider import ProviderRegistry


def build_context(
    bundled_dir: Path | None = None,
    user_dir: Path | None = None,
    media_type: str | None = None,
) -> dict[str, Any]:
    reg = ProviderRegistry(bundled_dir=bundled_dir, user_dir=user_dir)
    s = settings_mod.load()
    reg.discover(trust_user=False)

    store = CredentialStore()
    accounts = store.list_accounts()

    providers_out: list[dict[str, Any]] = []
    for info in reg.list(media_type=media_type):
        # credential status
        if not info.required_credentials:
            cred_status = "n/a"
        else:
            keys = [c.key for c in info.required_credentials]
            try:
                store.get(info.name, "default", required_keys=keys)
                cred_status = "ok"
            except MissingCredentialError:
                cred_status = "missing"

        providers_out.append(
            {
                "name": info.name,
                "display_name": info.display_name,
                "media_types": info.media_types,
                "capabilities": info.capabilities,
                "required_credentials": [
                    {"key": c.key, "description": c.description, "secret": c.secret}
                    for c in info.required_credentials
                ],
                "credential_status": cred_status,
                "source": info.source,
            }
        )

    return {
        "providers": providers_out,
        "accounts": accounts,
        "settings": {
            "default_mode": s.default_mode,
            "wizard_enabled": s.wizard_enabled,
            "auto_save_manifest": s.auto_save_manifest,
        },
    }
```

- [ ] **Step 4: Run test (should pass)**

Run: `pytest tests/core/test_wizard_context.py -v`
Expected: PASS — 4 passed.

- [ ] **Step 5: Commit**

```bash
git add core/wizard/context.py tests/core/test_wizard_context.py
git commit -m "feat(wizard): build_context for Claude consumption"
```

---

## Task 4: `core/wizard/source_extraction.md` — Stage 1 Prompt

**Files:**
- Modify: `core/wizard/source_extraction.md` (replacing placeholder)

- [ ] **Step 1: Write Stage 1 prompt**

```markdown
# Wizard Stage 1 — Source Extraction

You are guiding the user to convert source content into a structured draft.
**Do not write the manifest yet** — that happens in Stage 3 (`manifest_assembly.md`).

## Goal of this stage

Produce an internal draft holding these fields (in your conversation memory, not on disk yet):

- `type`: one of `image-post` / `longform` / `video-post`
- `title`: short title
- `body`: full content (Markdown for longform; caption text for image-post)
- `summary`: optional one-line synopsis
- `cover`: optional path to a cover image
- `images`: list of image paths (image-post only)
- `video`: path to video file (video-post only)
- `tags`: optional tag list
- `cta`: optional call-to-action text

## How to behave

1. Read whatever the user has shared so far — pasted text, file paths, links, screenshots.
2. **Determine `type`** by what's there:
   - Multiple images + short caption → `image-post`
   - Long markdown article → `longform`
   - Video file → `video-post`
   - Ambiguous → ask one short question
3. **Extract candidate fields** silently. Do not fabricate; if a field is unknown, leave it None.
4. **Reflect back** the extraction in 4–6 lines:

   ```
   type: longform
   title: <proposed>
   body: <first 80 chars>...
   cover: <path or "missing">
   tags: <inferred or "(none)">
   ```

5. **Ask ONE blocking question at a time**, only for missing required fields. Required:
   - `type` (always)
   - `title` (always)
   - `body` (always)
   - `cover` for `longform` (most providers require it)
   - `images` for `image-post`
6. Do NOT ask about target platforms here — that is Stage 2.
7. Do NOT ask about `mode` — that is Stage 2/3.

## When to advance

Once `type`, `title`, `body`, and (cover OR images depending on type) are present,
say:

> Source captured. Moving to target selection.

Then proceed to load `core/wizard/target_selection.md` and follow it.

## Examples of good behavior

- User pastes a markdown file path → extract `body` from the file, infer `title`
  from the first H1 heading, ask only for cover.
- User pastes a folder of images → list as `images`, ask for caption, infer
  `type=image-post`.
- User pastes raw text → ask whether it's the full article or a draft to expand.
```

- [ ] **Step 2: Commit**

```bash
git add core/wizard/source_extraction.md
git commit -m "feat(wizard): add stage 1 source_extraction prompt"
```

---

## Task 5: `core/wizard/target_selection.md` — Stage 2 Prompt

**Files:**
- Modify: `core/wizard/target_selection.md`

- [ ] **Step 1: Write Stage 2 prompt**

```markdown
# Wizard Stage 2 — Target Selection

You have a draft from Stage 1. Now choose where to publish.

## Goal of this stage

Produce a list of `Target` entries:

```json
[
  {"target": "wechat-article", "mode": "draft", "account": "default", "options": {}},
  {"target": "x-article", "mode": "draft", "account": "lewis", "options": {}}
]
```

## How to behave

1. **Get available providers**: run

   ```bash
   python3 scripts/mmp.py wizard --dump-context --type <draft.type>
   ```

   The output is JSON with `providers`, `accounts`, `settings`.

2. **Filter to compatible providers**: media_types must include the draft's `type`.

3. **Show the list** to the user with status markers:

   ```
   Available targets for <type>:
     ✓ wechat-article    (creds: ok)        — 微信公众号文章
     ✗ xiaohongshu       (creds: missing)   — 小红书图文 [run `mmp setup xiaohongshu` first]
     ✓ x-article         (creds: ok)        — X Articles
     ✓ substack          (creds: ok)        — Substack
   ```

4. **Ask which targets to use** as a multi-pick (e.g. "1, 3" or names).

5. **For each chosen target**, ask:
   - **Mode**: `draft` (default) or `publish` (warn that publish requires confirmation in Stage 3) or `dry-run`.
   - **Account**: if multiple accounts exist for that provider, list them. Otherwise default to `default`.
   - **Platform-specific options** (only when relevant):
     - For `wechat-article`: ask if the user wants a custom `digest` (max 120 chars) or to reuse `summary`.
     - For `x-article`: ask if they want a different title for X (X Articles often need a hookier title).
     - For `xiaohongshu`: ask about hashtags / hook. Title max 20 chars.
     - For `substack`: ask about subtitle / paid-tier flag.

6. Do NOT proceed if a chosen target has `credential_status: missing`. Tell the
   user which `mmp setup <provider>` to run, and either wait for them to do it
   (then re-run `--dump-context`) or drop that target.

## When to advance

Once you have at least one target with mode and account, say:

> Targets locked in. Moving to manifest assembly.

Proceed to `core/wizard/manifest_assembly.md`.

## What NOT to do

- Don't pick targets the user didn't ask for.
- Don't silently downgrade `publish` to `draft` — flag it explicitly.
- Don't ask about platforms not in the registry.
```

- [ ] **Step 2: Commit**

```bash
git add core/wizard/target_selection.md
git commit -m "feat(wizard): add stage 2 target_selection prompt"
```

---

## Task 6: `core/wizard/manifest_assembly.md` — Stage 3 Prompt

**Files:**
- Modify: `core/wizard/manifest_assembly.md`

- [ ] **Step 1: Write Stage 3 prompt**

```markdown
# Wizard Stage 3 — Manifest Assembly

You now have a Stage 1 draft and a Stage 2 target list. Time to render the
manifest, validate it, get user approval, and persist.

## Goal of this stage

1. Render `manifest.yaml` from collected info.
2. Validate via `python3 scripts/mmp.py validate <tmp>`.
3. Show the user the rendered YAML AND the violation report.
4. On approval, commit via `python3 scripts/mmp.py wizard --commit <path>`.

## Render rules

- Always include `schema_version: "0.2"` at the top.
- Use full-form targets when modes/accounts/options differ; short-form (string)
  when all defaults apply.
- For body: if the user pasted file content, write the file out to a sibling
  path and reference it with `./<file>.md`. If body is short and inline, embed.
- Cover and images: keep absolute paths if user gave absolute; otherwise
  relative to the manifest file.

## Validation flow

1. Write the rendered YAML to a temp path:

   ```bash
   tmp=$(mktemp -d)/manifest.yaml
   # write yaml content to $tmp
   ```

2. Run validate:

   ```bash
   python3 scripts/mmp.py validate "$tmp"
   ```

3. Parse the output:
   - Exit 0 + "OK" → green light.
   - Exit 2 with "ERROR" lines → blocking violations; surface each as
     "violation: <code> — <message>" and tell the user how to fix.
   - Lines starting with "WARN" → soft warnings; show them but allow continue.

## Approval gate

Show the user:

```
Manifest:
<rendered yaml>

Validation: <OK | N errors, M warnings>
[errors and warnings listed]

Confirm? (y/n/edit)
```

- `y` → commit.
- `n` → return to Stage 2 to revise targets, or Stage 1 to revise content.
- `edit` → ask which field to change, modify, re-render, re-validate.

## Publish-mode safety gate

If ANY target has `mode: publish`, after the user says `y`, ask one more time:

> The following targets will publish PUBLICLY (not just draft):
>   - wechat-article (account: default)
>   - x-article (account: lewis)
>
> Confirm public publish? (yes/no)

Only proceed on exact match `yes`. Anything else → downgrade to `draft` for
safety and inform the user.

## Commit

```bash
python3 scripts/mmp.py wizard --commit /tmp/manifest.yaml
```

The CLI prints `RUN_DIR <path>`. The manifest is now at `<RUN_DIR>/manifest.yaml`
and a `manifest.lock.json` is generated.

## Hand-off

Tell the user the run dir and ask whether to also execute now:

> Manifest ready at `<RUN_DIR>/manifest.yaml`. Execute now?
>   yes    → run `mmp publish <RUN_DIR>/manifest.yaml`
>   later  → I'll stop here; run `mmp publish` when you're ready.
```

- [ ] **Step 2: Commit**

```bash
git add core/wizard/manifest_assembly.md
git commit -m "feat(wizard): add stage 3 manifest_assembly prompt"
```

---

## Task 7: `core/wizard/credential_setup.md` — Setup Flow Prompt

**Files:**
- Modify: `core/wizard/credential_setup.md`

- [ ] **Step 1: Write credential setup prompt**

```markdown
# Wizard — Credential Setup

Triggered when:
- User says "setup credentials" / "添加账号" / "configure <provider>"
- A different stage discovers `credential_status: missing` for a target

## Goal

Populate `~/.config/mmp/credentials.json.age` with the keys the chosen
provider's `required_credentials` list. ENV variables override vault for
the current session.

## How to behave

1. **Identify provider + account**.
   - Provider: ask if not given (e.g. "Which provider? wechat-article / xiaohongshu / x-article / substack")
   - Account: default is `default`. Multi-account users may want `lewis`, `work`, etc.

2. **Show what's needed**: run

   ```bash
   python3 scripts/mmp.py wizard --dump-context | jq '.providers[] | select(.name=="<NAME>")'
   ```

   List each `required_credentials` entry with its `description` and `setup_hint`.

3. **For each key**, prompt the user:
   - If `secret: false`: ask normally; the value is shown in the conversation (e.g. AppID).
   - If `secret: true`: instruct user to paste in chat; warn that this conversation may be logged on their side. **Never echo the secret back in your reply.** Confirm receipt with "(received)".

4. **Persist** by running:

   ```bash
   python3 scripts/mmp.py setup <provider> --account <account>
   ```

   This subcommand prompts via stdin/getpass for each key. **Tell the user this
   is the safer path** — they enter the secret directly into the CLI, never
   into chat.

   Alternative (one-shot, less secure): pass through ENV-prefixed values:

   ```bash
   WECHAT_APP_ID=wx... WECHAT_APP_SECRET=... \
     python3 scripts/mmp.py publish manifest.yaml
   ```

5. **Verify**: run

   ```bash
   python3 scripts/mmp.py doctor
   ```

   Confirm the account appears in `accounts:` count.

6. **Optional: health check** (only if user wants the network round-trip):

   For wechat-article: verify by calling `get_access_token`. The provider's
   `health_check` returns `ok` / `failed`. We do not expose this in the CLI in
   v0.2; tell the user it'll come in v0.3.

## Security reminders to surface

- Tell the user: "I will not store, re-display, or log this secret."
- If the user pastes a secret in chat, advise them: "Consider rotating this key
  after we're done — chat history is on your side."
- Never pass secrets as command-line arguments (visible in `ps`).
```

- [ ] **Step 2: Commit**

```bash
git add core/wizard/credential_setup.md
git commit -m "feat(wizard): add credential_setup prompt"
```

---

## Task 8: `core/wizard/commit.py` — Commit a Validated Manifest

**Files:**
- Create: `core/wizard/commit.py`
- Test: `tests/core/test_wizard_commit.py`

- [ ] **Step 1: Write failing test**

`tests/core/test_wizard_commit.py`:

```python
from pathlib import Path

import pytest

from core.errors import ManifestError
from core.wizard.commit import commit_manifest


VALID_YAML = """\
schema_version: "0.2"
type: longform
title: "Test"
body: "inline body"
mode: dry-run
targets:
  - wechat-article
"""


def test_commit_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("MMP_RUNS_DIR", str(tmp_path / "runs"))
    src = tmp_path / "src.yaml"
    src.write_text(VALID_YAML, encoding="utf-8")

    run_dir = commit_manifest(src)
    assert run_dir.exists()
    assert (run_dir / "manifest.yaml").read_text() == VALID_YAML
    assert (run_dir / "manifest.lock.json").exists()


def test_commit_invalid_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("MMP_RUNS_DIR", str(tmp_path / "runs"))
    src = tmp_path / "src.yaml"
    src.write_text("not valid yaml: ::", encoding="utf-8")
    with pytest.raises(ManifestError):
        commit_manifest(src)
```

- [ ] **Step 2: Run test (should fail)**

Run: `pytest tests/core/test_wizard_commit.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `core/wizard/commit.py`**

```python
"""Commit a validated manifest from the wizard into a fresh run dir."""

from __future__ import annotations

from pathlib import Path

from core.manifest import load_manifest, write_lock
from core.run import Run


def commit_manifest(src_path: str | Path) -> Path:
    src = Path(src_path).resolve()
    manifest = load_manifest(src)

    run = Run.create(
        title=manifest.title,
        mmp_version="0.2.0",
        host="wizard",
        mode=manifest.mode,
    )
    target_path = run.dir / "manifest.yaml"
    target_path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    write_lock(manifest, run.dir)
    run.log("WIZARD_COMMIT", source=str(src))
    return run.dir
```

- [ ] **Step 4: Run test (should pass)**

Run: `pytest tests/core/test_wizard_commit.py -v`
Expected: PASS — 2 passed.

- [ ] **Step 5: Commit**

```bash
git add core/wizard/commit.py tests/core/test_wizard_commit.py
git commit -m "feat(wizard): commit_manifest validates and writes to run dir"
```

---

## Task 9: Wire `mmp wizard` Subcommand

**Files:**
- Modify: `scripts/mmp.py`
- Test: `tests/integration/test_wizard_cli.py`

- [ ] **Step 1: Replace `cmd_wizard` and update parser in `scripts/mmp.py`**

Replace the existing wizard parser block with:

```python
    sub_wizard = sub.add_parser("wizard", help="Conversational manifest wizard")
    sub_wizard.add_argument("--type", choices=["image-post", "longform", "video-post"])
    sub_wizard.add_argument("--targets", default=None, help="Comma-separated target names")
    sub_wizard.add_argument(
        "--dump-context",
        action="store_true",
        help="Dump current context as JSON for Claude to read",
    )
    sub_wizard.add_argument(
        "--commit",
        metavar="MANIFEST_PATH",
        default=None,
        help="Validate a manifest YAML and persist as a new run dir",
    )
```

Replace `cmd_wizard` body:

```python
def cmd_wizard(args: argparse.Namespace) -> int:
    if args.dump_context:
        from core.wizard.context import build_context
        ctx = build_context(media_type=args.type)
        print(json.dumps(ctx, indent=2, ensure_ascii=False))
        return 0
    if args.commit:
        from core.wizard.commit import commit_manifest
        from core.errors import MMPError
        try:
            run_dir = commit_manifest(args.commit)
            print(f"RUN_DIR  {run_dir}")
            return 0
        except MMPError as e:
            print(f"ERROR  {e}", file=sys.stderr)
            return 2
    # interactive (no flags) — Claude is expected to drive via SKILL.md prompts
    print(
        "wizard interactive mode is driven by Claude reading core/wizard/*.md.\n"
        "Run with --dump-context to fetch state, or --commit <path> to persist a manifest.",
        file=sys.stderr,
    )
    return 1
```

- [ ] **Step 2: Write integration test**

`tests/integration/test_wizard_cli.py`:

```python
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def _run(*args, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mmp.py"), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_dump_context_returns_json(tmp_path):
    p = _run(
        "wizard",
        "--dump-context",
        env_extra={
            "MMP_RUNS_DIR": str(tmp_path / "runs"),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        },
    )
    assert p.returncode == 0
    data = json.loads(p.stdout)
    assert "providers" in data
    assert "accounts" in data
    assert "settings" in data


def test_dump_context_filters_by_type(tmp_path):
    p = _run(
        "wizard",
        "--dump-context",
        "--type",
        "longform",
        env_extra={
            "MMP_RUNS_DIR": str(tmp_path / "runs"),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        },
    )
    assert p.returncode == 0
    data = json.loads(p.stdout)
    for prov in data["providers"]:
        assert "longform" in prov["media_types"]


def test_commit_writes_run_dir(tmp_path):
    src = tmp_path / "m.yaml"
    src.write_text(
        'schema_version: "0.2"\n'
        "type: longform\n"
        'title: "X"\n'
        'body: "hi"\n'
        "mode: dry-run\n"
        "targets: [wechat-article]\n",
        encoding="utf-8",
    )
    p = _run(
        "wizard",
        "--commit",
        str(src),
        env_extra={
            "MMP_RUNS_DIR": str(tmp_path / "runs"),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        },
    )
    assert p.returncode == 0, p.stderr
    assert "RUN_DIR" in p.stdout
    runs = list((tmp_path / "runs").iterdir())
    assert len(runs) == 1
    assert (runs[0] / "manifest.yaml").exists()
    assert (runs[0] / "manifest.lock.json").exists()
```

- [ ] **Step 3: Run test (should pass)**

Run: `pytest tests/integration/test_wizard_cli.py -v`
Expected: PASS — 3 passed.

- [ ] **Step 4: Commit**

```bash
git add scripts/mmp.py tests/integration/test_wizard_cli.py
git commit -m "feat(cli): wire mmp wizard --dump-context and --commit"
```

---

## Task 10: Update `cmd_setup` to Reference Wizard Prompt

**Files:**
- Modify: `scripts/mmp.py`

- [ ] **Step 1: Augment `cmd_setup` to mention the prompt fragment**

Replace the existing `cmd_setup` opening lines:

```python
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
    print(
        f"Configure {args.provider} (account: {args.account}). "
        "Press Enter to skip a key.\n"
        "(For Claude-driven setup, see core/wizard/credential_setup.md.)"
    )
    for spec in provider.required_credentials:
        prompt = f"  {spec.key}"
        if spec.description:
            prompt += f" ({spec.description})"
        if spec.setup_hint:
            prompt += f"  hint: {spec.setup_hint}"
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
```

- [ ] **Step 2: Quick manual sanity check**

Run: `python3 scripts/mmp.py setup --help`
Expected: shows usage with `--account` option.

- [ ] **Step 3: Commit**

```bash
git add scripts/mmp.py
git commit -m "feat(cli): improve setup prompts; reference credential_setup.md"
```

---

## Task 11: SKILL.md — Add Wizard Triggers + Claude-Driven Flow

**Files:**
- Modify: `SKILL.md`

- [ ] **Step 1: Replace the SKILL.md `description:` and add a wizard section**

In `SKILL.md` frontmatter, **append** the following triggers to the `description:` line so the router catches wizard intent:

```
... or "新发布", "帮我发一组到", "wizard", "guide me to publish"
```

Append a new section after the `Default mode = draft` block:

```markdown
## Wizard Mode

When the user says "新发布", "帮我发一组到 X / Y", "publish to ...", "cross-post",
or pastes content with publishing intent, run the **3-stage wizard** instead of
asking them to write a manifest:

1. **Stage 1 — Source Extraction**: read `core/wizard/source_extraction.md` and
   follow the instructions there. Extract `type`, `title`, `body`, `cover`,
   `images`, `tags`, `cta` into your conversation memory. Don't write files yet.

2. **Stage 2 — Target Selection**: read `core/wizard/target_selection.md`. Run
   `python3 scripts/mmp.py wizard --dump-context --type <T>` to fetch available
   providers + credential status + accounts. Ask which targets, modes, accounts.

3. **Stage 3 — Manifest Assembly**: read `core/wizard/manifest_assembly.md`.
   Render YAML, write to a temp file, validate via `python3 scripts/mmp.py validate`,
   show the user, get approval. On approve, run `python3 scripts/mmp.py wizard --commit <path>`.

For setup credentials flows ("配置凭证", "setup wechat-article account"), read
`core/wizard/credential_setup.md`. Direct the user to run `mmp setup <provider>`
locally — never ask them to paste a secret into chat unless they insist.

## Public-publish Gate

If a wizard run would result in `mode: publish` for any target, ALWAYS:

1. Show the rendered manifest first.
2. Ask "Confirm public publish? (yes/no)".
3. Proceed only on exact match `yes`. Anything else → downgrade to `draft`.

This rule overrides any earlier user permission. Each public publish is a fresh
ask in the active conversation.
```

- [ ] **Step 2: Commit**

```bash
git add SKILL.md
git commit -m "docs(skill): add wizard mode and public-publish gate"
```

---

## Task 12: Update HANDOFF.md

**Files:**
- Modify: `docs/HANDOFF.md`

- [ ] **Step 1: Append Plan 2 status block**

Append to `docs/HANDOFF.md`:

```markdown

### Plan 2 status (this commit range)

- `core/wizard/` package: source_extraction / target_selection / manifest_assembly / credential_setup prompts
- `core/wizard/loader.py`: render Markdown fragments with {{var}} substitution
- `core/wizard/context.py`: dump providers/accounts/settings as JSON for Claude
- `core/wizard/commit.py`: validate + persist a manifest into a new run dir
- `core/settings.py`: read/write `~/.config/mmp/settings.toml`
- CLI: `mmp wizard --dump-context [--type ...]`, `mmp wizard --commit <path>`
- SKILL.md: wizard triggers + 3-stage flow + public-publish gate

### Open items after Plan 2

- Remaining 4 providers (xiaohongshu / wechat_image / x_article / substack): Plan 3
- Plugin marketplace prep + CI: Plan 4
```

- [ ] **Step 2: Commit**

```bash
git add docs/HANDOFF.md
git commit -m "docs(handoff): note Plan 2 progress"
```

---

## Task 13: Final Lint + Test Pass

- [ ] **Step 1: Run lint**

Run: `python3 -m ruff check . && python3 -m ruff format --check .`
Expected: 0 issues. Fix anything reported.

- [ ] **Step 2: Run typecheck**

Run: `python3 -m mypy core`
Expected: 0 errors.

- [ ] **Step 3: Run full test**

Run: `make test`
Expected: all green; smoke prints `{"ok": true, ...}`.

- [ ] **Step 4: Manually exercise wizard CLI**

```bash
python3 scripts/mmp.py wizard --dump-context | head -40
```

Expected: JSON output with `providers`, `accounts`, `settings` keys.

- [ ] **Step 5: Commit any cleanup**

```bash
git add -A
git diff --cached --quiet || git commit -m "chore(plan-2): final cleanup"
```

---

## Self-Review Checklist

- [ ] All tasks 1–13 committed
- [ ] `make test` green
- [ ] `mmp wizard --dump-context` returns valid JSON
- [ ] All four prompt fragments are non-empty real prompts (not placeholders)
- [ ] Spec sections covered: §7 (Wizard Flow), §6.4 (Setup wizard)
- [ ] Spec items deferred: §10.1 remaining providers (Plan 3), §9 + §11 (Plan 4)

## Hand-off to Plan 3

Plan 3 will:
- Migrate `xiaohongshu`, `wechat_image`, `x_article`, `substack` providers to the same contract
- Replace `prepare_image_post.py` / `prepare_longform.py` / `execute_image_post.py` with thin deprecation shims
- Extend integration tests
