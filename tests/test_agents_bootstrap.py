import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "skills" / "agents-bootstrap" / "scripts" / "init_agents_md.py"


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def build_project_fixture(project_root: Path):
    (project_root / "skills" / "demo").mkdir(parents=True)
    (project_root / "skills" / "demo" / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\n---\n",
        encoding="utf-8",
    )
    (project_root / "tests").mkdir(parents=True)
    (project_root / "tests" / "test_demo.py").write_text("import unittest\n", encoding="utf-8")
    (project_root / "README.md").write_text("# Demo\n", encoding="utf-8")


class AgentsBootstrapTests(unittest.TestCase):
    def test_default_scope_is_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            project_root = base / "repo"
            project_root.mkdir()
            build_project_fixture(project_root)
            codex_home = base / "codex-home"

            completed = run_cli(
                "--project-root",
                str(project_root),
                "--codex-home",
                str(codex_home),
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            self.assertFalse((codex_home / "AGENTS.md").exists())
            self.assertTrue((project_root / "AGENTS.md").exists())

    def test_scope_global_project_both(self):
        cases = [
            ("global", True, False),
            ("project", False, True),
            ("both", True, True),
        ]

        for scope, expect_global, expect_project in cases:
            with self.subTest(scope=scope):
                with tempfile.TemporaryDirectory() as tmpdir:
                    base = Path(tmpdir)
                    project_root = base / "repo"
                    project_root.mkdir()
                    build_project_fixture(project_root)
                    codex_home = base / "codex-home"

                    completed = run_cli(
                        "--scope",
                        scope,
                        "--project-root",
                        str(project_root),
                        "--codex-home",
                        str(codex_home),
                    )

                    self.assertEqual(completed.returncode, 0, msg=completed.stderr)

                    global_file = codex_home / "AGENTS.md"
                    project_file = project_root / "AGENTS.md"
                    self.assertEqual(global_file.exists(), expect_global)
                    self.assertEqual(project_file.exists(), expect_project)

                    if expect_global:
                        text = global_file.read_text(encoding="utf-8")
                        self.assertIn("## 语言与输出", text)
                    if expect_project:
                        text = project_file.read_text(encoding="utf-8")
                        self.assertIn("## 项目基础信息", text)

    def test_global_template_is_reusable_and_project_agnostic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            project_root = base / "repo"
            project_root.mkdir()
            build_project_fixture(project_root)
            codex_home = base / "codex-home"

            completed = run_cli(
                "--scope",
                "global",
                "--project-root",
                str(project_root),
                "--codex-home",
                str(codex_home),
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            text = (codex_home / "AGENTS.md").read_text(encoding="utf-8")

            self.assertIn("# AGENTS 全局规则", text)
            self.assertIn("## 风险与边界", text)
            self.assertIn("## Git 纪律", text)
            self.assertNotIn("最后生成时间", text)
            self.assertNotIn("最近初始化来源项目", text)
            self.assertNotIn("目录结构", text)
            self.assertNotIn("测试命令", text)
            self.assertNotIn("README", text)

    def test_existing_file_requires_force(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            project_root = base / "repo"
            project_root.mkdir()
            build_project_fixture(project_root)
            codex_home = base / "codex-home"

            target = project_root / "AGENTS.md"
            target.write_text("ORIGINAL\n", encoding="utf-8")

            completed = run_cli(
                "--scope",
                "project",
                "--project-root",
                str(project_root),
                "--codex-home",
                str(codex_home),
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("already exists", completed.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), "ORIGINAL\n")

    def test_force_overwrites_existing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            project_root = base / "repo"
            project_root.mkdir()
            build_project_fixture(project_root)
            codex_home = base / "codex-home"

            target = project_root / "AGENTS.md"
            target.write_text("ORIGINAL\n", encoding="utf-8")

            completed = run_cli(
                "--scope",
                "project",
                "--project-root",
                str(project_root),
                "--codex-home",
                str(codex_home),
                "--force",
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            content = target.read_text(encoding="utf-8")
            self.assertNotEqual(content, "ORIGINAL\n")
            self.assertIn("## 项目基础信息", content)

    def test_dry_run_does_not_write_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            project_root = base / "repo"
            project_root.mkdir()
            build_project_fixture(project_root)
            codex_home = base / "codex-home"

            completed = run_cli(
                "--scope",
                "both",
                "--project-root",
                str(project_root),
                "--codex-home",
                str(codex_home),
                "--dry-run",
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            self.assertIn("[DRY-RUN]", completed.stdout)
            self.assertFalse((codex_home / "AGENTS.md").exists())
            self.assertFalse((project_root / "AGENTS.md").exists())
            self.assertFalse((project_root / ".gitignore").exists())

    def test_dry_run_allows_existing_without_force(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            project_root = base / "repo"
            project_root.mkdir()
            build_project_fixture(project_root)
            codex_home = base / "codex-home"

            target = project_root / "AGENTS.md"
            target.write_text("ORIGINAL\n", encoding="utf-8")

            completed = run_cli(
                "--scope",
                "project",
                "--project-root",
                str(project_root),
                "--codex-home",
                str(codex_home),
                "--dry-run",
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            self.assertIn("[DRY-RUN]", completed.stdout)
            self.assertEqual(target.read_text(encoding="utf-8"), "ORIGINAL\n")

    def test_project_write_updates_gitignore_without_duplication(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            project_root = base / "repo"
            project_root.mkdir()
            build_project_fixture(project_root)
            codex_home = base / "codex-home"

            first_run = run_cli(
                "--scope",
                "project",
                "--project-root",
                str(project_root),
                "--codex-home",
                str(codex_home),
            )
            self.assertEqual(first_run.returncode, 0, msg=first_run.stderr)

            gitignore = project_root / ".gitignore"
            self.assertTrue(gitignore.exists())
            text = gitignore.read_text(encoding="utf-8")
            self.assertIn("AGENTS.md\n", text)
            self.assertEqual(text.splitlines().count("AGENTS.md"), 1)

            second_run = run_cli(
                "--scope",
                "project",
                "--project-root",
                str(project_root),
                "--codex-home",
                str(codex_home),
                "--force",
            )
            self.assertEqual(second_run.returncode, 0, msg=second_run.stderr)
            text = gitignore.read_text(encoding="utf-8")
            self.assertEqual(text.splitlines().count("AGENTS.md"), 1)

    def test_template_is_chinese_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            project_root = base / "repo"
            project_root.mkdir()
            build_project_fixture(project_root)
            codex_home = base / "codex-home"

            run_result = run_cli(
                "--scope",
                "project",
                "--project-root",
                str(project_root),
                "--codex-home",
                str(codex_home),
            )
            self.assertEqual(run_result.returncode, 0, msg=run_result.stderr)

            text = (project_root / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("## 项目基础信息", text)
            self.assertIn("## 环境搭建与开发流程", text)
            self.assertIn("## 测试规范", text)
            self.assertIn("## 约定规则", text)
            self.assertIn("### 必须做", text)
            self.assertIn("### 先询问", text)
            self.assertIn("### 绝对禁止", text)
            self.assertIn("## 项目级与子目录级修改规则", text)
            self.assertNotIn("最后生成时间", text)
            self.assertNotIn("## 项目技能索引", text)
            self.assertNotIn("## 目录结构", text)
            self.assertNotIn("## 代码风格规范", text)
            self.assertNotIn("## 操作边界与禁止行为", text)
            self.assertNotIn("## Project Skill Index", text)

    def test_project_template_falls_back_to_todo_when_not_detectable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            project_root = base / "repo"
            project_root.mkdir()
            codex_home = base / "codex-home"

            completed = run_cli(
                "--scope",
                "project",
                "--project-root",
                str(project_root),
                "--codex-home",
                str(codex_home),
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)

            text = (project_root / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("TODO: 请补充项目类型", text)
            self.assertIn("TODO: 请补充核心技术栈", text)
            self.assertIn("TODO: 请补充项目用途、目标用户与业务边界", text)
            self.assertIn("TODO: 请补充环境搭建命令。", text)
            self.assertIn("TODO: 请补充测试执行命令", text)


if __name__ == "__main__":
    unittest.main()
