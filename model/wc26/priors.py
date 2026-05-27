"""Historical-pattern priors that adjust a base probability distribution.

These encode the empirical regularities of World Cup history:
- Every WC champion has come from UEFA or CONMEBOL
- Home-continent teams overperform (but 2026 in N. America has no precedent → mild)
- The same ~8 nations dominate — pedigree compounds
- Squad market value (Transfermarkt) correlates with player quality

Each adjustment returns a log-odds (additive in log-space), then `apply_priors`
multiplies by exp(total_adjustment) and renormalises.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp


# Coefficients are mild — base model already captures most of the signal via Elo.
# These are seasoning, not the main course. Dialled to a moderate level so the
# DC fit retains primary influence.
CONFEDERATION_LOG_ODDS: dict[str, float] = {
    "UEFA":     +0.25,   # 12 WC titles
    "CONMEBOL": +0.20,   # 10 WC titles
    "CONCACAF": -0.90,
    "AFC":      -1.00,
    "CAF":      -1.00,
    "OFC":      -1.40,
}

# Host-continent boost. 2026 is in North America — no historical precedent for
# a NA-hosted tournament producing a North American champion (Mexico hosted 1970, 1986
# and didn't win). Keep small.
HOST_CONTINENT_BOOST: float = 0.15

# Pedigree: log-odds contribution from prior WC wins (1.0 each) and prior semis (0.2 each)
# but with diminishing returns via tanh — being a 5x winner isn't 5x as good as 1x.
import math

def _tanh_diminish(x: float, scale: float) -> float:
    return scale * math.tanh(x / scale)


# Market-value centering. Calibrated so the median ~€400m squad sits at ~0.
# Coefficient chosen so a €1bn squad gets ~+0.5 log-odds, a €100m squad ~-0.5.
MARKET_VALUE_CENTER_EUR_M: float = 400.0
MARKET_VALUE_SCALE: float = 1000.0  # log-odds change per €1B above center


@dataclass
class TeamPriorFeatures:
    confederation: str
    continent: str
    prior_wins: int = 0       # FIFA World Cup wins
    prior_semis: int = 0      # FIFA World Cup semifinal appearances (incl. wins)
    squad_value_eur_m: float = MARKET_VALUE_CENTER_EUR_M


def confederation_log_odds(confederation: str) -> float:
    return CONFEDERATION_LOG_ODDS.get(confederation, -1.5)


def host_continent_log_odds(team_continent: str, host_continent: str) -> float:
    if team_continent == host_continent:
        return HOST_CONTINENT_BOOST
    return 0.0


def pedigree_log_odds(prior_wins: int, prior_semis: int) -> float:
    """Pedigree boost with strong diminishing returns.

    Saturates around +0.55 even for Brazil (5 wins, 11 semis). The DC fit and Elo
    already heavily favour these teams via recent form — pedigree is just a tiebreaker.
    """
    raw = 0.15 * prior_wins + 0.03 * prior_semis
    return _tanh_diminish(raw, scale=0.6)


def market_value_log_odds(squad_value_eur_m: float) -> float:
    """Linear in (value - center) / scale, mild magnitude.

    Scale of 1000 means a €1B premium over the median squad gets +1.0 log-odds
    (~2.7x multiplier).
    """
    return (squad_value_eur_m - MARKET_VALUE_CENTER_EUR_M) / 1000.0


def apply_priors(
    base: dict[str, float],
    features: dict[str, TeamPriorFeatures],
    host_continent: str,
) -> dict[str, float]:
    """Adjust a base probability distribution by the pattern priors and renormalise."""
    adjusted: dict[str, float] = {}
    for team, p in base.items():
        if team not in features:
            adjusted[team] = p
            continue
        f = features[team]
        log_adj = (
            confederation_log_odds(f.confederation)
            + host_continent_log_odds(f.continent, host_continent)
            + pedigree_log_odds(f.prior_wins, f.prior_semis)
            + market_value_log_odds(f.squad_value_eur_m)
        )
        adjusted[team] = max(p * exp(log_adj), 0.0)

    total = sum(adjusted.values())
    if total > 0:
        adjusted = {t: p / total for t, p in adjusted.items()}
    return adjusted
