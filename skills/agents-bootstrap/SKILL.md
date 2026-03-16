---
name: agents-bootstrap
description: 以模板优先的方式初始化与维护 Codex 的 AGENTS.md（默认项目级 仓库根目录/AGENTS.md；仅在用户明确要求时生成全局级 ~/.codex/AGENTS.md）。用于用户要求新建 AGENTS.md、搭建全局规则、落地项目规则、从 README 迁移开发维护说明、或校验 AGENTS 加载优先级时。
---

# AGENTS 初始化

始终以“最小改动、可验证、可回滚”为原则初始化 AGENTS 文档。

## 模板优先原则

优先使用模板完成初始化，脚本仅用于自动填充与批量执行：

- 项目级模板：`assets/templates/project_concise.md`
- 全局级模板：`assets/templates/global_concise.md`
- 全局级模板仅承载个人长期规则与通用工程纪律，不包含项目命令、目录结构、技术栈与发布流程。

## 执行流程

1. 先选模板再定范围
   - 默认项目级模板与项目级写入。
   - 仅在用户明确指出“全局级”时，才生成全局级文件。
2. 探测目标路径
   - 全局级：`~/.codex/AGENTS.md`
   - 项目级：`<project-root>/AGENTS.md`
3. 先预览再写入
   - 默认先执行 `--dry-run` 预览目标路径和摘要。
   - 仅在确认无误后执行实际写入。
4. 默认安全不覆盖
   - 若目标文件已存在且未传 `--force`，必须中止并提示。
5. 项目级默认写入 `.gitignore`
   - 生成项目级 `AGENTS.md` 后，默认将 `AGENTS.md` 加入项目 `.gitignore`（无重复追加）。
6. 写入后验证加载优先级
   - 让 Codex 输出当前加载到的指令来源，确认全局级与项目级生效顺序符合预期。

## 推荐命令

```bash
# 先预览（推荐）
python3 skills/agents-bootstrap/scripts/init_agents_md.py \
  --project-root . \
  --dry-run

# 再写入
python3 skills/agents-bootstrap/scripts/init_agents_md.py \
  --project-root .

# 仅在明确需要时生成全局级
python3 skills/agents-bootstrap/scripts/init_agents_md.py \
  --scope global
```

## 脚本接口

`skills/agents-bootstrap/scripts/init_agents_md.py` 支持：

- `--scope global|project|both`（默认 `project`）
- `--project-root <path>`（默认当前目录）
- `--codex-home <path>`（默认 `~/.codex`）
- `--style concise`（当前仅支持 `concise`）
- `--force`（允许覆盖）
- `--dry-run`（仅预览，不写入）

## 输出要求

每次执行后必须给出：

1. 目标文件路径与写入结果。
2. 是否发生覆盖（`--force`）。
3. 项目级 `.gitignore` 更新结果。
4. 验证加载优先级的操作步骤。
5. 可选 `config.toml` 片段（仅展示，不自动改写）。
