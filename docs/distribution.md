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

The release gate is draft-safe and account-free by default. It checks version
synchronization, plugin and marketplace metadata, tracked private paths,
generated wheel contents, install docs, and the no-network smoke flow. It does
not create live platform drafts, open a browser, read real credentials, submit
marketplace data, or publish anything publicly.

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
