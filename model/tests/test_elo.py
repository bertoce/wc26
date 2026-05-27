"""Tests for World Football Elo rating system.

References:
- https://www.eloratings.net/about
- Hvattum & Arntzen (2010) "Using ELO ratings for match result prediction in association football"
"""

import math
import pytest
from wc26.elo import (
    INITIAL_RATING,
    expected_score,
    update_ratings,
    run_history,
    Match,
)


class TestExpectedScore:
    def test_equal_ratings_give_half(self):
        """Two equal-rated teams should have 0.5 expected score each."""
        assert expected_score(1500, 1500) == pytest.approx(0.5)

    def test_higher_rating_higher_expectation(self):
        """A 400-point gap → ~91% expected for the stronger side (classic Elo property)."""
        e = expected_score(1900, 1500)
        assert e == pytest.approx(0.9091, abs=0.01)

    def test_symmetry(self):
        """E(A vs B) + E(B vs A) must equal 1."""
        a, b = 1700, 1450
        assert expected_score(a, b) + expected_score(b, a) == pytest.approx(1.0)

    def test_home_advantage_shifts_expectation(self):
        """100-point home advantage should boost expected score."""
        no_adv = expected_score(1500, 1500, home_adv=0)
        with_adv = expected_score(1500, 1500, home_adv=100)
        assert with_adv > no_adv
        assert with_adv == pytest.approx(expected_score(1600, 1500))


class TestUpdateRatings:
    def test_initial_ratings_default(self):
        """Teams should start at INITIAL_RATING (1500 is conventional)."""
        assert INITIAL_RATING == 1500

    def test_draw_between_equals_no_change(self):
        """Equal teams that draw should see no rating change."""
        new_home, new_away = update_ratings(1500, 1500, home_goals=1, away_goals=1)
        assert new_home == pytest.approx(1500, abs=0.01)
        assert new_away == pytest.approx(1500, abs=0.01)

    def test_win_increases_rating(self):
        """A winning team's rating should increase, loser's should decrease, sum preserved."""
        new_home, new_away = update_ratings(1500, 1500, home_goals=2, away_goals=0)
        assert new_home > 1500
        assert new_away < 1500
        # Elo is zero-sum
        assert (new_home + new_away) == pytest.approx(3000, abs=0.01)

    def test_upset_swings_more_than_expected_result(self):
        """A weaker team beating a stronger team should swing more points than the reverse."""
        # Strong team (1800) loses to weak team (1400) — big upset
        strong_after_upset, weak_after_upset = update_ratings(
            1800, 1400, home_goals=0, away_goals=1
        )
        upset_swing = abs(strong_after_upset - 1800)

        # Strong team (1800) beats weak team (1400) — expected result
        strong_after_expected, _ = update_ratings(
            1800, 1400, home_goals=1, away_goals=0
        )
        expected_swing = abs(strong_after_expected - 1800)

        assert upset_swing > expected_swing

    def test_goal_difference_multiplier(self):
        """A bigger goal margin should cause a bigger rating swing (World Football Elo)."""
        narrow_winner, _ = update_ratings(1500, 1500, home_goals=1, away_goals=0)
        blowout_winner, _ = update_ratings(1500, 1500, home_goals=5, away_goals=0)
        assert (blowout_winner - 1500) > (narrow_winner - 1500)

    def test_match_importance_weight(self):
        """Higher match-importance weight should amplify the rating change."""
        friendly_winner, _ = update_ratings(
            1500, 1500, home_goals=1, away_goals=0, match_weight=20
        )
        wc_winner, _ = update_ratings(
            1500, 1500, home_goals=1, away_goals=0, match_weight=60
        )
        assert (wc_winner - 1500) > (friendly_winner - 1500)


class TestRunHistory:
    def test_empty_history_returns_empty_ratings(self):
        ratings = run_history([])
        assert ratings == {}

    def test_deterministic(self):
        """Same matches in same order should produce the same final ratings."""
        matches = [
            Match(date="2020-01-01", home="A", away="B", home_goals=2, away_goals=1,
                  tournament="friendly", neutral=False),
            Match(date="2020-02-01", home="B", away="C", home_goals=0, away_goals=0,
                  tournament="friendly", neutral=False),
            Match(date="2020-03-01", home="A", away="C", home_goals=3, away_goals=0,
                  tournament="friendly", neutral=False),
        ]
        r1 = run_history(matches)
        r2 = run_history(matches)
        assert r1 == r2

    def test_consistently_winning_team_climbs(self):
        """A team that wins every match should end up the highest-rated."""
        matches = [
            Match(date=f"2020-01-{i:02d}", home="A", away="B",
                  home_goals=2, away_goals=0, tournament="friendly", neutral=False)
            for i in range(1, 21)
        ]
        ratings = run_history(matches)
        assert ratings["A"] > ratings["B"]
        assert ratings["A"] > INITIAL_RATING
        assert ratings["B"] < INITIAL_RATING

    def test_new_team_starts_at_initial(self):
        """A team's first match starts from INITIAL_RATING.

        Use a neutral-venue draw between equals so the rating doesn't shift at all
        (any home-advantage at a non-neutral venue would move the home team off 1500).
        """
        matches = [
            Match(date="2020-01-01", home="A", away="B",
                  home_goals=1, away_goals=1, tournament="friendly", neutral=True),
        ]
        ratings = run_history(matches)
        assert "A" in ratings and "B" in ratings
        assert ratings["A"] == pytest.approx(INITIAL_RATING, abs=0.01)
        assert ratings["B"] == pytest.approx(INITIAL_RATING, abs=0.01)
