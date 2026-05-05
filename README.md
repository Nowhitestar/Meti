# Multi-media Publisher / 多媒体发布

统一调度多平台内容发布的 OpenClaw skill / Claude Code plugin。

## 现状（v0.2 进行中）

- 架构：`core/` + `providers/<name>/` + `scripts/mmp.py`
- 已迁移：`wechat-article` 全链路（validate/prepare/execute draft）
- 进行中：`wizard`（Plan 2）、其他 4 个 provider（Plan 3）、CC plugin + CI（Plan 4）

详见：

- 设计：[docs/superpowers/specs/2026-05-05-multi-media-publisher-redesign-design.md](docs/superpowers/specs/2026-05-05-multi-media-publisher-redesign-design.md)
- 计划：[docs/superpowers/plans/](docs/superpowers/plans/)
- 交接：[docs/HANDOFF.md](docs/HANDOFF.md)
- Skill：[SKILL.md](SKILL.md)

## 安装

```bash
python3 -m pip install -e ".[dev]"
```

## 用法

```bash
# 校验
python3 scripts/mmp.py validate examples/longform.yaml

# 配置凭证
python3 scripts/mmp.py setup wechat-article

# 发布（默认 draft 模式）
python3 scripts/mmp.py publish examples/longform.yaml

# 自检
python3 scripts/mmp.py doctor

# 测试
make test
```

## 安全策略

- 默认 `draft` 模式
- 公开发布要求显式 `publish` 模式 + 对话二次确认
- 凭证存于 age 加密的 `~/.config/mmp/credentials.json.age`
- 详见 `docs/safety-policy.md`
