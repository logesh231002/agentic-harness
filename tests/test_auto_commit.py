"""Tests for the auto-commit module."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from src.modules.validation.auto_commit import (
    AutoCommitError,
    AutoCommitResult,
    FileClassification,
    auto_commit,
    classify_files,
    generate_commit_message,
)
from src.modules.validation.stop_hook import run_hook


def _make_completed_process(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


_GIT_OK = _make_completed_process(0)
_GIT_FAIL = _make_completed_process(1, stderr="fatal: error")


def _write_config(root: Path, *, enabled: bool = True, auto_commit_flag: bool = True) -> None:
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
        "stopHook": {"enabled": enabled, "autoCommit": auto_commit_flag, "autoFix": True},
    }
    (root / "harness.config.yaml").write_text(yaml.dump(config), encoding="utf-8")


class TestFileClassification:
    def test_product_files_classified(self) -> None:
        files = ["src/main.py", "src/utils/helpers.py", "README.md"]
        result = classify_files(files)
        assert result.product == files
        assert result.ai_layer == []

    def test_ai_layer_files_classified(self) -> None:
        files = [".claude/rules/foo.md", "harness.config.yaml", "hooks/pre-commit.sh"]
        result = classify_files(files)
        assert result.product == []
        assert result.ai_layer == files

    def test_mixed_files_split_correctly(self) -> None:
        files = [
            "src/app.py",
            ".claude/rules/coding.md",
            "tests/test_app.py",
            "rules/lint.md",
            "harness.config.yaml",
        ]
        result = classify_files(files)
        assert result.product == ["src/app.py", "tests/test_app.py"]
        assert result.ai_layer == [".claude/rules/coding.md", "rules/lint.md", "harness.config.yaml"]

    def test_context_path_is_ai_layer(self) -> None:
        files = ["docs/context/architecture.md"]
        result = classify_files(files)
        assert result.ai_layer == files

    def test_prompts_path_is_ai_layer(self) -> None:
        files = ["prompts/system.txt"]
        result = classify_files(files)
        assert result.ai_layer == files

    def test_skills_path_is_ai_layer(self) -> None:
        files = ["skills/refactor.md"]
        result = classify_files(files)
        assert result.ai_layer == files


class TestCommitMessageGeneration:
    def test_product_only_generates_conventional_format(self) -> None:
        classification = FileClassification(
            product=["src/modules/validation/stop_hook.py"],
            ai_layer=[],
        )
        msg = generate_commit_message(classification)
        assert msg.startswith("fix(src):")
        assert "1 file" in msg
        assert "[ai-layer]" not in msg

    def test_ai_layer_only_generates_chore_ai(self) -> None:
        classification = FileClassification(
            product=[],
            ai_layer=[".claude/rules/foo.md", "hooks/pre-commit.sh"],
        )
        msg = generate_commit_message(classification)
        assert msg.startswith("chore(ai):")
        assert "2 files" in msg
        assert "[ai-layer] updated:" in msg

    def test_mixed_changes_include_both_sections(self) -> None:
        classification = FileClassification(
            product=["src/main.py"],
            ai_layer=[".claude/rules/foo.md"],
        )
        msg = generate_commit_message(classification)
        lines = msg.splitlines()
        assert lines[0].startswith("fix(src):")
        assert "[ai-layer] updated:" in msg

    def test_test_files_get_test_type(self) -> None:
        classification = FileClassification(
            product=["tests/test_app.py", "tests/test_utils.py"],
            ai_layer=[],
        )
        msg = generate_commit_message(classification)
        assert msg.startswith("test(tests):")

    def test_single_file_no_plural(self) -> None:
        classification = FileClassification(
            product=["src/app.py"],
            ai_layer=[],
        )
        msg = generate_commit_message(classification)
        assert "1 file in" in msg
        assert "1 files" not in msg

    def test_multiple_files_plural(self) -> None:
        classification = FileClassification(
            product=["src/a.py", "src/b.py"],
            ai_layer=[],
        )
        msg = generate_commit_message(classification)
        assert "2 files in" in msg

    def test_ai_layer_categories_detected(self) -> None:
        classification = FileClassification(
            product=[],
            ai_layer=[".claude/rules/foo.md", "hooks/stop.sh"],
        )
        msg = generate_commit_message(classification)
        assert "claude" in msg
        assert "hooks" in msg
        assert "rules" in msg


class TestAutoCommitExecution:
    def test_stages_and_commits_when_files_changed(self) -> None:
        git_calls: list[list[str]] = []

        def mock_git(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            cmd = args[0] if args else kwargs.get("args", [])
            cmd_list = list(cmd)
            git_calls.append(cmd_list)

            if cmd_list[1:3] == ["diff", "--cached"]:
                return _make_completed_process(0, stdout="src/main.py\n")
            if cmd_list[1:3] == ["diff", "--name-only"]:
                return _make_completed_process(0, stdout="")
            return _GIT_OK

        with patch("src.modules.validation.auto_commit.subprocess.run", side_effect=mock_git):
            result = auto_commit(Path("/fake/project"))

        assert result.committed is True
        assert result.files == ["src/main.py"]

        add_calls = [c for c in git_calls if "add" in c and "-u" in c]
        assert len(add_calls) == 1

        commit_calls = [c for c in git_calls if "commit" in c]
        assert len(commit_calls) == 1

    def test_returns_not_committed_when_clean_tree(self) -> None:
        def mock_git(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return _make_completed_process(0, stdout="")

        with patch("src.modules.validation.auto_commit.subprocess.run", side_effect=mock_git):
            result = auto_commit(Path("/fake/project"))

        assert result.committed is False
        assert result.files == []

    def test_handles_git_add_error_gracefully(self) -> None:
        call_count = 0

        def mock_git(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            nonlocal call_count
            call_count += 1
            cmd = args[0] if args else kwargs.get("args", [])
            cmd_list = list(cmd)

            if "diff" in cmd_list:
                return _make_completed_process(0, stdout="src/main.py\n")
            if "add" in cmd_list:
                return _GIT_FAIL
            return _GIT_OK

        with patch("src.modules.validation.auto_commit.subprocess.run", side_effect=mock_git):
            with pytest.raises(AutoCommitError, match="git add -u failed"):
                auto_commit(Path("/fake/project"))

    def test_handles_git_commit_error_gracefully(self) -> None:
        def mock_git(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            cmd = args[0] if args else kwargs.get("args", [])
            cmd_list = list(cmd)

            if "diff" in cmd_list:
                return _make_completed_process(0, stdout="src/main.py\n")
            if "commit" in cmd_list:
                return _GIT_FAIL
            return _GIT_OK

        with patch("src.modules.validation.auto_commit.subprocess.run", side_effect=mock_git):
            with pytest.raises(AutoCommitError, match="git commit failed"):
                auto_commit(Path("/fake/project"))

    def test_result_dataclass_fields(self) -> None:
        result = AutoCommitResult(committed=True, message="fix(src): update 1 file in src", files=["src/main.py"])
        assert result.committed is True
        assert result.message == "fix(src): update 1 file in src"
        assert result.files == ["src/main.py"]


_STEP_PASS = _make_completed_process(0, stdout="ok")


class TestStopHookIntegration:
    def test_auto_commit_called_when_enabled_and_all_pass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, auto_commit_flag=True)
        monkeypatch.delenv("STOP_HOOK_ACTIVE", raising=False)

        with (
            patch("src.modules.validation.stop_hook.subprocess.run", return_value=_STEP_PASS),
            patch("src.modules.validation.stop_hook.auto_commit") as mock_ac,
        ):
            mock_ac.return_value = AutoCommitResult(committed=True, message="fix(src): update", files=["a.py"])
            code = run_hook(tmp_path)

        assert code == 0
        mock_ac.assert_called_once_with(tmp_path)

    def test_auto_commit_not_called_when_disabled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_config(tmp_path, auto_commit_flag=False)
        monkeypatch.delenv("STOP_HOOK_ACTIVE", raising=False)

        with (
            patch("src.modules.validation.stop_hook.subprocess.run", return_value=_STEP_PASS),
            patch("src.modules.validation.stop_hook.auto_commit") as mock_ac,
        ):
            code = run_hook(tmp_path)

        assert code == 0
        mock_ac.assert_not_called()

    def test_auto_commit_not_called_when_checks_fail(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_config(tmp_path, auto_commit_flag=True)
        monkeypatch.delenv("STOP_HOOK_ACTIVE", raising=False)

        fail = _make_completed_process(1, stdout="error")
        with (
            patch("src.modules.validation.stop_hook.subprocess.run", return_value=fail),
            patch("src.modules.validation.stop_hook.auto_commit") as mock_ac,
        ):
            code = run_hook(tmp_path)

        assert code == 1
        mock_ac.assert_not_called()

    def test_auto_commit_failure_does_not_change_exit_code(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, auto_commit_flag=True)
        monkeypatch.delenv("STOP_HOOK_ACTIVE", raising=False)

        with (
            patch("src.modules.validation.stop_hook.subprocess.run", return_value=_STEP_PASS),
            patch("src.modules.validation.stop_hook.auto_commit", side_effect=AutoCommitError("git broke")),
        ):
            code = run_hook(tmp_path)

        assert code == 0
