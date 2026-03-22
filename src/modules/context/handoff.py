"""Session handoff: generates HANDOFF.md summarizing session state for continuity."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


class HandoffError(Exception):
    """Raised when the handoff process encounters an unrecoverable error."""


@dataclass(frozen=True)
class HandoffResult:
    output_path: Path
    sections: dict[str, str]
    compaction_count: int


@dataclass
class SessionTracker:
    compaction_count: int = 0
    session_start_ref: str = "HEAD"

    def record_compaction(self) -> None:
        self.compaction_count += 1

    def should_force_handoff(self) -> bool:
        return self.compaction_count >= 2


def _run_git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
    return result.stdout.strip()


def _build_completed_section(project_root: Path, tracker: SessionTracker) -> str:
    ref = tracker.session_start_ref
    changed = _run_git(["diff", "--name-only", f"{ref}..HEAD"], cwd=project_root)
    commits = _run_git(["log", "--oneline", f"{ref}..HEAD"], cwd=project_root)
    lines: list[str] = []
    if commits:
        lines.append("### Commits")
        lines.append(commits)
    if changed:
        lines.append("### Changed Files")
        lines.append(changed)
    return "\n".join(lines) if lines else "_No commits this session._"


def _build_in_progress_section(project_root: Path) -> str:
    unstaged = _run_git(["diff", "--name-only"], cwd=project_root)
    staged = _run_git(["diff", "--cached", "--name-only"], cwd=project_root)
    lines: list[str] = []
    if staged:
        lines.append("### Staged")
        lines.append(staged)
    if unstaged:
        lines.append("### Unstaged")
        lines.append(unstaged)
    return "\n".join(lines) if lines else "_No uncommitted changes._"


def _build_blocked_section(project_root: Path, tracker: SessionTracker) -> str:
    ref = tracker.session_start_ref
    diff_output = _run_git(["diff", f"{ref}..HEAD", "-U0"], cwd=project_root)
    pattern = re.compile(r"^\+.*(TODO|FIXME).*$", re.MULTILINE)
    matches = pattern.findall(diff_output)
    if not matches:
        return "_No TODO/FIXME items found._"
    todo_lines = [m for m in re.findall(r"^\+(.*(TODO|FIXME).*)$", diff_output, re.MULTILINE)]
    items = [line[0].strip() for line in todo_lines]
    return "\n".join(f"- {item}" for item in items)


def _build_starting_point_section(project_root: Path, tracker: SessionTracker) -> str:
    ref = tracker.session_start_ref
    changed = _run_git(["diff", "--name-only", f"{ref}..HEAD"], cwd=project_root)
    unstaged = _run_git(["diff", "--name-only"], cwd=project_root)
    recent_files = unstaged or changed
    if not recent_files:
        return "_No files modified — start wherever makes sense._"
    first_file = recent_files.splitlines()[0]
    return f"Resume work in `{first_file}`."


def _format_handoff_md(sections: dict[str, str], compaction_count: int) -> str:
    lines: list[str] = ["# Session Handoff", ""]
    for section_name, content in sections.items():
        lines.append(f"## {section_name}")
        lines.append("")
        lines.append(content)
        lines.append("")
    lines.append(f"_Compaction count: {compaction_count}_")
    lines.append("")
    return "\n".join(lines)


def generate_handoff(project_root: Path, tracker: SessionTracker) -> HandoffResult:
    """Generate a HANDOFF.md summarizing the current session state."""
    sections: dict[str, str] = {
        "Completed This Session": _build_completed_section(project_root, tracker),
        "In Progress": _build_in_progress_section(project_root),
        "Blocked": _build_blocked_section(project_root, tracker),
        "Recommended Starting Point": _build_starting_point_section(project_root, tracker),
    }

    content = _format_handoff_md(sections, tracker.compaction_count)
    output_path = project_root / "HANDOFF.md"
    output_path.write_text(content, encoding="utf-8")

    return HandoffResult(
        output_path=output_path,
        sections=sections,
        compaction_count=tracker.compaction_count,
    )
