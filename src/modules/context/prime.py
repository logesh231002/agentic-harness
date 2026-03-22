"""Session bootstrapping: reads project context to prime an agent session."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


class PrimeError(Exception):
    """Raised when the prime process encounters an unrecoverable error."""


@dataclass(frozen=True)
class PrimeResult:
    project_name: str
    summary: str
    recent_changes: list[str]
    key_files: list[str]
    glossary: str | None
    handoff: str | None


_FRONTEND_DIRS = {"ui", "components", "pages", "frontend"}
_BACKEND_DIRS = {"api", "server", "backend", "modules"}

_KEY_FILE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".yaml", ".yml", ".toml", ".json"}
_MAX_KEY_FILES = 30


def _run_git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
    return result.stdout.strip()


def _extract_project_name(project_root: Path) -> str:
    claude_md = project_root / "CLAUDE.md"
    if claude_md.is_file():
        content = claude_md.read_text(encoding="utf-8")
        match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if match:
            return match.group(1).strip()
    return project_root.name


def _get_recent_changes(project_root: Path) -> list[str]:
    output = _run_git(["log", "--oneline", "-10"], cwd=project_root)
    if not output:
        return []
    return output.splitlines()


def _matches_subsystem(file_path: Path, subsystem: str | None) -> bool:
    if subsystem is None:
        return True
    dirs = _FRONTEND_DIRS if subsystem == "frontend" else _BACKEND_DIRS
    parts = {p.lower() for p in file_path.parts}
    return bool(parts & dirs)


def _discover_key_files(project_root: Path, subsystem: str | None) -> list[str]:
    found: list[str] = []
    for ext in sorted(_KEY_FILE_EXTENSIONS):
        for path in sorted(project_root.rglob(f"*{ext}")):
            if not _matches_subsystem(path.relative_to(project_root), subsystem):
                continue
            # Skip hidden directories and common noise
            rel = path.relative_to(project_root)
            if any(part.startswith(".") for part in rel.parts):
                continue
            if any(part in {"node_modules", "__pycache__", ".venv", "venv", "dist", "build"} for part in rel.parts):
                continue
            # Respect max-depth of 3
            if len(rel.parts) > 3:
                continue
            found.append(str(rel))
            if len(found) >= _MAX_KEY_FILES:
                return found
    return found


def _find_prd_artifact(project_root: Path) -> str | None:
    patterns = ["specs/**/*.md", "plans/**/*.md", "*.prd.md"]
    for pattern in patterns:
        matches = sorted(project_root.glob(pattern))
        if matches:
            content = matches[0].read_text(encoding="utf-8")
            # Return first 2000 chars as excerpt
            return content[:2000]
    return None


def _read_optional_file(project_root: Path, filename: str) -> str | None:
    path = project_root / filename
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return None


def _format_prime_summary(
    project_name: str,
    recent_changes: list[str],
    key_files: list[str],
    glossary: str | None,
    handoff: str | None,
    prd_excerpt: str | None,
) -> str:
    lines: list[str] = [f"# Project: {project_name}", ""]

    lines.append("## Recent Changes")
    lines.append("")
    if recent_changes:
        for change in recent_changes:
            lines.append(f"- {change}")
    else:
        lines.append("_No recent changes._")
    lines.append("")

    lines.append("## Key Files")
    lines.append("")
    if key_files:
        for f in key_files:
            lines.append(f"- {f}")
    else:
        lines.append("_No key files discovered._")
    lines.append("")

    if glossary is not None:
        lines.append("## Glossary")
        lines.append("")
        lines.append(glossary)
        lines.append("")

    if handoff is not None:
        lines.append("## Previous Session")
        lines.append("")
        lines.append(handoff)
        lines.append("")

    if prd_excerpt is not None:
        lines.append("## Current PRD/Plan")
        lines.append("")
        lines.append(prd_excerpt)
        lines.append("")

    return "\n".join(lines)


def prime(project_root: Path, subsystem: str | None = None) -> PrimeResult:
    """Read project context and produce a bootstrap summary for an agent session."""
    project_name = _extract_project_name(project_root)
    recent_changes = _get_recent_changes(project_root)
    key_files = _discover_key_files(project_root, subsystem)
    glossary = _read_optional_file(project_root, "glossary.md")
    handoff = _read_optional_file(project_root, "HANDOFF.md")
    prd_excerpt = _find_prd_artifact(project_root)

    summary = _format_prime_summary(
        project_name=project_name,
        recent_changes=recent_changes,
        key_files=key_files,
        glossary=glossary,
        handoff=handoff,
        prd_excerpt=prd_excerpt,
    )

    return PrimeResult(
        project_name=project_name,
        summary=summary,
        recent_changes=recent_changes,
        key_files=key_files,
        glossary=glossary,
        handoff=handoff,
    )
