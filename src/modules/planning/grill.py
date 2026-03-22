"""Grill skill: surfaces assumptions via structured questions before planning."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


class GrillError(Exception):
    """Raised when the grill process encounters an unrecoverable error."""


@dataclass(frozen=True)
class GrillQuestion:
    """A structured question targeting a specific assumption category."""

    category: str
    question: str
    assumption: str


_QUESTION_TEMPLATES: list[tuple[str, str, str]] = [
    (
        "scope",
        "What is the minimum viable version of '{feature}' that delivers value?",
        "The feature scope is well-defined and bounded.",
    ),
    (
        "scope",
        "Which parts of '{feature}' can be deferred to a follow-up iteration?",
        "All described functionality must ship in the first release.",
    ),
    (
        "edge_cases",
        "What happens when '{feature}' receives invalid or unexpected input?",
        "All inputs will be well-formed and within expected ranges.",
    ),
    (
        "edge_cases",
        "How should '{feature}' behave under concurrent access or race conditions?",
        "The feature will only be used in single-threaded, sequential scenarios.",
    ),
    (
        "dependencies",
        "What external services or libraries does '{feature}' depend on?",
        "No new external dependencies are required.",
    ),
    (
        "dependencies",
        "Are there existing modules that '{feature}' must integrate with or extend?",
        "The feature can be built in complete isolation.",
    ),
    (
        "ux",
        "How will users discover and learn to use '{feature}'?",
        "Users will intuitively understand the feature without guidance.",
    ),
    (
        "ux",
        "What feedback should '{feature}' provide when operations succeed or fail?",
        "Success and failure states are obvious and need no explicit communication.",
    ),
]


def generate_grill_questions(feature_description: str) -> Sequence[GrillQuestion]:
    """Produce structured questions targeting scope, edge cases, dependencies, and UX.

    Args:
        feature_description: A plain-text description of the feature to interrogate.

    Returns:
        A sequence of at least 5 GrillQuestion instances across different categories.

    Raises:
        GrillError: If feature_description is empty.
    """
    if not feature_description.strip():
        raise GrillError("Feature description must not be empty.")

    return [
        GrillQuestion(
            category=category,
            question=question_template.format(feature=feature_description),
            assumption=assumption,
        )
        for category, question_template, assumption in _QUESTION_TEMPLATES
    ]
