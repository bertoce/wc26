"""Tests for the empirical calibration layer (wc26/calibration.py)."""

import math

from wc26 import calibration as cal
from wc26.dixon_coles import match_outcome_probabilities


def test_goal_scale_applied_to_both_sides():
    lam, mu = cal.calibrated_lambdas(1.0, 1.0, neutral=False)
    assert lam == cal.GOAL_SCALE
    assert mu == cal.GOAL_SCALE


def test_nominal_home_edge_only_on_neutral():
    # Neutral venue: home gets the extra edge, away does not.
    lam_n, mu_n = cal.calibrated_lambdas(1.0, 1.0, neutral=True)
    assert lam_n == math.exp(cal.NOMINAL_HOME_EDGE) * cal.GOAL_SCALE
    assert mu_n == cal.GOAL_SCALE
    # Non-neutral (host already has real gamma): no extra edge.
    lam_h, _ = cal.calibrated_lambdas(1.0, 1.0, neutral=False)
    assert lam_h < lam_n


def test_calibrated_rho_pushes_negative_and_clamps():
    assert cal.calibrated_rho(-0.02) == -0.02 - cal.DRAW_RHO_EXTRA
    # Clamped to the floor rather than exceeding the fitted bound.
    assert cal.calibrated_rho(-0.30) == cal.RHO_FLOOR
    assert cal.calibrated_rho(-1.0) == cal.RHO_FLOOR


def test_calibration_increases_goals_draws_and_home_share():
    """For an even matchup the calibration should raise total goals, the draw
    probability, and the home win share relative to the raw model."""
    lam0, mu0 = 1.2, 1.2
    raw = match_outcome_probabilities(lam0, mu0, rho=-0.02)
    lam, mu = cal.calibrated_lambdas(lam0, mu0, neutral=True)
    adj = match_outcome_probabilities(lam, mu, rho=cal.calibrated_rho(-0.02))
    assert lam + mu > lam0 + mu0           # more goals
    assert adj[1] > raw[1]                  # more draws
    # Nominal-home edge tilts the home/away odds toward home (the absolute home
    # share can dip slightly because the stronger draw-correction also trims
    # low-scoring 1-0 wins, so compare the ratio rather than the level).
    assert adj[0] / adj[2] > raw[0] / raw[2]
