# meti

Publish one piece of content to many platforms — 小红书, 微信图文, 微信公众号
文章, X Articles, Substack — through one manifest, with draft-first safety
and an encrypted credential vault.

Works as a Claude Code plugin **and** an OpenClaw skill from the same source.

## Status

**v0.3.2** — five first-party providers, all real-account verified:

| Provider | What it drafts | How |
|---|---|---|
| `wechat-article` | 微信公众号 图文 | Open Platform API (`material/add_material` + `draft/add`) |
| `xiaohongshu` | 小红书 笔记草稿 | Local `draft.sh` writes JSON → user finalizes in XHS app |
| `x-article` | X (Twitter) Articles | OpenCLI Browser Bridge → real Chrome (Premium req'd) |
| `substack` | Substack post draft | OpenCLI Browser Bridge → real Chrome |
| `wechat-image` | 微信公众号 贴图 | OpenCLI Browser Bridge → real Chrome |

OpenCLI-backed providers reuse your real Chrome session (no separate
login, no anti-bot detection). See
[`docs/browser-connectors.md`](docs/browser-connectors.md) for setup.

Full design spec: [`docs/HANDOFF.md`](docs/HANDOFF.md).

## Install

### As a Claude Code plugin

(Marketplace submission pending — for now, clone the repo and point Claude
Code at the directory.)

```bash
git clone https://github.com/yxliao-lewis/meti.git
# Then in Claude Code: settings → plugins → load from directory
```

After v0.2.0 marketplace submission lands, the install will be:

```
/plugin install meti
```

### As an OpenClaw skill

Clone into your skills directory:

```bash
git clone https://github.com/yxliao-lewis/meti.git \
  ~/.openclaw/skills/meti
```

### Python deps

```bash
pip install -e ".[dev]"
```

Requires Python 3.10+.

## Quickstart

### Conversational wizard (recommended)

In Claude Code or OpenClaw, just say what you want:

> 帮我把这篇文章发到公众号、X 长文章、Substack 草稿。

Claude reads `core/wizard/*.md` and walks you through source extraction →
target selection → manifest assembly → draft.

### CLI

```bash
# Validate a manifest
meti validate examples/longform.yaml

# Configure credentials for a provider
meti setup wechat-article

# Run a publish (defaults to draft mode in the manifest)
meti publish examples/longform.yaml

# List providers / accounts / runs
meti list providers
meti list accounts
meti list runs

# Self-check
meti doctor
```

## Safety

- Default `mode: draft`. Public publishing requires explicit `mode: publish`
  in the manifest **plus** an in-conversation confirmation.
- Credentials are stored in `~/.config/meti/credentials.json.age` (age-encrypted).
- Secrets never appear in `result.json`, `publish-log.md`, or printed output.
- Full policy: [`docs/safety-policy.md`](docs/safety-policy.md).

## Architecture

- [`docs/architecture.md`](docs/architecture.md) — high-level overview
- [`docs/provider-contract.md`](docs/provider-contract.md) — write your own provider
- [`docs/credentials.md`](docs/credentials.md) — vault and ENV usage
- [`docs/manual-verification.md`](docs/manual-verification.md) — pre-release checklist
- [`docs/superpowers/specs/`](docs/superpowers/specs/) — full design spec

## Project layout

```
core/                    # host-agnostic Python (manifest, providers, vault, runs)
providers/               # bundled first-party providers
  wechat_article/
  xiaohongshu/
  wechat_image/
  x_article/
  substack/
scripts/meti.py           # CLI entry
.claude-plugin/          # Claude Code plugin manifest
SKILL.md                 # OpenClaw + Claude Code skill manifest
docs/                    # user-facing docs
tests/                   # core tests + integration tests
```

## Contributing

- New provider? Read [`docs/provider-contract.md`](docs/provider-contract.md).
- Bug or design discussion? Open an issue.

## License

MIT.
