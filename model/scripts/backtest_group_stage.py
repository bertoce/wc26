"""Backtest the group-stage predictions and report calibration learnings.

Joins the FROZEN pre-match predictions (data/state/prematch_snapshots.json)
with the actual group results, then reports outcome-mix, goal, and probabilistic
calibration — for the honest pre-match subset (post_hoc=False) and for all 72.

It also re-scores the honest subset under the empirical calibration in
wc26/calibration.py so the effect of each correction is visible and auditable.

Run from model/:
    .venv/bin/python scripts/backtest_group_stage.py
"""

import json
import math
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env.local")

from wc26 import calibration as cal
from wc26.dixon_coles import match_outcome_probabilities
from wc26.ingest import fetch_wc26_matches
from wc26.results import extract_finished_group_results, result_key
from wc26.venues import is_host_home_fixture

# rho used when the snapshots were generated (predictions.json metadata, v0.5.0)
SNAPSHOT_RHO = -0.0209
IDX = {"H": 0, "D": 1, "A": 2}


def load_rows():
    snaps = json.loads((ROOT / "model" / "data" / "state" / "prematch_snapshots.json").read_text())
    known = extract_finished_group_results(fetch_wc26_matches()["matches"])
    actual = {result_key(k["group"], k["home"], k["away"]): k for k in known}
    rows = []
    for key, kr in actual.items():
        s = snaps.get(key)
        if not s:
            continue
        home_tla = key.split(":")[1].split("-")[0]
        hg, ag = kr["home_goals"], kr["away_goals"]
        rows.append({
            "post_hoc": s.get("post_hoc", False),
            "lam": s["expected_home_goals"], "mu": s["expected_away_goals"],
            "ph": s["p_home_win"], "pd": s["p_draw"], "pa": s["p_away_win"],
            "neutral": not is_host_home_fixture(home_tla, "group"),
            "res": "H" if hg > ag else ("A" if ag > hg else "D"),
            "goals": hg + ag,
        })
    return rows


def metrics(probs, results, goals_pred, goals_act):
    n = len(results)
    goals_act = list(goals_act)
    ll = br = 0.0
    pm = [0.0, 0.0, 0.0]
    am = [0.0, 0.0, 0.0]
    for (ph, pd, pa), res in zip(probs, results):
        p = (ph, pd, pa)
        i = IDX[res]
        ll += -math.log(max(p[i], 1e-9))
        y = [0, 0, 0]; y[i] = 1
        br += sum((a - b) ** 2 for a, b in zip(p, y))
        for j in range(3):
            pm[j] += p[j]
        am[i] += 1
    return {
        "n": n, "logloss": ll / n, "brier": br / n,
        "pred": [x / n * 100 for x in pm], "act": [x / n * 100 for x in am],
        "goals_pred": sum(goals_pred) / n, "goals_act": sum(goals_act) / n,
    }


def show(title, m):
    print(f"\n## {title}  (n={m['n']})")
    print(f"  {'':6}{'PRED':>8}{'ACTUAL':>9}")
    for lab, j in (("Home", 0), ("Draw", 1), ("Away", 2)):
        print(f"  {lab:6}{m['pred'][j]:>7.1f}%{m['act'][j]:>8.1f}%   (Δ {m['pred'][j]-m['act'][j]:+.1f})")
    print(f"  Goals/match: pred {m['goals_pred']:.2f}  actual {m['goals_act']:.2f}  (Δ {m['goals_pred']-m['goals_act']:+.2f})")
    print(f"  LogLoss {m['logloss']:.4f}   Brier {m['brier']:.4f}")


def main():
    rows = load_rows()
    honest = [r for r in rows if not r["post_hoc"]]

    # As-predicted (frozen snapshot probabilities)
    show("ALL 72 (incl. post-hoc) — as predicted",
         metrics([(r["ph"], r["pd"], r["pa"]) for r in rows],
                 [r["res"] for r in rows],
                 [r["lam"] + r["mu"] for r in rows], [r["goals"] for r in rows]))
    show("HONEST pre-match — as predicted",
         metrics([(r["ph"], r["pd"], r["pa"]) for r in honest],
                 [r["res"] for r in honest],
                 [r["lam"] + r["mu"] for r in honest], [r["goals"] for r in honest]))

    # Apples-to-apples control: recompute the SAME lambdas with NO calibration,
    # so the calibration delta below isn't confounded by how the frozen
    # snapshot probabilities were produced.
    ctrl_probs = [match_outcome_probabilities(r["lam"], r["mu"], rho=SNAPSHOT_RHO) for r in honest]
    show("HONEST pre-match — recomputed, NO calibration (control)",
         metrics(ctrl_probs, [r["res"] for r in honest],
                 [r["lam"] + r["mu"] for r in honest], [r["goals"] for r in honest]))

    # Re-scored under the new calibration layer
    cal_probs, cal_goals = [], []
    for r in honest:
        lam, mu = cal.calibrated_lambdas(r["lam"], r["mu"], r["neutral"])
        cal_probs.append(match_outcome_probabilities(lam, mu, rho=cal.calibrated_rho(SNAPSHOT_RHO)))
        cal_goals.append(lam + mu)
    show("HONEST pre-match — WITH calibration layer",
         metrics(cal_probs, [r["res"] for r in honest], cal_goals, [r["goals"] for r in honest]))

    print(f"\nCalibration constants: goal_scale={cal.GOAL_SCALE} "
          f"nominal_home_edge={cal.NOMINAL_HOME_EDGE} draw_rho_extra={cal.DRAW_RHO_EXTRA}")

    # ---- Confidence-tiered hit-rate (calibrated model, honest subset) ----
    # Demonstrates the one honest route to >=70%: only "call" games above a
    # confidence floor; the coin-flips (high upset mass) are left as toss-ups.
    pick = lambda p: ("H", "D", "A")[max(range(3), key=lambda i: p[i])]
    scored = []
    for r in honest:
        lam, mu = cal.calibrated_lambdas(r["lam"], r["mu"], r["neutral"])
        p = match_outcome_probabilities(lam, mu, rho=cal.calibrated_rho(SNAPSHOT_RHO))
        scored.append((max(p), pick(p) == r["res"]))
    n = len(scored)
    print("\n## Confidence-tiered accuracy (calibrated model)")
    print(f"  {'floor':>7}{'accuracy':>10}{'coverage':>16}")
    for c in (0.00, 0.50, 0.55, 0.60, 0.65, 0.70):
        sub = [hit for conf, hit in scored if conf >= c]
        if not sub:
            continue
        acc = sum(sub) / len(sub) * 100
        print(f"  {c:>7.2f}{acc:>9.0f}%{f'{len(sub)}/{n} ({len(sub)/n*100:.0f}%)':>16}")
    print("  (floor 0.00 = predict every game; higher floors skip the toss-ups)")


if __name__ == "__main__":
    main()
