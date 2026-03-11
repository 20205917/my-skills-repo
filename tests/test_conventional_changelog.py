import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO_ROOT / "skills" / "dev2release" / "scripts" / "conventional_changelog.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("conventional_changelog", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@contextmanager
def working_directory(path: Path):
    prev = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


def run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


class ConventionalChangelogTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_module()

    def test_commit_type_classification(self):
        cases = {
            "feat(ui): add dashboard": "features",
            "fix(api): handle timeout": "fixes",
            "docs: update readme": "documentation",
            "chore: bump deps": "chores",
            "refactor(core): simplify parser": "refactoring",
            "perf(db): improve query": "performance",
        }

        for subject, expected in cases.items():
            commit = self.mod.build_commit_entry("a" * 40, subject, "")
            self.assertEqual(self.mod.section_for_commit(commit), expected)

    def test_infer_bump_levels(self):
        major_commits = [
            self.mod.build_commit_entry("a" * 40, "feat!: remove v1 endpoint", ""),
        ]
        minor_commits = [
            self.mod.build_commit_entry("b" * 40, "feat: add search", ""),
            self.mod.build_commit_entry("c" * 40, "fix: patch bug", ""),
        ]
        patch_commits = [
            self.mod.build_commit_entry("d" * 40, "fix: patch bug", ""),
            self.mod.build_commit_entry("e" * 40, "chore: tidy", ""),
        ]

        self.assertEqual(self.mod.infer_bump(major_commits), "major")
        self.assertEqual(self.mod.infer_bump(minor_commits), "minor")
        self.assertEqual(self.mod.infer_bump(patch_commits), "patch")

    def test_breaking_change_detected_from_body(self):
        commit = self.mod.build_commit_entry(
            "f" * 40,
            "feat: add new auth flow",
            "BREAKING CHANGE: remove old auth token format",
        )
        self.assertTrue(commit.breaking)
        self.assertEqual(self.mod.section_for_commit(commit), "breaking")
        self.assertEqual(self.mod.infer_bump([commit]), "major")

    def test_render_release_notes_order_and_empty_sections(self):
        commits = [
            self.mod.build_commit_entry("1" * 40, "fix(api): retry request", ""),
            self.mod.build_commit_entry("2" * 40, "chore: update lockfile", ""),
        ]
        notes = self.mod.render_release_notes("1.2.3", "2026-03-11", commits)

        self.assertIn("## [1.2.3] - 2026-03-11", notes)
        self.assertIn("### Fixes", notes)
        self.assertIn("### Chores", notes)
        self.assertNotIn("### Features", notes)
        self.assertLess(notes.index("### Fixes"), notes.index("### Chores"))

    @unittest.skipUnless(shutil.which("git"), "git is required for smoke test")
    def test_smoke_collect_commits_from_temp_repo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            run(["git", "init"], cwd=repo)
            run(["git", "config", "user.name", "Test User"], cwd=repo)
            run(["git", "config", "user.email", "test@example.com"], cwd=repo)

            (repo / "README.md").write_text("hello\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: init repo"], cwd=repo)
            run(["git", "tag", "v0.1.0"], cwd=repo)

            (repo / "README.md").write_text("hello world\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "feat: add docs home"], cwd=repo)

            (repo / "README.md").write_text("hello world!\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "fix: typo in docs"], cwd=repo)

            with working_directory(repo):
                commits = self.mod.collect_commits("v0.1.0", "HEAD")

            self.assertEqual(len(commits), 2)
            self.assertEqual(self.mod.infer_bump(commits), "minor")
            notes = self.mod.render_release_notes("0.2.0", "2026-03-11", commits)
            self.assertIn("### Features", notes)
            self.assertIn("### Fixes", notes)


if __name__ == "__main__":
    unittest.main()
