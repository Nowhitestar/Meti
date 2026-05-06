# wechat-image (贴图) reverse-engineering notes

This file documents the findings from network-capture of the WeChat MP
"贴图" (sticker / image post, `type=77`) creation flow. It informs the
implementation of `providers/wechat_image/internal/browser_flow.py`.

Captured against `mp.weixin.qq.com` Creator UI on 2026-05-06 with an
authenticated Chrome session via the OpenCLI Bridge (XHR/fetch
interceptor + `opencli browser network` server-side capture).

## Why "browser-flow" and not API

The Open Platform `material/add_material` + `draft/add` API (used by the
`wechat-article` provider) exposes only the "图文" (article) draft type.
**The "贴图" type (`type=77`) is web-only** — there is no public
endpoint to create or list it. Implementation must drive the Creator
Studio web UI like our other browser-flow providers (`x-article`,
`substack`).

## Editor URL

```
https://mp.weixin.qq.com/cgi-bin/appmsg
  ?t=media/appmsg_edit
  &action=add        # or &action=edit&appmsgid=<id> for existing draft
  &type=77           # confirmed: 77 = 贴图
  &token=<TOKEN>     # session CSRF token (URL-resident)
  &lang=zh_CN
```

After `action=add` MP allocates a new `appmsgid` and rewrites the URL
to `action=edit&appmsgid=<id>`. That `appmsgid` is what we return as
the provider's `external_id`.

## Two endpoints we drive

### 1. Image upload — `POST /cgi-bin/filetransfer`

```
URL: /cgi-bin/filetransfer
  ?action=upload_material
  &f=json
  &ticket_id=<USER_NAME>      # ← wx.data.user_name
  &ticket=<UPLOAD_TICKET>     # ← wx.data.ticket (40-char hex)
  &svr_time=<UNIX_S>          # ← wx.cgiData.svr_time
  &scene=5                    # constant (image post)
  &writetype=doublewrite      # constant
  &groupid=1                  # constant
  &token=<TOKEN>
  &lang=zh_CN
  &seq=<MS_TIMESTAMP>         # client-side dedup id

Content-Type: multipart/form-data
FormData:
  id:              "WU_FILE_<idx>"     # webuploader convention
  name:            "<filename>"
  type:            "image/png"          # or image/jpeg
  lastModifiedDate: "<JS Date string>"
  size:            <bytes>
  file:            <File blob>
```

Response (JSON):
```json
{
  "base_resp": {"ret": 0, "err_msg": "ok"},
  "location": "bizfile",
  "type":     "image",
  "content":  "<MP_FILE_ID>",                            ← MP-internal file_id
  "cdn_url":  "https://mmbiz.qpic.cn/sz_mmbiz_png/.../0?wx_fmt=png&from=appmsg",
  "ai_status": 1
}
```

The `content` field is what gets used as `file_id` in the save body's
`crop_list` and `share_imageinfo`. The `cdn_url` is the original (PNG)
URL, used as `cdn_url_back0` in the save body.

### 2. Save draft — `POST /cgi-bin/operate_appmsg`

```
URL: /cgi-bin/operate_appmsg
  ?t=ajax-response
  &sub=update
  &type=77
  &token=<TOKEN>
  &lang=zh_CN

Content-Type: application/x-www-form-urlencoded
Body fields (the meaningful ones for 贴图):

  AppMsgId:           <existing draft id, or 0 for new>
  count:              1                               # number of items in this draft
  data_seq:           <19-digit session seq>          # client dedup token
  operate_from:       Chrome
  isnew:              0 / 1
  articlenum:         1                               # always 1 for 贴图
  fingerprint:        <32-char MD5>                   # session-bound, computed by MP's AJAX wrapper
  random:             <0..1 float>
  token:              <TOKEN>
  lang:               zh_CN
  f:                  json
  ajax:               1

  # per-item fields (suffix 0 = first item)
  title0:             <title text>
  content0:           <body text>          # HTML for article, plain for 贴图
  guide_words0:       <duplicate of content for 贴图>
  is_user_title0:     1
  digest0:            ""                    # auto-generated
  auto_gen_digest0:   1
  cdn_url0:           <CDN URL, jpeg variant>
  cdn_235_1_url0:     <2.35:1 crop CDN URL>      # MP server-generated when user crops
  cdn_3_4_url0:       <3:4 crop CDN URL>          # ditto
  cdn_1_1_url0:       <1:1 crop CDN URL>          # ditto
  cdn_url_back0:      <original PNG CDN URL>
  crop_list0:         <JSON: ratios + per-ratio file_id>
  share_imageinfo0:   <JSON: list of {url, file_id, height, width, theme_color}>
  style_type0:        3                            # constant for 贴图
  new_pic_process0:   1                            # constant
  share_page_type0:   8                            # constant for 贴图
  sticker_info0:      {}                           # empty unless using stickers overlay
  show_cover_pic0:    0
  copyright_type0:    0
  need_open_comment0: 1
  reply_flag0:        2
  open_comment_ad0:   1
  can_insert_ad0:     1
  msg_index_id0:      "0_<AppMsgId>_0"

  # nested req structure (large JSON blob with idx_infos)
  req: {"idx_infos":[{...}]}

  # session-level
  remind_flag:        ""
  is_auto_type_setting: 3
  save_type:          0
  isneedsave:         0
```

Response (JSON):
```json
{
  "base_resp": {"ret": 0, "err_msg": ""},
  "appMsgId": <DRAFT_ID>,                            ← updated/created draft id
  "data_seq": "4504367451828338688",
  "msg_index_id_list": ["0_<DRAFT_ID>_0"],
  "ret": "0",
  ...
}
```

## Bootstrap params (extractable from page context)

| Param | Source |
|---|---|
| `token`     | `wx.data.t` (or URL `?token=`) |
| `lang`      | `wx.data.lang` |
| `ticket`    | `wx.data.ticket` |
| `ticket_id` | `wx.data.user_name` |
| `svr_time`  | `wx.cgiData.svr_time` |
| `uin`       | `wx.data.uin` |
| `appmsgid`  | `wx.cgiData.app_id` (after MP allocates) |

## The `fingerprint` problem

`fingerprint` (32-char MD5) is in every authenticated MP request body
but **not exposed as a global** — it's computed inside MP's seajs
modules and wrapped around `$.ajax`. It does NOT propagate to plain
`$.ajax({url, data})` calls without going through MP's wrapper.

We don't need to reverse-engineer the generator. The chosen
implementation strategy avoids the fingerprint problem entirely (see
below).

## Architecture decision

**Drive the Creator Studio editor via DOM-level interaction, then
click MP's own "保存为草稿" button.** This way MP's own save logic
runs end-to-end, which:

1. Generates `fingerprint` correctly via its internal wrappers
2. Constructs the full `req` JSON blob (idx_infos, link_info, etc.)
3. Issues `collaboration_get` + `collaboration_edit` locks
4. POSTs the operate_appmsg with all required fields populated
5. Updates the URL with the new `appmsgid` (we read this for `external_id`)

We do NOT manually POST `operate_appmsg` ourselves.

The only programmatic action we take that must look like a real user is
the **file upload**. We use the `DataTransfer` trick to populate
`<input type=file>.files` from a Blob constructed from the local image
bytes (passed through `eval` as base64). MP's webuploader listens on
the input's `change` event and triggers its own filetransfer POST —
again, generating tickets via its internal flow.

### Step-by-step

1. `core.browser.open_url(<editor URL with action=add&type=77>)`
2. Wait for editor to load (selector `textarea.js_article_title`)
3. **Image upload** — for each image:
   - Read local bytes, base64-encode in Python
   - `eval` JS that:
     - Decodes base64 → `Uint8Array` → `Blob`
     - Constructs `File` with name + type
     - Finds the right `<input type=file>` (3 candidates on page; 贴图 input is the one with `accept` containing `image`)
     - Sets `input.files` via `DataTransfer.items.add` + bypass setter
     - Dispatches `change` event
   - Wait for upload XHR to complete (capture via interceptor or check for image preview to appear)
4. **Title** — use `core.browser.type_text("textarea.js_article_title", title)` (real keyboard, dirties React state)
5. **Body** — type into `.ProseMirror` (visible one)
6. **Save** — `core.browser.click()` on button with text `保存为草稿`
7. Wait for save XHR (capture via interceptor) and successful toast
8. Read new `appmsgid` from URL or page state
9. Return `{external_id: appmsgid, draft_url: editor_url}`

### Selector reference (subject to UI drift)

| Element | Selector | Notes |
|---|---|---|
| Title textarea | `textarea.js_article_title` | placeholder: "请在这里输入标题（选填）" |
| Body editor | `.ProseMirror` (visible, idx 1 of 3) | TipTap-based contenteditable |
| Image file input | `input[type=file]` (first one accepting image) | hidden; webuploader manages |
| Save draft button | `button` with text `保存为草稿` | `parentElement.className` includes `btn_input btn_primary` |
| Success toast | `.weui-desktop-mass__pop_main` or similar | check for "保存成功" text |

### Failure modes & recovery

| Failure | Symptom | Handling |
|---|---|---|
| Not logged in | URL redirects to login | Same as x-article: raise RuntimeError with login URL hint |
| `action=add` rejected | URL still on home, no editor | `RuntimeError("MP didn't allocate draft — check publication permissions")` |
| Image upload fails | filetransfer XHR returns ret != 0 | `RuntimeError("upload failed: <err_msg>")` |
| Save fails | operate_appmsg returns ret != 0 | `RuntimeError("save failed: <err_msg>")` |
| Selector drift | type/click can't find target | Same pattern as x-article — selector constants at top of file, friendly error message pointing to this doc |

## What we do NOT support

- **Multiple images per 贴图**: 贴图 supports up to 9 images. v0.3.2 starts
  with single-image; multi-image is a follow-up.
- **Crop ratios**: 贴图 lets users explicitly crop. We just upload the
  image and let MP fill default crops on save (MP server-side generates
  variants from the original).
- **Stickers / overlays**: `sticker_info0={}` always.
- **Topic tags / mentions**: deferred.
- **Music / vote / pay**: deferred.
- **Direct publish**: only `draft` supported, same as wechat-article.

## Open questions (to revisit if needed)

- Does MP rate-limit upload by IP? (We hit it once — no rate-limit error,
  but at scale this could matter.)
- Does session expiry on cookies trigger a graceful redirect or just a
  silent 401? Need to verify by letting the cookie expire and retrying.
- Multi-image flow: presumably webuploader supports `multiple=true` or
  multiple change events; need to verify selectors match.

## Browser MCP / file-upload alternatives considered

- `mcp__chrome-devtools__upload_file`: works via CDP, but requires
  launching Chrome with `--remote-debugging-port` + non-default
  user-data-dir. Same friction we abandoned in v0.3.1.
- `mcp__playwright__browser_file_upload`: needs fresh Chromium, breaks
  the "user's real Chrome session" model.
- DataTransfer + `input.files` setter: works on most sites including
  MP's webuploader. **Chosen path.**
