"""Harness configuration schema using Pydantic v2."""

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class _CamelBaseModel(BaseModel):
    """Shared base with camelCase alias support and strict extra-field rejection."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)


class ModelRoutingEntry(_CamelBaseModel):
    """Maps a task type to a primary and fallback model."""

    primary: str = Field(min_length=1)
    fallback: str = Field(min_length=1)


class ModelRouting(_CamelBaseModel):
    """Model routing for each task type."""

    planning: ModelRoutingEntry
    implementation: ModelRoutingEntry
    review: ModelRoutingEntry
    quick_fix: ModelRoutingEntry = Field(alias="quick-fix")


class CouncilTier(StrEnum):
    """Whether a workflow step is council-worthy or single-agent-sufficient."""

    COUNCIL_WORTHY = "council-worthy"
    SINGLE_AGENT = "single-agent-sufficient"


class CouncilEntry(_CamelBaseModel):
    """Configuration for a single council tier entry."""

    tier: CouncilTier
    cost_multiplier: float = Field(alias="costMultiplier", gt=0)


class TournamentSizes(_CamelBaseModel):
    """Default tournament sizes for parallel agent execution."""

    full: int = Field(default=3, ge=3, le=4)
    pair: int = Field(default=2, ge=1, le=3)
    solo: int = Field(default=1, ge=1, le=1)
    turns_per_agent: int = Field(default=3, alias="turnsPerAgent", gt=0)


class Notifications(_CamelBaseModel):
    """Notification settings."""

    terminal_bell: bool = Field(default=True, alias="terminalBell")
    webhook_url: str | None = Field(default=None, alias="webhookUrl")

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook_url(cls, v: str | None) -> str | None:
        if v is not None and not v.startswith(("https://", "http://")):
            raise ValueError("webhookUrl must start with https:// or http://")
        return v


class StopHook(_CamelBaseModel):
    """Stop hook settings."""

    enabled: bool = Field(default=True)
    auto_commit: bool = Field(default=True, alias="autoCommit")
    auto_fix: bool = Field(default=True, alias="autoFix")


class ValidationThresholds(_CamelBaseModel):
    """Validation threshold settings."""

    max_line_length: int = Field(default=120, alias="maxLineLength", gt=0)
    max_cyclomatic_complexity: int = Field(default=10, alias="maxCyclomaticComplexity", gt=0)


class HarnessConfig(_CamelBaseModel):
    """Complete harness configuration."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    model_routing: ModelRouting = Field(alias="modelRouting")
    council_tiers: dict[str, CouncilEntry] = Field(alias="councilTiers")
    tournament_sizes: TournamentSizes = Field(default_factory=TournamentSizes, alias="tournamentSizes")
    notifications: Notifications = Field(default_factory=Notifications, alias="notifications")
    stop_hook: StopHook = Field(default_factory=StopHook, alias="stopHook")
    validation_thresholds: ValidationThresholds = Field(
        default_factory=ValidationThresholds, alias="validationThresholds"
    )

    @field_validator("council_tiers")
    @classmethod
    def validate_council_tiers_not_empty(cls, v: dict[str, CouncilEntry]) -> dict[str, CouncilEntry]:
        if not v:
            raise ValueError("councilTiers must have at least one entry")
        return v


class ConfigError(Exception):
    """Raised when config loading or validation fails."""


def load_config(path: str | Path) -> HarnessConfig:
    """Load and validate a harness config from a YAML file.

    Args:
        path: Path to the YAML config file.

    Returns:
        Validated HarnessConfig instance.

    Raises:
        ConfigError: If the file can't be read, parsed, or validated.
    """
    config_path = Path(path)

    try:
        raw = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {config_path}")
    except OSError as e:
        raise ConfigError(f"Failed to read config file: {config_path}") from e

    try:
        parsed: Any = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ConfigError(f"Failed to parse YAML in config file: {config_path}") from e

    if not isinstance(parsed, dict):
        raise ConfigError(f"Config file must contain a YAML mapping, got {type(parsed).__name__}")

    try:
        return HarnessConfig.model_validate(parsed)
    except ValidationError as e:
        issues = "\n".join(f"  - {'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors())
        raise ConfigError(f"Invalid harness config at {config_path}:\n{issues}") from e
