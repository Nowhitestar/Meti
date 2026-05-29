# Distribution

Meti ships from one source tree as a Python CLI, a Claude Code local plugin, a
future Claude Code marketplace plugin, and an OpenClaw skill. Keep these paths
explicit so users know what is available today and what is pending marketplace
review.

## Current install paths

### Claude Code local plugin

```bash
git clone https://github.com/Nowhitestar/meti.git
```

Then open Claude Code settings and load the cloned directory as a local plugin.

### Claude Code marketplace

Claude Code marketplace submission is pending. After Meti is listed, the
marketplace install command will be:

```text
/plugin install meti
```

Do not present this as currently available until the listing is live.

### OpenClaw skill

```bash
git clone https://github.com/Nowhitestar/meti.git ~/.openclaw/skills/meti
```

After installing, ask OpenClaw for the multi-media publisher skill or invoke the
wizard flow described in `SKILL.md`.

### Direct CLI

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/meti --help
```

Use a virtualenv by default. It keeps runtime dependencies such as `pyrage` and
`tomli_w` isolated from system Python package-management rules.

## Versioned release install

Versioned installs use GitHub Release artifacts. Default updates target the
latest stable release; use `--version vX.Y.Z` for pinning, rollback, or a
controlled rollout.

```bash
# latest stable
scripts/install.sh --latest --target ~/.openclaw/skills/meti

# explicit version
scripts/install.sh --version vX.Y.Z --target ~/.openclaw/skills/meti --yes
```

The installer downloads the versioned release asset, `release.json`, and
`SHA256SUMS` from GitHub Releases, verifies the selected artifact checksum, and
replaces only the install target files. It does not delete `~/.config/meti`,
`~/.config/meti/credentials.json.age`, or `~/.config/meti/age-key.txt`.

Existing installs can use the CLI wrapper:

```bash
meti update --latest
meti update --version vX.Y.Z
meti update --version vX.Y.Z --yes
```

Without `--yes`, `meti update` prints the current version, target version,
install path, planned `scripts/install.sh` command, and preserved config paths
before asking for confirmation.

## Prefer reinstall

For existing Claude Code plugin or OpenClaw skill installs, Prefer reinstall
over partial update unless the installation layout is known and verified. Meti
supports multiple host layouts, and reinstall reduces stale plugin metadata,
stale `SKILL.md`, and partial local-state drift.

Safe reinstall means replacing the source checkout or skill/plugin directory.
Do not delete `~/.config/meti`, `~/.config/meti/credentials.json.age`, or
`~/.config/meti/age-key.txt` during a normal reinstall. Those files hold local
settings and the encrypted credential vault.

Secondary update path:

```bash
cd /path/to/meti
git pull --ff-only
python scripts/check_release.py
```

Use `git pull` only when the local install path is known, clean, and verified.
Host-native update commands can become primary later once the relevant host
flow is verified for installed users.

## Clean install verification

Verify the OpenClaw path from an empty skill directory:

```bash
rm -rf ~/.openclaw/skills/meti
git clone https://github.com/Nowhitestar/meti.git ~/.openclaw/skills/meti
cd ~/.openclaw/skills/meti
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python scripts/check_release.py
```

For Claude Code local plugin verification, load the same checkout from settings
and verify that `SKILL.md` exposes the wizard and draft-first safety policy.

## Release gate

Run the one-command release gate before tagging a release or preparing
marketplace submission material:

```bash
python scripts/check_release.py
```

The release gate is draft-safe and account-free by default. It checks
`release.json` version synchronization, plugin and marketplace metadata, tracked
private paths, generated wheel/release bundle contents, install docs, and the
no-network smoke flow. It does not create live platform drafts, open a browser,
read real credentials, submit marketplace data, or publish anything publicly.

## Automated release policy

CI owns normal releases from `main`. After the full macOS + Ubuntu test matrix
passes, the release job inspects commits since the latest `vX.Y.Z` tag and
publishes only when there is a release-worthy signal.

Automatic release signals:

- `feat(scope): ...` or `perf(scope): ...` creates a minor release.
- `feat(scope)!: ...` or a `BREAKING CHANGE:` footer creates a major release.
- `release: patch`, `release: minor`, or `release: major` in the commit body
  overrides the automatic choice.

Routine `fix:`, `docs:`, `test:`, `chore:`, `ci:`, and `refactor:` commits do
not publish a release by default. This keeps the release stream focused on
important user-visible changes instead of every small maintenance update.

When a release is selected, CI runs:

```bash
python scripts/plan_release.py --github-output
python scripts/release.py prepare --version X.Y.Z
python scripts/check_release.py
python scripts/release.py build
```

Then CI commits the synchronized version files, atomically pushes `main` and
`vX.Y.Z`, and creates the GitHub Release with the generated artifacts from
`dist/releases/vX.Y.Z/`.

Manual override is available from the CI workflow dispatch UI for exceptional
cases: choose `patch`, `minor`, or `major`, or provide an exact `X.Y.Z` version.
Use this sparingly; the default path should be normal commits to `main`.

Release maintainers can still inspect the same flow locally with dry-run-first
commands:

```bash
python scripts/plan_release.py
python scripts/release.py prepare --version X.Y.Z --dry-run
python scripts/release.py build --dry-run
python scripts/release.py publish --version X.Y.Z --dry-run
```

Manual local publish creates the `vX.Y.Z` tag and published GitHub Release only
after the maintainer approves the printed target version, artifact list,
checksums, and `gh release create` command. Prefer CI for routine releases.

## Private artifacts

Do not package or commit:

- `.planning/`
- `runs/`
- `.env` or `.env.*`
- credential vaults or age keys
- `.claude/` or `.openclaw/` workspaces
- `.mcp/` connector local state
- internal-only docs such as `docs/HANDOFF.md`
- private screenshots, account names, raw token-bearing draft URLs, or live run
  artifacts

The release gate scans tracked paths and built wheel contents, but maintainers
should still review `git status` before release.
