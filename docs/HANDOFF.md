# Multi-media Publisher 开发交接文档

最后更新：2026-05-05

## 1. 项目目标

`multi-media-publisher` 是一个 OpenClaw skill，用来统一调度多平台内容发布。

核心思路：

- 不从零实现所有平台发布器。
- 以统一 manifest 为入口。
- 根据内容类型拆分平台适配。
- 复用已有平台 skill / API / browser flow。
- 默认草稿优先，公开发布必须二次确认。

当前规划支持三类内容：

1. `image-post`：图文内容
   - 小红书图文
   - 微信图文内容
2. `longform`：长文章
   - 微信公众号文章
   - X Articles
   - Substack
3. `video-post`：未来扩展
   - 小红书视频、视频号、抖音、B站、YouTube Shorts 等

重要判断：

- 微信“图文内容”和微信公众号“文章”不是同一个东西。
- 微信图文内容更像小红书图文流。
- 微信公众号文章属于 longform。
- 微信相关能力优先走 API，browser flow 只作为 fallback。

## 2. 当前完成状态

当前本地 MVP 已跑绿。

已完成：

- Skill 骨架与触发描述
- 平台矩阵
- manifest schema
- 发布安全策略
- 候选 ClawHub skill 调研
- 图文 MVP prepare
- 图文 MVP draft executor v1
- 微信公众号 API draft helper
- 长文章 MVP prepare
- 本地测试入口

测试命令：

```bash
cd skills/multi-media-publisher
make test
```

最近一次主会话验证通过：

```json
{
  "ok": true,
  "tmp": "/Users/liaoyuxing/.openclaw/tmp/mmp-local-test-qmdaiwjx",
  "image_run": "/Users/liaoyuxing/.openclaw/tmp/mmp-local-test-qmdaiwjx/runs/20260505-135225-ai-创业的三个误区",
  "longform_run": "/Users/liaoyuxing/.openclaw/tmp/mmp-local-test-qmdaiwjx/runs/20260505-135225-ai-agent-不是工具-而是一种新的组织形态"
}
```

测试覆盖：

- Python 语法检查
- image-post prepare
- 微信 browser-flow guide 生成
- 小红书本地 draft 创建
- 微信 API draft dry-run
- longform prepare

没有做任何真实外部发布。
没有使用真实 secrets。

## 3. 目录结构

```text
skills/multi-media-publisher/
  SKILL.md
  README.md
  Makefile
  docs/
    HANDOFF.md
  examples/
    image-post.yaml
    longform.yaml
  references/
    candidate-skills.md
    image-post-mvp.md
    manifest-schema.md
    phase2-audit.md
    platform-map.md
    publishing-policy.md
    wechat-api-provider.md
    wechat-image-calibration.md
    workflows.md
  scripts/
    adapt_content.py
    execute_image_post.py
    prepare_image_post.py
    prepare_longform.py
    publish_manifest.py
    test_local.py
    wechat_api_draft.py
```

## 4. 关键脚本

### `scripts/prepare_image_post.py`

用途：

- 读取 `image-post` manifest
- 校验本地图片
- 生成 run 目录
- 生成小红书 payload
- 生成微信图文 payload
- 生成微信公众号 API bridge payload
- 生成 `preview.md`

输出示例：

```text
runs/<timestamp>-<slug>/
  manifest.json
  preview.md
  result.json
  packs/
    xiaohongshu/
      payload.json
      content.md
    wechat-image/
      payload.json
      content.md
      browser-flow.md  # execute 时生成
    wechat-article-api-bridge/
      payload.json
```

### `scripts/execute_image_post.py`

用途：

- 执行已准备好的 image-post run。
- 当前只支持 draft-safe 操作。

当前能力：

- `--target xiaohongshu --yes-draft`
  - 调用 `skills/xiaohongshu/scripts/draft.sh`
  - 创建本地小红书草稿
  - 不发布
- `--target wechat-image`
  - 生成微信图文 browser flow guide
  - 不打开浏览器，不发布

安全限制：

- 公开发布未实现。
- 小红书本地草稿也必须显式 `--yes-draft`。

### `scripts/wechat_api_draft.py`

用途：微信公众号 API 草稿助手。

命令：

```bash
python3 scripts/wechat_api_draft.py check-env
python3 scripts/wechat_api_draft.py get-token
python3 scripts/wechat_api_draft.py upload-thumb ./cover.png
python3 scripts/wechat_api_draft.py add-draft ./articles.json
python3 scripts/wechat_api_draft.py draft-from-payload ./payload.json --dry-run
```

环境变量：

- `WECHAT_APP_ID`
- `WECHAT_APP_SECRET`
- 可选：`WECHAT_ACCESS_TOKEN`

当前只实现草稿，不实现公开发布/freepublish。

### `scripts/prepare_longform.py`

用途：

- 读取 `longform` manifest
- 生成：
  - `wechat-article` payload
  - `x-article` payload
  - `substack` payload
  - `preview.md`

当前 X Articles / Substack 仍是 payload + preview 级别，没有真实外部 draft connector。

### `scripts/test_local.py`

本地测试入口，由 `make test` 调用。

## 5. 已安装/参考的外部 Skills

### 已安装

- `xiaohongshu`
  - 本地已有。
  - 当前用于小红书本地 draft。
- `multi-post`
  - ClawHub 安装。
  - instruction-only。
  - 用作平台规则和 browser automation flow 参考。
- `social-media-publish`
  - ClawHub 安装。
  - instruction-only。
  - 用作微信/百家号 browser flow 参考。

### 候选/后续

- `wechatsync`
  - 长文 Markdown/HTML 多平台同步候选。
- `wenyan` / `wenyan-publish`
  - 微信公众号文章专项候选。
- `x-articles`
  - X Articles 专项候选。
- `substack-autopilot`
  - Substack 草稿/审核流候选。
- `video-multi-publish` / `auto-publisher`
  - 视频发布后续候选。

详见：

- `references/candidate-skills.md`
- `references/phase2-audit.md`

## 6. 安全策略

详见：`references/publishing-policy.md`

核心规则：

- 默认 draft mode。
- 任何公开发布必须明确二次确认。
- 不绕过登录、验证码、风控、平台审核。
- 不打印 secrets。
- 不把 AppID/AppSecret/token 写进 manifest 或 result log。
- 平台执行串行，不并发。
- 失败时记录 target/status/error，不假装成功。

## 7. 已知限制

1. 微信真实 API 草稿未用真实账号验证。
   - 当前只跑了 dry-run。
   - 需要公众号 AppID/AppSecret、IP 白名单和接口权限。

2. 微信图文 browser flow 未校准。
   - OpenClaw browser 当前访问 `mp.weixin.qq.com` 被 policy 阻止。
   - 但 API 路线优先，所以这不是主线 blocker。

3. 小红书当前只验证到本地草稿。
   - 未保存到小红书平台草稿。
   - 未公开发布。

4. X Articles / Substack 只有 prepare payload。
   - 未安装/验证真实 connector。

5. `wechat-image` 与 `wechat-article-api-bridge` 的最终语义还需要真实微信 API 能力确认。
   - 如果微信 API 只能发公众号文章草稿，则微信图文内容可能仍需要特定 API 或 browser/UI 路径。

## 8. 下一步建议

优先级建议：

1. **微信真实 API 草稿验证**
   - 配置 `WECHAT_APP_ID` / `WECHAT_APP_SECRET`
   - 确认 IP 白名单
   - 用测试 payload 创建草稿
   - 不发布

2. **小红书平台草稿验证**
   - 使用现有 `xiaohongshu/scripts/save-platform-draft.sh latest`
   - 只保存平台草稿，不发布

3. **Longform connector**
   - 微信公众号文章：API / wenyan 二选一或并行 provider
   - X Articles：审计并接入 `x-articles`
   - Substack：审计并接入 `substack-autopilot` 或通用 Substack provider

4. **Provider abstraction**
   - 把平台执行器抽象成 provider registry
   - 每个 provider 声明：required env、mode support、draft/publish 能力、风险等级

5. **视频扩展**
   - 增加 `video-post` manifest
   - 审计 `video-multi-publish` / `auto-publisher`

## 9. 快速上手

### 跑测试

```bash
cd skills/multi-media-publisher
make test
```

### 准备 image-post

```bash
python3 scripts/prepare_image_post.py examples/image-post.yaml
```

### 准备 longform

```bash
python3 scripts/prepare_longform.py examples/longform.yaml
```

### 微信 API dry-run

```bash
python3 scripts/wechat_api_draft.py draft-from-payload \
  <run-dir>/packs/wechat-article-api-bridge/payload.json \
  --dry-run
```

### 小红书本地草稿

```bash
python3 scripts/execute_image_post.py <run-dir> \
  --target xiaohongshu \
  --yes-draft
```

注意：这只创建本地草稿，不发布。

## 10. 交接结论

当前项目已经从“规划”推进到“本地 MVP 跑绿”。

已经可稳定完成：

- 输入 manifest
- 生成多平台 payload
- 生成 preview
- 小红书本地草稿
- 微信公众号 API dry-run
- longform 多平台 prepare
- 本地回归测试

下一任开发者可以直接从“真实 provider 验证”开始，不需要重做架构设计。

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
- v0.3 backlog: vault concurrent-write locking, atomic vault write, lost-key UX (deferred from Task 6 review)

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
