# Manifest Schema

Use YAML. Keep one source content package and a list of targets.

## Shared Fields

```yaml
type: image-post | longform | video-post
title: "Human-readable title"
body: "Inline content or ./path/to/content.md"
summary: "Optional short synopsis"
mode: draft # draft | publish
language: zh-CN
targets:
  - xiaohongshu
assets:
  cover: ./cover.png
  images: []
  video: null
tags: []
cta: "Optional call to action"
metadata:
  slug: optional-slug
  source: optional-source
```

## Image Post Example

```yaml
type: image-post
title: "20字内小红书标题，可另行适配"
body: ./caption.md
mode: draft
targets:
  - xiaohongshu
  - wechat-image
assets:
  images:
    - ./01.png
    - ./02.png
tags:
  - AI
  - 创业
```

## Longform Example

```yaml
type: longform
title: "长文章标题"
body: ./article.md
mode: draft
targets:
  - wechat-article
  - x-article
  - substack
assets:
  cover: ./cover.png
tags:
  - AI
  - 观察
```

## Generated Payload Notes

- `prepare_image_post.py` writes selected target payloads under `packs/<target>/payload.json` and, when `wechat-image` is selected, also writes `packs/wechat-article-api-bridge/payload.json`. The bridge payload contains `title`, `content`, `cover`, `digest`, `tags`, and `mode`, and can be passed to `wechat_api_draft.py draft-from-payload --dry-run` without extra field edits.
- `prepare_longform.py` writes `packs/wechat-article/payload.json`, `packs/x-article/payload.json`, and `packs/substack/payload.json` for the MVP longform targets. The WeChat article payload includes both Markdown `content` and minimal rendered `html` for API draft smoke tests.

## Validation Rules

- `type`, `title`, `body`, `targets`, and `mode` are required.
- `image-post` requires at least one image unless the target explicitly supports text-only.
- `longform` should use a Markdown body path when possible.
- `publish` mode requires explicit user confirmation before any public action.
- Paths are resolved relative to the manifest file.
