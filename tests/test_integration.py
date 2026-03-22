"""End-to-end integration smoke tests for AFK loop + council + tournament."""

from __future__ import annotations

import time

from src.modules.multi_agent.afk_loop import (
    AfkIssue,
    IterationResult,
    LoopConfig,
    filter_afk_issues,
    find_unblocked,
    get_closed_issue_numbers,
    plan_next_iteration,
    record_failure,
    record_success,
    should_stop_loop,
    sort_by_blocking_order,
)
from src.modules.multi_agent.council import (
    CouncilResponse,
    CouncilStep,
    is_council_worthy,
    run_council,
)
from src.modules.multi_agent.tournament import (
    TournamentEntry,
    TournamentSize,
    approve_qa,
    build_judge_prompt,
    filter_disqualified,
    filter_qualified,
    is_merge_blocked,
    parse_tournament_size,
    run_tournament,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _issue(
    number: int,
    *,
    labels: list[str] | None = None,
    blocked_by: list[int] | None = None,
) -> AfkIssue:
    return AfkIssue(
        number=number,
        title=f"Issue {number}",
        labels=labels or ["AFK"],
        blocked_by=blocked_by or [],
    )


def _result(number: int, *, success: bool = True, elapsed: float = 10.0) -> IterationResult:
    return IterationResult(
        issue_number=number,
        success=success,
        reason="completed" if success else "failed",
        elapsed_seconds=elapsed,
    )


def _step(
    *,
    models: list[str] | None = None,
    chairman_prompt: str = "Synthesize the plans below.",
) -> CouncilStep:
    return CouncilStep(
        name="planning",
        models=models if models is not None else ["claude-sonnet", "gpt-4"],
        chairman_prompt=chairman_prompt,
        cost_multiplier=2.0,
    )


def _entry(
    agent_id: str = "agent-1",
    *,
    compiled: bool = True,
    tests_passed: bool = True,
    diff: str = "+added line",
) -> TournamentEntry:
    return TournamentEntry(
        agent_id=agent_id,
        worktree_path=f"/tmp/wt-{agent_id}",
        compiled=compiled,
        tests_passed=tests_passed,
        diff=diff,
    )


# ---------------------------------------------------------------------------
# AFK Loop Integration
# ---------------------------------------------------------------------------


class TestAfkLoopIntegration:
    """Full pipeline: filter → sort → find_unblocked → record → plan_next."""

    def test_full_pipeline_picks_correct_issue(self) -> None:
        """Filter AFK issues, sort by blocking order, pick first unblocked."""
        issues = [
            _issue(3, blocked_by=[1, 2]),
            _issue(1),
            _issue(2, blocked_by=[1]),
            _issue(4, labels=["bug"]),  # not AFK
        ]

        filtered = filter_afk_issues(issues)
        assert len(filtered) == 3  # issue 4 excluded

        sorted_issues = sort_by_blocking_order(filtered)
        assert sorted_issues[0].number == 1  # unblocked, lowest number

        picked = find_unblocked(sorted_issues, closed=set())
        assert picked is not None
        assert picked.number == 1

    def test_record_results_and_plan_next_respects_blocking(self) -> None:
        """Complete issue 1, verify issue 2 unblocks, issue 3 stays blocked."""
        issues = [
            _issue(1),
            _issue(2, blocked_by=[1]),
            _issue(3, blocked_by=[1, 2]),
        ]
        config = LoopConfig(max_iterations=10)

        # Iteration 1: pick issue 1
        picked = plan_next_iteration(issues, [], config)
        assert picked is not None
        assert picked.number == 1

        result_1 = record_success(picked, elapsed=30.0)
        assert result_1.success is True

        # Iteration 2: issue 2 should unblock
        picked = plan_next_iteration(issues, [result_1], config)
        assert picked is not None
        assert picked.number == 2

        result_2 = record_success(picked, elapsed=25.0)

        # Iteration 3: issue 3 should unblock (both deps closed)
        picked = plan_next_iteration(issues, [result_1, result_2], config)
        assert picked is not None
        assert picked.number == 3

    def test_failed_dependency_blocks_downstream(self) -> None:
        """When a dependency fails, downstream issues remain blocked."""
        issues = [_issue(1), _issue(2, blocked_by=[1])]
        config = LoopConfig(max_iterations=10)

        picked = plan_next_iteration(issues, [], config)
        assert picked is not None
        assert picked.number == 1

        result_1 = record_failure(picked, elapsed=60.0, reason="tests failed")
        assert result_1.success is False

        # Issue 2 stays blocked — dep 1 failed, not closed
        picked = plan_next_iteration(issues, [result_1], config)
        assert picked is None

    def test_loop_stops_at_max_iterations(self) -> None:
        """plan_next_iteration returns None after max iterations."""
        issues = [_issue(i) for i in range(1, 20)]
        config = LoopConfig(max_iterations=3)

        completed: list[IterationResult] = []
        for _ in range(3):
            picked = plan_next_iteration(issues, completed, config)
            assert picked is not None
            completed.append(record_success(picked, elapsed=5.0))

        stop, reason = should_stop_loop(config, completed)
        assert stop is True
        assert "3" in reason

        assert plan_next_iteration(issues, completed, config) is None

    def test_closed_issue_numbers_tracks_successes_only(self) -> None:
        """get_closed_issue_numbers only includes successful iterations."""
        completed = [
            _result(1, success=True),
            _result(2, success=False),
            _result(3, success=True),
        ]
        closed = get_closed_issue_numbers(completed)
        assert closed == {1, 3}


# ---------------------------------------------------------------------------
# Council Integration
# ---------------------------------------------------------------------------


class TestCouncilIntegration:
    """Full pipeline: anonymize → deduplicate → build_chairman_prompt → run_council."""

    def test_full_council_pipeline_anonymizes_and_deduplicates(self) -> None:
        """Two model responses go through anonymization, dedup, and chairman synthesis."""
        step = _step(chairman_prompt="Merge the architectural suggestions.")
        responses = [
            CouncilResponse(model="claude-sonnet", content="I am Claude. Use dependency injection."),
            CouncilResponse(model="gpt-4", content="As GPT-4, prefer composition over inheritance."),
        ]

        result = run_council(step, responses)

        assert result.was_single_agent is False
        assert result.responses_count == 2
        # Model names stripped
        assert "Claude" not in result.chairman_output
        assert "GPT-4" not in result.chairman_output
        # Chairman template present
        assert "Merge the architectural suggestions." in result.chairman_output
        # Both responses present (different content → not deduped)
        assert result.chairman_output.count("### Response") == 2

    def test_single_agent_fallback(self) -> None:
        """With one response, council returns content directly without chairman."""
        step = _step()
        responses = [CouncilResponse(model="claude-sonnet", content="Solo analysis.")]

        result = run_council(step, responses)

        assert result.was_single_agent is True
        assert result.chairman_output == "Solo analysis."
        assert result.responses_count == 1

    def test_near_duplicate_responses_collapsed(self) -> None:
        """Near-identical responses from different models are deduplicated."""
        step = _step()
        responses = [
            CouncilResponse(model="claude-sonnet", content="Refactor the auth module for testability."),
            CouncilResponse(model="gpt-4", content="Refactor the auth module for testability!"),
        ]

        result = run_council(step, responses)

        # Near-duplicates should be collapsed to 1 response
        assert result.chairman_output.count("### Response") == 1
        assert result.was_single_agent is False

    def test_council_worthiness_gates_multi_model(self) -> None:
        """is_council_worthy correctly identifies single vs multi-model steps."""
        single = _step(models=["claude-sonnet"])
        multi = _step(models=["claude-sonnet", "gpt-4"])

        assert is_council_worthy(single) is False
        assert is_council_worthy(multi) is True


# ---------------------------------------------------------------------------
# Tournament Integration
# ---------------------------------------------------------------------------


class TestTournamentIntegration:
    """Full pipeline: filter → judge prompt → run_tournament → QA gate."""

    def test_full_tournament_pipeline(self) -> None:
        """Two entries (one compiles, one doesn't) → tournament → QA gate."""
        entries = [
            _entry("agent-a", compiled=True, tests_passed=True, diff="+good code"),
            _entry("agent-b", compiled=False, tests_passed=False, diff="+broken code"),
        ]

        result = run_tournament(entries, "Fix auth bug", "Auth is broken on login.")

        assert len(result.qualified) == 1
        assert result.qualified[0].agent_id == "agent-a"
        assert len(result.disqualified) == 1
        assert result.disqualified[0].agent_id == "agent-b"
        assert result.qa_approved is False
        assert is_merge_blocked(result) is True

        # Build judge prompt from qualified entries
        prompt = build_judge_prompt("Fix auth bug", "Auth is broken on login.", result.qualified)
        assert "**Fix auth bug**" in prompt
        assert "+good code" in prompt
        assert "+broken code" not in prompt  # disqualified entry excluded

        # Approve QA → unblocks merge
        approved = approve_qa(result)
        assert is_merge_blocked(approved) is False
        assert approved.qa_approved is True

    def test_qa_gate_blocks_until_approved(self) -> None:
        """Tournament result is merge-blocked until explicitly approved."""
        entries = [_entry("agent-1")]
        result = run_tournament(entries, "T", "B")

        assert is_merge_blocked(result) is True
        approved = approve_qa(result)
        assert is_merge_blocked(approved) is False
        # Original unchanged (frozen dataclass)
        assert is_merge_blocked(result) is True

    def test_tournament_size_from_labels(self) -> None:
        """Labels on an AFK issue determine tournament size."""
        issue = _issue(1, labels=["AFK", "tournament:full"])
        size = parse_tournament_size(list(issue.labels))
        assert size is TournamentSize.FULL

        issue_default = _issue(2, labels=["AFK"])
        size_default = parse_tournament_size(list(issue_default.labels))
        assert size_default is TournamentSize.PAIR


# ---------------------------------------------------------------------------
# Cross-Module Integration
# ---------------------------------------------------------------------------


class TestCrossModuleIntegration:
    """AFK loop picks issue → council reviews → tournament implements."""

    def test_afk_to_council_to_tournament_flow(self) -> None:
        """Full cross-module flow: pick issue, council review, tournament implementation."""
        # Step 1: AFK loop picks an issue
        issues = [
            _issue(10, labels=["AFK", "tournament:pair"]),
            _issue(20, labels=["AFK"], blocked_by=[10]),
        ]
        config = LoopConfig(max_iterations=5)

        picked = plan_next_iteration(issues, [], config)
        assert picked is not None
        assert picked.number == 10

        # Step 2: Council reviews the issue (plan phase)
        step = _step(chairman_prompt=f"Review implementation plan for: {picked.title}")
        responses = [
            CouncilResponse(model="claude-sonnet", content="Add input validation first."),
            CouncilResponse(model="gpt-4", content="Write tests before implementation."),
        ]
        council_result = run_council(step, responses)
        assert council_result.was_single_agent is False
        assert "Review implementation plan for: Issue 10" in council_result.chairman_output

        # Step 3: Tournament implements the issue
        entries = [
            _entry("agent-a", compiled=True, tests_passed=True, diff="+validation added"),
            _entry("agent-b", compiled=True, tests_passed=False, diff="+partial fix"),
        ]
        tournament_result = run_tournament(entries, picked.title, "Fix the auth module")
        assert len(tournament_result.qualified) == 2

        # Step 4: QA approves → record success → next issue unblocks
        approved = approve_qa(tournament_result)
        assert not is_merge_blocked(approved)

        result_10 = record_success(picked, elapsed=120.0)
        next_picked = plan_next_iteration(issues, [result_10], config)
        assert next_picked is not None
        assert next_picked.number == 20  # unblocked by issue 10 success

    def test_data_flows_between_modules_correctly(self) -> None:
        """Verify AfkIssue fields (title, labels) are usable by council and tournament."""
        issue = _issue(42, labels=["AFK", "tournament:full"])

        # Issue title flows into council chairman prompt (need 2+ responses to avoid single-agent fallback)
        step = _step(chairman_prompt=f"Analyze: {issue.title}")
        responses = [
            CouncilResponse(model="m1", content="Plan A."),
            CouncilResponse(model="m2", content="Plan B."),
        ]
        council_result = run_council(step, responses)
        assert "Issue 42" in council_result.chairman_output

        # Issue labels determine tournament size
        size = parse_tournament_size(list(issue.labels))
        assert size is TournamentSize.FULL

        # Issue title flows into tournament judge prompt
        entries = [_entry("a")]
        prompt = build_judge_prompt(issue.title, "Description", entries)
        assert "**Issue 42**" in prompt

    def test_failed_issue_prevents_downstream_unblock(self) -> None:
        """If tournament fails for issue 10, issue 20 (blocked by 10) stays blocked."""
        issues = [
            _issue(10),
            _issue(20, blocked_by=[10]),
        ]
        config = LoopConfig(max_iterations=5)

        picked = plan_next_iteration(issues, [], config)
        assert picked is not None
        assert picked.number == 10

        # Tournament/implementation fails
        result_10 = record_failure(picked, elapsed=90.0, reason="all entries disqualified")

        next_picked = plan_next_iteration(issues, [result_10], config)
        assert next_picked is None  # issue 20 still blocked


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


class TestPerformance:
    """All integration tests should complete well under 5 seconds."""

    def test_all_integration_logic_is_fast(self) -> None:
        """Run a representative workload and assert it completes in under 2 seconds."""
        start = time.monotonic()

        # Simulate a multi-iteration AFK loop
        issues = [_issue(i, blocked_by=[i - 1] if i > 1 else []) for i in range(1, 51)]
        config = LoopConfig(max_iterations=50)
        completed: list[IterationResult] = []

        for _ in range(50):
            picked = plan_next_iteration(issues, completed, config)
            if picked is None:
                break
            completed.append(record_success(picked, elapsed=1.0))

        assert len(completed) == 50

        # Council with many responses
        step = _step()
        responses = [CouncilResponse(model=f"model-{i}", content=f"Suggestion {i} for improvement.") for i in range(20)]
        council_result = run_council(step, responses)
        assert council_result.responses_count == 20

        # Tournament with many entries
        entries = [_entry(f"agent-{i}", compiled=(i % 3 != 0)) for i in range(20)]
        qualified = filter_qualified(entries)
        disqualified = filter_disqualified(entries)
        assert len(qualified) + len(disqualified) == 20

        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"Integration workload took {elapsed:.2f}s, expected < 2s"
