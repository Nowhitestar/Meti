# Wizard Stage 2 — Target Selection

You have a draft from Stage 1. Now choose where to publish.

## Goal of this stage

Produce a list of `Target` entries:

```json
[
  {"target": "wechat-article", "mode": "draft", "account": "default", "options": {}},
  {"target": "x-article", "mode": "draft", "account": "lewis", "options": {}}
]
```

## How to behave

1. **Get available providers**: run

   ```bash
   python3 scripts/meti.py wizard --dump-context --type <draft.type>
   ```

   The output is JSON with `providers`, `accounts`, `settings`. Provider entries
   include `source`, `trusted`, `trust_status`, and `overrides_bundled`.

2. **Filter to compatible providers**: media_types must include the draft's `type`.

3. **Show the list** to the user with status markers. Do not present
   `trust_status: untrusted` providers as selectable targets; show the trust
   command instead.

   ```
   Available targets for <type>:
     ✓ wechat-article    (bundled, creds: ok)       — 微信公众号文章
     ✗ xiaohongshu       (bundled, creds: missing)  — 小红书图文 [run `meti setup xiaohongshu` first]
     ✓ x-article         (bundled, creds: ok)       — X Articles
     ! local-demo        (user, untrusted)           — run `meti providers trust local-demo`
   ```

4. **Ask which targets to use** as a multi-pick (e.g. "1, 3" or names).

5. **For each chosen target**, ask:
   - **Mode**: `draft` (default) or `publish` (warn that publish requires confirmation in Stage 3) or `dry-run`.
   - **Account**: if multiple accounts exist for that provider, list them. Otherwise default to `default`.
   - **Platform-specific options** (only when relevant):
     - For `wechat-article`: ask if the user wants a custom `digest` (max 120 chars) or to reuse `summary`.
     - For `x-article`: ask if they want a different title for X (X Articles often need a hookier title).
     - For `xiaohongshu`: ask about hashtags / hook. Title max 20 chars.
     - For `substack`: ask about subtitle / paid-tier flag.

6. Do NOT proceed if a chosen target has `trust_status: untrusted` or
   `credential_status: missing`. For untrusted providers, tell the user which
   `meti providers trust <provider>` command enables it. For missing
   credentials, tell the user which `meti setup <provider>` command to run.
   Either wait for them to do it (then re-run `--dump-context`) or drop that target.

## When to advance

Once you have at least one target with mode and account, say:

> Targets locked in. Moving to manifest assembly.

Proceed to `core/wizard/manifest_assembly.md`.

## What NOT to do

- Don't pick targets the user didn't ask for.
- Don't silently downgrade `publish` to `draft` — flag it explicitly.
- Don't ask about platforms not in the registry.
