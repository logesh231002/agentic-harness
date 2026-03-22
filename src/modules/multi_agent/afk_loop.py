"""AFK agent loop: filters, sorts, and picks issues for autonomous processing."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

_AFK_LABEL = "AFK"


class AfkLoopError(Exception):
    """Raised when the AFK loop encounters an unrecoverable error."""


@dataclass(frozen=True)
class AfkIssue:
    """A GitHub issue eligible for AFK processing."""

    number: int
    title: str
    labels: Sequence[str]
    blocked_by: Sequence[int]


@dataclass(frozen=True)
class LoopConfig:
    """Tunables for the AFK loop."""

    max_iterations: int = 10
    max_seconds_per_issue: int = 1800


@dataclass(frozen=True)
class IterationResult:
    """Outcome of processing a single issue."""

    issue_number: int
    success: bool
    reason: str
    elapsed_seconds: float


@dataclass(frozen=True)
class LoopResult:
    """Outcome of an entire AFK loop run."""

    iterations: Sequence[IterationResult]
    stopped_reason: str


def filter_afk_issues(issues: Sequence[AfkIssue]) -> Sequence[AfkIssue]:
    """Keep only issues that carry the AFK label."""
    return [issue for issue in issues if _AFK_LABEL in issue.labels]


def get_closed_issue_numbers(iterations: Sequence[IterationResult]) -> set[int]:
    """Extract issue numbers that were successfully closed."""
    return {it.issue_number for it in iterations if it.success}


def find_unblocked(issues: Sequence[AfkIssue], closed: set[int]) -> AfkIssue | None:
    """Return the first issue whose blockers are all resolved."""
    for issue in issues:
        if all(dep in closed for dep in issue.blocked_by):
            return issue
    return None


def sort_by_blocking_order(issues: Sequence[AfkIssue]) -> Sequence[AfkIssue]:
    """Sort issues so that those with fewer/no blockers come first (topological-ish)."""
    return sorted(issues, key=lambda i: (len(i.blocked_by), i.number))


def should_stop_loop(config: LoopConfig, iterations: Sequence[IterationResult]) -> tuple[bool, str]:
    """Check whether the loop has reached its max-iterations limit."""
    if len(iterations) >= config.max_iterations:
        return True, f"Reached max iterations ({config.max_iterations})"
    return False, ""


def check_time_limit(config: LoopConfig, elapsed_seconds: float) -> bool:
    """Return True if the elapsed time exceeds the per-issue limit."""
    return elapsed_seconds >= config.max_seconds_per_issue


def plan_next_iteration(
    afk_issues: Sequence[AfkIssue],
    completed: Sequence[IterationResult],
    config: LoopConfig,
) -> AfkIssue | None:
    """Pick the next issue to work on, or None if the loop should stop."""
    stop, _ = should_stop_loop(config, completed)
    if stop:
        return None

    filtered = filter_afk_issues(afk_issues)
    sorted_issues = sort_by_blocking_order(filtered)
    closed = get_closed_issue_numbers(completed)

    attempted = {it.issue_number for it in completed}
    remaining = [i for i in sorted_issues if i.number not in attempted]

    return find_unblocked(remaining, closed)


def record_success(issue: AfkIssue, elapsed: float) -> IterationResult:
    """Record a successful issue completion."""
    return IterationResult(
        issue_number=issue.number,
        success=True,
        reason="completed",
        elapsed_seconds=elapsed,
    )


def record_failure(issue: AfkIssue, elapsed: float, reason: str) -> IterationResult:
    """Record a failed issue attempt."""
    return IterationResult(
        issue_number=issue.number,
        success=False,
        reason=reason,
        elapsed_seconds=elapsed,
    )
