import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "skills" / "agents-bootstrap" / "scripts" / "init_agents_md.py"
UNITTEST_CMD = 'python3 -m unittest discover -s tests -p "test_*.py" -v'


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def build_project_fixture(project_root: Path, include_readme: bool = True, include_skills_index: bool = True):
    (project_root / "skills" / "demo").mkdir(parents=True)
    (project_root / "skills" / "demo" / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo skill\n---\n",
        encoding="utf-8",
    )
    (project_root / "tests").mkdir(parents=True)
    (project_root / "tests" / "test_demo.py").write_text("import unittest\n", encoding="utf-8")
    if include_readme:
        (project_root / "README.md").write_text("# Demo Repo\n", encoding="utf-8")
    if include_skills_index:
        (project_root / "skills-index.md").write_text(
            "# Skills Index\n\n"
            "- `demo`\n"
            "  - 用途：demo skill\n"
            "  - 入口：`skills/demo/SKILL.md`\n",
            encoding="utf-8",
        )


def build_valid_draft(include_pending: bool = False) -> str:
    text = f"""# AGENTS 开发指南（demo）

## 当前技能与位置

- `demo`
  - 位置：`skills/demo/`
  - 入口：`skills/demo/SKILL.md`

## 开发者快速命令

```bash
{UNITTEST_CMD}
```

## 测试

```bash
{UNITTEST_CMD}
```

## 目录结构

```text
skills/
tests/
```

## 维护约定

- 新增或修改核心脚本时，同时补充对应测试用例。
"""
    if include_pending:
        text += "\n## 待确认项\n\n- README.md 缺失或不可读\n"
    return text


class AgentsBootstrapTests(unittest.TestCase):
    def test_global_scope_still_uses_template(self):
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
            self.assertTrue((codex_home / "AGENTS.md").exists())
            self.assertFalse((project_root / "AGENTS.md").exists())
            text = (codex_home / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("# AGENTS 全局规则", text)

    def test_project_without_draft_outputs_prompt_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "repo"
            project_root.mkdir()
            build_project_fixture(project_root)

            completed = run_cli(
                "--scope",
                "project",
                "--project-root",
                str(project_root),
                "--dry-run",
                "--no-print-prompt",
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            self.assertIn("未提供 --draft-file", completed.stdout)
            self.assertFalse((project_root / "AGENTS.md").exists())

    def test_project_prompt_output_can_be_written(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "repo"
            project_root.mkdir()
            build_project_fixture(project_root)
            prompt_output = Path(tmpdir) / "prompt.md"

            completed = run_cli(
                "--scope",
                "project",
                "--project-root",
                str(project_root),
                "--prompt-output",
                str(prompt_output),
                "--no-print-prompt",
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            self.assertTrue(prompt_output.exists())
            text = prompt_output.read_text(encoding="utf-8")
            self.assertIn("PROJECT_FACTS", text)
            self.assertIn("STYLE_RULES", text)
            self.assertIn("PRESERVE_RULES", text)
            self.assertIn("demo", text)
            self.assertIn("python3 -m unittest discover -s tests -p", text)
            self.assertIn("test_*.py", text)
            self.assertFalse((project_root / "AGENTS.md").exists())

    def test_project_draft_validation_rejects_placeholders(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "repo"
            project_root.mkdir()
            build_project_fixture(project_root)

            draft = Path(tmpdir) / "draft.md"
            draft.write_text(build_valid_draft() + "\nTODO: 请补充\n", encoding="utf-8")

            completed = run_cli(
                "--scope",
                "project",
                "--project-root",
                str(project_root),
                "--draft-file",
                str(draft),
                "--dry-run",
                "--no-print-prompt",
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("占位词", completed.stdout)
            self.assertFalse((project_root / "AGENTS.md").exists())

    def test_project_dry_run_with_draft_shows_diff_without_writing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "repo"
            project_root.mkdir()
            build_project_fixture(project_root)

            target = project_root / "AGENTS.md"
            target.write_text("# OLD\n", encoding="utf-8")
            draft = Path(tmpdir) / "draft.md"
            draft.write_text(build_valid_draft(), encoding="utf-8")

            completed = run_cli(
                "--scope",
                "project",
                "--project-root",
                str(project_root),
                "--draft-file",
                str(draft),
                "--dry-run",
                "--no-print-prompt",
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            self.assertIn("[DIFF]", completed.stdout)
            self.assertIn("[DRY-RUN] project", completed.stdout)
            self.assertEqual(target.read_text(encoding="utf-8"), "# OLD\n")

    def test_project_write_requires_force_when_target_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "repo"
            project_root.mkdir()
            build_project_fixture(project_root)

            target = project_root / "AGENTS.md"
            target.write_text("# OLD\n", encoding="utf-8")
            draft = Path(tmpdir) / "draft.md"
            draft.write_text(build_valid_draft(), encoding="utf-8")

            completed = run_cli(
                "--scope",
                "project",
                "--project-root",
                str(project_root),
                "--draft-file",
                str(draft),
                "--no-print-prompt",
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("already exists", completed.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), "# OLD\n")

    def test_project_write_with_force_creates_backup_and_updates_gitignore(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "repo"
            project_root.mkdir()
            build_project_fixture(project_root)

            target = project_root / "AGENTS.md"
            target.write_text("# OLD\n", encoding="utf-8")
            draft = Path(tmpdir) / "draft.md"
            draft.write_text(build_valid_draft(), encoding="utf-8")

            completed = run_cli(
                "--scope",
                "project",
                "--project-root",
                str(project_root),
                "--draft-file",
                str(draft),
                "--force",
                "--no-print-prompt",
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), build_valid_draft())

            backups = list(project_root.glob("AGENTS.md.bak.*"))
            self.assertEqual(len(backups), 1)
            self.assertIn("[ROLLBACK]", completed.stdout)

            gitignore = project_root / ".gitignore"
            self.assertTrue(gitignore.exists())
            lines = gitignore.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines.count("AGENTS.md"), 1)

    def test_missing_facts_requires_pending_section(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "repo"
            project_root.mkdir()
            build_project_fixture(project_root, include_readme=False, include_skills_index=False)

            draft = Path(tmpdir) / "draft.md"
            draft.write_text(build_valid_draft(include_pending=False), encoding="utf-8")

            completed = run_cli(
                "--scope",
                "project",
                "--project-root",
                str(project_root),
                "--draft-file",
                str(draft),
                "--dry-run",
                "--no-print-prompt",
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("待确认项", completed.stdout)

    def test_current_repo_prompt_contains_core_facts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt_output = Path(tmpdir) / "repo-prompt.md"

            completed = run_cli(
                "--scope",
                "project",
                "--project-root",
                str(REPO_ROOT),
                "--prompt-output",
                str(prompt_output),
                "--no-print-prompt",
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            text = prompt_output.read_text(encoding="utf-8")
            for skill_name in ("bug-fix-loop", "data-generator", "dev2release", "xlsx2json"):
                self.assertIn(skill_name, text)
            self.assertIn("python3 -m unittest discover -s tests -p", text)
            self.assertIn("test_*.py", text)


if __name__ == "__main__":
    unittest.main()
