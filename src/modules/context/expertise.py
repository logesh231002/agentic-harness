"""Expertise store: append-only JSONL store with BM25 text search."""

from __future__ import annotations

import fcntl
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path


class ExpertiseError(Exception):
    """Raised when the expertise store encounters an unrecoverable error."""


@dataclass(frozen=True)
class ExpertiseRecord:
    timestamp: str
    domain: str
    decision: str
    reasoning: str
    outcome: str | None
    related_files: list[str]


def record(store_path: Path, entry: ExpertiseRecord) -> None:
    """Append one JSON line to the JSONL file.

    Creates the file if it doesn't exist.  Uses file locking for concurrent
    write safety.  Never overwrites existing records — append-only invariant.
    """
    store_path.parent.mkdir(parents=True, exist_ok=True)
    with open(store_path, "a", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            fh.write(json.dumps(asdict(entry)) + "\n")
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _load_records(store_path: Path) -> list[ExpertiseRecord]:
    if not store_path.exists():
        return []

    records: list[ExpertiseRecord] = []
    raw = store_path.read_text(encoding="utf-8")
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        data: dict[str, object] = json.loads(stripped)
        raw_files = data.get("related_files")
        files_list: list[str] = [str(f) for f in raw_files] if isinstance(raw_files, list) else []
        records.append(
            ExpertiseRecord(
                timestamp=str(data["timestamp"]),
                domain=str(data["domain"]),
                decision=str(data["decision"]),
                reasoning=str(data["reasoning"]),
                outcome=str(data["outcome"]) if data.get("outcome") is not None else None,
                related_files=files_list,
            )
        )
    return records


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


def _build_search_text(rec: ExpertiseRecord) -> str:
    return f"{rec.domain} {rec.decision} {rec.reasoning}"


def _bm25_score(
    query_tokens: list[str],
    doc_tokens: list[str],
    doc_freq: dict[str, int],
    num_docs: int,
    avg_dl: float,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    """BM25: IDF = log((N - df + 0.5) / (df + 0.5) + 1), TF normalized by doc length."""
    dl = len(doc_tokens)
    tf_map: dict[str, int] = {}
    for token in doc_tokens:
        tf_map[token] = tf_map.get(token, 0) + 1

    score = 0.0
    for term in query_tokens:
        if term not in tf_map:
            continue
        tf = tf_map[term]
        df = doc_freq.get(term, 0)
        idf = math.log((num_docs - df + 0.5) / (df + 0.5) + 1)
        tf_component = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl)) if avg_dl > 0 else 0.0
        score += idf * tf_component
    return score


def query(store_path: Path, search_text: str, top_k: int = 5) -> list[ExpertiseRecord]:
    """BM25 text search across all records.

    Searches ``domain``, ``decision``, and ``reasoning`` fields.
    Returns top-K matches sorted by relevance score (descending).
    """
    records = _load_records(store_path)
    if not records:
        return []

    query_tokens = _tokenize(search_text)
    if not query_tokens:
        return []

    doc_tokens_list: list[list[str]] = [_tokenize(_build_search_text(r)) for r in records]
    num_docs = len(records)
    avg_dl = sum(len(dt) for dt in doc_tokens_list) / num_docs if num_docs > 0 else 0.0

    doc_freq: dict[str, int] = {}
    for dt in doc_tokens_list:
        seen: set[str] = set()
        for token in dt:
            if token not in seen:
                doc_freq[token] = doc_freq.get(token, 0) + 1
                seen.add(token)

    scored: list[tuple[float, int]] = []
    for idx, dt in enumerate(doc_tokens_list):
        score = _bm25_score(query_tokens, dt, doc_freq, num_docs, avg_dl)
        if score > 0:
            scored.append((score, idx))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [records[idx] for _, idx in scored[:top_k]]


def query_by_file(store_path: Path, file_path: str) -> list[ExpertiseRecord]:
    """Return all records whose ``related_files`` contain the given path."""
    records = _load_records(store_path)
    return [r for r in records if file_path in r.related_files]
