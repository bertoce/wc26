"""Monte Carlo projection from the Round of 32 through the Final.

The R32 bracket is fixed (real pairings from fd.org). Beyond R32, fd.org leaves
the slots TBD, but its match IDs are the official sequential bracket numbering,
so sorting R32 by id gives bracket order and pairing adjacent winners through
each round reconstructs the tree (same logic as the simulator).

This is a genuine Monte Carlo run (unlike the closed-form R32 four-outcome
table): each sim plays every knockout match with the calibrated model
(goal-rate scale + R32 host/nominal-home edge), regulation Poisson scorelines,
extra time at 1/3 lambda, and a 50/50 shootout — then tallies, per team:
  P(reach R16 / QF / SF / Final / Champion), P(runner-up), P(third place).

Golden Boot is an individual award; with no player data we proxy it as the
team most likely to finish as the tournament's top-scoring side (actual group
goals already banked + simulated knockout goals).

Run from model/:
    .venv/bin/python scripts/r32_to_final_simulation.py
"""

import json
import math
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
FORCE = os.environ.get("WC26_FORCE", "0") == "1"

from dotenv import load_dotenv
load_dotenv(ROOT / ".env.local")

from wc26 import calibration as cal
from wc26.dixon_coles import DixonColesModel
from wc26.ingest import fetch_wc26_matches, fetch_wc26_teams, load_results
from wc26.results import extract_finished_group_results, known_results_to_dc_matches
from wc26.venues import is_host_home_fixture

N_SIMS = 50_000
SEED = 2026
RECENT_YEAR_CUTOFF = 2018
DC_TIME_DECAY_PER_YEAR = 0.693
DC_REF_YEAR = 2026
ATTACK_CLIP = (-0.8, 1.5)
DEFENCE_CLIP = (-1.1, 1.5)
ET_FRACTION = 1.0 / 3.0
HOSTS = {"MEX", "USA"}   # host teams that play their R32 at home (from martj42 venue flag)

COMPETITIVE_KEYWORDS = (
    "FIFA World Cup", "UEFA Euro", "UEFA Nations League", "Copa América",
    "African Cup of Nations", "AFC Asian Cup", "Gold Cup", "Confederations Cup",
    "CONCACAF", "qualification", "Nations League",
)


def is_competitive(t: str) -> bool:
    return bool(t) and t != "Friendly" and any(k.lower() in t.lower() for k in COMPETITIVE_KEYWORDS)


def _clip(v, b):
    return max(b[0], min(b[1], v))


def main() -> None:
    # ---- fit (identical setup to the R32 predictor; form off) ----
    df = load_results(force=FORCE)
    recent = df[(df.date.dt.year >= RECENT_YEAR_CUTOFF) & df.tournament.map(is_competitive)].copy()
    features = json.loads((ROOT / "model" / "data" / "static" / "team_features.json").read_text())
    features = {k: v for k, v in features.items() if not k.startswith("_")}
    names = {v["name_historical"] for v in features.values()}
    recent = recent[recent.home_team.isin(names) | recent.away_team.isin(names)].copy()
    dc = [{"date": r.date.strftime("%Y-%m-%d"), "home": r.home_team, "away": r.away_team,
           "home_goals": int(r.home_score), "away_goals": int(r.away_score), "neutral": bool(r.neutral)}
          for r in recent.itertuples(index=False)]
    fd_matches = fetch_wc26_matches(force=FORCE)["matches"]
    known = extract_finished_group_results(fd_matches)
    tla_hist = {tla: f["name_historical"] for tla, f in features.items()}
    dc.extend(known_results_to_dc_matches(known, tla_hist, dc))
    model = DixonColesModel().fit(dc, time_decay_per_year=DC_TIME_DECAY_PER_YEAR, ref_year=DC_REF_YEAR)
    ha = model.home_advantage

    fd_teams = fetch_wc26_teams(force=FORCE)["teams"]
    name = {t["tla"]: t["name"] for t in fd_teams}

    att, dfc = {}, {}
    for tla, f in features.items():
        h = f["name_historical"]
        att[tla] = _clip(model.attack.get(h, 0.0), ATTACK_CLIP)
        dfc[tla] = _clip(model.defence.get(h, 0.5), DEFENCE_CLIP)

    # group goals already banked (Golden Boot base)
    group_goals = defaultdict(int)
    for k in known:
        group_goals[k["home"]] += k["home_goals"]
        group_goals[k["away"]] += k["away_goals"]

    # R32 in official bracket order (by match id)
    r32 = [m for m in fd_matches if m["stage"] == "LAST_32"]
    r32.sort(key=lambda m: m.get("id", 0))
    bracket = [(m["homeTeam"]["tla"], m["awayTeam"]["tla"]) for m in r32]
    teams = [t for pair in bracket for t in pair]

    def lambdas(h, a, r32_round):
        """Calibrated (lam_home, lam_away). R32: host gets real gamma, else the
        designated-home nominal edge. Later rounds: neutral, goal-scale only."""
        host = r32_round and h in HOSTS
        lh = math.exp(att[h] + dfc[a] + (ha if host else 0.0))
        la = math.exp(att[a] + dfc[h])
        lh *= cal.GOAL_SCALE
        la *= cal.GOAL_SCALE
        if r32_round and not host:
            lh *= math.exp(cal.NOMINAL_HOME_EDGE)
        return lh, la

    rng = np.random.default_rng(SEED)

    def play(h, a, r32_round):
        lh, la = lambdas(h, a, r32_round)
        gh, ga = int(rng.poisson(lh)), int(rng.poisson(la))
        if gh == ga:
            gh += int(rng.poisson(lh * ET_FRACTION))
            ga += int(rng.poisson(la * ET_FRACTION))
        if gh > ga:
            return h, gh, ga
        if ga > gh:
            return a, gh, ga
        return (h if rng.random() < 0.5 else a), gh, ga  # shootout

    reach = {r: defaultdict(int) for r in ("R16", "QF", "SF", "Final", "Champion")}
    runner_up = defaultdict(int)
    third = defaultdict(int)
    boot = defaultdict(int)   # times this team is the tournament top scorer

    for _ in range(N_SIMS):
        sim_goals = dict(group_goals)  # copy banked group goals
        # R32 -> R16
        cur = []
        for h, a in bracket:
            w, gh, ga = play(h, a, True)
            sim_goals[h] = sim_goals.get(h, 0) + gh
            sim_goals[a] = sim_goals.get(a, 0) + ga
            reach["R16"][w] += 1
            cur.append(w)
        # R16 -> QF -> SF (neutral)
        for label in ("QF", "SF"):
            nxt = []
            for i in range(0, len(cur), 2):
                w, gh, ga = play(cur[i], cur[i + 1], False)
                sim_goals[cur[i]] = sim_goals.get(cur[i], 0) + gh
                sim_goals[cur[i + 1]] = sim_goals.get(cur[i + 1], 0) + ga
                reach[label][w] += 1
                nxt.append(w)
            cur = nxt
        # SF: cur has 4 -> 2 finalists + 2 losers
        finalists, sf_losers = [], []
        for i in (0, 2):
            w, gh, ga = play(cur[i], cur[i + 1], False)
            sim_goals[cur[i]] = sim_goals.get(cur[i], 0) + gh
            sim_goals[cur[i + 1]] = sim_goals.get(cur[i + 1], 0) + ga
            loser = cur[i + 1] if w == cur[i] else cur[i]
            reach["Final"][w] += 1
            finalists.append(w)
            sf_losers.append(loser)
        # Final
        champ, gh, ga = play(finalists[0], finalists[1], False)
        sim_goals[finalists[0]] = sim_goals.get(finalists[0], 0) + gh
        sim_goals[finalists[1]] = sim_goals.get(finalists[1], 0) + ga
        reach["Champion"][champ] += 1
        runner_up[finalists[1] if champ == finalists[0] else finalists[0]] += 1
        # Third-place playoff
        t3, gh, ga = play(sf_losers[0], sf_losers[1], False)
        sim_goals[sf_losers[0]] = sim_goals.get(sf_losers[0], 0) + gh
        sim_goals[sf_losers[1]] = sim_goals.get(sf_losers[1], 0) + ga
        third[t3] += 1
        # Golden Boot proxy: team with most total goals this sim
        boot[max(sim_goals, key=sim_goals.get)] += 1

    # ---- report ----
    pct = lambda c: c / N_SIMS * 100
    order = sorted(teams, key=lambda t: -reach["Champion"][t])
    print(f"WC26 — Monte Carlo from R32 to Final  ({N_SIMS:,} sims, calibrated model)\n")
    print(f"{'Team':<22}{'R16':>7}{'QF':>7}{'SF':>7}{'Final':>7}{'Champ':>7}")
    print("-" * 57)
    for t in order:
        print(f"{name.get(t,t):<22}{pct(reach['R16'][t]):>6.1f}%{pct(reach['QF'][t]):>6.1f}%"
              f"{pct(reach['SF'][t]):>6.1f}%{pct(reach['Final'][t]):>6.1f}%{pct(reach['Champion'][t]):>6.1f}%")

    def top(counter, label):
        t = max(counter, key=counter.get)
        print(f"  {label:<14} {name.get(t,t):<22} {pct(counter[t]):.1f}%")

    print("\nMost likely (given the current draw):")
    top(reach["Champion"], "Champion")
    top(runner_up, "Runner-up")
    top(third, "Third place")
    top(boot, "Golden Boot*")
    print("  * Golden Boot = team-level proxy (most tournament goals; no player data)")

    out = {
        "n_sims": N_SIMS, "seed": SEED, "stage": "R32_to_final",
        "bracket_order": "fd.org match-id order, adjacent pairing",
        "teams": {name.get(t, t): {r: round(pct(reach[r][t]) / 100, 4) for r in reach}
                  | {"runner_up": round(pct(runner_up[t]) / 100, 4),
                     "third_place": round(pct(third[t]) / 100, 4),
                     "golden_boot_proxy": round(pct(boot[t]) / 100, 4)}
                  for t in order},
    }
    p = ROOT / "model" / "data" / "processed" / "r32_to_final_projection.json"
    p.write_text(json.dumps(out, indent=2))
    print(f"\nSaved → {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
