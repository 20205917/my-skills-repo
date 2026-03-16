---
name: agents-bootstrap
description: 以提示词优先的方式生成项目级 AGENTS.md（基于项目事实采集 + Prompt Contract + 草稿校验 + 差异预览），并保留全局级模板化初始化能力。
---

# AGENTS 初始化（提示词驱动）

始终以“最小改动、可验证、可回滚”为原则维护 AGENTS 文档。

## 策略总览

- 项目级：提示词优先，不再由脚本直接生成正文。
- 全局级：继续使用模板初始化（`assets/templates/global_concise.md`）。

## 项目级固定流程

1. 事实采集（脚本）
   - 从 `AGENTS.md`、`README.md`、`skills-index.md`、`skills/*/SKILL.md` 采集可验证事实。
2. Prompt Contract 生成（脚本）
   - 输出标准输入块：`PROJECT_FACTS`、`STYLE_RULES`、`PRESERVE_RULES`。
3. 人审预览（脚本）
   - 传入模型生成草稿后，先执行 `--dry-run`，查看草稿预览与 diff 摘要。
4. 写入与验证（脚本）
   - 草稿通过质量门槛后再落盘，记录覆盖与回滚信息。

## 推荐命令

```bash
# 1) 生成 Prompt Contract（只预览，不写入项目 AGENTS）
python3 skills/agents-bootstrap/scripts/init_agents_md.py \
  --scope project \
  --project-root . \
  --dry-run \
  --prompt-output ./tmp/project_agents_prompt.md

# 2) 将 Prompt Contract 提交给模型，获得草稿（示例：./tmp/project_agents_draft.md）

# 3) 草稿校验 + 预览差异（不写入）
python3 skills/agents-bootstrap/scripts/init_agents_md.py \
  --scope project \
  --project-root . \
  --draft-file ./tmp/project_agents_draft.md \
  --dry-run

# 4) 通过后写入（如目标已存在，需 --force）
python3 skills/agents-bootstrap/scripts/init_agents_md.py \
  --scope project \
  --project-root . \
  --draft-file ./tmp/project_agents_draft.md \
  --force

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
- `--draft-file <path>`（模型生成的项目级草稿）
- `--prompt-output <path>`（输出 Prompt Contract）
- `--force`（允许覆盖已有目标）
- `--dry-run`（仅预览，不写入）
- `--no-print-prompt`（不在终端打印 Prompt 正文）
- `--preview-lines <n>`（草稿预览行数）
- `--diff-lines <n>`（diff 预览行数）
- `--no-backup`（写入前不生成备份）

## 质量门槛

项目级草稿写入前必须通过：

- 包含必需章节：技能与入口、开发命令、测试、目录结构、维护约定。
- 不包含占位词：`TODO:`、`TODO：`、`请补充`、`待补充`。
- 技能名与入口路径、测试命令均可在项目事实中映射。
- 若事实缺失，必须使用 `## 待确认项` 显式列出。

## 输出要求

每次执行后应汇报：

1. 目标文件路径与写入结果。
2. 是否发生覆盖（`--force`）。
3. 项目级 `.gitignore` 更新结果。
4. 差异预览与回滚信息（若有写入）。
5. 验证加载优先级的操作步骤。
6. 可选 `config.toml` 片段（仅展示，不自动改写）。
