"""Tests for the expertise store."""

from __future__ import annotations

from pathlib import Path

from src.modules.context.expertise import ExpertiseRecord, query, query_by_file, record


def _make_record(
    domain: str = "testing",
    decision: str = "use pytest",
    reasoning: str = "industry standard",
    outcome: str | None = None,
    related_files: list[str] | None = None,
) -> ExpertiseRecord:
    return ExpertiseRecord(
        timestamp="2026-03-22T10:00:00Z",
        domain=domain,
        decision=decision,
        reasoning=reasoning,
        outcome=outcome,
        related_files=related_files or [],
    )


class TestRecord:
    def test_appends_without_overwrite(self, tmp_path: Path) -> None:
        store = tmp_path / "expertise.jsonl"
        record(store, _make_record(domain="first"))
        record(store, _make_record(domain="second"))

        lines = store.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

    def test_creates_file_if_missing(self, tmp_path: Path) -> None:
        store = tmp_path / "subdir" / "expertise.jsonl"
        assert not store.exists()

        record(store, _make_record())

        assert store.exists()

    def test_preserves_existing_records(self, tmp_path: Path) -> None:
        store = tmp_path / "expertise.jsonl"
        record(store, _make_record(domain="original"))
        record(store, _make_record(domain="added"))

        lines = store.read_text(encoding="utf-8").strip().splitlines()
        assert '"original"' in lines[0]
        assert '"added"' in lines[1]

    def test_record_fields_serialized(self, tmp_path: Path) -> None:
        store = tmp_path / "expertise.jsonl"
        entry = _make_record(
            domain="architecture",
            decision="use dataclasses",
            reasoning="simple and typed",
            outcome="successful",
            related_files=["src/models.py"],
        )
        record(store, entry)

        raw = store.read_text(encoding="utf-8").strip()
        assert '"domain": "architecture"' in raw
        assert '"decision": "use dataclasses"' in raw
        assert '"reasoning": "simple and typed"' in raw
        assert '"outcome": "successful"' in raw
        assert '"related_files": ["src/models.py"]' in raw


class TestQuery:
    def test_returns_relevant_results(self, tmp_path: Path) -> None:
        store = tmp_path / "expertise.jsonl"
        record(store, _make_record(domain="database", decision="use postgres", reasoning="relational data"))
        record(store, _make_record(domain="frontend", decision="use react", reasoning="component model"))
        record(store, _make_record(domain="database", decision="add index", reasoning="query performance"))

        results = query(store, "database query")

        assert len(results) >= 1
        assert results[0].domain == "database"

    def test_returns_empty_for_no_matches(self, tmp_path: Path) -> None:
        store = tmp_path / "expertise.jsonl"
        record(store, _make_record(domain="frontend", decision="use react", reasoning="component model"))

        results = query(store, "xyznonexistentterm")

        assert results == []

    def test_respects_top_k(self, tmp_path: Path) -> None:
        store = tmp_path / "expertise.jsonl"
        for i in range(10):
            record(store, _make_record(domain="testing", decision=f"test decision {i}", reasoning="testing reasoning"))

        results = query(store, "testing", top_k=3)

        assert len(results) == 3

    def test_returns_empty_for_missing_file(self, tmp_path: Path) -> None:
        store = tmp_path / "nonexistent.jsonl"

        results = query(store, "anything")

        assert results == []


class TestQueryByFile:
    def test_finds_records_by_file_path(self, tmp_path: Path) -> None:
        store = tmp_path / "expertise.jsonl"
        record(store, _make_record(domain="arch", related_files=["src/models.py", "src/views.py"]))
        record(store, _make_record(domain="test", related_files=["tests/test_models.py"]))
        record(store, _make_record(domain="arch2", related_files=["src/models.py"]))

        results = query_by_file(store, "src/models.py")

        assert len(results) == 2
        domains = [r.domain for r in results]
        assert "arch" in domains
        assert "arch2" in domains

    def test_returns_empty_when_no_match(self, tmp_path: Path) -> None:
        store = tmp_path / "expertise.jsonl"
        record(store, _make_record(related_files=["src/other.py"]))

        results = query_by_file(store, "src/nonexistent.py")

        assert results == []
