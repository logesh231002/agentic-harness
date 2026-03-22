"""Scoped rules loader: reads rule files and matches them to active file paths."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ScopedRulesError(Exception):
    """Raised when a rule file cannot be loaded or parsed."""


@dataclass(frozen=True)
class ScopedRule:
    source_path: Path
    globs: list[str]
    body: str


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)", re.DOTALL)


def _parse_rule_file(path: Path) -> ScopedRule:
    """Parse a single .rule.md file into a ScopedRule."""
    raw = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(raw)
    if match is None:
        raise ScopedRulesError(f"Missing YAML frontmatter in {path}")

    frontmatter_text, body = match.group(1), match.group(2)

    try:
        parsed: Any = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as exc:
        raise ScopedRulesError(f"Invalid YAML frontmatter in {path}") from exc

    if not isinstance(parsed, dict) or "globs" not in parsed:
        raise ScopedRulesError(f"Missing 'globs' field in frontmatter of {path}")

    globs_value: Any = parsed["globs"]
    if isinstance(globs_value, str):
        globs_value = [globs_value]
    if not isinstance(globs_value, list) or not all(isinstance(g, str) for g in globs_value):
        raise ScopedRulesError(f"'globs' must be a string or list of strings in {path}")

    return ScopedRule(source_path=path, globs=globs_value, body=body)


def load_rules(rules_dir: Path) -> list[ScopedRule]:
    """Read all ``*.rule.md`` files from *rules_dir* and return parsed rules.

    Raises:
        ScopedRulesError: If any rule file has invalid or missing frontmatter.
    """
    if not rules_dir.is_dir():
        return []

    rules: list[ScopedRule] = []
    for path in sorted(rules_dir.glob("*.rule.md")):
        rules.append(_parse_rule_file(path))
    return rules


def _glob_matches_path(glob_pattern: str, file_path: str) -> bool:
    """Check if a glob pattern matches a file path using fnmatch."""
    # fnmatch doesn't handle ** natively for directory traversal,
    # but PurePosixPath.match handles ** patterns well in Python 3.12+
    from pathlib import PurePosixPath

    return PurePosixPath(file_path).match(glob_pattern)


def _derive_module_paths(file_paths: list[str]) -> list[str]:
    """Derive DECISIONS.md paths for module directories.

    If an active file is within ``src/modules/<name>/...``, produce
    ``src/modules/<name>/DECISIONS.md`` as an additional virtual path.
    """
    extra: list[str] = []
    module_prefix = "src/modules/"
    for fp in file_paths:
        if fp.startswith(module_prefix):
            rest = fp[len(module_prefix) :]
            parts = rest.split("/")
            if parts:
                extra.append(f"{module_prefix}{parts[0]}/DECISIONS.md")
    return extra


def match_rules(rules: list[ScopedRule], file_paths: list[str]) -> list[ScopedRule]:
    """Return the subset of *rules* whose globs match any of *file_paths*.

    A rule matches if ANY of its glob patterns matches ANY of the given file
    paths.  For files inside ``src/modules/<name>/``, the matcher also checks
    whether ``src/modules/<name>/DECISIONS.md`` would match a rule's globs
    (auto-discovery for module-level decision docs).
    """
    all_paths = list(file_paths) + _derive_module_paths(file_paths)
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_paths: list[str] = []
    for p in all_paths:
        if p not in seen:
            seen.add(p)
            unique_paths.append(p)

    matched: list[ScopedRule] = []
    for rule in rules:
        if _rule_matches_any(rule, unique_paths):
            matched.append(rule)
    return matched


def _rule_matches_any(rule: ScopedRule, file_paths: list[str]) -> bool:
    for glob_pattern in rule.globs:
        for fp in file_paths:
            if _glob_matches_path(glob_pattern, fp):
                return True
    return False
