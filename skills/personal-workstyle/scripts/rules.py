#!/usr/bin/env python3
import argparse
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "rules" / "active.md"
PENDING = ROOT / "rules" / "pending.md"
HISTORY = ROOT / "rules" / "history.md"


def read_lines(path: Path):
    return path.read_text(encoding="utf-8").splitlines()


def write_lines(path: Path, lines):
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def list_active():
    lines = read_lines(ACTIVE)
    for ln in lines:
        if ln.strip().startswith("- ["):
            print(ln)


def list_pending():
    lines = read_lines(PENDING)
    for ln in lines:
        if ln.strip().startswith("- ["):
            print(ln)


def next_pending_id(lines):
    max_id = 0
    for ln in lines:
        ln = ln.strip()
        if ln.startswith("- [P") and "]" in ln:
            token = ln.split("]", 1)[0].replace("- [P", "")
            if token.isdigit():
                max_id = max(max_id, int(token))
    return f"P{max_id + 1:03d}"


def add_pending(rule_text):
    lines = read_lines(PENDING)
    pid = next_pending_id(lines)
    lines.append(f"- [{pid}] {rule_text}")
    write_lines(PENDING, lines)
    append_history(f"{now()} ADD-PENDING {pid}: {rule_text}")
    print(f"已新增待确认规则 {pid}")


def find_line(lines, rid):
    prefix = f"- [{rid}]"
    for i, ln in enumerate(lines):
        if ln.strip().startswith(prefix):
            return i
    return -1


def next_active_id(lines):
    max_id = 0
    for ln in lines:
        ln = ln.strip()
        if ln.startswith("- [R") and "]" in ln:
            token = ln.split("]", 1)[0].replace("- [R", "")
            if token.isdigit():
                max_id = max(max_id, int(token))
    return f"R{max_id + 1:03d}"


def promote_pending(pid):
    pending = read_lines(PENDING)
    idx = find_line(pending, pid)
    if idx < 0:
        raise SystemExit(f"未找到待确认规则 {pid}")

    rule_text = pending[idx].split("]", 1)[1].strip()
    del pending[idx]
    write_lines(PENDING, pending)

    active = read_lines(ACTIVE)
    rid = next_active_id(active)
    active.append(f"- [{rid}] {rule_text}")
    write_lines(ACTIVE, active)

    append_history(f"{now()} PROMOTE {pid} -> {rid}: {rule_text}")
    print(f"已将 {pid} 转为生效规则 {rid}")


def remove_active(rid):
    active = read_lines(ACTIVE)
    idx = find_line(active, rid)
    if idx < 0:
        raise SystemExit(f"未找到生效规则 {rid}")

    removed = active[idx]
    del active[idx]
    write_lines(ACTIVE, active)
    append_history(f"{now()} REMOVE {rid}: {removed}")
    print(f"已删除规则 {rid}")


def append_history(event):
    history = read_lines(HISTORY)
    history.append(f"- {event}")
    write_lines(HISTORY, history)


def load_rules():
    print("已加载当前生效规则：")
    list_active()


def main():
    parser = argparse.ArgumentParser(description="管理 personal-workstyle 规则")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="罗列生效规则")
    sub.add_parser("pending", help="罗列待确认规则")

    add_p = sub.add_parser("add", help="新增待确认规则")
    add_p.add_argument("text", help="规则内容")

    promote_p = sub.add_parser("promote", help="将待确认规则转为生效规则")
    promote_p.add_argument("id", help="待确认规则 ID，例如 P001")

    remove_p = sub.add_parser("remove", help="删除生效规则")
    remove_p.add_argument("id", help="生效规则 ID，例如 R001")

    sub.add_parser("load", help="加载并显示当前生效规则")

    args = parser.parse_args()

    if args.cmd == "list":
        list_active()
    elif args.cmd == "pending":
        list_pending()
    elif args.cmd == "add":
        add_pending(args.text)
    elif args.cmd == "promote":
        promote_pending(args.id)
    elif args.cmd == "remove":
        remove_active(args.id)
    elif args.cmd == "load":
        load_rules()


if __name__ == "__main__":
    main()
