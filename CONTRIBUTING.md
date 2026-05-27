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

- **Commit messages**: imperative present tense, scope-prefixed when it helps (`feat(substack):`, `fix(wechat-image):`, `docs:`, `refactor(browser):`). The recent git log is a good style reference.
- **PRs** target `main`. Squash-merge by default. PR description should answer: what, why, how-verified.
- **Tests required** for any code change. New providers ship with both unit tests and a real-account verification note.
- **Releases**: maintainers tag `vMAJOR.MINOR.PATCH` on `main` after CI green; `pyproject.toml` version bump lands in the same PR as the user-visible feature.

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
