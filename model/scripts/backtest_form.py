"""Backtest the 'last-N games' form layer to find a data-backed weight.

Walk-forward over the group stage: for every matchday-2 and matchday-3 fixture,
each team's form delta is computed ONLY from its strictly-earlier group games
(vs the base model's calibrated expectation for those games), then applied on
top of the calibrated base prediction for the target fixture — exactly how the
R32 script applies form on top of already-refit ratings. We score log-loss /
Brier on the actual result across form weights {0, .15, .25, .30, .45, .60}.

W=0 is the no-form control (calibrated model only). This tells us whether the
explicit form layer helps at all, and at what cap.

Run from model/:
    .venv/bin/python scripts/backtest_form.py
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

SNAPSHOT_RHO = -0.0209
FORM_SMOOTH = 1.0
IDX = {"H": 0, "D": 1, "A": 2}
WEIGHTS = [0.0, 0.15, 0.25, 0.30, 0.45, 0.60]


def build_games():
    snaps = json.loads((ROOT / "model" / "data" / "state" / "prematch_snapshots.json").read_text())
    known = extract_finished_group_results(fetch_wc26_matches()["matches"])
    games = []
    for kr in known:
        key = result_key(kr["group"], kr["home"], kr["away"])
        s = snaps.get(key)
        if not s:
            continue
        games.append({
            "date": kr["utc_date"], "home": kr["home"], "away": kr["away"],
            "neutral": not is_host_home_fixture(kr["home"], "group"),
            "lam": s["expected_home_goals"], "mu": s["expected_away_goals"],
            "hg": kr["home_goals"], "ag": kr["away_goals"],
        })
    games.sort(key=lambda g: g["date"])
    return games


def form_delta(team, before_date, games, weight):
    """Form (att, def) delta for `team` from its group games strictly before
    `before_date`, vs the base model's CALIBRATED expectation for those games."""
    gf_a = ga_a = gf_e = ga_e = 0.0
    seen = 0
    for g in games:
        if g["date"] >= before_date:
            continue
        if team not in (g["home"], g["away"]):
            continue
        lam, mu = cal.calibrated_lambdas(g["lam"], g["mu"], g["neutral"])
        if team == g["home"]:
            gf_a += g["hg"]; ga_a += g["ag"]; gf_e += lam; ga_e += mu
        else:
            gf_a += g["ag"]; ga_a += g["hg"]; gf_e += mu; ga_e += lam
        seen += 1
    if seen == 0:
        return None  # no prior games — can't form-adjust
    d_att = math.log((gf_a + FORM_SMOOTH) / (gf_e + FORM_SMOOTH))
    d_def = math.log((ga_a + FORM_SMOOTH) / (ga_e + FORM_SMOOTH))
    cap = lambda x: max(-weight, min(weight, x))
    return cap(d_att), cap(d_def)


def score(weight, games):
    ll = br = 0.0
    n = 0
    for tgt in games:
        fh = form_delta(tgt["home"], tgt["date"], games, weight)
        fa = form_delta(tgt["away"], tgt["date"], games, weight)
        if fh is None or fa is None:
            continue  # matchday 1 — both teams need history
        lam, mu = cal.calibrated_lambdas(tgt["lam"], tgt["mu"], tgt["neutral"])
        lam *= math.exp(fh[0] + fa[1])   # home attack form + away defence form
        mu *= math.exp(fa[0] + fh[1])
        p = match_outcome_probabilities(lam, mu, rho=cal.calibrated_rho(SNAPSHOT_RHO))
        res = "H" if tgt["hg"] > tgt["ag"] else ("A" if tgt["ag"] > tgt["hg"] else "D")
        i = IDX[res]
        ll += -math.log(max(p[i], 1e-9))
        y = [0, 0, 0]; y[i] = 1
        br += sum((a - b) ** 2 for a, b in zip(p, y))
        n += 1
    return ll / n, br / n, n


def main():
    games = build_games()
    print("Form-layer walk-forward backtest (MD2+MD3 group fixtures)\n")
    print(f"{'form cap (weight)':>18}{'logloss':>10}{'brier':>9}{'n':>5}")
    best = None
    for w in WEIGHTS:
        ll, br, n = score(w, games)
        tag = "  <- no-form control" if w == 0.0 else ""
        print(f"{w:>18.2f}{ll:>10.4f}{br:>9.4f}{n:>5}{tag}")
        if best is None or ll < best[1]:
            best = (w, ll, br)
    print(f"\nBest weight by log-loss: cap={best[0]:.2f}  (logloss {best[1]:.4f}, brier {best[2]:.4f})")
    if best[0] == 0.0:
        print("=> Form did NOT improve out-of-sample prediction here; the model already")
        print("   absorbs recent results via the daily refit. Lower form weight is safer.")


if __name__ == "__main__":
    main()
