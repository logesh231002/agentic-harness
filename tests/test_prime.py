"""Tests for the session bootstrapping prime command."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

from src.modules.context.prime import _format_prime_summary, prime


def _make_completed_process(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _git_side_effect(responses: dict[str, subprocess.CompletedProcess[str]]) -> Any:
    """Return a side_effect callable that matches git subcommands to canned responses."""
    default = _make_completed_process(0, stdout="")

    def _side_effect(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        cmd: list[str] = args[0] if args else kwargs.get("args", [])
        cmd_str = " ".join(cmd)
        for key, response in responses.items():
            if key in cmd_str:
                return response
        return default

    return _side_effect


class TestPrime:
    def test_extracts_project_name_from_claude_md(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text("# MyProject\n\nSome description.\n", encoding="utf-8")
        with patch("src.modules.context.prime.subprocess.run", return_value=_make_completed_process()):
            result = prime(tmp_path)
        assert result.project_name == "MyProject"

    def test_falls_back_to_directory_name(self, tmp_path: Path) -> None:
        with patch("src.modules.context.prime.subprocess.run", return_value=_make_completed_process()):
            result = prime(tmp_path)
        assert result.project_name == tmp_path.name

    def test_includes_recent_git_log(self, tmp_path: Path) -> None:
        responses = {
            "log --oneline": _make_completed_process(
                stdout="abc1234 feat: add prime\ndef5678 fix: typo\nghi9012 docs: readme"
            ),
        }
        with patch("src.modules.context.prime.subprocess.run", side_effect=_git_side_effect(responses)):
            result = prime(tmp_path)
        assert len(result.recent_changes) == 3
        assert "abc1234 feat: add prime" in result.recent_changes
        assert "def5678 fix: typo" in result.recent_changes
        assert "ghi9012 docs: readme" in result.recent_changes

    def test_discovers_key_files(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("print('hello')\n", encoding="utf-8")
        (tmp_path / "utils.py").write_text("pass\n", encoding="utf-8")
        with patch("src.modules.context.prime.subprocess.run", return_value=_make_completed_process()):
            result = prime(tmp_path)
        assert "main.py" in result.key_files
        assert "utils.py" in result.key_files

    def test_loads_glossary_when_present(self, tmp_path: Path) -> None:
        (tmp_path / "glossary.md").write_text("# Glossary\n\n- **TPO**: Time Price Opportunity\n", encoding="utf-8")
        with patch("src.modules.context.prime.subprocess.run", return_value=_make_completed_process()):
            result = prime(tmp_path)
        assert result.glossary is not None
        assert "TPO" in result.glossary

    def test_glossary_none_when_missing(self, tmp_path: Path) -> None:
        with patch("src.modules.context.prime.subprocess.run", return_value=_make_completed_process()):
            result = prime(tmp_path)
        assert result.glossary is None

    def test_loads_handoff_when_present(self, tmp_path: Path) -> None:
        (tmp_path / "HANDOFF.md").write_text("# Session Handoff\n\nResume in src/main.py\n", encoding="utf-8")
        with patch("src.modules.context.prime.subprocess.run", return_value=_make_completed_process()):
            result = prime(tmp_path)
        assert result.handoff is not None
        assert "Resume in src/main.py" in result.handoff

    def test_handoff_none_when_missing(self, tmp_path: Path) -> None:
        with patch("src.modules.context.prime.subprocess.run", return_value=_make_completed_process()):
            result = prime(tmp_path)
        assert result.handoff is None

    def test_frontend_subsystem_filters_files(self, tmp_path: Path) -> None:
        # Frontend file — should be included
        frontend_dir = tmp_path / "components"
        frontend_dir.mkdir()
        (frontend_dir / "button.py").write_text("pass\n", encoding="utf-8")
        # Backend file — should be excluded
        backend_dir = tmp_path / "api"
        backend_dir.mkdir()
        (backend_dir / "server.py").write_text("pass\n", encoding="utf-8")
        # Root file — should be excluded (no matching parent dir)
        (tmp_path / "main.py").write_text("pass\n", encoding="utf-8")
        with patch("src.modules.context.prime.subprocess.run", return_value=_make_completed_process()):
            result = prime(tmp_path, subsystem="frontend")
        key_files_str = " ".join(result.key_files)
        assert "button.py" in key_files_str
        assert "server.py" not in key_files_str

    def test_backend_subsystem_filters_files(self, tmp_path: Path) -> None:
        # Backend file — should be included
        backend_dir = tmp_path / "api"
        backend_dir.mkdir()
        (backend_dir / "routes.py").write_text("pass\n", encoding="utf-8")
        # Frontend file — should be excluded
        frontend_dir = tmp_path / "components"
        frontend_dir.mkdir()
        (frontend_dir / "button.py").write_text("pass\n", encoding="utf-8")
        # Root file — should be excluded
        (tmp_path / "main.py").write_text("pass\n", encoding="utf-8")
        with patch("src.modules.context.prime.subprocess.run", return_value=_make_completed_process()):
            result = prime(tmp_path, subsystem="backend")
        key_files_str = " ".join(result.key_files)
        assert "routes.py" in key_files_str
        assert "button.py" not in key_files_str


class TestFormatPrimeSummary:
    def test_includes_project_header(self) -> None:
        output = _format_prime_summary(
            project_name="TestProject",
            recent_changes=[],
            key_files=[],
            glossary=None,
            handoff=None,
            prd_excerpt=None,
        )
        assert "# Project: TestProject" in output

    def test_omits_empty_sections(self) -> None:
        output = _format_prime_summary(
            project_name="TestProject",
            recent_changes=[],
            key_files=[],
            glossary=None,
            handoff=None,
            prd_excerpt=None,
        )
        assert "## Glossary" not in output
        assert "## Previous Session" not in output
        assert "## Current PRD/Plan" not in output
