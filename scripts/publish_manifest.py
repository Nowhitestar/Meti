#!/usr/bin/env python3
"""Validate a multi-media-publisher manifest and create a run skeleton.

This intentionally does not publish. Dispatch should be handled by verified
platform skills with explicit user approval.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys

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

REQUIRED = {"type", "title", "body", "targets", "mode"}
VALID_TYPES = {"image-post", "longform", "video-post"}
VALID_MODES = {"draft", "publish"}


def load_manifest(path: pathlib.Path) -> dict:
    text = path.read_text(encoding="utf-8")
    data = yaml_load(text)
    if not isinstance(data, dict):
        raise SystemExit("Manifest must be a YAML mapping/object")
    return data


def validate(data: dict) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED - set(data))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if data.get("type") not in VALID_TYPES:
        errors.append(f"type must be one of {sorted(VALID_TYPES)}")
    if data.get("mode") not in VALID_MODES:
        errors.append(f"mode must be one of {sorted(VALID_MODES)}")
    if not isinstance(data.get("targets"), list) or not data.get("targets"):
        errors.append("targets must be a non-empty list")
    if data.get("type") == "image-post":
        images = ((data.get("assets") or {}).get("images") or []) if isinstance(data.get("assets"), dict) else []
        if not images:
            errors.append("image-post requires assets.images")
    return errors


def slugify(title: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", title.lower()).strip("-")
    return s[:48] or "run"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", type=pathlib.Path)
    ap.add_argument("--runs-dir", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1] / "runs")
    args = ap.parse_args()

    data = load_manifest(args.manifest)
    errors = validate(data)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False, indent=2))
        return 2

    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = args.runs_dir / f"{ts}-{slugify(str(data.get('title', 'run')))}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "result.json").write_text(json.dumps({"status": "planned", "targets": data["targets"], "results": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "run_dir": str(run_dir), "mode": data["mode"], "targets": data["targets"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
