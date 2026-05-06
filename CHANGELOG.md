# Changelog

## 0.2.0 — 2026-05-06

Major refactor: provider abstraction + dual-host distribution + wizard.

Real-account verified end-to-end: `wechat-article` creates real drafts
on `mp.weixin.qq.com`; `xiaohongshu` creates real local drafts via the
xhs skill's `draft.sh`. 7 integration bugs discovered + fixed during
verification. See `docs/HANDOFF.md` "Discovered during real-account
verification" for the full list.

### Added

- `core/` host-agnostic Python: manifest schema, provider registry,
  credential vault (age-encrypted), run lifecycle, platform rules, settings,
  wizard fragments
- 5 bundled providers: `wechat-article`, `xiaohongshu`, `wechat-image`,
  `x-article`, `substack`
- `scripts/mmp.py` unified CLI: `validate`, `publish`, `setup`, `list`,
  `resume`, `doctor`, `wizard`
- `.claude-plugin/plugin.json` for Claude Code plugin marketplace
- 3-stage conversational wizard (source extraction → target selection →
  manifest assembly) + credential setup wizard
- Manifest schema v0.2: `schema_version`, full-form/short-form targets,
  `defaults` block, `dry-run` mode, account override per target
- Age-encrypted vault at `~/.config/mmp/credentials.json.age`
- GitHub Actions CI matrix (macOS + ubuntu × Python 3.10/3.11/3.12)
- User-facing docs: `architecture.md`, `provider-contract.md`,
  `credentials.md`, `safety-policy.md`, `manual-verification.md`

### Changed

- Default `mode` is `draft`; `publish` requires explicit confirmation
- Manifest fields normalized; lock-file `manifest.lock.json` written per run
- `runs/<ts>-<slug>/` is now self-contained: manifest, lock, packs, result,
  log, checkpoints, artifacts
- `mode_actual` introduces `"stub"` value to distinguish connector-not-implemented
  draft fallbacks (x-article, substack) from real dry-run

### Deprecated

- `scripts/prepare_image_post.py`, `scripts/prepare_longform.py`,
  `scripts/execute_image_post.py`, `scripts/adapt_content.py`,
  `scripts/publish_manifest.py`, `scripts/wechat_api_draft.py` — kept as
  thin shims; removal in v0.3

### Removed

- Legacy `references/*.md` (moved to `docs/` or `providers/<name>/notes.md`)

## 0.1.0 — 2026-05 (pre-redesign)

- Initial OpenClaw skill: prepare/execute scripts, image-post + longform
  pipelines, WeChat API dry-run helper, local smoke test.
