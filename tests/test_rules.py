import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "skills" / "personal-workstyle" / "scripts" / "rules.py"


def load_module():
    spec = importlib.util.spec_from_file_location("rules_tool", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RulesToolTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_module()
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)

        self.active = base / "active.md"
        self.pending = base / "pending.md"
        self.history = base / "history.md"

        self.active.write_text("# Active Rules\n\n- [R001] 默认使用中文。\n", encoding="utf-8")
        self.pending.write_text("# Pending Rules\n\n", encoding="utf-8")
        self.history.write_text("# Rule Change History\n\n", encoding="utf-8")

        self.old_active = self.mod.ACTIVE
        self.old_pending = self.mod.PENDING
        self.old_history = self.mod.HISTORY

        self.mod.ACTIVE = self.active
        self.mod.PENDING = self.pending
        self.mod.HISTORY = self.history

    def tearDown(self):
        self.mod.ACTIVE = self.old_active
        self.mod.PENDING = self.old_pending
        self.mod.HISTORY = self.old_history
        self.tmp.cleanup()

    def test_add_and_promote_pending_rule(self):
        self.mod.add_pending("输出包含 Done / Decision / Next。")
        pending_text = self.pending.read_text(encoding="utf-8")
        self.assertIn("- [P001] 输出包含 Done / Decision / Next。", pending_text)

        self.mod.promote_pending("P001")
        active_text = self.active.read_text(encoding="utf-8")
        pending_text = self.pending.read_text(encoding="utf-8")
        history_text = self.history.read_text(encoding="utf-8")

        self.assertIn("- [R002] 输出包含 Done / Decision / Next。", active_text)
        self.assertNotIn("P001", pending_text)
        self.assertIn("PROMOTE P001 -> R002", history_text)

    def test_remove_active_rule(self):
        self.mod.remove_active("R001")
        active_text = self.active.read_text(encoding="utf-8")
        history_text = self.history.read_text(encoding="utf-8")

        self.assertNotIn("R001", active_text)
        self.assertIn("REMOVE R001", history_text)

    def test_promote_missing_rule_raises(self):
        with self.assertRaises(SystemExit):
            self.mod.promote_pending("P999")


if __name__ == "__main__":
    unittest.main()
