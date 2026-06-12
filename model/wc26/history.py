"""Append-only probability history log.

One JSONL line per pipeline run: timestamp, model version, finished-match
count, per-team adjusted win probabilities. Lives in model/data/state/
(git-committed) so the tournament's full probability evolution is queryable
without digging through git history of predictions.json.

Usage to pull the data later:
    from wc26.history import read_history
    records = read_history(Path("model/data/state/probability_history.jsonl"))
    # → [{generated_at, model_version, n_finished_matches,
    #     win_probability_adjusted: {TLA: prob, ...}}, ...]
"""

from __future__ import annotations

import json
from pathlib import Path


def append_history(path: Path, record: dict) -> None:
    """Append one record as a JSON line. Never modifies existing content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def read_history(path: Path) -> list[dict]:
    """Read all records. Returns [] if the file doesn't exist."""
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text().strip().split("\n")
        if line.strip()
    ]
