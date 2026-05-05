# Plan 3 — Remaining 4 Provider Migrations

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `xiaohongshu`, `wechat_image`, `x_article`, `substack` from the legacy `prepare_*`/`execute_*` scripts to the v0.2 `Provider` contract; deprecate old scripts as thin shims; extend integration coverage.

**Architecture:** Each provider becomes a directory under `providers/` with `provider.yaml`, `rules.py`, `provider.py`, `tests/`. Logic from `scripts/prepare_image_post.py`, `scripts/prepare_longform.py`, `scripts/execute_image_post.py`, `scripts/adapt_content.py` is split out per provider. Real-connector status varies: `xiaohongshu` keeps local-draft via `xiaohongshu/scripts/draft.sh`; `wechat_image` keeps browser-flow guide; `x_article`/`substack` remain payload-only (stub `execute`).

**Tech Stack:** Same as Plan 1/2.

**Spec reference:** `docs/superpowers/specs/2026-05-05-multi-media-publisher-redesign-design.md` §10 (Bundled Provider Migration).

**Depends on:** Plan 1 + Plan 2 complete. `Provider`, `ProviderRegistry`, `Manifest`, `CredentialStore`, `Run`, `Wizard` already in place.

---

## File Structure

**Created:**

```
providers/xiaohongshu/__init__.py
providers/xiaohongshu/provider.yaml
providers/xiaohongshu/rules.py
providers/xiaohongshu/provider.py
providers/xiaohongshu/tests/__init__.py
providers/xiaohongshu/tests/test_provider.py

providers/wechat_image/__init__.py
providers/wechat_image/provider.yaml
providers/wechat_image/rules.py
providers/wechat_image/provider.py
providers/wechat_image/tests/__init__.py
providers/wechat_image/tests/test_provider.py
providers/wechat_image/notes.md           # (moved from references/wechat-image-calibration.md)

providers/x_article/__init__.py
providers/x_article/provider.yaml
providers/x_article/rules.py
providers/x_article/provider.py
providers/x_article/tests/__init__.py
providers/x_article/tests/test_provider.py

providers/substack/__init__.py
providers/substack/provider.yaml
providers/substack/rules.py
providers/substack/provider.py
providers/substack/tests/__init__.py
providers/substack/tests/test_provider.py

tests/fixtures/image-post-xhs.yaml
tests/fixtures/image-post-xhs.body.md
tests/fixtures/longform-multi.yaml
tests/integration/test_image_post_e2e.py
tests/integration/test_longform_multi_e2e.py
```

**Modified (deprecation shims):**

```
scripts/prepare_image_post.py             # thin shim → mmp publish
scripts/prepare_longform.py               # thin shim → mmp publish
scripts/execute_image_post.py             # thin shim → mmp publish
scripts/adapt_content.py                  # thin shim → mmp publish
scripts/publish_manifest.py               # thin shim → mmp validate
```

**Modified:**

```
SKILL.md                                  # provider table updated to ✓ for all 5 providers
docs/HANDOFF.md                           # Plan 3 status note
scripts/test_local.py                     # smoke covers all 5 providers in dry-run
references/wechat-image-calibration.md    # moved to providers/wechat_image/notes.md
references/wechat-api-provider.md         # moved to providers/wechat_article/notes.md
```

---

## Task 1: `xiaohongshu` Provider — Scaffold + Rules

**Files:**
- Create: `providers/xiaohongshu/__init__.py`
- Create: `providers/xiaohongshu/provider.yaml`
- Create: `providers/xiaohongshu/rules.py`
- Create: `providers/xiaohongshu/tests/__init__.py`

- [ ] **Step 1: Create scaffold dirs**

```bash
mkdir -p providers/xiaohongshu/tests
touch providers/xiaohongshu/__init__.py providers/xiaohongshu/tests/__init__.py
```

- [ ] **Step 2: Write `provider.yaml`**

```yaml
name: xiaohongshu
display_name: 小红书
media_types:
  - image-post
  - video-post
capabilities:
  draft: true
  publish: false
  schedule: false
required_credentials:
  - key: XHS_COOKIE_PATH
    description: "Path to xiaohongshu cookies file (JSON)"
    secret: false
    setup_hint: "Use the xiaohongshu skill's `xhs-login` flow to capture cookies; default path `~/.config/mmp/cookies/xhs.json`"
entry: provider:XiaohongshuProvider
schema_version: 1
```

- [ ] **Step 3: Write `rules.py`**

```python
"""Platform rules for Xiaohongshu image posts.

Sources (current MCP docs):
- title <= 20 chars
- body (caption) <= 1000 chars
- images 1..9
- tags max 10 (soft warning above)
"""

from __future__ import annotations

from core.rules import PlatformRules

XHS_RULES = PlatformRules(
    title_max=20,
    body_max=1000,
    image_count_min=1,
    image_count_max=9,
    tag_max=10,
)
```

- [ ] **Step 4: Commit**

```bash
git add providers/xiaohongshu/
git commit -m "feat(xiaohongshu): scaffold provider yaml + rules"
```

---

## Task 2: `xiaohongshu` Provider — validate + prepare + execute (local draft)

**Files:**
- Create: `providers/xiaohongshu/provider.py`
- Create: `providers/xiaohongshu/tests/test_provider.py`

- [ ] **Step 1: Write failing test**

`providers/xiaohongshu/tests/test_provider.py`:

```python
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from core.manifest import Manifest, Target
from providers.xiaohongshu.provider import XiaohongshuProvider


@pytest.fixture
def img_manifest(tmp_path):
    img1 = tmp_path / "01.png"
    img2 = tmp_path / "02.png"
    img1.write_bytes(b"png1")
    img2.write_bytes(b"png2")
    return Manifest(
        schema_version="0.2",
        type="image-post",
        title="短标题",
        body="这是一段不超过 1000 字的图文 caption。",
        mode="dry-run",
        targets=[Target(name="xiaohongshu")],
        images=[str(img1), str(img2)],
        tags=["AI", "创业"],
    )


def test_validate_passes(img_manifest):
    p = XiaohongshuProvider()
    res = p.validate(img_manifest, img_manifest.targets[0])
    assert all(v.severity.value != "error" for v in res.violations)


def test_validate_title_too_long(img_manifest):
    img_manifest.title = "这个标题肯定超过了二十个字符的小红书限制确实如此非常长"
    p = XiaohongshuProvider()
    res = p.validate(img_manifest, img_manifest.targets[0])
    assert any(v.code == "TITLE_TOO_LONG" for v in res.violations)


def test_validate_no_images(img_manifest):
    img_manifest.images = []
    p = XiaohongshuProvider()
    res = p.validate(img_manifest, img_manifest.targets[0])
    assert any(v.code == "IMAGE_COUNT_BELOW_MIN" for v in res.violations)


def test_prepare_writes_payload(img_manifest, tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    p = XiaohongshuProvider()
    out = p.prepare(img_manifest, img_manifest.targets[0], run_dir)
    assert out.payload_path.exists()
    payload = json.loads(out.payload_path.read_text())
    assert payload["title"] == "短标题"
    assert len(payload["images"]) == 2
    assert payload["tags"] == ["AI", "创业"]


def test_execute_dry_run(img_manifest, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "xiaohongshu").mkdir(parents=True)
    p = XiaohongshuProvider()
    p.prepare(img_manifest, img_manifest.targets[0], run_dir)
    res = p.execute(run_dir, img_manifest.targets[0], mode="dry-run", credentials={})
    assert res.status == "ok"
    assert res.mode_actual == "dry-run"


def test_execute_draft_invokes_local_script(img_manifest, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "xiaohongshu").mkdir(parents=True)
    p = XiaohongshuProvider()
    p.prepare(img_manifest, img_manifest.targets[0], run_dir)

    with patch(
        "providers.xiaohongshu.provider._invoke_local_draft",
        return_value={"draft_id": "xhs_local_abc"},
    ) as mock:
        res = p.execute(
            run_dir,
            img_manifest.targets[0],
            mode="draft",
            credentials={"XHS_COOKIE_PATH": "/tmp/x"},
        )
    mock.assert_called_once()
    assert res.status == "ok"
    assert res.mode_actual == "draft-local"
    assert res.external_id == "xhs_local_abc"


def test_execute_publish_refused(img_manifest, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "xiaohongshu").mkdir(parents=True)
    p = XiaohongshuProvider()
    p.prepare(img_manifest, img_manifest.targets[0], run_dir)
    with pytest.raises(NotImplementedError, match="publish"):
        p.execute(
            run_dir,
            img_manifest.targets[0],
            mode="publish",
            credentials={"XHS_COOKIE_PATH": "x"},
        )
```

- [ ] **Step 2: Run test (should fail)**

Run: `pytest providers/xiaohongshu/tests/test_provider.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `provider.py`**

```python
"""Xiaohongshu provider — local draft via the xiaohongshu skill's draft.sh.

This v0.2 provider only knows the `draft-local` path (creates a local draft
file, no platform upload). Platform draft and publish are deferred.
"""

from __future__ import annotations

import json
import shutil
import subprocess
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
from providers.xiaohongshu.rules import XHS_RULES


def _invoke_local_draft(payload_path: Path, cookie_path: str) -> dict[str, Any]:
    """Call the xiaohongshu skill's draft.sh. Returns parsed JSON output."""
    candidates = [
        Path.home() / ".openclaw" / "skills" / "xiaohongshu" / "scripts" / "draft.sh",
        Path.home() / ".config" / "mmp" / "skills" / "xiaohongshu" / "scripts" / "draft.sh",
    ]
    script = next((c for c in candidates if c.exists()), None)
    if script is None:
        raise FileNotFoundError(
            "xiaohongshu draft.sh not found in expected locations: "
            + ", ".join(str(c) for c in candidates)
        )
    result = subprocess.run(
        [str(script), "--payload", str(payload_path), "--cookie", cookie_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"draft.sh failed: {result.stderr}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"draft_id": f"xhs_local_{abs(hash(result.stdout)) % 10**9}"}


class XiaohongshuProvider(Provider):
    name = "xiaohongshu"
    display_name = "小红书"
    media_types = ["image-post", "video-post"]
    capabilities = {"draft": True, "publish": False, "schedule": False}
    required_credentials = [
        CredentialSpec(
            key="XHS_COOKIE_PATH",
            description="Path to xiaohongshu cookies file",
            secret=False,
            setup_hint="Use xhs-login from the xiaohongshu skill",
        )
    ]
    platform_rules = XHS_RULES

    def validate(self, manifest: Any, target: Any) -> ValidationResult:
        return ValidationResult(violations=self.platform_rules.lint(manifest, self.name))

    def prepare(self, manifest: Any, target: Any, run_dir: Path) -> PreparedPayload:
        pack_dir = run_dir / "packs" / self.name
        pack_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "title": manifest.title,
            "caption": manifest.body,
            "images": list(manifest.images or []),
            "tags": list(manifest.tags or []),
            "cta": manifest.cta,
            "mode": target.mode,
            "options": dict(target.options or {}),
        }
        payload_path = pack_dir / "payload.json"
        payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        (pack_dir / "content.md").write_text(manifest.body or "", encoding="utf-8")
        return PreparedPayload(pack_dir=pack_dir, payload_path=payload_path)

    def execute(
        self,
        run_dir: Path,
        target: Any,
        mode: str,
        credentials: dict[str, str],
    ) -> ExecutionResult:
        if mode == "publish":
            raise NotImplementedError(
                "xiaohongshu publish path not enabled in v0.2; use mode=draft"
            )
        if mode == "dry-run":
            return ExecutionResult(status="ok", mode_actual="dry-run", external_id=None)

        cookie_path = credentials.get("XHS_COOKIE_PATH")
        if not cookie_path:
            raise ProviderExecutionError(
                target=self.name,
                step="auth",
                upstream=ValueError("missing XHS_COOKIE_PATH"),
                retryable=False,
            )

        payload_path = run_dir / "packs" / self.name / "payload.json"
        try:
            out = _invoke_local_draft(payload_path, cookie_path)
        except Exception as exc:
            raise ProviderExecutionError(
                target=self.name, step="local_draft", upstream=exc, retryable=True
            ) from exc

        return ExecutionResult(
            status="ok",
            mode_actual="draft-local",
            external_id=out.get("draft_id"),
            extras={"draft_path": out.get("draft_path")},
        )

    def health_check(self, credentials: dict[str, str]) -> HealthStatus:
        cookie_path = credentials.get("XHS_COOKIE_PATH")
        if cookie_path and Path(cookie_path).exists():
            return HealthStatus.ok
        return HealthStatus.failed
```

- [ ] **Step 4: Run test (should pass)**

Run: `pytest providers/xiaohongshu/tests/test_provider.py -v`
Expected: PASS — 7 passed.

- [ ] **Step 5: Commit**

```bash
git add providers/xiaohongshu/provider.py providers/xiaohongshu/tests/test_provider.py
git commit -m "feat(xiaohongshu): implement provider with local draft via draft.sh"
```

---

## Task 3: `wechat_image` Provider — Scaffold + Rules

**Files:**
- Create: `providers/wechat_image/__init__.py`
- Create: `providers/wechat_image/provider.yaml`
- Create: `providers/wechat_image/rules.py`
- Create: `providers/wechat_image/tests/__init__.py`
- Move: `references/wechat-image-calibration.md` → `providers/wechat_image/notes.md`

- [ ] **Step 1: Create scaffold + move notes**

```bash
mkdir -p providers/wechat_image/tests
touch providers/wechat_image/__init__.py providers/wechat_image/tests/__init__.py
git mv references/wechat-image-calibration.md providers/wechat_image/notes.md
```

- [ ] **Step 2: Write `provider.yaml`**

```yaml
name: wechat-image
display_name: 微信图文内容
media_types:
  - image-post
capabilities:
  draft: true
  publish: false
  schedule: false
required_credentials: []
entry: provider:WeChatImageProvider
schema_version: 1
```

- [ ] **Step 3: Write `rules.py`**

```python
"""Platform rules for WeChat image posts (图文内容, not OA articles).

Approximate limits (refine when browser flow lands):
- title up to ~64 chars
- caption up to ~600 chars
- images 1..9
"""

from __future__ import annotations

from core.rules import PlatformRules

WECHAT_IMAGE_RULES = PlatformRules(
    title_max=64,
    body_max=600,
    image_count_min=1,
    image_count_max=9,
)
```

- [ ] **Step 4: Commit**

```bash
git add providers/wechat_image/
git commit -m "feat(wechat_image): scaffold provider yaml + rules; move calibration notes"
```

---

## Task 4: `wechat_image` Provider — validate + prepare + execute (browser-flow guide)

**Files:**
- Create: `providers/wechat_image/provider.py`
- Create: `providers/wechat_image/tests/test_provider.py`

- [ ] **Step 1: Write failing test**

`providers/wechat_image/tests/test_provider.py`:

```python
import json
from pathlib import Path

import pytest

from core.manifest import Manifest, Target
from providers.wechat_image.provider import WeChatImageProvider


@pytest.fixture
def img_manifest(tmp_path):
    img = tmp_path / "01.png"
    img.write_bytes(b"png")
    return Manifest(
        schema_version="0.2",
        type="image-post",
        title="短",
        body="caption text",
        mode="dry-run",
        targets=[Target(name="wechat-image")],
        images=[str(img)],
    )


def test_validate(img_manifest):
    p = WeChatImageProvider()
    res = p.validate(img_manifest, img_manifest.targets[0])
    assert all(v.severity.value != "error" for v in res.violations)


def test_prepare_writes_payload(img_manifest, tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    p = WeChatImageProvider()
    out = p.prepare(img_manifest, img_manifest.targets[0], run_dir)
    assert out.payload_path.exists()
    payload = json.loads(out.payload_path.read_text())
    assert payload["title"] == "短"
    assert payload["caption"] == "caption text"


def test_execute_draft_writes_browser_flow_guide(img_manifest, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "wechat-image").mkdir(parents=True)
    p = WeChatImageProvider()
    p.prepare(img_manifest, img_manifest.targets[0], run_dir)
    res = p.execute(run_dir, img_manifest.targets[0], mode="draft", credentials={})
    guide = run_dir / "packs" / "wechat-image" / "browser-flow.md"
    assert guide.exists()
    assert "mp.weixin.qq.com" in guide.read_text()
    assert res.status == "ok"
    assert res.mode_actual == "draft-local"


def test_execute_dry_run_skips_guide(img_manifest, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "wechat-image").mkdir(parents=True)
    p = WeChatImageProvider()
    p.prepare(img_manifest, img_manifest.targets[0], run_dir)
    res = p.execute(run_dir, img_manifest.targets[0], mode="dry-run", credentials={})
    assert res.mode_actual == "dry-run"


def test_execute_publish_refused(img_manifest, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "wechat-image").mkdir(parents=True)
    p = WeChatImageProvider()
    p.prepare(img_manifest, img_manifest.targets[0], run_dir)
    with pytest.raises(NotImplementedError, match="publish"):
        p.execute(run_dir, img_manifest.targets[0], mode="publish", credentials={})
```

- [ ] **Step 2: Run test (should fail)**

Run: `pytest providers/wechat_image/tests/test_provider.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `provider.py`**

```python
"""WeChat 图文内容 provider — emits a browser-flow guide for the user.

The browser path to mp.weixin.qq.com is currently blocked under OpenClaw policy,
so this provider does NOT automate the upload. Instead, it produces a
step-by-step Markdown guide the user follows in their own browser.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.provider import (
    ExecutionResult,
    HealthStatus,
    PreparedPayload,
    Provider,
    ValidationResult,
)
from providers.wechat_image.rules import WECHAT_IMAGE_RULES


_GUIDE_TEMPLATE = """\
# WeChat 图文内容 — 手动执行指南

> 自动化未启用：浏览器对 mp.weixin.qq.com 的访问被策略阻止。请按下面的步骤手动完成。

## Payload

文件：`{payload_path}`

字段：

- **标题**：`{title}`
- **正文**：见 `content.md`
- **图片**（{n_images} 张）：
{image_list}
- **CTA**：{cta}

## 操作步骤

1. 打开 https://mp.weixin.qq.com/ 并登录目标公众号。
2. 顶部菜单选择 **图文素材** → **新建图文素材**（图文内容）。
3. 填入标题、摘要（如有）。
4. 把上面列出的每张图片按顺序上传。
5. 把 `content.md` 内容粘贴到正文。
6. 点击 **保存草稿**。**不要点发布**。
7. 回到这里继续后续动作或确认草稿状态。

## 安全提示

- 不要绕过登录或验证码。
- 不要导出 cookie 文件到任何外部位置。
- 草稿确认后，如需公开发布，使用公众号原生的"群发"功能。
"""


class WeChatImageProvider(Provider):
    name = "wechat-image"
    display_name = "微信图文内容"
    media_types = ["image-post"]
    capabilities = {"draft": True, "publish": False, "schedule": False}
    required_credentials = []
    platform_rules = WECHAT_IMAGE_RULES

    def validate(self, manifest: Any, target: Any) -> ValidationResult:
        return ValidationResult(violations=self.platform_rules.lint(manifest, self.name))

    def prepare(self, manifest: Any, target: Any, run_dir: Path) -> PreparedPayload:
        pack_dir = run_dir / "packs" / self.name
        pack_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "title": manifest.title,
            "caption": manifest.body,
            "images": list(manifest.images or []),
            "cta": manifest.cta,
            "mode": target.mode,
            "options": dict(target.options or {}),
        }
        payload_path = pack_dir / "payload.json"
        payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        (pack_dir / "content.md").write_text(manifest.body or "", encoding="utf-8")
        return PreparedPayload(pack_dir=pack_dir, payload_path=payload_path)

    def execute(
        self,
        run_dir: Path,
        target: Any,
        mode: str,
        credentials: dict[str, str],
    ) -> ExecutionResult:
        if mode == "publish":
            raise NotImplementedError("wechat-image publish path not supported in v0.2")
        if mode == "dry-run":
            return ExecutionResult(status="ok", mode_actual="dry-run", external_id=None)

        # mode == draft → write a browser-flow guide
        pack_dir = run_dir / "packs" / self.name
        payload_path = pack_dir / "payload.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        image_list = "\n".join(f"   - `{img}`" for img in payload["images"]) or "   - (none)"
        guide = _GUIDE_TEMPLATE.format(
            payload_path=str(payload_path),
            title=payload["title"],
            n_images=len(payload["images"]),
            image_list=image_list,
            cta=payload.get("cta") or "(none)",
        )
        guide_path = pack_dir / "browser-flow.md"
        guide_path.write_text(guide, encoding="utf-8")
        return ExecutionResult(
            status="ok",
            mode_actual="draft-local",
            external_id=None,
            extras={"guide_path": str(guide_path)},
        )

    def health_check(self, credentials: dict[str, str]) -> HealthStatus:
        return HealthStatus.unknown
```

- [ ] **Step 4: Run test (should pass)**

Run: `pytest providers/wechat_image/tests/test_provider.py -v`
Expected: PASS — 5 passed.

- [ ] **Step 5: Commit**

```bash
git add providers/wechat_image/provider.py providers/wechat_image/tests/test_provider.py
git commit -m "feat(wechat_image): implement provider with browser-flow guide draft"
```

---

## Task 5: `x_article` Provider — Scaffold + Rules + Provider

**Files:**
- Create: `providers/x_article/__init__.py`
- Create: `providers/x_article/provider.yaml`
- Create: `providers/x_article/rules.py`
- Create: `providers/x_article/provider.py`
- Create: `providers/x_article/tests/__init__.py`
- Create: `providers/x_article/tests/test_provider.py`

- [ ] **Step 1: Create scaffold**

```bash
mkdir -p providers/x_article/tests
touch providers/x_article/__init__.py providers/x_article/tests/__init__.py
```

- [ ] **Step 2: Write `provider.yaml`**

```yaml
name: x-article
display_name: X Articles
media_types:
  - longform
capabilities:
  draft: true
  publish: false
  schedule: false
required_credentials:
  - key: X_AUTH_TOKEN
    description: "X (Twitter) auth token cookie value"
    secret: true
    setup_hint: "Capture from a logged-in browser session; rotate after testing"
entry: provider:XArticleProvider
schema_version: 1
```

- [ ] **Step 3: Write `rules.py`**

```python
"""Platform rules for X Articles.

Approximate (X Articles are evolving):
- title <=70 chars practical
- body <=25000 chars
- cover optional
"""

from __future__ import annotations

from core.rules import PlatformRules

X_ARTICLE_RULES = PlatformRules(
    title_max=70,
    body_max=25000,
)
```

- [ ] **Step 4: Write failing test**

`providers/x_article/tests/test_provider.py`:

```python
import json
from pathlib import Path

import pytest

from core.manifest import Manifest, Target
from providers.x_article.provider import XArticleProvider


@pytest.fixture
def article(tmp_path):
    return Manifest(
        schema_version="0.2",
        type="longform",
        title="An X Article",
        body="# Heading\n\nBody.",
        mode="dry-run",
        targets=[Target(name="x-article")],
        summary="A summary",
        tags=["tech"],
    )


def test_validate(article):
    p = XArticleProvider()
    res = p.validate(article, article.targets[0])
    assert all(v.severity.value != "error" for v in res.violations)


def test_validate_title_too_long(article):
    article.title = "x" * 200
    p = XArticleProvider()
    res = p.validate(article, article.targets[0])
    assert any(v.code == "TITLE_TOO_LONG" for v in res.violations)


def test_prepare_writes_payload(article, tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    p = XArticleProvider()
    out = p.prepare(article, article.targets[0], run_dir)
    payload = json.loads(out.payload_path.read_text())
    assert payload["title"] == "An X Article"
    assert payload["body"].startswith("# Heading")


def test_execute_dry_run(article, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "x-article").mkdir(parents=True)
    p = XArticleProvider()
    p.prepare(article, article.targets[0], run_dir)
    res = p.execute(run_dir, article.targets[0], mode="dry-run", credentials={})
    assert res.mode_actual == "dry-run"


def test_execute_draft_returns_stub(article, tmp_path):
    """v0.2: no real X connector. Draft falls back to dry-run-like result with TODO note."""
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "x-article").mkdir(parents=True)
    p = XArticleProvider()
    p.prepare(article, article.targets[0], run_dir)
    res = p.execute(
        run_dir,
        article.targets[0],
        mode="draft",
        credentials={"X_AUTH_TOKEN": "stub"},
    )
    assert res.mode_actual == "dry-run"
    assert res.extras.get("connector_status") == "not-implemented"


def test_execute_publish_refused(article, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "x-article").mkdir(parents=True)
    p = XArticleProvider()
    p.prepare(article, article.targets[0], run_dir)
    with pytest.raises(NotImplementedError, match="publish"):
        p.execute(run_dir, article.targets[0], mode="publish", credentials={})
```

- [ ] **Step 5: Run test (should fail)**

Run: `pytest providers/x_article/tests/test_provider.py -v`
Expected: FAIL — module not found.

- [ ] **Step 6: Implement `provider.py`**

```python
"""X Articles provider — payload-only stub.

A real connector (likely the `x-articles` skill or browser automation) is not
shipped in v0.2. `execute` writes a TODO marker into the run dir and returns
mode_actual=dry-run, so multi-target manifests can still progress past this
target without failing the run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.provider import (
    CredentialSpec,
    ExecutionResult,
    HealthStatus,
    PreparedPayload,
    Provider,
    ValidationResult,
)
from providers.x_article.rules import X_ARTICLE_RULES


class XArticleProvider(Provider):
    name = "x-article"
    display_name = "X Articles"
    media_types = ["longform"]
    capabilities = {"draft": True, "publish": False, "schedule": False}
    required_credentials = [
        CredentialSpec(
            key="X_AUTH_TOKEN",
            description="X (Twitter) auth token",
            secret=True,
        )
    ]
    platform_rules = X_ARTICLE_RULES

    def validate(self, manifest: Any, target: Any) -> ValidationResult:
        return ValidationResult(violations=self.platform_rules.lint(manifest, self.name))

    def prepare(self, manifest: Any, target: Any, run_dir: Path) -> PreparedPayload:
        pack_dir = run_dir / "packs" / self.name
        pack_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "title": manifest.title,
            "body": manifest.body,
            "summary": manifest.summary,
            "cover": manifest.cover,
            "tags": list(manifest.tags or []),
            "mode": target.mode,
            "options": dict(target.options or {}),
        }
        payload_path = pack_dir / "payload.json"
        payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        (pack_dir / "content.md").write_text(manifest.body or "", encoding="utf-8")
        return PreparedPayload(pack_dir=pack_dir, payload_path=payload_path)

    def execute(
        self,
        run_dir: Path,
        target: Any,
        mode: str,
        credentials: dict[str, str],
    ) -> ExecutionResult:
        if mode == "publish":
            raise NotImplementedError("x-article publish path not enabled in v0.2")
        if mode == "dry-run":
            return ExecutionResult(status="ok", mode_actual="dry-run", external_id=None)

        # mode == draft, no real connector yet
        pack_dir = run_dir / "packs" / self.name
        (pack_dir / "TODO-connector.md").write_text(
            "# x-article connector not implemented in v0.2\n\n"
            "Payload is ready at `payload.json`. To complete the draft:\n"
            "1. Open https://x.com/i/articles/compose in a logged-in browser\n"
            "2. Paste title from payload.title\n"
            "3. Paste body from content.md\n"
            "4. Set cover from payload.cover (if present)\n"
            "5. Save Draft\n",
            encoding="utf-8",
        )
        return ExecutionResult(
            status="ok",
            mode_actual="dry-run",
            external_id=None,
            extras={"connector_status": "not-implemented"},
        )

    def health_check(self, credentials: dict[str, str]) -> HealthStatus:
        return HealthStatus.unknown
```

- [ ] **Step 7: Run test (should pass)**

Run: `pytest providers/x_article/tests/test_provider.py -v`
Expected: PASS — 6 passed.

- [ ] **Step 8: Commit**

```bash
git add providers/x_article/
git commit -m "feat(x_article): implement provider as payload-only stub"
```

---

## Task 6: `substack` Provider — Scaffold + Rules + Provider

**Files:**
- Create: `providers/substack/*` (mirroring x_article structure)

- [ ] **Step 1: Create scaffold**

```bash
mkdir -p providers/substack/tests
touch providers/substack/__init__.py providers/substack/tests/__init__.py
```

- [ ] **Step 2: Write `provider.yaml`**

```yaml
name: substack
display_name: Substack
media_types:
  - longform
capabilities:
  draft: true
  publish: false
  schedule: false
required_credentials:
  - key: SUBSTACK_SESSION_COOKIE
    description: "Substack session cookie value"
    secret: true
    setup_hint: "Capture `substack.sid` from a logged-in browser session"
entry: provider:SubstackProvider
schema_version: 1
```

- [ ] **Step 3: Write `rules.py`**

```python
"""Platform rules for Substack posts.

- title <=100 chars practical
- subtitle <=200 chars
- body <=50000 chars
- cover optional
"""

from __future__ import annotations

from core.rules import PlatformRules, Severity, Violation


def _subtitle_lint(manifest, target_name: str) -> list[Violation]:
    subtitle = (manifest.metadata or {}).get("subtitle") or ""
    if subtitle and len(subtitle) > 200:
        return [
            Violation(
                code="SUBSTACK_SUBTITLE_TOO_LONG",
                message=f"subtitle length {len(subtitle)} exceeds 200",
                target=target_name,
                field_path="metadata.subtitle",
                severity=Severity.warning,
            )
        ]
    return []


SUBSTACK_RULES = PlatformRules(
    title_max=100,
    body_max=50000,
    extra_lints=[_subtitle_lint],
)
```

- [ ] **Step 4: Write failing test**

`providers/substack/tests/test_provider.py`:

```python
import json
from pathlib import Path

import pytest

from core.manifest import Manifest, Target
from providers.substack.provider import SubstackProvider


@pytest.fixture
def article():
    return Manifest(
        schema_version="0.2",
        type="longform",
        title="A Substack Post",
        body="Body text here.",
        mode="dry-run",
        targets=[Target(name="substack")],
        metadata={"subtitle": "An optional subtitle"},
    )


def test_validate_passes(article):
    p = SubstackProvider()
    res = p.validate(article, article.targets[0])
    assert all(v.severity.value != "error" for v in res.violations)


def test_validate_subtitle_too_long(article):
    article.metadata["subtitle"] = "x" * 250
    p = SubstackProvider()
    res = p.validate(article, article.targets[0])
    codes = [v.code for v in res.violations]
    assert "SUBSTACK_SUBTITLE_TOO_LONG" in codes


def test_prepare_writes_payload(article, tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    p = SubstackProvider()
    out = p.prepare(article, article.targets[0], run_dir)
    payload = json.loads(out.payload_path.read_text())
    assert payload["title"] == "A Substack Post"
    assert payload["subtitle"] == "An optional subtitle"


def test_execute_draft_returns_stub(article, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "substack").mkdir(parents=True)
    p = SubstackProvider()
    p.prepare(article, article.targets[0], run_dir)
    res = p.execute(
        run_dir,
        article.targets[0],
        mode="draft",
        credentials={"SUBSTACK_SESSION_COOKIE": "stub"},
    )
    assert res.mode_actual == "dry-run"
    assert res.extras.get("connector_status") == "not-implemented"


def test_execute_publish_refused(article, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "packs" / "substack").mkdir(parents=True)
    p = SubstackProvider()
    p.prepare(article, article.targets[0], run_dir)
    with pytest.raises(NotImplementedError, match="publish"):
        p.execute(run_dir, article.targets[0], mode="publish", credentials={})
```

- [ ] **Step 5: Implement `provider.py`**

```python
"""Substack provider — payload-only stub.

A real connector (substack-autopilot or generic browser) is not shipped in
v0.2. Behavior parallels x_article: payload + TODO marker + dry-run-like
result.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.provider import (
    CredentialSpec,
    ExecutionResult,
    HealthStatus,
    PreparedPayload,
    Provider,
    ValidationResult,
)
from providers.substack.rules import SUBSTACK_RULES


class SubstackProvider(Provider):
    name = "substack"
    display_name = "Substack"
    media_types = ["longform"]
    capabilities = {"draft": True, "publish": False, "schedule": False}
    required_credentials = [
        CredentialSpec(
            key="SUBSTACK_SESSION_COOKIE",
            description="Substack session cookie",
            secret=True,
        )
    ]
    platform_rules = SUBSTACK_RULES

    def validate(self, manifest: Any, target: Any) -> ValidationResult:
        return ValidationResult(violations=self.platform_rules.lint(manifest, self.name))

    def prepare(self, manifest: Any, target: Any, run_dir: Path) -> PreparedPayload:
        pack_dir = run_dir / "packs" / self.name
        pack_dir.mkdir(parents=True, exist_ok=True)
        meta = manifest.metadata or {}
        payload = {
            "title": manifest.title,
            "subtitle": meta.get("subtitle"),
            "body": manifest.body,
            "cover": manifest.cover,
            "tags": list(manifest.tags or []),
            "mode": target.mode,
            "options": dict(target.options or {}),
        }
        payload_path = pack_dir / "payload.json"
        payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        (pack_dir / "content.md").write_text(manifest.body or "", encoding="utf-8")
        return PreparedPayload(pack_dir=pack_dir, payload_path=payload_path)

    def execute(
        self,
        run_dir: Path,
        target: Any,
        mode: str,
        credentials: dict[str, str],
    ) -> ExecutionResult:
        if mode == "publish":
            raise NotImplementedError("substack publish path not enabled in v0.2")
        if mode == "dry-run":
            return ExecutionResult(status="ok", mode_actual="dry-run", external_id=None)

        pack_dir = run_dir / "packs" / self.name
        (pack_dir / "TODO-connector.md").write_text(
            "# substack connector not implemented in v0.2\n\n"
            "Payload is ready at `payload.json`. To complete:\n"
            "1. Open https://substack.com/dashboard in a logged-in browser\n"
            "2. Click 'New post'\n"
            "3. Paste title and subtitle from payload\n"
            "4. Paste body from content.md\n"
            "5. Set cover from payload.cover (if present)\n"
            "6. Save Draft\n",
            encoding="utf-8",
        )
        return ExecutionResult(
            status="ok",
            mode_actual="dry-run",
            external_id=None,
            extras={"connector_status": "not-implemented"},
        )

    def health_check(self, credentials: dict[str, str]) -> HealthStatus:
        return HealthStatus.unknown
```

- [ ] **Step 6: Run tests (should pass)**

Run: `pytest providers/substack/tests/test_provider.py -v`
Expected: PASS — 5 passed.

- [ ] **Step 7: Commit**

```bash
git add providers/substack/
git commit -m "feat(substack): implement provider as payload-only stub"
```

---

## Task 7: Integration Test — image-post (xhs + wechat-image)

**Files:**
- Create: `tests/fixtures/image-post-multi.body.md`
- Create: `tests/fixtures/image-post-multi.yaml`
- Create: `tests/fixtures/img-01.png`, `img-02.png`
- Create: `tests/integration/test_image_post_e2e.py`

- [ ] **Step 1: Create fixtures**

```bash
python3 -c "import struct; \
open('tests/fixtures/img-01.png','wb').write(bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108020000009077533de0000000016352474200aece1ce90000000c4944415478da6300010000050001a5f645400000000049454e44ae426082')); \
open('tests/fixtures/img-02.png','wb').write(bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108020000009077533de0000000016352474200aece1ce90000000c4944415478da6300010000050001a5f645400000000049454e44ae426082'))"
```

`tests/fixtures/image-post-multi.body.md`:

```markdown
这是一组图文 caption。
不超过 1000 字。
```

`tests/fixtures/image-post-multi.yaml`:

```yaml
schema_version: "0.2"
type: image-post
title: "AI 创业的三个误区"
body: ./image-post-multi.body.md
mode: dry-run
language: zh-CN
targets:
  - xiaohongshu
  - wechat-image
assets:
  images:
    - ./img-01.png
    - ./img-02.png
tags:
  - AI
  - 创业
```

- [ ] **Step 2: Write integration test**

`tests/integration/test_image_post_e2e.py`:

```python
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "image-post-multi.yaml"


def test_image_post_dry_run_both_targets(tmp_path):
    p = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mmp.py"), "publish", str(FIXTURE)],
        capture_output=True,
        text=True,
        env={**os.environ, "MMP_RUNS_DIR": str(tmp_path / "runs")},
    )
    assert p.returncode == 0, p.stderr

    runs = list((tmp_path / "runs").iterdir())
    rd = runs[0]
    result = json.loads((rd / "result.json").read_text())
    names = [t["name"] for t in result["targets"]]
    assert "xiaohongshu" in names
    assert "wechat-image" in names
    for t in result["targets"]:
        assert t["status"] == "ok"
        assert t["mode_actual"] == "dry-run"

    assert (rd / "packs" / "xiaohongshu" / "payload.json").exists()
    assert (rd / "packs" / "wechat-image" / "payload.json").exists()
```

- [ ] **Step 3: Run test (should pass)**

Run: `pytest tests/integration/test_image_post_e2e.py -v`
Expected: PASS — 1 passed.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_image_post_e2e.py tests/fixtures/image-post-multi*  tests/fixtures/img-*.png
git commit -m "test(integration): image-post dry-run covers xhs + wechat-image"
```

---

## Task 8: Integration Test — longform-multi (wechat-article + x-article + substack)

**Files:**
- Create: `tests/fixtures/longform-multi.yaml`
- Create: `tests/fixtures/longform-multi.body.md`
- Create: `tests/fixtures/longform-cover.png`
- Create: `tests/integration/test_longform_multi_e2e.py`

- [ ] **Step 1: Create fixtures**

```bash
python3 -c "open('tests/fixtures/longform-cover.png','wb').write(bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108020000009077533de0000000016352474200aece1ce90000000c4944415478da6300010000050001a5f645400000000049454e44ae426082'))"
```

`tests/fixtures/longform-multi.body.md`:

```markdown
# 一篇示例长文

正文段落。
```

`tests/fixtures/longform-multi.yaml`:

```yaml
schema_version: "0.2"
type: longform
title: "Example Longform"
body: ./longform-multi.body.md
mode: dry-run
language: zh-CN
targets:
  - wechat-article
  - x-article
  - substack
assets:
  cover: ./longform-cover.png
summary: "A quick summary."
metadata:
  digest: "公众号摘要"
  subtitle: "Substack subtitle"
tags:
  - test
```

- [ ] **Step 2: Write integration test**

`tests/integration/test_longform_multi_e2e.py`:

```python
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "longform-multi.yaml"


def test_longform_multi_dry_run(tmp_path):
    p = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mmp.py"), "publish", str(FIXTURE)],
        capture_output=True,
        text=True,
        env={**os.environ, "MMP_RUNS_DIR": str(tmp_path / "runs")},
    )
    assert p.returncode == 0, p.stderr

    rd = next((tmp_path / "runs").iterdir())
    result = json.loads((rd / "result.json").read_text())
    names = sorted(t["name"] for t in result["targets"])
    assert names == ["substack", "wechat-article", "x-article"]
    for t in result["targets"]:
        assert t["status"] == "ok"
    for sub in ["wechat-article", "x-article", "substack"]:
        assert (rd / "packs" / sub / "payload.json").exists()
```

- [ ] **Step 3: Run test (should pass)**

Run: `pytest tests/integration/test_longform_multi_e2e.py -v`
Expected: PASS — 1 passed.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_longform_multi_e2e.py tests/fixtures/longform-multi* tests/fixtures/longform-cover.png
git commit -m "test(integration): longform multi-target dry-run e2e"
```

---

## Task 9: Deprecate Old Scripts as Thin Shims

**Files:**
- Modify: `scripts/prepare_image_post.py`
- Modify: `scripts/prepare_longform.py`
- Modify: `scripts/execute_image_post.py`
- Modify: `scripts/adapt_content.py`
- Modify: `scripts/publish_manifest.py`
- Move: `references/wechat-api-provider.md` → `providers/wechat_article/notes.md`

- [ ] **Step 1: Move the wechat-api-provider notes**

```bash
git mv references/wechat-api-provider.md providers/wechat_article/notes.md
```

- [ ] **Step 2: Replace each script with a deprecation shim**

`scripts/prepare_image_post.py`:

```python
"""DEPRECATED in v0.2. Use `mmp publish <manifest>`.

Logic moved to providers/xiaohongshu/ and providers/wechat_image/.
This shim will be removed in v0.3.
"""

from __future__ import annotations

import sys
import warnings


def main() -> int:
    warnings.warn(
        "prepare_image_post.py is deprecated; use `python3 scripts/mmp.py publish <manifest>`",
        DeprecationWarning,
        stacklevel=2,
    )
    print(
        "DEPRECATED. Run `python3 scripts/mmp.py publish <manifest>` instead.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

`scripts/prepare_longform.py`:

```python
"""DEPRECATED in v0.2. Use `mmp publish <manifest>`.

Logic moved to providers/wechat_article/, providers/x_article/, providers/substack/.
This shim will be removed in v0.3.
"""

from __future__ import annotations

import sys
import warnings


def main() -> int:
    warnings.warn(
        "prepare_longform.py is deprecated; use `python3 scripts/mmp.py publish <manifest>`",
        DeprecationWarning,
        stacklevel=2,
    )
    print(
        "DEPRECATED. Run `python3 scripts/mmp.py publish <manifest>` instead.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

`scripts/execute_image_post.py`:

```python
"""DEPRECATED in v0.2. Use `mmp publish <manifest> [--mode-override draft]`.

Logic moved to providers/xiaohongshu/ and providers/wechat_image/.
This shim will be removed in v0.3.
"""

from __future__ import annotations

import sys
import warnings


def main() -> int:
    warnings.warn(
        "execute_image_post.py is deprecated; use "
        "`python3 scripts/mmp.py publish <manifest> --mode-override draft`",
        DeprecationWarning,
        stacklevel=2,
    )
    print(
        "DEPRECATED. Run `python3 scripts/mmp.py publish <manifest> --mode-override draft` instead.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

`scripts/adapt_content.py`:

```python
"""DEPRECATED in v0.2. Use `mmp publish <manifest>`.

Per-target pack scaffolding is now done by each provider's prepare() method.
This shim will be removed in v0.3.
"""

from __future__ import annotations

import sys
import warnings


def main() -> int:
    warnings.warn(
        "adapt_content.py is deprecated; use `python3 scripts/mmp.py publish <manifest>`",
        DeprecationWarning,
        stacklevel=2,
    )
    print(
        "DEPRECATED. Run `python3 scripts/mmp.py publish <manifest>` instead.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

`scripts/publish_manifest.py`:

```python
"""DEPRECATED in v0.2. Use `mmp validate <manifest>` or `mmp publish <manifest>`.

Manifest skeleton creation is now part of `mmp publish`.
This shim will be removed in v0.3.
"""

from __future__ import annotations

import sys
import warnings


def main() -> int:
    warnings.warn(
        "publish_manifest.py is deprecated; use `python3 scripts/mmp.py validate <manifest>` "
        "or `python3 scripts/mmp.py publish <manifest>`",
        DeprecationWarning,
        stacklevel=2,
    )
    print(
        "DEPRECATED. Run `python3 scripts/mmp.py validate <manifest>` instead.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Verify imports succeed**

```bash
for s in prepare_image_post prepare_longform execute_image_post adapt_content publish_manifest; do
  python3 -c "import importlib.util; spec=importlib.util.spec_from_file_location('s','scripts/${s}.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)"
done
```

Expected: all return exit 0 with no error.

- [ ] **Step 4: Commit**

```bash
git add scripts/prepare_image_post.py scripts/prepare_longform.py \
        scripts/execute_image_post.py scripts/adapt_content.py \
        scripts/publish_manifest.py providers/wechat_article/notes.md
git commit -m "refactor: deprecate v0.1 scripts as thin shims; move wechat notes"
```

---

## Task 10: Update SKILL.md Provider Table + smoke test

**Files:**
- Modify: `SKILL.md`
- Modify: `scripts/test_local.py`

- [ ] **Step 1: Replace the v0.2 supported providers table in `SKILL.md`**

Replace the table with:

```markdown
| Provider | Media | Mode support |
|---|---|---|
| `wechat-article` | longform | dry-run, draft (real WeChat API; needs AppID/AppSecret) |
| `xiaohongshu` | image-post (video planned) | dry-run, draft (local draft via xiaohongshu skill) |
| `wechat-image` | image-post | dry-run, draft (browser-flow guide) |
| `x-article` | longform | dry-run, draft (payload + TODO; no connector in v0.2) |
| `substack` | longform | dry-run, draft (payload + TODO; no connector in v0.2) |
```

- [ ] **Step 2: Extend `scripts/test_local.py` smoke**

Edit `scripts/test_local.py` to also exercise the image-post and longform-multi fixtures. Replace the body of `main()`:

```python
def main() -> int:
    fixtures = [
        ROOT / "tests" / "fixtures" / "wechat-article-e2e.yaml",
        ROOT / "tests" / "fixtures" / "image-post-multi.yaml",
        ROOT / "tests" / "fixtures" / "longform-multi.yaml",
    ]
    with tempfile.TemporaryDirectory(prefix="mmp-smoke-") as tmp:
        tmp_path = Path(tmp)
        runs_dir = tmp_path / "runs"
        env_extra = {
            "MMP_RUNS_DIR": str(runs_dir),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        }

        for fix in fixtures:
            p = _run_mmp("validate", str(fix), env_extra=env_extra)
            assert p.returncode == 0, f"validate failed for {fix}:\n{p.stderr}"

            p = _run_mmp("publish", str(fix), env_extra=env_extra)
            assert p.returncode == 0, f"publish dry-run failed for {fix}:\n{p.stderr}"

        # doctor + list
        p = _run_mmp("doctor", env_extra=env_extra)
        assert p.returncode == 0
        p = _run_mmp("list", "providers", env_extra=env_extra)
        assert p.returncode == 0
        for prov in ("wechat-article", "xiaohongshu", "wechat-image", "x-article", "substack"):
            assert prov in p.stdout, f"{prov} missing from list"

        runs = sorted((runs_dir).iterdir())
        print(json.dumps({"ok": True, "tmp": str(tmp_path), "runs": [str(r) for r in runs]}, indent=2))
        return 0
```

- [ ] **Step 3: Run smoke**

Run: `make smoke`
Expected: prints `{"ok": true, "runs": [...]}` with 3 run dirs.

- [ ] **Step 4: Commit**

```bash
git add SKILL.md scripts/test_local.py
git commit -m "docs(skill): mark all 5 providers available; smoke covers all of them"
```

---

## Task 11: Update HANDOFF.md

**Files:**
- Modify: `docs/HANDOFF.md`

- [ ] **Step 1: Append Plan 3 status block**

```markdown

### Plan 3 status (this commit range)

- All 4 remaining providers migrated:
  - `xiaohongshu` (image-post + video-post): local draft via `xiaohongshu/scripts/draft.sh`
  - `wechat-image` (image-post): browser-flow guide (mp.weixin.qq.com is policy-blocked)
  - `x-article` (longform): payload-only stub; connector TODO
  - `substack` (longform): payload-only stub; connector TODO
- Old scripts (`prepare_image_post.py`, `prepare_longform.py`, `execute_image_post.py`,
  `adapt_content.py`, `publish_manifest.py`) deprecated as thin shims; remove in v0.3
- Smoke test covers wechat-article + image-post-multi + longform-multi
- 5 providers visible in `mmp list providers`

### Open items after Plan 3

- Plugin marketplace prep + dual-host distribution: Plan 4
- CI matrix (GitHub Actions): Plan 4
- Real WeChat / X / Substack account verification: see `docs/manual-verification.md` (Plan 4)
```

- [ ] **Step 2: Commit**

```bash
git add docs/HANDOFF.md
git commit -m "docs(handoff): note Plan 3 completion"
```

---

## Task 12: Final Lint + Test Pass

- [ ] **Step 1: Run lint**

Run: `python3 -m ruff check . && python3 -m ruff format --check .`
Expected: 0 issues.

- [ ] **Step 2: Run typecheck**

Run: `python3 -m mypy core providers`
Expected: 0 errors. (Note: `providers/` was not in mypy `files` config in Plan 1; if errors flood, narrow to per-file or update config.)

If providers cause noise, update `pyproject.toml`:

```toml
[tool.mypy]
files = ["core", "providers"]
[[tool.mypy.overrides]]
module = "providers.*.internal.*"
ignore_errors = true
```

- [ ] **Step 3: Run full test**

Run: `make test`
Expected: all green.

- [ ] **Step 4: Commit any cleanup**

```bash
git add -A
git diff --cached --quiet || git commit -m "chore(plan-3): final cleanup"
```

---

## Self-Review Checklist

- [ ] All 12 tasks committed
- [ ] `make test` green
- [ ] `mmp list providers` shows 5 providers
- [ ] All 5 providers have test files in `providers/<name>/tests/`
- [ ] Old scripts in `scripts/` are now shims that exit 1 with deprecation warning
- [ ] `references/wechat-image-calibration.md` and `references/wechat-api-provider.md` moved to provider notes
- [ ] Spec sections covered: §10 (all 5 providers migrated)
- [ ] Items deferred: §9 (dual-host plugin manifest) + §11 (CI) → Plan 4

## Hand-off to Plan 4

Plan 4 will:
- Write `.claude-plugin/plugin.json`
- Polish SKILL.md for plugin marketplace submission
- Rewrite README.md as user-facing install + usage
- Create `docs/architecture.md`, `docs/provider-contract.md`, `docs/credentials.md`, `docs/safety-policy.md`, `docs/manual-verification.md`
- Add `.github/workflows/ci.yml` with matrix
- Bump version to 0.2.0 in pyproject + plugin.json + SKILL.md
- Decide whether to remove deprecated shims (probably keep through v0.2 → remove in v0.3)
