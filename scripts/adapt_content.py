#!/usr/bin/env python3
"""Create lightweight per-platform content pack scaffolds from a manifest."""
from __future__ import annotations

import argparse
import json
import pathlib
import textwrap

try:
    import yaml  # type: ignore
except Exception:
    yaml = None


def simple_yaml_load(text: str) -> dict:
    """Tiny fallback parser for the simple manifests in this skill."""
    data: dict = {}
    stack: list[tuple[int, object]] = [(-1, data)]
    last_key_at_indent: dict[int, str] = {}
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if line.startswith("- "):
            item = line[2:].strip().strip('"\'')
            if isinstance(parent, list):
                parent.append(item)
            continue
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip()
        val = val.strip()
        if val == "":
            # Heuristic: common list containers vs mapping containers.
            container = [] if key in {"targets", "images", "tags"} else {}
            if isinstance(parent, dict):
                parent[key] = container
            stack.append((indent, container))
            last_key_at_indent[indent] = key
        else:
            val = val.split(" #", 1)[0].strip().strip('"\'')
            if isinstance(parent, dict):
                parent[key] = val
    return data


def yaml_load(text: str) -> dict:
    if yaml:
        return yaml.safe_load(text)
    return simple_yaml_load(text)


def resolve_path(base: pathlib.Path, value: str) -> pathlib.Path:
    p = pathlib.Path(value)
    return p if p.is_absolute() else (base / p).resolve()


def read_body(base: pathlib.Path, body: str) -> str:
    p = resolve_path(base, body)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return body


def existing_images(base: pathlib.Path, data: dict) -> list[str]:
    assets = data.get("assets") if isinstance(data.get("assets"), dict) else {}
    images = assets.get("images") or []
    out = []
    for img in images:
        p = resolve_path(base, str(img))
        out.append(str(p))
    return out


def payload_for(target: str, data: dict, body: str, base: pathlib.Path) -> dict:
    title = str(data.get("title", ""))
    images = existing_images(base, data)
    tags = data.get("tags", []) or []
    if target == "xiaohongshu":
        return {"title": title[:20], "content": body[:1000], "images": images, "tags": tags}
    if target == "wechat-image":
        cover = images[0] if images else ((data.get("assets") or {}).get("cover") if isinstance(data.get("assets"), dict) else None)
        return {"title": title, "content": body, "images": images, "cover": cover, "mode": data.get("mode", "draft")}
    return {"title": title, "content": body, "images": images, "tags": tags, "mode": data.get("mode", "draft")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    args = ap.parse_args()
    data = yaml_load(args.manifest.read_text(encoding="utf-8"))
    base = args.manifest.parent
    body = read_body(base, str(data.get("body", "")))
    args.out.mkdir(parents=True, exist_ok=True)

    for target in data.get("targets", []):
        target_dir = args.out / str(target)
        target_dir.mkdir(parents=True, exist_ok=True)
        title = str(data.get("title", ""))
        adapted_title = title[:20] if target == "xiaohongshu" else title
        md = textwrap.dedent(f"""\
        ---
        target: {target}
        source_type: {data.get('type')}
        mode: {data.get('mode')}
        title: {adapted_title!r}
        tags: {json.dumps(data.get('tags', []), ensure_ascii=False)}
        ---

        {body}
        """)
        (target_dir / "content.md").write_text(md, encoding="utf-8")
        (target_dir / "payload.json").write_text(json.dumps(payload_for(str(target), data, body, base), ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"ok": True, "out": str(args.out), "targets": data.get("targets", [])}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
