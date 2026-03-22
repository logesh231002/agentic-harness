"""Issues skill: generates labeled GitHub issues from a PRD."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from src.modules.planning.prd import Prd


class IssueClassificationError(Exception):
    """Raised when issue classification encounters an unrecoverable error."""


class IssueLabel(Enum):
    """Classification for whether an issue can be automated or needs human input."""

    AFK = "afk"
    HITL = "hitl"


_HITL_KEYWORDS = frozenset(
    {
        "design",
        "decision",
        "review",
        "approve",
        "choose",
        "evaluate",
        "feedback",
        "ux",
        "user research",
        "stakeholder",
    }
)


@dataclass(frozen=True)
class PlannedIssue:
    """A GitHub issue derived from a PRD."""

    title: str
    body: str
    label: IssueLabel
    blocked_by: Sequence[int]


def classify_issue(title: str, body: str) -> IssueLabel:
    """Classify an issue as AFK (automatable) or HITL (requires human).

    Args:
        title: The issue title.
        body: The issue body.

    Returns:
        IssueLabel.HITL if the issue requires human judgment, IssueLabel.AFK otherwise.

    Raises:
        IssueClassificationError: If title is empty.
    """
    if not title.strip():
        raise IssueClassificationError("Issue title must not be empty")

    combined = f"{title} {body}".lower()
    for keyword in _HITL_KEYWORDS:
        if keyword in combined:
            return IssueLabel.HITL
    return IssueLabel.AFK


def extract_issues_from_prd(prd: Prd) -> Sequence[PlannedIssue]:
    """Generate vertical-slice issues from a PRD.

    Each PRD section (except Overview and Non-Goals) produces at least one issue.
    The first issue is always a setup/scaffolding issue that others depend on.

    Args:
        prd: A complete PRD to decompose.

    Returns:
        A sequence of PlannedIssue with dependency information.
    """
    issues: list[PlannedIssue] = []

    scaffold_body = f"Set up project structure for: {prd.title}\n\nDerived from PRD."
    issues.append(
        PlannedIssue(
            title=f"Scaffold {prd.title}",
            body=scaffold_body,
            label=classify_issue(f"Scaffold {prd.title}", scaffold_body),
            blocked_by=[],
        )
    )

    for section in prd.sections:
        if section.title in ("Overview", "Non-Goals"):
            continue

        issue_title = f"Implement {section.title} for {prd.title}"
        issue_body = f"## {section.title}\n\n{section.content}\n\nDerived from PRD section."
        issues.append(
            PlannedIssue(
                title=issue_title,
                body=issue_body,
                label=classify_issue(issue_title, issue_body),
                blocked_by=[0],
            )
        )

    return issues


def get_blocking_order(issues: Sequence[PlannedIssue]) -> Sequence[int]:
    """Return execution order respecting dependency constraints.

    Uses topological sort to produce an order where each issue appears
    after all issues it is blocked by.

    Args:
        issues: The issues to order.

    Returns:
        A sequence of issue indices in valid execution order.
    """
    n = len(issues)
    in_degree: list[int] = [0] * n
    dependents: dict[int, list[int]] = {i: [] for i in range(n)}

    for i, issue in enumerate(issues):
        for blocker in issue.blocked_by:
            if 0 <= blocker < n:
                in_degree[i] += 1
                dependents[blocker].append(i)

    queue: list[int] = [i for i in range(n) if in_degree[i] == 0]
    order: list[int] = []

    while queue:
        current = queue.pop(0)
        order.append(current)
        for dep in dependents[current]:
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                queue.append(dep)

    return order
