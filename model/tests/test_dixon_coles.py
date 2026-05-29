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


class TestTimeDecay:
    """Exponential time-decay weighting in DC.fit() should shift parameter
    estimates toward more recent matches when a team's strength changes over time."""

    def _synthesize_changing_team(self, seed: int = 42):
        """Team T0 is WEAK from 2018-2022, then STRONG from 2023-2026.
        Other teams are uniformly average. With time decay, fits should see
        T0 as strong; without decay, fits should average it out toward zero."""
        rng = np.random.default_rng(seed)
        teams = [f"T{i}" for i in range(6)]
        # T0 is the "changing" team. Others are average (0).
        # Old era: T0 attack = -0.7  (weak)
        # New era: T0 attack = +0.7  (strong)
        matches = []

        def add_matches(year: int, t0_attack: float, n: int):
            for _ in range(n):
                home, away = rng.choice(teams, size=2, replace=False)
                a_h = t0_attack if home == "T0" else 0.0
                a_a = t0_attack if away == "T0" else 0.0
                # Everyone has neutral defence
                lam = np.exp(a_h + 0.0 + 0.0)  # neutral venue, no defence shift
                mu = np.exp(a_a + 0.0)
                hg = rng.poisson(lam)
                ag = rng.poisson(mu)
                matches.append({
                    "date": f"{year}-06-15",
                    "home": home, "away": away,
                    "home_goals": int(hg), "away_goals": int(ag),
                    "neutral": True,
                })

        # 5 matches/year in old era (weak T0): 2018-2022 = 5 years × 60 matches = 300 matches
        for yr in (2018, 2019, 2020, 2021, 2022):
            add_matches(yr, t0_attack=-0.7, n=60)
        # Same volume in new era (strong T0): 2023-2026 = 4 years × 60 matches = 240 matches
        for yr in (2023, 2024, 2025, 2026):
            add_matches(yr, t0_attack=+0.7, n=60)

        return matches

    def test_no_decay_averages_eras(self):
        """Without time decay, the fit should land between the two eras' values.
        Since old-era matches (n=300, weak) outweigh new-era (n=240, strong),
        T0's estimated attack should be on the negative side or near zero."""
        matches = self._synthesize_changing_team()
        model = DixonColesModel()
        model.fit(matches, time_decay_per_year=0.0)
        # Without decay, T0 is averaged. Should be in [-0.7, +0.7] but closer to 0
        # because the two eras pull it both ways. The KEY assertion is that it's
        # clearly NOT at +0.7 (the recent value).
        assert model.attack["T0"] < 0.3, (
            f"Without decay, T0 attack={model.attack['T0']:+.3f} — should be averaged, not recent-dominated"
        )

    def test_decay_shifts_toward_recent(self):
        """With a 1-year half-life (ln(2) ≈ 0.693), recent matches dominate.
        Matches from 2018 (8 years ago) get weight ~0.004 — effectively ignored.
        T0's estimated attack should be much closer to +0.7 than to 0 or -0.7."""
        matches = self._synthesize_changing_team()
        model = DixonColesModel()
        model.fit(matches, time_decay_per_year=0.693, ref_year=2026)
        # Recent value is +0.7. Fit should be near it (within sampling noise).
        assert model.attack["T0"] > 0.3, (
            f"With decay, T0 attack={model.attack['T0']:+.3f} — should reflect recent +0.7 strength"
        )

    def test_decay_estimate_closer_to_recent_than_no_decay(self):
        """Direct comparison: decay-fit's T0 attack should be CLOSER to +0.7 (recent)
        than no-decay-fit's T0 attack."""
        matches = self._synthesize_changing_team()
        m_no = DixonColesModel(); m_no.fit(matches, time_decay_per_year=0.0)
        m_yes = DixonColesModel(); m_yes.fit(matches, time_decay_per_year=0.693, ref_year=2026)
        recent_truth = 0.7
        no_decay_dist = abs(m_no.attack["T0"] - recent_truth)
        with_decay_dist = abs(m_yes.attack["T0"] - recent_truth)
        assert with_decay_dist < no_decay_dist, (
            f"Decay distance to recent={with_decay_dist:.3f} should be < "
            f"no-decay distance={no_decay_dist:.3f}"
        )

    def test_zero_decay_equals_no_decay(self):
        """time_decay_per_year=0 must produce the same fit as omitting the argument."""
        matches = self._synthesize_changing_team()
        m1 = DixonColesModel(); m1.fit(matches)
        m2 = DixonColesModel(); m2.fit(matches, time_decay_per_year=0.0)
        for t in m1.attack:
            assert m1.attack[t] == pytest.approx(m2.attack[t], abs=1e-6)
