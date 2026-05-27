"""Tests for Dixon-Coles Poisson goals model.

Dixon & Coles (1997) "Modelling Association Football Scores and Inefficiencies
in the Football Betting Market".

The model assigns each team an attack strength α_i and defence strength β_i,
plus a global home advantage γ. Expected goals for team i (home) vs team j (away):
    λ = exp(α_i + β_j + γ)
    μ = exp(α_j + β_i)
Then goals ~ Poisson(λ), Poisson(μ), with a low-score correction τ(0,0), τ(1,0), τ(0,1), τ(1,1).
"""

import numpy as np
import pytest
from wc26.dixon_coles import (
    DixonColesModel,
    score_probabilities,
    match_outcome_probabilities,
)


class TestScoreProbabilities:
    def test_probabilities_sum_to_one(self):
        """Scoreline probabilities up to a high cap should sum to ~1."""
        probs = score_probabilities(lam_home=1.5, lam_away=1.2, rho=0.0, max_goals=10)
        assert probs.sum() == pytest.approx(1.0, abs=1e-3)

    def test_zero_rho_is_independent_poissons(self):
        """With rho=0, joint = product of marginals."""
        from scipy.stats import poisson
        probs = score_probabilities(lam_home=1.0, lam_away=1.0, rho=0.0, max_goals=5)
        # P(2,1) = P(home=2) * P(away=1)
        expected = poisson.pmf(2, 1.0) * poisson.pmf(1, 1.0)
        assert probs[2, 1] == pytest.approx(expected, abs=1e-6)

    def test_negative_rho_inflates_low_draws(self):
        """Dixon-Coles τ with rho<0 inflates P(0,0) and P(1,1).

        Per the 1997 paper:  τ(0,0) = 1 − λμρ,  τ(1,1) = 1 − ρ.
        With ρ < 0 these are > 1 → inflation. This matches real football where
        low-scoring draws are over-represented vs independent Poissons.
        """
        no_corr = score_probabilities(lam_home=1.0, lam_away=1.0, rho=0.0, max_goals=5)
        neg_corr = score_probabilities(lam_home=1.0, lam_away=1.0, rho=-0.1, max_goals=5)
        assert neg_corr[0, 0] > no_corr[0, 0]
        assert neg_corr[1, 1] > no_corr[1, 1]
        # And total still sums to 1
        assert neg_corr.sum() == pytest.approx(1.0, abs=1e-3)


class TestMatchOutcomeProbabilities:
    def test_home_draw_away_sum_to_one(self):
        p_home, p_draw, p_away = match_outcome_probabilities(lam_home=1.5, lam_away=1.0)
        assert (p_home + p_draw + p_away) == pytest.approx(1.0, abs=1e-3)

    def test_equal_lambdas_favor_home_only_slightly(self):
        """Equal expected goals: home and away win probs should match, draw ~25-30%."""
        p_home, p_draw, p_away = match_outcome_probabilities(lam_home=1.3, lam_away=1.3)
        assert p_home == pytest.approx(p_away, abs=0.01)
        assert 0.2 < p_draw < 0.35

    def test_higher_lambda_higher_win_prob(self):
        """Team with higher expected goals should be more likely to win."""
        p_home, _, p_away = match_outcome_probabilities(lam_home=2.5, lam_away=0.5)
        assert p_home > 0.7
        assert p_away < 0.1


class TestDixonColesModelFit:
    def _synthesize_matches(self, n_matches=2000, seed=42):
        """Generate matches from a known true model so we can test parameter recovery."""
        rng = np.random.default_rng(seed)
        # 8 teams with known attack and defence strengths
        teams = [f"T{i}" for i in range(8)]
        # Attack strengths centered at 0 (model is identifiable up to a constant shift)
        true_attack = {t: rng.normal(0, 0.3) for t in teams}
        true_defence = {t: rng.normal(0, 0.3) for t in teams}
        true_home_adv = 0.25

        matches = []
        for _ in range(n_matches):
            home, away = rng.choice(teams, size=2, replace=False)
            lam = np.exp(true_attack[home] + true_defence[away] + true_home_adv)
            mu = np.exp(true_attack[away] + true_defence[home])
            hg = rng.poisson(lam)
            ag = rng.poisson(mu)
            matches.append({
                "date": "2020-01-01",
                "home": home, "away": away,
                "home_goals": int(hg), "away_goals": int(ag),
                "neutral": False,
            })
        return matches, true_attack, true_defence, true_home_adv

    def test_recovers_home_advantage(self):
        matches, _, _, true_home_adv = self._synthesize_matches(n_matches=3000)
        model = DixonColesModel()
        model.fit(matches)
        assert model.home_advantage == pytest.approx(true_home_adv, abs=0.1)

    def test_recovers_team_ordering(self):
        """The best-attack team in synthetic data should be ranked best by the fit."""
        matches, true_attack, _, _ = self._synthesize_matches(n_matches=3000)
        model = DixonColesModel()
        model.fit(matches)
        # Rank teams by true vs estimated attack
        true_ranking = sorted(true_attack, key=true_attack.get, reverse=True)
        est_ranking = sorted(model.attack, key=model.attack.get, reverse=True)
        # The top team should match (allow some noise — top-3 overlap >=2)
        top3_true = set(true_ranking[:3])
        top3_est = set(est_ranking[:3])
        assert len(top3_true & top3_est) >= 2

    def test_predict_returns_valid_probabilities(self):
        matches, _, _, _ = self._synthesize_matches(n_matches=1000)
        model = DixonColesModel()
        model.fit(matches)
        p_home, p_draw, p_away = model.predict_match("T0", "T1", neutral=False)
        assert (p_home + p_draw + p_away) == pytest.approx(1.0, abs=1e-3)
        assert all(0 <= p <= 1 for p in (p_home, p_draw, p_away))

    def test_neutral_venue_removes_home_advantage(self):
        matches, _, _, _ = self._synthesize_matches(n_matches=1000)
        model = DixonColesModel()
        model.fit(matches)
        p_home_neutral, _, p_away_neutral = model.predict_match("T0", "T1", neutral=True)
        p_home_at_home, _, p_away_at_home = model.predict_match("T0", "T1", neutral=False)
        # At home, T0's win prob should be higher than at neutral
        assert p_home_at_home > p_home_neutral
