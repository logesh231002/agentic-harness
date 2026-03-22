"""Tests for the reset and recovery module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.modules.reset_recovery.reset import (
    CommitInfo,
    CompactionTracker,
    ResetError,
    cross_model_critique,
    export_conversation,
    get_reset_recovery_rule,
    record_compaction,
    reset_to_clean_commit,
    should_force_handoff,
)


class TestResetToCleanCommit:
    def test_returns_first_commit_when_it_passes(self) -> None:
        commits = [
            CommitInfo(sha="aaa", message="latest", tests_passed=True),
            CommitInfo(sha="bbb", message="older", tests_passed=True),
        ]
        result = reset_to_clean_commit(commits)
        assert result.target_commit == "aaa"
        assert result.commits_checked == 1
        assert result.strategy == "stash"

    def test_skips_failing_commits_to_find_clean(self) -> None:
        commits = [
            CommitInfo(sha="aaa", message="broken", tests_passed=False),
            CommitInfo(sha="bbb", message="also broken", tests_passed=False),
            CommitInfo(sha="ccc", message="last good", tests_passed=True),
        ]
        result = reset_to_clean_commit(commits)
        assert result.target_commit == "ccc"
        assert result.commits_checked == 3
        assert result.strategy == "hard_reset"

    def test_raises_on_empty_history(self) -> None:
        with pytest.raises(ResetError, match="No commit history provided"):
            reset_to_clean_commit([])

    def test_raises_when_no_clean_commit_exists(self) -> None:
        commits = [
            CommitInfo(sha="aaa", message="bad", tests_passed=False),
            CommitInfo(sha="bbb", message="worse", tests_passed=False),
        ]
        with pytest.raises(ResetError, match="No clean commit found"):
            reset_to_clean_commit(commits)

    def test_strategy_is_stash_for_first_commit(self) -> None:
        commits = [CommitInfo(sha="aaa", message="good", tests_passed=True)]
        result = reset_to_clean_commit(commits)
        assert result.strategy == "stash"

    def test_strategy_is_hard_reset_for_non_first(self) -> None:
        commits = [
            CommitInfo(sha="aaa", message="bad", tests_passed=False),
            CommitInfo(sha="bbb", message="good", tests_passed=True),
        ]
        result = reset_to_clean_commit(commits)
        assert result.strategy == "hard_reset"


class TestExportConversation:
    def test_reads_plain_text_file(self, tmp_path: Path) -> None:
        session_file = tmp_path / "session.txt"
        session_file.write_text("Hello\nWorld", encoding="utf-8")
        result = export_conversation(session_file)
        assert result == "Hello\nWorld"

    def test_reads_json_lines_with_content_field(self, tmp_path: Path) -> None:
        session_file = tmp_path / "session.jsonl"
        lines = [
            json.dumps({"role": "user", "content": "What is 2+2?"}),
            json.dumps({"role": "assistant", "content": "4"}),
        ]
        session_file.write_text("\n".join(lines), encoding="utf-8")
        result = export_conversation(session_file)
        assert "What is 2+2?" in result
        assert "4" in result

    def test_raises_on_missing_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.txt"
        with pytest.raises(ResetError, match="Session file not found"):
            export_conversation(missing)

    def test_raises_on_empty_file(self, tmp_path: Path) -> None:
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("", encoding="utf-8")
        with pytest.raises(ResetError, match="Session file is empty"):
            export_conversation(empty_file)

    def test_falls_back_to_plain_text_for_non_json(self, tmp_path: Path) -> None:
        session_file = tmp_path / "session.txt"
        session_file.write_text("not json at all\njust plain text", encoding="utf-8")
        result = export_conversation(session_file)
        assert result == "not json at all\njust plain text"


class TestCrossModelCritique:
    def test_returns_string_containing_conversation(self) -> None:
        prompt = cross_model_critique("User said hello")
        assert "User said hello" in prompt

    def test_includes_review_categories(self) -> None:
        prompt = cross_model_critique("test conversation")
        assert "Logical errors" in prompt
        assert "Missed alternatives" in prompt
        assert "Scope creep" in prompt
        assert "Unverified claims" in prompt

    def test_includes_instructions_section(self) -> None:
        prompt = cross_model_critique("test conversation")
        assert "## Instructions" in prompt
        assert "Issue" in prompt
        assert "Evidence" in prompt
        assert "Recommendation" in prompt


class TestCompactionTracker:
    def test_default_values(self) -> None:
        tracker = CompactionTracker()
        assert tracker.count == 0
        assert tracker.limit == 2

    def test_record_compaction_increments_count(self) -> None:
        tracker = CompactionTracker()
        updated = record_compaction(tracker)
        assert updated.count == 1
        assert tracker.count == 0

    def test_record_compaction_preserves_limit(self) -> None:
        tracker = CompactionTracker(count=0, limit=5)
        updated = record_compaction(tracker)
        assert updated.limit == 5

    def test_should_force_handoff_at_limit(self) -> None:
        tracker = CompactionTracker(count=2, limit=2)
        assert should_force_handoff(tracker) is True

    def test_should_not_force_handoff_below_limit(self) -> None:
        tracker = CompactionTracker(count=1, limit=2)
        assert should_force_handoff(tracker) is False

    def test_should_force_handoff_above_limit(self) -> None:
        tracker = CompactionTracker(count=3, limit=2)
        assert should_force_handoff(tracker) is True

    def test_custom_limit(self) -> None:
        tracker = CompactionTracker(count=4, limit=5)
        assert should_force_handoff(tracker) is False
        tracker_at_limit = CompactionTracker(count=5, limit=5)
        assert should_force_handoff(tracker_at_limit) is True

    def test_frozen_immutability(self) -> None:
        tracker = CompactionTracker()
        with pytest.raises(AttributeError):
            tracker.count = 1  # type: ignore[misc]


class TestResetRecoveryRule:
    def test_returns_non_empty_string(self) -> None:
        rule = get_reset_recovery_rule()
        assert isinstance(rule, str)
        assert len(rule) > 0

    def test_contains_protocol_header(self) -> None:
        rule = get_reset_recovery_rule()
        assert "# Reset & Recovery Protocol" in rule

    def test_contains_compaction_rule(self) -> None:
        rule = get_reset_recovery_rule()
        assert "2 compactions" in rule

    def test_contains_steps(self) -> None:
        rule = get_reset_recovery_rule()
        assert "Stash or reset" in rule
        assert "Export" in rule
        assert "Hand off" in rule
