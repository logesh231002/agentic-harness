"""Tests for the harness configuration schema."""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.config.schema import (
    ConfigError,
    CouncilTier,
    HarnessConfig,
    load_config,
)

FIXTURES_DIR = Path(__file__).parent.parent / "src" / "config" / "fixtures"


def _valid_config_dict() -> dict[str, Any]:
    """Return a valid config dictionary for testing."""
    return {
        "modelRouting": {
            "planning": {"primary": "claude-opus", "fallback": "claude-sonnet"},
            "implementation": {"primary": "claude-sonnet", "fallback": "claude-haiku"},
            "review": {"primary": "gemini-pro", "fallback": "claude-sonnet"},
            "quick-fix": {"primary": "claude-haiku", "fallback": "claude-sonnet"},
        },
        "councilTiers": {
            "grill-me": {"tier": "council-worthy", "costMultiplier": 4},
            "todos": {"tier": "single-agent-sufficient", "costMultiplier": 1},
        },
        "tournamentSizes": {"full": 3, "pair": 2, "solo": 1, "turnsPerAgent": 3},
        "notifications": {"terminalBell": True},
        "stopHook": {"enabled": True, "autoCommit": True, "autoFix": True},
        "validationThresholds": {"maxLineLength": 120, "maxCyclomaticComplexity": 10},
    }


class TestHarnessConfigSchema:
    """Tests for HarnessConfig Pydantic model."""

    def test_parses_valid_config(self) -> None:
        config = HarnessConfig.model_validate(_valid_config_dict())
        assert config.model_routing.planning.primary == "claude-opus"
        assert config.council_tiers["grill-me"].tier == CouncilTier.COUNCIL_WORTHY
        assert config.tournament_sizes.full == 3

    def test_applies_defaults_for_optional_sections(self) -> None:
        data = _valid_config_dict()
        minimal = {
            "modelRouting": data["modelRouting"],
            "councilTiers": data["councilTiers"],
        }
        config = HarnessConfig.model_validate(minimal)
        assert config.notifications.terminal_bell is True
        assert config.stop_hook.enabled is True
        assert config.tournament_sizes.full == 3
        assert config.validation_thresholds.max_line_length == 120

    def test_rejects_missing_required_fields(self) -> None:
        incomplete = {"modelRouting": _valid_config_dict()["modelRouting"]}
        with pytest.raises(ValidationError) as exc_info:
            HarnessConfig.model_validate(incomplete)
        assert len(exc_info.value.errors()) > 0

    def test_rejects_extra_fields(self) -> None:
        """extra='forbid' catches typos in config keys."""
        data = _valid_config_dict()
        data["modelRouting"]["invalid-task"] = {"primary": "x", "fallback": "y"}
        with pytest.raises(ValidationError):
            HarnessConfig.model_validate(data)

    def test_rejects_negative_cost_multiplier(self) -> None:
        data = _valid_config_dict()
        data["councilTiers"] = {"test": {"tier": "council-worthy", "costMultiplier": -1}}
        with pytest.raises(ValidationError):
            HarnessConfig.model_validate(data)

    def test_rejects_zero_cost_multiplier(self) -> None:
        data = _valid_config_dict()
        data["councilTiers"] = {"test": {"tier": "council-worthy", "costMultiplier": 0}}
        with pytest.raises(ValidationError):
            HarnessConfig.model_validate(data)

    def test_rejects_invalid_council_tier_value(self) -> None:
        data = _valid_config_dict()
        data["councilTiers"] = {"test": {"tier": "invalid-tier", "costMultiplier": 1}}
        with pytest.raises(ValidationError):
            HarnessConfig.model_validate(data)

    def test_rejects_empty_council_tiers(self) -> None:
        data = _valid_config_dict()
        data["councilTiers"] = {}
        with pytest.raises(ValidationError):
            HarnessConfig.model_validate(data)

    def test_rejects_empty_model_name(self) -> None:
        """Model names must be non-empty strings."""
        data = _valid_config_dict()
        data["modelRouting"]["planning"] = {"primary": "", "fallback": "claude-sonnet"}
        with pytest.raises(ValidationError):
            HarnessConfig.model_validate(data)

    def test_rejects_invalid_webhook_url(self) -> None:
        """webhook_url must start with http:// or https://."""
        data = _valid_config_dict()
        data["notifications"] = {"webhookUrl": "not-a-url"}
        with pytest.raises(ValidationError):
            HarnessConfig.model_validate(data)

    def test_accepts_valid_webhook_url(self) -> None:
        data = _valid_config_dict()
        data["notifications"] = {"webhookUrl": "https://hooks.slack.com/services/xxx"}
        config = HarnessConfig.model_validate(data)
        assert config.notifications.webhook_url == "https://hooks.slack.com/services/xxx"

    def test_rejects_zero_pair_size(self) -> None:
        """pair must be >= 1."""
        data = _valid_config_dict()
        data["tournamentSizes"] = {"full": 3, "pair": 0, "solo": 1, "turnsPerAgent": 3}
        with pytest.raises(ValidationError):
            HarnessConfig.model_validate(data)

    def test_config_is_frozen(self) -> None:
        """Config objects are immutable after creation."""
        config = HarnessConfig.model_validate(_valid_config_dict())
        with pytest.raises(ValidationError):
            config.stop_hook = None  # type: ignore[assignment]


class TestLoadConfig:
    """Tests for the load_config function."""

    def test_loads_valid_yaml_fixture(self) -> None:
        config = load_config(FIXTURES_DIR / "test-config.yaml")
        assert config.model_routing.review.primary == "gemini-pro"
        assert config.stop_hook.auto_commit is True

    def test_raises_config_error_for_missing_file(self) -> None:
        with pytest.raises(ConfigError, match="Config file not found"):
            load_config("/nonexistent/path.yaml")

    def test_raises_config_error_for_invalid_config(self) -> None:
        with pytest.raises(ConfigError, match="Invalid harness config"):
            load_config(FIXTURES_DIR / "invalid-config.yaml")

    def test_loads_default_harness_config(self) -> None:
        """Smoke test: the shipped harness.config.yaml parses correctly."""
        project_root = Path(__file__).parent.parent
        config = load_config(project_root / "harness.config.yaml")
        assert config.model_routing.planning.primary == "claude-opus"
        assert config.council_tiers["architecture"].cost_multiplier == 5
        assert config.council_tiers["architecture"].tier == CouncilTier.COUNCIL_WORTHY

    def test_raises_config_error_for_malformed_yaml(self, tmp_path: Path) -> None:
        """Malformed YAML triggers ConfigError."""
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(":\n  - [broken", encoding="utf-8")
        with pytest.raises(ConfigError, match="Failed to parse YAML"):
            load_config(bad_yaml)

    def test_raises_config_error_for_non_mapping_yaml(self, tmp_path: Path) -> None:
        """YAML that parses to a list instead of a mapping triggers ConfigError."""
        list_yaml = tmp_path / "list.yaml"
        list_yaml.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="Config file must contain a YAML mapping"):
            load_config(list_yaml)
