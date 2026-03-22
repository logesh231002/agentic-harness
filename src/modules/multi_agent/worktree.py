"""Git worktree manager: create, list, and cleanup worktrees for issue branches."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


class WorktreeError(Exception):
    """Raised when a git worktree operation fails."""


@dataclass(frozen=True)
class WorktreeInfo:
    path: Path
    issue_number: int
    branch: str
    last_commit_message: str


@dataclass(frozen=True)
class CreateResult:
    path: Path
    branch: str
    already_existed: bool


@dataclass(frozen=True)
class CleanupResult:
    removed: list[str]


_ISSUE_DIR_PATTERN = re.compile(r"^issue-(\d+)$")


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)


def create(project_root: Path, issue_number: int) -> CreateResult:
    """Create a worktree for the given issue number.

    Returns *CreateResult* with ``already_existed=True`` when the worktree
    directory or branch already exists.
    """
    worktree_dir = project_root / ".worktrees" / f"issue-{issue_number}"
    branch = f"issue-{issue_number}"

    if worktree_dir.exists():
        return CreateResult(path=worktree_dir, branch=branch, already_existed=True)

    result = _run_git(
        ["worktree", "add", str(worktree_dir), "-b", branch],
        cwd=project_root,
    )

    if result.returncode != 0:
        if worktree_dir.exists():
            return CreateResult(path=worktree_dir, branch=branch, already_existed=True)
        raise WorktreeError(result.stderr.strip() or result.stdout.strip())

    return CreateResult(path=worktree_dir, branch=branch, already_existed=False)


def list_worktrees(project_root: Path) -> list[WorktreeInfo]:
    """List issue worktrees by parsing ``git worktree list --porcelain``."""
    result = _run_git(["worktree", "list", "--porcelain"], cwd=project_root)
    if result.returncode != 0:
        return []

    worktrees: list[WorktreeInfo] = []
    blocks = result.stdout.strip().split("\n\n")

    for block in blocks:
        if not block.strip():
            continue

        wt_path: str | None = None
        wt_branch: str | None = None

        for line in block.splitlines():
            if line.startswith("worktree "):
                wt_path = line[len("worktree ") :]
            elif line.startswith("branch "):
                raw_branch = line[len("branch ") :]
                wt_branch = raw_branch.removeprefix("refs/heads/")

        if wt_path is None:
            continue

        dir_name = Path(wt_path).name
        match = _ISSUE_DIR_PATTERN.match(dir_name)
        if match is None:
            continue

        issue_number = int(match.group(1))

        log_result = _run_git(["log", "-1", "--format=%s"], cwd=Path(wt_path))
        last_commit_message = log_result.stdout.strip() if log_result.returncode == 0 else ""

        worktrees.append(
            WorktreeInfo(
                path=Path(wt_path),
                issue_number=issue_number,
                branch=wt_branch or f"issue-{issue_number}",
                last_commit_message=last_commit_message,
            )
        )

    return worktrees


def cleanup(project_root: Path) -> CleanupResult:
    """Remove worktrees whose branch has been merged into main."""
    worktrees = list_worktrees(project_root)
    if not worktrees:
        return CleanupResult(removed=[])

    merged_result = _run_git(["branch", "--merged", "main"], cwd=project_root)
    merged_branches: set[str] = set()
    if merged_result.returncode == 0:
        for line in merged_result.stdout.splitlines():
            merged_branches.add(line.strip().lstrip("* "))

    removed: list[str] = []
    for wt in worktrees:
        if wt.branch not in merged_branches:
            continue
        _run_git(["worktree", "remove", str(wt.path)], cwd=project_root)
        _run_git(["branch", "-d", wt.branch], cwd=project_root)
        removed.append(wt.branch)

    return CleanupResult(removed=removed)
