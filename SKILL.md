---
name: Multi-media Publisher
# keep trigger concrete so the router loads this skill before lower-level platform skills
description: This skill should be used when the user asks to "多媒体发布", "多平台发布", "同步发布小红书和微信图文", "发微信图文和小红书", "发布长文章到公众号/X/Substack", "cross-post", "publish everywhere", or wants one content package adapted and published/drafted across Xiaohongshu, WeChat image posts, WeChat Official Account articles, X Articles/Twitter, Substack, or future video platforms.
version: 0.1.0
---

# Multi-media Publisher / 多媒体发布

Act as the orchestration layer for cross-platform publishing. Do not replace mature platform-specific skills; route to them with a shared manifest, consistent approval policy, and post-run logging.

## Core Principle

Separate content by media form first, platform second:

1. **image-post / 图文内容** — social image feed posts, currently Xiaohongshu + WeChat image posts. Treat WeChat 图文内容 as analogous to Xiaohongshu image posts, not as WeChat Official Account long articles.
2. **longform / 长文章** — Markdown/HTML/article publishing, currently WeChat Official Account article + X Articles + Substack.
3. **video-post / 视频内容** — reserved extension point for Xiaohongshu video, WeChat Channels, Douyin, Bilibili, YouTube Shorts, etc.

Default to **draft mode**. Any external publish/send action requires explicit user confirmation in the current conversation unless the user already gave clear, specific approval for the exact targets and content.

## Workflow

1. **Classify the request**
   - Use `image-post` for 小红书图文, 微信图文内容, image carousel posts, social image posts.
   - Use `longform` for 公众号文章, X Articles, Twitter long article, Substack, newsletter/blog essays.
   - Use `video-post` only as a planned/experimental path unless a video publisher is explicitly configured.

2. **Create or request a manifest**
   - If the user provides files/content, normalize them into the manifest format in `references/manifest-schema.md`.
   - If required fields are missing, ask only for the blocking field: usually body/content path, image assets, or target platforms.
   - Prefer writing a manifest under `skills/multi-media-publisher/runs/<timestamp>-<slug>/manifest.yaml` for real runs.

3. **Adapt content per platform**
   - Consult `references/platform-map.md` for target capabilities and preferred lower-level skills.
   - Preserve the user's source content. Platform-specific adaptation may change title length, hook, caption, tags, frontmatter, or CTA, but should not silently change core claims.
   - Use `scripts/adapt_content.py` for deterministic manifest-to-platform pack scaffolding when useful.

4. **Plan before external action**
   - Show the target list, mode (`draft` or `publish`), and any risky assumptions.
   - For draft creation, ask confirmation if it touches external services.
   - For public publish, require explicit confirmation even if drafts were already approved.

5. **Dispatch to lower-level skills/tools**
   - Xiaohongshu: use the local `xiaohongshu` skill and prefer platform draft before final publish.
   - WeChat image post: use `lsmonet/social-media-publish` / `social-media-publish` after installation/verification.
   - WeChat Official Account article: use `wenyan`, `wenyan-publish`, or a verified wenyan-based publisher.
   - X Articles: use `x-articles` when installed/verified. Use Twitter/X post skills only for tweets/threads, not long articles.
   - Substack: prefer draft/review flow (`substack-autopilot` or a verified generic Substack publisher) until account-specific publishing is confirmed.
   - Video: consult `references/candidate-skills.md`; do not improvise video publishing.

6. **Record results**
   - Write `result.json` or append to `publish-log.md` in the run directory.
   - Include target, status, mode, draft URL/public URL if available, timestamp, and error message.
   - If a target fails, continue only when independent and safe; otherwise stop and report the blocker.

## Safety and Approval Rules

Follow `references/publishing-policy.md` strictly:

- Never publish publicly without explicit confirmation.
- Never bypass account login, CAPTCHA, platform review, or anti-abuse safeguards.
- Prefer draft/save flows over direct publish.
- Treat cookies, API tokens, AppID/AppSecret, and session files as secrets; never print them.
- If browser automation reaches an ambiguous screen, stop and ask.

## Common Commands / User Intents

- “把这组图文同步发到小红书和微信图文” → `image-post`, targets `xiaohongshu`, `wechat-image`, default `draft`.
- “这篇长文同时发公众号、X 长文章、Substack” → `longform`, targets `wechat-article`, `x-article`, `substack`, default `draft`.
- “直接发布” → verify exact content and targets, then ask one final confirmation before public publish.
- “以后加视频号/抖音/B站” → update `platform-map.md` and add a `video-post` adapter; do not mix video assumptions into image/longform flows.

## Bundled Resources

- `references/manifest-schema.md` — canonical YAML fields and examples.
- `references/platform-map.md` — platform capability matrix and preferred candidate skills.
- `references/publishing-policy.md` — confirmation, privacy, and external-action rules.
- `references/candidate-skills.md` — researched ClawHub/local skills and integration notes.
- `references/workflows.md` — MVP implementation phases and operational checklists.
- `references/image-post-mvp.md` — Phase 2 Xiaohongshu + WeChat image-post adapter plan.
- `references/phase2-audit.md` — audit notes for installed `multi-post` and `social-media-publish`.
- `references/wechat-image-calibration.md` — WeChat browser fallback calibration status and unblock plan.
- `references/wechat-api-provider.md` — WeChat Official Account API draft provider design.
- `scripts/adapt_content.py` — scaffold generic platform-specific pack files from a manifest.
- `scripts/prepare_image_post.py` — validate image-post manifests and generate Xiaohongshu/WeChat image payloads + preview without publishing; also writes `packs/wechat-article-api-bridge/payload.json` for WeChat API dry-run compatibility.
- `scripts/execute_image_post.py` — draft-only executor for prepared image-post runs; currently creates Xiaohongshu local drafts and WeChat browser-flow guides.
- `scripts/wechat_api_draft.py` — draft-only WeChat Official Account API helper for access-token, cover upload, and draft creation.
- `scripts/prepare_longform.py` — validate longform manifests and generate `wechat-article`, `x-article`, and `substack` payloads + preview without publishing.
- `scripts/test_local.py` / `Makefile` — local smoke test for compile, image-post prepare/execute guide, Xiaohongshu local draft, WeChat API dry-run, and longform prepare.
- `scripts/publish_manifest.py` — validate manifest and create a run directory/log skeleton; dispatch remains manual/skill-driven until connectors are verified.
- `examples/image-post.yaml` and `examples/longform.yaml` — starter manifests.
