# Phase 2 Audit: multi-post + social-media-publish

## multi-post

- Install slug: `multi-post`
- Owner/version: `jeffchang2024` / `1.0.0`
- Structure:
  - `SKILL.md`
  - `references/platform-flows.md`
  - `references/platform-rules.md`
- Code/scripts: none; instruction-only skill.
- Security posture: clean scan, but it uses the user's logged-in Chrome profile and can post as the current account. It does not enforce per-platform confirmation by itself.

### Dependencies

- OpenClaw browser automation with user Chrome/profile.
- Target platforms logged in already.
- Image files must be local and browser-accessible.

### Supported Platforms

Weibo, Xiaohongshu, Zhihu, Twitter/X, Reddit, V2EX, LinkedIn, Douban.

### Reusable Parts

- Platform adaptation rules: char limits, image counts, hashtags, tone, link handling.
- Browser flow templates per platform.
- Post-publish logging checklist: screenshot, URL, status, timestamp, small waits between platforms.

### MMP Integration Notes

Use `multi-post` primarily as:

1. Content adaptation reference.
2. Browser automation flow reference.
3. Optional executor for non-core social platforms after adding MMP's confirmation wrapper.

Do not let it drive all-platform direct publish by default.

## social-media-publish

- Install slug: `social-media-publish`
- Owner/version: `lsmonet` / `1.0.0`
- Structure:
  - `SKILL.md`
- Code/scripts: none; instruction-only skill.
- Security posture: clean scan, but it can operate logged-in accounts for drafts/publishing/group-send. It explicitly expects final user confirmation.

### Dependencies

- OpenClaw browser automation against web UIs.
- First-time manual login.
- No special config.

### Supported Platforms

- WeChat Official Account / 微信公众号
- Baijiahao / 百度百家号
- Xiaohongshu via another publish skill path, not expanded here.

### Inputs

- WeChat Official Account: title required, body, optional cover image, Markdown conversion/formatting.
- Baijiahao: title required, body, cover image required, category.

### Reusable Parts

- WeChat flow: backend → content/image-text → new creation → fill title/body/cover → save draft or publish.
- Baijiahao flow: backend → publish image-text → fill fields → submit for review.
- Interaction protocol: confirm platform, title, body, cover before automation.

### MMP Integration Notes

Use `social-media-publish` as the safer browser-flow reference for WeChat/Baijiahao, especially because it recommends draft-first for WeChat.

## Phase 2 Decision

- Use `multi-post` for platform rules and generic browser flow patterns.
- Use `social-media-publish` for WeChat/Baijiahao-specific flow and confirmation protocol.
- Keep MMP as the safety wrapper:
  1. Generate platform previews.
  2. Show target/account/page/title/body/images/mode.
  3. Ask for confirmation before external write.
  4. Execute sequentially, never parallel.
  5. Log screenshot/URL/status/error.

## Extra Audit Needed

If MMP later supports 小红书长文 through a separate `xiaohongshu-publish` skill, audit that skill independently before wiring it in.
