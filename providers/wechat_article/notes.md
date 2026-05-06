# WeChat Official Account API Provider

Use this provider before browser automation when the account has Official Account API access.

## Goal

Create WeChat Official Account drafts from MMP payloads without opening `mp.weixin.qq.com`.

## API Concepts

Typical flow:

1. Get `access_token` with AppID/AppSecret.
2. Upload cover image as permanent material or temporary material and obtain `thumb_media_id`.
3. Upload inline images via the article image upload endpoint and replace local image paths with returned URLs when needed.
4. Call draft add endpoint with an `articles` array.
5. Record returned `media_id` as the draft identifier.

## Environment

Use environment variables by default:

- `WECHAT_APP_ID`
- `WECHAT_APP_SECRET`
- Optional `WECHAT_ACCESS_TOKEN` to bypass token fetch for testing.

Never print secrets. Do not store secrets in manifests or result logs.

## Draft Article Shape

Minimum article fields:

```json
{
  "title": "标题",
  "author": "optional",
  "digest": "optional summary",
  "content": "HTML content",
  "content_source_url": "optional original URL",
  "thumb_media_id": "cover media id",
  "need_open_comment": 0,
  "only_fans_can_comment": 0
}
```

## Safety

- This provider creates drafts only in MVP.
- Do not call publish/freepublish endpoints without a separate explicit user confirmation and implementation review.
- Validate account/IP whitelist/API permission blockers and report them clearly.

## Current Implementation

`scripts/wechat_api_draft.py` implements:

- `check-env`
- `get-token`
- `upload-thumb`
- `add-draft`
- `draft-from-payload`

The script supports `--dry-run` to generate request payloads without network writes.
