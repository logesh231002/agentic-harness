"""Tests for the model routing config parser."""

from __future__ import annotations

import pytest

from src.config.schema import ModelRouting
from src.modules.multi_agent.routing import ModelSelection, RoutingError, get_model_for_task


def _make_routing() -> ModelRouting:
    return ModelRouting.model_validate(
        {
            "planning": {"primary": "claude-opus", "fallback": "claude-sonnet"},
            "implementation": {"primary": "claude-sonnet", "fallback": "claude-haiku"},
            "review": {"primary": "gemini-pro", "fallback": "claude-sonnet"},
            "quick-fix": {"primary": "claude-haiku", "fallback": "claude-sonnet"},
        }
    )


class TestGetModelForTask:
    def test_returns_primary_for_planning(self) -> None:
        result = get_model_for_task(_make_routing(), "planning")
        assert result == ModelSelection(model="claude-opus", is_fallback=False)

    def test_returns_primary_for_implementation(self) -> None:
        result = get_model_for_task(_make_routing(), "implementation")
        assert result == ModelSelection(model="claude-sonnet", is_fallback=False)

    def test_returns_primary_for_review(self) -> None:
        result = get_model_for_task(_make_routing(), "review")
        assert result == ModelSelection(model="gemini-pro", is_fallback=False)

    def test_returns_primary_for_quick_fix(self) -> None:
        result = get_model_for_task(_make_routing(), "quick-fix")
        assert result == ModelSelection(model="claude-haiku", is_fallback=False)

    def test_raises_on_unknown_task_type(self) -> None:
        with pytest.raises(RoutingError, match="Unknown task type 'unknown'"):
            get_model_for_task(_make_routing(), "unknown")


class TestFallbackBehavior:
    def test_uses_fallback_when_primary_unavailable(self) -> None:
        result = get_model_for_task(_make_routing(), "planning", available_models=["claude-sonnet"])
        assert result == ModelSelection(model="claude-sonnet", is_fallback=True)

    def test_uses_primary_when_both_available(self) -> None:
        result = get_model_for_task(_make_routing(), "planning", available_models=["claude-opus", "claude-sonnet"])
        assert result == ModelSelection(model="claude-opus", is_fallback=False)

    def test_raises_when_neither_available(self) -> None:
        with pytest.raises(RoutingError, match="No available model"):
            get_model_for_task(_make_routing(), "planning", available_models=["gemini-flash"])

    def test_none_available_models_assumes_all_available(self) -> None:
        result = get_model_for_task(_make_routing(), "planning", available_models=None)
        assert result == ModelSelection(model="claude-opus", is_fallback=False)
