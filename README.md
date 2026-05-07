<div align="center">
  <h1>Meti</h1>
  <p><b>One manifest, every Chinese-platform you publish to.</b></p>
  <a href="https://github.com/Nowhitestar/meti/stargazers"><img src="https://img.shields.io/github/stars/Nowhitestar/meti?style=flat-square" alt="Stars"></a>
  <a href="https://github.com/Nowhitestar/meti/releases"><img src="https://img.shields.io/github/v/tag/Nowhitestar/meti?label=version&style=flat-square" alt="Version"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square" alt="License"></a>
  <a href="https://github.com/Nowhitestar/meti/actions"><img src="https://img.shields.io/github/actions/workflow/status/Nowhitestar/meti/ci.yml?branch=main&style=flat-square" alt="CI"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10+-blue?style=flat-square" alt="Python 3.10+"></a>
</div>

## Why

Meti (μῆτις, *mētis* — Greek for "wise counsel"; *meticulous* in English; 媒体 *méi-tǐ* — "media" in Mandarin). Three readings, one idea: **publishing should be careful, deliberate, and reproducible — not a tab-juggling marathon.**

Writers who care about more than one Chinese-platform audience face the same chore: open WeChat OA, paste, save draft. Open Xiaohongshu, paste, save draft. Open X, paste, save. Open Substack, paste, save. Each platform forgets what the other knows. Each tab is a place a typo can hide. Each retry costs the same five minutes.

Meti collapses that into **one YAML manifest → drafts on every platform**, with an explicit safety model:

- **Draft-first by default.** Public publishing requires explicit opt-in *plus* an in-conversation confirmation. Mistakes stop at the draft folder.
- **Cookies stay in your real Chrome.** No CDP debug-port dance, no fresh-Chromium anti-bot battle. Browser-flow providers drive your existing logged-in session via the [OpenCLI Bridge](https://github.com/jackwener/opencli) extension.
- **Credentials are encrypted at rest.** `age`-encrypted vault at `~/.config/meti/credentials.json.age`. Secrets never appear in run artifacts.
- **Every run is reproducible.** A self-contained run dir captures the locked manifest, payloads, checkpoints, log, and result. Resume from any failure point with `meti resume <run-dir>`.

Works as a [Claude Code](https://claude.com/claude-code) plugin **and** as an [OpenClaw](https://openclaw.com) skill from the same source — say what you want in natural language, and the wizard walks you through source extraction → target selection → manifest assembly → draft.

## See it

| Provider | Drafts to | How it gets there |
|---|---|---|
| `wechat-article` | 公众号 图文 (article) | WeChat Open Platform API — `material/add_material` + `draft/add` |
| `wechat-image` | 公众号 贴图 (image post) | OpenCLI Bridge → real Chrome → `DataTransfer` injection |
| `xiaohongshu` | 小红书 草稿 (note) | Local `draft.sh` → JSON file → finalize in XHS app |
| `x-article` | X Articles (Premium) | OpenCLI Bridge → real Chrome |
| `substack` | Substack post draft | OpenCLI Bridge → real Chrome |

All five are real-account verified. See [docs/browser-connectors.md](docs/browser-connectors.md) for the OpenCLI-backed three.

## Install

**As a Claude Code plugin** (recommended)

```bash
git clone https://github.com/Nowhitestar/meti.git
# Claude Code: settings → plugins → load from directory
```

The Claude Code marketplace submission is pending; once landed the install becomes:

```
/plugin install meti
```

**As an OpenClaw skill**

```bash
git clone https://github.com/Nowhitestar/meti.git ~/.openclaw/skills/meti
```

**Direct CLI** (Python ≥ 3.10)

```bash
pip install -e ".[dev]"
meti --help
```

**Optional: OpenCLI Bridge** for `x-article` / `substack` / `wechat-image`. One-time setup:

```bash
brew install node            # or apt install nodejs npm — needs Node ≥ 21
# Install Chrome extension: https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk
meti browser status          # → OK Browser Bridge connected
```

Full setup: [docs/browser-connectors.md](docs/browser-connectors.md).

## Quickstart

**The conversational wizard** (in Claude Code or OpenClaw):

> 帮我把这篇文章发到公众号、X 长文、Substack 草稿。

The wizard reads `core/wizard/*.md` and walks you through extraction, target selection, manifest assembly, and draft execution — no manifest YAML to hand-write.

**The CLI** (when you already have a manifest):

```bash
# Validate without executing
meti validate examples/longform.yaml

# Configure credentials for a provider
meti setup wechat-article

# Publish (defaults to draft mode in the manifest)
meti publish examples/longform.yaml

# Resume from where the last run failed
meti resume runs/20260507-001255-mmp

# Inspect state
meti list providers
meti list accounts
meti list runs
meti doctor
```

A minimal manifest:

```yaml
schema_version: "0.2"
type: longform
title: "AI for the rest of us"
body: ./article.md
mode: draft
language: zh-CN
targets:
  - wechat-article
  - x-article
  - substack
assets:
  cover: ./cover.png
tags: [ai, essay]
```

## Design

**One language, every constraint encoded.** Meti's manifest is a YAML version of "what should land on every platform" — title length caps, tag count limits, image-format constraints all live in `providers/*/rules.py` and run before any network call. A 64-character WeChat title and a 280-character XHS title are both rejected at validate-time, not at the platform.

**Provider abstraction is small on purpose.** Five methods (`validate`, `prepare`, `execute`, `health_check`, plus a registration block). New platforms drop into `providers/<name>/` and are picked up automatically. See [docs/provider-contract.md](docs/provider-contract.md).

**Two execute paths per platform:**

| Path | When | Trade-off |
|---|---|---|
| **API** (`wechat-article`) | Platform exposes a draft API + you have AppID/Secret | Fast, scriptable, no Chrome dependency |
| **Browser-flow** (`wechat-image`, `x-article`, `substack`) | No API exists, OR API can't create the post type | Reuses real Chrome session, no anti-bot detection, breaks when platform UI drifts (selectors are constants at the top of each `internal/browser_flow.py`) |

**Safety is a property of the design, not a runtime check.** `mode: draft` is the default for every provider. `mode: publish` requires both manifest opt-in *and* an in-conversation `--confirm-publish` flag. Vault writes are atomic (tmp + fsync + os.replace) under flock — no concurrent-write data loss. Run dirs are append-only — `result.json` is written once, at the end.

Full architecture: [docs/architecture.md](docs/architecture.md). Safety policy: [docs/safety-policy.md](docs/safety-policy.md). Browser connector internals: [docs/browser-connectors.md](docs/browser-connectors.md).

## Project layout

```
core/                  # host-agnostic Python (manifest, providers, vault, runs)
providers/             # bundled first-party providers
  wechat_article/      # API
  wechat_image/        # OpenCLI Bridge (贴图)
  xiaohongshu/         # local draft.sh
  x_article/           # OpenCLI Bridge
  substack/            # OpenCLI Bridge
scripts/meti.py        # CLI entry
.claude-plugin/        # Claude Code plugin manifest
SKILL.md               # OpenClaw + Claude Code skill manifest
docs/                  # user-facing docs
tests/                 # 142 unit + integration tests
```

## Roadmap

- ✅ **v0.2** — Provider abstraction + dual-host distribution + wizard + age-encrypted vault
- ✅ **v0.3** — WeChat API proxy (split-routing IP whitelist) + vault hardening + `meti resume`
- ✅ **v0.3.1** — `x-article` + `substack` connectors via OpenCLI Bridge
- ✅ **v0.3.2** — `wechat-image` (贴图) connector — solves the local-file-upload + `fingerprint` reverse-engineering problem
- ✅ **v0.4** — Rebrand to Meti
- ⏳ **v0.4.x** — `wechat-channel` (视频号) connector
- ⏳ **v0.5** — Multi-account routing (`target.account: <name>`) + per-provider session-expiry detection
- ⏳ **v1.0** — Public marketplace listings (Claude Code plugin store, OpenClaw)

## Contributing

Bug reports, feature requests, and provider PRs are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the dev environment, test conventions, and provider authoring guide.

The fastest way to add a new platform: copy [`providers/substack/`](providers/substack/) (smallest browser-flow provider), update the URL pattern + selectors, register in the manifest schema. Real-account verification is mandatory before merge — see [docs/manual-verification.md](docs/manual-verification.md).

## License

[MIT](LICENSE) © 2026 Lewis Liao
