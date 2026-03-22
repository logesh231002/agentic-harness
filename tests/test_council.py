"""Tests for the council mode orchestrator."""

from __future__ import annotations

import pytest

from src.modules.multi_agent.council import (
    CouncilConfig,
    CouncilError,
    CouncilResponse,
    CouncilResult,
    CouncilStep,
    anonymize_response,
    build_chairman_prompt,
    deduplicate_responses,
    get_cost_multiplier,
    is_council_worthy,
    parse_council_config,
    run_council,
)


def _make_step(
    name: str = "planning",
    models: list[str] | None = None,
    chairman_prompt: str = "Synthesize the plans below.",
    cost_multiplier: float = 2.0,
) -> CouncilStep:
    return CouncilStep(
        name=name,
        models=models if models is not None else ["claude-sonnet", "gpt-4"],
        chairman_prompt=chairman_prompt,
        cost_multiplier=cost_multiplier,
    )


def _make_response(model: str = "claude-sonnet", content: str = "Use dependency injection.") -> CouncilResponse:
    return CouncilResponse(model=model, content=content)


class TestIsCouncilWorthy:
    def test_multiple_models_returns_true(self) -> None:
        step = _make_step(models=["claude-sonnet", "gpt-4"])
        assert is_council_worthy(step) is True

    def test_single_model_returns_false(self) -> None:
        step = _make_step(models=["claude-sonnet"])
        assert is_council_worthy(step) is False

    def test_empty_models_returns_false(self) -> None:
        step = _make_step(models=[])
        assert is_council_worthy(step) is False

    def test_three_models_returns_true(self) -> None:
        step = _make_step(models=["claude-sonnet", "gpt-4", "gemini-pro"])
        assert is_council_worthy(step) is True


class TestAnonymizeResponse:
    def test_strips_i_am_claude(self) -> None:
        resp = _make_response(content="I am Claude and I suggest refactoring.")
        result = anonymize_response(resp)
        assert "Claude" not in result
        assert "[REDACTED]" in result

    def test_strips_as_gpt(self) -> None:
        resp = _make_response(content="As GPT-4, I recommend testing.")
        result = anonymize_response(resp)
        assert "GPT-4" not in result

    def test_strips_bare_model_name(self) -> None:
        resp = _make_response(content="Gemini suggests using async patterns.")
        result = anonymize_response(resp)
        assert "Gemini" not in result

    def test_preserves_non_model_content(self) -> None:
        resp = _make_response(content="Use dependency injection for testability.")
        result = anonymize_response(resp)
        assert result == "Use dependency injection for testability."

    def test_case_insensitive_matching(self) -> None:
        resp = _make_response(content="I am claude and this is my answer.")
        result = anonymize_response(resp)
        assert "claude" not in result


class TestDeduplicateResponses:
    def test_empty_list_returns_empty(self) -> None:
        assert deduplicate_responses([]) == []

    def test_unique_responses_preserved(self) -> None:
        responses = ["Use DI for testing.", "Prefer composition over inheritance."]
        result = deduplicate_responses(responses)
        assert len(result) == 2

    def test_identical_responses_deduplicated(self) -> None:
        responses = ["Use dependency injection.", "Use dependency injection."]
        result = deduplicate_responses(responses)
        assert len(result) == 1
        assert result[0] == "Use dependency injection."

    def test_near_duplicate_removed(self) -> None:
        responses = [
            "Use dependency injection for better testability.",
            "Use dependency injection for better testability!",
        ]
        result = deduplicate_responses(responses)
        assert len(result) == 1

    def test_different_responses_kept(self) -> None:
        responses = [
            "Implement caching at the service layer.",
            "Add comprehensive error handling throughout.",
        ]
        result = deduplicate_responses(responses)
        assert len(result) == 2

    def test_first_occurrence_kept(self) -> None:
        responses = ["First version of the answer.", "First version of the answer."]
        result = deduplicate_responses(responses)
        assert result[0] == "First version of the answer."


class TestBuildChairmanPrompt:
    def test_includes_chairman_template(self) -> None:
        prompt = build_chairman_prompt("You are the chairman.", ["Response A."])
        assert "You are the chairman." in prompt

    def test_includes_all_responses_numbered(self) -> None:
        prompt = build_chairman_prompt("Template.", ["Alpha.", "Beta."])
        assert "### Response 1" in prompt
        assert "Alpha." in prompt
        assert "### Response 2" in prompt
        assert "Beta." in prompt

    def test_includes_synthesis_instructions(self) -> None:
        prompt = build_chairman_prompt("Template.", ["One."])
        assert "Deduplicate" in prompt
        assert "merge" in prompt

    def test_single_response_still_formatted(self) -> None:
        prompt = build_chairman_prompt("Template.", ["Solo response."])
        assert "### Response 1" in prompt
        assert "Solo response." in prompt


class TestRunCouncil:
    def test_single_response_returns_content_directly(self) -> None:
        step = _make_step()
        responses = [_make_response(content="Solo answer.")]
        result = run_council(step, responses)
        assert result.chairman_output == "Solo answer."
        assert result.responses_count == 1
        assert result.was_single_agent is True

    def test_multiple_responses_produces_chairman_prompt(self) -> None:
        step = _make_step(chairman_prompt="Synthesize these.")
        responses = [
            _make_response(model="claude-sonnet", content="Use DI."),
            _make_response(model="gpt-4", content="Prefer composition."),
        ]
        result = run_council(step, responses)
        assert result.was_single_agent is False
        assert result.responses_count == 2
        assert "Synthesize these." in result.chairman_output
        assert "### Response 1" in result.chairman_output

    def test_anonymizes_model_names_in_output(self) -> None:
        step = _make_step()
        responses = [
            _make_response(model="claude-sonnet", content="I am Claude and I suggest X."),
            _make_response(model="gpt-4", content="As GPT-4, I suggest Y."),
        ]
        result = run_council(step, responses)
        assert "Claude" not in result.chairman_output
        assert "GPT-4" not in result.chairman_output

    def test_deduplicates_near_identical_responses(self) -> None:
        step = _make_step()
        responses = [
            _make_response(model="claude-sonnet", content="Use dependency injection."),
            _make_response(model="gpt-4", content="Use dependency injection."),
        ]
        result = run_council(step, responses)
        assert result.chairman_output.count("### Response") == 1

    def test_zero_responses_raises_error(self) -> None:
        step = _make_step()
        with pytest.raises(CouncilError, match="zero responses"):
            run_council(step, [])

    def test_result_is_frozen_dataclass(self) -> None:
        step = _make_step()
        responses = [_make_response()]
        result = run_council(step, responses)
        assert isinstance(result, CouncilResult)
        with pytest.raises(AttributeError):
            result.chairman_output = "modified"  # type: ignore[misc]


class TestParseCouncilConfig:
    def test_parses_valid_config(self) -> None:
        data = {
            "steps": [
                {
                    "name": "planning",
                    "models": ["claude-sonnet", "gpt-4"],
                    "chairman_prompt": "Synthesize.",
                    "cost_multiplier": 2.0,
                }
            ]
        }
        config = parse_council_config(data)
        assert isinstance(config, CouncilConfig)
        assert len(config.steps) == 1
        assert config.steps[0].name == "planning"

    def test_parses_multiple_steps(self) -> None:
        data = {
            "steps": [
                {"name": "planning", "models": ["a"], "chairman_prompt": "P", "cost_multiplier": 1.0},
                {"name": "review", "models": ["b", "c"], "chairman_prompt": "R", "cost_multiplier": 3.0},
            ]
        }
        config = parse_council_config(data)
        assert len(config.steps) == 2
        assert config.steps[1].cost_multiplier == 3.0

    def test_missing_steps_key_raises_error(self) -> None:
        with pytest.raises(CouncilError, match="'steps' list"):
            parse_council_config({})

    def test_steps_not_a_list_raises_error(self) -> None:
        with pytest.raises(CouncilError, match="'steps' list"):
            parse_council_config({"steps": "not-a-list"})

    def test_step_not_a_dict_raises_error(self) -> None:
        with pytest.raises(CouncilError, match="must be a mapping"):
            parse_council_config({"steps": ["not-a-dict"]})

    def test_missing_required_field_raises_error(self) -> None:
        data = {"steps": [{"name": "planning", "models": ["a"]}]}
        with pytest.raises(CouncilError, match="missing required fields"):
            parse_council_config(data)

    def test_models_not_list_of_strings_raises_error(self) -> None:
        data = {"steps": [{"name": "p", "models": [1, 2], "chairman_prompt": "P", "cost_multiplier": 1.0}]}
        with pytest.raises(CouncilError, match="list of strings"):
            parse_council_config(data)

    def test_cost_multiplier_not_number_raises_error(self) -> None:
        data = {"steps": [{"name": "p", "models": ["a"], "chairman_prompt": "P", "cost_multiplier": "high"}]}
        with pytest.raises(CouncilError, match="must be a number"):
            parse_council_config(data)

    def test_integer_cost_multiplier_accepted(self) -> None:
        data = {"steps": [{"name": "p", "models": ["a"], "chairman_prompt": "P", "cost_multiplier": 3}]}
        config = parse_council_config(data)
        assert config.steps[0].cost_multiplier == 3.0


class TestCostMultiplier:
    def test_returns_configured_value(self) -> None:
        step = _make_step(cost_multiplier=2.5)
        assert get_cost_multiplier(step) == 2.5

    def test_returns_integer_cost_as_float(self) -> None:
        step = _make_step(cost_multiplier=3.0)
        assert get_cost_multiplier(step) == 3.0
        assert isinstance(get_cost_multiplier(step), float)

    def test_default_step_cost(self) -> None:
        step = _make_step()
        assert get_cost_multiplier(step) == 2.0
