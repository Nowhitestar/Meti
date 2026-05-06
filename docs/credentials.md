# Credentials & Vault

multi-media-publisher stores per-provider credentials in an age-encrypted
JSON file and never exposes them in result/log/output.

## File layout

```
~/.config/mmp/
├── credentials.json.age            # encrypted vault
├── age-key.txt                     # private key (chmod 600)
├── providers/                      # user-installed providers (this directory)
└── settings.toml                   # user preferences
```

## Adding credentials

```bash
mmp setup <provider> [--account <name>]
```

You'll be prompted for each `required_credentials` key declared in that
provider's `provider.yaml`. Secrets are read via `getpass` (no echo).

To list what's stored:

```bash
mmp list accounts
# wechat-article:default
# x-article:lewis
```

To delete an account:

```bash
mmp setup <provider> --account <name>
# (re-enter empty values to clear; future: explicit `mmp accounts rm`)
```

## Per-conversation override (ENV)

Any environment variable matching a `required_credentials.key` overrides the
vault for that one run:

```bash
WECHAT_APP_ID=wx... WECHAT_APP_SECRET=... mmp publish manifest.yaml
```

This is the recommended path for CI and one-off testing.

## Multiple accounts

A provider can have many accounts. Use `--account <name>` at setup, and
reference the account in the manifest:

```yaml
targets:
  - target: x-article
    mode: draft
    account: lewis
```

## Rotating

Compromised vault key:

```bash
rm ~/.config/mmp/credentials.json.age ~/.config/mmp/age-key.txt
mmp setup <each provider>   # re-enter all values
```

The new key is auto-generated on first `setup` after deletion.

## What never leaves the vault

- `result.json` (per-run summary)
- `publish-log.md` (per-run timeline)
- console output beyond `(received)` confirmations
- any git-tracked file in this repo

If you find a credential leaked into one of these, report as a P0 bug.

## Future (v0.3)

- macOS Keychain backend
- Linux secret-service backend
- Windows Credential Manager backend

The `Backend` ABC is already in place; switching is config-only once
implemented.
