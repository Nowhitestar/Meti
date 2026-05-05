# Multi-media Publisher v0.2 Redesign — Design Spec

**Date**: 2026-05-05
**Status**: Draft (awaiting user review)
**Owner**: Lewis (yxliao.lewis@gmail.com)
**Supersedes**: existing v0.1 SKILL.md scripts-first architecture

---

## 1. Context

`multi-media-publisher` 当前是一个 OpenClaw skill，处于"本地 MVP 跑绿"状态：
- `image-post`（小红书 + 微信图文）prepare + 小红书本地 draft + 微信 browser flow guide
- `longform`（公众号 + X Articles + Substack）prepare 输出 payload + preview
- 微信公众号 API helper（dry-run only）
- 默认 draft mode；公开发布要求二次确认；本地 smoke test 覆盖语法和 prepare 链路

存在的工程问题：
- Provider 逻辑硬编码在 `prepare_image_post.py` / `prepare_longform.py` / `execute_image_post.py`，加新平台要改 6 处
- 没有真实 connector 接通（所有 target 都停在 payload / dry-run）
- Manifest 必须用户手写 YAML，门槛高
- 凭证散在 ENV / `~/.openclaw/` 各处，不可移植
- 仅在 OpenClaw 工作，Claude Code 无法触发

## 2. Goals & Non-Goals

### Goals

1. **架构抽象**：把"调度层"和"provider 实现"彻底解耦；新平台 = 新一个 provider 包，零侵入
2. **双宿主分发**：同一份代码同时是 Claude Code plugin 和 OpenClaw skill
3. **对话式 manifest**：用户不再手写 YAML，Claude 通过三阶段 wizard 引导
4. **统一凭证仓库**：跨宿主共享、加密、按 provider × account 隔离
5. **Plugin marketplace ready**：第三方能写 provider folder-drop 即生效；first-party 走同一接口
6. **Run lifecycle 可观测、可重入**：失败可恢复、log 可读、result.json machine-readable
7. **Platform rules as code**：标题长度、图片比例、字数等做成 lint，violation 在 prepare 阶段拦下

### Non-Goals (v0.2)

- 不上 PyPI（保留代码组织上的可拆性，但不发包）
- 不做 video-post（仅预留接口）
- 不做 schedule（仅记录字段）
- 不做 GUI / TUI（wizard 完全 Claude 对话驱动）
- 不真账号 e2e CI（仅 mock connector）
- 不重做 OpenClaw browser policy 兼容（继续作为 fallback，主路径走 API）

## 3. Architecture

### 3.1 三层定位

| 层 | 内容 | 约束 |
|---|---|---|
| **Shell** | `SKILL.md` + `.claude-plugin/plugin.json` | 薄壳；只声明触发 + 入口 + 版本；不放业务逻辑 |
| **Core** | `core/` Python 模块 | 宿主无关；不 import providers；不读宿主特定路径；未来可拆 PyPI |
| **Providers** | `providers/<name>/`（bundled）+ `~/.config/mmp/providers/<name>/`（user） | 同一 `Provider` 接口；互不 import |

### 3.2 项目目录结构

```
multi-media-publisher/
├── .claude-plugin/
│   └── plugin.json                # CC plugin manifest
├── SKILL.md                       # 双宿主触发
├── README.md
├── docs/
│   ├── architecture.md
│   ├── provider-contract.md
│   ├── credentials.md
│   ├── HANDOFF.md
│   └── superpowers/specs/         # 本文件所在目录
├── core/
│   ├── __init__.py
│   ├── manifest.py                # schema + 校验 + lock
│   ├── provider.py                # Provider base + ProviderRegistry
│   ├── credentials.py             # CredentialStore + backends
│   ├── wizard/
│   │   ├── source_extraction.md
│   │   ├── target_selection.md
│   │   ├── manifest_assembly.md
│   │   └── credential_setup.md
│   ├── run.py                     # run lifecycle + checkpoint + result
│   ├── rules.py                   # PlatformRules base + Violation 类型
│   ├── host.py                    # 宿主探测（仅用于 user-data 路径解析）
│   └── errors.py
├── providers/                     # bundled
│   ├── xiaohongshu/
│   │   ├── provider.yaml
│   │   ├── provider.py
│   │   ├── rules.py
│   │   └── tests/
│   ├── wechat_image/
│   ├── wechat_article/
│   ├── x_article/
│   └── substack/
├── examples/
│   ├── image-post.yaml
│   └── longform.yaml
├── runs/                          # gitignored；运行时输出
├── scripts/
│   ├── mmp.py                     # 统一 CLI 入口
│   └── test_local.py
├── tests/
│   ├── core/
│   └── integration/
├── Makefile
└── pyproject.toml                 # 仅用于本地 dev（lint / type / 路径）
```

### 3.3 共享用户数据路径

跨 CC / OpenClaw 共享，遵循 XDG：

```
~/.config/mmp/
├── credentials.json.age           # age 加密 vault
├── age-key.txt                    # vault 密钥（chmod 600）
├── providers/                     # user-installed providers
│   └── <name>/
│       ├── provider.yaml
│       └── provider.py
├── settings.toml                  # 偏好（默认 mode、默认目标列表、wizard 开关）
└── cookies/                       # 平台 cookie 文件目录
```

宿主探测（`core/host.py`）只用于：
- 决定 `runs/` 写在哪（默认 skill 目录下；ENV `MMP_RUNS_DIR` 覆盖）
- 决定 user-data 路径（XDG_CONFIG_HOME 优先，否则 `~/.config/mmp/`）

### 3.4 数据流（一次发布的生命周期）

```
用户在 CC / OpenClaw 触发
  → SKILL.md 引导
  → core/wizard 三阶段对话（source → targets → manifest 确认）
  → 落盘 runs/<ts>-<slug>/manifest.yaml
  → core/run.dispatch(manifest):
       for target in manifest.targets:
         provider = ProviderRegistry.resolve(target)
         provider.validate(manifest)            # platform_rules.lint()
         provider.prepare(manifest, run_dir)    # 写 packs/<target>/
         if mode in {draft, publish}:
           credentials = CredentialStore.get(target.name, target.account)
           provider.execute(run_dir, mode, credentials)
         写 result.json + 追加 publish-log.md + checkpoint
  → 摘要回报
```

### 3.5 关键架构约束

1. `core/` 不能 `import providers.*`、不能 `from skill_root import *`
2. Provider 之间不能互相 import
3. Vault 读写只通过 `core.credentials.CredentialStore`
4. 任何"调宿主特定路径"必须封在 provider 内部，不漏到 core
5. CC 和 OpenClaw 入口都收敛到 `scripts/mmp.py`
6. `runs/<ts>-<slug>/` 是 self-contained，不依赖项目外文件即可恢复运行

## 4. Provider Contract

### 4.1 Provider 抽象类

```python
# core/provider.py

class Provider(ABC):
    name: str                          # "xiaohongshu"
    display_name: str                  # "小红书"
    media_types: list[str]             # ["image-post", "video-post"]
    capabilities: dict[str, bool]      # {"draft": True, "publish": False, "schedule": False}
    required_credentials: list[CredentialSpec]
    platform_rules: PlatformRules

    @abstractmethod
    def validate(self, manifest: Manifest, target: Target) -> ValidationResult: ...

    @abstractmethod
    def prepare(self, manifest: Manifest, target: Target, run_dir: Path) -> PreparedPayload: ...

    @abstractmethod
    def execute(
        self,
        run_dir: Path,
        target: Target,
        mode: Mode,
        credentials: dict[str, str],
    ) -> ExecutionResult: ...

    def health_check(self, credentials: dict[str, str]) -> HealthStatus:
        """Optional: 连通性测试。default 返回 unknown。"""
        return HealthStatus.unknown
```

### 4.2 provider.yaml（元信息）

```yaml
name: xiaohongshu
display_name: 小红书
media_types:
  - image-post
  - video-post
capabilities:
  draft: true
  publish: false   # MVP 不开
  schedule: false
required_credentials:
  - key: XHS_COOKIE_PATH
    description: "Path to Xiaohongshu cookies file"
    secret: false
    setup_hint: "运行 `xhs-login` 抓 cookies；或手动从浏览器导出"
entry: provider:XiaohongshuProvider
schema_version: 1
```

### 4.3 PlatformRules

```python
# core/rules.py

@dataclass
class PlatformRules:
    title_max: int | None = None
    body_max: int | None = None
    image_count_min: int | None = None
    image_count_max: int | None = None
    image_aspect_ratios: list[str] | None = None   # e.g. ["3:4", "1:1"]
    tag_max: int | None = None
    cover_required: bool = False
    cover_aspect_ratios: list[str] | None = None
    extra_lints: list[Callable[[Manifest, Target], list[Violation]]] = field(default_factory=list)

    def lint(self, manifest: Manifest, target: Target) -> list[Violation]: ...
```

`Violation` 分级：`error`（阻断 prepare）/ `warning`（仅提示）/ `info`。

### 4.4 命名约定

| 用途 | 形式 | 例 |
|---|---|---|
| 目录名（Python module） | `snake_case` | `providers/wechat_article/` |
| `provider.yaml.name`（manifest 中引用） | `kebab-case` | `wechat-article` |
| Pack 目录（`packs/<target>/`） | 同 `provider.yaml.name` | `packs/wechat-article/` |
| Credential account ID | `<provider.name>:<account>` | `wechat-article:lewis` |

`ProviderRegistry` 按 `provider.yaml.name`（kebab）建索引；目录名只用于 Python import 路径。两者一一对应但不必同形（hyphen 在 Python 模块名中非法）。

### 4.5 Provider 发现与加载

```python
class ProviderRegistry:
    def discover(self) -> None:
        # 1. bundled: scan providers/*/provider.yaml
        # 2. user: scan ~/.config/mmp/providers/*/provider.yaml
        # 3. 同名时 user 覆盖 bundled，但首次加载 user provider 提示用户确认
        ...

    def resolve(self, target_name: str) -> Provider: ...
    def list(self) -> list[ProviderInfo]: ...
```

User-installed provider 首次加载时 SKILL.md 提示：「即将加载第三方 provider `<name>`（来自 `~/.config/mmp/providers/<name>/`），确认？」用户同意后写入 `~/.config/mmp/settings.toml` 的 trusted_providers 列表。

## 5. Manifest Schema (v0.2)

### 5.1 Schema 顶层

```yaml
schema_version: "0.2"             # 必填，用于未来兼容性
type: image-post | longform | video-post
title: "Human-readable title"
body: "Inline content or ./path/to/content.md"
summary: "Optional short synopsis"
mode: draft                        # draft | publish | dry-run
language: zh-CN
defaults:                          # 可选；应用到所有 target
  account: default
  options: {}
targets:
  # 简写：string，沿用顶层 mode
  - xiaohongshu
  # 全写：object，可覆盖 mode / account / options
  - target: wechat-article
    mode: draft
    account: lewis
    options:
      digest: "可选摘要"
      cover_url: "https://..."
assets:
  cover: ./cover.png
  images: []
  video: null
tags: []
cta: "Optional call to action"
metadata:
  slug: optional-slug
  source: optional-source
  # run_id 由 system 写，不要手填
```

### 5.2 Mode 语义

| Mode | 行为 |
|---|---|
| `dry-run` | 仅 prepare，不调 connector，不写凭证 |
| `draft` | prepare + execute 到平台 draft（或 local draft if 平台不支持） |
| `publish` | prepare + execute 到公开发布；额外二次确认 |

### 5.3 校验 (`core.manifest.validate`)

执行顺序：
1. Schema 校验：必填字段、类型、enum 值
2. Target 解析：每个 target 在 ProviderRegistry 中存在
3. Media-type 兼容：`type` ∈ `provider.media_types`
4. Capability 校验：`mode` ∈ provider.capabilities 中为 true 的项
5. PlatformRules.lint() 跑每个 target；error 级阻断
6. Credential 完备性：required_credentials 都已在 vault 中（缺则触发 setup wizard）

校验通过后落 `manifest.lock.json`（归一化形式：所有简写展开、defaults 合并）。

## 6. Credential Vault

### 6.1 文件布局

```
~/.config/mmp/
├── credentials.json.age           # 加密文件
└── age-key.txt                    # 密钥（chmod 600；ENV MMP_VAULT_KEY 覆盖）
```

加密方案：`age` （X25519，Go/Rust/Python 均有实现；选 `pyrage` 或 shell out 到 `age` CLI）。

### 6.2 解密后的 JSON 格式

```json
{
  "version": 1,
  "accounts": {
    "wechat-article:default": {
      "WECHAT_APP_ID": "wx...",
      "WECHAT_APP_SECRET": "..."
    },
    "xiaohongshu:default": {
      "XHS_COOKIE_PATH": "~/.config/mmp/cookies/xhs.json"
    },
    "x-article:lewis": {
      "X_AUTH_TOKEN": "..."
    },
    "substack:default": {
      "SUBSTACK_SESSION_COOKIE": "..."
    }
  },
  "metadata": {
    "created_at": "2026-05-05T12:00:00Z",
    "last_modified": "2026-05-05T12:00:00Z"
  }
}
```

Account ID 形式：`<provider_name>:<account>`，default account 名为 `default`。manifest 里 target 可指定 `account: lewis` 选用其他账号。

### 6.3 CredentialStore API

```python
# core/credentials.py

class CredentialStore:
    def __init__(self, backend: Backend = FileBackend()): ...

    def get(self, provider: str, account: str = "default") -> dict[str, str]:
        """优先级：ENV > vault > MissingCredentialError"""

    def set(self, provider: str, account: str, values: dict[str, str]) -> None: ...

    def list_accounts(self, provider: str | None = None) -> list[str]: ...

    def delete(self, provider: str, account: str) -> None: ...

    def health_check(self, provider: str, account: str = "default") -> HealthStatus:
        """调 provider.health_check 验证凭证可用"""
```

Backends：
- `FileBackend`：默认，age 加密
- `EnvBackend`：从 ENV 读，仅供 CI
- `KeychainBackend`：未来扩展（macOS / linux secret-service / win credential manager）

### 6.4 Setup Wizard 触发

3 种入口：
1. 用户主动："setup credentials" / "添加微信账号" / "configure xiaohongshu"
2. Manifest 校验缺凭证 → 反向触发该 provider 的 setup
3. CLI：`mmp setup [provider]`

Wizard 行为（`core/wizard/credential_setup.md`）：
- 询问 provider × account
- 列出 required_credentials；逐项询问；secret 字段不回显
- 写入 vault 后调 `health_check`，结果回报
- 失败时给出 `setup_hint`

### 6.5 安全约束

- vault 文件 chmod 600
- age-key.txt chmod 600
- 凭证值绝不进 result.json / publish-log.md / 任何 git-tracked 文件
- provider 拿到 `credentials: dict[str, str]` 后，禁止打印；如必须 log，要 mask
- ENV 覆盖优先，便于 CI / 临时使用，不污染 vault

## 7. Wizard Flow

3 阶段对话流，prompt 片段在 `core/wizard/*.md`，被 SKILL.md 引用。

### 7.1 阶段 1 — Source Extraction (`source_extraction.md`)

**输入**：用户贴的 markdown / 截图描述 / 链接 / 自然语言。

**Claude 行为**：
- 识别媒介类型（image-post / longform / video-post）
- 抽取候选字段：title / body / cover / images / tags / cta
- 不存在的字段反问，但**最小化反问**（一次最多 2 个字段）

**输出**：内部草稿（不直接落盘）。

### 7.2 阶段 2 — Target Selection (`target_selection.md`)

**输入**：阶段 1 草稿 + `ProviderRegistry.list()` + `CredentialStore.list_accounts()`。

**Claude 行为**：
- 列可用 targets（按 `media_types` 过滤）
- 标 credentials 状态：✓ 已配置 / ✗ 缺凭证（提示 setup） / ! health_check 失败
- 询问 mode（draft / publish / dry-run）
- 询问平台特化：要不要给小红书写 hook、给 X Article 起独立标题、给微信加摘要……

**输出**：target 列表 + per-target options。

### 7.3 阶段 3 — Manifest Assembly (`manifest_assembly.md`)

**输入**：阶段 1 + 阶段 2。

**Claude 行为**：
- 渲染 manifest yaml
- 跑 `manifest.validate()`，展示 violations
- error 级 violation 必须用户解决（提供修复建议）
- warning 级用户可选择忽略
- 给最终预览 + 一键确认
- 落盘 `runs/<ts>-<slug>/manifest.yaml` 和 `manifest.lock.json`

**输出**：可执行 manifest 路径 + run_id。

### 7.4 入口

- **对话**：SKILL.md 触发关键词（"发一组到..." / "cross-post to..." / "publish to..." / "新发布"）→ Claude 调 `core.wizard.run()`
- **CLI 跳过**：`mmp publish ./manifest.yaml` 直接执行（适合已有 manifest）
- **半自动**：`mmp wizard --type longform --targets wechat-article,x-article` 进 wizard 但跳过 target 选择

### 7.5 Wizard 关闭开关

`~/.config/mmp/settings.toml`:
```toml
[wizard]
enabled = true
auto_save_manifest = true
default_mode = "draft"
```

## 8. Run Lifecycle & Logging

### 8.1 Run dir 布局

```
runs/<YYYYMMDD-HHMMSS>-<slug>/
├── manifest.yaml             # 用户确认的源
├── manifest.lock.json        # 归一化、validated
├── packs/
│   └── <target>/
│       ├── payload.json
│       ├── content.md
│       ├── browser-flow.md   # 仅当 provider 需要
│       └── adapted.md        # 平台特化后的内容
├── result.json               # 顶层结果
├── publish-log.md            # 人读 timeline
├── checkpoints/
│   └── <target>.checkpoint.json
└── artifacts/
    ├── <target>-screenshot.png
    └── <target>-platform-response.json
```

### 8.2 result.json

```json
{
  "run_id": "20260505-180000-ai-foo",
  "schema_version": 1,
  "manifest_path": "manifest.yaml",
  "started_at": "2026-05-05T18:00:00Z",
  "completed_at": "2026-05-05T18:01:32Z",
  "mode": "draft",
  "host": "claude-code",
  "mmp_version": "0.2.0",
  "targets": [
    {
      "name": "xiaohongshu",
      "account": "default",
      "status": "ok",
      "mode_actual": "draft-local",
      "draft_url": null,
      "external_id": "xhs_local_xxx",
      "started_at": "2026-05-05T18:00:01Z",
      "completed_at": "2026-05-05T18:00:15Z",
      "error": null,
      "checkpoint": "checkpoints/xiaohongshu.checkpoint.json",
      "violations": []
    }
  ]
}
```

`status` enum：`ok` / `failed` / `skipped` / `partial` / `pending`。
`mode_actual` enum：`dry-run` / `draft-local` / `draft-platform` / `published`。

### 8.3 publish-log.md

人读 timeline，每个事件一行：

```
2026-05-05T18:00:00Z  RUN_START  run_id=20260505-180000-ai-foo  mode=draft
2026-05-05T18:00:01Z  TARGET_START  target=xiaohongshu  account=default
2026-05-05T18:00:03Z  PREPARE_OK  target=xiaohongshu  payload_path=packs/xiaohongshu/payload.json
2026-05-05T18:00:15Z  EXECUTE_OK  target=xiaohongshu  mode_actual=draft-local
2026-05-05T18:00:15Z  TARGET_DONE  target=xiaohongshu  status=ok
2026-05-05T18:01:32Z  RUN_DONE    overall=ok
```

### 8.4 Checkpoint & 重入

每个 target 在关键步骤写 checkpoint：

```json
{
  "target": "wechat-article",
  "step": "media_uploaded",
  "started_at": "...",
  "external_ids": {"thumb_media_id": "..."},
  "next_step": "create_draft"
}
```

`mmp resume <run-dir> [--target <name>]` 从最后 checkpoint 继续。
重入语义：execute 必须 idempotent；同一 step 重跑要么是 no-op 要么 detect 已完成跳过。

### 8.5 错误模型

```python
# core/errors.py

class MMPError(Exception): ...
class ManifestError(MMPError): ...
class ProviderNotFoundError(MMPError): ...
class MissingCredentialError(MMPError): ...
class PlatformRuleViolation(MMPError): ...
class ProviderExecutionError(MMPError):
    target: str
    step: str
    upstream: Exception | None
    retryable: bool
```

Provider 抛出 `ProviderExecutionError` 时声明 `retryable` 布尔；core 据此决定是否标记可 resume。

## 9. Dual-Host Distribution

### 9.1 SKILL.md（双兼容）

frontmatter 保持现有 yaml：`name` + `description` + `version`。
描述里的触发关键词同时覆盖 OpenClaw 和 Claude Code 路由器。

正文中清晰说明：
- 入口：`scripts/mmp.py`
- Wizard 触发短语
- 安全策略

### 9.2 `.claude-plugin/plugin.json`

```json
{
  "name": "multi-media-publisher",
  "version": "0.2.0",
  "description": "Cross-platform content publishing orchestration: 小红书 / 微信图文 / 公众号文章 / X Articles / Substack.",
  "skills": ["./SKILL.md"],
  "scripts": {
    "publish": "scripts/mmp.py publish",
    "setup":   "scripts/mmp.py setup",
    "list":    "scripts/mmp.py list"
  },
  "homepage": "https://github.com/<owner>/multi-media-publisher",
  "license": "MIT"
}
```

### 9.3 OpenClaw 安装

继续放 `skills/multi-media-publisher/`，无变化。`scripts/mmp.py` 同时为 OpenClaw 入口。

### 9.4 入口收敛

CC 和 OpenClaw 都通过 SKILL.md → `scripts/mmp.py` → `core/`。

`mmp.py` 子命令：
- `mmp publish <manifest.yaml>` — 执行
- `mmp wizard [--type ... --targets ...]` — 交互
- `mmp setup [provider]` — 凭证
- `mmp list [providers|accounts|runs]` — 检视
- `mmp resume <run-dir>` — 重入
- `mmp validate <manifest.yaml>` — 仅校验
- `mmp doctor` — 自检（vault / providers / health）

### 9.5 发布渠道

- GitHub repo（source of truth）
- Claude Code plugin marketplace（按官方流程提交）
- 不上 PyPI（保持代码组织上的 pkg-ready，但不发包）

## 10. Bundled Provider Migration

5 个 first-party provider，按以下顺序迁移：

### 10.1 迁移矩阵

| Provider | 旧位置 | 新位置 | 真实 connector 状态 | v0.2 目标 |
|---|---|---|---|---|
| wechat_article | scripts/wechat_api_draft.py + prepare_longform.py | providers/wechat_article/ | API draft dry-run | 真实账号验证草稿 |
| xiaohongshu | scripts/execute_image_post.py + prepare_image_post.py | providers/xiaohongshu/ | 本地 draft | 平台 draft 接通 |
| wechat_image | scripts/prepare_image_post.py | providers/wechat_image/ | browser flow guide | 仅 prepare + guide（unblocked 后再接 browser） |
| x_article | scripts/prepare_longform.py | providers/x_article/ | payload only | 接 `x-articles` connector OR browser stub |
| substack | scripts/prepare_longform.py | providers/substack/ | payload only | 接 `substack-autopilot` OR browser stub |

### 10.2 单 provider 迁移步骤

每个 provider 迁移 = 6 个动作：
1. 写 `provider.yaml`
2. 写 `provider.py`（继承 `Provider`，实现 4 个抽象方法）
3. 写 `rules.py`（PlatformRules 实例 + extra_lints）
4. 写 `tests/`（prepare 输入/输出 fixture + dry-run execute 单测）
5. 老脚本里对应逻辑改成 thin wrapper（call 新 provider）；smoke test 同时跑新老两路确认等价
6. 老脚本标 deprecated；下个版本删除

### 10.3 deprecate 旧脚本时间表

- v0.2 发布：旧脚本仍在，调新 provider；`make test` 同时验证新老路径
- v0.3：旧脚本删除；`make test` 仅走新路径

## 11. Testing & CI

### 11.1 测试分层

| 层 | 位置 | 范围 | 跑法 |
|---|---|---|---|
| Core 单元 | `tests/core/` | manifest schema、credential store、provider registry、wizard prompt 渲染、rules.lint | pytest |
| Provider 单元 | `providers/<name>/tests/` | prepare / rules / dry-run execute | pytest（被 provider discovery 自动收集） |
| 集成 | `tests/integration/` | 完整 run lifecycle，end-to-end mock connector | pytest |
| Smoke | `scripts/test_local.py` | 现有 make test，扩展为每 provider 一组 | `make test` |

### 11.2 CI matrix（GitHub Actions）

- OS：macOS-latest + ubuntu-latest
- Python：3.10 / 3.11 / 3.12
- Steps：lint (ruff + black --check) → typecheck (mypy core/) → pytest → smoke
- 不跑真账号；secrets 全 mock
- 在 PR 上必须全绿

### 11.3 真账号验证（手动）

`docs/manual-verification.md` 列出每个 provider 的真账号验证步骤：
- 准备凭证
- 跑 health_check
- 跑 dry-run
- 跑 draft
- 仅在用户确认后跑 publish

## 12. Extension Hooks

### 12.1 Video-post (v0.3+)

- 新增 media type：在 manifest schema 里 `type: video-post` 已合法
- `assets.video` 字段已存在
- 新 providers/<name>/ 即可：`xiaohongshu_video`、`wechat_channel`、`douyin`、`bilibili`、`youtube_shorts`
- v0.2 不实现，仅保证接口预留

### 12.2 Schedule

- manifest 加 optional `schedule:` 字段（ISO 8601 timestamp）
- core 不长驻、不实际触发；仅在 manifest 中记录
- 第三方可写 schedule provider 或外部 cron 读 manifest
- v0.2 仅记录，不执行

### 12.3 第三方 provider

- folder-drop 至 `~/.config/mmp/providers/<name>/`
- ProviderRegistry 启动时扫描
- 校验 provider.yaml schema
- 首次加载提示用户确认（防止恶意 provider）
- 信任后写入 `settings.toml.trusted_providers`

## 13. Open Questions / Risks

1. **age 加密 vs OS keychain**：v0.2 默认 age 文件方案；keychain 留给 v0.3。需确认用户对额外依赖（`age` CLI 或 `pyrage`）的容忍度。
2. **微信公众号 API 真实账号**：仍未验证；v0.2 完成时必须有一次真实账号 dry-run + draft 通过。
3. **小红书 platform draft**：现有 `xhs/save-platform-draft.sh` 是否能在 CC 环境下跑？需要审一遍依赖。
4. **第三方 provider 安全**：folder-drop 是任意 Python 代码执行风险。trusted_providers 机制要不要加签名？v0.2 仅做 confirmation prompt，不签名。
5. **Wizard prompt 的 i18n**：当前所有 wizard md 都是中文。英文用户怎么处理？v0.2 中文优先；英文翻译留给社区贡献。
6. **OpenClaw 路径硬编码迁移**：当前代码里 `~/.openclaw/tmp/` 等路径需要扫一遍，全部走 `core.host`。

## 14. Out-of-Scope (v0.2)

明确不做：
- PyPI 发包
- Video-post 真实 connector
- Schedule 执行器
- GUI / TUI / Web UI
- 自动 i18n
- 真账号 e2e CI
- Provider 数字签名
- Multi-tenant / 团队协作
- Analytics / 发布数据回流

---

## Appendix A: 文件树最终态预览

```
multi-media-publisher/
├── .claude-plugin/plugin.json
├── SKILL.md
├── README.md
├── Makefile
├── pyproject.toml
├── docs/
│   ├── architecture.md
│   ├── provider-contract.md
│   ├── credentials.md
│   ├── manual-verification.md
│   ├── HANDOFF.md
│   └── superpowers/specs/2026-05-05-multi-media-publisher-redesign-design.md
├── core/
│   ├── __init__.py
│   ├── manifest.py
│   ├── provider.py
│   ├── credentials.py
│   ├── wizard/{source_extraction,target_selection,manifest_assembly,credential_setup}.md
│   ├── run.py
│   ├── rules.py
│   ├── host.py
│   └── errors.py
├── providers/
│   ├── xiaohongshu/{provider.yaml,provider.py,rules.py,tests/}
│   ├── wechat_image/{...}
│   ├── wechat_article/{...}
│   ├── x_article/{...}
│   └── substack/{...}
├── examples/{image-post.yaml,longform.yaml}
├── scripts/{mmp.py,test_local.py}
└── tests/{core/,integration/}
```

## Appendix B: 现有资产盘点（迁移参考）

| 现有文件 | 处置 |
|---|---|
| `SKILL.md` | 改写：精简内容，引入 `scripts/mmp.py` 入口 + wizard 触发短语 |
| `README.md` | 重写：面向 CC plugin + OpenClaw 双安装说明 |
| `Makefile` | 保留 + 扩展 lint / typecheck target |
| `references/manifest-schema.md` | 替换为 `docs/architecture.md` 的 schema 节 |
| `references/platform-map.md` | 内容拆到各 `providers/<name>/provider.yaml` |
| `references/publishing-policy.md` | 升格为 `docs/safety-policy.md` |
| `references/candidate-skills.md` | 保留 in `docs/`；不再是核心引用 |
| `references/workflows.md` | 替换为 `docs/run-lifecycle.md` |
| `references/image-post-mvp.md` | 历史归档 |
| `references/phase2-audit.md` | 历史归档 |
| `references/wechat-image-calibration.md` | 移至 `providers/wechat_image/notes.md` |
| `references/wechat-api-provider.md` | 移至 `providers/wechat_article/notes.md` |
| `scripts/publish_manifest.py` | deprecate；功能归 `mmp validate` + `mmp publish` |
| `scripts/adapt_content.py` | deprecate；功能归 provider.prepare |
| `scripts/prepare_image_post.py` | 拆解到 providers/xiaohongshu + wechat_image |
| `scripts/execute_image_post.py` | 拆解到对应 providers 的 execute |
| `scripts/wechat_api_draft.py` | 移到 `providers/wechat_article/internal/` 作为内部工具 |
| `scripts/prepare_longform.py` | 拆解到 wechat_article + x_article + substack |
| `scripts/test_local.py` | 保留 + 扩展 |
| `examples/*.yaml` | 升级到 schema 0.2 |
| `docs/HANDOFF.md` | 保留作为历史；新增本 design spec |
