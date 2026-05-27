# Manual Verification Checklist

Real-account testing is **not** in CI and is never part of default pytest.
Automated tests use mocks and fixtures only; live checks are manual,
draft-only, and stop before final public publish controls.

## Privacy checklist

Do not commit or paste into tracked files:

- private screenshots
- raw draft URLs with tokens or sensitive query strings
- account names or account identifiers
- private run directories
- raw live platform artifacts

Record only sanitized outcomes, such as "draft visible in platform draft
folder" and redacted IDs when needed.

## Run result inspection

After every live `meti publish` or `meti resume` check, inspect
`runs/<run-id>/result.json` using the schema-v2 contract in
[`docs/run-results.md`](run-results.md):

- top-level `status`
- top-level `next_action`
- top-level `resume_targets`
- top-level `review_targets`
- each target's `status`, `mode_actual`, and `next_action`
- safe `external_id` or `draft_url` evidence when available
- redaction of sensitive query values as `[REDACTED]`

Do not use terminal output alone as sign-off evidence. Use `publish-log.md` only
for event-order diagnostics.

## Shared setup

For browser-flow providers, verify the OpenCLI Bridge before live checks:

```bash
meti browser status
meti browser doctor
```

If a provider session is expired, open the login page in your real Chrome:

```bash
meti browser login wechat-image
meti browser login xiaohongshu
meti browser login x-article
meti browser login x-thread
meti browser login substack
```

## wechat-article

Prerequisites:
- WeChat Official Account with API access enabled
- IP whitelist includes your test machine
- AppID + AppSecret available

Steps:

```bash
meti setup wechat-article
# Enter WECHAT_APP_ID and WECHAT_APP_SECRET when prompted
meti doctor
# Expect: providers >= 6; accounts: wechat-article:default
meti publish examples/longform.yaml --mode-override dry-run
# Expect: RUN_DIR <path>; result.json status=ok mode_actual=dry-run
meti publish examples/longform.yaml --mode-override draft
# Expect: status=ok, mode_actual=draft-platform, external_id is a draft media_id
# Verify: log into mp.weixin.qq.com → 草稿箱 → see the new draft
```

Cleanup: delete the draft from the WeChat console.

## xiaohongshu

Prerequisites:
- Chrome is logged in to Xiaohongshu Creator Studio
- OpenCLI Bridge reports ready

```bash
meti browser status
meti browser login xiaohongshu
meti publish examples/image-post.yaml --mode-override dry-run
meti publish examples/image-post.yaml --mode-override draft
# Expect: result.json mode_actual=draft-platform or a recoverable browser-flow failure
# Verify manually: Creator Studio 草稿箱 shows the draft, then delete it
```

## wechat-image

Prerequisites:
- Chrome is logged in to mp.weixin.qq.com
- OpenCLI Bridge reports ready

```bash
meti browser status
meti browser login wechat-image
meti publish examples/image-post.yaml --mode-override draft
# Expect: result.json mode_actual=draft-platform with safe draft evidence
# Verify manually: mp.weixin.qq.com 草稿箱 shows the 贴图 draft, then delete it
```

## x-article

Prerequisites:
- Chrome is logged in to X
- The account can use X Articles

```bash
meti browser status
meti browser login x-article
meti publish examples/longform.yaml --mode-override draft
# Expect: result.json mode_actual=draft-platform with safe article draft evidence
# Verify manually: x.com/i/articles shows the draft, then delete it
```

## x-thread

Prerequisites:
- Chrome is logged in to X

```bash
meti browser status
meti browser login x-thread
meti publish examples/thread.yaml --mode-override draft
# Expect: composer is filled and Meti stops before Post all
# Verify manually: review the composer, then discard it without posting
```

## substack

Prerequisites:
- Chrome is logged in to Substack
- Manifest target options include `publication_url`, or `SUBSTACK_PUBLICATION_URL` is set

```bash
meti browser status
meti browser login substack
meti publish examples/longform.yaml --mode-override draft
# Expect: result.json mode_actual=draft-platform with safe draft evidence, or a clear publication URL configuration error
# Verify manually: Substack publication dashboard shows the draft, then delete it
```

## Cross-host check

Verify the same vault works from both hosts:

```bash
# In Claude Code:
python3 scripts/meti.py list accounts
# In OpenClaw:
python3 scripts/meti.py list accounts
# Both should show identical accounts.
```

## Sign-off

Tag a release only when:
- [ ] wechat-article real-draft round-trip green
- [ ] xiaohongshu browser-flow draft round-trip green
- [ ] wechat-image browser-flow draft round-trip green
- [ ] x-article browser-flow draft round-trip green
- [ ] x-thread composer draft/review flow stops before public posting
- [ ] substack browser-flow draft round-trip green
- [ ] Cross-host vault read consistent
