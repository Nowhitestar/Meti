# WeChat API Proxy (v0.3+)

WeChat Official Account API requires the calling IP to be in a pre-configured
whitelist. Home networks, mobile hotspots, and split-routing setups (common
in mainland-blocked regions) hit two problems:

1. **Outbound IP changes** — every router restart, ISP DHCP renewal, network
   switch (home → cafe → office) means whitelist update.
2. **Different IP per destination** — split-routing can mean
   `ipinfo.io` reports one IP while `api.weixin.qq.com` sees another.
   Verified empirically during v0.2 dev: `103.129.180.55` (Taipei) on the
   public side, `115.199.114.116` (杭州/大陆直连) for WeChat traffic.
3. **50-IP whitelist ceiling** — every band-aid IP eventually fills the slot.

Solution: route all WeChat API calls through a static-IP bastion. Set
`WECHAT_API_PROXY` to point at the bastion; meti will rewrite all
`api.weixin.qq.com/cgi-bin/*` calls to `<your-bastion>/cgi-bin/*`.

## Setup

### 1. Pick a bastion

Anything with a static outbound IP works. Pricing/effort tradeoffs:

| Option | Cost | Static IP | Setup time |
|---|---|---|---|
| Cloudflare Workers | Free tier (100k req/day) | One Cloudflare IP range — add `*` to whitelist or use Cloudflare egress IPs | 5 min |
| Vercel Edge / Deno Deploy | Free tier | Egress IP changes within range | 10 min |
| $5/mo VPS (Vultr / Hetzner / DO) | $5/mo | Yes, single IP | 30 min |
| Tailscale + home-server exit node | Free | Stable home IP | 1 hr |

Recommendation: **Cloudflare Workers** for the median user — fastest setup,
Cloudflare egress IPs are well-documented and few enough to whitelist.

### 2. Deploy a thin proxy

The proxy must:

- Accept `/cgi-bin/<anything>` paths
- Forward to `https://api.weixin.qq.com/cgi-bin/<same path>`
- Preserve method, headers (especially `Content-Type`), and body
- Return WeChat's response verbatim (status code, headers, body)

That's it. No auth, no logic. The token in the query string is WeChat's own
session token — the proxy doesn't need to handle credentials.

### 3. Add the proxy IP(s) to your WeChat IP whitelist

Go to mp.weixin.qq.com → 设置与开发 → 基本配置 → IP白名单. Add the
bastion's static IP(s).

For Cloudflare Workers, see
<https://www.cloudflare.com/ips/> for the egress IP ranges. They publish
both IPv4 and IPv6 ranges; whitelist all the IPv4 ranges you'll be using.

### 4. Configure meti

```bash
export WECHAT_API_PROXY="https://my-bastion.example.com"
meti publish examples/longform.yaml --mode-override draft
```

Or persist for an account:

```bash
meti setup wechat-article
# When prompted, instead of just AppID/Secret, also include
# WECHAT_API_PROXY at the top of your shell profile or env file.
```

(`WECHAT_API_PROXY` is intentionally NOT in the vault — it's not a secret and
having it in env makes A/B-testing different bastions easier.)

## Cloudflare Worker template

This is a complete `worker.js`. Deploy via `wrangler deploy` or paste into
the Cloudflare dashboard's Workers editor.

```javascript
// wechat-api-proxy worker
//
// Forwards everything under /cgi-bin/* to api.weixin.qq.com verbatim.
// Cloudflare's egress IPs are stable enough to whitelist; the user only
// updates their WeChat IP whitelist once (at setup) instead of every time
// their network changes.

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Only forward /cgi-bin/* paths. Anything else gets a 404.
    if (!url.pathname.startsWith("/cgi-bin/")) {
      return new Response("Not Found", { status: 404 });
    }

    // Rewrite to api.weixin.qq.com, preserve path + query string.
    const upstream = new URL(url.pathname + url.search, "https://api.weixin.qq.com");

    // Build the upstream request. Preserve method, headers (minus Host), body.
    const headers = new Headers(request.headers);
    headers.delete("host");
    headers.delete("cf-connecting-ip");  // Cloudflare-specific noise

    const upstreamRequest = new Request(upstream.toString(), {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
      redirect: "follow",
    });

    return fetch(upstreamRequest);
  },
};
```

### Deploy with wrangler

```bash
npm install -g wrangler
wrangler login

# Create wrangler.toml in a fresh directory:
cat > wrangler.toml <<'TOML'
name = "wechat-api-proxy"
main = "worker.js"
compatibility_date = "2025-01-01"
TOML

# Save the worker code above as worker.js, then:
wrangler deploy
# → Published to https://wechat-api-proxy.<your-subdomain>.workers.dev
```

Set `WECHAT_API_PROXY=https://wechat-api-proxy.<your-subdomain>.workers.dev`.

## Security notes

- **Don't add auth to the proxy.** WeChat's own access_token is the
  authentication; the proxy is just a network hop. Adding HTTP Basic Auth
  on top means putting credentials in `WECHAT_API_PROXY` URL or HTTP
  headers, which leaks into logs.
- **Don't log request/response bodies in the proxy.** They contain
  access_tokens and (briefly) draft contents.
- **Rate-limit the worker** if you're worried about abuse — Cloudflare
  free tier has 100k req/day default cap, which is plenty for personal use.
  If exposing to multiple users, add a `WECHAT_PROXY_KEY` header check at
  the worker (and a matching `headers={"X-Proxy-Key": "..."}` injection at
  the meti side — currently not supported but easy v0.3.x add).
- **Cloudflare logs request paths and metadata** by default. If WeChat
  paths leak any sensitive info beyond `/cgi-bin/<endpoint>` shape, this
  matters. Audit your CF account's request logging settings before
  routing production traffic.

## Troubleshooting

### `errcode: 40164 invalid ip <IP>`

The IP belongs to **the proxy**, not your machine. Add that IP to
`mp.weixin.qq.com` whitelist. Once added, all subsequent requests from
the proxy will pass.

### `errcode: 40001 invalid credential`

The proxy is forwarding correctly but your AppID/AppSecret are wrong.
Re-run `meti setup wechat-article`.

### Proxy works for `get_access_token` but not `add_draft`

Most likely a header/body issue in your proxy. Common cause: stripping
`Content-Type` for POST. The Cloudflare template above preserves headers
correctly; if you wrote your own, make sure POSTs preserve
`Content-Type: application/json` and the multipart boundary for
`upload_thumb`.

### Verifying

After setup:

```bash
# Should hit your proxy, then proxy hits WeChat.
WECHAT_API_PROXY=https://your-proxy.example.com meti publish \
  examples/longform.yaml --mode-override draft
```

Check `result.json` for `external_id` (means WeChat accepted the draft via
your proxy). If you see `errcode: 40164`, the WeChat IP whitelist needs
the proxy's IP added.

## Related v0.3 work

- `meti setup wechat-article` could prompt for `WECHAT_API_PROXY` and store
  it in `~/.config/meti/settings.toml` (currently env-only)
- Health-check: `meti doctor` could ping `<proxy>/cgi-bin/token` with a
  malformed AppID and confirm the proxy returns WeChat's `errcode: 40013`
  (proves end-to-end connectivity without needing real creds)
