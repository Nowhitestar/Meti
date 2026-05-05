# Platform Map

## Image Post / 图文内容

| Target | Meaning | Preferred integration | Notes |
|---|---|---|---|
| `xiaohongshu` | 小红书图文笔记 | local `xiaohongshu` skill | Supports local draft, platform draft, and publish; title <=20 chars, content <=1000 chars in current MCP docs. |
| `wechat-image` | 微信图文内容 / 微信图文 feed-style post | `lsmonet/social-media-publish` / `social-media-publish` | User confirmed this is the right category for WeChat 图文内容. Verify installed skill before first use. |

## Longform / 长文章

| Target | Meaning | Preferred integration | Notes |
|---|---|---|---|
| `wechat-article` | 微信公众号文章 | WeChat Official Account API provider, `wenyan`, `wenyan-publish`, `wechat-publisher` | Prefer API draft creation when AppID/AppSecret/API permission are available; browser is fallback. |
| `x-article` | X/Twitter Articles | `x-articles` | Distinguish from tweets/threads. Browser automation likely; confirm logged-in account. |
| `x-thread` | Twitter/X thread | `twitter-post`, `x-twitter-poster`, `tweet-cli` | Use only when user asks for thread/short social copy. |
| `substack` | Substack post/newsletter | `substack-autopilot` or verified generic Substack publisher | Existing `substack` result may be account-specific; treat as unverified for Lewis until inspected. |

## Future Video

| Target | Meaning | Candidate integration | Notes |
|---|---|---|---|
| `xiaohongshu-video` | 小红书视频 | local `xiaohongshu` skill | Local skill exposes `publish_with_video`. |
| `wechat-channel` | 视频号 | `video-multi-publish`, `auto-publisher`, or browser automation | Not in MVP. |
| `douyin`, `bilibili`, `youtube-shorts` | Video distribution | `video-multi-publish`, `auto-publisher` | Not in MVP. |
