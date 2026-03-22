"""Tests for the bootstrap harness wiring script."""

import json
from pathlib import Path

import pytest

from src.bootstrap import BootstrapError, bootstrap_harness


@pytest.fixture()
def harness_source(tmp_path: Path) -> Path:
    """Create a fake harness directory structure for testing."""
    harness_root = tmp_path / "harness"
    harness_root.mkdir()

    claude_dir = harness_root / ".claude"
    claude_dir.mkdir()

    rules_dir = claude_dir / "rules"
    rules_dir.mkdir()
    (rules_dir / "testing.rule.md").write_text("# Testing Rule\nAlways test.", encoding="utf-8")

    (claude_dir / "settings.json").write_text(json.dumps({"key": "value"}), encoding="utf-8")
    (claude_dir / "settings.local.example.json").write_text(json.dumps({"local_key": "local_value"}), encoding="utf-8")

    (harness_root / "harness.config.yaml").write_text(
        "modelRouting:\n  planning:\n    primary: claude\n", encoding="utf-8"
    )

    return harness_root


class TestBootstrapSymlink:
    """Tests for symlink mode."""

    def test_creates_symlinks_for_claude_items(self, tmp_path: Path, harness_source: Path) -> None:
        target = tmp_path / "project"
        target.mkdir()

        bootstrap_harness(target_dir=target, mode="symlink", force=False, harness_root=harness_source)

        target_claude = target / ".claude"
        assert (target_claude / "rules").is_symlink()
        assert (target_claude / "settings.json").is_symlink()
        assert (target_claude / "settings.local.example.json").is_symlink()

    def test_symlinks_point_to_harness_source(self, tmp_path: Path, harness_source: Path) -> None:
        target = tmp_path / "project"
        target.mkdir()

        bootstrap_harness(target_dir=target, mode="symlink", force=False, harness_root=harness_source)

        target_claude = target / ".claude"
        source_claude = harness_source / ".claude"

        assert (target_claude / "rules").resolve() == (source_claude / "rules").resolve()
        assert (target_claude / "settings.json").resolve() == (source_claude / "settings.json").resolve()

    def test_symlinks_harness_config_to_project_root(self, tmp_path: Path, harness_source: Path) -> None:
        target = tmp_path / "project"
        target.mkdir()

        bootstrap_harness(target_dir=target, mode="symlink", force=False, harness_root=harness_source)

        harness_config = target / "harness.config.yaml"
        assert harness_config.is_symlink()
        assert harness_config.resolve() == (harness_source / "harness.config.yaml").resolve()


class TestBootstrapCopy:
    """Tests for copy mode."""

    def test_creates_real_copies_not_symlinks(self, tmp_path: Path, harness_source: Path) -> None:
        target = tmp_path / "project"
        target.mkdir()

        bootstrap_harness(target_dir=target, mode="copy", force=False, harness_root=harness_source)

        target_claude = target / ".claude"
        assert not (target_claude / "rules").is_symlink()
        assert not (target_claude / "settings.json").is_symlink()
        assert (target_claude / "rules").is_dir()
        assert (target_claude / "settings.json").is_file()

    def test_copied_content_matches_source(self, tmp_path: Path, harness_source: Path) -> None:
        target = tmp_path / "project"
        target.mkdir()

        bootstrap_harness(target_dir=target, mode="copy", force=False, harness_root=harness_source)

        source_content = (harness_source / ".claude" / "settings.json").read_text(encoding="utf-8")
        target_content = (target / ".claude" / "settings.json").read_text(encoding="utf-8")
        assert target_content == source_content

        source_rule = (harness_source / ".claude" / "rules" / "testing.rule.md").read_text(encoding="utf-8")
        target_rule = (target / ".claude" / "rules" / "testing.rule.md").read_text(encoding="utf-8")
        assert target_rule == source_rule

    def test_copies_harness_config_to_project_root(self, tmp_path: Path, harness_source: Path) -> None:
        target = tmp_path / "project"
        target.mkdir()

        bootstrap_harness(target_dir=target, mode="copy", force=False, harness_root=harness_source)

        harness_config = target / "harness.config.yaml"
        assert harness_config.is_file()
        assert not harness_config.is_symlink()
        source_content = (harness_source / "harness.config.yaml").read_text(encoding="utf-8")
        assert harness_config.read_text(encoding="utf-8") == source_content


class TestBootstrapForce:
    """Tests for --force flag behavior."""

    def test_raises_without_force_when_claude_dir_exists(self, tmp_path: Path, harness_source: Path) -> None:
        target = tmp_path / "project"
        target.mkdir()
        (target / ".claude").mkdir()

        with pytest.raises(BootstrapError, match="already exists"):
            bootstrap_harness(target_dir=target, mode="symlink", force=False, harness_root=harness_source)

    def test_overwrites_with_force(self, tmp_path: Path, harness_source: Path) -> None:
        target = tmp_path / "project"
        target.mkdir()
        (target / ".claude").mkdir()
        (target / ".claude" / "old_file.txt").write_text("old", encoding="utf-8")

        bootstrap_harness(target_dir=target, mode="symlink", force=True, harness_root=harness_source)

        assert (target / ".claude" / "rules").is_symlink()
        assert (target / ".claude" / "settings.json").is_symlink()


class TestBootstrapSettingsLocal:
    """Tests for settings.local.json handling."""

    def test_creates_settings_local_from_template(self, tmp_path: Path, harness_source: Path) -> None:
        target = tmp_path / "project"
        target.mkdir()

        bootstrap_harness(target_dir=target, mode="symlink", force=False, harness_root=harness_source)

        settings_local = target / ".claude" / "settings.local.json"
        assert settings_local.exists()
        content = json.loads(settings_local.read_text(encoding="utf-8"))
        assert content == {"local_key": "local_value"}

    def test_does_not_overwrite_existing_settings_local(self, tmp_path: Path, harness_source: Path) -> None:
        target = tmp_path / "project"
        target.mkdir()
        target_claude = target / ".claude"
        target_claude.mkdir()
        existing = target_claude / "settings.local.json"
        existing.write_text(json.dumps({"existing": True}), encoding="utf-8")

        bootstrap_harness(target_dir=target, mode="symlink", force=True, harness_root=harness_source)

        content = json.loads(existing.read_text(encoding="utf-8"))
        assert content == {"existing": True}


class TestBootstrapGitignore:
    """Tests for .gitignore handling."""

    def test_creates_gitignore_when_absent(self, tmp_path: Path, harness_source: Path) -> None:
        target = tmp_path / "project"
        target.mkdir()

        bootstrap_harness(target_dir=target, mode="symlink", force=False, harness_root=harness_source)

        gitignore = target / ".gitignore"
        assert gitignore.exists()
        assert ".claude/settings.local.json" in gitignore.read_text(encoding="utf-8")

    def test_appends_entry_when_missing(self, tmp_path: Path, harness_source: Path) -> None:
        target = tmp_path / "project"
        target.mkdir()
        gitignore = target / ".gitignore"
        gitignore.write_text("node_modules/\n", encoding="utf-8")

        bootstrap_harness(target_dir=target, mode="symlink", force=False, harness_root=harness_source)

        content = gitignore.read_text(encoding="utf-8")
        assert "node_modules/" in content
        assert ".claude/settings.local.json" in content

    def test_does_not_duplicate_entry(self, tmp_path: Path, harness_source: Path) -> None:
        target = tmp_path / "project"
        target.mkdir()
        gitignore = target / ".gitignore"
        gitignore.write_text(".claude/settings.local.json\n", encoding="utf-8")

        bootstrap_harness(target_dir=target, mode="symlink", force=False, harness_root=harness_source)

        content = gitignore.read_text(encoding="utf-8")
        assert content.count(".claude/settings.local.json") == 1

    def test_skips_when_settings_local_entry_present(self, tmp_path: Path, harness_source: Path) -> None:
        target = tmp_path / "project"
        target.mkdir()
        gitignore = target / ".gitignore"
        gitignore.write_text("settings.local.json\n", encoding="utf-8")

        bootstrap_harness(target_dir=target, mode="symlink", force=False, harness_root=harness_source)

        content = gitignore.read_text(encoding="utf-8")
        assert ".claude/settings.local.json" not in content
        assert "settings.local.json" in content


class TestBootstrapErrors:
    """Tests for error handling."""

    def test_raises_for_nonexistent_target_dir(self, tmp_path: Path, harness_source: Path) -> None:
        nonexistent = tmp_path / "does_not_exist"

        with pytest.raises(BootstrapError, match="does not exist"):
            bootstrap_harness(target_dir=nonexistent, mode="symlink", force=False, harness_root=harness_source)

    def test_raises_for_file_as_target(self, tmp_path: Path, harness_source: Path) -> None:
        target_file = tmp_path / "not_a_dir"
        target_file.write_text("oops", encoding="utf-8")

        with pytest.raises(BootstrapError, match="not a directory"):
            bootstrap_harness(target_dir=target_file, mode="symlink", force=False, harness_root=harness_source)

    def test_raises_for_missing_harness_source(self, tmp_path: Path) -> None:
        target = tmp_path / "project"
        target.mkdir()
        fake_harness = tmp_path / "no_harness"
        fake_harness.mkdir()

        with pytest.raises(BootstrapError, match="not found"):
            bootstrap_harness(target_dir=target, mode="symlink", force=False, harness_root=fake_harness)

    def test_raises_for_missing_source_item(self, tmp_path: Path, harness_source: Path) -> None:
        (harness_source / ".claude" / "settings.json").unlink()
        target = tmp_path / "project"
        target.mkdir()

        with pytest.raises(BootstrapError, match="not found"):
            bootstrap_harness(target_dir=target, mode="symlink", force=False, harness_root=harness_source)
