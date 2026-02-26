# Schema 规范

## 解析范围

`generate_test_data.py` 面向常见 MySQL/PostgreSQL DDL 语法。

重点支持：

- `CREATE TABLE ... (...);`
- 字段类型、可空、默认值解析
- 主键（`PRIMARY KEY` 行内或表级）
- 唯一键（`UNIQUE`、`UNIQUE KEY`、`UNIQUE INDEX`）
- 外键（`FOREIGN KEY ... REFERENCES ...`、行内 `REFERENCES`）

当前不覆盖（有意简化）：

- 分区表
- 生成列
- 触发器/存储过程
- 复杂表达式校验
- 视图/物化视图自动造数

## 外键决策优先级

严格按以下顺序执行：

1. 用户覆盖（`--schema-override`）
2. DDL 显式外键
3. 命名推断（`xxx_id`、`device_id`、`line_id`、`tenant_id`、`org_id`）
4. PK/UK 单列匹配

当推断存在歧义时，选择确定性的一种并写入 `summary.json`。

## 覆盖文件格式

支持 JSON 或 YAML，建议 YAML。

### YAML 示例

```yaml
rows:
  devices: 5000
  alarms: 120000

fks:
  alarms:
    device_id: devices.id
    line_id:
      table: lines
      column: id
  work_orders:
    alarm_id: alarms.id
```

### JSON 示例

```json
{
  "rows": {
    "devices": 5000,
    "alarms": 120000
  },
  "fks": {
    "alarms": {
      "device_id": "devices.id"
    }
  }
}
```

## CLI 说明

- `--rows`：每张表默认行数。
- `--table-rows table=n`：按表覆盖行数。
- `--devices 5000 --alarms 120000`：按实体快速指定规模（映射同名表）。
- `--seed`：固定随机种子，保证结果可复现。
- `--no-infer-fk`：关闭隐式外键推断，仅用显式关系。

## 校验要求

在合法模式下，出现任何问题都应立即失败：

- NOT NULL 被违反
- 主键重复或为 NULL
- 唯一键重复
- 外键引用缺失
- 插入顺序与依赖图冲突

排查时优先查看 `summary.json`。
