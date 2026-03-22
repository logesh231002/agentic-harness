"""TDD skill: enforces red-green-refactor discipline and provides scoped testing rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from src.modules.context.scoped_rules import ScopedRule


class TddError(Exception):
    """Raised when TDD discipline is violated."""


class TddPhase(Enum):
    """The three phases of the TDD cycle."""

    RED = "red"
    GREEN = "green"
    REFACTOR = "refactor"


@dataclass(frozen=True)
class TddSession:
    """Tracks current TDD phase and enforces one-failing-test-at-a-time discipline."""

    phase: TddPhase
    failing_test: str | None

    @staticmethod
    def start(test_name: str) -> TddSession:
        if not test_name:
            raise TddError("test_name is required to start a TDD session")
        return TddSession(phase=TddPhase.RED, failing_test=test_name)


def advance_phase(session: TddSession, test_passed: bool) -> TddSession:
    """Advance the TDD state machine through red -> green -> refactor.

    State transitions:
        RED   + test fails  -> RED (still working on making the test pass)
        RED   + test passes -> GREEN (the failing test now passes)
        GREEN + test passes -> REFACTOR (all tests still pass, safe to refactor)
        GREEN + test fails  -> error (broke something while implementing)
        REFACTOR + test passes -> REFACTOR (refactoring keeps tests green)
        REFACTOR + test fails  -> error (refactor broke a test)

    Raises:
        TddError: If a test fails during GREEN or REFACTOR phase.
    """
    phase = session.phase

    if phase is TddPhase.RED:
        if test_passed:
            return TddSession(phase=TddPhase.GREEN, failing_test=session.failing_test)
        return session

    if phase is TddPhase.GREEN:
        if test_passed:
            return TddSession(phase=TddPhase.REFACTOR, failing_test=session.failing_test)
        raise TddError("Test failed during GREEN phase — fix the implementation before proceeding")

    # REFACTOR
    if test_passed:
        return session
    raise TddError("Test failed during REFACTOR phase — revert the refactor and try again")


def add_failing_test(session: TddSession, test_name: str) -> TddSession:
    """Start a new RED cycle after completing a previous refactor.

    Only allowed when the current phase is REFACTOR (previous cycle complete).
    Enforces the one-failing-test-at-a-time constraint.

    Raises:
        TddError: If called during RED or GREEN phase, or with empty test_name.
    """
    if not test_name:
        raise TddError("test_name is required")
    if session.phase == TddPhase.RED:
        raise TddError(
            f"Cannot add a new failing test while '{session.failing_test}' is still red"
            " — finish the current cycle first"
        )
    if session.phase == TddPhase.GREEN:
        raise TddError("Cannot add a new failing test during GREEN phase — advance to REFACTOR first")
    return TddSession(phase=TddPhase.RED, failing_test=test_name)


_TESTING_RULE_BODY = """\
# Testing Constraints (Non-Negotiable)

## 1. Mock at Boundaries Only

Mock **only** at system boundaries: network calls, filesystem I/O, subprocesses,
and external services. Never mock internal collaborators, private methods, or
data transformations. If you need to mock an internal function, that's a design
smell — refactor to push the dependency to the boundary.

## 2. Test Behavior, Not Implementation

Tests must verify **observable behavior** through public interfaces. A test that
breaks when you refactor internals (but behavior is unchanged) is a bad test.
Ask: "Would this test still make sense if I rewrote the implementation from
scratch?" If not, rewrite the test.

## 3. Vertical Slices Only

Write ONE failing test, make it pass, then refactor. Never write multiple
failing tests at once. Each red-green-refactor cycle is atomic:

```
RED:   Write ONE test -> it fails
GREEN: Write minimal code -> test passes
REFACTOR: Clean up -> all tests still pass
```

Do NOT write all tests first then all implementation (horizontal slicing).
Each test responds to what you learned from the previous cycle.
"""


def get_testing_rule() -> ScopedRule:
    return ScopedRule(
        source_path=Path("src/modules/tdd/tdd_skill.py"),
        globs=["**/*test*.py"],
        body=_TESTING_RULE_BODY,
    )


_ARCHITECTURE_REVIEW_STUB = (
    "Weekly deep-module review: identify shallow modules that leak complexity "
    "through their interfaces. Look for opportunities to deepen modules by "
    "moving implementation details behind simpler APIs. Priority targets: "
    "modules with high fan-out, thin wrappers that add no abstraction, and "
    "classes whose interface is as complex as their implementation."
)


def get_architecture_review_stub() -> str:
    return _ARCHITECTURE_REVIEW_STUB
