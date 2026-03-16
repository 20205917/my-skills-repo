import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "skills" / "xlsx2json" / "scripts" / "xlsx_to_json.py"


def load_module():
    spec = importlib.util.spec_from_file_location("xlsx_to_json", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def excel_col_name(index: int) -> str:
    if index <= 0:
        raise ValueError("index must be >= 1")

    name = []
    value = index
    while value > 0:
        value, rem = divmod(value - 1, 26)
        name.append(chr(ord("A") + rem))
    return "".join(reversed(name))


def build_minimal_xlsx(path: Path, rows):
    shared_strings = []
    shared_indexes = {}

    def shared_index(text: str) -> int:
        if text not in shared_indexes:
            shared_indexes[text] = len(shared_strings)
            shared_strings.append(text)
        return shared_indexes[text]

    row_xml_parts = []
    for row_idx, row in enumerate(rows, start=1):
        cells = []
        for col_idx, value in enumerate(row, start=1):
            if value is None:
                continue

            cell_ref = f"{excel_col_name(col_idx)}{row_idx}"
            if isinstance(value, bool):
                cells.append(f'<c r="{cell_ref}" t="b"><v>{1 if value else 0}</v></c>')
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{cell_ref}"><v>{value}</v></c>')
            else:
                idx = shared_index(str(value))
                cells.append(f'<c r="{cell_ref}" t="s"><v>{idx}</v></c>')

        row_xml_parts.append(f'<row r="{row_idx}">{"".join(cells)}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheetData>{"".join(row_xml_parts)}</sheetData>'
        "</worksheet>"
    )

    shared_items = "".join(f"<si><t>{escape(text)}</t></si>" for text in shared_strings)
    shared_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{len(shared_strings)}" uniqueCount="{len(shared_strings)}">'
        f"{shared_items}</sst>"
    )

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )

    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )

    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/sharedStrings.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        "</Types>"
    )

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", root_rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        zf.writestr("xl/sharedStrings.xml", shared_xml)


class XlsxToJsonTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_module()

    def test_read_xlsx_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            xlsx_path = Path(tmpdir) / "input.xlsx"
            build_minimal_xlsx(
                xlsx_path,
                rows=[
                    ["名称", "状态", "年龄"],
                    ["A", "启用", 18],
                    ["B", "禁用", 20],
                ],
            )

            records = self.mod.read_xlsx_records(xlsx_path)
            self.assertEqual(
                records,
                [
                    {"名称": "A", "状态": "启用", "年龄": 18},
                    {"名称": "B", "状态": "禁用", "年龄": 20},
                ],
            )

    def test_transform_records_with_column_and_enum_mapping(self):
        source = [
            {"名称": "A", "状态": "启用", "年龄": 18},
            {"名称": "B", "状态": "禁用", "年龄": 20},
        ]

        result = self.mod.transform_records(
            source,
            column_map={"名称": "name", "状态": "status"},
            enum_map={"status": {"启用": 1, "禁用": 0}},
        )

        self.assertEqual(
            result,
            [
                {"name": "A", "status": 1, "年龄": 18},
                {"name": "B", "status": 0, "年龄": 20},
            ],
        )

    def test_cli_convert_with_config_and_inline_enum_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            xlsx_path = tmpdir_path / "input.xlsx"
            json_path = tmpdir_path / "output.json"
            config_path = tmpdir_path / "mapping.json"

            build_minimal_xlsx(
                xlsx_path,
                rows=[
                    ["名称", "状态"],
                    ["A", "启用"],
                    ["B", "禁用"],
                ],
            )

            config_path.write_text(
                json.dumps(
                    {
                        "column_map": {"名称": "name", "状态": "status"},
                        "enum_map": {"状态": {"启用": "ACTIVE", "禁用": "INACTIVE"}},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--xlsx",
                    str(xlsx_path),
                    "--config",
                    str(config_path),
                    "--enum",
                    "status:启用=1",
                    "--enum",
                    "status:禁用=0",
                    "--output",
                    str(json_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(
                payload,
                [
                    {"name": "A", "status": 1},
                    {"name": "B", "status": 0},
                ],
            )
            self.assertIn("Stats:", completed.stdout)

    def test_transform_records_with_transforms_and_stats(self):
        source = [
            {
                "订单号": " A001 ",
                "批次": 101,
                "封装类型": 2,
                "生产时间": 45200.5,
                "数量": "",
                "状态": "启用",
            }
        ]

        converted, stats = self.mod.transform_records_with_stats(
            source,
            column_map={
                "订单号": "orderCode",
                "批次": "batch",
                "封装类型": "encapsulationType",
                "生产时间": "produceTime",
                "数量": "quantity",
                "状态": "status",
            },
            enum_map={"status": {"启用": 1, "禁用": 0}},
            drop_empty=True,
            transforms={
                "trim": ["orderCode"],
                "types": {
                    "batch": "string",
                    "encapsulationType": "string",
                },
                "formats": {
                    "produceTime": {
                        "kind": "excel_serial_datetime",
                        "output": "%Y-%m-%dT%H:%M:%S",
                    }
                },
                "defaults": {
                    "quantity": None,
                    "alias": None,
                    "bigAlias": None,
                },
            },
        )

        self.assertEqual(
            converted,
            [
                {
                    "orderCode": "A001",
                    "batch": "101",
                    "encapsulationType": "2",
                    "produceTime": "2023-10-01T12:00:00",
                    "status": 1,
                    "quantity": None,
                    "alias": None,
                    "bigAlias": None,
                }
            ],
        )
        self.assertEqual(
            stats,
            {
                "input_rows": 1,
                "output_rows": 1,
                "enum_applied": 1,
                "trim_applied": 1,
                "format_applied": 1,
                "format_errors": 0,
                "type_applied": 2,
                "type_errors": 0,
                "defaults_applied": 3,
                "dropped_empty_fields": 1,
            },
        )

    def test_transform_records_type_error_keep_value(self):
        source = [{"批次": "ABC"}]
        converted, stats = self.mod.transform_records_with_stats(
            source,
            column_map={"批次": "batch"},
            transforms={"types": {"batch": "int"}},
        )
        self.assertEqual(converted, [{"batch": "ABC"}])
        self.assertEqual(stats["type_errors"], 1)

    def test_cli_convert_with_v2_transforms_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            xlsx_path = tmpdir_path / "input.xlsx"
            json_path = tmpdir_path / "output.json"
            config_path = tmpdir_path / "mapping_v2.json"

            build_minimal_xlsx(
                xlsx_path,
                rows=[
                    ["订单号", "批次", "封装类型", "生产时间", "状态"],
                    [" A001 ", 101, 2, 45200.5, "启用"],
                ],
            )

            config_path.write_text(
                json.dumps(
                    {
                        "column_map": {
                            "订单号": "orderCode",
                            "批次": "batch",
                            "封装类型": "encapsulationType",
                            "生产时间": "produceTime",
                            "状态": "status",
                        },
                        "enum_map": {
                            "status": {"启用": 1, "禁用": 0},
                        },
                        "transforms": {
                            "trim": ["orderCode"],
                            "types": {
                                "batch": "string",
                                "encapsulationType": "string",
                            },
                            "formats": {
                                "produceTime": {
                                    "kind": "excel_serial_datetime",
                                    "output": "%Y-%m-%dT%H:%M:%S",
                                }
                            },
                            "defaults": {
                                "quantity": None,
                                "alias": None,
                                "bigAlias": None,
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--xlsx",
                    str(xlsx_path),
                    "--config",
                    str(config_path),
                    "--output",
                    str(json_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(
                payload,
                [
                    {
                        "orderCode": "A001",
                        "batch": "101",
                        "encapsulationType": "2",
                        "produceTime": "2023-10-01T12:00:00",
                        "status": 1,
                        "quantity": None,
                        "alias": None,
                        "bigAlias": None,
                    }
                ],
            )
            self.assertIn("Stats:", completed.stdout)


if __name__ == "__main__":
    unittest.main()
