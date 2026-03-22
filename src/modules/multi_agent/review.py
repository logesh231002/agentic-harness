"""Cross-agent review orchestrator: constructs review prompts and formats output."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReviewOutputMode(Enum):
    """Where to post the review output."""

    PR_COMMENT = "pr_comment"
    GITHUB_ISSUE = "github_issue"


class ReviewError(Exception):
    """Raised when a review operation fails."""


@dataclass(frozen=True)
class ReviewRequest:
    """Input for a cross-agent review."""

    issue_title: str
    issue_body: str
    diff: str
    review_model: str
    pr_number: int | None = None
    output_mode: ReviewOutputMode = ReviewOutputMode.PR_COMMENT


@dataclass(frozen=True)
class ReviewResult:
    """Output of a cross-agent review."""

    review_text: str
    skipped: bool
    reason: str


_REVIEW_INSTRUCTIONS = """\
You are a senior code reviewer. Review the diff below against the original issue spec.

Focus on:
- Correctness: Does the implementation match the spec?
- Edge cases: Are failure modes handled?
- Style: Is the code clean and idiomatic?
- Security: Any obvious vulnerabilities?

Be constructive. If the code looks good, say so briefly."""


def should_skip_review(diff: str) -> bool:
    """Return True if *diff* is empty or whitespace-only."""
    return not diff.strip()


def construct_review_prompt(issue_title: str, issue_body: str, diff: str) -> str:
    """Build the review prompt with issue spec + diff + review instructions."""
    return (
        f"## Issue: {issue_title}\n\n"
        f"{issue_body}\n\n"
        f"## Diff\n\n"
        f"```diff\n{diff}\n```\n\n"
        f"## Review Instructions\n\n"
        f"{_REVIEW_INSTRUCTIONS}"
    )


def create_review(request: ReviewRequest) -> ReviewResult:
    """Check for empty diff, construct prompt, return result. Pure — does not call any LLM."""
    if should_skip_review(request.diff):
        return ReviewResult(review_text="", skipped=True, reason="Empty diff — nothing to review.")

    prompt = construct_review_prompt(request.issue_title, request.issue_body, request.diff)
    return ReviewResult(review_text=prompt, skipped=False, reason="Review prompt constructed.")


def format_pr_comment(review_result: ReviewResult, review_model: str) -> str:
    """Format a review result as a PR comment with model attribution."""
    if review_result.skipped:
        return f"_Review skipped: {review_result.reason}_"

    return f"{review_result.review_text}\n\n---\n_Reviewed by `{review_model}`_"


def format_github_issue(review_result: ReviewResult, issue_title: str, review_model: str) -> tuple[str, str]:
    """Format a review result as a new GitHub issue. Returns ``(title, body)``."""
    title = f"Review: {issue_title}"

    if review_result.skipped:
        body = f"_Review skipped: {review_result.reason}_\n\n---\n_Reviewed by `{review_model}`_"
    else:
        body = f"{review_result.review_text}\n\n---\n_Reviewed by `{review_model}`_"

    return title, body
