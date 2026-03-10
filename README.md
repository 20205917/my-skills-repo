# My Skills Repo

个人技能仓库，用于沉淀可复用的 `SKILL.md` 工作流与配套脚本。

## 当前技能

- `data-generator`
  - 位置：`skills/data-generator/`
  - 用途：根据 MySQL/PostgreSQL DDL 生成满足 PK/UK/FK 约束的 SQL/JSON 测试数据。
- `personal-workstyle`
  - 位置：`skills/personal-workstyle/`
  - 用途：管理长期工作规则（`active / pending / history`）并执行规则变更流程。

## 快速开始

### 1. 生成测试数据

```bash
python3 skills/data-generator/scripts/generate_test_data.py \
  --ddl ./schema.sql \
  --db-dialect mysql \
  --rows 100 \
  --seed 42 \
  --formats sql,json \
  --output-dir ./generated-sample
```

### 2. 管理个人规则

```bash
python3 skills/personal-workstyle/scripts/rules.py list
python3 skills/personal-workstyle/scripts/rules.py add "新规则内容"
python3 skills/personal-workstyle/scripts/rules.py pending
```

## 测试

仓库使用 Python 标准库 `unittest`，无需额外安装测试框架：

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

## 目录结构

```text
skills/
  data-generator/
    SKILL.md
    scripts/
    references/
    agents/openai.yaml
  personal-workstyle/
    SKILL.md
    scripts/
    rules/
    templates/
    agents/openai.yaml
tests/
skills-index.md
```

## 维护约定

- 每个 skill 至少包含：`SKILL.md`、`agents/openai.yaml`、必要的 `scripts/` 与参考文档。
- `agents/openai.yaml` 统一使用以下结构：
  - `version: 1`
  - `skill.display_name`
  - `skill.short_description`
  - `skill.default_prompt`
- 新增或修改核心脚本时，同时补充对应测试用例。
