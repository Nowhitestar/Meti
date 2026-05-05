# Image Post MVP

Targets: `xiaohongshu`, `wechat-image`.

## Installed Dependencies

- `xiaohongshu` — local MCP-backed skill. Prefer its draft/save-to-platform-draft flow.
- `multi-post` — installed from ClawHub. Browser automation reference for multi-platform text+images. Includes:
  - `references/platform-rules.md`
  - `references/platform-flows.md`
- `social-media-publish` — installed from ClawHub. Browser automation instructions for 微信公众号、百家号、小红书. Use as WeChat 图文 browser-flow reference.

## Unified Input

Use an `image-post` manifest:

```yaml
type: image-post
title: "标题"
body: ./caption.md
mode: draft
targets: [xiaohongshu, wechat-image]
assets:
  images:
    - ./01.png
tags: [AI, 创业]
```

## Phase 2 Audit Summary

- `multi-post` is instruction-only and useful for platform rules/browser flows, but it is direct-publish oriented; MMP must wrap it with draft/confirmation safety.
- `social-media-publish` is instruction-only and better aligned with draft-first WeChat flows; use it for WeChat/Baijiahao procedure.
- See `references/phase2-audit.md` for detailed notes.

## Preparation Script

Use `scripts/prepare_image_post.py <manifest>` to create an offline run pack. It validates local images, resolves body text, writes per-target `payload.json`, and creates `preview.md`. It never publishes.

## Adapter Outputs

Generate a platform pack directory per target:

```text
packs/
  xiaohongshu/
    content.md
    payload.json
  wechat-image/
    content.md
    payload.json
```

### Xiaohongshu Payload

```json
{
  "title": "<=20 chars preferred",
  "content": "<=1000 chars preferred",
  "images": ["/absolute/path/01.png"],
  "tags": ["AI", "创业"]
}
```

Execution preference:

1. `skills/xiaohongshu/scripts/draft.sh <payload-json>` to create a local draft.
2. `skills/xiaohongshu/scripts/save-platform-draft.sh latest` only after user confirms external draft write.
3. `skills/xiaohongshu/scripts/publish-draft.sh latest --yes` only after explicit public publish confirmation.

### WeChat Image Payload

```json
{
  "title": "title",
  "content": "caption/body",
  "images": ["/absolute/path/01.png"],
  "cover": "/absolute/path/01.png",
  "mode": "draft"
}
```

Execution preference:

1. Use `social-media-publish` browser workflow for WeChat 图文/公众号-like browser drafting after verifying the exact UI.
2. Use `multi-post` browser flow patterns for upload/confirmation handling.
3. Stop at draft/save screen unless the user explicitly confirms public publish.

## Draft Executor

Use `scripts/execute_image_post.py <run-dir>` only after reviewing `preview.md`. Current behavior:

- `--target xiaohongshu --yes-draft` creates a local Xiaohongshu draft through `skills/xiaohongshu/scripts/draft.sh`.
- `--target wechat-image` writes a `browser-flow.md` guide for manual/agent browser drafting.
- Public publish is intentionally unsupported.

## Preflight Checklist

- Confirm target list.
- Confirm mode is `draft` unless user explicitly requests publish.
- Verify every image path exists and is local.
- Resolve body path to text.
- Generate platform packs and show concise preview.
- Ask for confirmation before any browser/API write.

## Notes

- `social-media-publish` currently describes 微信公众号草稿流程, not a code adapter. Treat it as procedural guidance.
- The user distinguishes 微信图文内容 from 公众号文章. If the actual UI path differs, update this reference after first manual/browser run.


## WeChat Calibration Status

Initial browser calibration is blocked by navigation policy for `mp.weixin.qq.com`. See `references/wechat-image-calibration.md`.
