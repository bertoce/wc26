"""Dixon-Coles Poisson goals model for soccer match prediction.

Reference:
  Dixon, M.J. & Coles, S.G. (1997). Modelling Association Football Scores and
  Inefficiencies in the Football Betting Market. Applied Statistics 46: 265-280.

Model:
  λ (home expected goals) = exp(α_h + β_a + γ)
  μ (away expected goals) = exp(α_a + β_h)
  P(home=h, away=a) = Poisson(h; λ) * Poisson(a; μ) * τ(h, a, λ, μ, ρ)

where τ is a low-score correction:
  τ(0,0) = 1 - λμρ
  τ(0,1) = 1 + λρ
  τ(1,0) = 1 + μρ
  τ(1,1) = 1 - ρ
  τ(h,a) = 1 otherwise

α_i: team i's attack strength
β_i: team i's defence strength (higher = leakier, since it goes into opponent λ)
γ:   global home advantage
ρ:   low-score correction (typically slightly negative for real football)

For identifiability, we constrain sum(α) = 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson


def _tau(h: int, a: int, lam: float, mu: float, rho: float) -> float:
    """Dixon-Coles low-score correction τ. Returns 1 for (h, a) outside {0, 1}²."""
    if h == 0 and a == 0:
        return 1.0 - lam * mu * rho
    if h == 0 and a == 1:
        return 1.0 + lam * rho
    if h == 1 and a == 0:
        return 1.0 + mu * rho
    if h == 1 and a == 1:
        return 1.0 - rho
    return 1.0


def score_probabilities(
    lam_home: float, lam_away: float, rho: float = 0.0, max_goals: int = 10
) -> np.ndarray:
    """Joint pmf P(home=h, away=a) as a (max_goals+1, max_goals+1) array."""
    h = np.arange(max_goals + 1)
    p_home = poisson.pmf(h, lam_home)
    p_away = poisson.pmf(h, lam_away)
    joint = np.outer(p_home, p_away)
    if rho == 0.0:
        # Independent Poissons — leave un-renormalised so values match the
        # marginal-product exactly (used for the independence test).
        return joint
    for i in (0, 1):
        for j in (0, 1):
            joint[i, j] *= _tau(i, j, lam_home, lam_away, rho)
    # Guard against negative joint cells caused by extreme rho
    joint = np.clip(joint, 0.0, None)
    total = joint.sum()
    if total > 0:
        joint /= total
    return joint


def match_outcome_probabilities(
    lam_home: float, lam_away: float, rho: float = 0.0, max_goals: int = 10
) -> tuple[float, float, float]:
    """Return (P(home win), P(draw), P(away win))."""
    p = score_probabilities(lam_home, lam_away, rho=rho, max_goals=max_goals)
    p_home = float(np.tril(p, k=-1).sum())  # home_goals > away_goals
    p_draw = float(np.trace(p))
    p_away = float(np.triu(p, k=1).sum())
    return p_home, p_draw, p_away


@dataclass
class DixonColesModel:
    """Fits attack/defence strengths per team plus global home advantage and rho."""

    attack: dict[str, float] = field(default_factory=dict)
    defence: dict[str, float] = field(default_factory=dict)
    home_advantage: float = 0.0
    rho: float = 0.0
    max_goals: int = 10

    def fit(
        self,
        matches: list[dict],
        time_decay_per_year: float = 0.0,
        ref_year: int | None = None,
    ) -> "DixonColesModel":
        """MLE fit. `matches` is a list of dicts with keys:
        home, away, home_goals, away_goals, neutral, [date]
        """
        teams = sorted({m["home"] for m in matches} | {m["away"] for m in matches})
        n = len(teams)
        idx = {t: i for i, t in enumerate(teams)}

        # Free parameters: α[1..n-1], β[0..n-1], γ, ρ
        # α[0] is determined by sum(α) = 0  →  α[0] = -sum(α[1:])
        n_free = (n - 1) + n + 2

        # Pre-compute match arrays for speed
        home_idx = np.array([idx[m["home"]] for m in matches])
        away_idx = np.array([idx[m["away"]] for m in matches])
        home_goals = np.array([m["home_goals"] for m in matches], dtype=int)
        away_goals = np.array([m["away_goals"] for m in matches], dtype=int)
        neutral = np.array([m.get("neutral", False) for m in matches], dtype=bool)

        # Time-decay weights
        if time_decay_per_year > 0 and ref_year is not None:
            years = np.array([int(m["date"][:4]) for m in matches])
            weights = np.exp(-time_decay_per_year * (ref_year - years))
        else:
            weights = np.ones(len(matches))

        def unpack(params: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float]:
            alpha_free = params[: n - 1]
            beta = params[n - 1 : n - 1 + n]
            gamma = params[n - 1 + n]
            rho = params[n - 1 + n + 1]
            alpha = np.empty(n)
            alpha[1:] = alpha_free
            alpha[0] = -alpha_free.sum()
            return alpha, beta, float(gamma), float(rho)

        def neg_log_lik(params: np.ndarray) -> float:
            alpha, beta, gamma, rho = unpack(params)
            # λ for home, μ for away
            home_adv_vec = np.where(neutral, 0.0, gamma)
            lam = np.exp(alpha[home_idx] + beta[away_idx] + home_adv_vec)
            mu = np.exp(alpha[away_idx] + beta[home_idx])
            # Poisson log-likelihood
            ll = (
                home_goals * np.log(lam) - lam
                + away_goals * np.log(mu) - mu
            )
            # Dixon-Coles low-score correction
            # Apply per match only for (h,a) in {0,1}²
            low_mask = (home_goals <= 1) & (away_goals <= 1)
            if low_mask.any():
                tau_vals = np.ones_like(lam)
                for i in np.where(low_mask)[0]:
                    tau_vals[i] = _tau(int(home_goals[i]), int(away_goals[i]),
                                       float(lam[i]), float(mu[i]), rho)
                # Avoid log of non-positive values from extreme rho
                tau_vals = np.clip(tau_vals, 1e-12, None)
                ll = ll + np.log(tau_vals)
            return -float(np.sum(weights * ll))

        # Initial guess: zeros for attack/defence, 0.25 home adv, -0.1 rho
        x0 = np.zeros(n_free)
        x0[-2] = 0.25  # gamma
        x0[-1] = -0.1  # rho

        bounds = [(-3.0, 3.0)] * (n - 1)        # α_free
        bounds += [(-3.0, 3.0)] * n              # β
        bounds += [(-1.0, 1.0), (-0.3, 0.3)]     # γ, ρ

        result = minimize(neg_log_lik, x0, method="L-BFGS-B", bounds=bounds)

        alpha, beta, gamma, rho = unpack(result.x)
        self.attack = {t: float(alpha[idx[t]]) for t in teams}
        self.defence = {t: float(beta[idx[t]]) for t in teams}
        self.home_advantage = gamma
        self.rho = rho
        return self

    def expected_goals(self, home: str, away: str, neutral: bool = False) -> tuple[float, float]:
        adv = 0.0 if neutral else self.home_advantage
        lam = np.exp(self.attack[home] + self.defence[away] + adv)
        mu = np.exp(self.attack[away] + self.defence[home])
        return float(lam), float(mu)

    def predict_match(
        self, home: str, away: str, neutral: bool = False
    ) -> tuple[float, float, float]:
        lam, mu = self.expected_goals(home, away, neutral=neutral)
        return match_outcome_probabilities(lam, mu, rho=self.rho, max_goals=self.max_goals)
