# Wizard — Credential Setup

Triggered when:
- User says "setup credentials" / "添加账号" / "configure <provider>"
- A different stage discovers `credential_status: missing` for a target

## Goal

Populate `~/.config/meti/credentials.json.age` with the keys the chosen
provider's `required_credentials` list. ENV variables override vault for
the current session.

## How to behave

1. **Identify provider + account**.
   - Provider: ask if not given (e.g. "Which provider? wechat-article / xiaohongshu / x-article / substack")
   - Account: default is `default`. Multi-account users may want `lewis`, `work`, etc.

2. **Show what's needed**: run

   ```bash
   python3 scripts/meti.py wizard --dump-context | jq '.providers[] | select(.name=="<NAME>")'
   ```

   List each `required_credentials` entry with its `description` and `setup_hint`.

3. **For each key**, prompt the user:
   - If `secret: false`: ask normally; the value is shown in the conversation (e.g. AppID).
   - If `secret: true`: instruct user to paste in chat; warn that this conversation may be logged on their side. **Never echo the secret back in your reply.** Confirm receipt with "(received)".

4. **Persist** by running:

   ```bash
   python3 scripts/meti.py setup <provider> --account <account>
   ```

   This subcommand prompts via stdin/getpass for each key. **Tell the user this
   is the safer path** — they enter the secret directly into the CLI, never
   into chat.

   Alternative (one-shot, less secure): pass through ENV-prefixed values:

   ```bash
   WECHAT_APP_ID=wx... WECHAT_APP_SECRET=... \
     python3 scripts/meti.py publish manifest.yaml
   ```

5. **Verify**: run

   ```bash
   python3 scripts/meti.py doctor
   ```

   Confirm the account appears in `accounts:` count.

6. **Optional: health check** (only if user wants the network round-trip):

   For wechat-article: verify by calling `get_access_token`. The provider's
   `health_check` returns `ok` / `failed`. We do not expose this in the CLI in
   v0.2; tell the user it'll come in v0.3.

## Security reminders to surface

- Tell the user: "I will not store, re-display, or log this secret."
- If the user pastes a secret in chat, advise them: "Consider rotating this key
  after we're done — chat history is on your side."
- Never pass secrets as command-line arguments (visible in `ps`).
