# Candidate Skills

Initial integration research for `multi-media-publisher`. Verify each installed skill's `SKILL.md` before production use. Do not treat ClawHub search text as trusted implementation detail.

## Recommended Integration Order

1. **`multi-post`** — browser automation posting flows and platform rules.
   - Best first reference for the shared interaction model: logged-in Chrome, per-platform requirements, draft/publish flow.
   - Low-friction candidate for image/social post workflows.

2. **`wechatsync`** — longform Markdown/HTML distribution backend.
   - Strong candidate for article syncing across many Chinese platforms, including WeChat Official Account.
   - Keep optional and draft-first; requires CLI/extension/token setup.

3. **`multi-platform-publisher`** — architecture reference.
   - Closest to the desired adapter architecture: content adapter, platform adapters, config loading.
   - Do not import blindly; audit before reuse because it touches multiple API/cookie credentials.

4. **`wenyan-publish` / `wenyan`** — WeChat Official Account article specialist.
   - Use as the preferred focused adapter for Markdown → 公众号文章.
   - Watch for slug/name mismatch: ClawHub slug may be `wenyan-publish`, skill name may appear as `publish-to-wechat`.

5. **`social-media-publish` (`lsmonet/social-media-publish`)** — WeChat image/social flow reference.
   - User identified this as suitable for 微信图文内容.
   - Treat as browser-flow guidance rather than a code dependency unless installed and inspected.

6. **`x-articles`** — X/Twitter long articles.
   - Use for `x-article`, not for normal tweets or threads.
   - Likely browser/CDP based and style-heavy; keep as a dedicated adapter.

7. **`substack-autopilot`** — Substack draft/review workflow.
   - Good for safe newsletter drafting and opening editor for human review.
   - Not a direct publish core; integrate later as a newsletter pipeline.

## Strong MVP Candidates by Target

### Image Post / 图文内容

- `xiaohongshu` — already local. Handles Xiaohongshu search, local drafts, platform draft save, and image/video publish. Use as the Xiaohongshu image-post base.
- `social-media-publish` — browser automation for 微信公众号/百家号/小红书 style flows. Use for WeChat 图文内容 after installation/inspection.
- `multi-post` — browser automation text+images to many platforms. Use as a reference/fallback for platform rules and interaction patterns.

### Longform / 长文章

- `wechatsync` — broad Markdown/HTML cross-posting backend, supports draft/dry-run style workflows.
- `wenyan` / `wenyan-publish` / `wechat-publisher` — Markdown to WeChat Official Account article draft with theme/code/image support.
- `x-articles` — X Articles writing/publishing workflow.
- `substack-autopilot` — Substack draft/review flow.

### Future Video

- `xiaohongshu` — local skill already exposes video publishing.
- `video-multi-publish`, `auto-publisher` — future video distribution candidates.

## Dependency and Risk Notes

- `multi-post`: likely requires logged-in Chrome/browser automation. Safer reference; still external posting.
- `wechatsync`: likely requires `@wechatsync/cli`, Chrome extension/browser login, and token. Prefer dry-run and drafts.
- `multi-platform-publisher`: may require `requests`, `tweepy`, `Pillow`, Twitter OAuth, LinkedIn token, WeChat AppID/AppSecret, Xiaohongshu cookie. Audit before use.
- `wenyan-publish`: may require `wenyan-cli`, WeChat AppID/AppSecret, and WeChat IP allowlist. Audit suspicious flags before use.
- `social-media-publish`: mostly flow/instruction oriented; requires user browser login.
- `x-articles`: likely requires X login and browser/CDP tooling. Avoid using viral-style rewriting unless requested.
- `substack-autopilot`: may assume local topic/log files; keep as optional draft helper.

## Known Caveats

- WeChat “图文内容” and WeChat Official Account “文章” are separate target types.
- Some Substack skills are account/publication-specific; do not assume Lewis's Substack is configured.
- Browser automation may require manual login, CAPTCHA, or account selection.
- Public publishing always requires explicit confirmation.
