#!/usr/bin/env python3
"""Prepare a longform run pack for WeChat Official Account + X Articles + Substack.

Offline-only by design: validates local inputs, resolves assets, generates per-target
payloads and previews, and writes a run directory. It never opens browsers, calls
external APIs, or publishes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import pathlib
import re
import shutil
import sys
import textwrap
from typing import Any

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
DEFAULT_TARGETS = ["wechat-article", "x-article", "substack"]
SUPPORTED_TARGETS = set(DEFAULT_TARGETS)


def simple_yaml_load(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    stack: list[tuple[int, object]] = [(-1, data)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if line.startswith("- "):
            if isinstance(parent, list):
                parent.append(line[2:].strip().strip('"\''))
            continue
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key, val = key.strip(), val.strip()
        if not val:
            container: object = [] if key in {"targets", "tags"} else {}
            if isinstance(parent, dict):
                parent[key] = container
            stack.append((indent, container))
        else:
            val = val.split(" #", 1)[0].strip().strip('"\'')
            if isinstance(parent, dict):
                parent[key] = val
    return data


def yaml_load(path: pathlib.Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text) if yaml else simple_yaml_load(text)
    if not isinstance(data, dict):
        raise SystemExit("Manifest must be a YAML mapping/object")
    return data


def resolve(base: pathlib.Path, value: str | pathlib.Path | None) -> pathlib.Path | None:
    if value is None or str(value).strip() == "":
        return None
    p = pathlib.Path(str(value)).expanduser()
    return p if p.is_absolute() else (base / p).resolve()


def read_body(base: pathlib.Path, body: str) -> tuple[str, str | None]:
    p = resolve(base, body)
    if p and p.exists() and p.is_file():
        return p.read_text(encoding="utf-8"), str(p)
    return body, None


def slugify(s: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", s.lower()).strip("-")
    return s[:48] or "longform"


def truncate_text(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)].rstrip() + "…"


def normalize_tag(tag: str) -> str:
    return tag.strip().lstrip("#")


def markdown_to_html(text: str) -> str:
    """Small deterministic Markdown subset for API draft previews.

    This intentionally avoids depending on a renderer. The payload also keeps the
    original Markdown in `content` so downstream platform-specific renderers can
    replace this HTML later.
    """
    parts: list[str] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        block = block.strip()
        if not block:
            continue
        if block.startswith("# "):
            parts.append(f"<h1>{html.escape(block[2:].strip())}</h1>")
        elif block.startswith("## "):
            parts.append(f"<h2>{html.escape(block[3:].strip())}</h2>")
        elif block.startswith("### "):
            parts.append(f"<h3>{html.escape(block[4:].strip())}</h3>")
        else:
            parts.append("<p>" + html.escape(block).replace("\n", "<br/>") + "</p>")
    return "\n".join(parts)


def validate_cover(base: pathlib.Path, data: dict[str, Any]) -> tuple[str | None, list[str]]:
    assets = data.get("assets") if isinstance(data.get("assets"), dict) else {}
    cover_raw = assets.get("cover") if isinstance(assets, dict) else None
    if not cover_raw:
        return None, []
    p = resolve(base, str(cover_raw))
    if not p or not p.exists():
        return None, [f"cover image not found: {p}"]
    if p.suffix.lower() not in IMAGE_EXTS:
        return None, [f"unsupported cover image extension: {p}"]
    return str(p), []


def build_payloads(data: dict[str, Any], body_text: str, cover: str | None) -> dict[str, dict[str, Any]]:
    title = str(data.get("title", "")).strip()
    tags = [normalize_tag(str(t)) for t in (data.get("tags") or []) if str(t).strip()]
    mode = str(data.get("mode", "draft"))
    author = str(data.get("author") or (data.get("metadata") or {}).get("author") or "") if isinstance(data.get("metadata", {}), dict) else str(data.get("author") or "")
    summary = str(data.get("summary") or "").strip()
    digest = truncate_text(summary or re.sub(r"\s+", " ", re.sub(r"[#>*_`\-]", "", body_text)).strip(), 120)
    source_url = str((data.get("metadata") or {}).get("source_url") or data.get("content_source_url") or "") if isinstance(data.get("metadata", {}), dict) else str(data.get("content_source_url") or "")
    cta = str(data.get("cta") or "").strip()
    article_body = body_text.strip() + (("\n\n" + cta) if cta else "")

    return {
        "wechat-article": {
            "title": truncate_text(title, 64),
            "author": author,
            "digest": digest,
            "content": article_body,
            "html": markdown_to_html(article_body),
            "content_source_url": source_url,
            "cover": cover,
            "tags": tags,
            "mode": mode,
            "notes": ["微信公众号草稿标题按 64 字截断", "payload 可直接用于 wechat_api_draft.py draft-from-payload --dry-run", "真实 API 草稿需要 thumb_media_id 或上传 cover"],
        },
        "x-article": {
            "title": title,
            "body": article_body,
            "content": article_body,
            "cover": cover,
            "tags": tags,
            "mode": mode,
            "notes": ["X Articles 连接器未验证；默认只生成草稿 payload", "不要误用为短推文/thread"],
        },
        "substack": {
            "title": title,
            "subtitle": summary,
            "body": article_body,
            "content": article_body,
            "cover": cover,
            "tags": tags,
            "mode": mode,
            "notes": ["Substack 连接器未验证；默认只生成草稿 payload", "发送 newsletter 前必须再次确认"],
        },
    }


def preview_markdown(data: dict[str, Any], payloads: dict[str, dict[str, Any]], targets: list[str], source_body: str | None, errors: list[str]) -> str:
    lines = [
        "# Longform Preview",
        "",
        f"- Source title: {data.get('title', '')}",
        f"- Source body: {source_body or 'inline'}",
        f"- Mode: {data.get('mode', 'draft')}",
        f"- Targets: {', '.join(targets)}",
        "",
    ]
    if errors:
        lines += ["## Validation Errors", ""] + [f"- {e}" for e in errors] + [""]
    for target in targets:
        payload = payloads[target]
        body = str(payload.get("body") or payload.get("content") or "")
        lines += [
            f"## {target}",
            "",
            f"- Title: {payload.get('title', '')}",
            f"- Cover: {payload.get('cover') or '(none)'}",
            f"- Tags: {', '.join(payload.get('tags') or []) or '(none)'}",
            f"- Mode: {payload.get('mode')}",
            "",
            "### Content excerpt",
            "",
            truncate_text(body, 1200),
            "",
            "### Notes",
            "",
        ] + [f"- {n}" for n in payload.get("notes", [])] + [""]
    lines += ["## Next Step", "", "Review payloads, then confirm before any external draft/API/browser write."]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", type=pathlib.Path)
    ap.add_argument("--runs-dir", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1] / "runs")
    ap.add_argument("--copy-assets", action="store_true", help="Copy cover into the run directory and use copied path in payloads")
    args = ap.parse_args()

    manifest = args.manifest.resolve()
    data = yaml_load(manifest)
    base = manifest.parent
    errors: list[str] = []

    if data.get("type") != "longform":
        errors.append("manifest type must be longform")
    if data.get("mode", "draft") not in {"draft", "publish"}:
        errors.append("mode must be draft or publish")
    if not str(data.get("title") or "").strip():
        errors.append("title is required")

    targets = data.get("targets") or DEFAULT_TARGETS
    targets = [str(t) for t in targets]
    unsupported = [t for t in targets if t not in SUPPORTED_TARGETS]
    if unsupported:
        errors.append(f"unsupported longform targets for MVP: {', '.join(unsupported)}")

    body_text, source_body = read_body(base, str(data.get("body", "")))
    if not body_text.strip():
        errors.append("longform requires non-empty body content")

    cover, cover_errors = validate_cover(base, data)
    errors.extend(cover_errors)

    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = args.runs_dir / f"{ts}-{slugify(str(data.get('title', 'longform')))}"
    packs_dir = run_dir / "packs"
    packs_dir.mkdir(parents=True, exist_ok=True)

    if args.copy_assets and cover:
        asset_dir = run_dir / "assets"
        asset_dir.mkdir(exist_ok=True)
        src = pathlib.Path(cover)
        dst = asset_dir / f"cover{src.suffix.lower()}"
        shutil.copy2(src, dst)
        cover = str(dst.resolve())

    payloads = build_payloads(data, body_text, cover)
    selected_payloads = {t: payloads[t] for t in targets if t in payloads}

    (run_dir / "manifest.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    for target, payload in selected_payloads.items():
        d = packs_dir / target
        d.mkdir(exist_ok=True)
        (d / "payload.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        body = payload.get("body") or payload.get("content") or ""
        (d / "content.md").write_text(textwrap.dedent(f"""\
        ---
        target: {target}
        type: longform
        mode: {payload.get('mode')}
        title: {json.dumps(payload.get('title', ''), ensure_ascii=False)}
        ---

        {body}
        """), encoding="utf-8")

    preview = preview_markdown(data, payloads, targets, source_body, errors)
    (run_dir / "preview.md").write_text(preview, encoding="utf-8")
    (run_dir / "result.json").write_text(json.dumps({"status": "blocked" if errors else "prepared", "errors": errors, "targets": targets, "results": []}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"ok": not errors, "run_dir": str(run_dir), "preview": str(run_dir / "preview.md"), "targets": targets, "errors": errors}, ensure_ascii=False, indent=2))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
