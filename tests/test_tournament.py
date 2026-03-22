"""Tests for the tournament Ralph Loop orchestrator."""

from __future__ import annotations

import pytest

from src.modules.multi_agent.tournament import (
    JudgeResult,
    TournamentEntry,
    TournamentError,
    TournamentResult,
    TournamentSize,
    approve_qa,
    auto_classify_size,
    build_judge_prompt,
    create_judge_result,
    filter_disqualified,
    filter_qualified,
    get_worktree_count,
    is_merge_blocked,
    parse_tournament_size,
    run_tournament,
)


def _make_entry(
    agent_id: str = "agent-1",
    worktree_path: str = "/tmp/wt-1",
    compiled: bool = True,
    tests_passed: bool = True,
    diff: str = "+added line",
) -> TournamentEntry:
    return TournamentEntry(
        agent_id=agent_id,
        worktree_path=worktree_path,
        compiled=compiled,
        tests_passed=tests_passed,
        diff=diff,
    )


class TestParseTournamentSize:
    def test_full_label(self) -> None:
        assert parse_tournament_size(["tournament:full"]) is TournamentSize.FULL

    def test_pair_label(self) -> None:
        assert parse_tournament_size(["tournament:pair"]) is TournamentSize.PAIR

    def test_solo_label(self) -> None:
        assert parse_tournament_size(["tournament:solo"]) is TournamentSize.SOLO

    def test_no_matching_label_defaults_to_pair(self) -> None:
        assert parse_tournament_size(["bug", "priority:high"]) is TournamentSize.PAIR

    def test_empty_labels_defaults_to_pair(self) -> None:
        assert parse_tournament_size([]) is TournamentSize.PAIR

    def test_first_tournament_label_wins(self) -> None:
        assert parse_tournament_size(["tournament:full", "tournament:solo"]) is TournamentSize.FULL

    def test_case_insensitive(self) -> None:
        assert parse_tournament_size(["Tournament:Full"]) is TournamentSize.FULL

    def test_whitespace_stripped(self) -> None:
        assert parse_tournament_size(["  tournament:solo  "]) is TournamentSize.SOLO


class TestAutoClassifySize:
    def test_high_story_points_returns_full(self) -> None:
        assert auto_classify_size(story_points=9, file_count=1, dep_count=0) is TournamentSize.FULL

    def test_high_file_count_returns_full(self) -> None:
        assert auto_classify_size(story_points=1, file_count=11, dep_count=0) is TournamentSize.FULL

    def test_high_dep_count_returns_full(self) -> None:
        assert auto_classify_size(story_points=1, file_count=1, dep_count=6) is TournamentSize.FULL

    def test_medium_story_points_returns_pair(self) -> None:
        assert auto_classify_size(story_points=4, file_count=1, dep_count=0) is TournamentSize.PAIR

    def test_medium_file_count_returns_pair(self) -> None:
        assert auto_classify_size(story_points=1, file_count=4, dep_count=0) is TournamentSize.PAIR

    def test_medium_dep_count_returns_pair(self) -> None:
        assert auto_classify_size(story_points=1, file_count=1, dep_count=3) is TournamentSize.PAIR

    def test_low_complexity_returns_solo(self) -> None:
        assert auto_classify_size(story_points=1, file_count=1, dep_count=0) is TournamentSize.SOLO

    def test_boundary_at_eight_story_points_is_pair(self) -> None:
        assert auto_classify_size(story_points=8, file_count=1, dep_count=0) is TournamentSize.PAIR

    def test_boundary_at_three_story_points_is_solo(self) -> None:
        assert auto_classify_size(story_points=3, file_count=1, dep_count=0) is TournamentSize.SOLO


class TestGetWorktreeCount:
    def test_solo_returns_one(self) -> None:
        assert get_worktree_count(TournamentSize.SOLO) == 1

    def test_pair_returns_two(self) -> None:
        assert get_worktree_count(TournamentSize.PAIR) == 2

    def test_full_returns_four(self) -> None:
        assert get_worktree_count(TournamentSize.FULL) == 4


class TestFilterQualified:
    def test_keeps_compiled_entries(self) -> None:
        entries = [_make_entry(compiled=True), _make_entry(agent_id="agent-2", compiled=False)]
        result = filter_qualified(entries)
        assert len(result) == 1
        assert result[0].agent_id == "agent-1"

    def test_empty_input_returns_empty(self) -> None:
        assert filter_qualified([]) == ()

    def test_all_compiled_keeps_all(self) -> None:
        entries = [_make_entry(agent_id="a"), _make_entry(agent_id="b")]
        assert len(filter_qualified(entries)) == 2

    def test_none_compiled_returns_empty(self) -> None:
        entries = [_make_entry(compiled=False), _make_entry(agent_id="b", compiled=False)]
        assert len(filter_qualified(entries)) == 0

    def test_disqualified_keeps_non_compiled(self) -> None:
        entries = [_make_entry(compiled=True), _make_entry(agent_id="agent-2", compiled=False)]
        result = filter_disqualified(entries)
        assert len(result) == 1
        assert result[0].agent_id == "agent-2"


class TestBuildJudgePrompt:
    def test_includes_issue_title(self) -> None:
        prompt = build_judge_prompt("Fix auth", "Auth is broken", [_make_entry()])
        assert "**Fix auth**" in prompt

    def test_includes_issue_body(self) -> None:
        prompt = build_judge_prompt("Title", "Detailed description", [_make_entry()])
        assert "Detailed description" in prompt

    def test_includes_agent_id(self) -> None:
        prompt = build_judge_prompt("T", "B", [_make_entry(agent_id="agent-7")])
        assert "agent-7" in prompt

    def test_includes_diff(self) -> None:
        prompt = build_judge_prompt("T", "B", [_make_entry(diff="+new code")])
        assert "+new code" in prompt

    def test_includes_test_status(self) -> None:
        prompt = build_judge_prompt("T", "B", [_make_entry(tests_passed=False)])
        assert "False" in prompt

    def test_multiple_entries_numbered(self) -> None:
        entries = [_make_entry(agent_id="a"), _make_entry(agent_id="b")]
        prompt = build_judge_prompt("T", "B", entries)
        assert "### Implementation 1" in prompt
        assert "### Implementation 2" in prompt

    def test_includes_instructions(self) -> None:
        prompt = build_judge_prompt("T", "B", [_make_entry()])
        assert "Select the best implementation" in prompt

    def test_zero_qualified_raises_error(self) -> None:
        with pytest.raises(TournamentError, match="zero qualified entries"):
            build_judge_prompt("T", "B", [])


class TestRunTournament:
    def test_single_qualified_entry(self) -> None:
        entries = [_make_entry()]
        result = run_tournament(entries, "Title", "Body")
        assert len(result.qualified) == 1
        assert len(result.disqualified) == 0
        assert result.judge_result is None
        assert result.qa_approved is False

    def test_mixed_entries_separates_qualified_and_disqualified(self) -> None:
        entries = [
            _make_entry(agent_id="good", compiled=True),
            _make_entry(agent_id="bad", compiled=False),
        ]
        result = run_tournament(entries, "T", "B")
        assert len(result.qualified) == 1
        assert result.qualified[0].agent_id == "good"
        assert len(result.disqualified) == 1
        assert result.disqualified[0].agent_id == "bad"

    def test_preserves_all_entries(self) -> None:
        entries = [_make_entry(agent_id="a"), _make_entry(agent_id="b")]
        result = run_tournament(entries, "T", "B")
        assert len(result.entries) == 2

    def test_zero_entries_raises_error(self) -> None:
        with pytest.raises(TournamentError, match="zero entries"):
            run_tournament([], "T", "B")

    def test_all_disqualified_raises_error(self) -> None:
        entries = [_make_entry(compiled=False), _make_entry(agent_id="b", compiled=False)]
        with pytest.raises(TournamentError, match="disqualified"):
            run_tournament(entries, "T", "B")

    def test_result_is_frozen(self) -> None:
        result = run_tournament([_make_entry()], "T", "B")
        assert isinstance(result, TournamentResult)
        with pytest.raises(AttributeError):
            result.qa_approved = True  # type: ignore[misc]

    def test_judge_result_defaults_to_none(self) -> None:
        result = run_tournament([_make_entry()], "T", "B")
        assert result.judge_result is None


class TestQaGate:
    def test_new_result_is_merge_blocked(self) -> None:
        result = run_tournament([_make_entry()], "T", "B")
        assert is_merge_blocked(result) is True

    def test_approved_result_is_not_blocked(self) -> None:
        result = run_tournament([_make_entry()], "T", "B")
        approved = approve_qa(result)
        assert is_merge_blocked(approved) is False

    def test_approve_qa_returns_new_instance(self) -> None:
        result = run_tournament([_make_entry()], "T", "B")
        approved = approve_qa(result)
        assert approved is not result
        assert approved.qa_approved is True
        assert result.qa_approved is False

    def test_approve_qa_preserves_other_fields(self) -> None:
        entries = [_make_entry(agent_id="a"), _make_entry(agent_id="b", compiled=False)]
        result = run_tournament(entries, "Title", "Body")
        approved = approve_qa(result)
        assert approved.entries == result.entries
        assert approved.qualified == result.qualified
        assert approved.disqualified == result.disqualified
        assert approved.judge_result == result.judge_result

    def test_create_judge_result_returns_frozen(self) -> None:
        jr = create_judge_result("agent-1", "Best coverage", combined=False)
        assert isinstance(jr, JudgeResult)
        assert jr.selected_agent == "agent-1"
        assert jr.rationale == "Best coverage"
        assert jr.combined is False
        with pytest.raises(AttributeError):
            jr.selected_agent = "other"  # type: ignore[misc]
