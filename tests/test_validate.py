"""Tests for the validate command: full validation gate."""

from __future__ import annotations

from pathlib import Path

from src.modules.validation.validate import (
    QualityThresholds,
    ValidationResult,
    ValidationSeverity,
    ValidationStep,
    check_file_quality,
    detect_circular_deps,
    get_architecture_improvements,
    get_default_steps,
    run_validation,
)


class TestValidationSteps:
    def test_default_steps_returns_four_steps(self) -> None:
        steps = get_default_steps()
        assert len(steps) == 4

    def test_default_step_names(self) -> None:
        steps = get_default_steps()
        names = [s.name for s in steps]
        assert names == ["type-check", "lint", "test", "build"]

    def test_all_default_steps_are_block_severity(self) -> None:
        steps = get_default_steps()
        assert all(s.severity == ValidationSeverity.BLOCK for s in steps)

    def test_validation_step_is_frozen(self) -> None:
        step = ValidationStep(name="x", command="y", severity=ValidationSeverity.BLOCK)
        try:
            step.name = "z"  # type: ignore[misc]
            assert False, "Expected FrozenInstanceError"
        except AttributeError:
            pass


class TestFileQuality:
    def test_clean_file_returns_no_results(self, tmp_path: Path) -> None:
        f = tmp_path / "clean.py"
        f.write_text("x = 1\ny = 2\n", encoding="utf-8")
        results = check_file_quality(f, QualityThresholds())
        assert len(results) == 0

    def test_detects_long_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "long.py"
        f.write_text("x" * 130 + "\n", encoding="utf-8")
        results = check_file_quality(f, QualityThresholds(max_line_length=120))
        assert len(results) == 1
        assert not results[0].passed
        assert results[0].severity == ValidationSeverity.WARNING
        assert "max length" in results[0].message

    def test_detects_file_too_long(self, tmp_path: Path) -> None:
        f = tmp_path / "big.py"
        f.write_text("\n".join(f"x_{i} = {i}" for i in range(600)), encoding="utf-8")
        results = check_file_quality(f, QualityThresholds(max_file_lines=500))
        file_length_results = [r for r in results if "lines exceeds max" in r.message]
        assert len(file_length_results) == 1

    def test_detects_high_complexity(self, tmp_path: Path) -> None:
        f = tmp_path / "complex.py"
        lines = ["def foo():\n"]
        for i in range(15):
            lines.append(f"    if x_{i}:\n        pass\n")
        f.write_text("".join(lines), encoding="utf-8")
        results = check_file_quality(f, QualityThresholds(max_cyclomatic_complexity=5))
        complexity_results = [r for r in results if "complexity" in r.message]
        assert len(complexity_results) == 1

    def test_unreadable_file_returns_warning(self, tmp_path: Path) -> None:
        f = tmp_path / "missing.py"
        results = check_file_quality(f, QualityThresholds())
        assert len(results) == 1
        assert not results[0].passed
        assert "Could not read" in results[0].message

    def test_all_results_are_warning_severity(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("x" * 200 + "\n", encoding="utf-8")
        results = check_file_quality(f, QualityThresholds(max_line_length=50))
        assert all(r.severity == ValidationSeverity.WARNING for r in results)

    def test_custom_thresholds_respected(self, tmp_path: Path) -> None:
        f = tmp_path / "short.py"
        f.write_text("ab\ncd\nef\n", encoding="utf-8")
        results = check_file_quality(f, QualityThresholds(max_file_lines=2))
        assert any("lines exceeds max 2" in r.message for r in results)


class TestCircularDeps:
    def test_no_cycles_in_dag(self) -> None:
        graph = {"a": ["b"], "b": ["c"], "c": []}
        cycles = detect_circular_deps(graph)
        assert len(cycles) == 0

    def test_detects_simple_cycle(self) -> None:
        graph = {"a": ["b"], "b": ["a"]}
        cycles = detect_circular_deps(graph)
        assert len(cycles) == 1
        assert set(cycles[0]) == {"a", "b"}

    def test_detects_three_node_cycle(self) -> None:
        graph = {"a": ["b"], "b": ["c"], "c": ["a"]}
        cycles = detect_circular_deps(graph)
        assert len(cycles) == 1
        assert set(cycles[0]) == {"a", "b", "c"}

    def test_empty_graph_returns_no_cycles(self) -> None:
        cycles = detect_circular_deps({})
        assert len(cycles) == 0

    def test_self_loop_detected(self) -> None:
        graph = {"a": ["a"]}
        cycles = detect_circular_deps(graph)
        assert len(cycles) == 1
        assert cycles[0] == ("a",)

    def test_multiple_independent_cycles(self) -> None:
        graph = {"a": ["b"], "b": ["a"], "c": ["d"], "d": ["c"]}
        cycles = detect_circular_deps(graph)
        assert len(cycles) == 2

    def test_no_duplicate_cycles(self) -> None:
        graph = {"a": ["b"], "b": ["a"]}
        cycles = detect_circular_deps(graph)
        assert len(cycles) == 1


class TestRunValidation:
    def test_passes_with_no_failures(self) -> None:
        steps = [ValidationStep(name="test", command="pytest", severity=ValidationSeverity.BLOCK)]
        report = run_validation(steps, quality_results=[], circular_deps=[])
        assert report.passed is True
        assert len(report.results) == 1

    def test_passes_with_warning_failures_only(self) -> None:
        warning_result = ValidationResult(
            step="file-quality", passed=False, severity=ValidationSeverity.WARNING, message="too long"
        )
        report = run_validation(steps=[], quality_results=[warning_result], circular_deps=[])
        assert report.passed is True

    def test_fails_with_block_failure(self) -> None:
        block_result = ValidationResult(
            step="lint", passed=False, severity=ValidationSeverity.BLOCK, message="lint failed"
        )
        report = run_validation(steps=[], quality_results=[block_result], circular_deps=[])
        assert report.passed is False

    def test_circular_deps_added_as_warnings(self) -> None:
        report = run_validation(steps=[], quality_results=[], circular_deps=[("a", "b")])
        assert report.passed is True
        dep_results = [r for r in report.results if r.step == "circular-deps"]
        assert len(dep_results) == 1
        assert dep_results[0].severity == ValidationSeverity.WARNING
        assert "a -> b -> a" in dep_results[0].message

    def test_combines_all_result_types(self) -> None:
        steps = [ValidationStep(name="build", command="make", severity=ValidationSeverity.BLOCK)]
        quality = [
            ValidationResult(step="file-quality", passed=False, severity=ValidationSeverity.WARNING, message="warn")
        ]
        cycles: list[tuple[str, ...]] = [("x", "y")]
        report = run_validation(steps, quality, cycles)
        assert len(report.results) == 3
        assert report.passed is True

    def test_report_is_frozen(self) -> None:
        report = run_validation(steps=[], quality_results=[], circular_deps=[])
        try:
            report.passed = False  # type: ignore[misc]
            assert False, "Expected FrozenInstanceError"
        except AttributeError:
            pass


class TestArchitectureImprovements:
    def test_identifies_shallow_module(self) -> None:
        graph = {"a": ["utils"], "b": ["utils"], "c": ["utils"], "utils": []}
        improvements = get_architecture_improvements(graph)
        assert any("utils" in s and "shallow" in s for s in improvements)

    def test_identifies_hub_module(self) -> None:
        graph = {"hub": ["a", "b", "c", "d"], "a": [], "b": [], "c": [], "d": []}
        improvements = get_architecture_improvements(graph)
        assert any("hub" in s and "hub module" in s for s in improvements)

    def test_empty_graph_returns_no_improvements(self) -> None:
        improvements = get_architecture_improvements({})
        assert len(improvements) == 0

    def test_no_false_positives_on_balanced_graph(self) -> None:
        graph = {"a": ["b"], "b": ["c"], "c": []}
        improvements = get_architecture_improvements(graph)
        assert len(improvements) == 0

    def test_shallow_modules_sorted_by_fan_in(self) -> None:
        graph = {
            "a": ["x"],
            "b": ["x"],
            "c": ["x"],
            "d": ["y"],
            "e": ["y"],
            "x": [],
            "y": [],
        }
        improvements = get_architecture_improvements(graph)
        shallow = [s for s in improvements if "shallow" in s]
        assert len(shallow) == 2
        assert "x" in shallow[0]
        assert "y" in shallow[1]
