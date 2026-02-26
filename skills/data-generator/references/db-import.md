# 数据库导入

## 输出结构

- SQL 文件：`output/sql/<table>.sql`（每表一个文件）
- JSON 文件：`output/json/<table>.json` 或 `output/json/data.json`
- 汇总文件：`output/summary.json`

## MySQL 8

### 按依赖顺序导入

按 `summary.json.insert_order` 顺序执行导入。

示例：

```bash
mysql -u root -p test_db < generated/sql/lines.sql
mysql -u root -p test_db < generated/sql/devices.sql
mysql -u root -p test_db < generated/sql/sensors.sql
```

### 建议

- 大批量场景优先提高 `--batch-size`。
- 若导入内存压力偏高，降低 `--batch-size` 并按表分批。

## PostgreSQL 14

示例：

```bash
psql -U postgres -d test_db -f generated/sql/lines.sql
psql -U postgres -d test_db -f generated/sql/devices.sql
psql -U postgres -d test_db -f generated/sql/sensors.sql
```

## Java 侧读取 JSON

### 按表文件

- 每个文件映射到对应实体 DTO 列表。
- 按父表到子表顺序落库。

### 单文件

- 顶层结构：`{ "table_name": [ ... ] }`
- 按 `summary.insert_order` 顺序遍历写入。

## 性能建议

100k 级别：

- `--batch-size` 建议 `3000~10000`
- 先生成到本地磁盘，再导入数据库
- CI 中固定 `--seed` 保证可重复

1M 级别：

- 逐步调大批量大小
- 允许时先关闭非核心索引，导入后重建
- 导入后执行统计信息更新（如 analyze）
