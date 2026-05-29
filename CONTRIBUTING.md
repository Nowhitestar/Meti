# Contributing to Meti

Thanks for considering a contribution. Meti is a small project; we keep the bar high but the friction low.

This doc covers: dev setup, what makes a good change, how to propose a new platform provider, and the test/review expectations before merge.

For the architecture overview, read [`docs/architecture.md`](docs/architecture.md) first.

## Quick start

```bash
# 1. Clone + editable install
git clone https://github.com/Nowhitestar/meti.git
cd meti
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"

# 2. Basic CLI check
.venv/bin/meti --help
```

The editable dev install brings in runtime and test dependencies, including
`pyrage` for the encrypted vault and `tomli_w` for settings writes. Prefer this
venv path over global pip: Homebrew Python can reject global editable installs
with PEP 668 externally-managed-environment errors.

## Verification layers

### Quick

Run focused tests for the area you changed:

```bash
.venv/bin/python -m pytest -q tests/core/test_provider.py
.venv/bin/python -m pytest -q providers/wechat_image/tests/test_provider.py providers/xiaohongshu/tests/test_provider.py
.venv/bin/python -m pytest -q tests/core/test_browser.py tests/integration/test_browser_cli.py
```

### Smoke

Run the no-network local smoke flow with isolated state:

```bash
METI_RUNS_DIR="$(mktemp -d)" XDG_CONFIG_HOME="$(mktemp -d)" .venv/bin/python scripts/test_local.py
```

When changing publish, resume, provider execution, or run artifacts, verify the
schema-v2 `result.json` contract in [docs/run-results.md](docs/run-results.md).
Do not infer resumability from status alone.

### Full

Run the full local gate before opening a PR:

```bash
make PYTHON=.venv/bin/python test
```

This matches the project quality surface in `pyproject.toml`: pytest, Ruff
check, Ruff format check, mypy on `core`, and the no-network smoke script. CI
runs the same style of checks across macOS + Ubuntu × Python 3.10/3.11/3.12.

### Release readiness

Before tagging a release or preparing marketplace submission material, run the
one-command release gate:

```bash
python scripts/check_release.py
# or
make PYTHON=.venv/bin/python release-check
```

The release gate checks version synchronization, plugin and marketplace
metadata, private-path hygiene, built wheel contents, distribution docs, and the
no-network smoke flow. It is draft-safe and account-free by default: it does not
create live platform drafts, open a browser, read real credentials, or submit
marketplace data.

`release.json` is the canonical publication source for versioned releases.
Normal releases are created by CI from `main` after the full test matrix passes.
CI updates Python package metadata, SKILL frontmatter, plugin metadata,
marketplace metadata, artifacts, changelog, tag, and GitHub Release together.

Release selection is intentionally conservative:

- `feat(scope): ...` or `perf(scope): ...` creates a minor release.
- `feat(scope)!: ...` or a `BREAKING CHANGE:` footer creates a major release.
- `release: patch`, `release: minor`, or `release: major` in the commit body
  can force a release when the Conventional Commit type is not enough.
- Routine `fix:`, `docs:`, `test:`, `chore:`, `ci:`, and `refactor:` commits do
  not publish by default.

Use the local dry-run commands only when reviewing or recovering a release:

```bash
python scripts/plan_release.py
python scripts/release.py prepare --version X.Y.Z --dry-run
python scripts/release.py build --dry-run
python scripts/release.py publish --version X.Y.Z --dry-run
```

After reviewing the dry-run output, run the same commands without `--dry-run`.
`publish` prints the target version, tag, artifact paths, `SHA256SUMS`, and
`gh release create` command before confirmation. Use `--yes` only in CI or an
already-reviewed scripted release.

## What kind of changes are most welcome

In rough priority order:

1. **New platform providers** (see "Adding a provider" below) — especially platforms whose drafts are currently a hand-paste chore.
2. **Selector-drift fixes** — when X / Substack / WeChat MP ships a UI change and a browser-flow connector breaks. These are 1-line PRs to a `*_SELECTOR_*` constant.
3. **Locale support** for existing browser-flow providers — current selectors target Chinese UI primarily; English / other-language placeholders go in the same constants list.
4. **Doc improvements** — anything that helps a new contributor get from `git clone` to "first draft created" faster.
5. **Bug fixes with reproductions** — file an issue first if it's non-trivial.

What we're more cautious about:

- New manifest schema fields. The schema is a public contract; additions need to be tagged `schema_version` and migrated.
- Background daemons / long-running processes. Meti is intentionally a one-shot CLI.
- Anything that requires storing platform passwords. Browser-flow is the right answer; we don't manage cookies.

## Adding a provider

Five-method contract — see [`docs/provider-contract.md`](docs/provider-contract.md) for full spec. The fastest path:

```bash
cp -r providers/substack/ providers/<your-platform>/
# Then in providers/<your-platform>/:
#   - rename SubstackProvider → YourPlatformProvider
#   - update name / display_name / media_types / capabilities
#   - rewrite internal/browser_flow.py for the new platform
#   - update rules.py with the platform's content-rules (title length, etc.)
#   - add tests/test_provider.py (mock core.browser.*) and test_browser_flow.py
```

Then add the new provider's name to the `targets` schema enum and to the README's "See it" table.

**Real-account verification is mandatory before merge.** A working unit-test
suite is necessary but not sufficient for new or changed browser-flow
providers. Use [`docs/manual-verification.md`](docs/manual-verification.md) for
the manual, draft-only checklist, and keep private evidence out of git: no raw
draft URLs with tokens, account names, screenshots, private run dirs, or live
platform artifacts in tracked files.

## Commits, PRs, releases

- **Commit messages**: imperative present tense, scope-prefixed when it helps (`feat(substack):`, `fix(wechat-image):`, `docs:`, `refactor(browser):`). CI uses `feat`, `perf`, `!`, `BREAKING CHANGE:`, and `release:*` markers to decide whether to publish a release, so reserve those signals for important user-visible changes.
- **PRs** target `main`. Squash-merge by default. PR description should answer: what, why, how-verified.
- **Tests required** for any code change. New providers ship with both unit tests and a real-account verification note.
- **Releases**: CI publishes `vMAJOR.MINOR.PATCH` from `main` after CI green and `python scripts/check_release.py` passes. The `release.json` bump lands in the CI-created release commit.

### Prefer reinstall

For existing local Claude Code plugin or OpenClaw skill installs, Prefer reinstall
over partial update unless the exact installation layout is known and verified.
Meti supports multiple host layouts, and reinstall reduces stale plugin
metadata, stale `SKILL.md`, and partial local-state drift. Reinstall the code
only; do not delete `~/.config/meti`, `~/.config/meti/credentials.json.age`, or
`~/.config/meti/age-key.txt` unless intentionally rotating credentials.

Host-native update commands such as `git pull` are acceptable only when the
local install path is known, clean, and verified.

For versioned installs, prefer:

```bash
scripts/install.sh --latest --target ~/.openclaw/skills/meti
scripts/install.sh --version vX.Y.Z --target ~/.openclaw/skills/meti --yes
meti update --latest
meti update --version vX.Y.Z
```

`meti update` confirms interactively by default; `--yes` is for CI or reviewed
automation. Normal reinstall/update preserves `~/.config/meti`,
`~/.config/meti/credentials.json.age`, and `~/.config/meti/age-key.txt`.

## Reporting bugs

Open an issue with:

1. What you ran (`meti publish ...`) and the manifest you ran it on (redact tokens).
2. The expected outcome and the actual outcome.
3. Relevant log lines from `runs/<run-id>/publish-log.md` and `result.json`.
4. The platform / browser / OS where it broke. For browser-flow providers, include `meti browser doctor` output.

Don't include cookie values, access tokens, or AppSecrets in issues. The vault and run dirs already redact these for you; double-check before posting.

## Code style

- **Python ≥ 3.10**. Use the type system: `list[str]`, `dict[str, Any]`, `X | None`.
- **Imports**: stdlib → third-party → first-party. Ruff enforces.
- **Errors are typed**: subclass `core.errors.MetiError`. Don't `raise Exception("...")`.
- **Docstrings on public functions**. Triple-quoted, first line is a summary.
- **No comments that just repeat the code**. Comments explain *why*, not *what*.

## Code of Conduct

By participating you agree to abide by [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Be respectful, be patient, ask questions early.

## Licensing

All contributions are accepted under the [MIT License](LICENSE). By opening a PR you agree your contribution is licensed under the same terms.
