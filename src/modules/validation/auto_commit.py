"""Auto-commit: stages tracked changes and commits with a conventional message."""

from __future__ import annotations

import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class AutoCommitError(Exception):
    """Raised when the auto-commit process encounters an unrecoverable error."""


_AI_LAYER_PATTERNS: tuple[str, ...] = (
    ".claude/",
    "rules/",
    "skills/",
    "hooks/",
    "context/",
    "prompts/",
)

_AI_LAYER_FILENAMES: frozenset[str] = frozenset(
    {
        "harness.config.yaml",
    }
)


@dataclass(frozen=True)
class FileClassification:
    """Separates changed files into product and AI layer categories."""

    product: list[str]
    ai_layer: list[str]


@dataclass(frozen=True)
class AutoCommitResult:
    """Outcome of an auto-commit attempt."""

    committed: bool
    message: str
    files: list[str]


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a git command, returning the completed process."""
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def _get_changed_files(project_root: Path) -> list[str]:
    """Return list of tracked files with changes (staged + unstaged)."""
    staged = _run_git(["diff", "--cached", "--name-only"], cwd=project_root)
    unstaged = _run_git(["diff", "--name-only"], cwd=project_root)

    files: set[str] = set()
    for output in (staged.stdout, unstaged.stdout):
        for line in output.strip().splitlines():
            stripped = line.strip()
            if stripped:
                files.add(stripped)
    return sorted(files)


def _is_ai_layer_file(filepath: str) -> bool:
    """Check whether a file path belongs to the AI layer."""
    if PurePosixPath(filepath).name in _AI_LAYER_FILENAMES:
        return True
    return any(pattern in filepath for pattern in _AI_LAYER_PATTERNS)


def classify_files(files: list[str]) -> FileClassification:
    """Split files into product and AI layer categories."""
    product: list[str] = []
    ai_layer: list[str] = []
    for f in files:
        if _is_ai_layer_file(f):
            ai_layer.append(f)
        else:
            product.append(f)
    return FileClassification(product=product, ai_layer=ai_layer)


def _infer_type(filepath: str) -> str:
    """Infer conventional commit type from a file path."""
    parts = PurePosixPath(filepath).parts
    name = PurePosixPath(filepath).name

    if any(p.startswith("test") for p in parts) or name.startswith("test_") or name.endswith("_test.py"):
        return "test"
    if name in {
        "pyproject.toml",
        "setup.cfg",
        "setup.py",
        "Makefile",
        ".gitignore",
        "ruff.toml",
        "mypy.ini",
        ".pre-commit-config.yaml",
    }:
        return "chore"
    return "fix"


def _most_common_directory(files: list[str]) -> str:
    """Return the most common top-level directory among *files*."""
    dirs: Counter[str] = Counter()
    for f in files:
        parts = PurePosixPath(f).parts
        if len(parts) > 1:
            dirs[parts[0]] = dirs.get(parts[0], 0) + 1
        else:
            dirs["root"] = dirs.get("root", 0) + 1
    if not dirs:
        return "root"
    return dirs.most_common(1)[0][0]


def _ai_layer_categories(files: list[str]) -> list[str]:
    """Return which AI layer categories are represented in *files*."""
    categories: set[str] = set()
    for f in files:
        if ".claude/" in f:
            categories.add("claude")
        if "rules/" in f:
            categories.add("rules")
        if "skills/" in f:
            categories.add("skills")
        if "hooks/" in f:
            categories.add("hooks")
        if "context/" in f:
            categories.add("context")
        if "prompts/" in f:
            categories.add("prompts")
        if PurePosixPath(f).name in _AI_LAYER_FILENAMES:
            categories.add("config")
    return sorted(categories)


def generate_commit_message(classification: FileClassification) -> str:
    """Build a conventional-commits message from classified files."""
    lines: list[str] = []

    product = classification.product
    ai_layer = classification.ai_layer
    all_files = product + ai_layer

    if product:
        types = Counter(_infer_type(f) for f in product)
        commit_type = types.most_common(1)[0][0]
        scope = _most_common_directory(product)
        n = len(product)
        desc = f"update {n} file{'s' if n != 1 else ''} in {scope}"
        lines.append(f"{commit_type}({scope}): {desc}")
    else:
        n = len(all_files)
        desc = f"update {n} file{'s' if n != 1 else ''}"
        lines.append(f"chore(ai): {desc}")

    if ai_layer:
        cats = _ai_layer_categories(ai_layer)
        lines.append("")
        lines.append(f"[ai-layer] updated: {', '.join(cats)}")

    return "\n".join(lines)


def auto_commit(project_root: Path) -> AutoCommitResult:
    """Stage tracked modifications and commit with a generated message.

    Returns:
        AutoCommitResult with committed=False if nothing to commit.

    Raises:
        AutoCommitError: If a git command fails unexpectedly.
    """
    changed = _get_changed_files(project_root)
    if not changed:
        return AutoCommitResult(committed=False, message="nothing to commit", files=[])

    classification = classify_files(changed)
    message = generate_commit_message(classification)

    stage_result = _run_git(["add", "-u"], cwd=project_root)
    if stage_result.returncode != 0:
        raise AutoCommitError(f"git add -u failed: {stage_result.stderr.strip()}")

    commit_result = _run_git(["commit", "-m", message], cwd=project_root)
    if commit_result.returncode != 0:
        raise AutoCommitError(f"git commit failed: {commit_result.stderr.strip()}")

    return AutoCommitResult(committed=True, message=message, files=changed)
