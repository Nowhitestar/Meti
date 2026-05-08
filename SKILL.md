---
name: Multi-media Publisher
description: This skill should be used when the user asks to "多媒体发布", "多平台发布", "同步发布小红书和微信图文", "发微信图文和小红书", "发布长文章到公众号/X/Substack", "cross-post", "publish everywhere", or wants one content package adapted and published/drafted across Xiaohongshu, WeChat image posts, WeChat Official Account articles, X Articles/Twitter, Substack, or future video platforms; or "新发布", "帮我发一组到", "wizard", "guide me to publish".
version: 0.2.0
---

# Multi-media Publisher / 多媒体发布

Cross-platform content publishing orchestration. Routes one source content
package to multiple platform providers via a unified manifest, draft-first
safety policy, and per-platform rules.

## When to use

- User wants to publish/draft the same content across multiple platforms
- User wants to add a new platform/provider
- User needs to validate a manifest, set up credentials, or inspect runs

## Entry point

All operations go through `scripts/meti.py`:

```bash
python3 scripts/meti.py <subcommand> [args]
```

Subcommands:

- `validate <manifest.yaml>` — validate without executing
- `publish <manifest.yaml> [--mode-override ...]` — prepare + execute
- `setup <provider> [--account NAME]` — configure credentials
- `list providers|accounts|runs` — inspect state
- `resume <run-dir> [--target NAME]` — recover failed run
- `doctor` — self-check
- `wizard [--type ... --targets ...]` — conversational manifest builder

## Default mode = draft

Every run defaults to `mode: draft`. Public publishing requires explicit
top-level `mode: publish` AND a second confirmation in conversation.

## Wizard Mode

When the user says "新发布", "帮我发一组到 X / Y", "publish to ...", "cross-post",
or pastes content with publishing intent, run the **3-stage wizard** instead of
asking them to write a manifest:

1. **Stage 1 — Source Extraction**: read `core/wizard/source_extraction.md` and
   follow the instructions there. Extract `type`, `title`, `body`, `cover`,
   `images`, `tags`, `cta` into your conversation memory. Don't write files yet.

2. **Stage 2 — Target Selection**: read `core/wizard/target_selection.md`. Run
   `python3 scripts/meti.py wizard --dump-context --type <T>` to fetch available
   providers + credential status + accounts. Ask which targets, modes, accounts.

3. **Stage 3 — Manifest Assembly**: read `core/wizard/manifest_assembly.md`.
   Render YAML, write to a temp file, validate via `python3 scripts/meti.py validate`,
   show the user, get approval. On approve, run `python3 scripts/meti.py wizard --commit <path>`.

For setup credentials flows ("配置凭证", "setup wechat-article account"), read
`core/wizard/credential_setup.md`. Direct the user to run `meti setup <provider>`
locally — never ask them to paste a secret into chat unless they insist.

## Public-publish Gate

If a wizard run would result in `mode: publish` for any target, ALWAYS:

1. Show the rendered manifest first.
2. Ask "Confirm public publish? (yes/no)".
3. Proceed only on exact match `yes`. Anything else → downgrade to `draft`.

This rule overrides any earlier user permission. Each public publish is a fresh
ask in the active conversation.

## v0.2 supported providers

| Provider | Media | Mode support | Notes |
|---|---|---|---|
| `wechat-article` | longform | dry-run, draft | Real WeChat OA API; needs AppID/AppSecret |
| `xiaohongshu` | image-post (video planned) | dry-run, draft (local) | Uses xiaohongshu skill's `draft.sh` |
| `wechat-image` | image-post | dry-run, draft (browser-flow guide) | UI calibration TODO; guide-only path |
| `x-article` | longform | dry-run, draft (payload + TODO) | No connector yet; manual paste step |
| `x-thread` | thread | dry-run, draft (browser-flow, fills modal) | Stops before "Post all"; user reviews + ships |
| `substack` | longform | dry-run, draft (payload + TODO) | No connector yet; manual paste step |

## Safety rules

1. Never publish publicly without explicit confirmation
2. Never bypass login, CAPTCHA, platform review, or anti-abuse safeguards
3. Treat all credentials as secrets; never print them
4. If browser automation reaches an ambiguous screen, stop and ask
5. Read `docs/safety-policy.md` (was `references/publishing-policy.md`)

## Architecture

See `docs/architecture.md` for the full overview. In short:

- **Shell**: this SKILL.md + `.claude-plugin/plugin.json`
- **Core**: `core/` — host-agnostic Python (manifest, provider registry, vault, run lifecycle)
- **Providers**: `providers/<name>/` (bundled) + `~/.config/meti/providers/<name>/` (user)

## Quickstart

```bash
# 1. Validate
python3 scripts/meti.py validate examples/longform.yaml

# 2. Configure WeChat credentials
python3 scripts/meti.py setup wechat-article

# 3. Dry-run
python3 scripts/meti.py publish examples/longform.yaml --mode-override dry-run

# 4. Inspect runs
python3 scripts/meti.py list runs
```

## Bundled resources

- `core/` — manifest, provider, credentials, run, rules, host, errors
- `providers/<name>/` — first-party providers (wechat-article, wechat-image, xiaohongshu, x-article, substack)
- `examples/longform.yaml` — sample manifest
- `docs/architecture.md` — high-level architecture overview
- `docs/provider-contract.md` — how to author a new provider
- `docs/safety-policy.md` — draft-first / publishing safeguards
- `docs/browser-connectors.md` — OpenCLI Bridge setup for browser-flow providers
