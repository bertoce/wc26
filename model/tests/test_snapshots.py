"""Tests for the pre-match prediction snapshot store.

The point: once a match is FINISHED, its pre-match prediction is FROZEN —
later pipeline runs (with a re-fit model that has absorbed the result)
must never retroactively change what we predicted before kickoff. That's
what makes the dashboard's "how close did the model get?" comparison honest.
"""

import json
from pathlib import Path

import pytest
from wc26.results import result_key
from wc26.snapshots import load_snapshots, save_snapshots, update_snapshots


def _pred(group="A", home="MEX", away="RSA", p_home=0.55, p_draw=0.30, p_away=0.15):
    return {
        "group": group,
        "home": home,
        "away": away,
        "p_home_win": p_home,
        "p_draw": p_draw,
        "p_away_win": p_away,
        "expected_home_goals": 1.31,
        "expected_away_goals": 0.55,
    }


class TestLoadSave:
    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert load_snapshots(tmp_path / "nope.json") == {}

    def test_roundtrip(self, tmp_path: Path):
        p = tmp_path / "snaps.json"
        snaps = {"A:MEX-RSA": {"p_home_win": 0.5, "p_draw": 0.3, "p_away_win": 0.2}}
        save_snapshots(p, snaps)
        assert load_snapshots(p) == snaps


class TestUpdateSnapshots:
    def test_unplayed_fixture_overwritten_with_latest(self):
        """Before a match is played, every run refreshes its snapshot."""
        key = result_key("A", "MEX", "RSA")
        old = {key: {"p_home_win": 0.50, "p_draw": 0.30, "p_away_win": 0.20}}
        updated = update_snapshots(
            old, [_pred(p_home=0.58, p_draw=0.27, p_away=0.15)], finished_keys=set()
        )
        assert updated[key]["p_home_win"] == 0.58

    def test_finished_fixture_frozen(self):
        """Once finished, the stored snapshot survives any later prediction."""
        key = result_key("A", "MEX", "RSA")
        frozen = {key: {"p_home_win": 0.55, "p_draw": 0.30, "p_away_win": 0.15}}
        updated = update_snapshots(
            frozen,
            [_pred(p_home=0.80, p_draw=0.15, p_away=0.05)],  # model re-fit post-result
            finished_keys={key},
        )
        assert updated[key]["p_home_win"] == 0.55  # NOT 0.80

    def test_finished_without_prior_snapshot_marked_post_hoc(self):
        """If a match finished before we ever snapshotted it (e.g. pipeline was
        down), store the current prediction but flag it as post-hoc — it was
        computed by a model that already saw the result."""
        key = result_key("A", "MEX", "RSA")
        updated = update_snapshots({}, [_pred()], finished_keys={key})
        assert updated[key]["post_hoc"] is True

    def test_normal_snapshot_not_marked_post_hoc(self):
        key = result_key("A", "MEX", "RSA")
        updated = update_snapshots({}, [_pred()], finished_keys=set())
        assert updated[key].get("post_hoc", False) is False

    def test_multiple_fixtures_mixed_states(self):
        k_finished = result_key("A", "MEX", "RSA")
        k_upcoming = result_key("A", "KOR", "CZE")
        existing = {
            k_finished: {"p_home_win": 0.55, "p_draw": 0.30, "p_away_win": 0.15},
            k_upcoming: {"p_home_win": 0.36, "p_draw": 0.33, "p_away_win": 0.31},
        }
        preds = [
            _pred(home="MEX", away="RSA", p_home=0.90),       # finished — must stay frozen
            _pred(home="KOR", away="CZE", p_home=0.40),       # upcoming — must refresh
        ]
        updated = update_snapshots(existing, preds, finished_keys={k_finished})
        assert updated[k_finished]["p_home_win"] == 0.55
        assert updated[k_upcoming]["p_home_win"] == 0.40

    def test_snapshot_for_fixture_absent_from_predictions_kept(self):
        """A fixture in the store but missing from this run's predictions
        (e.g. fd.org hiccup) keeps its existing snapshot."""
        key = result_key("A", "MEX", "RSA")
        existing = {key: {"p_home_win": 0.55, "p_draw": 0.30, "p_away_win": 0.15}}
        updated = update_snapshots(existing, [], finished_keys=set())
        assert key in updated
