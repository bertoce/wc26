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
    locked_results: dict[tuple[str, str], tuple[int, int]] | None = None,
) -> dict[str, list[GroupStanding]]:
    """Run all group fixtures and return standings per group.

    locked_results maps (home, away) → (home_goals, away_goals) for matches
    that have actually been played — those scores are applied verbatim in
    every simulation instead of being drawn from the model.
    """
    # Initialise standings — group by Fixture.group, falling back to a single "X" group
    by_group: dict[str, dict[str, GroupStanding]] = defaultdict(dict)
    for f in fixtures:
        g = f.group or "X"
        for t in (f.home, f.away):
            if t not in by_group[g]:
                by_group[g][t] = GroupStanding(team=t)

    for f in fixtures:
        g = f.group or "X"
        locked = (locked_results or {}).get((f.home, f.away))
        if locked is not None:
            hg, ag = locked
        else:
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
    """Pair adjacent teams in the order given (deterministic for testability).

    This is the inner-rounds pairing — once seeding has placed teams in their
    bracket slots, R16/QF/SF/F just pair winners of adjacent matches.
    """
    if len(advancers) % 2 != 0:
        raise ValueError(f"Need an even number of advancers, got {len(advancers)}")
    return [(advancers[i], advancers[i + 1]) for i in range(0, len(advancers), 2)]


def bracket_seed_order(n: int) -> list[int]:
    """Standard tournament seeding for a single-elimination bracket of size n.

    n must be a power of 2. Returns the seed numbers (1-indexed) in the order
    they should be laid out in the bracket — pairing adjacent yields the
    canonical structure where #1 vs #n, the top half ends at the seed-2 path,
    and seeds 1 and 2 only meet in the final.

    For n=4 returns [1, 4, 2, 3]. For n=32 returns the full 32-team layout.
    """
    if n == 2:
        return [1, 2]
    half = bracket_seed_order(n // 2)
    out: list[int] = []
    for s in half:
        out.append(s)
        out.append(n + 1 - s)
    return out


def _seed_advancers(
    standings_by_group: dict[str, list[GroupStanding]],
    qualifiers_per_group: int,
    best_thirds: int,
) -> list[tuple[str, str]]:
    """Rank all advancers and return them as a list of (team, group) tuples
    in seed order (best first).

    Tiers: group winners > runners-up > best 3rds. Within tier, sort by
    FIFA tiebreakers (points → GD → GF).
    """
    by_tier: list[list[tuple[GroupStanding, str]]] = [[] for _ in range(qualifiers_per_group + 1)]
    thirds_pool: list[tuple[GroupStanding, str]] = []

    for group, ranked in standings_by_group.items():
        for pos, s in enumerate(ranked[:qualifiers_per_group]):
            by_tier[pos].append((s, group))
        if best_thirds > 0 and len(ranked) >= qualifiers_per_group + 1:
            thirds_pool.append((ranked[qualifiers_per_group], group))

    def _rank_key(entry: tuple[GroupStanding, str]):
        s, _ = entry
        # Sort descending: more points first
        return (-s.points, -s.gd, -s.gf, s.team)

    seeded: list[tuple[str, str]] = []
    for tier in by_tier:
        tier_sorted = sorted(tier, key=_rank_key)
        seeded.extend((s.team, g) for s, g in tier_sorted)
    if best_thirds > 0 and thirds_pool:
        thirds_sorted = sorted(thirds_pool, key=_rank_key)[:best_thirds]
        seeded.extend((s.team, g) for s, g in thirds_sorted)
    return seeded


def _build_r32_pairings(
    seeded: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Build the first-round bracket using standard tournament seeding, then
    swap to avoid same-group rematches when possible.

    `seeded` is a list of (team, group) tuples in seed order (best first).
    Returns a list of (home_team, away_team) pairings for the first knockout
    round, length = len(seeded) // 2.
    """
    n = len(seeded)
    if n == 0:
        return []
    if n == 1:
        return [(seeded[0][0], seeded[0][0])]  # degenerate — single team
    if n & (n - 1) != 0:
        # Not a power of 2 — fall back to adjacent pairing
        return [(seeded[i][0], seeded[i + 1][0]) for i in range(0, n - 1, 2)]

    # Lay out by seed order; pair adjacent
    order = bracket_seed_order(n)
    # order is 1-indexed seed numbers; seeded is 0-indexed
    slots: list[tuple[str, str]] = [seeded[s - 1] for s in order]

    # Build pairings and swap to avoid same-group rematches
    pairings_with_groups: list[tuple[tuple[str, str], tuple[str, str]]] = [
        (slots[i], slots[i + 1]) for i in range(0, n, 2)
    ]
    # If any pair has same group, find a swap candidate from a non-conflicting
    # match in the same bracket half (so the bracket's seeding semantics survive).
    half = len(pairings_with_groups) // 2
    for half_offset, half_start in enumerate((0, half)):
        for i in range(half_start, half_start + half):
            (ta, ga), (tb, gb) = pairings_with_groups[i]
            if ga == gb:
                # Try swapping tb with another team in the same half
                for j in range(half_start, half_start + half):
                    if j == i:
                        continue
                    (tc, gc), (td, gd) = pairings_with_groups[j]
                    # Swap tb ↔ td if it removes the conflict without creating one
                    if gd != ga and gc != gb:
                        pairings_with_groups[i] = ((ta, ga), (td, gd))
                        pairings_with_groups[j] = ((tc, gc), (tb, gb))
                        break

    return [(pa[0], pb[0]) for pa, pb in pairings_with_groups]


def _simulate_knockout(
    advancers: list[str],
    teams_by_code: dict[str, Team],
    home_advantage: float,
    rho: float,
    rng: np.random.Generator,
    r32_pairings: list[tuple[str, str]] | None = None,
) -> tuple[str, dict[int, list[str]], dict[int, list[tuple[str, str]]]]:
    """Single-elimination from the given list.

    If r32_pairings is provided, use it for the first round (this is how
    seeded brackets work — the first round's pairings come from the seeding,
    subsequent rounds just pair adjacent winners).

    Returns (champion, rounds_remaining, matchups_per_round).
    """
    # Determine starting order of the bracket: if we have explicit first-round
    # pairings, lay teams out so adjacent pairing reproduces them; otherwise
    # use the input order as-is.
    if r32_pairings is not None:
        current = [t for pair in r32_pairings for t in pair]
    else:
        current = list(advancers)
    rounds_remaining: dict[int, list[str]] = {len(current): list(current)}
    matchups_per_round: dict[int, list[tuple[str, str]]] = {}
    while len(current) > 1:
        round_size = len(current)
        pairings = _single_elim_pairings(current)
        matchups_per_round[round_size] = list(pairings)
        winners = []
        for h, a in pairings:
            lam, mu = _expected_goals(h, a, teams_by_code, home_advantage, rho, neutral=True)
            winner, _, _ = simulate_knockout_match(h, a, lam, mu, rng)
            winners.append(winner)
        current = winners
        rounds_remaining[len(current)] = list(current)
    return current[0], rounds_remaining, matchups_per_round


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
    known_results: list[dict] | None = None,
) -> dict:
    """Simulate the tournament n_sims times and return per-team win probabilities.

    For the test fixture (1 group of 4): qualifiers_per_group=2 → top-2 to final.
    For WC26 (12 groups of 4): qualifiers_per_group=2, best_thirds=8 → 32 teams to R32.

    known_results: list of {home, away, group, home_goals, away_goals} dicts
    for matches already played in the real tournament. Those fixtures use the
    actual score in every simulation; only the remaining fixtures vary.
    Results referencing fixtures not in the schedule are silently ignored.
    """
    teams_by_code = {t.code: t for t in teams}
    # Build (home, away) → (hg, ag) lookup, restricted to fixtures that exist
    scheduled_pairs = {(f.home, f.away) for f in fixtures}
    locked_results: dict[tuple[str, str], tuple[int, int]] = {}
    for kr in known_results or []:
        pair = (kr["home"], kr["away"])
        if pair in scheduled_pairs:
            locked_results[pair] = (int(kr["home_goals"]), int(kr["away_goals"]))
    win_counts: dict[str, int] = defaultdict(int)
    # round_counts[tla][k] = number of sims where the team was alive when k teams remained
    round_counts: dict[str, dict[int, int]] = {
        t.code: defaultdict(int) for t in teams
    }
    # matchup_counts[k][match_idx][(home_tla, away_tla)] = count
    matchup_counts: dict[int, dict[int, dict[tuple[str, str], int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    rng = np.random.default_rng(seed)

    for _ in range(n_sims):
        standings = _simulate_group_stage(
            fixtures, teams_by_code, home_advantage, rho, rng,
            locked_results=locked_results,
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
            matchups_this_sim: dict[int, list[tuple[str, str]]] = {}
        else:
            # Build seeded first-round pairings (avoids same-group R32 rematches,
            # and pairs top seeds with bottom seeds).
            seeded = _seed_advancers(
                standings, qualifiers_per_group, best_thirds,
            )
            r32_pairings = _build_r32_pairings(seeded)
            champion, rounds_remaining, matchups_this_sim = _simulate_knockout(
                advancers, teams_by_code, home_advantage, rho, rng,
                r32_pairings=r32_pairings,
            )
        if champion is not None:
            win_counts[champion] += 1

        # Tally survival for this sim
        for k, alive in rounds_remaining.items():
            for tla in alive:
                if tla in round_counts:
                    round_counts[tla][k] += 1

        # Tally matchups for this sim
        for round_size, pairings in matchups_this_sim.items():
            for match_idx, (h, a) in enumerate(pairings):
                matchup_counts[round_size][match_idx][(h, a)] += 1

    win_probability = {t.code: win_counts.get(t.code, 0) / n_sims for t in teams}
    round_survival = {
        tla: {k: cnt / n_sims for k, cnt in counts.items()}
        for tla, counts in round_counts.items()
    }
    matchup_distribution = {
        round_size: {
            match_idx: {pair: cnt / n_sims for pair, cnt in pair_counts.items()}
            for match_idx, pair_counts in by_match.items()
        }
        for round_size, by_match in matchup_counts.items()
    }
    return {
        "win_probability": win_probability,
        "round_survival": round_survival,
        "matchup_distribution": matchup_distribution,
        "n_sims": n_sims,
        "seed": seed,
    }
