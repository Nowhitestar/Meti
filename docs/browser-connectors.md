# Browser-flow connectors (v0.3.1+)

Some platforms (X Articles, Substack, future ones) have no public draft
API or have an API gated behind onboarding most users won't pass. mmp
drives a real Chromium browser via [Playwright][pw] for these, using a
saved login session.

[pw]: https://playwright.dev/python/

The browser layer is **opt-in**: install with the `[browser]` extra,
configure each provider once, and only providers that opt into browser
flows (`browser_login_url` set on the Provider class) are touched.

## When you need this

| Provider | Auth model | This guide applies? |
|---|---|---|
| `wechat-article` | API + AppID/Secret | No (use API) |
| `xiaohongshu` | Local skill via `draft.sh` | No |
| `wechat-image` | Manual browser-flow guide | No (manual) |
| `x-article` | Browser session | **Yes** |
| `substack` | Browser session | **Yes** |

If you only publish to wechat-article + xiaohongshu, you can ignore this
file entirely.

## Setup

### 1. Install the optional dependency

```bash
pip install -e ".[browser]"
playwright install chromium
```

The Chromium download is ~120 MB. If you've installed Playwright before
for another project, `playwright install chromium` is a no-op.

### 2. Capture login state per provider

Run once for each provider you'll use:

```bash
mmp browser login x-article
```

This:
1. Opens a **headed** Chromium window at `https://x.com/i/flow/login`
2. You log in normally (including 2FA, captcha, anything X throws at you)
3. When you're on a logged-in page (your home feed, profile, etc.),
   come back to the terminal and press Enter
4. mmp saves cookies + localStorage to
   `~/.config/mmp/browser-state/x-article.json` (chmod 600)

The saved state is reused for headless draft creation later — no further
login needed until the session expires.

### 3. Verify

```bash
mmp browser status
#   x-article             saved 2026-05-06 12:34 UTC  (~/.config/mmp/browser-state/x-article.json)
```

### 4. Create a draft

```bash
mmp publish examples/longform.yaml --mode-override draft
```

If a target with `browser_login_url` (currently x-article, substack) is
in the manifest, mmp will:
1. Check if state exists → if not, fall back to "stub" mode and write
   `TODO-connector.md` with setup instructions
2. Launch headless Chromium with the saved state
3. Navigate, fill the editor, click Save Draft
4. Capture the draft URL / ID, return as `external_id`

## Session lifecycle

Sessions don't last forever. Both X and Substack invalidate cookies
after periods of inactivity (typically 1–4 weeks).

When that happens:
- `mmp publish ...` fails on the browser flow with a `RuntimeError`
  about the compose page not loading
- `result.json` shows `status: failed` with a message pointing at
  re-running `mmp browser login <provider>`

Re-capture:

```bash
mmp browser logout x-article    # delete stale state
mmp browser login x-article     # capture fresh
mmp resume <run-dir>            # retry the failed run
```

## CI / headless-only environments

The browser flow is local-only by design. Use cases like CI that don't
have a real browser shouldn't enable the `[browser]` extra. Without
Playwright installed, browser-flow providers fall back to writing
`TODO-connector.md` and reporting `mode_actual="stub"` — multi-target
manifests still progress, x-article/substack just become manual steps.

## Selector drift / when the connector breaks

X and Substack ship UI changes regularly. When they break our selectors,
the symptom is usually:

```
RuntimeError: x-article compose page didn't load (selector
'[data-testid="articleTitle"]'). Likely causes: session expired
(re-run `mmp browser login x-article`), or X changed their UI (update
selectors in providers/x_article/internal/browser_flow.py).
```

Fix path:
1. Open the provider's `internal/browser_flow.py` (e.g.
   `providers/x_article/internal/browser_flow.py`)
2. Selectors are constants at the top of the file (TITLE_SELECTOR,
   BODY_SELECTOR, SAVE_DRAFT_BUTTON_TEXT, DRAFT_SAVED_INDICATOR)
3. Run `mmp browser login <provider>` to open a headed window, use
   browser DevTools to find the new selectors
4. Update the constants, run `make test`, file a PR

## Security

- Browser state files contain session cookies and localStorage data.
  Treat them like a password.
- Never commit `~/.config/mmp/browser-state/*.json` to git (covered by
  default `.gitignore` since it's outside the repo).
- Don't share state files across machines unless both are yours.
- If you suspect compromise: `mmp browser logout <provider>` to delete,
  then on the platform site, log out of all sessions to invalidate the
  stolen cookies, then `mmp browser login <provider>` to recapture.

## Troubleshooting

### `BrowserStateMissingError: no saved browser state for 'x-article'`

You haven't run `mmp browser login x-article` yet. Run it.

### `BrowserNotInstalledError: playwright is not installed`

`pip install -e ".[browser]"` and `playwright install chromium`.

### Login window opens but I can't tell if I'm logged in

X / Substack URLs aren't always a clear indicator. If `home`, `dashboard`,
or your profile page loads — you're in. Press Enter on the terminal.

### `playwright install` hangs on the download

Check your network. The Chromium binaries come from `playwright.azureedge.net`
(120 MB). If you're on a restricted network, you may need to mirror —
see Playwright's docs on `PLAYWRIGHT_BROWSERS_PATH`.

### Draft was saved but `external_id` is empty

X doesn't always update the URL on draft save. Fall back to checking the
draft listing manually. Future: parse the toast / response to extract
the article ID more reliably.

## Roadmap

- v0.3.1: x-article connector (this PR), stub fallback, docs
- v0.3.2: substack connector
- v0.4: per-provider session refresh detection (auto-prompt re-login
  when health_check sees stale cookies)
- v0.4: proxy support (route Playwright traffic through SOCKS5 for users
  on restricted networks)
