"""Bootstrap script to wire harness files into a target project's .claude/ directory."""

import argparse
import shutil
import sys
from pathlib import Path
from typing import Literal


def _get_harness_root() -> Path:
    """Return the harness root directory (parent of src/)."""
    return Path(__file__).resolve().parent.parent


_CLAUDE_ITEMS = [
    "rules",
    "settings.json",
    "settings.local.example.json",
]

_SETTINGS_LOCAL = "settings.local.json"
_GITIGNORE_ENTRY = ".claude/settings.local.json"


class BootstrapError(Exception):
    """Raised when bootstrap operation fails."""


def _ensure_gitignore(target_dir: Path) -> None:
    """Ensure .gitignore contains an entry for .claude/settings.local.json."""
    gitignore_path = target_dir / ".gitignore"

    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped == _GITIGNORE_ENTRY or stripped == _SETTINGS_LOCAL:
                return
        if content and not content.endswith("\n"):
            content += "\n"
        content += _GITIGNORE_ENTRY + "\n"
        gitignore_path.write_text(content, encoding="utf-8")
    else:
        gitignore_path.write_text(_GITIGNORE_ENTRY + "\n", encoding="utf-8")


def _create_settings_local(target_claude_dir: Path, harness_claude_dir: Path) -> bool:
    """Create settings.local.json from template if it doesn't exist. Returns True if created."""
    target_local = target_claude_dir / _SETTINGS_LOCAL
    if target_local.exists():
        return False

    template = harness_claude_dir / "settings.local.example.json"
    if template.exists():
        shutil.copy2(template, target_local)
        return True
    return False


def bootstrap_harness(
    target_dir: Path, mode: Literal["symlink", "copy"], force: bool, harness_root: Path | None = None
) -> None:
    """Wire harness files into a target project's .claude/ directory.

    Args:
        target_dir: Path to the target project root.
        mode: Either "symlink" or "copy".
        force: If True, overwrite existing .claude/ directory without prompting.
        harness_root: Optional override for the harness root directory. Defaults to auto-detected root.

    Raises:
        BootstrapError: If the operation fails for any reason.
    """
    if harness_root is None:
        harness_root = _get_harness_root()
    harness_claude_dir = harness_root / ".claude"

    if not target_dir.exists():
        raise BootstrapError(f"Target directory does not exist: {target_dir}")

    if not target_dir.is_dir():
        raise BootstrapError(f"Target path is not a directory: {target_dir}")

    if not harness_claude_dir.exists():
        raise BootstrapError(f"Harness source .claude/ directory not found: {harness_claude_dir}")

    target_claude_dir = target_dir / ".claude"

    if target_claude_dir.exists() and not force:
        raise BootstrapError(
            f"Target .claude/ directory already exists: {target_claude_dir}\nUse --force to overwrite existing files."
        )

    target_claude_dir.mkdir(parents=True, exist_ok=True)

    actions: list[str] = []

    for item_name in _CLAUDE_ITEMS:
        source = harness_claude_dir / item_name
        target = target_claude_dir / item_name

        if not source.exists():
            raise BootstrapError(f"Harness source item not found: {source}")

        if target.exists() or target.is_symlink():
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()

        if mode == "symlink":
            target.symlink_to(source, target_is_directory=source.is_dir())
            actions.append(f"  symlink: .claude/{item_name} -> {source}")
        else:
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)
            actions.append(f"  copied: .claude/{item_name}")

    harness_config_source = harness_root / "harness.config.yaml"
    harness_config_target = target_dir / "harness.config.yaml"

    if harness_config_source.exists():
        if harness_config_target.exists() or harness_config_target.is_symlink():
            if harness_config_target.is_dir() and not harness_config_target.is_symlink():
                shutil.rmtree(harness_config_target)
            else:
                harness_config_target.unlink()

        if mode == "symlink":
            harness_config_target.symlink_to(harness_config_source)
            actions.append(f"  symlink: harness.config.yaml -> {harness_config_source}")
        else:
            shutil.copy2(harness_config_source, harness_config_target)
            actions.append("  copied: harness.config.yaml")

    if _create_settings_local(target_claude_dir, harness_claude_dir):
        actions.append(f"  created: .claude/{_SETTINGS_LOCAL} (from template)")

    _ensure_gitignore(target_dir)
    actions.append(f"  ensured: .gitignore contains '{_GITIGNORE_ENTRY}'")

    summary = f"Bootstrap complete ({mode} mode) -> {target_dir}\n" + "\n".join(actions)
    print(summary)


def main() -> None:
    """CLI entry point for the bootstrap script."""
    parser = argparse.ArgumentParser(
        description="Wire harness files into a target project's .claude/ directory.",
    )
    parser.add_argument(
        "target",
        type=Path,
        help="Path to the target project root directory.",
    )
    parser.add_argument(
        "--mode",
        choices=["symlink", "copy"],
        default="symlink",
        help="How to install harness files (default: symlink).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Overwrite existing .claude/ directory without confirmation.",
    )

    args = parser.parse_args()

    try:
        bootstrap_harness(target_dir=args.target, mode=args.mode, force=args.force)
    except BootstrapError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
