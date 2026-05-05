#!/usr/bin/env python3
"""WeChat Official Account draft API helper.

Draft-only by design. Public publishing/freepublish is intentionally not implemented.
"""
from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
import pathlib
import sys
import urllib.parse
import urllib.request
from typing import Any

API_BASE = "https://api.weixin.qq.com/cgi-bin"


def die(msg: str, code: int = 2) -> None:
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False, indent=2))
    raise SystemExit(code)


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def multipart_upload(url: str, field_name: str, file_path: pathlib.Path) -> dict[str, Any]:
    boundary = "----OpenClawMMPBoundary"
    ctype = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    body = []
    body.append(f"--{boundary}\r\n".encode())
    body.append(f'Content-Disposition: form-data; name="{field_name}"; filename="{file_path.name}"\r\n'.encode())
    body.append(f"Content-Type: {ctype}\r\n\r\n".encode())
    body.append(file_path.read_bytes())
    body.append(f"\r\n--{boundary}--\r\n".encode())
    data = b"".join(body)
    req = urllib.request.Request(url, data=data, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def env_token() -> str | None:
    return os.environ.get("WECHAT_ACCESS_TOKEN")


def get_token(app_id: str | None, app_secret: str | None, dry_run: bool = False) -> dict[str, Any]:
    if env_token():
        return {"ok": True, "access_token": env_token(), "source": "WECHAT_ACCESS_TOKEN"}
    if not app_id or not app_secret:
        die("WECHAT_APP_ID and WECHAT_APP_SECRET are required unless WECHAT_ACCESS_TOKEN is set")
    url = f"{API_BASE}/token?" + urllib.parse.urlencode({"grant_type": "client_credential", "appid": app_id, "secret": app_secret})
    if dry_run:
        return {"ok": True, "dry_run": True, "method": "GET", "url": url.replace(app_secret, "***")}
    data = get_json(url)
    if "access_token" not in data:
        die(f"failed to get access_token: {data}", 1)
    return {"ok": True, "access_token": data["access_token"], "expires_in": data.get("expires_in"), "source": "api"}


def token_value(args: argparse.Namespace) -> str:
    token = args.access_token or env_token()
    if token:
        return token
    tok = get_token(os.environ.get("WECHAT_APP_ID"), os.environ.get("WECHAT_APP_SECRET"))
    return str(tok["access_token"])


def local_markdown_to_html(text: str) -> str:
    # Minimal safe-ish conversion. Prefer a real Markdown renderer upstream.
    parts = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if para.startswith("# "):
            parts.append(f"<h1>{html.escape(para[2:].strip())}</h1>")
        elif para.startswith("## "):
            parts.append(f"<h2>{html.escape(para[3:].strip())}</h2>")
        else:
            parts.append("<p>" + html.escape(para).replace("\n", "<br/>") + "</p>")
    return "\n".join(parts)


def upload_thumb(token: str, file_path: pathlib.Path, dry_run: bool) -> dict[str, Any]:
    if not file_path.exists():
        die(f"cover image not found: {file_path}")
    url = f"{API_BASE}/material/add_material?" + urllib.parse.urlencode({"access_token": token, "type": "thumb"})
    if dry_run:
        return {"ok": True, "dry_run": True, "method": "POST multipart", "url": url.replace(token, "***"), "file": str(file_path)}
    data = multipart_upload(url, "media", file_path)
    if "media_id" not in data:
        die(f"failed to upload thumb: {data}", 1)
    return {"ok": True, "media_id": data["media_id"], "url": data.get("url")}


def add_draft(token: str, articles: list[dict[str, Any]], dry_run: bool) -> dict[str, Any]:
    payload = {"articles": articles}
    url = f"{API_BASE}/draft/add?" + urllib.parse.urlencode({"access_token": token})
    if dry_run:
        return {"ok": True, "dry_run": True, "method": "POST", "url": url.replace(token, "***"), "payload": payload}
    data = post_json(url, payload)
    if "media_id" not in data:
        die(f"failed to add draft: {data}", 1)
    return {"ok": True, "media_id": data["media_id"]}


def article_from_payload(payload: dict[str, Any], thumb_media_id: str | None) -> dict[str, Any]:
    content = str(payload.get("html") or "")
    if not content:
        content = local_markdown_to_html(str(payload.get("content") or ""))
    article = {
        "title": str(payload.get("title") or "")[:64],
        "author": str(payload.get("author") or ""),
        "digest": str(payload.get("digest") or "")[:120],
        "content": content,
        "content_source_url": str(payload.get("content_source_url") or ""),
        "thumb_media_id": thumb_media_id or str(payload.get("thumb_media_id") or ""),
        "need_open_comment": int(payload.get("need_open_comment") or 0),
        "only_fans_can_comment": int(payload.get("only_fans_can_comment") or 0),
    }
    if not article["title"]:
        die("title is required")
    if not article["content"]:
        die("content/html is required")
    if not article["thumb_media_id"]:
        die("thumb_media_id is required; provide it or provide --cover to upload")
    return article


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check-env")

    p = sub.add_parser("get-token")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("upload-thumb")
    p.add_argument("image", type=pathlib.Path)
    p.add_argument("--access-token")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("add-draft")
    p.add_argument("articles_json", type=pathlib.Path)
    p.add_argument("--access-token")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("draft-from-payload")
    p.add_argument("payload_json", type=pathlib.Path)
    p.add_argument("--cover", type=pathlib.Path)
    p.add_argument("--thumb-media-id")
    p.add_argument("--access-token")
    p.add_argument("--dry-run", action="store_true")

    args = ap.parse_args()

    if args.cmd == "check-env":
        print(json.dumps({
            "ok": bool(env_token() or (os.environ.get("WECHAT_APP_ID") and os.environ.get("WECHAT_APP_SECRET"))),
            "has_access_token": bool(env_token()),
            "has_app_id": bool(os.environ.get("WECHAT_APP_ID")),
            "has_app_secret": bool(os.environ.get("WECHAT_APP_SECRET")),
        }, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "get-token":
        print(json.dumps(get_token(os.environ.get("WECHAT_APP_ID"), os.environ.get("WECHAT_APP_SECRET"), args.dry_run), ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "upload-thumb":
        token = args.access_token or token_value(args)
        print(json.dumps(upload_thumb(token, args.image, args.dry_run), ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "add-draft":
        token = args.access_token or token_value(args)
        articles = json.loads(args.articles_json.read_text(encoding="utf-8"))
        if isinstance(articles, dict):
            articles = articles.get("articles", [])
        print(json.dumps(add_draft(token, articles, args.dry_run), ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "draft-from-payload":
        token = args.access_token or ("DRY_RUN_TOKEN" if args.dry_run else token_value(args))
        payload = json.loads(args.payload_json.read_text(encoding="utf-8"))
        thumb_media_id = args.thumb_media_id
        upload_result = None
        cover = args.cover or (pathlib.Path(str(payload.get("cover"))).expanduser() if payload.get("cover") else None)
        if not thumb_media_id and cover:
            upload_result = upload_thumb(token, cover, args.dry_run)
            thumb_media_id = upload_result.get("media_id") or "DRY_RUN_THUMB_MEDIA_ID"
        article = article_from_payload(payload, thumb_media_id)
        result = add_draft(token, [article], args.dry_run)
        print(json.dumps({"ok": True, "upload": upload_result, "draft": result}, ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
