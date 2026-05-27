"""Tournament simulator: group stage with FIFA tiebreakers, knockouts with shootouts.

Designed to be flexible enough to handle:
- The test fixture: 1 group of 4 → top 2 to a final
- The real WC26: 12 groups of 4 → top-2 + best-8 thirds → R32 → R16 → QF → SF → F
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .dixon_coles import match_outcome_probabilities


@dataclass
class Team:
    code: str
    name: str
    attack: float        # Dixon-Coles α
    defence: float       # Dixon-Coles β
    confederation: str = "UEFA"


@dataclass
class Fixture:
    home: str
    away: str
    neutral: bool = True
    stage: str = "group"  # "group", "r32", "r16", "qf", "sf", "third_place", "final"
    group: str | None = None  # e.g. "A"


@dataclass
class GroupStanding:
    team: str
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    gf: int = 0
    ga: int = 0

    @property
    def points(self) -> int:
        return 3 * self.wins + self.draws

    @property
    def gd(self) -> int:
        return self.gf - self.ga


def sort_group(standings: list[GroupStanding]) -> list[GroupStanding]:
    """FIFA tiebreakers: points → goal difference → goals scored → team code (stable)."""
    return sorted(
        standings,
        key=lambda s: (s.points, s.gd, s.gf, s.team),
        reverse=True,
    )


def simulate_match(
    lam_home: float, lam_away: float, rng: np.random.Generator
) -> tuple[int, int]:
    """Draw a scoreline from independent Poissons."""
    return int(rng.poisson(lam_home)), int(rng.poisson(lam_away))


def simulate_knockout_match(
    home: str,
    away: str,
    lam_home: float,
    lam_away: float,
    rng: np.random.Generator,
) -> tuple[str, int, int]:
    """Returns (winner, home_goals, away_goals).

    If regulation is a draw, extra time uses a scaled-down lambda (30 min instead of 90).
    If still drawn, penalty shootout decides — 50/50 baseline since shootouts are noisy.
    """
    hg, ag = simulate_match(lam_home, lam_away, rng)
    if hg != ag:
        return (home if hg > ag else away), hg, ag
    # Extra time: 1/3 of regulation expected goals
    et_h, et_a = simulate_match(lam_home / 3.0, lam_away / 3.0, rng)
    hg_total, ag_total = hg + et_h, ag + et_a
    if hg_total != ag_total:
        return (home if hg_total > ag_total else away), hg_total, ag_total
    # Penalty shootout
    winner = home if rng.random() < 0.5 else away
    return winner, hg_total, ag_total


def _expected_goals(
    home: str,
    away: str,
    teams_by_code: dict[str, Team],
    home_advantage: float,
    rho: float,
    neutral: bool,
) -> tuple[float, float]:
    th = teams_by_code[home]
    ta = teams_by_code[away]
    adv = 0.0 if neutral else home_advantage
    lam = float(np.exp(th.attack + ta.defence + adv))
    mu = float(np.exp(ta.attack + th.defence))
    return lam, mu


def _simulate_group_stage(
    fixtures: list[Fixture],
    teams_by_code: dict[str, Team],
    home_advantage: float,
    rho: float,
    rng: np.random.Generator,
) -> dict[str, list[GroupStanding]]:
    """Run all group fixtures and return standings per group."""
    # Initialise standings — group by Fixture.group, falling back to a single "X" group
    by_group: dict[str, dict[str, GroupStanding]] = defaultdict(dict)
    for f in fixtures:
        g = f.group or "X"
        for t in (f.home, f.away):
            if t not in by_group[g]:
                by_group[g][t] = GroupStanding(team=t)

    for f in fixtures:
        g = f.group or "X"
        lam, mu = _expected_goals(
            f.home, f.away, teams_by_code, home_advantage, rho, neutral=f.neutral
        )
        hg, ag = simulate_match(lam, mu, rng)
        h = by_group[g][f.home]
        a = by_group[g][f.away]
        h.played += 1; a.played += 1
        h.gf += hg; h.ga += ag
        a.gf += ag; a.ga += hg
        if hg > ag:
            h.wins += 1; a.losses += 1
        elif hg < ag:
            a.wins += 1; h.losses += 1
        else:
            h.draws += 1; a.draws += 1

    return {g: sort_group(list(s.values())) for g, s in by_group.items()}


def _single_elim_pairings(advancers: list[str]) -> list[tuple[str, str]]:
    """Pair adjacent teams in the order given (deterministic for testability)."""
    if len(advancers) % 2 != 0:
        raise ValueError(f"Need an even number of advancers, got {len(advancers)}")
    return [(advancers[i], advancers[i + 1]) for i in range(0, len(advancers), 2)]


def _simulate_knockout(
    advancers: list[str],
    teams_by_code: dict[str, Team],
    home_advantage: float,
    rho: float,
    rng: np.random.Generator,
) -> tuple[str, dict[int, list[str]]]:
    """Single-elimination from the given list.

    Returns (champion, rounds_remaining) where rounds_remaining[k] is the list
    of teams that were alive when k teams remained in the bracket. The starting
    set lives at key len(advancers); the champion lives at key 1.
    """
    current = list(advancers)
    rounds_remaining: dict[int, list[str]] = {len(current): list(current)}
    while len(current) > 1:
        pairings = _single_elim_pairings(current)
        winners = []
        for h, a in pairings:
            lam, mu = _expected_goals(h, a, teams_by_code, home_advantage, rho, neutral=True)
            winner, _, _ = simulate_knockout_match(h, a, lam, mu, rng)
            winners.append(winner)
        current = winners
        rounds_remaining[len(current)] = list(current)
    return current[0], rounds_remaining


def predict_group_fixtures(
    fixtures: list["Fixture"],
    teams_by_code: dict[str, "Team"],
    home_advantage: float,
    rho: float,
) -> list[dict]:
    """Compute deterministic W/D/L + expected goals for each group fixture.

    Knockout-stage fixtures (where teams are still placeholders pre-tournament)
    are skipped. Returns a list of dicts with keys:
        home, away, group, p_home_win, p_draw, p_away_win,
        expected_home_goals, expected_away_goals.
    """
    out: list[dict] = []
    for f in fixtures:
        if f.stage != "group":
            continue
        if f.home not in teams_by_code or f.away not in teams_by_code:
            continue
        lam, mu = _expected_goals(
            f.home, f.away, teams_by_code, home_advantage, rho, neutral=f.neutral
        )
        p_h, p_d, p_a = match_outcome_probabilities(lam, mu, rho=rho)
        out.append({
            "home": f.home,
            "away": f.away,
            "group": f.group,
            "neutral": f.neutral,
            "p_home_win": p_h,
            "p_draw": p_d,
            "p_away_win": p_a,
            "expected_home_goals": lam,
            "expected_away_goals": mu,
        })
    return out


def simulate_tournament(
    teams: list[Team],
    fixtures: list[Fixture],
    n_sims: int = 10_000,
    seed: int = 42,
    home_advantage: float = 0.25,
    rho: float = -0.1,
    qualifiers_per_group: int = 2,
    best_thirds: int = 0,
) -> dict:
    """Simulate the tournament n_sims times and return per-team win probabilities.

    For the test fixture (1 group of 4): qualifiers_per_group=2 → top-2 to final.
    For WC26 (12 groups of 4): qualifiers_per_group=2, best_thirds=8 → 32 teams to R32.
    """
    teams_by_code = {t.code: t for t in teams}
    win_counts: dict[str, int] = defaultdict(int)
    # round_counts[tla][k] = number of sims where the team was alive when k teams remained
    round_counts: dict[str, dict[int, int]] = {
        t.code: defaultdict(int) for t in teams
    }
    rng = np.random.default_rng(seed)

    for _ in range(n_sims):
        standings = _simulate_group_stage(
            fixtures, teams_by_code, home_advantage, rho, rng
        )
        # Collect top-N from each group
        advancers: list[str] = []
        thirds: list[GroupStanding] = []
        for group, ranked in standings.items():
            for s in ranked[:qualifiers_per_group]:
                advancers.append(s.team)
            if best_thirds > 0 and len(ranked) >= 3:
                thirds.append(ranked[2])
        if best_thirds > 0 and thirds:
            ranked_thirds = sort_group(thirds)
            advancers.extend(s.team for s in ranked_thirds[:best_thirds])

        if len(advancers) < 2:
            champion = advancers[0] if advancers else None
            rounds_remaining = {len(advancers): list(advancers), 1: [champion] if champion else []}
        else:
            champion, rounds_remaining = _simulate_knockout(
                advancers, teams_by_code, home_advantage, rho, rng
            )
        if champion is not None:
            win_counts[champion] += 1

        # Tally survival for this sim
        for k, alive in rounds_remaining.items():
            for tla in alive:
                if tla in round_counts:
                    round_counts[tla][k] += 1

    win_probability = {t.code: win_counts.get(t.code, 0) / n_sims for t in teams}
    round_survival = {
        tla: {k: cnt / n_sims for k, cnt in counts.items()}
        for tla, counts in round_counts.items()
    }
    return {
        "win_probability": win_probability,
        "round_survival": round_survival,
        "n_sims": n_sims,
        "seed": seed,
    }
