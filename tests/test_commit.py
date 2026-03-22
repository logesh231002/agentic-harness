"""Tests for the commit skill."""

from __future__ import annotations

import pytest

from src.modules.evolution.commit import (
    CommitError,
    classify_changes,
    generate_commit_message,
    is_ai_layer_file,
)


class TestIsAiLayerFile:
    def test_claude_directory_files(self) -> None:
        assert is_ai_layer_file(".claude/rules/foo.rule.md") is True
        assert is_ai_layer_file(".claude/settings.json") is True

    def test_decisions_md_at_any_depth(self) -> None:
        assert is_ai_layer_file("DECISIONS.md") is True
        assert is_ai_layer_file("src/modules/foo/DECISIONS.md") is True

    def test_rule_md_at_any_depth(self) -> None:
        assert is_ai_layer_file("testing.rule.md") is True
        assert is_ai_layer_file("src/deep/nested/safety.rule.md") is True

    def test_harness_config(self) -> None:
        assert is_ai_layer_file("harness.config.yaml") is True

    def test_product_code_is_not_ai_layer(self) -> None:
        assert is_ai_layer_file("src/main.py") is False
        assert is_ai_layer_file("tests/test_foo.py") is False
        assert is_ai_layer_file("README.md") is False

    def test_similar_but_non_matching_paths(self) -> None:
        assert is_ai_layer_file("not-claude/rules/foo.md") is False
        assert is_ai_layer_file("DECISIONS.txt") is False


class TestClassifyChanges:
    def test_all_product_files(self) -> None:
        result = classify_changes(["src/main.py", "src/utils.py"])

        assert result.product == ("src/main.py", "src/utils.py")
        assert result.ai_layer == ()

    def test_all_ai_layer_files(self) -> None:
        result = classify_changes([".claude/rules/foo.rule.md", "harness.config.yaml"])

        assert result.product == ()
        assert result.ai_layer == (".claude/rules/foo.rule.md", "harness.config.yaml")

    def test_mixed_files(self) -> None:
        result = classify_changes(["src/main.py", ".claude/settings.json", "tests/test_foo.py"])

        assert result.product == ("src/main.py", "tests/test_foo.py")
        assert result.ai_layer == (".claude/settings.json",)

    def test_empty_input(self) -> None:
        result = classify_changes([])

        assert result.product == ()
        assert result.ai_layer == ()


class TestGenerateCommitMessage:
    def test_conventional_format_with_scope(self) -> None:
        msg = generate_commit_message("feat", "auth", "add login endpoint", [])

        assert msg == "feat(auth): add login endpoint"

    def test_conventional_format_without_scope(self) -> None:
        msg = generate_commit_message("fix", "", "resolve crash on startup", [])

        assert msg == "fix: resolve crash on startup"

    def test_includes_ai_layer_section_when_ai_files_present(self) -> None:
        msg = generate_commit_message(
            "feat",
            "commit",
            "add commit skill",
            ["src/commit.py", ".claude/rules/commit.rule.md", "harness.config.yaml"],
        )

        assert msg.startswith("feat(commit): add commit skill")
        assert "[ai-layer]" in msg
        assert "  - .claude/rules/commit.rule.md" in msg
        assert "  - harness.config.yaml" in msg
        assert "src/commit.py" not in msg.split("[ai-layer]")[1]

    def test_omits_ai_layer_section_when_no_ai_files(self) -> None:
        msg = generate_commit_message("refactor", "utils", "extract helper", ["src/utils.py", "src/helpers.py"])

        assert "[ai-layer]" not in msg
        assert msg == "refactor(utils): extract helper"

    def test_raises_on_empty_commit_type(self) -> None:
        with pytest.raises(CommitError, match="commit_type is required"):
            generate_commit_message("", "scope", "desc", [])

    def test_raises_on_empty_description(self) -> None:
        with pytest.raises(CommitError, match="description is required"):
            generate_commit_message("feat", "scope", "", [])
