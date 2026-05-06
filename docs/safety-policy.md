# Safety & Approval Policy

multi-media-publisher will never circumvent platform safeguards or post
publicly without explicit confirmation in the active conversation.

## Defaults

- Manifest top-level `mode` defaults to `draft` if omitted by user.
- All providers ship with `capabilities.publish: false` in v0.2.
- Public publishing requires explicit `mode: publish` in the manifest AND a
  second confirmation in the active conversation.

## Hard rules

1. **No public publish without active confirmation.** Even if the user
   pre-authorized a publish in a prior conversation, ask again on this run.
2. **No bypass.** Never skip login flows, CAPTCHAs, platform reviews, or
   anti-abuse checks. If the browser hits an ambiguous state, stop and ask.
3. **No secret leakage.** Credentials never appear in:
   - `result.json`
   - `publish-log.md`
   - any git-tracked file
   - any printed output beyond `(received)` confirmation
4. **No CLI-arg secrets.** Pass through ENV or vault. CLI args are visible in
   `ps`.
5. **No silent failure.** A target that fails records `status: failed` with
   the upstream error message; the run does not pretend success.
6. **No batch surprise.** Publishing N targets is N explicit confirmations
   when at least one is `mode: publish`.

## Vault & key rotation

- Vault file: `~/.config/mmp/credentials.json.age` (chmod 600).
- Vault key: `~/.config/mmp/age-key.txt` (chmod 600).
- ENV variables override vault for the current session; useful for CI.

To rotate the vault key:
1. `mmp list accounts` to enumerate
2. Re-run `mmp setup <provider> --account <a>` for each
3. Delete the old vault file + age key file

## Third-party providers

- User-installed providers under `~/.config/mmp/providers/<name>/` are
  arbitrary Python.
- v0.2 ProviderRegistry does NOT auto-load user providers — they are detected
  but require explicit `trust_user=True` from the calling host.
- Future v0.3: trust prompt + signature verification.

## Reporting

If a provider is found to publish without confirmation or leak secrets,
treat as a P0 bug. Open an issue and disable the provider in
`settings.toml.providers.trusted_user_providers` until patched.
