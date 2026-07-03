"""Compute Mexico's Round-of-16 opponent distribution.

Reuses the production pipeline's input construction (cached data, no network),
re-fits Dixon-Coles, then runs the tournament simulator while tracking, for
every sim where Mexico reaches the R16, which team it faces there.

Run from model/:
    .venv/bin/python scripts/mex_r16_opponents.py
"""

import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
FORCE = os.environ.get("WC26_FORCE", "0") == "1"

from dotenv import load_dotenv
load_dotenv(ROOT / ".env.local")

from wc26.dixon_coles import DixonColesModel
from wc26.ingest import fetch_wc26_matches, fetch_wc26_teams, load_results
from wc26.results import (
    extract_finished_group_results,
    known_results_to_dc_matches,
)
from wc26.simulator import (
    Team,
    Fixture,
    GroupStanding,
    sort_group,
    _simulate_group_stage,
    _seed_advancers,
    _build_r32_pairings,
    _simulate_knockout,
)
from wc26.venues import is_host_home_fixture

N_SIMS = 20_000
SEED = 2026
RECENT_YEAR_CUTOFF = 2018
DC_TIME_DECAY_PER_YEAR = 0.693
DC_REF_YEAR = 2026
TARGET = "MEX"

COMPETITIVE_KEYWORDS = (
    "FIFA World Cup", "UEFA Euro", "UEFA Nations League", "Copa América",
    "African Cup of Nations", "AFC Asian Cup", "Gold Cup", "Confederations Cup",
    "CONCACAF", "qualification", "Nations League",
)


def is_competitive(t: str) -> bool:
    if not t or t == "Friendly":
        return False
    return any(kw.lower() in t.lower() for kw in COMPETITIVE_KEYWORDS)


def main() -> None:
    df = load_results(force=FORCE)
    recent = df[(df.date.dt.year >= RECENT_YEAR_CUTOFF) & df.tournament.map(is_competitive)].copy()

    features = json.loads((ROOT / "model" / "data" / "static" / "team_features.json").read_text())
    features = {k: v for k, v in features.items() if not k.startswith("_")}
    wc26_names = {v["name_historical"] for v in features.values()}

    recent = recent[recent.home_team.isin(wc26_names) | recent.away_team.isin(wc26_names)].copy()
    dc_matches = [
        {
            "date": r.date.strftime("%Y-%m-%d"), "home": r.home_team, "away": r.away_team,
            "home_goals": int(r.home_score), "away_goals": int(r.away_score), "neutral": bool(r.neutral),
        }
        for r in recent.itertuples(index=False)
    ]

    fd_matches = fetch_wc26_matches(force=FORCE)["matches"]
    known_results = extract_finished_group_results(fd_matches)
    tla_to_hist = {tla: f["name_historical"] for tla, f in features.items()}
    injected = known_results_to_dc_matches(known_results, tla_to_hist, dc_matches)
    dc_matches.extend(injected)

    model = DixonColesModel()
    model.fit(dc_matches, time_decay_per_year=DC_TIME_DECAY_PER_YEAR, ref_year=DC_REF_YEAR)

    fd_teams = fetch_wc26_teams(force=FORCE)["teams"]
    tla_to_name = {t["tla"]: t["name"] for t in fd_teams}

    ATTACK_CLIP = (-0.8, 1.5)
    DEFENCE_CLIP = (-1.1, 1.5)
    teams: list[Team] = []
    for tla, feat in features.items():
        hist = feat["name_historical"]
        if hist not in model.attack:
            attack, defence = 0.0, 0.5
        else:
            attack = max(ATTACK_CLIP[0], min(ATTACK_CLIP[1], model.attack[hist]))
            defence = max(DEFENCE_CLIP[0], min(DEFENCE_CLIP[1], model.defence[hist]))
        teams.append(Team(code=tla, name=hist, attack=attack, defence=defence,
                          confederation=feat["confederation"]))
    teams_by_code = {t.code: t for t in teams}

    group_matches = [m for m in fd_matches if m["stage"] == "GROUP_STAGE"]
    fixtures: list[Fixture] = []
    for m in group_matches:
        h = m["homeTeam"].get("tla"); a = m["awayTeam"].get("tla")
        if not h or not a or h not in features or a not in features:
            continue
        group = (m.get("group") or "").replace("GROUP_", "") or None
        host_home = is_host_home_fixture(h, "group")
        fixtures.append(Fixture(home=h, away=a, neutral=not host_home, stage="group", group=group))

    # Lock real scores for finished matches (same as pipeline)
    scheduled_pairs = {(f.home, f.away) for f in fixtures}
    locked: dict[tuple[str, str], tuple[int, int]] = {}
    for kr in known_results:
        pair = (kr["home"], kr["away"])
        if pair in scheduled_pairs:
            locked[pair] = (int(kr["home_goals"]), int(kr["away_goals"]))

    rng = np.random.default_rng(SEED)
    ha, rho = model.home_advantage, model.rho

    reach_r16 = 0
    opp_counts: dict[str, int] = defaultdict(int)
    reach_r32 = 0
    opp32_counts: dict[str, int] = defaultdict(int)

    for _ in range(N_SIMS):
        standings = _simulate_group_stage(fixtures, teams_by_code, ha, rho, rng, locked_results=locked)
        advancers: list[str] = []
        thirds: list[GroupStanding] = []
        for group, ranked in standings.items():
            for s in ranked[:2]:
                advancers.append(s.team)
            if len(ranked) >= 3:
                thirds.append(ranked[2])
        if thirds:
            advancers.extend(s.team for s in sort_group(thirds)[:8])

        seeded = _seed_advancers(standings, 2, 8)
        r32_pairings = _build_r32_pairings(seeded)
        _champ, _rounds, matchups = _simulate_knockout(
            advancers, teams_by_code, ha, rho, rng, r32_pairings=r32_pairings)

        # R32 pairings = matchups[32]; find the pair containing MEX
        for h, a in matchups.get(32, []):
            if h == TARGET:
                reach_r32 += 1; opp32_counts[a] += 1; break
            if a == TARGET:
                reach_r32 += 1; opp32_counts[h] += 1; break

        # R16 pairings = matchups[16]; find the pair containing MEX (if alive)
        for h, a in matchups.get(16, []):
            if h == TARGET:
                reach_r16 += 1
                opp_counts[a] += 1
                break
            if a == TARGET:
                reach_r16 += 1
                opp_counts[h] += 1
                break

    print(f"Mexico reaches R32 in {reach_r32}/{N_SIMS} sims = {reach_r32/N_SIMS*100:.1f}%")
    print("R32 opponent distribution:")
    for tla, c in sorted(opp32_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {tla_to_name.get(tla, tla):<22}{c/reach_r32*100:>6.1f}%")
    print()
    print(f"Mexico reaches R16 in {reach_r16}/{N_SIMS} sims = {reach_r16/N_SIMS*100:.1f}%\n")
    print("Conditional opponent distribution (given Mexico reaches R16):")
    print(f"{'Team':<22}{'P(opp | R16)':>14}{'P(this matchup)':>18}")
    ranked = sorted(opp_counts.items(), key=lambda kv: -kv[1])
    for tla, c in ranked:
        cond = c / reach_r16 * 100
        uncond = c / N_SIMS * 100
        print(f"{tla_to_name.get(tla, tla):<22}{cond:>13.1f}%{uncond:>17.1f}%")

    # Save JSON for reuse
    out = {
        "target": TARGET,
        "n_sims": N_SIMS,
        "seed": SEED,
        "reach_r16_prob": reach_r16 / N_SIMS,
        "opponents": [
            {
                "tla": tla,
                "name": tla_to_name.get(tla, tla),
                "p_conditional": c / reach_r16,
                "p_unconditional": c / N_SIMS,
            }
            for tla, c in ranked
        ],
    }
    out_path = ROOT / "model" / "data" / "processed" / "mex_r16_opponents.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nSaved → {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
