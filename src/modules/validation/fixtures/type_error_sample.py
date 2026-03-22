"""Sample file with a type error for testing."""


def add(a: int, b: int) -> int:
    return "not an int"  # type: ignore[return-value]
