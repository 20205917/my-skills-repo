---
name: data-generator
description: 基于 MySQL 或 PostgreSQL 的 DDL，为 Java 后端测试生成可复现的 SQL/JSON 关系型测试数据。用于用户希望按表结构、字段约束和业务规则快速产出可导入数据的场景；默认严格满足 PK/UK/FK、父表先于子表插入顺序与基础时间逻辑（如 created_at 不晚于 updated_at、start_time 不晚于 end_time）。支持工业场景实体模板（产线、设备、工位、传感器、告警、工单、维护、库存、班次等），支持按 xxx_id 命名规则推断未声明外键，并支持 YAML/JSON 显式覆盖推断结果。默认仅生成合法数据，异常或脏数据仅在用户明确要求时开启。
---

# 数据生成器

## 最小澄清

仅在缺失时补问以下信息：

1. 目标数据库与版本（默认 `mysql 8` 或 `postgres 14`）。
2. DDL 文件路径，以及是否提供 schema 覆盖文件。
3. 数据规模（`100` 样例或 `100000+` 压测）与输出布局（SQL 按表拆分、JSON 单文件或多文件）。

## 执行流程

1. 读取 DDL，解析表、字段与约束元数据。
2. 读取可选覆盖文件（YAML/JSON，支持 `rows` 与显式 FK 映射）。
3. 按以下优先级确定外键：
   - 用户覆盖
   - DDL 显式外键
   - 命名推断（`xxx_id`、`device_id`、`line_id`、`work_order_id`、`tenant_id`、`org_id`）
   - PK/UK 单列匹配
4. 对表做拓扑排序，保证父表先插入、子表后插入。
5. 默认生成合法数据：
   - 满足类型、NOT NULL、默认值。
   - 保证 PK/UK 唯一。
   - 保证 FK 可引用。
   - 尽量满足时间逻辑。
6. 仅在用户明确提出时开启脏数据模式（`--invalid-mode` 或 `--dirty-data`）。
7. 生成后校验 PK/UK/FK 与插入顺序。
8. 导出 SQL/JSON 与汇总文件。

## 命令示例

### 小样本（默认 100 行，输出 SQL + JSON）

```bash
python3 scripts/generate_test_data.py \
  --ddl ./schema.sql \
  --db-dialect mysql \
  --rows 100 \
  --seed 42 \
  --formats sql,json \
  --output-dir ./generated-sample
```

### 大样本（100000 行，混合按表覆盖）

```bash
python3 scripts/generate_test_data.py \
  --ddl ./schema.sql \
  --db-dialect postgres \
  --rows 100000 \
  --devices 5000 \
  --table-rows alarms=120000 \
  --table-rows work_orders=30000 \
  --batch-size 5000 \
  --seed 42 \
  --json-layout single \
  --formats sql,json \
  --output-dir ./generated-load
```

### 显式覆盖 FK（推断存在歧义时推荐）

```bash
python3 scripts/generate_test_data.py \
  --ddl ./schema.sql \
  --schema-override ./schema-override.yaml \
  --rows 10000 \
  --formats sql,json
```

### 脏数据模式（仅在明确要求时启用）

```bash
python3 scripts/generate_test_data.py \
  --ddl ./schema.sql \
  --rows 1000 \
  --invalid-mode \
  --invalid-ratio 0.03 \
  --invalid-target alarms.severity,work_orders
```

## 输出规则

- SQL 输出到 `output/sql/*.sql`，每张表一个文件。
- JSON 输出到 `output/json/`：
  - `per-table` 或 `auto`：每张表一个文件。
  - `single`：合并为一个 `data.json`。
- 生成 `summary.json`，记录推断/覆盖的外键、插入顺序、行数计划与校验结果。

## 参考资料

- [references/schema-spec.md](references/schema-spec.md)：DDL 解析范围与覆盖格式。
- [references/industrial-templates.md](references/industrial-templates.md)：工业实体模板、关系与数值分布建议。
- [references/db-import.md](references/db-import.md)：MySQL/PostgreSQL 导入与批量建议。

## 护栏

- 默认合法模式；未明确要求时不要生成脏数据。
- 合法模式校验失败时立即停止，并要求提供覆盖文件或补充业务规则。
- 固定 `--seed` 以保证可复现。
