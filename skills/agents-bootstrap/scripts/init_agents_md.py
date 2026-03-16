#!/usr/bin/env python3
"""初始化全局级/项目级 AGENTS.md。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
TEMPLATE_DIR = SKILL_ROOT / "assets" / "templates"


@dataclass(frozen=True)
class Target:
    scope: str
    path: Path


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
    return parser.parse_args()


def resolve_targets(scope: str, project_root: Path, codex_home: Path) -> List[Target]:
    targets: List[Target] = []
    if scope in {"global", "both"}:
        targets.append(Target(scope="global", path=codex_home / "AGENTS.md"))
    if scope in {"project", "both"}:
        targets.append(Target(scope="project", path=project_root / "AGENTS.md"))
    return targets


def read_package_json(project_root: Path) -> Dict[str, Any]:
    package_json_path = project_root / "package.json"
    if not package_json_path.exists():
        return {}
    try:
        raw = package_json_path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def detect_package_manager(project_root: Path) -> str:
    if (project_root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (project_root / "yarn.lock").exists():
        return "yarn"
    return "npm"


def collect_dependencies(package_json: Dict[str, Any]) -> Dict[str, str]:
    deps: Dict[str, str] = {}
    for field in ("dependencies", "devDependencies", "peerDependencies"):
        section = package_json.get(field)
        if isinstance(section, dict):
            for key, value in section.items():
                if isinstance(key, str) and isinstance(value, str):
                    deps[key] = value
    return deps


def detect_project_type(project_root: Path, package_json: Dict[str, Any]) -> str:
    deps = collect_dependencies(package_json)
    if package_json:
        if "next" in deps:
            return "Web 全栈项目（Next.js）"
        if "react" in deps:
            return "Web 前端项目（React）"
        if "vue" in deps:
            return "Web 前端项目（Vue）"
        if "nestjs" in deps:
            return "Node 服务项目（NestJS）"
        return "Node 项目"
    if (project_root / "go.mod").exists():
        return "Go 项目"
    if (project_root / "pom.xml").exists():
        return "Java 项目"
    if (project_root / "Cargo.toml").exists():
        return "Rust 项目"
    if (project_root / "pyproject.toml").exists() or (project_root / "requirements.txt").exists():
        return "Python 项目"
    return "TODO: 请补充项目类型"


def detect_tech_stack(project_root: Path, package_json: Dict[str, Any]) -> str:
    stacks: List[str] = []
    deps = collect_dependencies(package_json)

    if package_json:
        manager = detect_package_manager(project_root)
        stacks.append(f"Node.js（{manager}）")
        if "react" in deps:
            stacks.append("React")
        if "vue" in deps:
            stacks.append("Vue")
        if "next" in deps:
            stacks.append("Next.js")
        if "typescript" in deps or (project_root / "tsconfig.json").exists():
            stacks.append("TypeScript")

    if (project_root / "pyproject.toml").exists() or (project_root / "requirements.txt").exists():
        stacks.append("Python")
    if (project_root / "go.mod").exists():
        stacks.append("Go")
    if (project_root / "pom.xml").exists():
        stacks.append("Java")
    if (project_root / "Cargo.toml").exists():
        stacks.append("Rust")

    unique_stacks = list(dict.fromkeys(stacks))
    if unique_stacks:
        return " + ".join(unique_stacks)
    return "TODO: 请补充核心技术栈"


def detect_project_purpose(project_root: Path) -> str:
    readme_path = project_root / "README.md"
    if readme_path.exists():
        for line in readme_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                title = stripped.lstrip("#").strip()
                if title:
                    return f"TODO: 请补充项目用途（当前仓库标题：{title}）"
                break
    return "TODO: 请补充项目用途、目标用户与业务边界"


def detect_core_constraints(project_root: Path, package_json: Dict[str, Any]) -> str:
    deps = collect_dependencies(package_json)
    constraints: List[str] = []
    if (project_root / "tsconfig.json").exists() or "typescript" in deps:
        constraints.append("- 保持 TypeScript 类型约束，避免滥用 `any`。")
    if (project_root / ".eslintrc").exists() or (project_root / ".eslintrc.js").exists() or "eslint" in deps:
        constraints.append("- 变更需通过项目既有 Lint 规则。")
    constraints.append("- TODO: 补充鉴权、权限或数据边界约束。")
    constraints.append("- TODO: 补充敏感信息与配置管理约束。")
    return "\n".join(constraints)


def script_command(manager: str, script_name: str) -> str:
    if manager == "yarn":
        return f"yarn {script_name}"
    if manager == "pnpm":
        return f"pnpm run {script_name}"
    if script_name == "test":
        return "npm test"
    return f"npm run {script_name}"


def detect_test_framework(project_root: Path, package_json: Dict[str, Any]) -> str:
    deps = collect_dependencies(package_json)
    if (project_root / "pytest.ini").exists():
        return "pytest"
    if (project_root / "tests").exists() and list((project_root / "tests").glob("test_*.py")):
        return "unittest"
    if "vitest" in deps:
        return "vitest"
    if "jest" in deps:
        return "jest"
    if "cypress" in deps:
        return "cypress"
    if (project_root / "go.mod").exists():
        return "go test"
    if (project_root / "pom.xml").exists():
        return "maven surefire"
    if (project_root / "Cargo.toml").exists():
        return "cargo test"
    return "TODO: 请补充测试框架"


def detect_test_command(project_root: Path, package_json: Dict[str, Any]) -> str:
    tests_dir = project_root / "tests"
    scripts = package_json.get("scripts")
    manager = detect_package_manager(project_root)

    if tests_dir.exists() and list(tests_dir.glob("test_*.py")):
        if (project_root / "pytest.ini").exists():
            return "pytest -q"
        return 'python3 -m unittest discover -s tests -p "test_*.py" -v'
    if (project_root / "pytest.ini").exists() or (project_root / "pyproject.toml").exists():
        return "pytest -q"
    if isinstance(scripts, dict) and "test" in scripts:
        return script_command(manager, "test")
    if (project_root / "go.mod").exists():
        return "go test ./..."
    if (project_root / "pom.xml").exists():
        return "mvn test"
    if (project_root / "Cargo.toml").exists():
        return "cargo test"
    return "TODO: 请补充测试执行命令"


def detect_dev_workflow(project_root: Path, package_json: Dict[str, Any], test_command: str) -> str:
    workflow: List[str] = []
    scripts = package_json.get("scripts")
    manager = detect_package_manager(project_root)

    if package_json:
        install_cmd = {"pnpm": "pnpm install", "yarn": "yarn install", "npm": "npm install"}[manager]
        workflow.append(f"- 安装依赖：`{install_cmd}`")
        if isinstance(scripts, dict) and "dev" in scripts:
            workflow.append(f"- 本地开发：`{script_command(manager, 'dev')}`")
        if isinstance(scripts, dict) and "build" in scripts:
            workflow.append(f"- 构建产物：`{script_command(manager, 'build')}`")
        if isinstance(scripts, dict) and "start" in scripts:
            workflow.append(f"- 启动服务：`{script_command(manager, 'start')}`")

    if (project_root / "pyproject.toml").exists() or (project_root / "requirements.txt").exists():
        workflow.append("- Python 环境：`python3 -m venv .venv && source .venv/bin/activate`")
        if (project_root / "requirements.txt").exists():
            workflow.append("- 安装依赖：`pip install -r requirements.txt`")
    if (project_root / "go.mod").exists():
        workflow.append("- Go 依赖整理：`go mod tidy`")
    if (project_root / "pom.xml").exists():
        workflow.append("- Maven 构建：`mvn -DskipTests package`")
    if (project_root / "Cargo.toml").exists():
        workflow.append("- Rust 构建：`cargo build`")

    if not workflow:
        workflow.append("- TODO: 请补充环境搭建命令。")
        workflow.append("- TODO: 请补充本地开发与构建流程命令。")

    if not test_command.startswith("TODO"):
        workflow.append(f"- 验证测试：`{test_command}`")
    return "\n".join(dict.fromkeys(workflow))


def detect_test_spec(project_root: Path, package_json: Dict[str, Any]) -> str:
    framework = detect_test_framework(project_root, package_json)
    test_command = detect_test_command(project_root, package_json)
    lines = [f"- 测试框架：{framework}"]
    if test_command.startswith("TODO"):
        lines.append(f"- 执行命令：{test_command}")
    else:
        lines.append(f"- 执行命令：`{test_command}`")
    lines.append("- 验收标准：核心路径通过；新增或变更核心逻辑补测试；无法执行测试需说明原因。")
    return "\n".join(lines)


def detect_must_rules(project_root: Path, package_json: Dict[str, Any]) -> str:
    deps = collect_dependencies(package_json)
    rules: List[str] = [
        "- 改动前明确需求边界、影响范围和验收标准。",
        "- 变更保持最小闭环，优先复用现有实现，避免无关重构。",
        "- 改动后执行与风险相称的验证；无法执行测试需明确说明原因。",
        "- 涉及核心脚本或核心逻辑时，补充相应测试。",
    ]
    if (project_root / "tsconfig.json").exists() or "typescript" in deps:
        rules.append("- TypeScript 代码保持类型收敛，避免引入不必要的 `any`。")
    if (project_root / ".eslintrc").exists() or (project_root / ".eslintrc.js").exists() or "eslint" in deps:
        rules.append("- 提交前确保 Lint 规则通过。")
    if (project_root / "pyproject.toml").exists() or (project_root / "ruff.toml").exists():
        rules.append("- Python 代码遵循项目既有格式化与静态检查规则。")
    rules.append("- 提交前检查 `git status`，只提交目标文件。")
    rules.append("- 一个问题一个 commit，提交说明保持可追溯。")
    return "\n".join(rules)


def detect_ask_first_rules() -> str:
    rules = [
        "- 涉及数据库迁移、生产数据改写、外部系统写入前先询问。",
        "- 涉及公共接口调整、目录结构重组、批量重命名前先询问。",
        "- 需要覆盖已有 `AGENTS.md`、批量修改大量文件或长时间任务前先询问。",
        "- 需要引入新依赖或改变构建/测试主流程前先询问。",
    ]
    return "\n".join(rules)


def detect_forbidden_rules() -> str:
    rules = [
        "- 禁止未获明确授权执行破坏性命令（如 `git reset --hard`、`git checkout --`）。",
        "- 禁止提交密钥、令牌、证书或其他敏感信息。",
        "- 禁止在未验证的情况下声称“已通过测试”或“已完成发布”。",
        "- 禁止为掩盖问题而绕过核心校验、删除测试或跳过必需检查。",
    ]
    return "\n".join(rules)


def load_template(scope: str, style: str) -> str:
    template_name = f"{scope}_{style}.md"
    template_path = TEMPLATE_DIR / template_name
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    return template_path.read_text(encoding="utf-8")


def render_content(scope: str, style: str, context: Dict[str, str]) -> str:
    text = load_template(scope=scope, style=style)
    for key, value in context.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    if not text.endswith("\n"):
        text += "\n"
    return text


def ensure_writable(targets: List[Target], force: bool, dry_run: bool) -> Tuple[bool, str]:
    for target in targets:
        if target.path.exists() and not force and not dry_run:
            return False, f"Target already exists: {target.path}. Use --force to overwrite."
    return True, ""


def write_target(target: Target, content: str, dry_run: bool) -> None:
    if dry_run:
        mode = "existing" if target.path.exists() else "new"
        print(f"[DRY-RUN] {target.scope}: {target.path} ({len(content.encode('utf-8'))} bytes, {mode})")
        return
    target.path.parent.mkdir(parents=True, exist_ok=True)
    target.path.write_text(content, encoding="utf-8")
    print(f"[WRITE] {target.scope}: {target.path}")


def update_project_gitignore(project_root: Path, dry_run: bool) -> None:
    gitignore_path = project_root / ".gitignore"
    entry = "AGENTS.md"

    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
        lines = content.splitlines()
    else:
        content = ""
        lines = []

    if any(line.strip() == entry for line in lines):
        print(f"[SKIP] gitignore: {gitignore_path} already contains {entry}")
        return

    if dry_run:
        print(f"[DRY-RUN] gitignore: {gitignore_path} add {entry}")
        return

    if content and not content.endswith("\n"):
        content += "\n"
    content += f"{entry}\n"
    gitignore_path.write_text(content, encoding="utf-8")
    print(f"[WRITE] gitignore: {gitignore_path} add {entry}")


def print_followups() -> None:
    print("\n验证加载优先级建议：")
    print("1. 重启或新开 Codex 会话进入项目目录。")
    print("2. 询问 Codex：请列出当前加载的 AGENTS 指令来源与优先级。")
    print("3. 确认项目级规则在该项目内覆盖全局默认规则。")
    print("\n可选 config.toml 片段（手动添加，不会自动改写）：")
    print('project_doc_fallback_filenames = ["AGENTS.md", "README.dev.md"]')


def main() -> int:
    args = parse_args()

    project_root = args.project_root.expanduser().resolve()
    codex_home = args.codex_home.expanduser().resolve()

    if not project_root.exists() or not project_root.is_dir():
        print(f"Invalid project root: {project_root}", file=sys.stderr)
        return 1

    package_json = read_package_json(project_root)
    test_command = detect_test_command(project_root, package_json)
    context = {
        "PROJECT_NAME": project_root.name,
        "PROJECT_TYPE": detect_project_type(project_root, package_json),
        "TECH_STACK": detect_tech_stack(project_root, package_json),
        "PROJECT_PURPOSE": detect_project_purpose(project_root),
        "CORE_CONSTRAINTS": detect_core_constraints(project_root, package_json),
        "DEV_WORKFLOW": detect_dev_workflow(project_root, package_json, test_command),
        "TEST_SPEC": detect_test_spec(project_root, package_json),
        "MUST_RULES": detect_must_rules(project_root, package_json),
        "ASK_FIRST_RULES": detect_ask_first_rules(),
        "FORBIDDEN_RULES": detect_forbidden_rules(),
    }

    targets = resolve_targets(scope=args.scope, project_root=project_root, codex_home=codex_home)
    ok, message = ensure_writable(targets=targets, force=args.force, dry_run=args.dry_run)
    if not ok:
        print(message, file=sys.stderr)
        return 1

    for target in targets:
        content = render_content(scope=target.scope, style=args.style, context=context)
        write_target(target=target, content=content, dry_run=args.dry_run)

    if any(target.scope == "project" for target in targets):
        update_project_gitignore(project_root=project_root, dry_run=args.dry_run)

    print_followups()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
