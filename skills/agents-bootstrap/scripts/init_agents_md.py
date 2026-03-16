#!/usr/bin/env python3
"""初始化全局级 AGENTS.md，并为项目级提供提示词驱动生成流程。"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
TEMPLATE_DIR = SKILL_ROOT / "assets" / "templates"
PROMPT_TEMPLATE_DIR = SKILL_ROOT / "assets" / "prompts"


STYLE_RULES = [
    "默认使用中文。",
    "文风执行导向，优先给出可直接执行的命令与路径。",
    "规则应可验证，避免抽象口号。",
]

PRESERVE_RULES = [
    "优先保留现有 AGENTS.md 中可执行且仍有效的事实信息（命令、路径、约定）。",
    "不得丢失技能名与入口路径。",
    "不得将可确认信息替换为 TODO 或泛化占位。",
]

PLACEHOLDER_PATTERNS = ("TODO:", "TODO：", "请补充", "待补充")
REQUIRED_HEADINGS = (
    "# AGENTS 开发指南",
    "## 当前技能与位置",
    "## 开发者快速命令",
    "## 测试",
    "## 目录结构",
    "## 维护约定",
)


@dataclass(frozen=True)
class Target:
    scope: str
    path: Path


@dataclass
class ValidationResult:
    errors: List[str]
    warnings: List[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="初始化全局级/项目级 AGENTS.md")
    parser.add_argument(
        "--scope",
        choices=("global", "project", "both"),
        default="project",
        help="生成范围：global/project/both",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="项目根目录（默认当前目录）",
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=Path("~/.codex"),
        help="Codex HOME 目录（默认 ~/.codex）",
    )
    parser.add_argument(
        "--style",
        choices=("concise",),
        default="concise",
        help="模板风格（当前仅支持 concise）",
    )
    parser.add_argument("--force", action="store_true", help="覆盖已存在文件")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入")
    parser.add_argument(
        "--draft-file",
        type=Path,
        help="模型生成的项目级 AGENTS 草稿文件（仅 project/both 生效）",
    )
    parser.add_argument(
        "--prompt-output",
        type=Path,
        help="将 Prompt Contract 输出到指定文件（默认输出到终端）",
    )
    parser.add_argument(
        "--no-print-prompt",
        action="store_true",
        help="不在终端打印 Prompt Contract 正文",
    )
    parser.add_argument(
        "--preview-lines",
        type=int,
        default=80,
        help="预览草稿前 N 行（默认 80）",
    )
    parser.add_argument(
        "--diff-lines",
        type=int,
        default=140,
        help="预览 diff 的前 N 行（默认 140）",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="写入前不生成 AGENTS.md 备份（默认生成）",
    )
    return parser.parse_args()


def resolve_targets(scope: str, project_root: Path, codex_home: Path) -> List[Target]:
    targets: List[Target] = []
    if scope in {"global", "both"}:
        targets.append(Target(scope="global", path=codex_home / "AGENTS.md"))
    if scope in {"project", "both"}:
        targets.append(Target(scope="project", path=project_root / "AGENTS.md"))
    return targets


def load_template(template_dir: Path, scope: str, style: str) -> str:
    template_name = f"{scope}_{style}.md"
    template_path = template_dir / template_name
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    return template_path.read_text(encoding="utf-8")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_optional_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return read_text(path)
    except OSError:
        return ""


def excerpt(text: str, max_chars: int = 4000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[TRUNCATED]..."


def read_package_json(project_root: Path) -> Dict[str, Any]:
    package_json_path = project_root / "package.json"
    if not package_json_path.exists():
        return {}
    try:
        payload = json.loads(read_text(package_json_path))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def detect_package_manager(project_root: Path) -> str:
    if (project_root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (project_root / "yarn.lock").exists():
        return "yarn"
    return "npm"


def script_command(manager: str, script_name: str) -> str:
    if manager == "yarn":
        return f"yarn {script_name}"
    if manager == "pnpm":
        return f"pnpm run {script_name}"
    if script_name == "test":
        return "npm test"
    return f"npm run {script_name}"


def detect_test_command(project_root: Path, package_json: Dict[str, Any]) -> str:
    tests_dir = project_root / "tests"
    if tests_dir.exists() and list(tests_dir.glob("test_*.py")):
        if (project_root / "pytest.ini").exists():
            return "pytest -q"
        return 'python3 -m unittest discover -s tests -p "test_*.py" -v'

    scripts = package_json.get("scripts")
    manager = detect_package_manager(project_root)
    if isinstance(scripts, dict) and "test" in scripts:
        return script_command(manager, "test")

    if (project_root / "go.mod").exists():
        return "go test ./..."
    if (project_root / "pom.xml").exists():
        return "mvn test"
    if (project_root / "Cargo.toml").exists():
        return "cargo test"
    return ""


def parse_frontmatter(content: str) -> Dict[str, str]:
    content = content.strip()
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    raw = parts[1]
    result: Dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def parse_skills_index(skills_index_text: str) -> Dict[str, Dict[str, str]]:
    mapping: Dict[str, Dict[str, str]] = {}
    current_skill = ""
    for raw_line in skills_index_text.splitlines():
        line = raw_line.rstrip()
        skill_match = re.match(r"^-\s+`([^`]+)`", line)
        if skill_match:
            current_skill = skill_match.group(1).strip()
            mapping.setdefault(current_skill, {})
            continue
        if not current_skill:
            continue
        entry_match = re.search(r"入口：`([^`]+)`", line)
        if entry_match:
            mapping[current_skill]["entry"] = entry_match.group(1).strip()
            continue
        purpose_match = re.search(r"用途：(.+)$", line)
        if purpose_match:
            mapping[current_skill]["purpose"] = purpose_match.group(1).strip()
    return mapping


def collect_skill_facts(project_root: Path, skills_index_text: str) -> List[Dict[str, str]]:
    skills_root = project_root / "skills"
    index_map = parse_skills_index(skills_index_text)
    rows: List[Dict[str, str]] = []

    if not skills_root.exists():
        return rows

    for skill_dir in sorted(path for path in skills_root.iterdir() if path.is_dir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        raw = read_optional_text(skill_md)
        meta = parse_frontmatter(raw)
        skill_name = meta.get("name", skill_dir.name)
        display_name = skill_name.strip() if skill_name else skill_dir.name
        index_item = index_map.get(display_name, {})

        entry = index_item.get("entry")
        if not entry:
            entry = f"skills/{skill_dir.name}/SKILL.md"

        purpose = meta.get("description") or index_item.get("purpose", "")
        rows.append(
            {
                "name": display_name,
                "path": f"skills/{skill_dir.name}/",
                "entry": entry,
                "purpose": purpose,
            }
        )

    return rows


def collect_shell_blocks(text: str) -> List[str]:
    blocks = re.findall(r"```bash\n(.*?)```", text, flags=re.DOTALL)
    commands: List[str] = []
    for block in blocks:
        cmd = block.strip()
        if cmd:
            commands.append(cmd)
    return commands


def collect_project_facts(project_root: Path) -> Dict[str, Any]:
    existing_agents = read_optional_text(project_root / "AGENTS.md")
    readme_text = read_optional_text(project_root / "README.md")
    skills_index_text = read_optional_text(project_root / "skills-index.md")

    package_json = read_package_json(project_root)
    test_command = detect_test_command(project_root, package_json)
    skills = collect_skill_facts(project_root, skills_index_text)

    missing_items: List[str] = []
    if not readme_text:
        missing_items.append("README.md 缺失或不可读")
    if not skills_index_text:
        missing_items.append("skills-index.md 缺失或不可读")
    if not skills:
        missing_items.append("未发现 skills/*/SKILL.md 可用技能定义")
    if not test_command:
        missing_items.append("未能自动识别测试命令")

    skill_files: Dict[str, str] = {}
    for skill in skills:
        skill_md = project_root / skill["path"] / "SKILL.md"
        skill_files[skill["path"] + "SKILL.md"] = excerpt(read_optional_text(skill_md), 1800)

    project_facts: Dict[str, Any] = {
        "project_name": project_root.name,
        "project_root": str(project_root),
        "skill_count": len(skills),
        "skills": skills,
        "test_command": test_command,
        "quick_commands_from_existing_agents": collect_shell_blocks(existing_agents),
        "source_snapshots": {
            "AGENTS.md": excerpt(existing_agents),
            "README.md": excerpt(readme_text),
            "skills-index.md": excerpt(skills_index_text),
        },
        "skill_snapshots": skill_files,
        "missing_items": missing_items,
    }
    return project_facts


def format_bullet_lines(items: List[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def render_project_prompt(style: str, project_facts: Dict[str, Any]) -> str:
    template = load_template(PROMPT_TEMPLATE_DIR, scope="project_prompt_contract", style=style)
    payload = template
    payload = payload.replace(
        "{{PROJECT_FACTS}}",
        "```json\n" + json.dumps(project_facts, ensure_ascii=False, indent=2) + "\n```",
    )
    payload = payload.replace("{{STYLE_RULES}}", format_bullet_lines(STYLE_RULES))
    payload = payload.replace("{{PRESERVE_RULES}}", format_bullet_lines(PRESERVE_RULES))
    if not payload.endswith("\n"):
        payload += "\n"
    return payload


def ensure_writable(path: Path, force: bool, dry_run: bool) -> Tuple[bool, str]:
    if path.exists() and not force and not dry_run:
        return False, f"Target already exists: {path}. Use --force to overwrite."
    return True, ""


def write_text_target(path: Path, content: str, dry_run: bool, label: str) -> None:
    if dry_run:
        mode = "existing" if path.exists() else "new"
        print(f"[DRY-RUN] {label}: {path} ({len(content.encode('utf-8'))} bytes, {mode})")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"[WRITE] {label}: {path}")


def update_project_gitignore(project_root: Path, dry_run: bool) -> str:
    gitignore_path = project_root / ".gitignore"
    entry = "AGENTS.md"

    if gitignore_path.exists():
        content = read_text(gitignore_path)
        lines = content.splitlines()
    else:
        content = ""
        lines = []

    if any(line.strip() == entry for line in lines):
        print(f"[SKIP] gitignore: {gitignore_path} already contains {entry}")
        return "skipped"

    if dry_run:
        print(f"[DRY-RUN] gitignore: {gitignore_path} add {entry}")
        return "dry-run"

    if content and not content.endswith("\n"):
        content += "\n"
    content += f"{entry}\n"
    gitignore_path.write_text(content, encoding="utf-8")
    print(f"[WRITE] gitignore: {gitignore_path} add {entry}")
    return "written"


def build_diff_summary(old_text: str, new_text: str, max_lines: int) -> Tuple[int, int, str]:
    diff_lines = list(
        difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile="existing/AGENTS.md",
            tofile="draft/AGENTS.md",
            lineterm="",
        )
    )
    plus = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    minus = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
    snippet = "\n".join(diff_lines[:max_lines])
    return plus, minus, snippet


def validate_project_draft(draft: str, facts: Dict[str, Any]) -> ValidationResult:
    errors: List[str] = []
    warnings: List[str] = []

    for token in PLACEHOLDER_PATTERNS:
        if token in draft:
            errors.append(f"草稿包含占位词：{token}")

    for heading in REQUIRED_HEADINGS:
        if heading not in draft:
            errors.append(f"缺少必需章节：{heading}")

    for skill in facts.get("skills", []):
        name = skill.get("name", "").strip()
        entry = skill.get("entry", "").strip()
        if name and name not in draft:
            errors.append(f"缺少技能名：{name}")
        if entry and entry not in draft:
            errors.append(f"缺少技能入口路径：{entry}")

    test_command = str(facts.get("test_command", "")).strip()
    if test_command and test_command not in draft:
        errors.append(f"缺少测试命令：{test_command}")

    missing_items = list(facts.get("missing_items", []))
    if missing_items and "## 待确认项" not in draft:
        errors.append("事实信息不完整时，草稿必须包含“## 待确认项”章节")
    if not missing_items and "## 待确认项" in draft:
        warnings.append("当前事实已完整，草稿仍包含“待确认项”，建议删除")

    return ValidationResult(errors=errors, warnings=warnings)


def print_followups() -> None:
    print("\n验证加载优先级建议：")
    print("1. 重启或新开 Codex 会话进入项目目录。")
    print("2. 询问 Codex：请列出当前加载的 AGENTS 指令来源与优先级。")
    print("3. 确认项目级规则在该项目内覆盖全局默认规则。")
    print("\n可选 config.toml 片段（手动添加，不会自动改写）：")
    print('project_doc_fallback_filenames = ["AGENTS.md", "README.dev.md"]')


def handle_global(target: Target, args: argparse.Namespace) -> int:
    content = load_template(TEMPLATE_DIR, scope="global", style=args.style)
    ok, message = ensure_writable(target.path, force=args.force, dry_run=args.dry_run)
    if not ok:
        print(message, file=sys.stderr)
        return 1
    write_text_target(target.path, content, dry_run=args.dry_run, label="global")
    return 0


def handle_project(target: Target, args: argparse.Namespace, project_root: Path) -> int:
    facts = collect_project_facts(project_root)
    prompt = render_project_prompt(args.style, facts)

    if args.prompt_output:
        ok, message = ensure_writable(args.prompt_output, force=args.force, dry_run=args.dry_run)
        if not ok:
            print(message, file=sys.stderr)
            return 1
        write_text_target(args.prompt_output, prompt, dry_run=args.dry_run, label="prompt")

    if not args.no_print_prompt:
        print("[PROMPT] project_prompt_contract:")
        print(prompt)

    if not args.draft_file:
        print("[INFO] 未提供 --draft-file，项目级 AGENTS 不会自动写入。")
        print("[INFO] 建议：先将 Prompt Contract 提交给模型生成草稿，再用 --draft-file 预览和写入。")
        return 0

    draft_path = args.draft_file.expanduser().resolve()
    if not draft_path.exists():
        print(f"Draft file not found: {draft_path}", file=sys.stderr)
        return 1

    draft = read_text(draft_path)
    existing = read_optional_text(target.path)

    validation = validate_project_draft(draft, facts)
    for warning in validation.warnings:
        print(f"[WARN] {warning}")
    if validation.errors:
        print("[ERROR] 草稿未通过质量门槛：")
        for err in validation.errors:
            print(f"- {err}")
        return 1

    preview = "\n".join(draft.splitlines()[: max(args.preview_lines, 1)])
    print(f"[PREVIEW] draft: {draft_path} (first {max(args.preview_lines, 1)} lines)")
    print(preview)

    plus, minus, diff_snippet = build_diff_summary(existing, draft, max(args.diff_lines, 1))
    print(f"[DIFF] +{plus} / -{minus}")
    if diff_snippet:
        print(diff_snippet)

    if args.dry_run:
        print(f"[DRY-RUN] project: {target.path} (validated, not written)")
        update_project_gitignore(project_root=project_root, dry_run=True)
        return 0

    ok, message = ensure_writable(target.path, force=args.force, dry_run=args.dry_run)
    if not ok:
        print(message, file=sys.stderr)
        return 1

    backup_path = ""
    if target.path.exists() and not args.no_backup:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = target.path.with_name(f"AGENTS.md.bak.{ts}")
        shutil.copy2(target.path, backup)
        backup_path = str(backup)
        print(f"[BACKUP] project: {backup}")

    write_text_target(target.path, draft, dry_run=False, label="project")
    update_project_gitignore(project_root=project_root, dry_run=False)

    if backup_path:
        print(f"[ROLLBACK] 可使用备份文件回滚：{backup_path}")
    return 0


def main() -> int:
    args = parse_args()

    project_root = args.project_root.expanduser().resolve()
    codex_home = args.codex_home.expanduser().resolve()

    if not project_root.exists() or not project_root.is_dir():
        print(f"Invalid project root: {project_root}", file=sys.stderr)
        return 1

    targets = resolve_targets(args.scope, project_root=project_root, codex_home=codex_home)
    status = 0

    for target in targets:
        if target.scope == "global":
            status = max(status, handle_global(target, args))
        elif target.scope == "project":
            status = max(status, handle_project(target, args, project_root))

    print_followups()
    return status


if __name__ == "__main__":
    raise SystemExit(main())
