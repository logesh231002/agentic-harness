"""Tests for the postmortem skill."""

from __future__ import annotations

from src.modules.evolution.postmortem import (
    classify_file,
    create_postmortem,
    format_postmortem_md,
    generate_questions,
)


class TestGenerateQuestions:
    def test_returns_three_questions(self) -> None:
        questions = generate_questions()

        assert len(questions) == 3

    def test_question_categories(self) -> None:
        questions = generate_questions()
        categories = [q.category for q in questions]

        assert categories == ["bug_class", "preventive_measure", "minimum_addition"]


class TestClassifyFile:
    def test_rule_files(self) -> None:
        assert classify_file(".claude/rules/foo.rule.md") == "rule"

    def test_context_files(self) -> None:
        assert classify_file("CLAUDE.md") == "context"
        assert classify_file("src/modules/foo/DECISIONS.md") == "context"

    def test_test_files(self) -> None:
        assert classify_file("tests/test_foo.py") == "test"

    def test_product_files(self) -> None:
        assert classify_file("src/modules/foo/bar.py") == "product"


class TestCreatePostmortem:
    def test_produces_result_with_all_fields(self) -> None:
        result = create_postmortem(
            bug_description="Off-by-one in loop",
            affected_files=["src/main.py"],
            answers={"preventive_measure": "Add a boundary check"},
        )

        assert len(result.questions) == 3
        assert isinstance(result.proposed_edits, list)
        assert isinstance(result.summary, str)
        assert len(result.summary) > 0

    def test_proposes_rule_edit_when_rule_mentioned(self) -> None:
        result = create_postmortem(
            bug_description="Missing validation",
            affected_files=["src/handler.py"],
            answers={"preventive_measure": "Add a rule to always validate input"},
        )

        rule_edits = [e for e in result.proposed_edits if e.file_type == "rule"]
        assert len(rule_edits) >= 1

    def test_proposes_test_edit_when_test_mentioned(self) -> None:
        result = create_postmortem(
            bug_description="Null pointer",
            affected_files=["src/service.py"],
            answers={"preventive_measure": "Add a test for null inputs"},
        )

        test_edits = [e for e in result.proposed_edits if e.file_type == "test"]
        assert len(test_edits) >= 1


class TestFormatPostmortemMd:
    def test_includes_bug_description(self) -> None:
        result = create_postmortem(
            bug_description="Race condition in queue",
            affected_files=["src/queue.py"],
            answers={"preventive_measure": "Add a rule for thread safety"},
        )
        md = format_postmortem_md(result)

        assert "Race condition in queue" in md
