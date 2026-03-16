---
name: xlsx2json
description: 将 XLSX 表格按“每行一条记录”转换为 JSON 数组，并支持列名映射与枚举值映射（例如把“名称”映射为 `name`，把“启用/禁用”映射为业务枚举或数值码）。当用户要求从 Excel 导出结构化 JSON、做字段重命名、做枚举标准化，或为接口/测试准备数据时使用。
---

# XLSX 转 JSON

## 最小澄清

仅在缺失时补问以下信息：

1. XLSX 文件路径。
2. 目标工作表与表头行（默认首个工作表、第一行表头）。
3. 是否需要列名映射与 enum 映射。

## 执行流程

1. 读取 XLSX 工作表，按表头将每一行解析为一条记录。
2. 应用列名映射（如 `名称 -> name`）。
3. 应用 enum 映射（如 `状态: 启用 -> 1`）。
4. 可选执行转换策略（`trim`、`types`、`formats`、`defaults`）。
5. 导出 JSON 数组文件，并在终端输出简要统计（不落盘）。

## 命令示例

### 1) 直接转换（无映射）

```bash
python3 skills/xlsx2json/scripts/xlsx_to_json.py \
  --xlsx ./input.xlsx \
  --output ./output.json
```

### 2) 列名映射 + enum 映射（命令行）

```bash
python3 skills/xlsx2json/scripts/xlsx_to_json.py \
  --xlsx ./input.xlsx \
  --output ./output.json \
  --map "名称=name" \
  --map "状态=status" \
  --enum "状态:启用=1" \
  --enum "状态:禁用=0"
```

### 3) 使用配置文件（推荐复杂映射）

```bash
python3 skills/xlsx2json/scripts/xlsx_to_json.py \
  --xlsx ./input.xlsx \
  --config ./mapping.json \
  --output ./output.json
```

`mapping.json` 示例：

```json
{
  "column_map": {
    "名称": "name",
    "状态": "status"
  },
  "enum_map": {
    "状态": {
      "启用": 1,
      "禁用": 0
    }
  }
}
```

### 4) 使用 v2 策略配置（类型/默认值/格式转换）

```json
{
  "column_map": {
    "订单号": "orderCode",
    "批次": "batch",
    "封装类型": "encapsulationType",
    "生产时间": "produceTime"
  },
  "enum_map": {
    "状态": {
      "启用": 1,
      "禁用": 0
    }
  },
  "transforms": {
    "trim": ["orderCode"],
    "types": {
      "batch": "string",
      "encapsulationType": "string"
    },
    "formats": {
      "produceTime": {
        "kind": "excel_serial_datetime",
        "output": "%Y-%m-%dT%H:%M:%S",
        "date_system": "1900",
        "on_error": "keep"
      }
    },
    "defaults": {
      "quantity": null,
      "alias": null,
      "bigAlias": null
    }
  }
}
```

## 输出约定

- 输出为 JSON 数组，每个元素对应 XLSX 一行数据。
- 默认输出 UTF-8 且保留中文字符。
- `--drop-empty` 可移除值为 `null` 或空字符串的字段。
- 终端会输出简要统计（如 enum 命中数、类型转换数、格式转换失败数、默认值填充数）。

## 护栏

- 把表头为空的列忽略，不生成键名为空的 JSON 字段。
- 优先使用显式映射；映射未命中时保留原列名与原值。
- 配置文件与命令行同时提供时，命令行映射覆盖配置文件。
