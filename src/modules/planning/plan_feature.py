"""Plan feature skill: creates implementation plans from GitHub issues."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


class PlanError(Exception):
    """Raised when plan creation or persistence fails."""


@dataclass(frozen=True)
class ImplementationPlan:
    """A structured implementation plan for a single issue."""

    issue_number: int
    tasks: Sequence[str]
    validation_strategy: str
    raw_md: str


def create_plan(issue_number: int, issue_title: str, issue_body: str) -> ImplementationPlan:
    """Create an implementation plan from a GitHub issue.

    Args:
        issue_number: The GitHub issue number.
        issue_title: The issue title.
        issue_body: The issue body/description.

    Returns:
        A structured ImplementationPlan.

    Raises:
        PlanError: If issue_number is non-positive or title is empty.
    """
    if issue_number <= 0:
        raise PlanError(f"Issue number must be positive, got {issue_number}")
    if not issue_title.strip():
        raise PlanError("Issue title must not be empty")

    title = issue_title.strip()
    body = issue_body.strip()

    tasks = _extract_tasks(title, body)
    validation = _derive_validation_strategy(title, body)
    raw_md = _format_plan_md(issue_number, title, tasks, validation)

    return ImplementationPlan(
        issue_number=issue_number,
        tasks=tasks,
        validation_strategy=validation,
        raw_md=raw_md,
    )


def save_plan(plan: ImplementationPlan, plans_dir: Path) -> Path:
    """Save an implementation plan to disk.

    Args:
        plan: The plan to persist.
        plans_dir: Directory to save plans into (e.g. `.claude/plans/`).

    Returns:
        The Path to the saved file.

    Raises:
        PlanError: If the plans directory cannot be created or written to.
    """
    try:
        plans_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PlanError(f"Cannot create plans directory: {plans_dir}") from exc

    file_path = plans_dir / f"{plan.issue_number}.md"
    try:
        file_path.write_text(plan.raw_md, encoding="utf-8")
    except OSError as exc:
        raise PlanError(f"Cannot write plan file: {file_path}") from exc

    return file_path


def _extract_tasks(title: str, body: str) -> list[str]:
    """Extract implementation tasks from an issue."""
    tasks: list[str] = [
        f"Read and understand: {title}",
        "Identify affected files and modules",
    ]

    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [ ]") or stripped.startswith("- [x]"):
            task_text = stripped[5:].strip()
            if task_text:
                tasks.append(task_text)

    tasks.append("Write tests for new behavior")
    tasks.append("Implement changes")
    tasks.append("Verify all checks pass")

    return tasks


def _derive_validation_strategy(title: str, body: str) -> str:
    """Derive a validation strategy from the issue content."""
    strategies: list[str] = ["Run existing test suite to check for regressions"]

    combined = f"{title} {body}".lower()
    if "api" in combined or "endpoint" in combined:
        strategies.append("Test API endpoints with curl or httpie")
    if "ui" in combined or "frontend" in combined:
        strategies.append("Manual visual verification in browser")
    if "database" in combined or "migration" in combined:
        strategies.append("Verify database schema changes apply cleanly")

    strategies.append("Run mypy --strict and ruff check")
    return "\n".join(f"- {s}" for s in strategies)


def _format_plan_md(issue_number: int, title: str, tasks: Sequence[str], validation: str) -> str:
    """Format the plan as markdown."""
    task_list = "\n".join(f"- [ ] {t}" for t in tasks)
    return f"# Plan: #{issue_number} — {title}\n\n## Tasks\n\n{task_list}\n\n## Validation Strategy\n\n{validation}\n"
