"""Postmortem skill: analyzes bugs and proposes AI-layer improvements to prevent recurrence."""

from __future__ import annotations

from dataclasses import dataclass


class PostmortemError(Exception):
    """Raised when the postmortem process encounters an unrecoverable error."""


@dataclass(frozen=True)
class PostmortemQuestion:
    """A diagnostic question for the postmortem."""

    category: str
    question: str


@dataclass(frozen=True)
class ProposedEdit:
    """A proposed file change to prevent bug recurrence."""

    file_path: str
    file_type: str
    description: str
    content: str


@dataclass(frozen=True)
class PostmortemResult:
    """The complete result of a postmortem analysis."""

    questions: list[PostmortemQuestion]
    proposed_edits: list[ProposedEdit]
    summary: str


def generate_questions() -> list[PostmortemQuestion]:
    """Return the 3 standard postmortem diagnostic questions."""
    return [
        PostmortemQuestion(
            category="bug_class",
            question="What class of bug is this? (logic error, missing validation, wrong assumption, etc.)",
        ),
        PostmortemQuestion(
            category="preventive_measure",
            question="What rule, context, or test would have prevented this bug?",
        ),
        PostmortemQuestion(
            category="minimum_addition",
            question="What is the minimum addition to the AI layer to prevent this bug class?",
        ),
    ]


def classify_file(file_path: str) -> str:
    """Classify a file path into rule, context, test, or product."""
    if file_path.startswith(".claude/") or file_path.endswith(".rule.md"):
        return "rule"
    basename = file_path.rsplit("/", maxsplit=1)[-1] if "/" in file_path else file_path
    if basename in ("DECISIONS.md", "CLAUDE.md", "harness.config.yaml"):
        return "context"
    if basename.startswith("test_") and basename.endswith(".py"):
        return "test"
    if basename.endswith("_test.py"):
        return "test"
    return "product"


def create_postmortem(
    bug_description: str,
    affected_files: list[str],
    answers: dict[str, str],
) -> PostmortemResult:
    """Create a postmortem analysis from bug info and diagnostic answers.

    Classifies each affected file, generates proposed edits based on the
    preventive_measure answer, and produces a markdown summary.
    """
    questions = generate_questions()
    proposed_edits: list[ProposedEdit] = []

    preventive = answers.get("preventive_measure", "").lower()

    if "rule" in preventive:
        proposed_edits.append(
            ProposedEdit(
                file_path=".claude/rules/prevent-bug.rule.md",
                file_type="rule",
                description="Add a rule to prevent this bug class",
                content=answers.get("preventive_measure", ""),
            )
        )

    if "test" in preventive:
        proposed_edits.append(
            ProposedEdit(
                file_path="tests/test_prevent_bug.py",
                file_type="test",
                description="Add a test case to catch this bug class",
                content=answers.get("preventive_measure", ""),
            )
        )

    if "context" in preventive:
        proposed_edits.append(
            ProposedEdit(
                file_path="CLAUDE.md",
                file_type="context",
                description="Update CLAUDE.md with context to prevent this bug class",
                content=answers.get("preventive_measure", ""),
            )
        )

    classified_files = [(f, classify_file(f)) for f in affected_files]

    file_list = "\n".join(f"- `{f}` ({t})" for f, t in classified_files)
    edit_list = "\n".join(f"- `{e.file_path}` ({e.file_type}): {e.description}" for e in proposed_edits)

    summary = (
        f"## Bug Description\n\n{bug_description}\n\n"
        f"## Classification\n\n{file_list}\n\n"
        f"## Proposed Changes\n\n{edit_list}"
    )

    return PostmortemResult(
        questions=questions,
        proposed_edits=proposed_edits,
        summary=summary,
    )


def format_postmortem_md(result: PostmortemResult) -> str:
    """Format a PostmortemResult as readable markdown."""
    sections: list[str] = ["# Postmortem Report\n"]

    sections.append("## Questions\n")
    for q in result.questions:
        sections.append(f"- **{q.category}**: {q.question}")

    sections.append("\n## Proposed Edits\n")
    for edit in result.proposed_edits:
        sections.append(f"### `{edit.file_path}` ({edit.file_type})\n")
        sections.append(f"{edit.description}\n")
        sections.append(f"```\n{edit.content}\n```\n")

    sections.append(f"## Summary\n\n{result.summary}")

    return "\n".join(sections)
