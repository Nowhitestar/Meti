#!/usr/bin/env python3
"""Local smoke test for the multi-media-publisher MVP.

Covers:
- py_compile for bundled scripts
- image-post prepare
- execute WeChat browser-flow guide
- Xiaohongshu local draft creation (no external publish)
- WeChat Official Account API dry-run from the generated bridge payload
- longform prepare for wechat-article/x-article/substack
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run(cmd: list[str], *, env: dict[str, str] | None = None, cwd: pathlib.Path | None = None, capture: bool = False) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(cmd))
    return subprocess.run(cmd, cwd=str(cwd or ROOT), env=env, text=True, capture_output=capture, check=True)


def write_png(path: pathlib.Path) -> None:
    raw = b"\x00\x00\x00\x00\x00"

    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)



def write_xhs_draft_stub(path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
mkdir -p "${XHS_DRAFT_DIR:?XHS_DRAFT_DIR required}"
out="$XHS_DRAFT_DIR/test-draft.json"
printf '%s' "$1" > "$out"
echo "✓ 已创建本地草稿: $out"
""",
        encoding="utf-8",
    )
    path.chmod(0o755)

def fixtures(tmp: pathlib.Path) -> pathlib.Path:
    ex = tmp / "examples"
    ex.mkdir(parents=True)
    (ex / "caption.md").write_text("第一段正文。\n\n第二段正文。\n", encoding="utf-8")
    (ex / "article.md").write_text("# 长文正文\n\n这是一篇用于本地测试的长文章。\n\n## 小节\n\n继续展开观点。\n", encoding="utf-8")
    for name in ["01.png", "02.png", "cover.png"]:
        write_png(ex / name)
    (ex / "image-post.yaml").write_text(
        """type: image-post
title: "AI 创业的三个误区"
body: ./caption.md
mode: draft
language: zh-CN
targets:
  - xiaohongshu
  - wechat-image
assets:
  images:
    - ./01.png
    - ./02.png
tags:
  - AI
  - 创业
cta: "欢迎留言聊聊你的看法。"
""",
        encoding="utf-8",
    )
    (ex / "longform.yaml").write_text(
        """type: longform
title: "AI Agent 不是工具，而是一种新的组织形态"
summary: "本地测试用摘要。"
body: ./article.md
mode: draft
language: zh-CN
targets:
  - wechat-article
  - x-article
  - substack
assets:
  cover: ./cover.png
tags:
  - AI
  - Agent
  - 组织
""",
        encoding="utf-8",
    )
    return ex


def main() -> int:
    tmp = pathlib.Path(os.environ.get("MMP_TEST_TMPDIR", tempfile.mkdtemp(prefix="mmp-local-test-"))).resolve()
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    runs = tmp / "runs"
    runs.mkdir()
    ex = fixtures(tmp)

    scripts = [
        "adapt_content.py",
        "publish_manifest.py",
        "prepare_image_post.py",
        "execute_image_post.py",
        "wechat_api_draft.py",
        "prepare_longform.py",
        "test_local.py",
    ]
    run([sys.executable, "-m", "py_compile", *[str(SCRIPTS / s) for s in scripts]])

    image_prepare = run(
        [sys.executable, str(SCRIPTS / "prepare_image_post.py"), str(ex / "image-post.yaml"), "--runs-dir", str(runs), "--copy-assets"],
        capture=True,
    )
    image_out = json.loads(image_prepare.stdout)
    assert image_out["ok"], image_out
    image_run = pathlib.Path(image_out["run_dir"])
    for rel in ["packs/xiaohongshu/payload.json", "packs/wechat-image/payload.json", "packs/wechat-article-api-bridge/payload.json", "preview.md"]:
        assert (image_run / rel).exists(), rel

    run([sys.executable, str(SCRIPTS / "execute_image_post.py"), str(image_run), "--target", "wechat-image"])
    assert (image_run / "packs/wechat-image/browser-flow.md").exists()

    stub_xhs = tmp / "bin" / "draft.sh"
    write_xhs_draft_stub(stub_xhs)
    env = os.environ.copy()
    env["XHS_DRAFT_DIR"] = str(tmp / "xhs-drafts")
    env["MMP_XHS_DRAFT_SH"] = str(stub_xhs)
    run([sys.executable, str(SCRIPTS / "execute_image_post.py"), str(image_run), "--target", "xiaohongshu", "--yes-draft"], env=env)
    assert any((tmp / "xhs-drafts").glob("*.json"))

    api = run(
        [sys.executable, str(SCRIPTS / "wechat_api_draft.py"), "draft-from-payload", str(image_run / "packs/wechat-article-api-bridge/payload.json"), "--dry-run"],
        capture=True,
    )
    api_out = json.loads(api.stdout)
    assert api_out["ok"], api_out
    assert api_out["draft"]["dry_run"] is True, api_out
    assert api_out["upload"]["dry_run"] is True, api_out

    longform_prepare = run(
        [sys.executable, str(SCRIPTS / "prepare_longform.py"), str(ex / "longform.yaml"), "--runs-dir", str(runs), "--copy-assets"],
        capture=True,
    )
    longform_out = json.loads(longform_prepare.stdout)
    assert longform_out["ok"], longform_out
    longform_run = pathlib.Path(longform_out["run_dir"])
    for rel in ["packs/wechat-article/payload.json", "packs/x-article/payload.json", "packs/substack/payload.json", "preview.md"]:
        assert (longform_run / rel).exists(), rel
    wechat = json.loads((longform_run / "packs/wechat-article/payload.json").read_text(encoding="utf-8"))
    assert wechat["html"].startswith("<h1>"), wechat

    print(json.dumps({"ok": True, "tmp": str(tmp), "image_run": str(image_run), "longform_run": str(longform_run)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
