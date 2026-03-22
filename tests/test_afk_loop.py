"""Tests for the AFK agent loop: issue filtering, sorting, and iteration planning."""

from __future__ import annotations

from src.modules.multi_agent.afk_loop import (
    AfkIssue,
    IterationResult,
    LoopConfig,
    check_time_limit,
    filter_afk_issues,
    find_unblocked,
    plan_next_iteration,
    record_failure,
    record_success,
    should_stop_loop,
    sort_by_blocking_order,
)


def _issue(number: int, *, labels: list[str] | None = None, blocked_by: list[int] | None = None) -> AfkIssue:
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


class TestFilterAfkIssues:
    def test_keeps_issues_with_afk_label(self) -> None:
        issues = [_issue(1, labels=["AFK", "bug"]), _issue(2, labels=["enhancement"])]
        result = filter_afk_issues(issues)
        assert len(result) == 1
        assert result[0].number == 1

    def test_returns_empty_when_no_afk_labels(self) -> None:
        issues = [_issue(1, labels=["bug"]), _issue(2, labels=["enhancement"])]
        assert filter_afk_issues(issues) == []

    def test_returns_empty_for_empty_input(self) -> None:
        assert filter_afk_issues([]) == []

    def test_keeps_all_when_all_have_afk(self) -> None:
        issues = [_issue(1), _issue(2), _issue(3)]
        assert len(filter_afk_issues(issues)) == 3


class TestSortByBlockingOrder:
    def test_unblocked_before_blocked(self) -> None:
        issues = [_issue(2, blocked_by=[1]), _issue(1)]
        result = sort_by_blocking_order(issues)
        assert [i.number for i in result] == [1, 2]

    def test_fewer_blockers_first(self) -> None:
        issues = [_issue(3, blocked_by=[1, 2]), _issue(2, blocked_by=[1]), _issue(1)]
        result = sort_by_blocking_order(issues)
        assert [i.number for i in result] == [1, 2, 3]

    def test_tiebreaker_by_issue_number(self) -> None:
        issues = [_issue(5), _issue(3), _issue(1)]
        result = sort_by_blocking_order(issues)
        assert [i.number for i in result] == [1, 3, 5]

    def test_empty_input(self) -> None:
        assert sort_by_blocking_order([]) == []


class TestFindUnblocked:
    def test_returns_first_unblocked(self) -> None:
        issues = [_issue(1), _issue(2, blocked_by=[1])]
        result = find_unblocked(issues, closed=set())
        assert result is not None
        assert result.number == 1

    def test_returns_none_when_all_blocked(self) -> None:
        issues = [_issue(1, blocked_by=[99]), _issue(2, blocked_by=[99])]
        assert find_unblocked(issues, closed=set()) is None

    def test_unblocks_when_dependency_closed(self) -> None:
        issues = [_issue(2, blocked_by=[1])]
        result = find_unblocked(issues, closed={1})
        assert result is not None
        assert result.number == 2

    def test_returns_none_for_empty_list(self) -> None:
        assert find_unblocked([], closed=set()) is None

    def test_issue_with_no_blockers_is_always_unblocked(self) -> None:
        issues = [_issue(1)]
        result = find_unblocked(issues, closed=set())
        assert result is not None
        assert result.number == 1


class TestShouldStopLoop:
    def test_stops_at_max_iterations(self) -> None:
        config = LoopConfig(max_iterations=2)
        iterations = [_result(1), _result(2)]
        stop, reason = should_stop_loop(config, iterations)
        assert stop is True
        assert "max iterations" in reason.lower()

    def test_does_not_stop_below_limit(self) -> None:
        config = LoopConfig(max_iterations=5)
        iterations = [_result(1)]
        stop, reason = should_stop_loop(config, iterations)
        assert stop is False
        assert reason == ""

    def test_does_not_stop_on_empty(self) -> None:
        config = LoopConfig(max_iterations=10)
        stop, _ = should_stop_loop(config, [])
        assert stop is False


class TestCheckTimeLimit:
    def test_within_limit(self) -> None:
        config = LoopConfig(max_seconds_per_issue=1800)
        assert check_time_limit(config, 900.0) is False

    def test_at_limit(self) -> None:
        config = LoopConfig(max_seconds_per_issue=1800)
        assert check_time_limit(config, 1800.0) is True

    def test_over_limit(self) -> None:
        config = LoopConfig(max_seconds_per_issue=1800)
        assert check_time_limit(config, 2000.0) is True


class TestPlanNextIteration:
    def test_picks_first_unblocked_afk_issue(self) -> None:
        issues = [_issue(1), _issue(2, blocked_by=[1])]
        config = LoopConfig(max_iterations=10)
        result = plan_next_iteration(issues, [], config)
        assert result is not None
        assert result.number == 1

    def test_skips_already_attempted(self) -> None:
        issues = [_issue(1), _issue(2)]
        completed = [_result(1)]
        config = LoopConfig(max_iterations=10)
        result = plan_next_iteration(issues, completed, config)
        assert result is not None
        assert result.number == 2

    def test_returns_none_when_max_iterations_reached(self) -> None:
        issues = [_issue(1)]
        completed = [_result(i) for i in range(10)]
        config = LoopConfig(max_iterations=10)
        assert plan_next_iteration(issues, completed, config) is None

    def test_returns_none_when_all_blocked(self) -> None:
        issues = [_issue(1, blocked_by=[99])]
        config = LoopConfig(max_iterations=10)
        assert plan_next_iteration(issues, [], config) is None

    def test_returns_none_when_no_afk_issues(self) -> None:
        issues = [_issue(1, labels=["bug"])]
        config = LoopConfig(max_iterations=10)
        assert plan_next_iteration(issues, [], config) is None

    def test_unblocks_after_dependency_completed(self) -> None:
        issues = [_issue(1), _issue(2, blocked_by=[1])]
        completed = [_result(1, success=True)]
        config = LoopConfig(max_iterations=10)
        result = plan_next_iteration(issues, completed, config)
        assert result is not None
        assert result.number == 2

    def test_failed_dependency_does_not_unblock(self) -> None:
        issues = [_issue(1), _issue(2, blocked_by=[1])]
        completed = [_result(1, success=False)]
        config = LoopConfig(max_iterations=10)
        assert plan_next_iteration(issues, completed, config) is None


class TestRecordResults:
    def test_record_success(self) -> None:
        issue = _issue(42)
        result = record_success(issue, elapsed=15.5)
        assert result.issue_number == 42
        assert result.success is True
        assert result.reason == "completed"
        assert result.elapsed_seconds == 15.5

    def test_record_failure(self) -> None:
        issue = _issue(7)
        result = record_failure(issue, elapsed=120.0, reason="timeout")
        assert result.issue_number == 7
        assert result.success is False
        assert result.reason == "timeout"
        assert result.elapsed_seconds == 120.0
