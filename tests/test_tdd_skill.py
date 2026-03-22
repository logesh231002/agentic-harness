"""Tests for the TDD skill."""

from __future__ import annotations

import pytest

from src.modules.tdd.tdd_skill import (
    TddError,
    TddPhase,
    TddSession,
    add_failing_test,
    advance_phase,
    get_architecture_review_stub,
    get_testing_rule,
)


class TestTddSessionStart:
    def test_starts_in_red_phase_with_failing_test_name(self) -> None:
        session = TddSession.start("test_login_redirects")

        assert session.phase == TddPhase.RED
        assert session.failing_test == "test_login_redirects"

    def test_raises_on_empty_test_name(self) -> None:
        with pytest.raises(TddError, match="test_name is required"):
            TddSession.start("")

    def test_session_is_immutable(self) -> None:
        session = TddSession.start("test_foo")

        with pytest.raises(AttributeError):
            session.phase = TddPhase.GREEN  # type: ignore[misc]


class TestAdvancePhase:
    def test_red_stays_red_when_test_fails(self) -> None:
        session = TddSession.start("test_foo")

        result = advance_phase(session, test_passed=False)

        assert result.phase == TddPhase.RED
        assert result is session

    def test_red_to_green_when_test_passes(self) -> None:
        session = TddSession.start("test_foo")

        result = advance_phase(session, test_passed=True)

        assert result.phase == TddPhase.GREEN
        assert result.failing_test == "test_foo"

    def test_green_to_refactor_when_test_passes(self) -> None:
        session = TddSession(phase=TddPhase.GREEN, failing_test="test_foo")

        result = advance_phase(session, test_passed=True)

        assert result.phase == TddPhase.REFACTOR

    def test_green_raises_when_test_fails(self) -> None:
        session = TddSession(phase=TddPhase.GREEN, failing_test="test_foo")

        with pytest.raises(TddError, match="GREEN phase"):
            advance_phase(session, test_passed=False)

    def test_refactor_stays_refactor_when_tests_pass(self) -> None:
        session = TddSession(phase=TddPhase.REFACTOR, failing_test="test_foo")

        result = advance_phase(session, test_passed=True)

        assert result.phase == TddPhase.REFACTOR
        assert result is session

    def test_refactor_raises_when_test_fails(self) -> None:
        session = TddSession(phase=TddPhase.REFACTOR, failing_test="test_foo")

        with pytest.raises(TddError, match="REFACTOR phase"):
            advance_phase(session, test_passed=False)

    def test_full_cycle_red_green_refactor(self) -> None:
        session = TddSession.start("test_checkout")

        session = advance_phase(session, test_passed=False)
        assert session.phase == TddPhase.RED

        session = advance_phase(session, test_passed=True)
        assert session.phase == TddPhase.GREEN

        session = advance_phase(session, test_passed=True)
        assert session.phase == TddPhase.REFACTOR


class TestAddFailingTest:
    def test_can_add_new_test_from_refactor_phase(self) -> None:
        session = TddSession(phase=TddPhase.REFACTOR, failing_test="test_old")

        result = add_failing_test(session, "test_new")

        assert result.phase == TddPhase.RED
        assert result.failing_test == "test_new"

    def test_cannot_add_test_during_red_phase(self) -> None:
        session = TddSession.start("test_current")

        with pytest.raises(TddError, match="Cannot add a new failing test"):
            add_failing_test(session, "test_another")

    def test_cannot_add_test_during_green_phase(self) -> None:
        session = TddSession(phase=TddPhase.GREEN, failing_test="test_current")

        with pytest.raises(TddError, match="GREEN phase"):
            add_failing_test(session, "test_another")

    def test_raises_on_empty_test_name(self) -> None:
        session = TddSession(phase=TddPhase.REFACTOR, failing_test="test_old")

        with pytest.raises(TddError, match="test_name is required"):
            add_failing_test(session, "")

    def test_error_message_includes_current_test_name(self) -> None:
        session = TddSession.start("test_login")

        with pytest.raises(TddError, match="test_login"):
            add_failing_test(session, "test_signup")


class TestGetTestingRule:
    def test_rule_matches_test_files(self) -> None:
        rule = get_testing_rule()

        assert "**/*test*.py" in rule.globs

    def test_rule_body_contains_three_constraints(self) -> None:
        rule = get_testing_rule()

        assert "Mock" in rule.body and "Boundaries" in rule.body
        assert "Behavior" in rule.body and "Implementation" in rule.body
        assert "Vertical Slices" in rule.body

    def test_rule_body_forbids_horizontal_slicing(self) -> None:
        rule = get_testing_rule()

        assert "horizontal slicing" in rule.body.lower()

    def test_rule_has_source_path(self) -> None:
        rule = get_testing_rule()

        assert rule.source_path.name == "tdd_skill.py"


class TestGetArchitectureReviewStub:
    def test_stub_mentions_deep_modules(self) -> None:
        stub = get_architecture_review_stub()

        assert "deep module" in stub.lower() or "deepen modules" in stub.lower()

    def test_stub_mentions_shallow_modules(self) -> None:
        stub = get_architecture_review_stub()

        assert "shallow module" in stub.lower()

    def test_stub_is_nonempty_string(self) -> None:
        stub = get_architecture_review_stub()

        assert isinstance(stub, str)
        assert len(stub) > 50
