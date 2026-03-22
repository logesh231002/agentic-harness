"""Tests for the stop hook validation pipeline."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from src.modules.validation.stop_hook import StepResult, run_hook


def _write_config(root: Path, *, enabled: bool = True, auto_fix: bool = True) -> None:
    config: dict[str, Any] = {
        "modelRouting": {
            "planning": {"primary": "claude-opus", "fallback": "claude-sonnet"},
            "implementation": {"primary": "claude-sonnet", "fallback": "claude-haiku"},
            "review": {"primary": "gemini-pro", "fallback": "claude-sonnet"},
            "quick-fix": {"primary": "claude-haiku", "fallback": "claude-sonnet"},
        },
        "councilTiers": {
            "test": {"tier": "council-worthy", "costMultiplier": 1},
        },
        "stopHook": {"enabled": enabled, "autoCommit": True, "autoFix": auto_fix},
    }
    (root / "harness.config.yaml").write_text(yaml.dump(config), encoding="utf-8")


def _make_completed_process(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


_ALL_PASS = _make_completed_process(0, stdout="ok")
_FAIL = _make_completed_process(1, stdout="error found")


class TestReentryGuard:
    def test_skips_when_env_var_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_config(tmp_path)
        monkeypatch.setenv("STOP_HOOK_ACTIVE", "1")
        code = run_hook(tmp_path)
        assert code == 0
        assert "skipping re-entrant" in capsys.readouterr().out.lower()

    def test_env_var_cleaned_up_after_run(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_config(tmp_path)
        monkeypatch.delenv("STOP_HOOK_ACTIVE", raising=False)
        with patch("src.modules.validation.stop_hook.subprocess.run", return_value=_ALL_PASS):
            run_hook(tmp_path)
        import os

        assert os.environ.get("STOP_HOOK_ACTIVE") is None


class TestDisabledHook:
    def test_exits_zero_when_disabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_config(tmp_path, enabled=False)
        monkeypatch.delenv("STOP_HOOK_ACTIVE", raising=False)
        code = run_hook(tmp_path)
        assert code == 0
        assert "disabled" in capsys.readouterr().out.lower()

    def test_no_subprocess_calls_when_disabled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_config(tmp_path, enabled=False)
        monkeypatch.delenv("STOP_HOOK_ACTIVE", raising=False)
        with patch("src.modules.validation.stop_hook.subprocess.run") as mock_run:
            run_hook(tmp_path)
        mock_run.assert_not_called()


class TestTypeCheckStep:
    def test_detects_mypy_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_config(tmp_path)
        monkeypatch.delenv("STOP_HOOK_ACTIVE", raising=False)
        mypy_fail = _make_completed_process(1, stdout="error: Incompatible return type")
        with patch("src.modules.validation.stop_hook.subprocess.run", return_value=mypy_fail):
            code = run_hook(tmp_path)
        assert code == 1


class TestLintStep:
    def test_detects_ruff_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_config(tmp_path, auto_fix=False)
        monkeypatch.delenv("STOP_HOOK_ACTIVE", raising=False)

        def side_effect(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            cmd = args[0] if args else kwargs.get("args", [])
            if cmd and cmd[0] == "ruff":
                return _FAIL
            return _ALL_PASS

        with patch("src.modules.validation.stop_hook.subprocess.run", side_effect=side_effect):
            code = run_hook(tmp_path)
        assert code == 1

    def test_auto_fix_runs_ruff_fix_first(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_config(tmp_path, auto_fix=True)
        monkeypatch.delenv("STOP_HOOK_ACTIVE", raising=False)
        calls: list[list[str]] = []

        def capture_calls(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            cmd = args[0] if args else kwargs.get("args", [])
            calls.append(list(cmd))
            return _ALL_PASS

        with patch("src.modules.validation.stop_hook.subprocess.run", side_effect=capture_calls):
            run_hook(tmp_path)

        ruff_cmds = [c for c in calls if c and c[0] == "ruff"]
        assert len(ruff_cmds) == 2
        assert "--fix" in ruff_cmds[0]
        assert "--fix" not in ruff_cmds[1]


class TestAllPassPath:
    def test_returns_zero_when_all_pass(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_config(tmp_path)
        monkeypatch.delenv("STOP_HOOK_ACTIVE", raising=False)
        with patch("src.modules.validation.stop_hook.subprocess.run", return_value=_ALL_PASS):
            code = run_hook(tmp_path)
        assert code == 0

    def test_prints_success_message(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_config(tmp_path)
        monkeypatch.delenv("STOP_HOOK_ACTIVE", raising=False)
        with patch("src.modules.validation.stop_hook.subprocess.run", return_value=_ALL_PASS):
            run_hook(tmp_path)
        assert "all steps passed" in capsys.readouterr().out.lower()


class TestStructuredErrorReport:
    def test_json_report_on_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_config(tmp_path, auto_fix=False)
        monkeypatch.delenv("STOP_HOOK_ACTIVE", raising=False)

        def side_effect(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            cmd = args[0] if args else kwargs.get("args", [])
            if cmd and cmd[0] == "mypy":
                return _make_completed_process(1, stdout="type error output")
            return _ALL_PASS

        with patch("src.modules.validation.stop_hook.subprocess.run", side_effect=side_effect):
            code = run_hook(tmp_path)

        assert code == 1
        output = capsys.readouterr().out
        report = json.loads(output)
        assert report["success"] is False
        assert isinstance(report["steps"], list)
        assert len(report["steps"]) == 3

        step_names = [s["name"] for s in report["steps"]]
        assert step_names == ["type-check", "lint", "test"]

        type_step = report["steps"][0]
        assert type_step["passed"] is False
        assert "type error output" in type_step["output"]

    def test_step_result_dataclass_fields(self) -> None:
        result = StepResult(name="test", passed=True, output="ok")
        assert result.name == "test"
        assert result.passed is True
        assert result.output == "ok"
