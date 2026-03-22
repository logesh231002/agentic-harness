"""PRD skill: produces a structured Product Requirements Document from grill output."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


class PrdError(Exception):
    """Raised when PRD generation encounters an unrecoverable error."""


_REQUIRED_SECTIONS = ("Overview", "User Stories", "Acceptance Criteria", "Non-Goals", "Dependencies")


@dataclass(frozen=True)
class PrdSection:
    """A single section of a PRD."""

    title: str
    content: str


@dataclass(frozen=True)
class Prd:
    """A complete Product Requirements Document."""

    title: str
    sections: Sequence[PrdSection]
    raw_md: str


def generate_prd(feature_title: str, grill_answers: Sequence[tuple[str, str]]) -> Prd:
    """Generate a structured PRD from a feature title and grill Q&A pairs.

    Args:
        feature_title: The name of the feature.
        grill_answers: Sequence of (question, answer) tuples from the grill phase.

    Returns:
        A complete Prd with all required sections.

    Raises:
        PrdError: If feature_title is empty or no grill answers are provided.
    """
    if not feature_title.strip():
        raise PrdError("Feature title must not be empty")
    if not grill_answers:
        raise PrdError("At least one grill answer is required")

    title = feature_title.strip()
    qa_block = "\n".join(f"- **Q:** {q}\n  **A:** {a}" for q, a in grill_answers)

    sections: list[PrdSection] = [
        PrdSection(
            title="Overview",
            content=f"{title} — a feature shaped by the following discovery:\n\n{qa_block}",
        ),
        PrdSection(
            title="User Stories",
            content=_derive_user_stories(title, grill_answers),
        ),
        PrdSection(
            title="Acceptance Criteria",
            content=_derive_acceptance_criteria(title, grill_answers),
        ),
        PrdSection(
            title="Non-Goals",
            content=_derive_non_goals(grill_answers),
        ),
        PrdSection(
            title="Dependencies",
            content=_derive_dependencies(grill_answers),
        ),
    ]

    raw_md = _format_prd_md(title, sections)

    return Prd(title=title, sections=sections, raw_md=raw_md)


def _derive_user_stories(title: str, answers: Sequence[tuple[str, str]]) -> str:
    """Derive user stories from grill answers."""
    stories: list[str] = [f"- As a user, I want {title.lower()} so that I can accomplish my goal"]
    for question, answer in answers:
        if "user" in question.lower() or "ux" in question.lower():
            stories.append(f"- As a user, {answer}")
    return "\n".join(stories)


def _derive_acceptance_criteria(title: str, answers: Sequence[tuple[str, str]]) -> str:
    """Derive acceptance criteria from grill answers."""
    criteria: list[str] = [f"- [ ] {title} is functional and tested"]
    for question, answer in answers:
        if "edge" in question.lower() or "invalid" in question.lower():
            criteria.append(f"- [ ] Handles edge case: {answer}")
    return "\n".join(criteria)


def _derive_non_goals(answers: Sequence[tuple[str, str]]) -> str:
    """Derive non-goals from scope-related grill answers."""
    non_goals: list[str] = []
    for question, answer in answers:
        if "scope" in question.lower() or "out of scope" in question.lower():
            non_goals.append(f"- {answer}")
    return "\n".join(non_goals) if non_goals else "- None identified during discovery"


def _derive_dependencies(answers: Sequence[tuple[str, str]]) -> str:
    """Derive dependencies from dependency-related grill answers."""
    deps: list[str] = []
    for question, answer in answers:
        if "depend" in question.lower() or "service" in question.lower():
            deps.append(f"- {answer}")
    return "\n".join(deps) if deps else "- No external dependencies identified"


def _format_prd_md(title: str, sections: Sequence[PrdSection]) -> str:
    """Format PRD sections as markdown."""
    parts: list[str] = [f"# PRD: {title}\n"]
    for section in sections:
        parts.append(f"## {section.title}\n")
        parts.append(f"{section.content}\n")
    return "\n".join(parts)
