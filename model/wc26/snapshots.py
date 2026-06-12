"""Pre-match prediction snapshot store.

Accumulates each fixture's most recent PRE-match prediction across pipeline
runs. Once a fixture is finished, its snapshot freezes — later runs (whose
re-fit model has already absorbed the result) can never retroactively
change what was predicted before kickoff. This keeps the dashboard's
"predicted vs actual" comparison honest.

Persisted in model/data/state/prematch_snapshots.json (git-committed so
the daily CI run accumulates state across days).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .results import result_key

SNAPSHOT_FIELDS = (
    "p_home_win", "p_draw", "p_away_win",
    "expected_home_goals", "expected_away_goals",
)


def load_snapshots(path: Path) -> dict:
    """Load the snapshot store. Returns {} if the file doesn't exist."""
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_snapshots(path: Path, snapshots: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshots, indent=2, sort_keys=True))


def update_snapshots(
    snapshots: dict,
    predictions: list[dict],
    finished_keys: set[str],
) -> dict:
    """Merge this run's fixture predictions into the snapshot store.

    Rules:
      - Fixture NOT finished → overwrite with the latest prediction
        (the pre-match estimate keeps improving until kickoff).
      - Fixture finished AND already snapshotted → keep the stored snapshot
        verbatim (FROZEN — this is the whole point).
      - Fixture finished but never snapshotted → store the current
        prediction flagged post_hoc=True (computed by a model that already
        saw the result; comparison should be taken with a grain of salt).
      - Fixture in the store but absent from this run's predictions → kept.
    """
    out = dict(snapshots)
    for p in predictions:
        key = result_key(p.get("group"), p["home"], p["away"])
        record = {f: p[f] for f in SNAPSHOT_FIELDS if f in p}
        record["snapshot_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if key in finished_keys:
            if key in out:
                continue  # frozen — never overwrite
            record["post_hoc"] = True
            out[key] = record
        else:
            record["post_hoc"] = False
            out[key] = record
    return out
