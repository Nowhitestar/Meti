# Architecture

This is the user-facing architecture summary. The full design spec lives at
`docs/superpowers/specs/2026-05-05-meti-redesign-design.md`.

## Three layers

```
Shell:       SKILL.md  +  .claude-plugin/plugin.json
              │
              ▼
Core:        core/    (host-agnostic Python)
              │
              ▼
Providers:   providers/<name>/  +  ~/.config/meti/providers/<name>/
```

- **Shell** is what Claude Code or OpenClaw load to know this skill exists.
  It declares triggers and points at `scripts/meti.py`.
- **Core** is `core/manifest.py`, `core/provider.py`, `core/credentials.py`,
  `core/run.py`, `core/rules.py`, `core/host.py`, `core/errors.py`,
  `core/wizard/`, `core/settings.py`. Nothing in core depends on a host.
- **Providers** ship one per platform: `providers/wechat_article/` etc.
  Each declares `provider.yaml` + `provider.py` + `rules.py`.

## Manifest schema (v0.2)

See `docs/provider-contract.md` for full field list and lock-file format.

```yaml
schema_version: "0.2"
type: image-post | longform | video-post
title: "..."
body: "inline or ./path.md"
mode: dry-run | draft | publish
language: zh-CN
defaults:           # optional
  account: default
  options: {}
targets:
  - <provider-name>                    # short form, inherits top mode
  - target: <provider-name>            # full form
    mode: draft
    account: lewis
    options:
      digest: "..."
assets:
  cover: ./cover.png
  images: []
  video: null
tags: []
metadata: {}
```

## Run lifecycle

```
meti publish manifest.yaml
  → load + validate manifest
  → create runs/<ts>-<slug>/ + manifest.lock.json
  → for each target:
       provider.validate (lint platform rules)
       provider.prepare  (write packs/<target>/)
       provider.execute  (dry-run | draft | publish)
       record TARGET_DONE in publish-log.md
       checkpoint after key steps
  → finalize: write result.json
```

## Why this shape

- One manifest, many providers — adding a platform is one directory, not six edits.
- Core is host-agnostic — same code works in Claude Code, OpenClaw, or `python3 meti.py`.
- draft-first — capabilities default to draft only; publish requires explicit opt-in.
- Vault is shared across hosts — `~/.config/meti/` is a single source of truth.
