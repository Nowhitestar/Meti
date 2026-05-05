# Workflows

## Phase 1 — Planning + Skeleton

- Create skill structure and manifest schema.
- Record platform matrix and candidate integrations.
- Provide validation/adaptation scripts.
- No real external publishing.

## Phase 2 — Image Post MVP

Targets: `xiaohongshu`, `wechat-image`.

1. Accept content package: title, caption/body, images, tags.
2. Run `scripts/prepare_image_post.py <manifest>` to generate `preview.md` and per-target payloads.
3. Review preview with the user.
4. After confirmation, use `scripts/execute_image_post.py <run-dir> --target ... --yes-draft` for supported draft actions.
   - Xiaohongshu: local draft via `xiaohongshu/scripts/draft.sh`.
   - WeChat image: generate `browser-flow.md`; execute browser flow only after UI calibration.
5. Record draft status and links/screenshots if available.

## Phase 3 — Longform MVP

Targets: `wechat-article`, `x-article`, `substack`.

1. Accept Markdown article and optional cover.
2. Run `scripts/prepare_longform.py <manifest>` to generate `preview.md` and per-target payloads.
3. Review the preview and payloads with the user.
4. For WeChat API smoke tests, run `scripts/wechat_api_draft.py draft-from-payload <run-dir>/packs/wechat-article/payload.json --dry-run`.
5. Create real external drafts only after confirmation and connector/account verification.
6. Ask again before public publish/newsletter send.

## Phase 4 — Video Extension

Add `video-post` target adapters only after choosing a video publisher skill and validating login/account flow.

## Operational Checklist

- Confirm target list.
- Confirm mode (`draft` vs `publish`).
- Validate required assets exist.
- Preview platform-specific adaptations.
- Ask for approval before external write.
- Dispatch target-by-target.
- Log result.
