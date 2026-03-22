"""Reset and recovery: documented protocols for reverting to clean state and cross-model critique."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path


class ResetError(Exception):
    """Raised when the reset process encounters an unrecoverable error."""


@dataclass(frozen=True)
class CommitInfo:
    """A single commit with its test result."""

    sha: str
    message: str
    tests_passed: bool


@dataclass(frozen=True)
class ResetResult:
    """Result of finding the last clean commit to reset to."""

    target_commit: str
    commits_checked: int
    strategy: str


@dataclass(frozen=True)
class CompactionTracker:
    """Tracks compaction count and forces handoff after limit."""

    count: int = 0
    limit: int = 2


def reset_to_clean_commit(commits: Sequence[CommitInfo]) -> ResetResult:
    """Find the most recent commit where tests passed and return a reset plan.

    Walks the commit history (newest-first) looking for the first entry
    where ``tests_passed`` is True.  Returns a ``ResetResult`` describing
    which commit to target and how many were inspected.

    Raises ``ResetError`` if no clean commit is found or the history is empty.
    """
    if not commits:
        raise ResetError("No commit history provided")

    for idx, commit in enumerate(commits, start=1):
        if commit.tests_passed:
            strategy = "stash" if idx == 1 else "hard_reset"
            return ResetResult(
                target_commit=commit.sha,
                commits_checked=idx,
                strategy=strategy,
            )

    raise ResetError(f"No clean commit found in {len(commits)} commits")


def export_conversation(session_path: Path) -> str:
    """Read a session file and extract conversation text.

    Supports two formats:
    - JSON Lines: each line is a JSON object with a ``"content"`` field.
    - Plain text: returned as-is.

    Raises ``ResetError`` if the file does not exist or is empty.
    """
    if not session_path.exists():
        raise ResetError(f"Session file not found: {session_path}")

    text = session_path.read_text(encoding="utf-8").strip()
    if not text:
        raise ResetError(f"Session file is empty: {session_path}")

    lines = text.splitlines()
    try:
        first = json.loads(lines[0])
        if isinstance(first, dict) and "content" in first:
            parts: list[str] = []
            for line in lines:
                if not line.strip():
                    continue
                obj = json.loads(line)
                parts.append(str(obj.get("content", "")))
            return "\n".join(parts)
    except (json.JSONDecodeError, KeyError):
        pass

    return text


def cross_model_critique(conversation_text: str) -> str:
    """Construct a structured prompt for fresh-model analysis of a conversation.

    Returns a markdown-formatted critique prompt that can be sent to a
    different model for an independent review.
    """
    return (
        "# Cross-Model Critique Request\n"
        "\n"
        "You are a fresh reviewer. Analyze the following conversation for:\n"
        "\n"
        "1. **Logical errors** — flawed reasoning or incorrect assumptions\n"
        "2. **Missed alternatives** — solutions not considered\n"
        "3. **Scope creep** — work that drifted from the original goal\n"
        "4. **Unverified claims** — assertions made without evidence\n"
        "\n"
        "## Conversation\n"
        "\n"
        f"{conversation_text}\n"
        "\n"
        "## Instructions\n"
        "\n"
        "Provide a numbered list of issues found, each with:\n"
        "- **Issue**: one-line summary\n"
        "- **Evidence**: quote from the conversation\n"
        "- **Recommendation**: concrete next step\n"
    )


def record_compaction(tracker: CompactionTracker) -> CompactionTracker:
    """Increment the compaction count, returning a new tracker."""
    return replace(tracker, count=tracker.count + 1)


def should_force_handoff(tracker: CompactionTracker) -> bool:
    """Return True if the compaction count has reached the limit."""
    return tracker.count >= tracker.limit


_RESET_RECOVERY_RULE = """\
# Reset & Recovery Protocol

## When to trigger

- Tests fail after a change and the fix is not obvious within 2 minutes.
- The session has been compacted twice (context is degraded).
- The model is going in circles on the same error.

## Steps

1. **Stash or reset** to the last green commit.
2. **Export** the conversation for cross-model critique.
3. **Hand off** to a fresh session with the critique prompt attached.

## Compaction rule

After **2 compactions**, force a handoff — do not continue in the degraded context.
"""


def get_reset_recovery_rule() -> str:
    """Return the markdown content for the reset-recovery rule."""
    return _RESET_RECOVERY_RULE
