# Marketplace Submission

This packet prepares Meti for Claude Code marketplace review. It is not an
external submission record. Any actual marketplace submission through accounts,
browser UI, or irreversible platform actions requires separate explicit
confirmation from the maintainer.

## Short description

One manifest to create draft-safe content across WeChat OA, WeChat image posts,
Xiaohongshu, X Articles, X Threads, and Substack.

## Long description

Meti is a manifest-driven publishing assistant for writers who need the same
content staged across multiple platforms without tab juggling or accidental
public posting. A YAML manifest defines the source content, assets, tags, mode,
and target providers. Meti validates platform constraints, prepares per-target
payloads, creates draft artifacts, and records a reproducible run directory with
`result.json`, `publish-log.md`, payload packs, and checkpoints.

The project is draft-first. Bundled providers default to draft or dry-run
behavior, and browser-flow providers reuse the user's real Chrome session
through OpenCLI Bridge instead of storing raw cookies. Credentials for API
providers live in an age-encrypted local vault.

## Category

Publishing

## Tags and Keywords

- publishing
- wechat
- xiaohongshu
- substack
- x-articles
- x-threads
- draft-first
- manifest-driven
- claude-code
- openclaw

## Installation

Current Claude Code local plugin path:

```bash
git clone https://github.com/Nowhitestar/meti.git
```

Then load the cloned directory from Claude Code settings.

Future marketplace path after listing approval:

```text
/plugin install meti
```

OpenClaw skill path:

```bash
git clone https://github.com/Nowhitestar/meti.git ~/.openclaw/skills/meti
```

Direct CLI path:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/meti --help
```

## Privacy

- Browser-flow providers do not capture raw cookies.
- Browser-flow providers reuse the user's real Chrome login session through
  OpenCLI Bridge.
- API credentials are stored in the local age-encrypted credential vault at
  `~/.config/meti/credentials.json.age`.
- Run artifacts redact sensitive token-bearing URL query values.
- Do not track private screenshots, account names, raw token-bearing draft URLs,
  private run dirs, or live platform artifacts.

## Safety

- Meti is draft-first by default.
- Public publishing requires explicit manifest intent and active confirmation.
- The release gate does not create live platform drafts, open a browser, read
  real credentials, submit marketplace data, or publish anything publicly.
- If a marketplace submission requires account access, browser UI, or an
  irreversible action, stop and ask for explicit confirmation before proceeding.

## Verification

Before submission:

```bash
python scripts/check_release.py
make PYTHON=.venv/bin/python test
```

Manual live-account checks belong in `docs/manual-verification.md`. They must
remain draft-only and must not commit private evidence.

## Screenshot and Demo Asset Checklist

- Show the Meti wizard or CLI creating a draft-safe manifest.
- Show provider selection without account names or private platform history.
- Show sanitized `result.json` fields such as `status`, `next_action`,
  `resume_targets`, and `review_targets`.
- Do not include raw draft URLs with tokens.
- Do not include private screenshots from live accounts.
- Do not include local `runs/` directories or `.planning/` artifacts.
