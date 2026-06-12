"""Tests for extracting finished match results from football-data.org data.

During the tournament, fd.org flips matches from status TIMED to FINISHED
and fills in score.fullTime. We turn those into known-result dicts the
simulator can lock in.
"""

import pytest
from wc26.results import extract_finished_group_results, result_key


def _fd_match(
    home_tla="MEX",
    away_tla="RSA",
    status="FINISHED",
    stage="GROUP_STAGE",
    group="GROUP_A",
    home_goals=2,
    away_goals=0,
):
    """Minimal fd.org-shaped match record."""
    return {
        "status": status,
        "stage": stage,
        "group": group,
        "utcDate": "2026-06-11T19:00:00Z",
        "homeTeam": {"tla": home_tla, "name": home_tla},
        "awayTeam": {"tla": away_tla, "name": away_tla},
        "score": {
            "winner": None,
            "duration": "REGULAR",
            "fullTime": {"home": home_goals, "away": away_goals},
        },
    }


class TestExtractFinishedGroupResults:
    def test_extracts_finished_match(self):
        results = extract_finished_group_results([_fd_match()])
        assert len(results) == 1
        r = results[0]
        assert r["home"] == "MEX"
        assert r["away"] == "RSA"
        assert r["home_goals"] == 2
        assert r["away_goals"] == 0
        assert r["group"] == "A"

    def test_ignores_unplayed_matches(self):
        for status in ("TIMED", "SCHEDULED", "IN_PLAY", "PAUSED", "POSTPONED", "CANCELLED"):
            results = extract_finished_group_results([_fd_match(status=status)])
            assert results == [], f"status={status} should not produce a result"

    def test_ignores_knockout_matches(self):
        results = extract_finished_group_results(
            [_fd_match(stage="LAST_32", group=None)]
        )
        assert results == []

    def test_ignores_matches_missing_tla(self):
        m = _fd_match()
        m["homeTeam"]["tla"] = None
        assert extract_finished_group_results([m]) == []

    def test_ignores_matches_missing_score(self):
        m = _fd_match()
        m["score"]["fullTime"] = {"home": None, "away": None}
        assert extract_finished_group_results([m]) == []

    def test_multiple_matches_mixed_statuses(self):
        matches = [
            _fd_match(home_tla="MEX", away_tla="RSA", status="FINISHED"),
            _fd_match(home_tla="KOR", away_tla="CZE", status="TIMED"),
            _fd_match(home_tla="CAN", away_tla="BIH", group="GROUP_B",
                      status="FINISHED", home_goals=1, away_goals=1),
        ]
        results = extract_finished_group_results(matches)
        assert len(results) == 2
        keys = {(r["home"], r["away"]) for r in results}
        assert keys == {("MEX", "RSA"), ("CAN", "BIH")}

    def test_draw_scores_preserved(self):
        results = extract_finished_group_results(
            [_fd_match(home_goals=1, away_goals=1)]
        )
        assert results[0]["home_goals"] == 1
        assert results[0]["away_goals"] == 1


class TestResultKey:
    def test_key_is_stable_and_unique_per_fixture(self):
        assert result_key("A", "MEX", "RSA") == "A:MEX-RSA"

    def test_key_distinguishes_home_away_order(self):
        """MEX vs RSA is a different fixture from RSA vs MEX."""
        assert result_key("A", "MEX", "RSA") != result_key("A", "RSA", "MEX")

    def test_key_handles_none_group(self):
        assert result_key(None, "MEX", "RSA") == "?:MEX-RSA"
