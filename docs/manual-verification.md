# Manual Verification Checklist

Real account testing is **not** in CI. Run these locally before tagging a
release.

## wechat-article

Prerequisites:
- WeChat Official Account with API access enabled
- IP whitelist includes your test machine
- AppID + AppSecret available

Steps:

```bash
mmp setup wechat-article
# Enter WECHAT_APP_ID and WECHAT_APP_SECRET when prompted
mmp doctor
# Expect: providers >= 5; accounts: wechat-article:default
mmp publish examples/longform.yaml --mode-override dry-run
# Expect: RUN_DIR <path>; result.json status=ok mode_actual=dry-run
mmp publish examples/longform.yaml --mode-override draft
# Expect: status=ok, mode_actual=draft-platform, external_id is a draft media_id
# Verify: log into mp.weixin.qq.com → 草稿箱 → see the new draft
```

Cleanup: delete the draft from the WeChat console.

## xiaohongshu

Prerequisites:
- xiaohongshu skill installed locally with `xhs-login` cookie captured
- `XHS_COOKIE_PATH` set in vault to that cookie file

```bash
mmp setup xiaohongshu
mmp publish examples/image-post.yaml --mode-override dry-run
mmp publish examples/image-post.yaml --mode-override draft
# Expect: result.json mode_actual=draft-local
# Verify: <draft_path> file exists and contains the payload
```

## wechat-image

```bash
mmp publish examples/image-post.yaml --mode-override draft
# Expect: <run-dir>/packs/wechat-image/browser-flow.md exists
# Verify: open the guide manually, confirm steps are accurate
```

## x-article

```bash
mmp publish examples/longform.yaml --mode-override draft
# Expect: result.json connector_status=not-implemented
# Manually follow the TODO-connector.md to create a draft
# Verify: x.com/i/articles → drafts shows the new entry
```

## substack

Same pattern as x-article.

## Cross-host check

Verify the same vault works from both hosts:

```bash
# In Claude Code:
python3 scripts/mmp.py list accounts
# In OpenClaw:
python3 scripts/mmp.py list accounts
# Both should show identical accounts.
```

## Sign-off

Tag a release only when:
- [ ] wechat-article real-draft round-trip green
- [ ] xiaohongshu local-draft round-trip green
- [ ] wechat-image guide is accurate
- [ ] x-article + substack TODO docs accurate
- [ ] Cross-host vault read consistent
