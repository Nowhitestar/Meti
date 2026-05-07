# Contributing to Meti

Thanks for considering a contribution. Meti is a small project; we keep the bar high but the friction low.

This doc covers: dev setup, what makes a good change, how to propose a new platform provider, and the test/review expectations before merge.

For the architecture overview, read [`docs/architecture.md`](docs/architecture.md) first.

## Quick start

```bash
# 1. Clone + editable install
git clone https://github.com/Nowhitestar/meti.git
cd meti
pip install -e ".[dev]"

# 2. Smoke test (no network, no platform side effects)
meti --help
python -m pytest -q
python -m ruff check . && python -m ruff format --check .
python -m mypy core
```

All four commands must pass before opening a PR. CI runs the same matrix across macOS + Ubuntu × Python 3.10/3.11/3.12.

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

**Real-account verification is mandatory before merge.** A working unit-test suite is necessary but not sufficient — at least one PR comment must show:

- The actual draft URL / ID returned by your provider on a real run
- A screenshot of the resulting draft in the platform's draft folder

This catches the things mocks can't: cookie expiry, platform automation flags, content-rule edge cases, network races. See [`docs/manual-verification.md`](docs/manual-verification.md) for the checklist we run before tagging releases.

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
