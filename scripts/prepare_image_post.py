#!/usr/bin/env python3
"""Prepare an image-post run pack for Xiaohongshu + WeChat image content.

This script is deliberately offline-only: it validates input, resolves local
paths, generates platform payloads and previews, and writes a run directory.
It never opens browsers and never publishes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import shutil
import sys
import textwrap

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
DEFAULT_TARGETS = ["xiaohongshu", "wechat-image"]


def simple_yaml_load(text: str) -> dict:
    data: dict = {}
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
            container = [] if key in {"targets", "images", "tags"} else {}
            if isinstance(parent, dict):
                parent[key] = container
            stack.append((indent, container))
        else:
            val = val.split(" #", 1)[0].strip().strip('"\'')
            if isinstance(parent, dict):
                parent[key] = val
    return data


def yaml_load(path: pathlib.Path) -> dict:
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text) if yaml else simple_yaml_load(text)
    if not isinstance(data, dict):
        raise SystemExit("Manifest must be a YAML mapping/object")
    return data


def resolve(base: pathlib.Path, value: str) -> pathlib.Path:
    p = pathlib.Path(value).expanduser()
    return p if p.is_absolute() else (base / p).resolve()


def read_body(base: pathlib.Path, body: str) -> tuple[str, str | None]:
    p = resolve(base, body)
    if p.exists() and p.is_file():
        return p.read_text(encoding="utf-8"), str(p)
    return body, None


def slugify(s: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", s.lower()).strip("-")
    return s[:48] or "image-post"


def truncate_text(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)].rstrip() + "…"


def normalize_tag(tag: str) -> str:
    return tag.strip().lstrip("#")


def validate_images(base: pathlib.Path, images: list) -> tuple[list[str], list[str]]:
    resolved: list[str] = []
    errors: list[str] = []
    for raw in images:
        p = resolve(base, str(raw))
        if not p.exists():
            errors.append(f"image not found: {p}")
            continue
        if p.suffix.lower() not in IMAGE_EXTS:
            errors.append(f"unsupported image extension: {p}")
            continue
        resolved.append(str(p))
    return resolved, errors


def build_payloads(data: dict, body_text: str, images: list[str]) -> dict[str, dict]:
    title = str(data.get("title", "")).strip()
    tags = [normalize_tag(str(t)) for t in (data.get("tags") or []) if str(t).strip()]
    cta = str(data.get("cta", "")).strip()
    xhs_content = body_text.strip()
    if tags:
        xhs_content = xhs_content + "\n\n" + " ".join(f"#{t}" for t in tags)
    if cta:
        xhs_content = xhs_content + "\n\n" + cta

    return {
        "xiaohongshu": {
            "title": truncate_text(title, 20),
            "content": truncate_text(xhs_content, 1000),
            "images": images[:9],
            "tags": tags,
            "mode": data.get("mode", "draft"),
            "notes": ["小红书标题按 20 字截断", "图片最多取前 9 张", "默认仅准备/草稿，不发布"],
        },
        "wechat-image": {
            "title": title,
            "content": body_text.strip() + (("\n\n" + cta) if cta else ""),
            "images": images,
            "cover": images[0] if images else None,
            "tags": tags,
            "mode": data.get("mode", "draft"),
            "notes": ["微信图文 UI 首次执行需人工校准", "默认保存草稿/等待确认，不群发"],
        },
        # API-compatible bridge payload. This lets the same prepared image-post
        # package be smoke-tested with wechat_api_draft.py dry-run when the
        # operator chooses to treat 微信图文内容 as a 公众号草稿 fallback.
        "wechat-article": {
            "title": truncate_text(title, 64),
            "content": body_text.strip() + (("\n\n" + cta) if cta else ""),
            "cover": images[0] if images else None,
            "tags": tags,
            "mode": data.get("mode", "draft"),
            "digest": truncate_text(re.sub(r"\s+", " ", body_text).strip(), 120),
            "notes": ["由 image-post 生成的公众号 API 兼容 payload", "可用于 wechat_api_draft.py draft-from-payload --dry-run", "真实 API 草稿需要 thumb_media_id 或上传 cover"],
        },
    }


def preview_markdown(data: dict, payloads: dict[str, dict], targets: list[str], source_body: str | None, errors: list[str]) -> str:
    lines = [
        "# Image Post Preview",
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
        lines += [
            f"## {target}",
            "",
            f"- Title: {payload.get('title', '')}",
            f"- Images: {len(payload.get('images') or [])}",
            f"- Tags: {', '.join(payload.get('tags') or []) or '(none)'}",
            f"- Mode: {payload.get('mode')}",
            "",
            "### Content",
            "",
            str(payload.get("content", "")),
            "",
            "### Notes",
            "",
        ] + [f"- {n}" for n in payload.get("notes", [])] + [""]
    lines += [
        "## Next Step",
        "",
        "Confirm before any external browser/API write. Recommended first action: create drafts only.",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", type=pathlib.Path)
    ap.add_argument("--runs-dir", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1] / "runs")
    ap.add_argument("--copy-assets", action="store_true", help="Copy images into the run directory and use copied paths in payloads")
    args = ap.parse_args()

    manifest = args.manifest.resolve()
    data = yaml_load(manifest)
    base = manifest.parent
    errors: list[str] = []

    if data.get("type") != "image-post":
        errors.append("manifest type must be image-post")
    if data.get("mode", "draft") not in {"draft", "publish"}:
        errors.append("mode must be draft or publish")
    targets = data.get("targets") or DEFAULT_TARGETS
    targets = [str(t) for t in targets]
    unsupported = [t for t in targets if t not in {"xiaohongshu", "wechat-image"}]
    if unsupported:
        errors.append(f"unsupported image-post targets for MVP: {', '.join(unsupported)}")

    body_text, source_body = read_body(base, str(data.get("body", "")))
    images_raw = ((data.get("assets") or {}).get("images") or []) if isinstance(data.get("assets"), dict) else []
    images, image_errors = validate_images(base, images_raw)
    errors.extend(image_errors)
    if not images:
        errors.append("image-post requires at least one valid local image")

    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = args.runs_dir / f"{ts}-{slugify(str(data.get('title', 'image-post')))}"
    packs_dir = run_dir / "packs"
    packs_dir.mkdir(parents=True, exist_ok=True)

    if args.copy_assets and images:
        asset_dir = run_dir / "assets"
        asset_dir.mkdir(exist_ok=True)
        copied = []
        for i, src in enumerate(images, 1):
            sp = pathlib.Path(src)
            dst = asset_dir / f"{i:02d}{sp.suffix.lower()}"
            shutil.copy2(sp, dst)
            copied.append(str(dst.resolve()))
        images = copied

    payloads = build_payloads(data, body_text, images)
    selected_payloads = {t: payloads[t] for t in targets if t in payloads}

    (run_dir / "manifest.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    for target, payload in selected_payloads.items():
        d = packs_dir / target
        d.mkdir(exist_ok=True)
        (d / "payload.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (d / "content.md").write_text(textwrap.dedent(f"""\
        ---
        target: {target}
        type: image-post
        mode: {payload.get('mode')}
        title: {json.dumps(payload.get('title', ''), ensure_ascii=False)}
        ---

        {payload.get('content', '')}
        """), encoding="utf-8")

    if "wechat-image" in selected_payloads:
        bridge_dir = packs_dir / "wechat-article-api-bridge"
        bridge_dir.mkdir(exist_ok=True)
        bridge_payload = payloads["wechat-article"]
        (bridge_dir / "payload.json").write_text(json.dumps(bridge_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (bridge_dir / "content.md").write_text(textwrap.dedent(f"""\
        ---
        target: wechat-article
        source_target: wechat-image
        type: image-post-api-bridge
        mode: {bridge_payload.get('mode')}
        title: {json.dumps(bridge_payload.get('title', ''), ensure_ascii=False)}
        ---

        {bridge_payload.get('content', '')}
        """), encoding="utf-8")

    preview = preview_markdown(data, payloads, targets, source_body, errors)
    (run_dir / "preview.md").write_text(preview, encoding="utf-8")
    (run_dir / "result.json").write_text(json.dumps({"status": "blocked" if errors else "prepared", "errors": errors, "targets": targets, "results": []}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"ok": not errors, "run_dir": str(run_dir), "preview": str(run_dir / "preview.md"), "targets": targets, "errors": errors}, ensure_ascii=False, indent=2))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
