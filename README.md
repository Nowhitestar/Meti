# Multi-media Publisher / 多媒体发布

统一调度多平台内容发布的 OpenClaw skill。

## MVP 目标

- 图文内容：小红书 + 微信图文内容
- 长文章：微信公众号文章 + X Articles + Substack 草稿
- 未来：视频号 / 小红书视频 / 抖音 / B站 / YouTube Shorts

## 当前状态

已完成：

- Skill 骨架：`SKILL.md`
- Manifest schema：`references/manifest-schema.md`
- 平台矩阵：`references/platform-map.md`
- 发布安全策略：`references/publishing-policy.md`
- 候选技能调研：`references/candidate-skills.md`
- 工作流规划：`references/workflows.md`
- 示例 manifest：`examples/image-post.yaml`, `examples/longform.yaml`
- 辅助脚本：
  - `scripts/publish_manifest.py`：校验 manifest 并创建 run skeleton
  - `scripts/adapt_content.py`：生成各平台 content pack 草稿
  - `scripts/prepare_image_post.py`：生成小红书/微信图文 payload 和预览，不发布；同时生成 `wechat-article-api-bridge` payload，可被 `wechat_api_draft.py --dry-run` 直接验证
  - `scripts/execute_image_post.py`：执行已确认的草稿动作；当前支持小红书本地草稿 + 微信图文操作指南
  - `scripts/wechat_api_draft.py`：微信公众号 API 草稿助手，支持 dry-run；`draft-from-payload` 可读取 payload 内的 `cover`
  - `scripts/prepare_longform.py`：生成公众号文章 / X Articles / Substack 长文 payload 和预览，不发布
  - `scripts/test_local.py` + `Makefile`：本地 smoke test，覆盖 py_compile、image-post prepare、微信 guide、小红书本地 draft、WeChat API dry-run、longform prepare

## 基本用法

```bash
python3 skills/multi-media-publisher/scripts/publish_manifest.py \
  skills/multi-media-publisher/examples/image-post.yaml

python3 skills/multi-media-publisher/scripts/adapt_content.py \
  skills/multi-media-publisher/examples/longform.yaml \
  --out /tmp/mmp-adapt

python3 skills/multi-media-publisher/scripts/prepare_image_post.py \
  /path/to/image-post.yaml

python3 skills/multi-media-publisher/scripts/execute_image_post.py \
  /path/to/run-dir --target xiaohongshu --yes-draft

python3 skills/multi-media-publisher/scripts/wechat_api_draft.py \
  draft-from-payload /path/to/run-dir/packs/wechat-article-api-bridge/payload.json --dry-run

python3 skills/multi-media-publisher/scripts/prepare_longform.py \
  skills/multi-media-publisher/examples/longform.yaml

make -C skills/multi-media-publisher test
```

脚本不会真实发布。真实外发必须通过已验证的平台 skill，并遵守 draft-first / confirmation-first 策略。
