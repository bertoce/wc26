"""Four-outcome knockout-match prediction (regulation W/D/L + extra-time split).

A knockout tie has four mutually-exclusive, exhaustive outcomes:
    1. Home (Team A) wins in regulation (90')
    2. Away (Team B) wins in regulation (90')
    3. Draw after 90', Team A advances via extra time / penalties
    4. Draw after 90', Team B advances via extra time / penalties
with P(A advances) = 1 + 3 and P(B advances) = 2 + 4.

Regulation W/D/L comes from the calibrated Dixon-Coles bivariate Poisson. The
regulation-draw mass is split with the simulator's own extra-time logic,
computed analytically at 1/3 lambda (strength-tilted, not a flat 50/50); the
residual extra-time-draw mass is split 50/50 for the penalty shootout.

Calibration (goal-rate scale, nominal-home edge, draw-rho) from the group-stage
backtest is applied here so every knockout consumer shares one code path.
"""

from __future__ import annotations

import math

from . import calibration as cal
from .dixon_coles import match_outcome_probabilities

ET_FRACTION = 1.0 / 3.0   # extra time = 30' vs 90' regulation


def four_outcome_prediction(
    att_home: float, def_home: float,
    att_away: float, def_away: float,
    home_advantage: float, rho: float,
    *, host_home: bool,
) -> dict:
    """Predict a single knockout tie.

    host_home=True → the listed home team plays in its own country: apply the
    real home-advantage gamma (and no nominal-home edge). Otherwise the venue is
    neutral and the calibration layer adds the small nominal-home edge that the
    group-stage backtest found for designated-home sides.
    """
    adv = home_advantage if host_home else 0.0
    lam = math.exp(att_home + def_away + adv)
    mu = math.exp(att_away + def_home)
    lam, mu = cal.calibrated_lambdas(lam, mu, neutral=not host_home)
    rho_cal = cal.calibrated_rho(rho)

    p_a_reg, p_draw, p_b_reg = match_outcome_probabilities(lam, mu, rho=rho_cal)
    et_a, et_d, et_b = match_outcome_probabilities(lam * ET_FRACTION, mu * ET_FRACTION, rho=rho_cal)
    q_a = et_a + 0.5 * et_d
    q_b = et_b + 0.5 * et_d
    s = q_a + q_b
    q_a, q_b = q_a / s, q_b / s

    o_draw_a = p_draw * q_a
    o_draw_b = p_draw * q_b
    p_a_adv = p_a_reg + o_draw_a
    p_b_adv = p_b_reg + o_draw_b
    return {
        "expected_home_goals": lam,
        "expected_away_goals": mu,
        "a_win_regulation": p_a_reg,
        "b_win_regulation": p_b_reg,
        "draw_then_a_advances": o_draw_a,
        "draw_then_b_advances": o_draw_b,
        "p_a_advances": p_a_adv,
        "p_b_advances": p_b_adv,
    }


def confidence_tier(advance_prob: float) -> str:
    """Tier the favourite's advance probability: strong ≥70%, lean ≥60%, else toss-up."""
    conf = max(advance_prob, 1.0 - advance_prob)
    return "strong" if conf >= 0.70 else ("lean" if conf >= 0.60 else "tossup")
