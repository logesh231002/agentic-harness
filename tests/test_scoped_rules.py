"""Tests for the scoped rules loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.modules.context.scoped_rules import ScopedRule, ScopedRulesError, load_rules, match_rules


def _write_rule(directory: Path, name: str, globs: list[str], body: str) -> Path:
    """Helper: write a .rule.md file with YAML frontmatter."""
    globs_yaml = ", ".join(f'"{g}"' for g in globs)
    content = f"---\nglobs: [{globs_yaml}]\n---\n{body}"
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


class TestLoadRules:
    def test_loads_single_rule_file(self, tmp_path: Path) -> None:
        _write_rule(tmp_path, "testing.rule.md", ["**/test_*.py"], "\n# Testing\nUse pytest.\n")

        rules = load_rules(tmp_path)

        assert len(rules) == 1
        assert rules[0].globs == ["**/test_*.py"]
        assert "Use pytest." in rules[0].body
        assert rules[0].source_path == tmp_path / "testing.rule.md"

    def test_loads_multiple_rule_files(self, tmp_path: Path) -> None:
        _write_rule(tmp_path, "alpha.rule.md", ["**/*.py"], "\n# Alpha\n")
        _write_rule(tmp_path, "beta.rule.md", ["**/*.ts"], "\n# Beta\n")

        rules = load_rules(tmp_path)

        assert len(rules) == 2
        names = [r.source_path.name for r in rules]
        assert "alpha.rule.md" in names
        assert "beta.rule.md" in names

    def test_raises_on_missing_globs(self, tmp_path: Path) -> None:
        content = "---\ntitle: no globs here\n---\n\n# Body\n"
        (tmp_path / "bad.rule.md").write_text(content, encoding="utf-8")

        with pytest.raises(ScopedRulesError, match="globs"):
            load_rules(tmp_path)

    def test_raises_on_missing_frontmatter(self, tmp_path: Path) -> None:
        content = "# No frontmatter\nJust markdown.\n"
        (tmp_path / "nofm.rule.md").write_text(content, encoding="utf-8")

        with pytest.raises(ScopedRulesError, match="frontmatter"):
            load_rules(tmp_path)

    def test_empty_directory_returns_empty_list(self, tmp_path: Path) -> None:
        rules = load_rules(tmp_path)
        assert rules == []

    def test_ignores_non_rule_files(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# readme", encoding="utf-8")
        (tmp_path / "notes.txt").write_text("notes", encoding="utf-8")
        _write_rule(tmp_path, "real.rule.md", ["**/*.py"], "\n# Real\n")

        rules = load_rules(tmp_path)

        assert len(rules) == 1
        assert rules[0].source_path.name == "real.rule.md"


class TestMatchRules:
    def test_matches_glob_pattern(self) -> None:
        rule = ScopedRule(source_path=Path("test.rule.md"), globs=["**/*.py"], body="# Py")

        matched = match_rules([rule], ["src/foo.py"])

        assert len(matched) == 1
        assert matched[0] is rule

    def test_no_match_returns_empty(self) -> None:
        rule = ScopedRule(source_path=Path("test.rule.md"), globs=["**/*.py"], body="# Py")

        matched = match_rules([rule], ["README.md"])

        assert matched == []

    def test_multiple_globs_any_matches(self) -> None:
        rule = ScopedRule(
            source_path=Path("test.rule.md"),
            globs=["**/*.py", "**/*.ts"],
            body="# Code",
        )

        matched = match_rules([rule], ["src/app.ts"])

        assert len(matched) == 1

    def test_multiple_rules_multiple_files(self) -> None:
        py_rule = ScopedRule(source_path=Path("py.rule.md"), globs=["**/*.py"], body="# Py")
        ts_rule = ScopedRule(source_path=Path("ts.rule.md"), globs=["**/*.ts"], body="# TS")
        md_rule = ScopedRule(source_path=Path("md.rule.md"), globs=["**/*.md"], body="# MD")

        matched = match_rules([py_rule, ts_rule, md_rule], ["src/main.py", "docs/guide.md"])

        assert py_rule in matched
        assert md_rule in matched
        assert ts_rule not in matched

    def test_decisions_md_loading(self) -> None:
        rule = ScopedRule(
            source_path=Path("decisions.rule.md"),
            globs=["src/modules/*/DECISIONS.md"],
            body="# Decisions",
        )

        matched = match_rules([rule], ["src/modules/context/scoped_rules.py"])

        assert len(matched) == 1
        assert matched[0] is rule
