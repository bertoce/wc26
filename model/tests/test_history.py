"""Tests for the append-only probability history log.

Every pipeline run appends one JSONL line: timestamp, model version,
finished-match count, and each team's adjusted win probability. This gives
an easy-to-query record of how the model's view evolved through the
tournament — no git archaeology needed.
"""

import json
from pathlib import Path

import pytest
from wc26.history import append_history, read_history


def _record(n_finished=2):
    return {
        "generated_at": "2026-06-11T20:00:00Z",
        "model_version": "0.5.0",
        "n_finished_matches": n_finished,
        "win_probability_adjusted": {"ARG": 0.25, "BRA": 0.23, "ENG": 0.15},
    }


class TestAppendHistory:
    def test_creates_file_and_parent_dirs(self, tmp_path: Path):
        path = tmp_path / "state" / "history.jsonl"
        append_history(path, _record())
        assert path.exists()

    def test_appends_one_json_line(self, tmp_path: Path):
        path = tmp_path / "history.jsonl"
        append_history(path, _record())
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["win_probability_adjusted"]["ARG"] == 0.25

    def test_successive_appends_accumulate(self, tmp_path: Path):
        path = tmp_path / "history.jsonl"
        append_history(path, _record(n_finished=0))
        append_history(path, _record(n_finished=2))
        append_history(path, _record(n_finished=5))
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 3
        assert [json.loads(l)["n_finished_matches"] for l in lines] == [0, 2, 5]

    def test_existing_content_never_modified(self, tmp_path: Path):
        path = tmp_path / "history.jsonl"
        append_history(path, _record(n_finished=0))
        first_line_before = path.read_text().split("\n")[0]
        append_history(path, _record(n_finished=2))
        first_line_after = path.read_text().split("\n")[0]
        assert first_line_before == first_line_after


class TestReadHistory:
    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert read_history(tmp_path / "nope.jsonl") == []

    def test_roundtrip(self, tmp_path: Path):
        path = tmp_path / "history.jsonl"
        append_history(path, _record(n_finished=0))
        append_history(path, _record(n_finished=2))
        records = read_history(path)
        assert len(records) == 2
        assert records[1]["n_finished_matches"] == 2
