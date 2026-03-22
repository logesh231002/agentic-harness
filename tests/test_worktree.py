"""Tests for the git worktree manager."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.modules.multi_agent.worktree import (
    WorktreeError,
    WorktreeInfo,
    cleanup,
    create,
    list_worktrees,
)


def _make_completed_process(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


_OK = _make_completed_process(0)
_FAIL = _make_completed_process(1, stderr="fatal: error")


class TestCreate:
    def test_creates_worktree_with_expected_path(self, tmp_path: Path) -> None:
        with patch("src.modules.multi_agent.worktree.subprocess.run", return_value=_OK):
            result = create(tmp_path, 42)

        assert result.path == tmp_path / ".worktrees" / "issue-42"
        assert result.branch == "issue-42"
        assert result.already_existed is False

    def test_returns_existing_when_directory_exists(self, tmp_path: Path) -> None:
        worktree_dir = tmp_path / ".worktrees" / "issue-42"
        worktree_dir.mkdir(parents=True)

        result = create(tmp_path, 42)

        assert result.path == worktree_dir
        assert result.branch == "issue-42"
        assert result.already_existed is True

    def test_raises_on_git_failure(self, tmp_path: Path) -> None:
        with patch("src.modules.multi_agent.worktree.subprocess.run", return_value=_FAIL):
            with pytest.raises(WorktreeError):
                create(tmp_path, 42)


_PORCELAIN_OUTPUT = """\
worktree /repo
HEAD abc123
branch refs/heads/main

worktree /repo/.worktrees/issue-7
HEAD def456
branch refs/heads/issue-7

"""


class TestListWorktrees:
    def test_parses_porcelain_output(self, tmp_path: Path) -> None:
        porcelain = _PORCELAIN_OUTPUT.replace("/repo", str(tmp_path))
        git_list = _make_completed_process(stdout=porcelain)
        git_log = _make_completed_process(stdout="fix: resolve flaky test\n")

        def side_effect(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            cmd: list[str] = args[0] if args else kwargs.get("args", [])
            if "worktree" in cmd:
                return git_list
            return git_log

        with patch("src.modules.multi_agent.worktree.subprocess.run", side_effect=side_effect):
            result = list_worktrees(tmp_path)

        assert len(result) == 1
        info = result[0]
        assert info.path == tmp_path / ".worktrees" / "issue-7"
        assert info.issue_number == 7
        assert info.branch == "issue-7"
        assert info.last_commit_message == "fix: resolve flaky test"

    def test_returns_empty_when_no_issue_worktrees(self, tmp_path: Path) -> None:
        porcelain = f"worktree {tmp_path}\nHEAD abc123\nbranch refs/heads/main\n\n"
        git_list = _make_completed_process(stdout=porcelain)

        with patch("src.modules.multi_agent.worktree.subprocess.run", return_value=git_list):
            result = list_worktrees(tmp_path)

        assert result == []

    def test_skips_main_worktree(self, tmp_path: Path) -> None:
        porcelain = _PORCELAIN_OUTPUT.replace("/repo", str(tmp_path))
        git_list = _make_completed_process(stdout=porcelain)
        git_log = _make_completed_process(stdout="some commit\n")

        def side_effect(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            cmd: list[str] = args[0] if args else kwargs.get("args", [])
            if "worktree" in cmd:
                return git_list
            return git_log

        with patch("src.modules.multi_agent.worktree.subprocess.run", side_effect=side_effect):
            result = list_worktrees(tmp_path)

        branches = [wt.branch for wt in result]
        assert "main" not in branches


class TestCleanup:
    def test_removes_merged_worktrees(self, tmp_path: Path) -> None:
        wt_info = WorktreeInfo(
            path=tmp_path / ".worktrees" / "issue-5",
            issue_number=5,
            branch="issue-5",
            last_commit_message="done",
        )
        merged_output = _make_completed_process(stdout="  issue-5\n  main\n")

        with (
            patch("src.modules.multi_agent.worktree.list_worktrees", return_value=[wt_info]),
            patch("src.modules.multi_agent.worktree.subprocess.run") as mock_run,
        ):
            mock_run.return_value = merged_output
            result = cleanup(tmp_path)

        assert result.removed == ["issue-5"]

        git_calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["git", "branch", "--merged", "main"] in git_calls
        assert ["git", "worktree", "remove", str(tmp_path / ".worktrees" / "issue-5")] in git_calls
        assert ["git", "branch", "-d", "issue-5"] in git_calls

    def test_keeps_unmerged_worktrees(self, tmp_path: Path) -> None:
        wt_info = WorktreeInfo(
            path=tmp_path / ".worktrees" / "issue-9",
            issue_number=9,
            branch="issue-9",
            last_commit_message="wip",
        )
        merged_output = _make_completed_process(stdout="  main\n")

        with (
            patch("src.modules.multi_agent.worktree.list_worktrees", return_value=[wt_info]),
            patch("src.modules.multi_agent.worktree.subprocess.run") as mock_run,
        ):
            mock_run.return_value = merged_output
            result = cleanup(tmp_path)

        assert result.removed == []
        remove_calls = [c for c in mock_run.call_args_list if "remove" in str(c)]
        assert remove_calls == []
