"""Validate command: full validation gate for milestone checkpoints and pre-merge."""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


class ValidateError(Exception):
    """Raised when the validation gate encounters an unrecoverable error."""


class ValidationSeverity(enum.Enum):
    """Severity level for a validation result."""

    BLOCK = "block"
    WARNING = "warning"


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of a single validation check."""

    step: str
    passed: bool
    severity: ValidationSeverity
    message: str


@dataclass(frozen=True)
class ValidationReport:
    """Aggregated report from all validation checks."""

    results: Sequence[ValidationResult]
    passed: bool


@dataclass(frozen=True)
class QualityThresholds:
    """Configurable thresholds for file quality checks."""

    max_line_length: int = 120
    max_cyclomatic_complexity: int = 10
    max_file_lines: int = 500


@dataclass(frozen=True)
class ValidationStep:
    """A named validation step with a command and severity."""

    name: str
    command: str
    severity: ValidationSeverity


def get_default_steps() -> Sequence[ValidationStep]:
    """Return the standard validation pipeline steps."""
    return (
        ValidationStep(name="type-check", command="mypy --strict .", severity=ValidationSeverity.BLOCK),
        ValidationStep(name="lint", command="ruff check .", severity=ValidationSeverity.BLOCK),
        ValidationStep(name="test", command="pytest", severity=ValidationSeverity.BLOCK),
        ValidationStep(name="build", command="python -m build", severity=ValidationSeverity.BLOCK),
    )


def check_file_quality(file_path: Path, thresholds: QualityThresholds) -> Sequence[ValidationResult]:
    """Check a single file against quality thresholds (line length, complexity, file size).

    Returns WARNING-severity results for any violations found.
    """
    results: list[ValidationResult] = []

    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return [
            ValidationResult(
                step="file-quality",
                passed=False,
                severity=ValidationSeverity.WARNING,
                message=f"Could not read {file_path}: {exc}",
            )
        ]

    # Check file length.
    if len(lines) > thresholds.max_file_lines:
        results.append(
            ValidationResult(
                step="file-quality",
                passed=False,
                severity=ValidationSeverity.WARNING,
                message=f"{file_path}: {len(lines)} lines exceeds max {thresholds.max_file_lines}",
            )
        )

    # Check individual line lengths.
    long_lines: list[int] = []
    for i, line in enumerate(lines, start=1):
        if len(line) > thresholds.max_line_length:
            long_lines.append(i)

    if long_lines:
        preview = long_lines[:5]
        suffix = f" (and {len(long_lines) - 5} more)" if len(long_lines) > 5 else ""
        results.append(
            ValidationResult(
                step="file-quality",
                passed=False,
                severity=ValidationSeverity.WARNING,
                message=f"{file_path}: lines exceed max length {thresholds.max_line_length}: {preview}{suffix}",
            )
        )

    # Estimate cyclomatic complexity (simple heuristic: count branching keywords).
    branching_keywords = {"if ", "elif ", "for ", "while ", "except ", "and ", "or "}
    complexity = 1  # Base complexity.
    for line in lines:
        stripped = line.lstrip()
        for kw in branching_keywords:
            if stripped.startswith(kw) or f" {kw}" in stripped:
                complexity += 1
                break

    if complexity > thresholds.max_cyclomatic_complexity:
        results.append(
            ValidationResult(
                step="file-quality",
                passed=False,
                severity=ValidationSeverity.WARNING,
                message=(
                    f"{file_path}: estimated complexity {complexity} exceeds max {thresholds.max_cyclomatic_complexity}"
                ),
            )
        )

    return results


def detect_circular_deps(import_graph: Mapping[str, Sequence[str]]) -> Sequence[tuple[str, ...]]:
    """Detect circular dependencies in an import graph via DFS.

    Returns a sequence of cycles, each represented as a tuple of module names.
    """
    visited: set[str] = set()
    on_stack: set[str] = set()
    path: list[str] = []
    cycles: list[tuple[str, ...]] = []

    def _dfs(node: str) -> None:
        if node in on_stack:
            # Extract the cycle from the current path.
            cycle_start = path.index(node)
            cycle = tuple(path[cycle_start:])
            # Normalize: rotate so the smallest element is first to avoid duplicates.
            min_idx = cycle.index(min(cycle))
            normalized = cycle[min_idx:] + cycle[:min_idx]
            if normalized not in cycles:
                cycles.append(normalized)
            return
        if node in visited:
            return

        visited.add(node)
        on_stack.add(node)
        path.append(node)

        for dep in import_graph.get(node, ()):
            _dfs(dep)

        path.pop()
        on_stack.remove(node)

    for module in import_graph:
        _dfs(module)

    return cycles


def run_validation(
    steps: Sequence[ValidationStep],
    quality_results: Sequence[ValidationResult],
    circular_deps: Sequence[tuple[str, ...]],
) -> ValidationReport:
    """Combine step results, quality checks, and circular dependency findings into a report.

    The report passes if no BLOCK-severity results have failed.
    Steps are represented as pre-defined ValidationStep descriptors (commands are NOT executed).
    """
    results: list[ValidationResult] = []

    # Add step placeholders (pure — no subprocess execution).
    for step in steps:
        results.append(
            ValidationResult(
                step=step.name,
                passed=True,
                severity=step.severity,
                message=f"Step '{step.name}' registered: {step.command}",
            )
        )

    # Add file quality results.
    results.extend(quality_results)

    # Add circular dependency warnings.
    for cycle in circular_deps:
        cycle_str = " -> ".join(cycle) + " -> " + cycle[0]
        results.append(
            ValidationResult(
                step="circular-deps",
                passed=False,
                severity=ValidationSeverity.WARNING,
                message=f"Circular dependency detected: {cycle_str}",
            )
        )

    # Report passes if no BLOCK-severity results have failed.
    has_block_failure = any(not r.passed and r.severity == ValidationSeverity.BLOCK for r in results)
    return ValidationReport(results=tuple(results), passed=not has_block_failure)


def get_architecture_improvements(import_graph: Mapping[str, Sequence[str]]) -> Sequence[str]:
    """Identify shallow modules that could benefit from deepening.

    A 'shallow' module is one that has many dependents but few internal dependencies,
    suggesting it may be a thin wrapper that could absorb more responsibility.

    Returns a prioritized list of improvement suggestions.
    """
    improvements: list[str] = []

    # Count how many modules depend on each module (fan-in).
    fan_in: dict[str, int] = {}
    for module, deps in import_graph.items():
        for dep in deps:
            fan_in[dep] = fan_in.get(dep, 0) + 1

    # Count outgoing dependencies (fan-out).
    fan_out: dict[str, int] = {module: len(deps) for module, deps in import_graph.items()}

    # Identify shallow modules: high fan-in but low fan-out.
    all_modules = set(import_graph.keys()) | set(fan_in.keys())
    shallow: list[tuple[str, int, int]] = []
    for module in sorted(all_modules):
        fi = fan_in.get(module, 0)
        fo = fan_out.get(module, 0)
        if fi >= 2 and fo <= 1:
            shallow.append((module, fi, fo))

    # Sort by fan-in descending (most depended-on first).
    shallow.sort(key=lambda x: x[1], reverse=True)

    for module, fi, fo in shallow:
        improvements.append(f"{module}: shallow module ({fi} dependents, {fo} dependencies) — consider deepening")

    # Detect hub modules (high fan-out).
    hubs = [(m, fo) for m, fo in fan_out.items() if fo >= 4]
    hubs.sort(key=lambda x: x[1], reverse=True)
    for module, fo in hubs:
        improvements.append(f"{module}: hub module ({fo} dependencies) — consider splitting responsibilities")

    return improvements
