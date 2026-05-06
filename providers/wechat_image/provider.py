"""WeChat 图文内容 provider — emits a browser-flow guide for the user.

The browser path to mp.weixin.qq.com is currently blocked under OpenClaw policy,
so this provider does NOT automate the upload. Instead, it produces a
step-by-step Markdown guide the user follows in their own browser.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.provider import (
    ExecutionResult,
    HealthStatus,
    PreparedPayload,
    Provider,
    ValidationResult,
)
from providers.wechat_image.rules import WECHAT_IMAGE_RULES

_GUIDE_TEMPLATE = """\
# WeChat 图文内容 — 手动执行指南

> 自动化未启用：浏览器对 mp.weixin.qq.com 的访问被策略阻止。请按下面的步骤手动完成。

## Payload

文件：`{payload_path}`

字段：

- **标题**：`{title}`
- **正文**：见 `content.md`
- **图片**（{n_images} 张）：
{image_list}
- **CTA**：{cta}

## 操作步骤

1. 打开 https://mp.weixin.qq.com/ 并登录目标公众号。
2. 顶部菜单选择 **图文素材** → **新建图文素材**（图文内容）。
3. 填入标题、摘要（如有）。
4. 把上面列出的每张图片按顺序上传。
5. 把 `content.md` 内容粘贴到正文。
6. 点击 **保存草稿**。**不要点发布**。
7. 回到这里继续后续动作或确认草稿状态。

## 安全提示

- 不要绕过登录或验证码。
- 不要导出 cookie 文件到任何外部位置。
- 草稿确认后，如需公开发布，使用公众号原生的"群发"功能。
"""


class WeChatImageProvider(Provider):
    name = "wechat-image"
    display_name = "微信图文内容"
    media_types = ["image-post"]
    capabilities = {"draft": True, "publish": False, "schedule": False}
    required_credentials = []
    platform_rules = WECHAT_IMAGE_RULES

    def validate(self, manifest: Any, target: Any) -> ValidationResult:
        return ValidationResult(violations=self.platform_rules.lint(manifest, self.name))

    def prepare(self, manifest: Any, target: Any, run_dir: Path) -> PreparedPayload:
        pack_dir = run_dir / "packs" / self.name
        pack_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "title": manifest.title,
            "caption": manifest.body,
            "images": list(manifest.images or []),
            "cta": manifest.cta,
            "mode": target.mode,
            "options": dict(target.options or {}),
        }
        payload_path = pack_dir / "payload.json"
        payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        (pack_dir / "content.md").write_text(manifest.body or "", encoding="utf-8")
        return PreparedPayload(pack_dir=pack_dir, payload_path=payload_path)

    def execute(
        self,
        run_dir: Path,
        target: Any,
        mode: str,
        credentials: dict[str, str],
    ) -> ExecutionResult:
        if mode == "publish":
            raise NotImplementedError("wechat-image publish path not supported in v0.2")
        if mode == "dry-run":
            return ExecutionResult(status="ok", mode_actual="dry-run", external_id=None)

        # mode == draft → write a browser-flow guide
        pack_dir = run_dir / "packs" / self.name
        payload_path = pack_dir / "payload.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        image_list = "\n".join(f"   - `{img}`" for img in payload["images"]) or "   - (none)"
        guide = _GUIDE_TEMPLATE.format(
            payload_path=str(payload_path),
            title=payload["title"],
            n_images=len(payload["images"]),
            image_list=image_list,
            cta=payload.get("cta") or "(none)",
        )
        guide_path = pack_dir / "browser-flow.md"
        guide_path.write_text(guide, encoding="utf-8")
        return ExecutionResult(
            status="ok",
            mode_actual="draft-local",
            external_id=None,
            extras={"guide_path": str(guide_path)},
        )

    def health_check(self, credentials: dict[str, str]) -> HealthStatus:
        return HealthStatus.unknown
