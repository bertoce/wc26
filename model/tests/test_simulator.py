"""Tests for the tournament simulator: group stage, knockouts, shootouts."""

import numpy as np
import pytest
from wc26.simulator import (
    GroupStanding,
    sort_group,
    simulate_match,
    simulate_knockout_match,
    simulate_tournament,
    predict_group_fixtures,
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


class TestPredictGroupFixtures:
    """Per-fixture deterministic W/D/L predictions for the group stage."""

    @pytest.fixture
    def field(self):
        teams = [
            Team(code="STR", name="Strong", attack=0.6, defence=-0.6, confederation="UEFA"),
            Team(code="GD2", name="Good", attack=0.2, defence=-0.2, confederation="UEFA"),
            Team(code="AVG", name="Average", attack=0.0, defence=0.0, confederation="AFC"),
            Team(code="WK1", name="Weak", attack=-0.5, defence=0.5, confederation="CAF"),
        ]
        fixtures = [
            Fixture(home="STR", away="WK1", neutral=True, stage="group", group="A"),
            Fixture(home="GD2", away="AVG", neutral=True, stage="group", group="A"),
            Fixture(home="WK1", away="STR", neutral=True, stage="group", group="A"),
        ]
        return teams, fixtures

    def test_returns_one_prediction_per_fixture(self, field):
        teams, fixtures = field
        preds = predict_group_fixtures(
            fixtures=fixtures,
            teams_by_code={t.code: t for t in teams},
            home_advantage=0.25,
            rho=-0.1,
        )
        assert len(preds) == len(fixtures)

    def test_probabilities_sum_to_one(self, field):
        teams, fixtures = field
        preds = predict_group_fixtures(
            fixtures=fixtures,
            teams_by_code={t.code: t for t in teams},
            home_advantage=0.25,
            rho=-0.1,
        )
        for p in preds:
            assert (p["p_home_win"] + p["p_draw"] + p["p_away_win"]) == pytest.approx(1.0, abs=1e-3)

    def test_stronger_team_more_likely_to_win(self, field):
        teams, fixtures = field
        preds = predict_group_fixtures(
            fixtures=fixtures,
            teams_by_code={t.code: t for t in teams},
            home_advantage=0.25,
            rho=-0.1,
        )
        # STR vs WK1 — home: STR much stronger
        str_vs_wk1 = next(p for p in preds if p["home"] == "STR" and p["away"] == "WK1")
        assert str_vs_wk1["p_home_win"] > 0.7
        assert str_vs_wk1["p_away_win"] < 0.1

    def test_expected_goals_present_and_positive(self, field):
        teams, fixtures = field
        preds = predict_group_fixtures(
            fixtures=fixtures,
            teams_by_code={t.code: t for t in teams},
            home_advantage=0.25,
            rho=-0.1,
        )
        for p in preds:
            assert p["expected_home_goals"] > 0
            assert p["expected_away_goals"] > 0

    def test_only_group_stage_fixtures_returned(self):
        """Non-group fixtures (knockouts placeholders) should be skipped."""
        teams = [
            Team(code="A", name="A", attack=0.0, defence=0.0),
            Team(code="B", name="B", attack=0.0, defence=0.0),
        ]
        fixtures = [
            Fixture(home="A", away="B", neutral=True, stage="group", group="A"),
            Fixture(home="A", away="B", neutral=True, stage="final"),
        ]
        preds = predict_group_fixtures(
            fixtures=fixtures,
            teams_by_code={t.code: t for t in teams},
            home_advantage=0.0,
            rho=0.0,
        )
        assert len(preds) == 1


class TestRoundSurvival:
    """Per-team probabilities of reaching each round of the tournament."""

    @pytest.fixture
    def tiny_field(self):
        teams = [
            Team(code="STR", name="Strong", attack=0.6, defence=-0.6, confederation="UEFA"),
            Team(code="GD2", name="Good", attack=0.2, defence=-0.2, confederation="UEFA"),
            Team(code="AVG", name="Average", attack=0.0, defence=0.0, confederation="AFC"),
            Team(code="WK1", name="Weak", attack=-0.5, defence=0.5, confederation="CAF"),
        ]
        fixtures = [
            Fixture(home="STR", away="GD2", neutral=True, stage="group"),
            Fixture(home="STR", away="AVG", neutral=True, stage="group"),
            Fixture(home="STR", away="WK1", neutral=True, stage="group"),
            Fixture(home="GD2", away="AVG", neutral=True, stage="group"),
            Fixture(home="GD2", away="WK1", neutral=True, stage="group"),
            Fixture(home="AVG", away="WK1", neutral=True, stage="group"),
        ]
        return teams, fixtures

    def test_simulator_returns_round_survival(self, tiny_field):
        teams, fixtures = tiny_field
        results = simulate_tournament(
            teams=teams, fixtures=fixtures, n_sims=500, seed=7,
        )
        assert "round_survival" in results
        # Keyed by team code, then by remaining-teams-count
        for t in teams:
            assert t.code in results["round_survival"]

    def test_round_survival_monotonically_decreasing(self, tiny_field):
        teams, fixtures = tiny_field
        results = simulate_tournament(
            teams=teams, fixtures=fixtures, n_sims=1000, seed=7,
        )
        for tla, survival in results["round_survival"].items():
            # survival[k] = P(team still in tournament when k teams remain)
            # As k decreases, survival should weakly decrease.
            keys_sorted_desc = sorted(survival.keys(), reverse=True)
            values = [survival[k] for k in keys_sorted_desc]
            for i in range(len(values) - 1):
                assert values[i] >= values[i + 1] - 0.001, (
                    f"survival broke monotonicity for {tla}: "
                    f"{dict(zip(keys_sorted_desc, values))}"
                )

    def test_final_round_survival_equals_win_probability(self, tiny_field):
        teams, fixtures = tiny_field
        results = simulate_tournament(
            teams=teams, fixtures=fixtures, n_sims=1000, seed=7,
        )
        for tla in [t.code for t in teams]:
            survival = results["round_survival"][tla]
            assert survival[1] == pytest.approx(
                results["win_probability"][tla], abs=1e-6
            )


class TestBracketSeeding:
    """Standard tournament seeding pairs strong vs weak in R32 — not adjacent
    advancers in the order they came out of groups."""

    def test_seed_order_2(self):
        from wc26.simulator import bracket_seed_order
        assert bracket_seed_order(2) == [1, 2]

    def test_seed_order_4(self):
        from wc26.simulator import bracket_seed_order
        assert bracket_seed_order(4) == [1, 4, 2, 3]

    def test_seed_order_8(self):
        from wc26.simulator import bracket_seed_order
        assert bracket_seed_order(8) == [1, 8, 4, 5, 2, 7, 3, 6]

    def test_seed_order_32_top_seeds_separated(self):
        """Seeds 1 and 2 should be in opposite halves — meeting only in the final."""
        from wc26.simulator import bracket_seed_order
        order = bracket_seed_order(32)
        assert len(order) == 32
        assert order.index(1) < 16
        assert order.index(2) >= 16

    def test_seed_order_pairs_top_with_bottom(self):
        """In standard seeding, seed N's first opponent is seed (32 - N + 1)."""
        from wc26.simulator import bracket_seed_order
        order = bracket_seed_order(32)
        # Pairs are adjacent indices: (order[0], order[1]), (order[2], order[3]), ...
        for i in range(0, 32, 2):
            high, low = order[i], order[i + 1]
            assert high + low == 33, f"pair ({high}, {low}) doesn't sum to 33"


class TestSeededBracketSimulation:
    """End-to-end: with seeded bracket, the strongest team faces a low seed
    in R32 (not a fellow group winner)."""

    @pytest.fixture
    def twelve_groups(self):
        """48 teams, 12 groups of 4, designed so STR0 is clearly best."""
        teams = []
        fixtures = []
        for g_idx, group in enumerate("ABCDEFGHIJKL"):
            # Each group has a strong (S), medium (M), and two weak teams (W1, W2)
            s = Team(code=f"S{g_idx:02d}", name=f"Strong-{group}",
                     attack=0.4 + g_idx * 0.01, defence=-0.4, confederation="UEFA")
            m = Team(code=f"M{g_idx:02d}", name=f"Mid-{group}",
                     attack=0.0, defence=0.0, confederation="UEFA")
            w1 = Team(code=f"X{g_idx:02d}", name=f"Weak1-{group}",
                      attack=-0.4, defence=0.4, confederation="CAF")
            w2 = Team(code=f"Y{g_idx:02d}", name=f"Weak2-{group}",
                      attack=-0.5, defence=0.5, confederation="CAF")
            teams.extend([s, m, w1, w2])
            ts = [s, m, w1, w2]
            for i, h in enumerate(ts):
                for a in ts[i + 1:]:
                    fixtures.append(Fixture(
                        home=h.code, away=a.code, neutral=True,
                        stage="group", group=group,
                    ))
        return teams, fixtures

    def test_top_seed_avoids_same_group_in_r32(self, twelve_groups):
        """Across many sims, the R32 matchups for the best winner should
        almost never include a team from their own group."""
        teams, fixtures = twelve_groups
        results = simulate_tournament(
            teams=teams, fixtures=fixtures, n_sims=200, seed=99,
            qualifiers_per_group=2, best_thirds=8,
        )
        # For each R32 match, find pairs and check no same-group rematches
        # Same-group teams share the same letter prefix index (e.g., S00 and M00 both end with "00")
        same_group_count = 0
        total_matchups = 0
        for match_idx, matchups in results["matchup_distribution"].get(32, {}).items():
            for (h, a), p in matchups.items():
                # Group is the last 2 chars (e.g., "00" through "11")
                if h[-2:] == a[-2:]:
                    same_group_count += p
                total_matchups += p
        same_group_rate = same_group_count / max(total_matchups, 1)
        assert same_group_rate < 0.05, (
            f"Same-group R32 rematches at {same_group_rate:.2%} — seeding not working"
        )
    """Per-slot matchup distribution across all sims — used to build the
    most-likely-bracket forecast."""

    @pytest.fixture
    def tiny_field(self):
        teams = [
            Team(code="STR", name="Strong", attack=0.6, defence=-0.6, confederation="UEFA"),
            Team(code="GD2", name="Good", attack=0.2, defence=-0.2, confederation="UEFA"),
            Team(code="AVG", name="Average", attack=0.0, defence=0.0, confederation="AFC"),
            Team(code="WK1", name="Weak", attack=-0.5, defence=0.5, confederation="CAF"),
        ]
        fixtures = [
            Fixture(home="STR", away="GD2", neutral=True, stage="group"),
            Fixture(home="STR", away="AVG", neutral=True, stage="group"),
            Fixture(home="STR", away="WK1", neutral=True, stage="group"),
            Fixture(home="GD2", away="AVG", neutral=True, stage="group"),
            Fixture(home="GD2", away="WK1", neutral=True, stage="group"),
            Fixture(home="AVG", away="WK1", neutral=True, stage="group"),
        ]
        return teams, fixtures

    def test_simulator_returns_matchup_distribution(self, tiny_field):
        teams, fixtures = tiny_field
        results = simulate_tournament(
            teams=teams, fixtures=fixtures, n_sims=500, seed=11,
        )
        assert "matchup_distribution" in results

    def test_matchup_probs_sum_to_one_per_match(self, tiny_field):
        """For every (round_size, match_idx), the matchup probabilities sum to 1
        — exactly one matchup happens at that bracket position per sim."""
        teams, fixtures = tiny_field
        results = simulate_tournament(
            teams=teams, fixtures=fixtures, n_sims=2000, seed=11,
        )
        dist = results["matchup_distribution"]
        for round_size, by_match in dist.items():
            for match_idx, matchups in by_match.items():
                total = sum(matchups.values())
                assert total == pytest.approx(1.0, abs=0.01), (
                    f"round_size={round_size} match_idx={match_idx} "
                    f"matchup probs sum to {total:.4f}, not 1.0"
                )

    def test_dominant_team_most_likely_in_some_slot(self, tiny_field):
        """STR should appear as the home or away side in the most-likely final
        matchup more than 50% of the time."""
        teams, fixtures = tiny_field
        results = simulate_tournament(
            teams=teams, fixtures=fixtures, n_sims=2000, seed=11,
        )
        dist = results["matchup_distribution"]
        # Final round has size=2, match_idx=0
        final_matchups = dist.get(2, {}).get(0, {})
        str_appears = sum(
            p for (h, a), p in final_matchups.items() if "STR" in (h, a)
        )
        assert str_appears > 0.6, f"STR appears in only {str_appears:.2%} of finals"
