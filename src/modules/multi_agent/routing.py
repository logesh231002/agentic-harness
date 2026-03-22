"""Model routing: parses routing config and selects models for task types."""

from __future__ import annotations

from dataclasses import dataclass

from src.config.schema import ModelRouting, ModelRoutingEntry

_VALID_TASK_TYPES = frozenset({"planning", "implementation", "review", "quick-fix"})

_TASK_TYPE_TO_ATTR: dict[str, str] = {
    "planning": "planning",
    "implementation": "implementation",
    "review": "review",
    "quick-fix": "quick_fix",
}


class RoutingError(Exception):
    """Raised when model routing fails due to invalid config or unavailable models."""


@dataclass(frozen=True)
class ModelSelection:
    """Result of selecting a model for a task type."""

    model: str
    is_fallback: bool


def get_model_for_task(
    routing: ModelRouting,
    task_type: str,
    available_models: list[str] | None = None,
) -> ModelSelection:
    """Select the best available model for a given task type."""
    if task_type not in _VALID_TASK_TYPES:
        raise RoutingError(f"Unknown task type {task_type!r}. Valid types: {', '.join(sorted(_VALID_TASK_TYPES))}")

    attr_name = _TASK_TYPE_TO_ATTR[task_type]
    entry: ModelRoutingEntry = getattr(routing, attr_name)

    if available_models is None:
        return ModelSelection(model=entry.primary, is_fallback=False)

    if entry.primary in available_models:
        return ModelSelection(model=entry.primary, is_fallback=False)

    if entry.fallback in available_models:
        return ModelSelection(model=entry.fallback, is_fallback=True)

    raise RoutingError(
        f"No available model for task type {task_type!r}: "
        f"primary {entry.primary!r} and fallback {entry.fallback!r} are both unavailable. "
        f"Available: {available_models}"
    )
