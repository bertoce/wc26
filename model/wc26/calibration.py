"""Empirical calibration layer learned from the WC26 group-stage backtest.

After all 72 group matches were played we compared the 70 *honest* pre-match
predictions (frozen in prematch_snapshots.json, post_hoc=False) against the
actual results. Three systematic errors showed up:

  1. GOALS under-predicted.   Model 2.68 goals/match vs actual 3.00.
  2. AWAY over-predicted.     Predicted H/D/A 41/24/34 vs actual 46/29/26 —
     the designated-"home" side overperformed even though almost all group
     fixtures are at neutral venues. The model gave nominal-home teams no edge.
  3. DRAWS under-predicted.   24.5% predicted vs 28.6% actual.

These three knobs were grid-searched on that backtest (see
scripts/backtest_group_stage.py), evaluated against the SAME predictions
recomputed without calibration (the honest apples-to-apples control). The
values below correct the goals mean (2.68 -> 2.98), shift the outcome mix
toward reality (H/D/A 42/24/35 -> 44/25/31 vs actual 46/29/26), and improve
BOTH log-loss (0.9142 -> 0.9092) and Brier (0.5415 -> 0.5390).

Note: GOAL_SCALE raises goals but *suppresses* draws (more goals => fewer
0-0/1-1), so DRAW_RHO_EXTRA has to be strong enough to overcome it and still
net more draws. The two are tuned together, not independently.

Caveats — this is in-sample on a single 70-match tournament:
  * NOMINAL_HOME_EDGE is kept at ~40% of the host home-advantage gamma. The raw
    away-skew was ~8pts but chasing all of it risks overfitting one World Cup;
    a small designated-home edge at neutral venues is also literature-plausible.
  * Draws are improved but still under actual (25% vs 29%) — a known residual.
"""

from __future__ import annotations

import math

# --- Fitted on the WC26 group-stage backtest (70 honest pre-match matches) ---
GOAL_SCALE = 1.06          # goals under-predicted (2.68 -> ~2.98 /match)
NOMINAL_HOME_EDGE = 0.10   # designated-home overperforms at neutral venues (log-goals)
DRAW_RHO_EXTRA = 0.13      # draws under-predicted; strong enough to beat the goal-scale
RHO_FLOOR = -0.30          # keep rho inside the model's fitted bound


def calibrated_lambdas(
    lam_home: float, lam_away: float, neutral: bool
) -> tuple[float, float]:
    """Apply the goal-rate scale to both sides, plus the nominal-home edge.

    The nominal-home edge is added ONLY for neutral-venue fixtures (group games
    between non-hosts, and every knockout match), because non-neutral host games
    already carry the real home-advantage gamma in `lam_home`. Without this
    guard the host bump would be double-counted.
    """
    lam_home *= GOAL_SCALE
    lam_away *= GOAL_SCALE
    if neutral:
        lam_home *= math.exp(NOMINAL_HOME_EDGE)
    return lam_home, lam_away


def calibrated_rho(rho: float) -> float:
    """Push rho more negative to add draw mass, clamped to the fitted floor."""
    return max(RHO_FLOOR, rho - DRAW_RHO_EXTRA)
