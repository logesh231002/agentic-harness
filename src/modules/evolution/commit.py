"""Commit skill: generates structured two-section commit messages with AI-layer tracking."""

from __future__ import annotations

import fnmatch
from collections.abc import Sequence
from dataclasses import dataclass

AI_LAYER_PATTERNS: tuple[str, ...] = (
    ".claude/**",
    "**/DECISIONS.md",
    "**/*.rule.md",
    "harness.config.yaml",
)


class CommitError(Exception):
    """Raised when the commit message generation encounters an unrecoverable error."""


@dataclass(frozen=True)
class ClassifiedChanges:
    """The result of classifying changed files into product code vs AI layer."""

    product: tuple[str, ...]
    ai_layer: tuple[str, ...]


def is_ai_layer_file(path: str) -> bool:
    """Check if a file path matches any AI layer pattern.

    AI layer patterns:
    - .claude/** (any file under .claude/)
    - **/DECISIONS.md (DECISIONS.md at any depth, including root)
    - **/*.rule.md (any .rule.md file at any depth, including root)
    - harness.config.yaml (root config)
    """
    for pattern in AI_LAYER_PATTERNS:
        if fnmatch.fnmatch(path, pattern):
            return True
        if pattern.startswith("**/"):
            basename_pattern = pattern[3:]
            if fnmatch.fnmatch(path, basename_pattern):
                return True
    return False


def classify_changes(changed_files: Sequence[str]) -> ClassifiedChanges:
    """Split changed files into product code vs AI layer categories."""
    product: list[str] = []
    ai_layer: list[str] = []

    for f in changed_files:
        if is_ai_layer_file(f):
            ai_layer.append(f)
        else:
            product.append(f)

    return ClassifiedChanges(
        product=tuple(product),
        ai_layer=tuple(ai_layer),
    )


def generate_commit_message(
    commit_type: str,
    scope: str,
    description: str,
    changed_files: Sequence[str],
) -> str:
    """Generate a structured commit message with optional AI-layer section.

    Section 1: conventional commits format — type(scope): description
    Section 2: [ai-layer] marker listing AI layer file changes (omitted if none)
    """
    if not commit_type:
        raise CommitError("commit_type is required")
    if not description:
        raise CommitError("description is required")

    header = f"{commit_type}({scope}): {description}" if scope else f"{commit_type}: {description}"

    classified = classify_changes(changed_files)

    if not classified.ai_layer:
        return header

    ai_lines = "\n".join(f"  - {f}" for f in classified.ai_layer)
    return f"{header}\n\n[ai-layer]\n{ai_lines}"
