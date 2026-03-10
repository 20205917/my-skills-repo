import importlib.util
import random
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "skills" / "data-generator" / "scripts" / "generate_test_data.py"


def load_module():
    spec = importlib.util.spec_from_file_location("generate_test_data", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class DataGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_module()

    def test_parse_ddl_with_explicit_foreign_key(self):
        ddl = """
        CREATE TABLE lines (
          id BIGINT PRIMARY KEY,
          name VARCHAR(64) NOT NULL
        );

        CREATE TABLE devices (
          id BIGINT PRIMARY KEY,
          line_id BIGINT NOT NULL,
          FOREIGN KEY (line_id) REFERENCES lines(id)
        );
        """
        tables = self.mod.parse_ddl(ddl)
        self.assertIn("lines", tables)
        self.assertIn("devices", tables)
        self.assertEqual(len(tables["devices"].foreign_keys), 1)
        fk = tables["devices"].foreign_keys[0]
        self.assertEqual((fk.column, fk.ref_table, fk.ref_column), ("line_id", "lines", "id"))

    def test_infer_implicit_foreign_key_from_column_name(self):
        ddl = """
        CREATE TABLE factories (
          id BIGINT PRIMARY KEY,
          name VARCHAR(64) NOT NULL
        );
        CREATE TABLE devices (
          id BIGINT PRIMARY KEY,
          factory_id BIGINT NOT NULL
        );
        """
        tables = self.mod.parse_ddl(ddl)
        inference_log = []
        self.mod.infer_implicit_foreign_keys(tables, inference_log)

        fks = tables["devices"].foreign_keys
        self.assertEqual(len(fks), 1)
        self.assertEqual((fks[0].column, fks[0].ref_table, fks[0].ref_column), ("factory_id", "factories", "id"))
        self.assertTrue(inference_log)

    def test_generate_and_validate_legal_data(self):
        ddl = """
        CREATE TABLE lines (
          id BIGINT PRIMARY KEY,
          name VARCHAR(64) NOT NULL
        );

        CREATE TABLE devices (
          id BIGINT PRIMARY KEY,
          line_id BIGINT NOT NULL,
          name VARCHAR(64) NOT NULL,
          created_at DATETIME NOT NULL,
          updated_at DATETIME NOT NULL,
          FOREIGN KEY (line_id) REFERENCES lines(id)
        );
        """
        tables = self.mod.parse_ddl(ddl)
        order = self.mod.compute_insert_order(tables)
        row_plan = self.mod.build_row_plan(tables, default_rows=5, table_rows=[], override_rows={}, entity_rows={})
        generated = self.mod.generate_rows(
            tables=tables,
            order=order,
            row_plan=row_plan,
            rng=random.Random(42),
            window_days=7,
            profile="generic",
        )

        validation = self.mod.validate_data(tables, order, generated)
        self.assertTrue(validation.ok, msg="\n".join(validation.issues))
        self.assertLess(order.index("lines"), order.index("devices"))
        self.assertEqual(len(generated["lines"]), 5)
        self.assertEqual(len(generated["devices"]), 5)


if __name__ == "__main__":
    unittest.main()
