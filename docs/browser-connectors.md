# Browser-flow connectors (v0.3.1+)

Some platforms (X Articles, Substack) have no public draft API. meti
drives the user's **real Chrome** via the [OpenCLI Browser
Bridge][opencli], which is a Chrome extension + small local daemon
that exposes browser primitives over a CLI.

[opencli]: https://github.com/jackwener/opencli

The advantage over a fresh-Chromium / Playwright approach:

- **Works inside your normal browser session.** Platform automation flags target headless Chromium and CDP-controlled instances; your everyday Chrome window is exactly what the platform expects to see.
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
| `x-article` | Browser session via OpenCLI | **Yes** (v0.3.1+) |
| `substack` | Browser session via OpenCLI | **Yes** (v0.3.1+) |
| `wechat-image` (贴图) | Browser session via OpenCLI | **Yes** (v0.3.2+) |

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
meti browser status
# → OK  Browser Bridge connected. Current tab: ...
```

If you see "Browser Bridge extension not connected", the extension
isn't installed or Chrome isn't running. Start Chrome and re-check.

For deeper diagnostic:

```bash
meti browser doctor
```

### 4. Make sure you're logged in

`meti browser login <provider>` opens the provider's login URL **in
your real Chrome**. If you're already logged in, it's a no-op.

```bash
meti browser login x-article    # opens https://x.com/i/flow/login
meti browser login substack     # opens https://substack.com/sign-in
meti browser login wechat-image # opens https://mp.weixin.qq.com/  (v0.3.2+)
```

### 5. Create a draft

```bash
meti publish examples/longform.yaml --mode-override draft
```

If the manifest includes a browser-flow provider (x-article, substack,
or wechat-image), meti:

1. Calls `opencli browser open <provider compose URL>` in your Chrome
2. For wechat-image: injects local image bytes via the
   `DataTransfer` API — MP's webuploader picks up the programmatic
   `change` event and POSTs to `/cgi-bin/filetransfer` normally
3. Drives the editor (type title, body, etc.)
4. For X/Substack: editor auto-saves while we type. For wechat-image:
   we click MP's own "保存为草稿" button so MP's internal save logic
   (with its request-signing wrappers) runs end-to-end
5. Captures the draft URL / ID, returns as `external_id`

If the bridge isn't connected, the run gracefully falls back to
"stub" mode: writes a `TODO-connector.md` with manual instructions
in the run dir. The other targets (wechat-article, etc.) still run.

## Session expiry

Browser sessions don't last forever. When X / Substack / WeChat MP
invalidates your cookies (typically 1–4 weeks of inactivity), `meti
publish` fails on the browser flow with a "redirected to login" error.
Just go to the provider's site in your Chrome, log in normally, then
retry:

```bash
# Just open it; the site remembers the rest.
meti browser login x-article     # or substack / wechat-image
meti resume <run-dir>
```

## CI / headless environments

Browser-flow providers are local-only by design. CI doesn't have a
real Chrome with your logins, so these providers fall back to stub
mode automatically — multi-target manifests still progress, with
x-article / substack / wechat-image becoming manual steps in the
run dir.

## Selector drift / when the connector breaks

X, Substack and WeChat MP ship UI changes regularly. When they break
selectors, the symptom is usually:

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
4. `meti publish ... --mode-override draft` to verify

## i18n caveats

Selectors in the current x-article connector target X's **Chinese
UI** (Lewis's account locale). Title placeholder is `添加标题`; we
also try `Add a title` for English UI. If your locale is different
(Spanish, French, etc.), update `TITLE_SELECTOR_CANDIDATES` in
`providers/x_article/internal/browser_flow.py` to add your
placeholder. PRs welcome.

The `wechat-image` connector targets MP's Chinese-only UI (button
text `保存为草稿`, title placeholder `请在这里输入标题（选填）`).
There is no English Creator Studio UI — overseas accounts log into
the same Chinese console.

## Notes specific to `wechat-image` (贴图)

The 贴图 connector has a few wrinkles the other two don't:

1. **No cover-only API**: WeChat Open Platform's `material/add_material`
   + `draft/add` covers articles (图文) but NOT 贴图 (`type=77`).
   See `docs/wechat-image-tietu-research.md` for the full
   implementation notes.
2. **Local-file upload**: unlike X / Substack drafts (text-only), 贴图
   requires real images. We pass them through the page via base64 in
   `eval` and reconstruct as a `Blob` → `File` → `DataTransfer.items.add`
   → `input.files` setter → `change` event. MP's webuploader picks it
   up the same as a real drag-drop.
3. **`fingerprint` form field**: MP's save endpoint expects a 32-char
   MD5 in the body that's generated inside MP's own seajs modules.
   We let MP handle this by populating the DOM and clicking MP's own "保存为草稿" button — the page's existing save flow runs end-to-end and signs the request itself.
4. **URL pattern is non-obvious**: `?action=add&type=77` returns 404.
   Creating a fresh draft uses
   `?t=media/appmsg_edit_v2&action=edit&isNew=1&type=10&createType=8`.
   `type=77` only filters the draft-list view.

If MP changes UI:

- Title textarea selector lives in `TITLE_SELECTOR`
- Save button is matched by Chinese text `保存为草稿`
- File input picker logic is in `_JS_INJECT_IMAGE_TPL` (currently
  skips `tpl_dropdown_menu_item` ancestors to avoid the leftover
  dropdown's hidden file input)

## Security

- Your X / Substack / WeChat MP cookies live in **your** Chrome, not
  in meti.
- meti doesn't read cookie databases or copy login state.
- For `wechat-image`, image bytes are passed to the page via base64 in
  the `eval` channel; they only live in the page memory of the editor
  tab and the upload XHR to `mp.weixin.qq.com`. meti never persists
  them outside the run-dir's pack folder.
- `result.json` and `publish-log.md` only record draft URLs and IDs
  — no session tokens.
- The OpenCLI extension only acts when you (or meti on your behalf)
  call `opencli browser ...`. Audit by running
  `npx @jackwener/opencli doctor`.

## Roadmap

- ✅ **v0.3.1**: x-article + substack connectors
- ✅ **v0.3.2**: wechat-image (贴图) connector — adds local-image
  injection via `DataTransfer` and "click MP's own save" pattern
  (no need to replicate MP's request-signing logic ourselves)
- **v0.4**: wechat-channel (视频号) connector
- **v0.4**: per-provider session-expiry detection (auto-prompt re-login)
- **v0.4**: cover image upload for x-article + substack (currently
  text-only)
- **v0.4**: contribute reusable adapters back to OpenCLI upstream
  (e.g. `opencli substack draft-create`)

## Why not Playwright?

v0.3.1 originally used Playwright with a fresh Chromium. Two
problems blocked verification:

1. **Google OAuth flagged Playwright as automated** and refused logins. X uses Google OAuth as a sign-in option; that
   path was unusable.
2. **Reusing the user's real Chrome via CDP** required them to
   re-launch Chrome with `--remote-debugging-port` and other flags,
   AND a non-default user-data-dir (Chrome refuses CDP on the
   default profile for security). That's heavy friction for an
   end-user setup.

OpenCLI avoids both: an extension + daemon attaches inside the
user's existing Chrome session, so platform defenses see the same
browser they'd see if the user were clicking manually.

## Related links

- OpenCLI repo: <https://github.com/jackwener/opencli>
- Chrome extension: <https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk>
- meti PR introducing this: <https://github.com/Nowhitestar/meti/pull/3>
