"""Tests for the session handoff command."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

from src.modules.context.handoff import (
    SessionTracker,
    _format_handoff_md,
    generate_handoff,
)


def _make_completed_process(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _git_side_effect(responses: dict[str, subprocess.CompletedProcess[str]]) -> Any:
    """Return a side_effect callable that matches git subcommands to canned responses."""
    default = _make_completed_process(0, stdout="")

    def _side_effect(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        cmd: list[str] = args[0] if args else kwargs.get("args", [])
        cmd_str = " ".join(cmd)
        for key, response in responses.items():
            if key in cmd_str:
                return response
        return default

    return _side_effect


class TestSessionTracker:
    def test_initial_compaction_count_is_zero(self) -> None:
        tracker = SessionTracker()
        assert tracker.compaction_count == 0

    def test_record_compaction_increments(self) -> None:
        tracker = SessionTracker()
        tracker.record_compaction()
        tracker.record_compaction()
        assert tracker.compaction_count == 2

    def test_should_force_handoff_after_two_compactions(self) -> None:
        tracker = SessionTracker()
        tracker.record_compaction()
        tracker.record_compaction()
        assert tracker.should_force_handoff() is True

    def test_no_force_handoff_below_threshold(self) -> None:
        tracker = SessionTracker()
        tracker.record_compaction()
        assert tracker.should_force_handoff() is False


class TestGenerateHandoff:
    def test_writes_handoff_file(self, tmp_path: Path) -> None:
        tracker = SessionTracker()
        with patch("src.modules.context.handoff.subprocess.run", return_value=_make_completed_process()):
            result = generate_handoff(tmp_path, tracker)
        assert result.output_path.exists()
        assert result.output_path == tmp_path / "HANDOFF.md"

    def test_includes_all_four_sections(self, tmp_path: Path) -> None:
        tracker = SessionTracker()
        with patch("src.modules.context.handoff.subprocess.run", return_value=_make_completed_process()):
            result = generate_handoff(tmp_path, tracker)
        expected_keys = {"Completed This Session", "In Progress", "Blocked", "Recommended Starting Point"}
        assert set(result.sections.keys()) == expected_keys

    def test_completed_section_includes_commit_messages(self, tmp_path: Path) -> None:
        tracker = SessionTracker()
        responses = {
            "log --oneline": _make_completed_process(stdout="abc1234 feat: add handoff\ndef5678 fix: typo"),
            "diff --name-only HEAD..HEAD": _make_completed_process(stdout="src/handoff.py\n"),
        }
        with patch("src.modules.context.handoff.subprocess.run", side_effect=_git_side_effect(responses)):
            result = generate_handoff(tmp_path, tracker)
        completed = result.sections["Completed This Session"]
        assert "abc1234 feat: add handoff" in completed
        assert "def5678 fix: typo" in completed

    def test_in_progress_section_includes_unstaged_files(self, tmp_path: Path) -> None:
        tracker = SessionTracker()

        def _side_effect(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            cmd: list[str] = args[0] if args else kwargs.get("args", [])
            if cmd == ["git", "diff", "--name-only"]:
                return _make_completed_process(stdout="src/wip.py\n")
            return _make_completed_process()

        with patch("src.modules.context.handoff.subprocess.run", side_effect=_side_effect):
            result = generate_handoff(tmp_path, tracker)
        assert "src/wip.py" in result.sections["In Progress"]

    def test_compaction_count_in_result(self, tmp_path: Path) -> None:
        tracker = SessionTracker()
        tracker.record_compaction()
        tracker.record_compaction()
        tracker.record_compaction()
        with patch("src.modules.context.handoff.subprocess.run", return_value=_make_completed_process()):
            result = generate_handoff(tmp_path, tracker)
        assert result.compaction_count == 3


class TestFormatHandoffMd:
    def test_markdown_has_header(self) -> None:
        sections = {
            "Completed This Session": "Done.",
            "In Progress": "WIP.",
            "Blocked": "None.",
            "Recommended Starting Point": "Start here.",
        }
        output = _format_handoff_md(sections, compaction_count=0)
        assert output.startswith("# Session Handoff")

    def test_markdown_includes_compaction_count(self) -> None:
        sections = {
            "Completed This Session": "Done.",
            "In Progress": "WIP.",
            "Blocked": "None.",
            "Recommended Starting Point": "Start here.",
        }
        output = _format_handoff_md(sections, compaction_count=5)
        assert "_Compaction count: 5_" in output
