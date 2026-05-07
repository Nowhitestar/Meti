# Changelog

All notable changes to Meti are documented here. Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 0.4.0 — 2026-05-07

Project rebrand: `multi-media-publisher` → **Meti**.

Triple etymology: Greek *mētis* (μῆτις, wise counsel), English *meticulous* (draft-first verification), Mandarin *méi-tǐ* (媒体, media). The rebrand cleans up packaging metadata for an open-source release: full PyPI-ready `pyproject.toml`, MIT `LICENSE` file added, Kami-style README, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, GitHub issue / PR templates.

### Changed (breaking)

- CLI command: `mmp` → `meti`
- Project name: `multi-media-publisher` → `meti`
- Config dir: `~/.config/mmp/` → `~/.config/meti/` (auto-migrated on first run, idempotent)
- Env vars: `MMP_VAULT_KEY` → `METI_VAULT_KEY`, `MMP_RUNS_DIR` → `METI_RUNS_DIR` (old names still read with `DeprecationWarning` for one release)
- `result.json` field: `mmp_version` → `meti_version`
- Error class: `MMPError` → `MetiError`

### Added

- `LICENSE` file (MIT)
- `CONTRIBUTING.md` — dev setup, provider authoring guide, real-account verification policy
- `CODE_OF_CONDUCT.md` — Contributor Covenant 2.1
- `.github/ISSUE_TEMPLATE/` (`bug.yml`, `feature.yml`, `config.yml`) and `PULL_REQUEST_TEMPLATE.md`
- Dynamic version source: `core.__version__` reads from `importlib.metadata`, single source of truth shared by `pyproject.toml` and `result.json`

## 0.3.2 — 2026-05-07

`wechat-image` provider rewritten to drive WeChat MP "贴图" (image post, `type=77`) creation programmatically. Previous v0.2 `wechat-image` only emitted a manual-steps Markdown guide; v0.3.2 creates a real draft.

Real-account verified end-to-end against the maintainer's test WeChat OA: two test images, title, and caption all landed in the platform's draft folder.

### Added

- `providers/wechat_image/internal/browser_flow.py` — end-to-end draft creation via OpenCLI Bridge
- `docs/wechat-image-tietu-research.md` — research notes on the editor URL pattern (`?t=media/appmsg_edit_v2&action=edit&isNew=1&type=10&createType=8`) and the save flow
- 13 new unit tests covering URL extraction, payload validation, login redirect, missing token, editor not ready, upload failure, oversize file, and missing source files
- New section in `docs/browser-connectors.md` covering the wechat-image-specific behaviors

## 0.3.1 — 2026-05-06

Browser-flow infrastructure + first two browser-driven providers.

Pivoted away from Playwright (anti-automation defenses on Google OAuth, plus `--remote-debugging-port` setup friction for end users) to the [OpenCLI Bridge](https://github.com/jackwener/opencli) Chrome extension model. Logged-in browser sessions are reused as-is, with no separate Chromium and no debug-port reconfiguration.

Real-account verified end-to-end on both providers against the maintainer's test accounts.

### Added

- `core/browser.py` — wraps the OpenCLI CLI as Python primitives (`open_url`, `get_url`, `click`, `type_text`, `evaluate`, `wait`, `is_connected`, `doctor`)
- `providers/x_article/internal/browser_flow.py` — drives `x.com/compose/articles`
- `providers/substack/internal/browser_flow.py` — drives `<publication>.substack.com/publish/post`
- `meti browser` subcommand: `status`, `doctor`, `login <provider>`
- `docs/browser-connectors.md` — setup guide and architecture notes
- Substack provider: `target.options.publication_url` field (or `SUBSTACK_PUBLICATION_URL` env var) to specify the user's publication subdomain

### Changed

- Removed Playwright dependency from `pyproject.toml`; OpenCLI runs via `npx @jackwener/opencli` so Meti has no Python deps for browser-flow providers
- `mode_actual="draft-platform"` is the new value when a browser-flow provider successfully creates a draft on the platform; `"stub"` remains for the bridge-not-connected fallback path

## 0.3.0 — 2026-05-06

WeChat API proxy support, vault hardening, and `meti resume` for retry-from-failure workflows.

### Added

- `WECHAT_API_PROXY` env var: when set, all WeChat Open Platform API calls are routed through the proxy URL instead of `api.weixin.qq.com` directly. Useful when the user's outbound IP is on a dynamic / split-routing network and can't reliably hit WeChat's IP whitelist. See `docs/wechat-api-proxy.md` for a Cloudflare Worker template
- `meti resume <run-dir>` — re-execute only the failed targets from a previous run, reusing the same prepared payloads
- `core.credentials.VaultIntegrityError` — raised instead of silently regenerating a key when the vault file exists but the key file is missing (would otherwise lock the user out of their own credentials)

### Changed

- Vault writes are now atomic (temp file + `fsync` + `os.replace`) under `fcntl.flock`. Concurrent `set` / `delete` calls no longer race
- `Backend.update(mutator)` exposes a single read-modify-write call that holds the lock for the full operation

## 0.2.0 — 2026-05-06

Major refactor: provider abstraction + dual-host distribution + wizard.

Real-account verified end-to-end: `wechat-article` creates real drafts on `mp.weixin.qq.com`; `xiaohongshu` creates real local drafts via the xhs skill's `draft.sh`. 7 integration bugs were discovered and fixed during verification.

### Added

- `core/` host-agnostic Python: manifest schema, provider registry, credential vault (age-encrypted), run lifecycle, platform rules, settings, wizard fragments
- 5 bundled providers: `wechat-article`, `xiaohongshu`, `wechat-image`, `x-article`, `substack`
- `scripts/meti.py` unified CLI: `validate`, `publish`, `setup`, `list`, `resume`, `doctor`, `wizard`
- `.claude-plugin/plugin.json` for Claude Code plugin marketplace
- 3-stage conversational wizard (source extraction → target selection → manifest assembly) + credential setup wizard
- Manifest schema v0.2: `schema_version`, full-form/short-form targets, `defaults` block, `dry-run` mode, account override per target
- Age-encrypted vault at `~/.config/meti/credentials.json.age`
- GitHub Actions CI matrix (macOS + ubuntu × Python 3.10/3.11/3.12)
- User-facing docs: `architecture.md`, `provider-contract.md`, `credentials.md`, `safety-policy.md`, `manual-verification.md`

### Changed

- Default `mode` is `draft`; `publish` requires explicit confirmation
- Manifest fields normalized; lock-file `manifest.lock.json` written per run
- `runs/<ts>-<slug>/` is now self-contained: manifest, lock, packs, result, log, checkpoints, artifacts
- `mode_actual` introduces `"stub"` value to distinguish connector-not-implemented draft fallbacks (x-article, substack) from real dry-run

### Deprecated

- `scripts/prepare_image_post.py`, `scripts/prepare_longform.py`, `scripts/execute_image_post.py`, `scripts/adapt_content.py`, `scripts/publish_manifest.py`, `scripts/wechat_api_draft.py` — kept as thin shims; removal in v0.3

### Removed

- Legacy `references/*.md` (moved to `docs/` or `providers/<name>/notes.md`)

## 0.1.0 — 2026-05 (pre-redesign)

- Initial OpenClaw skill: prepare/execute scripts, image-post + longform pipelines, WeChat API dry-run helper, local smoke test.
