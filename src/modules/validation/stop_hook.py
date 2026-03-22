"""Stop hook: runs type-check, lint, and test steps with re-entry guard."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from src.config.schema import ConfigError, load_config

_ENV_GUARD = "STOP_HOOK_ACTIVE"
_CONFIG_FILENAME = "harness.config.yaml"


class StopHookError(Exception):
    """Raised when the stop hook encounters an unrecoverable error."""


@dataclass(frozen=True)
class StepResult:
    name: str
    passed: bool
    output: str


def _find_config(start: Path) -> Path:
    """Walk up from *start* looking for harness.config.yaml."""
    current = start.resolve()
    while True:
        candidate = current / _CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            raise StopHookError(f"Could not find {_CONFIG_FILENAME} in {start} or any parent directory")
        current = parent


def _run_step(name: str, cmd: list[str], cwd: Path) -> StepResult:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    combined = result.stdout
    if result.stderr:
        combined = f"{combined}\n{result.stderr}".strip()
    return StepResult(name=name, passed=result.returncode == 0, output=combined)


def run_hook(project_root: Path) -> int:
    """Execute the stop hook pipeline. Returns 0 on success, 1 on failure."""
    if os.environ.get(_ENV_GUARD):
        print("Stop hook already active — skipping re-entrant invocation.")
        return 0

    os.environ[_ENV_GUARD] = "1"
    try:
        return _run_pipeline(project_root)
    finally:
        os.environ.pop(_ENV_GUARD, None)


def _run_pipeline(project_root: Path) -> int:
    try:
        config_path = _find_config(project_root)
        config = load_config(config_path)
    except (StopHookError, ConfigError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not config.stop_hook.enabled:
        print("Stop hook disabled in config — skipping.")
        return 0

    auto_fix = config.stop_hook.auto_fix
    steps: list[StepResult] = []

    steps.append(_run_step("type-check", ["mypy", "--strict", "."], cwd=project_root))

    if auto_fix:
        _run_step("lint-autofix", ["ruff", "check", "--fix", "."], cwd=project_root)
    steps.append(_run_step("lint", ["ruff", "check", "."], cwd=project_root))

    steps.append(_run_step("test", ["pytest"], cwd=project_root))

    all_passed = all(s.passed for s in steps)
    if all_passed:
        print("Stop hook: all steps passed ✓")
        return 0

    report = {
        "success": False,
        "steps": [asdict(s) for s in steps],
    }
    sys.stdout.write(json.dumps(report, indent=2) + "\n")
    return 1


def main(project_root: Path | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run stop-hook validation pipeline.")
    parser.add_argument("--project-root", type=Path, default=None, help="Project root directory (default: CWD).")
    args = parser.parse_args()

    root = project_root or args.project_root or Path.cwd()
    code = run_hook(root)
    sys.exit(code)


if __name__ == "__main__":
    main()
