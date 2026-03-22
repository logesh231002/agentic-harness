"""Tournament Ralph Loop: parallel implementation with Chairman judge."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum


class TournamentError(Exception):
    """Raised when a tournament operation fails."""


class TournamentSize(Enum):
    SOLO = 1
    PAIR = 2
    FULL = 4


@dataclass(frozen=True)
class TournamentEntry:
    agent_id: str
    worktree_path: str
    compiled: bool
    tests_passed: bool
    diff: str


@dataclass(frozen=True)
class JudgeResult:
    selected_agent: str
    rationale: str
    combined: bool


@dataclass(frozen=True)
class TournamentResult:
    entries: Sequence[TournamentEntry]
    qualified: Sequence[TournamentEntry]
    disqualified: Sequence[TournamentEntry]
    judge_result: JudgeResult | None
    qa_approved: bool


@dataclass(frozen=True)
class TournamentConfig:
    default_size: TournamentSize = TournamentSize.PAIR
    max_turns: int = 3


_LABEL_TO_SIZE: dict[str, TournamentSize] = {
    "tournament:full": TournamentSize.FULL,
    "tournament:pair": TournamentSize.PAIR,
    "tournament:solo": TournamentSize.SOLO,
}


def parse_tournament_size(labels: Sequence[str]) -> TournamentSize:
    for label in labels:
        normalized = label.strip().lower()
        if normalized in _LABEL_TO_SIZE:
            return _LABEL_TO_SIZE[normalized]
    return TournamentSize.PAIR


def auto_classify_size(story_points: int, file_count: int, dep_count: int) -> TournamentSize:
    if story_points > 8 or file_count > 10 or dep_count > 5:
        return TournamentSize.FULL
    if story_points > 3 or file_count > 3 or dep_count > 2:
        return TournamentSize.PAIR
    return TournamentSize.SOLO


def get_worktree_count(size: TournamentSize) -> int:
    return size.value


def filter_qualified(entries: Sequence[TournamentEntry]) -> Sequence[TournamentEntry]:
    return tuple(e for e in entries if e.compiled)


def filter_disqualified(entries: Sequence[TournamentEntry]) -> Sequence[TournamentEntry]:
    return tuple(e for e in entries if not e.compiled)


def build_judge_prompt(issue_title: str, issue_body: str, qualified: Sequence[TournamentEntry]) -> str:
    if not qualified:
        raise TournamentError("Cannot build judge prompt with zero qualified entries.")

    entries_text = "\n\n".join(
        f"### Implementation {i + 1} (agent: {entry.agent_id})\n"
        f"Tests passed: {entry.tests_passed}\n"
        f"```diff\n{entry.diff}\n```"
        for i, entry in enumerate(qualified)
    )

    return (
        f"## Issue\n\n"
        f"**{issue_title}**\n\n"
        f"{issue_body}\n\n"
        f"## Qualifying Implementations\n\n"
        f"{entries_text}\n\n"
        f"## Instructions\n\n"
        f"Select the best implementation or combine elements from multiple entries. "
        f"Provide a clear rationale for your decision."
    )


def create_judge_result(selected_agent: str, rationale: str, combined: bool) -> JudgeResult:
    return JudgeResult(selected_agent=selected_agent, rationale=rationale, combined=combined)


def run_tournament(
    entries: Sequence[TournamentEntry],
    issue_title: str,
    issue_body: str,
) -> TournamentResult:
    if not entries:
        raise TournamentError("Cannot run tournament with zero entries.")

    qualified = filter_qualified(entries)
    disqualified = filter_disqualified(entries)

    if not qualified:
        raise TournamentError("All entries were disqualified — none compiled successfully.")

    return TournamentResult(
        entries=tuple(entries),
        qualified=qualified,
        disqualified=disqualified,
        judge_result=None,
        qa_approved=False,
    )


def approve_qa(result: TournamentResult) -> TournamentResult:
    return replace(result, qa_approved=True)


def is_merge_blocked(result: TournamentResult) -> bool:
    return not result.qa_approved
