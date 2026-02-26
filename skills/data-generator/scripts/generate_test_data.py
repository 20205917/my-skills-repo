#!/usr/bin/env python3
"""根据 SQL DDL 生成关系型测试数据。

默认模式生成合法数据，满足 PK/UK/FK 与基础时间逻辑。
仅在明确开启时才注入异常/脏数据。
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


ID_CANDIDATE_COLUMNS = {
    "tenant_id",
    "org_id",
    "organization_id",
    "company_id",
    "factory_id",
    "plant_id",
    "line_id",
    "station_id",
    "device_id",
    "sensor_id",
    "work_order_id",
    "alarm_id",
    "maintenance_id",
}

STATUS_VALUES = {
    "alarm_status": ["NEW", "ACKED", "IN_PROGRESS", "RESOLVED", "CLOSED"],
    "work_order_status": ["CREATED", "ASSIGNED", "IN_PROGRESS", "DONE", "CLOSED"],
    "qc_result": ["PASS", "FAIL", "REWORK"],
    "status": ["ACTIVE", "INACTIVE", "DISABLED"],
}

INDUSTRIAL_METRIC_RANGES = {
    "temperature": (25.0, 95.0),
    "temp": (25.0, 95.0),
    "pressure": (0.8, 8.0),
    "vibration": (0.1, 12.0),
    "current": (1.0, 60.0),
    "voltage": (180.0, 450.0),
    "speed": (300.0, 4000.0),
    "humidity": (20.0, 95.0),
}


@dataclass
class Column:
    name: str
    raw_type: str
    nullable: bool = True
    default: Optional[str] = None
    is_primary: bool = False
    is_unique: bool = False
    is_auto_increment: bool = False
    enum_values: List[str] = field(default_factory=list)


@dataclass
class ForeignKey:
    column: str
    ref_table: str
    ref_column: str
    inferred: bool = False
    reason: str = ""


@dataclass
class Table:
    name: str
    columns: List[Column] = field(default_factory=list)
    primary_key: List[str] = field(default_factory=list)
    unique_keys: List[List[str]] = field(default_factory=list)
    foreign_keys: List[ForeignKey] = field(default_factory=list)


@dataclass
class ValidationResult:
    ok: bool
    issues: List[str]


def strip_ident(value: str) -> str:
    value = value.strip()
    if "." in value:
        value = value.split(".")[-1]
    if value and value[0] in '`"[' and value[-1] in '`"]':
        return value[1:-1]
    return value


def split_top_level(text: str, delimiter: str = ",") -> List[str]:
    out: List[str] = []
    start = 0
    depth = 0
    quote: Optional[str] = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == quote and (i == 0 or text[i - 1] != "\\"):
                quote = None
        else:
            if ch in ("'", '"'):
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            elif ch == delimiter and depth == 0:
                out.append(text[start:i].strip())
                start = i + 1
        i += 1
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out


def extract_create_table_blocks(ddl: str) -> List[Tuple[str, str]]:
    pattern = re.compile(
        r"create\s+table\s+(?:if\s+not\s+exists\s+)?([`\"\[\]\w\.]+)\s*\((.*?)\)\s*;",
        flags=re.IGNORECASE | re.DOTALL,
    )
    blocks = []
    for match in pattern.finditer(ddl):
        table_name = strip_ident(match.group(1))
        body = match.group(2)
        blocks.append((table_name, body))
    return blocks


def parse_column(defn: str) -> Optional[Column]:
    tokens = defn.strip().split()
    if not tokens:
        return None
    name = strip_ident(tokens[0])
    rest = defn[len(tokens[0]) :].strip()

    # 读取字段类型，直到遇到约束关键字
    keywords = {
        "not",
        "null",
        "default",
        "primary",
        "key",
        "unique",
        "references",
        "check",
        "constraint",
        "comment",
        "collate",
        "generated",
    }
    type_parts: List[str] = []
    for token in rest.split():
        if token.lower() in keywords:
            break
        type_parts.append(token)
    raw_type = " ".join(type_parts) if type_parts else "varchar(255)"

    lowered = rest.lower()
    nullable = "not null" not in lowered
    default_match = re.search(r"\bdefault\b\s+([^\s,]+(?:\s*\([^\)]*\))?)", rest, flags=re.IGNORECASE)
    default = default_match.group(1).strip() if default_match else None
    is_primary = "primary key" in lowered
    is_unique = bool(re.search(r"\bunique\b", lowered))
    is_auto = "auto_increment" in lowered or " serial" in f" {lowered}"

    enum_values: List[str] = []
    enum_match = re.search(r"enum\s*\((.*?)\)", raw_type, flags=re.IGNORECASE)
    if enum_match:
        enum_values = [part.strip().strip("'\"") for part in split_top_level(enum_match.group(1))]

    return Column(
        name=name,
        raw_type=raw_type,
        nullable=nullable,
        default=default,
        is_primary=is_primary,
        is_unique=is_unique,
        is_auto_increment=is_auto,
        enum_values=enum_values,
    )


def parse_constraint(defn: str, table: Table) -> None:
    lowered = defn.lower().strip()

    pk_match = re.search(r"primary\s+key\s*\((.*?)\)", defn, flags=re.IGNORECASE)
    if pk_match:
        table.primary_key = [strip_ident(p) for p in split_top_level(pk_match.group(1))]
        return

    unique_match = re.search(
        r"(?:unique\s+key|unique\s+index|unique)\s+(?:[`\"\[]?\w+[`\"\]]?\s*)?\((.*?)\)",
        defn,
        flags=re.IGNORECASE,
    )
    if unique_match:
        table.unique_keys.append([strip_ident(p) for p in split_top_level(unique_match.group(1))])
        return

    fk_match = re.search(
        r"foreign\s+key\s*\((.*?)\)\s*references\s+([`\"\[\]\w\.]+)\s*\((.*?)\)",
        defn,
        flags=re.IGNORECASE,
    )
    if fk_match:
        source_cols = [strip_ident(p) for p in split_top_level(fk_match.group(1))]
        ref_table = strip_ident(fk_match.group(2))
        ref_cols = [strip_ident(p) for p in split_top_level(fk_match.group(3))]
        for src, ref in zip(source_cols, ref_cols):
            table.foreign_keys.append(ForeignKey(column=src, ref_table=ref_table, ref_column=ref, inferred=False, reason="DDL显式外键"))
        return

    # 行内 references 在 parse_table 中处理
    if lowered.startswith("constraint"):
        return


def parse_table(table_name: str, body: str) -> Table:
    table = Table(name=table_name)

    for item in split_top_level(body):
        stripped = item.strip().rstrip(",")
        lowered = stripped.lower()
        if not stripped:
            continue
        if lowered.startswith(("primary key", "unique", "constraint", "foreign key")):
            parse_constraint(stripped, table)
            continue

        col = parse_column(stripped)
        if not col:
            continue

        ref_match = re.search(
            r"\breferences\b\s+([`\"\[\]\w\.]+)\s*\((.*?)\)",
            stripped,
            flags=re.IGNORECASE,
        )
        if ref_match:
            ref_table = strip_ident(ref_match.group(1))
            ref_cols = [strip_ident(p) for p in split_top_level(ref_match.group(2))]
            ref_col = ref_cols[0] if ref_cols else "id"
            table.foreign_keys.append(
                ForeignKey(column=col.name, ref_table=ref_table, ref_column=ref_col, inferred=False, reason="行内引用")
            )

        table.columns.append(col)

    # 将行内约束同步到表级元数据
    for col in table.columns:
        if col.is_primary and col.name not in table.primary_key:
            table.primary_key.append(col.name)
        if col.is_unique:
            table.unique_keys.append([col.name])

    # 主键兜底识别
    if not table.primary_key:
        if any(col.name == "id" for col in table.columns):
            table.primary_key = ["id"]

    dedup_unique = []
    seen = set()
    for uq in table.unique_keys:
        key = tuple(uq)
        if key not in seen:
            seen.add(key)
            dedup_unique.append(uq)
    table.unique_keys = dedup_unique

    return table


def parse_ddl(ddl_text: str) -> Dict[str, Table]:
    tables: Dict[str, Table] = {}
    for table_name, body in extract_create_table_blocks(ddl_text):
        table = parse_table(table_name, body)
        tables[table.name] = table
    return tables


def load_override(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    raw = p.read_text(encoding="utf-8")

    if p.suffix.lower() in {".json"}:
        return json.loads(raw)

    if p.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("YAML 覆盖文件依赖 PyYAML，请先执行: pip install pyyaml") from exc
        loaded = yaml.safe_load(raw)
        return loaded or {}

    # 兜底：先按 JSON 解析，再尝试 YAML
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("覆盖文件必须是 JSON 或 YAML；若为 YAML，请先安装 PyYAML。") from exc
        loaded = yaml.safe_load(raw)
        return loaded or {}


def apply_override(tables: Dict[str, Table], override: Dict[str, Any], inference_log: List[Dict[str, Any]]) -> Dict[str, int]:
    rows_override: Dict[str, int] = {}

    for table_name, row_count in (override.get("rows") or {}).items():
        if table_name in tables:
            rows_override[table_name] = int(row_count)

    for table_name, mapping in (override.get("fks") or {}).items():
        if table_name not in tables or not isinstance(mapping, dict):
            continue
        table = tables[table_name]
        for column_name, target in mapping.items():
            if isinstance(target, str) and "." in target:
                ref_table, ref_col = target.split(".", 1)
            elif isinstance(target, dict):
                ref_table = target.get("table")
                ref_col = target.get("column", "id")
            else:
                continue
            if ref_table not in tables:
                continue
            table.foreign_keys = [fk for fk in table.foreign_keys if fk.column != column_name]
            table.foreign_keys.append(
                ForeignKey(
                    column=column_name,
                    ref_table=ref_table,
                    ref_column=ref_col,
                    inferred=True,
                    reason="用户覆盖",
                )
            )
            inference_log.append(
                {
                    "table": table_name,
                    "column": column_name,
                    "ref_table": ref_table,
                    "ref_column": ref_col,
                    "method": "覆盖",
                    "priority": "用户覆盖",
                }
            )

    return rows_override


def table_name_variants(name: str) -> List[str]:
    n = name.lower()
    variants = {n, n.rstrip("s"), f"{n}s"}
    if n.endswith("ies"):
        variants.add(n[:-3] + "y")
    if n.endswith("y"):
        variants.add(n[:-1] + "ies")
    return sorted(variants)


def build_table_index(tables: Dict[str, Table]) -> Dict[str, Table]:
    index: Dict[str, Table] = {}
    for table in tables.values():
        for variant in table_name_variants(table.name):
            index[variant] = table
    return index


def infer_implicit_foreign_keys(tables: Dict[str, Table], inference_log: List[Dict[str, Any]]) -> None:
    table_index = build_table_index(tables)

    for table in tables.values():
        fk_columns = {fk.column for fk in table.foreign_keys}

        for col in table.columns:
            if col.name in fk_columns:
                continue

            col_name = col.name.lower()
            if not col_name.endswith("_id") and col_name not in ID_CANDIDATE_COLUMNS:
                continue

            candidates: List[Tuple[int, Table, str]] = []

            if col_name.endswith("_id"):
                base = col_name[:-3]
                for variant in table_name_variants(base):
                    if variant in table_index and table_index[variant].name != table.name:
                        target = table_index[variant]
                        score = 90
                        candidates.append((score, target, f"命名推断:{col_name}"))

            for other in tables.values():
                if other.name == table.name:
                    continue
                if col_name in other.primary_key:
                    candidates.append((75, other, f"主键匹配:{col_name}"))
                for uq in other.unique_keys:
                    if len(uq) == 1 and uq[0].lower() == col_name:
                        candidates.append((70, other, f"唯一键匹配:{col_name}"))

            if not candidates:
                continue

            candidates.sort(key=lambda item: item[0], reverse=True)
            best_score, best_table, reason = candidates[0]

            if len(best_table.primary_key) == 1:
                ref_col = best_table.primary_key[0]
            elif "id" in [c.name for c in best_table.columns]:
                ref_col = "id"
            else:
                ref_col = best_table.columns[0].name

            table.foreign_keys.append(
                ForeignKey(
                    column=col.name,
                    ref_table=best_table.name,
                    ref_column=ref_col,
                    inferred=True,
                    reason=reason,
                )
            )
            inference_log.append(
                {
                    "table": table.name,
                    "column": col.name,
                    "ref_table": best_table.name,
                    "ref_column": ref_col,
                    "method": "推断",
                    "priority": f"命名/类型评分={best_score}",
                    "reason": reason,
                }
            )


def compute_insert_order(tables: Dict[str, Table]) -> List[str]:
    deps: Dict[str, set] = {name: set() for name in tables}
    reverse: Dict[str, set] = {name: set() for name in tables}
    indegree: Dict[str, int] = {name: 0 for name in tables}

    for table in tables.values():
        for fk in table.foreign_keys:
            if fk.ref_table in tables and fk.ref_table != table.name:
                if fk.ref_table not in deps[table.name]:
                    deps[table.name].add(fk.ref_table)
                    reverse[fk.ref_table].add(table.name)
                    indegree[table.name] += 1

    queue = deque(sorted([name for name, deg in indegree.items() if deg == 0]))
    ordered: List[str] = []

    while queue:
        node = queue.popleft()
        ordered.append(node)
        for child in sorted(reverse[node]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    if len(ordered) != len(tables):
        # 发现环依赖时，保持确定性兜底顺序
        remainder = [name for name in sorted(tables.keys()) if name not in ordered]
        ordered.extend(remainder)

    return ordered


def normalize_type(raw_type: str) -> str:
    t = raw_type.lower()
    if "enum" in t:
        return "enum"
    if any(word in t for word in ["bigint", "smallint", "int", "serial"]):
        return "int"
    if any(word in t for word in ["decimal", "numeric", "float", "double", "real"]):
        return "float"
    if "bool" in t:
        return "bool"
    if "timestamp" in t or "datetime" in t:
        return "datetime"
    if re.search(r"\bdate\b", t):
        return "date"
    if "json" in t:
        return "json"
    if "uuid" in t:
        return "uuid"
    if any(word in t for word in ["char", "text", "varchar"]):
        return "string"
    return "string"


def parse_cli() -> Tuple[argparse.Namespace, Dict[str, int]]:
    parser = argparse.ArgumentParser(description="根据 DDL 生成 SQL/JSON 测试数据，并保证 PK/UK/FK 约束。")
    parser.add_argument("--ddl", required=True, help="DDL SQL 文件路径。")
    parser.add_argument("--schema-override", help="可选的 JSON/YAML 覆盖文件（行数与外键映射）。")
    parser.add_argument("--db-dialect", choices=["mysql", "postgres"], default="mysql")
    parser.add_argument("--db-version", help="可选数据库版本，默认: mysql=8, postgres=14")
    parser.add_argument("--rows", type=int, default=100, help="每张表的默认行数。")
    parser.add_argument(
        "--table-rows",
        action="append",
        default=[],
        help="按表覆盖行数，可重复传入：--table-rows devices=5000",
    )
    parser.add_argument("--seed", type=int, default=7, help="随机种子，保证结果可复现。")
    parser.add_argument("--output-dir", default="./generated-data")
    parser.add_argument("--formats", default="sql,json", help="输出格式，逗号分隔：sql,json")
    parser.add_argument("--json-layout", choices=["auto", "single", "per-table"], default="auto")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--time-window-days", type=int, default=30)
    parser.add_argument("--infer-fk", dest="infer_fk", action="store_true", default=True)
    parser.add_argument("--no-infer-fk", dest="infer_fk", action="store_false")

    parser.add_argument("--invalid-mode", action="store_true", help="开启脏数据模式。")
    parser.add_argument("--dirty-data", action="store_true", help="--invalid-mode 的别名。")
    parser.add_argument("--invalid-ratio", type=float, default=0.02)
    parser.add_argument("--invalid-target", default="", help="目标范围，逗号分隔：table 或 table.column")

    parser.add_argument("--profile", choices=["generic", "industrial"], default="industrial")
    parser.add_argument("--line-devices", type=int, default=8)
    parser.add_argument("--device-sensors", type=int, default=4)
    parser.add_argument("--alarm-work-order-ratio", type=float, default=0.35)

    args, unknown = parser.parse_known_args()
    if args.dirty_data:
        args.invalid_mode = True

    entity_rows: Dict[str, int] = {}
    i = 0
    while i < len(unknown):
        token = unknown[i]
        if token.startswith("--") and i + 1 < len(unknown) and not unknown[i + 1].startswith("--"):
            key = token[2:].replace("-", "_")
            value = unknown[i + 1]
            try:
                entity_rows[key] = int(value)
            except ValueError:
                pass
            i += 2
        else:
            i += 1

    return args, entity_rows


def build_row_plan(
    tables: Dict[str, Table],
    default_rows: int,
    table_rows: Sequence[str],
    override_rows: Dict[str, int],
    entity_rows: Dict[str, int],
) -> Dict[str, int]:
    plan = {name: max(0, default_rows) for name in tables}

    for item in table_rows:
        if "=" not in item:
            continue
        table, count = item.split("=", 1)
        table = table.strip()
        if table in tables:
            plan[table] = max(0, int(count))

    for table_name, count in override_rows.items():
        plan[table_name] = max(0, int(count))

    # 支持便捷写法：--devices 5000、--work-orders 1000 等。
    lower_table_map = {name.lower(): name for name in tables}
    for entity, count in entity_rows.items():
        key = entity.lower().rstrip("s")
        for table_lower, real_name in lower_table_map.items():
            table_key = table_lower.rstrip("s")
            if key == table_key:
                plan[real_name] = max(0, int(count))

    return plan


def pick_reference_row(
    generated: Dict[str, List[Dict[str, Any]]],
    ref_table: str,
    ref_column: str,
    rng: random.Random,
) -> Optional[Dict[str, Any]]:
    rows = generated.get(ref_table) or []
    if not rows:
        return None
    valid = [row for row in rows if row.get(ref_column) is not None]
    if not valid:
        return None
    return rng.choice(valid)


def random_datetime(window_days: int, rng: random.Random) -> datetime:
    now = datetime.now()
    delta_seconds = window_days * 86400
    offset = rng.randint(0, max(0, delta_seconds))
    return now - timedelta(seconds=offset)


def metric_value(name: str, rng: random.Random) -> float:
    lower_name = name.lower()
    for key, (lo, hi) in INDUSTRIAL_METRIC_RANGES.items():
        if key in lower_name:
            span = hi - lo
            value = lo + rng.random() * span
            # 低概率尖峰，模拟告警触发
            if rng.random() < 0.02:
                value += span * rng.uniform(0.1, 0.4)
            return round(value, 4)
    return round(rng.uniform(1.0, 100.0), 4)


def default_string(table: str, column: str, idx: int) -> str:
    return f"{table}_{column}_{idx + 1}"


def generate_column_value(
    table: Table,
    column: Column,
    row_idx: int,
    rng: random.Random,
    generated: Dict[str, List[Dict[str, Any]]],
    fk_map: Dict[str, ForeignKey],
    window_days: int,
    profile: str,
) -> Tuple[Any, Optional[Dict[str, Any]]]:
    col_name = column.name
    col_type = normalize_type(column.raw_type)

    fk = fk_map.get(col_name)
    if fk:
        parent_row = pick_reference_row(generated, fk.ref_table, fk.ref_column, rng)
        if parent_row is None:
            return None, None
        return parent_row.get(fk.ref_column), parent_row

    if col_type == "enum" and column.enum_values:
        return rng.choice(column.enum_values), None

    lower_name = col_name.lower()

    if lower_name in STATUS_VALUES:
        return rng.choice(STATUS_VALUES[lower_name]), None
    if lower_name.endswith("_status"):
        return rng.choice(["NEW", "IN_PROGRESS", "DONE", "CLOSED"]), None
    if lower_name.endswith("_result"):
        return rng.choice(["PASS", "FAIL"]), None

    if col_type == "int":
        if column.is_auto_increment or column.is_primary or column.is_unique:
            return row_idx + 1, None
        if lower_name in {"severity", "priority"}:
            return rng.randint(1, 5), None
        return rng.randint(1, 100000), None

    if col_type == "float":
        if profile == "industrial":
            return metric_value(col_name, rng), None
        return round(rng.uniform(1.0, 1000.0), 4), None

    if col_type == "bool":
        return rng.choice([True, False]), None

    if col_type == "date":
        return random_datetime(window_days, rng).date().isoformat(), None

    if col_type == "datetime":
        return random_datetime(window_days, rng).strftime("%Y-%m-%d %H:%M:%S"), None

    if col_type == "uuid":
        return f"{row_idx + 1:08x}-{rng.randint(0, 0xFFFF):04x}-{rng.randint(0, 0xFFFF):04x}-{rng.randint(0, 0xFFFF):04x}-{rng.randint(0, 0xFFFFFFFFFFFF):012x}", None

    if col_type == "json":
        return {"source": table.name, "row": row_idx + 1}, None

    if any(keyword in lower_name for keyword in ["name", "code", "no", "sn", "number"]):
        return default_string(table.name, col_name, row_idx), None

    return default_string(table.name, col_name, row_idx), None


def maybe_apply_default(value: Any, column: Column) -> Any:
    if value is not None:
        return value
    if column.default is None:
        return value

    default_value = column.default.strip().strip("'").strip('"')
    if re.match(r"^(current_timestamp|now\(\))$", default_value, flags=re.IGNORECASE):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if default_value.lower() == "null":
        return None
    return default_value


def enforce_temporal_logic(row: Dict[str, Any], parent_rows: List[Dict[str, Any]]) -> None:
    fmt = "%Y-%m-%d %H:%M:%S"

    def to_dt(value: Any) -> Optional[datetime]:
        if not isinstance(value, str):
            return None
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            return None

    created_key = "created_at" if "created_at" in row else None
    updated_key = "updated_at" if "updated_at" in row else None
    start_key = "start_time" if "start_time" in row else None
    end_key = "end_time" if "end_time" in row else None

    min_created: Optional[datetime] = None
    for parent in parent_rows:
        p_created = to_dt(parent.get("created_at"))
        if p_created and (min_created is None or p_created > min_created):
            min_created = p_created

    if created_key and updated_key:
        created = to_dt(row.get(created_key))
        updated = to_dt(row.get(updated_key))
        if created and updated and updated < created:
            row[updated_key] = created.strftime(fmt)
        if min_created and created and created < min_created:
            row[created_key] = min_created.strftime(fmt)

    if start_key and end_key:
        start = to_dt(row.get(start_key))
        end = to_dt(row.get(end_key))
        if start and end and end < start:
            row[end_key] = start.strftime(fmt)


def generate_rows(
    tables: Dict[str, Table],
    order: Sequence[str],
    row_plan: Dict[str, int],
    rng: random.Random,
    window_days: int,
    profile: str,
) -> Dict[str, List[Dict[str, Any]]]:
    generated: Dict[str, List[Dict[str, Any]]] = {}

    for table_name in order:
        table = tables[table_name]
        fk_map = {fk.column: fk for fk in table.foreign_keys}
        rows: List[Dict[str, Any]] = []

        for i in range(row_plan.get(table_name, 0)):
            row: Dict[str, Any] = {}
            parent_rows: List[Dict[str, Any]] = []
            for col in table.columns:
                value, parent_row = generate_column_value(
                    table=table,
                    column=col,
                    row_idx=i,
                    rng=rng,
                    generated=generated,
                    fk_map=fk_map,
                    window_days=window_days,
                    profile=profile,
                )

                if parent_row is not None:
                    parent_rows.append(parent_row)

                # 仅在可空且非关键字段上少量生成空值
                if (
                    value is not None
                    and col.nullable
                    and not col.is_primary
                    and not col.is_unique
                    and col.name not in fk_map
                    and rng.random() < 0.02
                ):
                    value = None

                value = maybe_apply_default(value, col)
                row[col.name] = value

            enforce_temporal_logic(row, parent_rows)
            rows.append(row)

        generated[table_name] = rows

    return generated


def inject_invalid_data(
    tables: Dict[str, Table],
    generated: Dict[str, List[Dict[str, Any]]],
    ratio: float,
    target_expr: str,
    rng: random.Random,
) -> None:
    if ratio <= 0:
        return

    targets = {item.strip() for item in target_expr.split(",") if item.strip()}
    for table_name, rows in generated.items():
        if not rows:
            continue

        table = tables[table_name]
        target_columns: List[str] = []
        for token in targets:
            if "." in token:
                t, c = token.split(".", 1)
                if t == table_name:
                    target_columns.append(c)
            elif token == table_name:
                target_columns.extend([col.name for col in table.columns])

        if not targets:
            # 未指定目标时，优先污染关键列
            target_columns.extend(table.primary_key)
            for fk in table.foreign_keys:
                target_columns.append(fk.column)
            if not target_columns and table.columns:
                target_columns.append(table.columns[0].name)

        target_columns = [c for c in target_columns if c in {col.name for col in table.columns}]
        if not target_columns:
            continue

        inject_count = max(1, int(len(rows) * ratio))
        chosen_indices = rng.sample(range(len(rows)), min(inject_count, len(rows)))

        for idx in chosen_indices:
            row = rows[idx]
            col_name = rng.choice(target_columns)
            col = next((c for c in table.columns if c.name == col_name), None)
            if not col:
                continue

            if col_name in table.primary_key:
                row[col_name] = rows[0].get(col_name)
                continue

            if any(col_name == fk.column for fk in table.foreign_keys):
                row[col_name] = -999999
                continue

            if not col.nullable:
                row[col_name] = None
                continue

            ctype = normalize_type(col.raw_type)
            if ctype == "int":
                row[col_name] = -1
            elif ctype == "float":
                row[col_name] = -9999.9
            else:
                row[col_name] = "@@INVALID@@"


def tuple_key(row: Dict[str, Any], columns: Sequence[str]) -> Tuple[Any, ...]:
    return tuple(row.get(col) for col in columns)


def validate_data(tables: Dict[str, Table], order: Sequence[str], generated: Dict[str, List[Dict[str, Any]]]) -> ValidationResult:
    issues: List[str] = []

    order_index = {name: i for i, name in enumerate(order)}
    for table in tables.values():
        for fk in table.foreign_keys:
            if fk.ref_table in order_index and order_index[fk.ref_table] > order_index[table.name]:
                issues.append(
                    f"插入顺序错误：{table.name}.{fk.column} 引用 {fk.ref_table}.{fk.ref_column}，但出现顺序更早。"
                )

    for table in tables.values():
        rows = generated.get(table.name, [])
        column_map = {col.name: col for col in table.columns}

        pk_seen = set()
        uq_seen: Dict[Tuple[str, ...], set] = defaultdict(set)

        ref_sets: Dict[Tuple[str, str], set] = {}
        for fk in table.foreign_keys:
            ref_rows = generated.get(fk.ref_table, [])
            ref_values = {ref_row.get(fk.ref_column) for ref_row in ref_rows}
            ref_sets[(fk.ref_table, fk.ref_column)] = ref_values

        for row_idx, row in enumerate(rows, start=1):
            for col in table.columns:
                value = row.get(col.name)
                if value is None and not col.nullable and col.default is None:
                    issues.append(f"{table.name}[{row_idx}].{col.name} 为 NULL，但字段是 NOT NULL")

            if table.primary_key:
                pk_value = tuple_key(row, table.primary_key)
                if any(v is None for v in pk_value):
                    issues.append(f"{table.name}[{row_idx}] 主键包含 NULL: {pk_value}")
                elif pk_value in pk_seen:
                    issues.append(f"{table.name}[{row_idx}] 主键重复: {pk_value}")
                pk_seen.add(pk_value)

            for uq in table.unique_keys:
                uq_value = tuple_key(row, uq)
                if any(v is None for v in uq_value):
                    continue
                uq_key = tuple(uq)
                if uq_value in uq_seen[uq_key]:
                    issues.append(f"{table.name}[{row_idx}] 唯一键 {uq} 重复: {uq_value}")
                uq_seen[uq_key].add(uq_value)

            for fk in table.foreign_keys:
                fk_value = row.get(fk.column)
                if fk_value is None:
                    continue
                ref_values = ref_sets.get((fk.ref_table, fk.ref_column), set())
                if fk_value not in ref_values:
                    issues.append(
                        f"{table.name}[{row_idx}].{fk.column}={fk_value} 缺少引用 {fk.ref_table}.{fk.ref_column}"
                    )

            # 枚举值校验
            for col_name, col in column_map.items():
                if col.enum_values and row.get(col_name) not in col.enum_values:
                    issues.append(
                        f"{table.name}[{row_idx}].{col_name}={row.get(col_name)} 不在枚举范围 {col.enum_values}"
                    )

    return ValidationResult(ok=not issues, issues=issues)


def sql_literal(value: Any, dialect: str) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        if dialect == "postgres":
            return "TRUE" if value else "FALSE"
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    return f"'{str(value)}'"


def write_sql_outputs(
    out_dir: Path,
    tables: Dict[str, Table],
    order: Sequence[str],
    generated: Dict[str, List[Dict[str, Any]]],
    dialect: str,
    batch_size: int,
) -> None:
    sql_dir = out_dir / "sql"
    sql_dir.mkdir(parents=True, exist_ok=True)

    for table_name in order:
        rows = generated.get(table_name, [])
        table = tables[table_name]
        if not table.columns:
            continue

        path = sql_dir / f"{table_name}.sql"
        with path.open("w", encoding="utf-8") as f:
            f.write(f"-- 自动生成数据表: {table_name}\n")
            f.write("BEGIN;\n")
            cols = [col.name for col in table.columns]
            col_clause = ", ".join(cols)

            for start in range(0, len(rows), max(1, batch_size)):
                batch = rows[start : start + max(1, batch_size)]
                values_sql = []
                for row in batch:
                    literals = [sql_literal(row.get(col), dialect=dialect) for col in cols]
                    values_sql.append("(" + ", ".join(literals) + ")")
                if values_sql:
                    f.write(f"INSERT INTO {table_name} ({col_clause}) VALUES\n")
                    f.write(",\n".join(values_sql))
                    f.write(";\n")

            f.write("COMMIT;\n")


def write_json_outputs(out_dir: Path, generated: Dict[str, List[Dict[str, Any]]], layout: str) -> None:
    json_dir = out_dir / "json"
    json_dir.mkdir(parents=True, exist_ok=True)

    if layout in {"auto", "per-table"}:
        for table_name, rows in generated.items():
            path = json_dir / f"{table_name}.json"
            path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    if layout == "single":
        path = json_dir / "data.json"
        path.write_text(json.dumps(generated, ensure_ascii=False, indent=2), encoding="utf-8")


def build_summary(
    args: argparse.Namespace,
    tables: Dict[str, Table],
    order: Sequence[str],
    row_plan: Dict[str, int],
    inference_log: List[Dict[str, Any]],
    validation: ValidationResult,
) -> Dict[str, Any]:
    return {
        "db": {
            "dialect": args.db_dialect,
            "version": args.db_version or ("8" if args.db_dialect == "mysql" else "14"),
        },
        "seed": args.seed,
        "rows": row_plan,
        "insert_order": list(order),
        "tables": sorted(list(tables.keys())),
        "inferred_or_overridden_fks": inference_log,
        "invalid_mode": args.invalid_mode,
        "validation_ok": validation.ok,
        "validation_issue_count": len(validation.issues),
        "validation_issues": validation.issues[:200],
    }


def main() -> None:
    args, entity_rows = parse_cli()
    rng = random.Random(args.seed)

    ddl_path = Path(args.ddl)
    if not ddl_path.exists():
        raise FileNotFoundError(f"未找到 DDL 文件: {ddl_path}")

    ddl_text = ddl_path.read_text(encoding="utf-8")
    tables = parse_ddl(ddl_text)
    if not tables:
        raise RuntimeError("DDL 中未找到 CREATE TABLE 语句。")

    inference_log: List[Dict[str, Any]] = []
    override = load_override(args.schema_override)
    override_rows = apply_override(tables, override, inference_log)

    if args.infer_fk:
        infer_implicit_foreign_keys(tables, inference_log)

    order = compute_insert_order(tables)
    row_plan = build_row_plan(tables, args.rows, args.table_rows, override_rows, entity_rows)

    generated = generate_rows(
        tables=tables,
        order=order,
        row_plan=row_plan,
        rng=rng,
        window_days=args.time_window_days,
        profile=args.profile,
    )

    if args.invalid_mode:
        inject_invalid_data(
            tables=tables,
            generated=generated,
            ratio=max(0.0, min(1.0, args.invalid_ratio)),
            target_expr=args.invalid_target,
            rng=rng,
        )

    validation = validate_data(tables, order, generated)
    if not args.invalid_mode and not validation.ok:
        preview = "\n".join(validation.issues[:30])
        raise RuntimeError(
            "合法模式下生成数据校验失败。\n"
            f"问题（前 30 条）：\n{preview}\n"
            "建议：通过 --schema-override 显式指定关系，消除外键推断歧义。"
        )

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    formats = {item.strip().lower() for item in args.formats.split(",") if item.strip()}
    if "sql" in formats:
        write_sql_outputs(out_dir, tables, order, generated, args.db_dialect, args.batch_size)
    if "json" in formats:
        write_json_outputs(out_dir, generated, args.json_layout)

    summary = build_summary(args, tables, order, row_plan, inference_log, validation)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("生成完成。")
    print(f"输出目录: {out_dir.resolve()}")
    print(f"校验是否通过: {validation.ok}")
    print(f"涉及数据表: {', '.join(order)}")


if __name__ == "__main__":
    main()
