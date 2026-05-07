<!-- Thanks for the PR. The check-boxes below are the bar — please tick them honestly. -->

## What

<!-- One paragraph: what changes, scoped to the diff. -->

## Why

<!-- One paragraph: the user-visible problem this solves, or the design rationale. Link any related issue. -->

## How verified

<!-- For provider changes: include the draft URL / ID from a real-account run, or a screenshot of the resulting draft. Mocks alone are not enough for browser-flow providers. See docs/manual-verification.md. -->

## Checklist

- [ ] Tests added or updated
- [ ] `python -m pytest -q` passes locally
- [ ] `python -m ruff check . && python -m ruff format --check .` clean
- [ ] `python -m mypy core` clean
- [ ] Docs updated (`README.md`, `docs/`, provider notes) if user-visible behavior changed
- [ ] `CHANGELOG.md` entry added for the next unreleased version
- [ ] No tokens / cookies / AppSecrets in code, fixtures, or commit messages
