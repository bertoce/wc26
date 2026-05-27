"""World Football Elo rating system.

Implements the formula used by eloratings.net, including:
- Goal-difference multiplier (G)
- Match-importance weight (K, the "K-factor")
- Optional home advantage

References:
- https://www.eloratings.net/about
- Hvattum & Arntzen (2010), "Using ELO ratings for match result prediction in
  association football", International Journal of Forecasting 26: 460-470.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

INITIAL_RATING: float = 1500.0
DEFAULT_HOME_ADVANTAGE: float = 100.0
WC_MATCH_WEIGHT: float = 60.0
FRIENDLY_MATCH_WEIGHT: float = 20.0


# Tournament-importance lookup (K-factor) per eloratings.net conventions.
# Names mirror common values in the martj42/international_results dataset.
TOURNAMENT_WEIGHTS: dict[str, float] = {
    "Friendly": 20.0,
    "FIFA World Cup": 60.0,
    "FIFA World Cup qualification": 40.0,
    "UEFA Euro": 50.0,
    "UEFA Euro qualification": 40.0,
    "UEFA Nations League": 40.0,
    "Copa América": 50.0,
    "African Cup of Nations": 50.0,
    "African Cup of Nations qualification": 40.0,
    "AFC Asian Cup": 50.0,
    "AFC Asian Cup qualification": 40.0,
    "Gold Cup": 50.0,
    "Confederations Cup": 50.0,
    "CONCACAF Championship": 50.0,
}


@dataclass
class Match:
    date: str
    home: str
    away: str
    home_goals: int
    away_goals: int
    tournament: str
    neutral: bool


def expected_score(rating_self: float, rating_opp: float, home_adv: float = 0.0) -> float:
    """Standard Elo expected score, with optional home advantage added to self."""
    diff = (rating_opp - (rating_self + home_adv)) / 400.0
    return 1.0 / (1.0 + 10.0**diff)


def _goal_diff_multiplier(home_goals: int, away_goals: int) -> float:
    """World Football Elo goal-difference multiplier G.

    G = 1 if |gd| <= 1
    G = 1.5 if |gd| == 2
    G = (11 + |gd|) / 8 if |gd| >= 3
    """
    gd = abs(home_goals - away_goals)
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    return (11.0 + gd) / 8.0


def update_ratings(
    home_rating: float,
    away_rating: float,
    home_goals: int,
    away_goals: int,
    match_weight: float = FRIENDLY_MATCH_WEIGHT,
    home_adv: float = 0.0,
) -> tuple[float, float]:
    """Return updated (home, away) ratings after a single match.

    Default home_adv=0 makes the function symmetric for testability;
    `run_history` is responsible for choosing a home advantage based on the
    neutral-venue flag.
    """
    g = _goal_diff_multiplier(home_goals, away_goals)
    k = match_weight * g

    if home_goals > away_goals:
        w_home, w_away = 1.0, 0.0
    elif home_goals < away_goals:
        w_home, w_away = 0.0, 1.0
    else:
        w_home, w_away = 0.5, 0.5

    we_home = expected_score(home_rating, away_rating, home_adv=home_adv)
    we_away = 1.0 - we_home

    delta_home = k * (w_home - we_home)
    delta_away = k * (w_away - we_away)
    return home_rating + delta_home, away_rating + delta_away


def tournament_weight(name: str) -> float:
    """Look up the K-factor for a tournament name, defaulting to friendly."""
    if not name:
        return FRIENDLY_MATCH_WEIGHT
    # Exact match first
    if name in TOURNAMENT_WEIGHTS:
        return TOURNAMENT_WEIGHTS[name]
    # Partial-match fallback for variants ("FIFA World Cup qualification - UEFA", etc.)
    for key, weight in TOURNAMENT_WEIGHTS.items():
        if key.lower() in name.lower():
            return weight
    return FRIENDLY_MATCH_WEIGHT


def run_history(matches: Iterable[Match]) -> dict[str, float]:
    """Run Elo forward through all matches and return final ratings per team."""
    ratings: dict[str, float] = {}
    for m in matches:
        rh = ratings.get(m.home, INITIAL_RATING)
        ra = ratings.get(m.away, INITIAL_RATING)
        home_adv = 0.0 if m.neutral else DEFAULT_HOME_ADVANTAGE
        weight = tournament_weight(m.tournament)
        new_rh, new_ra = update_ratings(
            rh, ra, m.home_goals, m.away_goals,
            match_weight=weight, home_adv=home_adv,
        )
        ratings[m.home] = new_rh
        ratings[m.away] = new_ra
    return ratings
