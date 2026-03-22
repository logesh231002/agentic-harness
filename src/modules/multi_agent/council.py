"""Council mode: chairman synthesis with anonymized multi-model review."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


class CouncilError(Exception):
    """Raised when a council operation fails."""


@dataclass(frozen=True)
class CouncilStep:
    """A single council-worthy step with participating models and chairman prompt."""

    name: str
    models: Sequence[str]
    chairman_prompt: str
    cost_multiplier: float


@dataclass(frozen=True)
class CouncilResponse:
    """A response from a single model in the council."""

    model: str
    content: str


@dataclass(frozen=True)
class CouncilResult:
    """Output of a council run."""

    chairman_output: str
    responses_count: int
    was_single_agent: bool


@dataclass(frozen=True)
class CouncilConfig:
    """Top-level council configuration containing all steps."""

    steps: Sequence[CouncilStep]


# Patterns that reveal model identity — case-insensitive
_MODEL_IDENTITY_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(r"\bI am (Claude|GPT|Gemini|Llama|Mistral|Grok)\b", re.IGNORECASE),
    re.compile(r"\bAs (Claude|GPT|Gemini|Llama|Mistral|Grok)\b", re.IGNORECASE),
    re.compile(r"\b(Claude|GPT-4|GPT-3\.5|Gemini|Llama|Mistral|Grok)\b"),
)

_SIMILARITY_THRESHOLD = 0.85


def is_council_worthy(step: CouncilStep) -> bool:
    """Return True if the step has more than one model configured."""
    return len(step.models) > 1


def get_cost_multiplier(step: CouncilStep) -> float:
    """Return the cost multiplier for a council step."""
    return step.cost_multiplier


def anonymize_response(response: CouncilResponse) -> str:
    """Strip model-identifying language from a response.

    Removes mentions of known model names and self-identification patterns
    so the chairman cannot determine which model produced which response.
    """
    text = response.content
    for pattern in _MODEL_IDENTITY_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def deduplicate_responses(responses: Sequence[str]) -> Sequence[str]:
    """Remove near-duplicate responses using simple similarity comparison.

    Keeps the first occurrence when two responses exceed the similarity threshold.
    """
    if not responses:
        return []

    unique: list[str] = []
    for candidate in responses:
        is_duplicate = False
        for existing in unique:
            ratio = SequenceMatcher(None, candidate, existing).ratio()
            if ratio >= _SIMILARITY_THRESHOLD:
                is_duplicate = True
                break
        if not is_duplicate:
            unique.append(candidate)
    return unique


def build_chairman_prompt(chairman_template: str, anonymized_responses: Sequence[str]) -> str:
    """Construct the chairman synthesis prompt from template and anonymized responses.

    The chairman is instructed to deduplicate, merge related items, and filter noise.
    """
    numbered = "\n\n".join(f"### Response {i + 1}\n{resp}" for i, resp in enumerate(anonymized_responses))
    return (
        f"{chairman_template}\n\n"
        f"## Anonymized Responses\n\n"
        f"{numbered}\n\n"
        f"## Instructions\n\n"
        f"Deduplicate overlapping points, merge related items, and filter noise. "
        f"Produce a single unified synthesis."
    )


def run_council(step: CouncilStep, responses: Sequence[CouncilResponse]) -> CouncilResult:
    """Run the council process: anonymize, deduplicate, build chairman prompt.

    Falls back to single-agent behavior when only one response is provided.
    Pure function — does not call any LLM. The ``chairman_output`` contains
    the prompt that a caller would send to the chairman model.
    """
    if not responses:
        raise CouncilError("Cannot run council with zero responses.")

    if len(responses) == 1:
        return CouncilResult(
            chairman_output=responses[0].content,
            responses_count=1,
            was_single_agent=True,
        )

    anonymized = [anonymize_response(r) for r in responses]
    deduped = deduplicate_responses(anonymized)
    chairman_output = build_chairman_prompt(step.chairman_prompt, deduped)

    return CouncilResult(
        chairman_output=chairman_output,
        responses_count=len(responses),
        was_single_agent=False,
    )


def parse_council_config(config_data: Mapping[str, Any]) -> CouncilConfig:
    """Parse council configuration from a dictionary.

    Expected format::

        {
            "steps": [
                {
                    "name": "planning",
                    "models": ["claude-sonnet", "gpt-4"],
                    "chairman_prompt": "Synthesize the plans.",
                    "cost_multiplier": 2.0
                }
            ]
        }

    Raises :class:`CouncilError` on invalid input.
    """
    raw_steps = config_data.get("steps")
    if not isinstance(raw_steps, list):
        raise CouncilError("Council config must contain a 'steps' list.")

    steps: list[CouncilStep] = []
    for i, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            raise CouncilError(f"Step {i} must be a mapping, got {type(raw).__name__}.")

        missing = {"name", "models", "chairman_prompt", "cost_multiplier"} - set(raw.keys())
        if missing:
            raise CouncilError(f"Step {i} missing required fields: {', '.join(sorted(missing))}.")

        models = raw["models"]
        if not isinstance(models, list) or not all(isinstance(m, str) for m in models):
            raise CouncilError(f"Step {i} 'models' must be a list of strings.")

        cost = raw["cost_multiplier"]
        if not isinstance(cost, int | float):
            raise CouncilError(f"Step {i} 'cost_multiplier' must be a number.")

        steps.append(
            CouncilStep(
                name=raw["name"],
                models=tuple(models),
                chairman_prompt=raw["chairman_prompt"],
                cost_multiplier=float(cost),
            )
        )

    return CouncilConfig(steps=tuple(steps))
