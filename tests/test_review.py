"""Tests for the cross-agent review orchestrator."""

from __future__ import annotations

from src.modules.multi_agent.review import (
    ReviewOutputMode,
    ReviewRequest,
    ReviewResult,
    construct_review_prompt,
    create_review,
    format_github_issue,
    format_pr_comment,
    should_skip_review,
)

_SAMPLE_DIFF = """\
diff --git a/src/foo.py b/src/foo.py
--- a/src/foo.py
+++ b/src/foo.py
@@ -1,3 +1,5 @@
+import os
+
 def hello():
-    pass
+    print(os.getcwd())"""


def _make_request(
    diff: str = _SAMPLE_DIFF,
    output_mode: ReviewOutputMode = ReviewOutputMode.PR_COMMENT,
    pr_number: int | None = 42,
) -> ReviewRequest:
    return ReviewRequest(
        issue_title="Add cwd logging",
        issue_body="Print the current working directory in hello().",
        diff=diff,
        review_model="claude-sonnet",
        pr_number=pr_number,
        output_mode=output_mode,
    )


class TestShouldSkipReview:
    def test_empty_string_returns_true(self) -> None:
        assert should_skip_review("") is True

    def test_whitespace_only_returns_true(self) -> None:
        assert should_skip_review("   \n\t  ") is True

    def test_real_diff_returns_false(self) -> None:
        assert should_skip_review(_SAMPLE_DIFF) is False

    def test_single_character_returns_false(self) -> None:
        assert should_skip_review("+") is False


class TestConstructReviewPrompt:
    def test_contains_issue_title(self) -> None:
        prompt = construct_review_prompt("Fix bug", "Description here", _SAMPLE_DIFF)
        assert "## Issue: Fix bug" in prompt

    def test_contains_issue_body(self) -> None:
        prompt = construct_review_prompt("Fix bug", "Description here", _SAMPLE_DIFF)
        assert "Description here" in prompt

    def test_contains_diff_in_code_block(self) -> None:
        prompt = construct_review_prompt("Fix bug", "Body", _SAMPLE_DIFF)
        assert f"```diff\n{_SAMPLE_DIFF}\n```" in prompt

    def test_contains_review_instructions(self) -> None:
        prompt = construct_review_prompt("Fix bug", "Body", _SAMPLE_DIFF)
        assert "## Review Instructions" in prompt
        assert "senior code reviewer" in prompt


class TestCreateReview:
    def test_returns_prompt_for_valid_diff(self) -> None:
        result = create_review(_make_request())
        assert result.skipped is False
        assert "## Issue: Add cwd logging" in result.review_text
        assert _SAMPLE_DIFF in result.review_text

    def test_skips_empty_diff(self) -> None:
        result = create_review(_make_request(diff=""))
        assert result.skipped is True
        assert result.review_text == ""
        assert "Empty diff" in result.reason

    def test_skips_whitespace_only_diff(self) -> None:
        result = create_review(_make_request(diff="  \n  "))
        assert result.skipped is True

    def test_preserves_output_mode_in_request(self) -> None:
        req = _make_request(output_mode=ReviewOutputMode.GITHUB_ISSUE)
        assert req.output_mode == ReviewOutputMode.GITHUB_ISSUE

    def test_default_output_mode_is_pr_comment(self) -> None:
        req = ReviewRequest(issue_title="T", issue_body="B", diff="d", review_model="m")
        assert req.output_mode == ReviewOutputMode.PR_COMMENT


class TestFormatPrComment:
    def test_includes_model_attribution(self) -> None:
        result = ReviewResult(review_text="Looks good.", skipped=False, reason="")
        comment = format_pr_comment(result, "claude-sonnet")
        assert "_Reviewed by `claude-sonnet`_" in comment

    def test_includes_review_text(self) -> None:
        result = ReviewResult(review_text="Found a bug on line 5.", skipped=False, reason="")
        comment = format_pr_comment(result, "claude-sonnet")
        assert "Found a bug on line 5." in comment

    def test_skipped_review_shows_reason(self) -> None:
        result = ReviewResult(review_text="", skipped=True, reason="Empty diff — nothing to review.")
        comment = format_pr_comment(result, "claude-sonnet")
        assert "Review skipped" in comment
        assert "Empty diff" in comment

    def test_skipped_review_does_not_include_attribution(self) -> None:
        result = ReviewResult(review_text="", skipped=True, reason="Empty diff — nothing to review.")
        comment = format_pr_comment(result, "claude-sonnet")
        assert "Reviewed by" not in comment


class TestFormatGithubIssue:
    def test_title_prefixed_with_review(self) -> None:
        result = ReviewResult(review_text="LGTM", skipped=False, reason="")
        title, _ = format_github_issue(result, "Add feature X", "gemini-pro")
        assert title == "Review: Add feature X"

    def test_body_includes_review_text(self) -> None:
        result = ReviewResult(review_text="Needs refactor.", skipped=False, reason="")
        _, body = format_github_issue(result, "Add feature X", "gemini-pro")
        assert "Needs refactor." in body

    def test_body_includes_model_attribution(self) -> None:
        result = ReviewResult(review_text="LGTM", skipped=False, reason="")
        _, body = format_github_issue(result, "T", "gemini-pro")
        assert "_Reviewed by `gemini-pro`_" in body

    def test_skipped_review_body_shows_reason(self) -> None:
        result = ReviewResult(review_text="", skipped=True, reason="Empty diff — nothing to review.")
        _, body = format_github_issue(result, "T", "gemini-pro")
        assert "Review skipped" in body
        assert "Empty diff" in body

    def test_skipped_review_still_has_attribution(self) -> None:
        result = ReviewResult(review_text="", skipped=True, reason="Empty diff — nothing to review.")
        _, body = format_github_issue(result, "T", "gemini-pro")
        assert "_Reviewed by `gemini-pro`_" in body
