# AGENTS 开发指南

本文件是 AI 优先读取的开发与维护文档，承接原 README 中的开发者内容。

## 当前技能与位置

- `bug-fix-loop`
  - 位置：`skills/bug-fix-loop/`
  - 入口：`skills/bug-fix-loop/SKILL.md`
- `data-generator`
  - 位置：`skills/data-generator/`
  - 入口：`skills/data-generator/scripts/generate_test_data.py`
- `dev2release`
  - 位置：`skills/dev2release/`
  - 入口：`skills/dev2release/scripts/conventional_changelog.py`
- `xlsx2json`
  - 位置：`skills/xlsx2json/`
  - 入口：`skills/xlsx2json/scripts/xlsx_to_json.py`

## 开发者快速命令

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

### 2. 生成 Conventional Changelog 条目

```bash
python3 skills/dev2release/scripts/conventional_changelog.py \
  --from-ref "$(git describe --tags --abbrev=0)" \
  --to-ref HEAD \
  --version 1.2.3 \
  --date 2026-03-11
```

### 3. XLSX 转 JSON

```bash
python3 skills/xlsx2json/scripts/xlsx_to_json.py \
  --xlsx ./input.xlsx \
  --output ./output.json \
  --map "名称=name" \
  --enum "状态:启用=1" \
  --enum "状态:禁用=0"
```

## 测试

仓库使用 Python 标准库 `unittest`：

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

## 目录结构

```text
skills/
  bug-fix-loop/
    SKILL.md
    agents/openai.yaml
  data-generator/
    SKILL.md
    scripts/
    references/
    agents/openai.yaml
  dev2release/
    SKILL.md
    scripts/
    references/
    agents/openai.yaml
  xlsx2json/
    SKILL.md
    scripts/
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
