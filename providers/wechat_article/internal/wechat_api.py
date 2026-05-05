"""WeChat Official Account draft API helper.

Internal module for the wechat_article provider. Draft-only by design;
public publishing / freepublish is intentionally not implemented.

Public API:
    get_access_token(app_id, app_secret) -> str
    upload_thumb(token, image_path) -> str  # returns media_id
    add_draft(token, articles) -> str       # returns media_id
    draft_from_payload(payload, credentials, dry_run) -> dict
"""
from __future__ import annotations

import html
import json
import mimetypes
import os
import pathlib
import urllib.parse
import urllib.request
from typing import Any

API_BASE = "https://api.weixin.qq.com/cgi-bin"


# ---------------------------------------------------------------------------
# Private HTTP helpers
# ---------------------------------------------------------------------------


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _multipart_upload(
    url: str, field_name: str, file_path: pathlib.Path
) -> dict[str, Any]:
    boundary = "----OpenClawMMPBoundary"
    ctype = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    body = []
    body.append(f"--{boundary}\r\n".encode())
    body.append(
        f'Content-Disposition: form-data; name="{field_name}"; filename="{file_path.name}"\r\n'.encode()
    )
    body.append(f"Content-Type: {ctype}\r\n\r\n".encode())
    body.append(file_path.read_bytes())
    body.append(f"\r\n--{boundary}--\r\n".encode())
    data = b"".join(body)
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _env_token() -> str | None:
    return os.environ.get("WECHAT_ACCESS_TOKEN")


def _local_markdown_to_html(text: str) -> str:
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


def _article_from_payload(
    payload: dict[str, Any], thumb_media_id: str | None
) -> dict[str, Any]:
    content = str(payload.get("html") or "")
    if not content:
        content = _local_markdown_to_html(str(payload.get("content") or ""))
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
        raise ValueError("title is required")
    if not article["content"]:
        raise ValueError("content/html is required")
    if not article["thumb_media_id"]:
        raise ValueError(
            "thumb_media_id is required; provide it or upload a cover image first"
        )
    return article


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_access_token(app_id: str, app_secret: str) -> str:
    """Fetch a WeChat OA access_token.

    If the environment variable ``WECHAT_ACCESS_TOKEN`` is set, return it
    instead of calling the API.
    """
    env = _env_token()
    if env:
        return env
    if not app_id or not app_secret:
        raise ValueError(
            "app_id and app_secret are required unless WECHAT_ACCESS_TOKEN is set"
        )
    url = f"{API_BASE}/token?" + urllib.parse.urlencode(
        {"grant_type": "client_credential", "appid": app_id, "secret": app_secret}
    )
    data = _get_json(url)
    if "access_token" not in data:
        raise RuntimeError(f"failed to get access_token: {data}")
    return str(data["access_token"])


def upload_thumb(token: str, image_path: pathlib.Path) -> str:
    """Upload a cover (thumb) image and return the resulting media_id."""
    if not image_path.exists():
        raise FileNotFoundError(f"cover image not found: {image_path}")
    url = f"{API_BASE}/material/add_material?" + urllib.parse.urlencode(
        {"access_token": token, "type": "thumb"}
    )
    data = _multipart_upload(url, "media", image_path)
    if "media_id" not in data:
        raise RuntimeError(f"failed to upload thumb: {data}")
    return str(data["media_id"])


def add_draft(token: str, articles: list[dict[str, Any]]) -> str:
    """Create a draft from a list of article dicts; returns the draft media_id."""
    payload = {"articles": articles}
    url = f"{API_BASE}/draft/add?" + urllib.parse.urlencode({"access_token": token})
    data = _post_json(url, payload)
    if "media_id" not in data:
        raise RuntimeError(f"failed to add draft: {data}")
    return str(data["media_id"])


def draft_from_payload(
    payload: dict[str, Any],
    credentials: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Build and submit a single-article draft from a high-level payload.

    Args:
        payload: dict with keys like ``title``, ``content``/``html``, ``author``,
            ``digest``, ``cover`` (path) or ``thumb_media_id``,
            ``content_source_url``, ``need_open_comment``,
            ``only_fans_can_comment``.
        credentials: dict that may contain ``app_id``, ``app_secret``,
            ``access_token``.
        dry_run: if True, no network calls are made; placeholder values are
            substituted and the would-be requests are returned.

    Returns:
        ``{"ok": True, "upload": <upload_info_or_None>, "draft": <draft_info>}``
    """
    app_id = str(credentials.get("app_id") or os.environ.get("WECHAT_APP_ID") or "")
    app_secret = str(
        credentials.get("app_secret") or os.environ.get("WECHAT_APP_SECRET") or ""
    )
    explicit_token = credentials.get("access_token") or _env_token()

    if dry_run:
        token = str(explicit_token or "DRY_RUN_TOKEN")
    else:
        token = (
            str(explicit_token)
            if explicit_token
            else get_access_token(app_id, app_secret)
        )

    thumb_media_id = payload.get("thumb_media_id")
    upload_result: dict[str, Any] | None = None
    cover_raw = payload.get("cover")
    cover = (
        pathlib.Path(str(cover_raw)).expanduser()
        if cover_raw and not thumb_media_id
        else None
    )

    if not thumb_media_id and cover:
        if dry_run:
            upload_url = f"{API_BASE}/material/add_material?" + urllib.parse.urlencode(
                {"access_token": token, "type": "thumb"}
            )
            upload_result = {
                "ok": True,
                "dry_run": True,
                "method": "POST multipart",
                "url": upload_url.replace(token, "***"),
                "file": str(cover),
            }
            thumb_media_id = "DRY_RUN_THUMB_MEDIA_ID"
        else:
            media_id = upload_thumb(token, cover)
            upload_result = {"ok": True, "media_id": media_id}
            thumb_media_id = media_id

    article = _article_from_payload(payload, thumb_media_id)

    if dry_run:
        draft_url = f"{API_BASE}/draft/add?" + urllib.parse.urlencode(
            {"access_token": token}
        )
        draft_result: dict[str, Any] = {
            "ok": True,
            "dry_run": True,
            "method": "POST",
            "url": draft_url.replace(token, "***"),
            "payload": {"articles": [article]},
        }
    else:
        media_id = add_draft(token, [article])
        draft_result = {"ok": True, "media_id": media_id}

    return {"ok": True, "upload": upload_result, "draft": draft_result}
