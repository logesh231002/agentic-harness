"""Tests for the planning pipeline: grill, prd, issues, plan_feature."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.modules.planning.grill import GrillError, generate_grill_questions
from src.modules.planning.issues import (
    IssueClassificationError,
    IssueLabel,
    PlannedIssue,
    classify_issue,
    extract_issues_from_prd,
    get_blocking_order,
)
from src.modules.planning.plan_feature import PlanError, create_plan, save_plan
from src.modules.planning.prd import PrdError, generate_prd


class TestGrillQuestions:
    def test_generates_at_least_five_questions(self) -> None:
        questions = generate_grill_questions("user authentication")

        assert len(questions) >= 5

    def test_questions_span_multiple_categories(self) -> None:
        questions = generate_grill_questions("user authentication")
        categories = {q.category for q in questions}

        assert len(categories) >= 3

    def test_questions_contain_feature_description(self) -> None:
        questions = generate_grill_questions("dark mode toggle")

        assert all("dark mode toggle" in q.question for q in questions)

    def test_each_question_has_assumption(self) -> None:
        questions = generate_grill_questions("file upload")

        assert all(len(q.assumption) > 0 for q in questions)

    def test_empty_description_raises_grill_error(self) -> None:
        with pytest.raises(GrillError):
            generate_grill_questions("")

    def test_whitespace_only_description_raises_grill_error(self) -> None:
        with pytest.raises(GrillError):
            generate_grill_questions("   ")


class TestPrdGeneration:
    def test_prd_has_all_required_sections(self) -> None:
        prd = generate_prd("Auth System", [("What scope?", "Login only")])
        section_titles = [s.title for s in prd.sections]

        assert "Overview" in section_titles
        assert "User Stories" in section_titles
        assert "Acceptance Criteria" in section_titles
        assert "Non-Goals" in section_titles
        assert "Dependencies" in section_titles

    def test_prd_title_matches_input(self) -> None:
        prd = generate_prd("Auth System", [("Q?", "A")])

        assert prd.title == "Auth System"

    def test_raw_md_contains_title(self) -> None:
        prd = generate_prd("Auth System", [("Q?", "A")])

        assert "Auth System" in prd.raw_md

    def test_raw_md_is_valid_markdown_with_headers(self) -> None:
        prd = generate_prd("Auth System", [("Q?", "A")])

        assert prd.raw_md.startswith("# PRD:")
        assert "## Overview" in prd.raw_md

    def test_empty_title_raises_prd_error(self) -> None:
        with pytest.raises(PrdError):
            generate_prd("", [("Q?", "A")])

    def test_no_answers_raises_prd_error(self) -> None:
        with pytest.raises(PrdError):
            generate_prd("Auth System", [])


class TestIssueClassification:
    def test_automation_task_classified_as_afk(self) -> None:
        label = classify_issue("Add unit tests", "Write pytest tests for module")

        assert label == IssueLabel.AFK

    def test_design_task_classified_as_hitl(self) -> None:
        label = classify_issue("Design the API", "Need to design the REST API")

        assert label == IssueLabel.HITL

    def test_review_task_classified_as_hitl(self) -> None:
        label = classify_issue("Code review", "Review the implementation")

        assert label == IssueLabel.HITL

    def test_ux_task_classified_as_hitl(self) -> None:
        label = classify_issue("UX improvements", "Improve user flow")

        assert label == IssueLabel.HITL

    def test_empty_title_raises_error(self) -> None:
        with pytest.raises(IssueClassificationError):
            classify_issue("", "")

    def test_extract_issues_from_prd_includes_scaffold(self) -> None:
        prd = generate_prd("Auth", [("What scope?", "Login flow")])
        issues = extract_issues_from_prd(prd)

        assert len(issues) >= 2
        assert "Scaffold" in issues[0].title

    def test_extract_issues_scaffold_has_no_blockers(self) -> None:
        prd = generate_prd("Auth", [("What scope?", "Login flow")])
        issues = extract_issues_from_prd(prd)

        assert list(issues[0].blocked_by) == []

    def test_extract_issues_subsequent_blocked_by_scaffold(self) -> None:
        prd = generate_prd("Auth", [("What scope?", "Login flow")])
        issues = extract_issues_from_prd(prd)

        for issue in list(issues)[1:]:
            assert 0 in list(issue.blocked_by)


class TestBlockingOrder:
    def test_scaffold_comes_first(self) -> None:
        prd = generate_prd("Auth", [("What scope?", "Login flow")])
        issues = extract_issues_from_prd(prd)
        order = get_blocking_order(issues)

        assert order[0] == 0

    def test_all_issues_included_in_order(self) -> None:
        prd = generate_prd("Auth", [("What scope?", "Login flow")])
        issues = extract_issues_from_prd(prd)
        order = get_blocking_order(issues)

        assert sorted(order) == list(range(len(issues)))

    def test_blockers_appear_before_dependents(self) -> None:
        issues = [
            PlannedIssue(title="Setup", body="scaffold", label=IssueLabel.AFK, blocked_by=[]),
            PlannedIssue(title="Build", body="code", label=IssueLabel.AFK, blocked_by=[0]),
            PlannedIssue(title="Test", body="verify", label=IssueLabel.AFK, blocked_by=[1]),
        ]
        order = get_blocking_order(issues)

        assert order.index(0) < order.index(1)
        assert order.index(1) < order.index(2)

    def test_independent_issues_all_scheduled(self) -> None:
        issues = [
            PlannedIssue(title="A", body="a", label=IssueLabel.AFK, blocked_by=[]),
            PlannedIssue(title="B", body="b", label=IssueLabel.AFK, blocked_by=[]),
            PlannedIssue(title="C", body="c", label=IssueLabel.AFK, blocked_by=[]),
        ]
        order = get_blocking_order(issues)

        assert sorted(order) == [0, 1, 2]


class TestPlanFeature:
    def test_plan_has_correct_issue_number(self) -> None:
        plan = create_plan(42, "Add logging", "Add structured logging to service")

        assert plan.issue_number == 42

    def test_plan_has_tasks(self) -> None:
        plan = create_plan(1, "Add logging", "Add structured logging")

        assert len(plan.tasks) >= 3

    def test_plan_tasks_reference_issue(self) -> None:
        plan = create_plan(7, "Fix bug", "Null pointer in handler")

        assert any("#7" in t or "Fix bug" in t for t in plan.tasks)

    def test_plan_has_validation_strategy(self) -> None:
        plan = create_plan(1, "Add feature", "New feature body")

        assert len(plan.validation_strategy) > 0

    def test_plan_raw_md_is_valid_markdown(self) -> None:
        plan = create_plan(1, "Add feature", "New feature body")

        assert plan.raw_md.startswith("# Plan:")
        assert "## Tasks" in plan.raw_md
        assert "## Validation Strategy" in plan.raw_md

    def test_empty_title_raises_plan_error(self) -> None:
        with pytest.raises(PlanError):
            create_plan(1, "", "body")

    def test_non_positive_issue_number_raises_plan_error(self) -> None:
        with pytest.raises(PlanError):
            create_plan(0, "Title", "body")

    def test_plan_extracts_checklist_items_from_body(self) -> None:
        plan = create_plan(1, "Setup", "- [ ] Install deps\n- [x] Create structure")

        task_text = " ".join(plan.tasks)
        assert "Install deps" in task_text
        assert "Create structure" in task_text


class TestSavePlan:
    def test_saves_plan_to_correct_path(self, tmp_path: Path) -> None:
        plan = create_plan(42, "Add logging", "body")
        result = save_plan(plan, tmp_path / "plans")

        assert result == tmp_path / "plans" / "42.md"
        assert result.exists()

    def test_saved_file_contains_raw_md(self, tmp_path: Path) -> None:
        plan = create_plan(5, "Fix bug", "body")
        result = save_plan(plan, tmp_path / "plans")

        content = result.read_text(encoding="utf-8")
        assert content == plan.raw_md

    def test_creates_nested_directory(self, tmp_path: Path) -> None:
        plan = create_plan(1, "Task", "body")
        nested = tmp_path / "deep" / "nested" / "plans"
        result = save_plan(plan, nested)

        assert result.exists()
        assert nested.is_dir()
