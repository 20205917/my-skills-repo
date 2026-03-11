#!/usr/bin/env python3
"""Generate release notes for Conventional Commits and optionally update CHANGELOG."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

RECORD_SEP = "\x1e"
FIELD_SEP = "\x1f"

CONVENTIONAL_RE = re.compile(
    r"^(?P<type>[a-zA-Z]+)(\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s+(?P<description>.+)$"
)
BREAKING_RE = re.compile(r"(^|\n)BREAKING CHANGE:\s+", re.IGNORECASE)

TYPE_TO_SECTION = {
    "feat": "features",
    "fix": "fixes",
    "docs": "documentation",
    "refactor": "refactoring",
    "perf": "performance",
    "chore": "chores",
}

SECTION_ORDER = [
    ("breaking", "Breaking Changes"),
    ("features", "Features"),
    ("fixes", "Fixes"),
    ("documentation", "Documentation"),
    ("refactoring", "Refactoring"),
    ("performance", "Performance"),
    ("chores", "Chores"),
    ("others", "Other Changes"),
]


@dataclass(frozen=True)
class CommitEntry:
    sha: str
    subject: str
    body: str
    commit_type: str
    scope: str | None
    description: str
    breaking: bool


def run_git(args: Sequence[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout


def detect_last_tag(to_ref: str) -> str | None:
    try:
        tag = run_git(["describe", "--tags", "--abbrev=0", to_ref]).strip()
    except subprocess.CalledProcessError:
        return None
    return tag or None


def parse_conventional_subject(subject: str) -> tuple[str, str | None, bool, str]:
    match = CONVENTIONAL_RE.match(subject.strip())
    if not match:
        return "other", None, False, subject.strip()

    commit_type = match.group("type").lower()
    scope = match.group("scope")
    breaking = bool(match.group("breaking"))
    description = match.group("description").strip()
    return commit_type, scope, breaking, description


def build_commit_entry(sha: str, subject: str, body: str) -> CommitEntry:
    commit_type, scope, subject_breaking, description = parse_conventional_subject(subject)
    body_breaking = bool(BREAKING_RE.search(body or ""))
    return CommitEntry(
        sha=sha,
        subject=subject.strip(),
        body=(body or "").strip(),
        commit_type=commit_type,
        scope=scope,
        description=description,
        breaking=subject_breaking or body_breaking,
    )


def parse_git_log(raw_output: str) -> list[CommitEntry]:
    commits: list[CommitEntry] = []
    for chunk in raw_output.split(RECORD_SEP):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        parts = chunk.split(FIELD_SEP)
        if len(parts) < 3:
            continue
        sha = parts[0].strip()
        subject = parts[1].strip()
        body = FIELD_SEP.join(parts[2:]).strip()
        commits.append(build_commit_entry(sha, subject, body))
    return commits


def collect_commits(from_ref: str | None, to_ref: str) -> list[CommitEntry]:
    range_expr = f"{from_ref}..{to_ref}" if from_ref else to_ref
    output = run_git(
        ["log", range_expr, f"--format=%H{FIELD_SEP}%s{FIELD_SEP}%b{RECORD_SEP}"]
    )
    return parse_git_log(output)


def section_for_commit(commit: CommitEntry) -> str:
    if commit.breaking:
        return "breaking"
    return TYPE_TO_SECTION.get(commit.commit_type, "others")


def infer_bump(commits: Iterable[CommitEntry]) -> str:
    commit_list = list(commits)
    if any(commit.breaking for commit in commit_list):
        return "major"
    if any(commit.commit_type == "feat" for commit in commit_list):
        return "minor"
    return "patch"


def render_release_notes(version: str, release_date: str, commits: Iterable[CommitEntry]) -> str:
    grouped: dict[str, list[CommitEntry]] = {key: [] for key, _ in SECTION_ORDER}
    for commit in commits:
        grouped[section_for_commit(commit)].append(commit)

    lines = [f"## [{version}] - {release_date}", ""]
    has_section = False

    for key, title in SECTION_ORDER:
        entries = grouped[key]
        if not entries:
            continue
        has_section = True
        lines.append(f"### {title}")
        for commit in entries:
            prefix = f"**{commit.scope}:** " if commit.scope else ""
            lines.append(f"- {prefix}{commit.description} ({commit.sha[:7]})")
        lines.append("")

    if not has_section:
        lines.extend(["### Other Changes", "- No user-visible changes.", ""])

    return "\n".join(lines).rstrip() + "\n"


def merge_changelog(existing: str, entry: str) -> tuple[str, bool]:
    heading = entry.splitlines()[0].strip() if entry.strip() else ""
    if heading and heading in existing:
        return existing, False

    clean_entry = entry.rstrip() + "\n"

    if not existing.strip():
        return f"# Changelog\n\n{clean_entry}", True

    if existing.startswith("# Changelog"):
        lines = existing.splitlines()
        header = lines[0]
        rest = "\n".join(lines[1:]).lstrip("\n")
        merged = f"{header}\n\n{clean_entry}"
        if rest:
            merged += f"\n{rest.rstrip()}\n"
        return merged, True

    merged = f"# Changelog\n\n{clean_entry}\n{existing.lstrip()}"
    if not merged.endswith("\n"):
        merged += "\n"
    return merged, True


def write_changelog(path: Path, entry: str) -> bool:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    merged, inserted = merge_changelog(existing, entry)
    if inserted:
        path.write_text(merged, encoding="utf-8")
    return inserted


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Conventional Commit changelog entries."
    )
    parser.add_argument("--from-ref", help="Start ref (tag or sha). Defaults to latest tag.")
    parser.add_argument("--to-ref", default="HEAD", help="End ref. Defaults to HEAD.")
    parser.add_argument("--version", help="Release version, e.g. 1.2.3")
    parser.add_argument(
        "--date",
        default=dt.date.today().isoformat(),
        help="Release date in YYYY-MM-DD. Defaults to today.",
    )
    parser.add_argument(
        "--changelog",
        default="CHANGELOG.md",
        help="Path to changelog file. Defaults to CHANGELOG.md.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write entry into changelog file instead of printing to stdout.",
    )
    parser.add_argument(
        "--infer-bump",
        action="store_true",
        help="Infer version bump (major|minor|patch).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    from_ref = args.from_ref or detect_last_tag(args.to_ref)

    try:
        commits = collect_commits(from_ref, args.to_ref)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr or str(exc))
        return 1

    bump = infer_bump(commits)

    if args.infer_bump and not args.version and not args.write:
        print(bump)
        return 0

    if not args.version:
        sys.stderr.write("--version is required unless only --infer-bump is used.\n")
        return 2

    notes = render_release_notes(args.version, args.date, commits)

    if args.write:
        inserted = write_changelog(Path(args.changelog), notes)
        if inserted:
            print(f"Updated {args.changelog}")
        else:
            print(f"No change: {args.changelog} already contains version {args.version}")
    else:
        print(notes, end="")

    if args.infer_bump:
        sys.stderr.write(f"Inferred bump: {bump}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
