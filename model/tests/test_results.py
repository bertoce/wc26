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


class TestKnownResultsToDcMatches:
    """Finished tournament results get injected into the Dixon-Coles fit as
    extra match rows — so team strengths update within minutes of full-time
    instead of waiting days for the historical dataset to catch up."""

    TLA_TO_NAME = {"MEX": "Mexico", "RSA": "South Africa",
                   "KOR": "South Korea", "CZE": "Czech Republic",
                   "BRA": "Brazil"}

    def _kr(self, home="MEX", away="RSA", hg=2, ag=0, utc="2026-06-11T19:00:00Z"):
        return {"home": home, "away": away, "group": "A",
                "home_goals": hg, "away_goals": ag, "utc_date": utc}

    def test_converts_tlas_to_historical_names(self):
        from wc26.results import known_results_to_dc_matches
        rows = known_results_to_dc_matches([self._kr()], self.TLA_TO_NAME, [])
        assert rows[0]["home"] == "Mexico"
        assert rows[0]["away"] == "South Africa"
        assert rows[0]["home_goals"] == 2
        assert rows[0]["away_goals"] == 0

    def test_date_comes_from_utc_date(self):
        from wc26.results import known_results_to_dc_matches
        rows = known_results_to_dc_matches([self._kr()], self.TLA_TO_NAME, [])
        assert rows[0]["date"] == "2026-06-11"

    def test_host_home_match_is_non_neutral(self):
        """Mexico's group match at home gets the home-advantage flag."""
        from wc26.results import known_results_to_dc_matches
        rows = known_results_to_dc_matches([self._kr(home="MEX")], self.TLA_TO_NAME, [])
        assert rows[0]["neutral"] is False

    def test_non_host_match_is_neutral(self):
        from wc26.results import known_results_to_dc_matches
        rows = known_results_to_dc_matches(
            [self._kr(home="KOR", away="CZE")], self.TLA_TO_NAME, [])
        assert rows[0]["neutral"] is True

    def test_dedup_against_existing_historical_rows(self):
        """If the historical CSV already includes the match (same date +
        teams), don't inject a duplicate — it would double-count."""
        from wc26.results import known_results_to_dc_matches
        existing = [{"date": "2026-06-11", "home": "Mexico", "away": "South Africa",
                     "home_goals": 2, "away_goals": 0, "neutral": False}]
        rows = known_results_to_dc_matches([self._kr()], self.TLA_TO_NAME, existing)
        assert rows == []

    def test_unknown_tla_skipped(self):
        from wc26.results import known_results_to_dc_matches
        rows = known_results_to_dc_matches(
            [self._kr(home="XXX")], self.TLA_TO_NAME, [])
        assert rows == []

    def test_multiple_results_mixed(self):
        from wc26.results import known_results_to_dc_matches
        existing = [{"date": "2026-06-11", "home": "Mexico", "away": "South Africa"}]
        rows = known_results_to_dc_matches(
            [self._kr(), self._kr(home="KOR", away="CZE", hg=2, ag=1)],
            self.TLA_TO_NAME, existing)
        assert len(rows) == 1
        assert rows[0]["home"] == "South Korea"


class TestExtractIncludesDate:
    def test_utc_date_present(self):
        m = _fd_match()
        results = extract_finished_group_results([m])
        assert results[0]["utc_date"] == "2026-06-11"


class TestResultKey:
    def test_key_is_stable_and_unique_per_fixture(self):
        assert result_key("A", "MEX", "RSA") == "A:MEX-RSA"

    def test_key_distinguishes_home_away_order(self):
        """MEX vs RSA is a different fixture from RSA vs MEX."""
        assert result_key("A", "MEX", "RSA") != result_key("A", "RSA", "MEX")

    def test_key_handles_none_group(self):
        assert result_key(None, "MEX", "RSA") == "?:MEX-RSA"
