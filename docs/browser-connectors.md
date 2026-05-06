# Browser-flow connectors (v0.3.1+)

Some platforms (X Articles, Substack) have no public draft API. mmp
drives the user's **real Chrome** via the [OpenCLI Browser
Bridge][opencli], which is a Chrome extension + small local daemon
that exposes browser primitives over a CLI.

[opencli]: https://github.com/jackwener/opencli

The advantage over a fresh-Chromium / Playwright approach:

- **No automation detection.** X / Google / Cloudflare don't flag
  your real Chrome as a bot — it's literally your browser.
- **No separate login.** Your existing X / Substack login session is
  reused as-is; no captcha re-solving, no 2FA dance per use.
- **No state files to manage.** Login state lives in your Chrome
  profile, exactly where you'd expect.
- **No CDP debug-port dance.** OpenCLI extension talks to its
  daemon via WebSocket; no `--remote-debugging-port` hassle.

Trade-offs:

- One-time Chrome extension install
- Node.js >= 21 prerequisite (OpenCLI is a Node CLI)
- Selectors break when the platform ships UI changes (same as any
  browser-driving solution); selectors are isolated as constants
  at the top of each provider's `internal/browser_flow.py` for easy
  patching

## When you need this

| Provider | Auth model | Browser flow? |
|---|---|---|
| `wechat-article` | API + AppID/Secret | No (use API) |
| `xiaohongshu` | Local skill via `draft.sh` | No |
| `wechat-image` | Manual browser-flow guide | No (manual) |
| `x-article` | Browser session via OpenCLI | **Yes** |
| `substack` | Browser session via OpenCLI | **Yes** (v0.3.2+) |

## Setup

### 1. Install Node.js

```bash
# macOS
brew install node

# Ubuntu / Debian
sudo apt install nodejs npm

# Verify (need 21+)
node --version
```

### 2. Install the OpenCLI Chrome extension

Open the Chrome Web Store: <https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk>

Click "Add to Chrome". Confirm the extension is enabled at
`chrome://extensions`.

### 3. Verify

```bash
mmp browser status
# → OK  Browser Bridge connected. Current tab: ...
```

If you see "Browser Bridge extension not connected", the extension
isn't installed or Chrome isn't running. Start Chrome and re-check.

For deeper diagnostic:

```bash
mmp browser doctor
```

### 4. Make sure you're logged in

`mmp browser login <provider>` opens the provider's login URL **in
your real Chrome**. If you're already logged in, it's a no-op.

```bash
mmp browser login x-article    # opens https://x.com/i/flow/login
mmp browser login substack     # opens https://substack.com/sign-in (v0.3.2+)
```

### 5. Create a draft

```bash
mmp publish examples/longform.yaml --mode-override draft
```

If the manifest includes a browser-flow provider (currently x-article;
substack landing in v0.3.2), mmp:

1. Calls `opencli browser open <provider compose URL>` in your Chrome
2. Drives the editor (type title, body, etc.)
3. X / Substack auto-saves while we type
4. Captures the draft URL / ID, returns as `external_id`

If the bridge isn't connected, the run gracefully falls back to
"stub" mode: writes a `TODO-connector.md` with manual instructions
in the run dir. The other targets (wechat-article, etc.) still run.

## Session expiry

Browser sessions don't last forever. When X or Substack invalidates
your cookies (typically 1–4 weeks of inactivity), `mmp publish` fails
on the browser flow with a "redirected to login" error. Just go to
the provider's site in your Chrome, log in normally, then retry:

```bash
# Just open it; X / Substack remembers the rest.
mmp browser login x-article
mmp resume <run-dir>
```

## CI / headless environments

Browser-flow providers are local-only by design. CI doesn't have a
real Chrome with your logins, so these providers fall back to stub
mode automatically — multi-target manifests still progress, with
x-article / substack becoming manual steps in the run dir.

## Selector drift / when the connector breaks

X and Substack ship UI changes regularly. When they break selectors,
the symptom is usually:

```
RuntimeError: x compose/articles: 'Write new' button not found.
Tried selectors: [...]. Update WRITE_BUTTON_CANDIDATES in
providers/x_article/internal/browser_flow.py.
```

Fix path:

1. Use OpenCLI to inspect the live page:
   ```bash
   npx @jackwener/opencli browser open https://x.com/compose/articles
   npx @jackwener/opencli browser state | head -100
   npx @jackwener/opencli browser find --css '[data-testid]' --limit 30
   ```
2. Find the new selector(s)
3. Update the candidates list in the provider's `internal/browser_flow.py`
4. `mmp publish ... --mode-override draft` to verify

## i18n caveats

Selectors in the current x-article connector target X's **Chinese
UI** (Lewis's account locale). Title placeholder is `添加标题`; we
also try `Add a title` for English UI. If your locale is different
(Spanish, French, etc.), update `TITLE_SELECTOR_CANDIDATES` in
`providers/x_article/internal/browser_flow.py` to add your
placeholder. PRs welcome.

## Security

- Your X / Substack cookies live in **your** Chrome, not in mmp.
- mmp doesn't read cookie databases or copy login state.
- `result.json` and `publish-log.md` only record draft URLs and IDs
  — no session tokens.
- The OpenCLI extension only acts when you (or mmp on your behalf)
  call `opencli browser ...`. Audit by running
  `npx @jackwener/opencli doctor`.

## Roadmap

- **v0.3.1**: x-article connector (this)
- **v0.3.2**: substack connector (PR-B)
- **v0.4**: per-provider session-expiry detection (auto-prompt re-login)
- **v0.4**: cover image upload across browser-flow providers
- **v0.4**: contribute reusable adapters back to OpenCLI upstream
  (e.g. `opencli substack draft-create`)

## Why not Playwright?

v0.3.1 originally used Playwright with a fresh Chromium. Two
problems blocked verification:

1. **Google OAuth (and other anti-bot) detected Playwright** and
   refused logins. X uses Google OAuth as a sign-in option; that
   path was unusable.
2. **Reusing the user's real Chrome via CDP** required them to
   re-launch Chrome with `--remote-debugging-port` and other flags,
   AND a non-default user-data-dir (Chrome refuses CDP on the
   default profile for security). That's heavy friction for an
   end-user setup.

OpenCLI sidesteps both: an extension + daemon attaches inside the
user's existing Chrome session, so anti-bot defenses see the same
browser they'd see if the user were clicking manually.

## Related links

- OpenCLI repo: <https://github.com/jackwener/opencli>
- Chrome extension: <https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk>
- mmp PR introducing this: <https://github.com/Nowhitestar/multi-media-publisher/pull/3>
