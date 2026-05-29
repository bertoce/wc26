"""Tests for the historical-pattern prior adjustments.

These encode the empirical patterns from past World Cups:
- Only UEFA & CONMEBOL teams have ever won
- Home-continent boost (smaller in 2026 because N.America has no precedent)
- Title pedigree (8 nations have ever won)
- Squad market value as a player-quality proxy
"""

import pytest
from wc26.priors import (
    chemistry_log_odds,
    confederation_log_odds,
    host_continent_log_odds,
    pedigree_log_odds,
    market_value_log_odds,
    apply_priors,
    TeamPriorFeatures,
)


class TestConfederationPrior:
    def test_uefa_positive(self):
        """UEFA teams have won 12/22 World Cups → positive log-odds."""
        assert confederation_log_odds("UEFA") > 0

    def test_conmebol_positive(self):
        """CONMEBOL has won 10/22 → positive log-odds."""
        assert confederation_log_odds("CONMEBOL") > 0

    def test_other_confederations_negative(self):
        """No AFC, CAF, CONCACAF, or OFC team has ever won → strongly negative."""
        for c in ("AFC", "CAF", "CONCACAF", "OFC"):
            assert confederation_log_odds(c) < 0


class TestHostContinentPrior:
    def test_matching_continent_positive(self):
        """A team from the host continent gets a boost."""
        # 2026 is in North America. CONCACAF teams gain a small boost.
        assert host_continent_log_odds(team_continent="North America",
                                       host_continent="North America") > 0

    def test_non_matching_continent_zero(self):
        """A team not from the host continent gets no boost."""
        assert host_continent_log_odds(team_continent="Europe",
                                       host_continent="North America") == pytest.approx(0.0)


class TestPedigreePrior:
    def test_prior_winner_positive(self):
        assert pedigree_log_odds(prior_wins=2, prior_semis=4) > 0

    def test_no_pedigree_zero_or_negative(self):
        assert pedigree_log_odds(prior_wins=0, prior_semis=0) <= 0

    def test_more_pedigree_more_boost(self):
        low = pedigree_log_odds(prior_wins=1, prior_semis=1)
        high = pedigree_log_odds(prior_wins=5, prior_semis=10)
        assert high > low


class TestMarketValuePrior:
    def test_higher_value_higher_log_odds(self):
        """Higher squad market value should give a higher log-odds adjustment."""
        low = market_value_log_odds(squad_value_eur_m=200.0)
        high = market_value_log_odds(squad_value_eur_m=1500.0)
        assert high > low

    def test_median_value_zero(self):
        """The median-valued squad should get ~0 adjustment (centering)."""
        # Median across WC26 teams ~ around €400m. Tolerance loose because we'll center on actual data.
        assert market_value_log_odds(squad_value_eur_m=400.0) == pytest.approx(0.0, abs=0.5)


class TestChemistryPrior:
    """Team chemistry is a small hand-curated bump — 'high' = settled squad
    with coach continuity, 'low' = recent upheaval, 'medium' (or missing) = neutral."""

    def test_high_chemistry_positive(self):
        assert chemistry_log_odds("high") > 0

    def test_medium_chemistry_zero(self):
        assert chemistry_log_odds("medium") == pytest.approx(0.0)

    def test_low_chemistry_negative(self):
        assert chemistry_log_odds("low") < 0

    def test_missing_or_none_is_zero(self):
        """Unknown ratings should be treated as neutral, not penalized."""
        assert chemistry_log_odds(None) == pytest.approx(0.0)
        assert chemistry_log_odds("") == pytest.approx(0.0)
        assert chemistry_log_odds("unknown") == pytest.approx(0.0)

    def test_high_greater_than_low(self):
        assert chemistry_log_odds("high") > chemistry_log_odds("low")

    def test_magnitude_modest(self):
        """The bump should be modest — chemistry is seasoning, not the main course.
        |log_odds| should stay below 0.25 so a single rating can't flip a
        prediction's ordering by more than ~30% relative."""
        assert abs(chemistry_log_odds("high")) <= 0.25
        assert abs(chemistry_log_odds("low")) <= 0.25


class TestApplyPriors:
    def test_returns_normalized_probabilities(self):
        """After applying priors and renormalizing, probs must sum to 1."""
        base = {
            "ARG": 0.20,
            "BRA": 0.18,
            "FRA": 0.15,
            "ENG": 0.12,
            "MEX": 0.05,
            "JPN": 0.03,
            "MAR": 0.02,
            "OTHER": 0.25,
        }
        features = {
            "ARG": TeamPriorFeatures(confederation="CONMEBOL", continent="South America",
                                     prior_wins=3, prior_semis=5, squad_value_eur_m=800),
            "BRA": TeamPriorFeatures(confederation="CONMEBOL", continent="South America",
                                     prior_wins=5, prior_semis=12, squad_value_eur_m=900),
            "FRA": TeamPriorFeatures(confederation="UEFA", continent="Europe",
                                     prior_wins=2, prior_semis=7, squad_value_eur_m=1100),
            "ENG": TeamPriorFeatures(confederation="UEFA", continent="Europe",
                                     prior_wins=1, prior_semis=2, squad_value_eur_m=1300),
            "MEX": TeamPriorFeatures(confederation="CONCACAF", continent="North America",
                                     prior_wins=0, prior_semis=0, squad_value_eur_m=150),
            "JPN": TeamPriorFeatures(confederation="AFC", continent="Asia",
                                     prior_wins=0, prior_semis=0, squad_value_eur_m=200),
            "MAR": TeamPriorFeatures(confederation="CAF", continent="Africa",
                                     prior_wins=0, prior_semis=1, squad_value_eur_m=250),
            "OTHER": TeamPriorFeatures(confederation="UEFA", continent="Europe",
                                       prior_wins=0, prior_semis=0, squad_value_eur_m=300),
        }
        adjusted = apply_priors(base, features, host_continent="North America")
        assert sum(adjusted.values()) == pytest.approx(1.0, abs=1e-6)
        # All probs remain non-negative
        assert all(p >= 0 for p in adjusted.values())

    def test_uefa_team_with_pedigree_gains_relative_share(self):
        """A high-pedigree UEFA team should gain relative share vs a no-pedigree AFC team."""
        base = {"FRA": 0.5, "JPN": 0.5}
        features = {
            "FRA": TeamPriorFeatures(confederation="UEFA", continent="Europe",
                                     prior_wins=2, prior_semis=7, squad_value_eur_m=1100),
            "JPN": TeamPriorFeatures(confederation="AFC", continent="Asia",
                                     prior_wins=0, prior_semis=0, squad_value_eur_m=200),
        }
        adjusted = apply_priors(base, features, host_continent="North America")
        assert adjusted["FRA"] > 0.5
        assert adjusted["JPN"] < 0.5

    def test_chemistry_shifts_otherwise_equal_teams(self):
        """Two teams with identical baselines & priors should diverge purely on chemistry."""
        base = {"A": 0.5, "B": 0.5}
        common = {"confederation": "UEFA", "continent": "Europe",
                  "prior_wins": 0, "prior_semis": 0, "squad_value_eur_m": 400}
        features = {
            "A": TeamPriorFeatures(**common, chemistry="high"),
            "B": TeamPriorFeatures(**common, chemistry="low"),
        }
        adjusted = apply_priors(base, features, host_continent="North America")
        assert adjusted["A"] > 0.5
        assert adjusted["B"] < 0.5

    def test_chemistry_default_does_not_shift(self):
        """If chemistry is left unset (default None), it should produce 0 bump."""
        base = {"A": 0.5, "B": 0.5}
        common = {"confederation": "UEFA", "continent": "Europe",
                  "prior_wins": 0, "prior_semis": 0, "squad_value_eur_m": 400}
        features = {
            "A": TeamPriorFeatures(**common),
            "B": TeamPriorFeatures(**common),
        }
        adjusted = apply_priors(base, features, host_continent="North America")
        assert adjusted["A"] == pytest.approx(0.5)
        assert adjusted["B"] == pytest.approx(0.5)
