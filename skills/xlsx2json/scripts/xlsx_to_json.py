#!/usr/bin/env python3
"""Convert XLSX rows to JSON with column mapping and enum mapping support."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import posixpath
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"

TYPE_ALIASES = {
    "str": "string",
    "string": "string",
    "text": "string",
    "int": "int",
    "integer": "int",
    "float": "float",
    "double": "float",
    "number": "float",
    "bool": "bool",
    "boolean": "bool",
    "date": "date",
    "datetime": "datetime",
}

FORMAT_KIND_ALIASES = {
    "excel_serial": "excel_serial_datetime",
    "excel_serial_datetime": "excel_serial_datetime",
    "serial_datetime": "excel_serial_datetime",
    "excel_serial_date": "excel_serial_date",
    "serial_date": "excel_serial_date",
    "datetime_reformat": "datetime_reformat",
    "datetime_parse": "datetime_reformat",
}

ERROR_MODES = {"keep", "null", "raise"}


def _tag(name: str) -> str:
    return f"{{{NS_MAIN}}}{name}"


def _parse_number(value: str) -> Any:
    text = value.strip()
    if text == "":
        return ""
    try:
        if re.fullmatch(r"[-+]?\d+", text):
            return int(text)
        return float(text)
    except ValueError:
        return text


def _column_ref_to_index(cell_ref: str) -> int:
    match = re.match(r"([A-Za-z]+)", cell_ref)
    if not match:
        raise ValueError(f"Invalid cell reference: {cell_ref}")

    result = 0
    for ch in match.group(1).upper():
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result - 1


def _parse_shared_strings(archive: zipfile.ZipFile) -> List[str]:
    try:
        raw = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []

    root = ET.fromstring(raw)
    items: List[str] = []
    for si in root.findall(_tag("si")):
        text = "".join((node.text or "") for node in si.iter(_tag("t")))
        items.append(text)
    return items


def _resolve_target(base_dir: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(f"{base_dir}/{target}")


def _load_sheet_paths(archive: zipfile.ZipFile) -> List[Tuple[str, str]]:
    workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
    rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))

    rel_targets: Dict[str, str] = {}
    for rel in rels_root.findall(f".//{{{NS_PKG_REL}}}Relationship"):
        rel_id = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        if rel_id and target:
            rel_targets[rel_id] = _resolve_target("xl", target)

    sheets: List[Tuple[str, str]] = []
    for sheet in workbook_root.findall(f".//{_tag('sheet')}"):
        sheet_name = sheet.attrib.get("name")
        rel_id = sheet.attrib.get(f"{{{NS_DOC_REL}}}id")
        if not sheet_name or not rel_id:
            continue
        sheet_path = rel_targets.get(rel_id)
        if sheet_path:
            sheets.append((sheet_name, sheet_path))

    if not sheets:
        raise ValueError("No worksheets found in XLSX file")
    return sheets


def _cell_value(cell: ET.Element, shared_strings: Sequence[str]) -> Any:
    cell_type = cell.attrib.get("t")
    value_node = cell.find(_tag("v"))
    value_text = value_node.text if value_node is not None else None

    if cell_type == "s":
        if value_text is None:
            return None
        index = int(value_text)
        return shared_strings[index] if 0 <= index < len(shared_strings) else None

    if cell_type == "inlineStr":
        inline_node = cell.find(_tag("is"))
        if inline_node is None:
            return None
        return "".join((node.text or "") for node in inline_node.iter(_tag("t")))

    if cell_type == "b":
        return value_text == "1"

    if cell_type in {"str", "d", "e"}:
        return value_text

    if value_text is None:
        return None

    return _parse_number(value_text)


def _sheet_rows(archive: zipfile.ZipFile, sheet_path: str, shared_strings: Sequence[str]) -> List[Tuple[int, List[Any]]]:
    root = ET.fromstring(archive.read(sheet_path))
    rows: List[Tuple[int, List[Any]]] = []

    for row_pos, row_node in enumerate(root.findall(f".//{_tag('row')}"), start=1):
        row_number = int(row_node.attrib.get("r", row_pos))
        values_by_col: Dict[int, Any] = {}
        last_col = -1

        for cell in row_node.findall(_tag("c")):
            cell_ref = cell.attrib.get("r")
            if cell_ref:
                col_index = _column_ref_to_index(cell_ref)
            else:
                col_index = last_col + 1
            last_col = col_index
            values_by_col[col_index] = _cell_value(cell, shared_strings)

        if not values_by_col:
            continue

        max_col = max(values_by_col)
        row_values = [None] * (max_col + 1)
        for index, value in values_by_col.items():
            row_values[index] = value

        rows.append((row_number, row_values))

    return rows


def rows_to_records(rows: Sequence[Tuple[int, List[Any]]], header_row: int = 1) -> List[Dict[str, Any]]:
    headers: Optional[List[Optional[str]]] = None
    records: List[Dict[str, Any]] = []

    for row_number, row_values in rows:
        if row_number == header_row:
            headers = []
            for value in row_values:
                if value is None:
                    headers.append(None)
                else:
                    text = str(value).strip()
                    headers.append(text or None)
            continue

        if row_number <= header_row:
            continue

        if headers is None:
            raise ValueError(f"Header row {header_row} not found")

        if all(value is None or (isinstance(value, str) and value.strip() == "") for value in row_values):
            continue

        record: Dict[str, Any] = {}
        for index, header in enumerate(headers):
            if not header:
                continue
            value = row_values[index] if index < len(row_values) else None
            record[header] = value

        if record:
            records.append(record)

    if headers is None:
        raise ValueError(f"Header row {header_row} not found")

    if all(header is None for header in headers):
        raise ValueError("Header row has no usable column names")

    return records


def read_xlsx_records(xlsx_path: Path, sheet_name: Optional[str] = None, header_row: int = 1) -> List[Dict[str, Any]]:
    if header_row <= 0:
        raise ValueError("header_row must be >= 1")

    with zipfile.ZipFile(xlsx_path, "r") as archive:
        sheets = _load_sheet_paths(archive)

        chosen_sheet_path: Optional[str] = None
        if sheet_name is None:
            chosen_sheet_path = sheets[0][1]
        else:
            for existing_name, path in sheets:
                if existing_name == sheet_name:
                    chosen_sheet_path = path
                    break
            if chosen_sheet_path is None:
                available = ", ".join(name for name, _ in sheets)
                raise ValueError(f"Sheet '{sheet_name}' not found. Available sheets: {available}")

        shared_strings = _parse_shared_strings(archive)
        rows = _sheet_rows(archive, chosen_sheet_path, shared_strings)
        return rows_to_records(rows, header_row=header_row)


def normalize_column_map(column_map: Optional[Dict[str, Any]]) -> Dict[str, str]:
    output: Dict[str, str] = {}
    if not column_map:
        return output

    for source, target in column_map.items():
        source_key = str(source).strip()
        target_key = str(target).strip()
        if source_key and target_key:
            output[source_key] = target_key
    return output


def normalize_enum_map(enum_map: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    if not enum_map:
        return output

    for column, mapping in enum_map.items():
        if not isinstance(mapping, dict):
            raise ValueError(f"enum_map for column '{column}' must be an object")

        column_key = str(column).strip()
        if not column_key:
            continue

        normalized_mapping: Dict[str, Any] = {}
        for source_value, target_value in mapping.items():
            normalized_mapping[str(source_value)] = target_value

        output[column_key] = normalized_mapping

    return output


def _normalize_error_mode(value: Any, *, default: str) -> str:
    if value is None:
        return default
    mode = str(value).strip().lower()
    if mode not in ERROR_MODES:
        raise ValueError(f"Unsupported on_error mode: {value}")
    return mode


def _normalize_trim_config(raw: Any) -> Tuple[bool, Set[str]]:
    if raw is None:
        return False, set()
    if isinstance(raw, bool):
        return raw, set()
    if isinstance(raw, list):
        return False, {str(item).strip() for item in raw if str(item).strip()}
    if isinstance(raw, dict):
        trim_all = bool(raw.get("all", False))
        fields = raw.get("fields") or raw.get("columns") or []
        if not isinstance(fields, list):
            raise ValueError("transforms.trim.fields must be a list")
        normalized_fields = {str(item).strip() for item in fields if str(item).strip()}
        return trim_all, normalized_fields
    raise ValueError("transforms.trim must be bool, list, or object")


def _normalize_type_rules(raw: Any, default_on_error: str) -> Dict[str, Dict[str, str]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("transforms.types must be an object")

    output: Dict[str, Dict[str, str]] = {}
    for field, rule in raw.items():
        field_key = str(field).strip()
        if not field_key:
            continue

        if isinstance(rule, str):
            type_name = rule
            on_error = default_on_error
        elif isinstance(rule, dict):
            type_name = rule.get("type") or rule.get("kind")
            on_error = _normalize_error_mode(rule.get("on_error"), default=default_on_error)
        else:
            raise ValueError(f"Invalid transforms.types rule for '{field_key}'")

        if not type_name:
            raise ValueError(f"Missing type for transforms.types['{field_key}']")
        canonical_type = TYPE_ALIASES.get(str(type_name).strip().lower())
        if canonical_type is None:
            raise ValueError(f"Unsupported type '{type_name}' for field '{field_key}'")
        output[field_key] = {"type": canonical_type, "on_error": on_error}
    return output


def _normalize_format_rules(raw: Any, default_on_error: str) -> Dict[str, Dict[str, Any]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("transforms.formats must be an object")

    output: Dict[str, Dict[str, Any]] = {}
    for field, rule in raw.items():
        field_key = str(field).strip()
        if not field_key:
            continue

        if isinstance(rule, str):
            descriptor: Dict[str, Any] = {"kind": rule}
        elif isinstance(rule, dict):
            descriptor = dict(rule)
        else:
            raise ValueError(f"Invalid transforms.formats rule for '{field_key}'")

        kind_raw = descriptor.get("kind")
        if not kind_raw:
            raise ValueError(f"Missing kind for transforms.formats['{field_key}']")
        canonical_kind = FORMAT_KIND_ALIASES.get(str(kind_raw).strip().lower())
        if canonical_kind is None:
            raise ValueError(f"Unsupported format kind '{kind_raw}' for field '{field_key}'")

        normalized_rule: Dict[str, Any] = {
            "kind": canonical_kind,
            "on_error": _normalize_error_mode(descriptor.get("on_error"), default=default_on_error),
        }

        if canonical_kind in {"excel_serial_datetime", "excel_serial_date"}:
            date_system = str(descriptor.get("date_system", "1900")).strip()
            if date_system not in {"1900", "1904"}:
                raise ValueError(
                    f"Invalid date_system '{date_system}' for field '{field_key}', expected 1900 or 1904"
                )
            normalized_rule["date_system"] = date_system
            normalized_rule["output"] = descriptor.get(
                "output",
                "%Y-%m-%dT%H:%M:%S" if canonical_kind == "excel_serial_datetime" else "%Y-%m-%d",
            )
        elif canonical_kind == "datetime_reformat":
            normalized_rule["input"] = descriptor.get("input") or descriptor.get("input_format")
            normalized_rule["output"] = descriptor.get("output", "%Y-%m-%dT%H:%M:%S")

        output[field_key] = normalized_rule
    return output


def normalize_transforms(transforms: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not transforms:
        return {
            "trim_all": False,
            "trim_fields": set(),
            "defaults": {},
            "type_rules": {},
            "format_rules": {},
            "on_error": "keep",
        }
    if not isinstance(transforms, dict):
        raise ValueError("transforms must be an object")

    # Already normalized (internal call path from load_mapping_config).
    if {"trim_all", "trim_fields", "defaults", "type_rules", "format_rules", "on_error"} <= set(
        transforms.keys()
    ):
        trim_fields_raw = transforms.get("trim_fields") or set()
        if isinstance(trim_fields_raw, set):
            trim_fields = {str(item).strip() for item in trim_fields_raw if str(item).strip()}
        elif isinstance(trim_fields_raw, list):
            trim_fields = {str(item).strip() for item in trim_fields_raw if str(item).strip()}
        else:
            raise ValueError("normalized transforms.trim_fields must be set or list")
        return {
            "trim_all": bool(transforms.get("trim_all", False)),
            "trim_fields": trim_fields,
            "defaults": dict(transforms.get("defaults") or {}),
            "type_rules": dict(transforms.get("type_rules") or {}),
            "format_rules": dict(transforms.get("format_rules") or {}),
            "on_error": _normalize_error_mode(transforms.get("on_error"), default="keep"),
        }

    on_error = _normalize_error_mode(transforms.get("on_error"), default="keep")
    trim_all, trim_fields = _normalize_trim_config(transforms.get("trim"))

    defaults = transforms.get("defaults") or {}
    if not isinstance(defaults, dict):
        raise ValueError("transforms.defaults must be an object")

    return {
        "trim_all": trim_all,
        "trim_fields": trim_fields,
        "defaults": {
            str(key).strip(): value
            for key, value in defaults.items()
            if str(key).strip()
        },
        "type_rules": _normalize_type_rules(transforms.get("types"), on_error),
        "format_rules": _normalize_format_rules(transforms.get("formats"), on_error),
        "on_error": on_error,
    }


def _apply_enum_with_meta(
    source_key: str, target_key: str, value: Any, enum_map: Dict[str, Dict[str, Any]]
) -> Tuple[Any, bool]:
    # Prefer mapped target key rules so CLI overrides like status:启用=1
    # can take precedence over source-column rules from config files.
    for key in (target_key, source_key):
        mapping = enum_map.get(key)
        if not mapping:
            continue

        if value is None and "null" in mapping:
            return mapping["null"], True

        lookup = str(value) if value is not None else ""
        if lookup in mapping:
            return mapping[lookup], True

        if isinstance(value, str):
            stripped = value.strip()
            if stripped in mapping:
                return mapping[stripped], True

    return value, False


def _apply_enum(source_key: str, target_key: str, value: Any, enum_map: Dict[str, Dict[str, Any]]) -> Any:
    mapped_value, _ = _apply_enum_with_meta(source_key, target_key, value, enum_map)
    return mapped_value


def _is_empty_value(value: Any) -> bool:
    return value is None or value == ""


def _resolve_rule(
    rules: Dict[str, Dict[str, Any]], source_key: str, target_key: str
) -> Optional[Dict[str, Any]]:
    if target_key in rules:
        return rules[target_key]
    if source_key in rules:
        return rules[source_key]
    return None


def _should_trim(
    source_key: str, target_key: str, trim_fields: Set[str], trim_all: bool
) -> bool:
    return trim_all or source_key in trim_fields or target_key in trim_fields


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value in (0, 0.0):
            return False
        if value in (1, 1.0):
            return True
        raise ValueError(f"Cannot convert number {value} to bool")
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes", "y", "on"}:
            return True
        if text in {"false", "0", "no", "n", "off"}:
            return False
    raise ValueError(f"Cannot convert value {value!r} to bool")


def _parse_datetime_like(value: Any) -> dt.datetime:
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time.min)
    if not isinstance(value, str):
        raise ValueError(f"Cannot parse datetime from {value!r}")

    text = value.strip()
    if not text:
        raise ValueError("Cannot parse datetime from empty string")

    normalized_text = text.replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(normalized_text)
        if isinstance(parsed, dt.datetime):
            return parsed
    except ValueError:
        pass

    common_patterns = (
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
    )
    for pattern in common_patterns:
        try:
            parsed = dt.datetime.strptime(text, pattern)
            return parsed
        except ValueError:
            continue

    raise ValueError(f"Cannot parse datetime from {value!r}")


def _coerce_type(value: Any, type_name: str) -> Any:
    if value is None:
        return None

    if type_name == "string":
        return value if isinstance(value, str) else str(value)

    if type_name == "int":
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if value.is_integer():
                return int(value)
            raise ValueError(f"Cannot convert non-integer float {value} to int")
        if isinstance(value, str):
            text = value.strip()
            if not text:
                raise ValueError("Cannot convert empty string to int")
            if re.fullmatch(r"[-+]?\d+", text):
                return int(text)
            parsed_float = float(text)
            if parsed_float.is_integer():
                return int(parsed_float)
            raise ValueError(f"Cannot convert non-integer string {value!r} to int")
        raise ValueError(f"Cannot convert {value!r} to int")

    if type_name == "float":
        if isinstance(value, bool):
            return float(int(value))
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                raise ValueError("Cannot convert empty string to float")
            return float(text)
        raise ValueError(f"Cannot convert {value!r} to float")

    if type_name == "bool":
        return _parse_bool(value)

    if type_name == "date":
        parsed = _parse_datetime_like(value)
        return parsed.strftime("%Y-%m-%d")

    if type_name == "datetime":
        parsed = _parse_datetime_like(value)
        return parsed.strftime("%Y-%m-%dT%H:%M:%S")

    raise ValueError(f"Unsupported type conversion: {type_name}")


def _parse_excel_serial(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("Bool is not a valid Excel serial number")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("Empty string is not a valid Excel serial number")
        return float(text)
    raise ValueError(f"Unsupported Excel serial type: {type(value).__name__}")


def _excel_serial_to_datetime(serial: float, date_system: str) -> dt.datetime:
    if date_system == "1900":
        days = serial
        if days >= 60:
            days -= 1
        return dt.datetime(1899, 12, 31) + dt.timedelta(days=days)
    if date_system == "1904":
        return dt.datetime(1904, 1, 1) + dt.timedelta(days=serial)
    raise ValueError(f"Unsupported date_system: {date_system}")


def _apply_format(value: Any, rule: Dict[str, Any]) -> Any:
    kind = rule["kind"]
    if kind in {"excel_serial_datetime", "excel_serial_date"}:
        serial = _parse_excel_serial(value)
        parsed = _excel_serial_to_datetime(serial, rule["date_system"])
        return parsed.strftime(rule["output"])

    if kind == "datetime_reformat":
        if isinstance(value, str):
            text = value.strip()
            if not text:
                raise ValueError("Cannot reformat empty datetime string")
        else:
            text = value

        input_pattern = rule.get("input")
        if input_pattern:
            if not isinstance(text, str):
                raise ValueError("datetime_reformat with input pattern expects string value")
            parsed = dt.datetime.strptime(text, input_pattern)
        else:
            parsed = _parse_datetime_like(text)
        return parsed.strftime(rule["output"])

    raise ValueError(f"Unsupported format kind: {kind}")


def _normalize_defaults(defaults: Dict[str, Any], column_map: Dict[str, str]) -> Dict[str, Any]:
    output: Dict[str, Any] = {}
    for field, value in defaults.items():
        source_key = str(field).strip()
        if not source_key:
            continue
        target_key = column_map.get(source_key, source_key)
        output[target_key] = value
    return output


def _handle_transform_error(mode: str, current_value: Any, error: Exception) -> Any:
    if mode == "raise":
        raise ValueError(str(error))
    if mode == "null":
        return None
    return current_value


def _init_stats(total_rows: int) -> Dict[str, int]:
    return {
        "input_rows": total_rows,
        "output_rows": 0,
        "enum_applied": 0,
        "trim_applied": 0,
        "format_applied": 0,
        "format_errors": 0,
        "type_applied": 0,
        "type_errors": 0,
        "defaults_applied": 0,
        "dropped_empty_fields": 0,
    }


def transform_records_with_stats(
    records: Sequence[Dict[str, Any]],
    column_map: Optional[Dict[str, Any]] = None,
    enum_map: Optional[Dict[str, Any]] = None,
    drop_empty: bool = False,
    transforms: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    normalized_column_map = normalize_column_map(column_map)
    normalized_enum_map = normalize_enum_map(enum_map)
    normalized_transforms = normalize_transforms(transforms)

    trim_all = normalized_transforms["trim_all"]
    trim_fields: Set[str] = normalized_transforms["trim_fields"]
    type_rules = normalized_transforms["type_rules"]
    format_rules = normalized_transforms["format_rules"]
    defaults = _normalize_defaults(normalized_transforms["defaults"], normalized_column_map)

    stats = _init_stats(len(records))
    output: List[Dict[str, Any]] = []
    for row_index, record in enumerate(records, start=1):
        mapped_record: Dict[str, Any] = {}
        for source_key, raw_value in record.items():
            source_text = str(source_key).strip()
            target_key = normalized_column_map.get(source_text, source_text)

            mapped_value, enum_hit = _apply_enum_with_meta(
                source_text, target_key, raw_value, normalized_enum_map
            )
            if enum_hit:
                stats["enum_applied"] += 1

            if isinstance(mapped_value, str) and _should_trim(
                source_text, target_key, trim_fields, trim_all
            ):
                trimmed = mapped_value.strip()
                if trimmed != mapped_value:
                    stats["trim_applied"] += 1
                mapped_value = trimmed

            format_rule = _resolve_rule(format_rules, source_text, target_key)
            if format_rule is not None and not _is_empty_value(mapped_value):
                try:
                    converted = _apply_format(mapped_value, format_rule)
                    if converted != mapped_value:
                        stats["format_applied"] += 1
                    mapped_value = converted
                except ValueError as exc:
                    stats["format_errors"] += 1
                    wrapped = ValueError(
                        f"Row {row_index} field '{target_key}' format conversion failed: {exc}"
                    )
                    mapped_value = _handle_transform_error(
                        format_rule["on_error"], mapped_value, wrapped
                    )

            type_rule = _resolve_rule(type_rules, source_text, target_key)
            if type_rule is not None and not _is_empty_value(mapped_value):
                try:
                    converted = _coerce_type(mapped_value, type_rule["type"])
                    if converted != mapped_value or type(converted) is not type(mapped_value):
                        stats["type_applied"] += 1
                    mapped_value = converted
                except ValueError as exc:
                    stats["type_errors"] += 1
                    wrapped = ValueError(
                        f"Row {row_index} field '{target_key}' type conversion failed: {exc}"
                    )
                    mapped_value = _handle_transform_error(
                        type_rule["on_error"], mapped_value, wrapped
                    )

            if drop_empty and _is_empty_value(mapped_value):
                stats["dropped_empty_fields"] += 1
                continue

            mapped_record[target_key] = mapped_value

        for key, default_value in defaults.items():
            if key not in mapped_record or _is_empty_value(mapped_record.get(key)):
                mapped_record[key] = default_value
                stats["defaults_applied"] += 1

        output.append(mapped_record)

    stats["output_rows"] = len(output)
    return output, stats


def transform_records(
    records: Sequence[Dict[str, Any]],
    column_map: Optional[Dict[str, Any]] = None,
    enum_map: Optional[Dict[str, Any]] = None,
    drop_empty: bool = False,
    transforms: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    output, _ = transform_records_with_stats(
        records,
        column_map=column_map,
        enum_map=enum_map,
        drop_empty=drop_empty,
        transforms=transforms,
    )
    return output


def _parse_json_value(text: str) -> Any:
    trimmed = text.strip()
    try:
        return json.loads(trimmed)
    except json.JSONDecodeError:
        return trimmed


def parse_column_map_args(values: Iterable[str]) -> Dict[str, str]:
    output: Dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"Invalid --map value '{item}'. Use source=target")
        source, target = item.split("=", 1)
        source = source.strip()
        target = target.strip()
        if not source or not target:
            raise ValueError(f"Invalid --map value '{item}'. Use source=target")
        output[source] = target
    return output


def parse_enum_map_args(values: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    for item in values:
        if ":" not in item or "=" not in item:
            raise ValueError(
                f"Invalid --enum value '{item}'. Use column:sourceValue=targetValue"
            )

        column, rest = item.split(":", 1)
        source_value, target_value = rest.split("=", 1)

        column = column.strip()
        source_value = source_value.strip()
        if not column or not source_value:
            raise ValueError(
                f"Invalid --enum value '{item}'. Use column:sourceValue=targetValue"
            )

        output.setdefault(column, {})[source_value] = _parse_json_value(target_value)

    return output


def load_mapping_config(
    path: Optional[Path],
) -> Tuple[Dict[str, str], Dict[str, Dict[str, Any]], Dict[str, Any]]:
    if path is None:
        return {}, {}, {}

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Config file root must be an object")

    column_map = payload.get("column_map") or payload.get("column_mapping") or {}
    enum_map = payload.get("enum_map") or payload.get("enum_mapping") or {}
    transforms = payload.get("transforms") or {}

    # Compatibility aliases for v2 config.
    if not transforms and any(key in payload for key in ("defaults", "types", "formats", "trim")):
        transforms = {
            "defaults": payload.get("defaults"),
            "types": payload.get("types"),
            "formats": payload.get("formats"),
            "trim": payload.get("trim"),
            "on_error": payload.get("on_error"),
        }

    return (
        normalize_column_map(column_map),
        normalize_enum_map(enum_map),
        normalize_transforms(transforms),
    )


def merge_mappings(
    base_column_map: Dict[str, str],
    base_enum_map: Dict[str, Dict[str, Any]],
    override_column_map: Dict[str, str],
    override_enum_map: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, str], Dict[str, Dict[str, Any]]]:
    merged_column = dict(base_column_map)
    merged_column.update(override_column_map)

    merged_enum: Dict[str, Dict[str, Any]] = {
        key: dict(value) for key, value in base_enum_map.items()
    }
    for column, mapping in override_enum_map.items():
        merged_enum.setdefault(column, {}).update(mapping)

    return merged_column, merged_enum


def convert_xlsx(
    xlsx_path: Path,
    sheet_name: Optional[str],
    header_row: int,
    column_map: Optional[Dict[str, Any]],
    enum_map: Optional[Dict[str, Any]],
    drop_empty: bool,
    transforms: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    records = read_xlsx_records(xlsx_path, sheet_name=sheet_name, header_row=header_row)
    return transform_records(
        records,
        column_map=column_map,
        enum_map=enum_map,
        drop_empty=drop_empty,
        transforms=transforms,
    )


def convert_xlsx_with_stats(
    xlsx_path: Path,
    sheet_name: Optional[str],
    header_row: int,
    column_map: Optional[Dict[str, Any]],
    enum_map: Optional[Dict[str, Any]],
    drop_empty: bool,
    transforms: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    records = read_xlsx_records(xlsx_path, sheet_name=sheet_name, header_row=header_row)
    return transform_records_with_stats(
        records,
        column_map=column_map,
        enum_map=enum_map,
        drop_empty=drop_empty,
        transforms=transforms,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert XLSX rows to JSON with column mapping, enum mapping, "
            "and optional transforms (trim/types/formats/defaults)."
        )
    )
    parser.add_argument("--xlsx", type=Path, required=True, help="Path to source .xlsx file")
    parser.add_argument("--output", type=Path, help="Path to output .json file")
    parser.add_argument("--sheet", help="Worksheet name (default: first sheet)")
    parser.add_argument(
        "--header-row",
        type=int,
        default=1,
        help="Header row number in worksheet (1-based, default: 1)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help=(
            "JSON config file. Supports v1 (column_map/enum_map) and "
            "v2 transforms (trim/types/formats/defaults)"
        ),
    )
    parser.add_argument(
        "--map",
        action="append",
        default=[],
        metavar="SRC=DST",
        help="Column mapping rule, repeatable. Example: 名称=name",
    )
    parser.add_argument(
        "--enum",
        action="append",
        default=[],
        metavar="COL:FROM=TO",
        help=(
            "Enum mapping rule, repeatable. Example: 状态:启用=\"ACTIVE\" "
            "or 状态:启用=1"
        ),
    )
    parser.add_argument(
        "--drop-empty",
        action="store_true",
        help="Drop keys whose mapped value is null or empty string",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation spaces (default: 2)",
    )
    parser.add_argument(
        "--ensure-ascii",
        action="store_true",
        help="Escape all non-ASCII characters in output JSON",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.xlsx.exists():
        parser.error(f"XLSX file not found: {args.xlsx}")

    try:
        config_column_map, config_enum_map, config_transforms = load_mapping_config(args.config)
        cli_column_map = parse_column_map_args(args.map)
        cli_enum_map = parse_enum_map_args(args.enum)

        column_map, enum_map = merge_mappings(
            config_column_map,
            config_enum_map,
            cli_column_map,
            cli_enum_map,
        )

        converted, stats = convert_xlsx_with_stats(
            xlsx_path=args.xlsx,
            sheet_name=args.sheet,
            header_row=args.header_row,
            column_map=column_map,
            enum_map=enum_map,
            drop_empty=args.drop_empty,
            transforms=config_transforms,
        )

        output_path = args.output or args.xlsx.with_suffix(".json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                converted,
                ensure_ascii=args.ensure_ascii,
                indent=args.indent,
            )
            + "\n",
            encoding="utf-8",
        )

        print(f"Converted {len(converted)} rows -> {output_path}")
        print(f"Stats: {json.dumps(stats, ensure_ascii=False)}")
        return 0
    except (ValueError, KeyError, zipfile.BadZipFile) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
