"""Tests for the tournament simulator: group stage, knockouts, shootouts."""

import numpy as np
import pytest
from wc26.simulator import (
    GroupStanding,
    sort_group,
    simulate_match,
    simulate_knockout_match,
    simulate_tournament,
    Team,
    Fixture,
)


class TestGroupTiebreakers:
    def test_more_points_advances(self):
        s = [
            GroupStanding(team="A", played=3, wins=1, draws=1, losses=1, gf=3, ga=3),
            GroupStanding(team="B", played=3, wins=2, draws=1, losses=0, gf=4, ga=1),
            GroupStanding(team="C", played=3, wins=2, draws=0, losses=1, gf=5, ga=3),
            GroupStanding(team="D", played=3, wins=0, draws=0, losses=3, gf=1, ga=6),
        ]
        ranked = sort_group(s)
        assert ranked[0].team == "B"  # 7 points
        # C and A: 6 vs 4

    def test_goal_difference_breaks_tie(self):
        """Same points → better goal difference advances."""
        s = [
            GroupStanding(team="A", played=3, wins=2, draws=0, losses=1, gf=5, ga=3),  # 6pts, +2
            GroupStanding(team="B", played=3, wins=2, draws=0, losses=1, gf=7, ga=2),  # 6pts, +5
        ]
        ranked = sort_group(s)
        assert ranked[0].team == "B"

    def test_goals_scored_breaks_gd_tie(self):
        """Same points + same GD → more goals scored advances."""
        s = [
            GroupStanding(team="A", played=3, wins=2, draws=0, losses=1, gf=3, ga=1),  # 6pts, +2, 3 GF
            GroupStanding(team="B", played=3, wins=2, draws=0, losses=1, gf=5, ga=3),  # 6pts, +2, 5 GF
        ]
        ranked = sort_group(s)
        assert ranked[0].team == "B"


class TestSimulateMatch:
    def test_returns_nonneg_integers(self):
        rng = np.random.default_rng(0)
        hg, ag = simulate_match(lam_home=1.5, lam_away=1.0, rng=rng)
        assert isinstance(hg, (int, np.integer)) and hg >= 0
        assert isinstance(ag, (int, np.integer)) and ag >= 0

    def test_expected_goal_count_matches_lambda(self):
        """Mean of many samples should converge to lambda."""
        rng = np.random.default_rng(0)
        samples = [simulate_match(lam_home=2.0, lam_away=0.5, rng=rng) for _ in range(5000)]
        mean_home = np.mean([s[0] for s in samples])
        mean_away = np.mean([s[1] for s in samples])
        assert mean_home == pytest.approx(2.0, abs=0.1)
        assert mean_away == pytest.approx(0.5, abs=0.05)


class TestKnockout:
    def test_no_draw_returned(self):
        """A knockout match must produce a winner (after ET + shootout if needed)."""
        rng = np.random.default_rng(0)
        for _ in range(100):
            winner, _, _ = simulate_knockout_match(
                home="A", away="B", lam_home=1.0, lam_away=1.0, rng=rng
            )
            assert winner in ("A", "B")

    def test_shootout_50_50_for_equal_teams(self):
        """For two equal teams forced to shootout, each should win ~50%."""
        rng = np.random.default_rng(0)
        a_wins = 0
        n = 1000
        for _ in range(n):
            winner, _, _ = simulate_knockout_match(
                home="A", away="B", lam_home=1.0, lam_away=1.0, rng=rng
            )
            if winner == "A":
                a_wins += 1
        # Some home edge possible from lam_home being treated as such — but with equal lambdas
        # and balanced strengths, A should win in roughly 50% of cases.
        assert 0.42 < (a_wins / n) < 0.58


class TestSimulateTournament:
    @pytest.fixture
    def tiny_field(self):
        """4-team field, 1 group, top 2 to a final.

        Dixon-Coles convention: defence β is "leakiness" — higher β means the team
        concedes more, so a strong team has high attack and *low* defence.
        """
        teams = [
            Team(code="STR", name="Strong", attack=0.6, defence=-0.6, confederation="UEFA"),
            Team(code="GD2", name="Good", attack=0.2, defence=-0.2, confederation="UEFA"),
            Team(code="AVG", name="Average", attack=0.0, defence=0.0, confederation="AFC"),
            Team(code="WK1", name="Weak", attack=-0.5, defence=0.5, confederation="CAF"),
        ]
        # Round-robin group fixtures
        fixtures = [
            Fixture(home="STR", away="GD2", neutral=True, stage="group"),
            Fixture(home="STR", away="AVG", neutral=True, stage="group"),
            Fixture(home="STR", away="WK1", neutral=True, stage="group"),
            Fixture(home="GD2", away="AVG", neutral=True, stage="group"),
            Fixture(home="GD2", away="WK1", neutral=True, stage="group"),
            Fixture(home="AVG", away="WK1", neutral=True, stage="group"),
        ]
        return teams, fixtures

    def test_runs_without_error(self, tiny_field):
        teams, fixtures = tiny_field
        results = simulate_tournament(
            teams=teams, fixtures=fixtures, n_sims=100, seed=42
        )
        assert "win_probability" in results
        assert sum(results["win_probability"].values()) == pytest.approx(1.0, abs=0.01)

    def test_dominant_team_wins_most(self, tiny_field):
        teams, fixtures = tiny_field
        results = simulate_tournament(
            teams=teams, fixtures=fixtures, n_sims=2000, seed=42
        )
        # The strongest team should win at least 35% — and clearly the most
        win_probs = results["win_probability"]
        assert win_probs["STR"] > 0.35
        assert win_probs["STR"] == max(win_probs.values())

    def test_weak_team_rarely_wins(self, tiny_field):
        teams, fixtures = tiny_field
        results = simulate_tournament(
            teams=teams, fixtures=fixtures, n_sims=2000, seed=42
        )
        assert results["win_probability"]["WK1"] < 0.10

    def test_deterministic_with_seed(self, tiny_field):
        teams, fixtures = tiny_field
        r1 = simulate_tournament(teams=teams, fixtures=fixtures, n_sims=500, seed=123)
        r2 = simulate_tournament(teams=teams, fixtures=fixtures, n_sims=500, seed=123)
        assert r1["win_probability"] == r2["win_probability"]
