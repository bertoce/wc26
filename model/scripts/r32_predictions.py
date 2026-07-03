"""Round-of-32 four-outcome predictions for the 16 real WC26 knockout fixtures.

Unlike the group-stage pipeline, the R32 bracket is *determined* — the 32 teams
and their 16 pairings are fixed once the group stage ends. So this is not a
tournament rollout; it's 16 independent head-to-head knockout predictions with
known opponents.

For each fixture we emit FOUR mutually-exclusive, exhaustive outcomes:
    1. Team A wins in regulation (90')          = p_home_win
    2. Team B wins in regulation (90')          = p_away_win
    3. Draw after 90', Team A wins in ET/pens    = p_draw * q_A
    4. Draw after 90', Team B wins in ET/pens    = p_draw * q_B
with q_A + q_B = 1. P(A advances) = (1) + (3); P(B advances) = (2) + (4).

Two modelling layers on top of the base Dixon-Coles fit:
  * Regulation W/D/L from the bivariate Poisson (match_outcome_probabilities).
  * Draw-mass split via the simulator's own extra-time logic, computed
    analytically at 1/3 lambda (strength-tilted, not a flat 50/50): the
    stronger side is correctly more likely to survive a draw. The residual
    ET-draw mass is split 50/50 to represent the penalty shootout.

  * A "last-3 WC group games" FORM layer (user-specified): each qualified
    team's three group matches are compared against what the base model
    *expected* for those exact fixtures. Over-/under-performance in goals
    scored and conceded is converted to a STRONG, bounded delta on the team's
    attack / defence ratings before predicting the R32 match. NB: 3 games is a
    noisy sample — "strong" weighting deliberately lets recent form dominate,
    at the cost of higher variance / overfitting risk.

Run from model/:
    .venv/bin/python scripts/r32_predictions.py
"""

import json
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
FORCE = os.environ.get("WC26_FORCE", "0") == "1"

from dotenv import load_dotenv
load_dotenv(ROOT / ".env.local")

from wc26 import calibration as cal
from wc26.dixon_coles import DixonColesModel
from wc26.knockout import confidence_tier, four_outcome_prediction
from wc26.ingest import fetch_wc26_matches, fetch_wc26_teams, load_results
from wc26.results import extract_finished_group_results, known_results_to_dc_matches
from wc26.venues import is_host_home_fixture

RECENT_YEAR_CUTOFF = 2018
DC_TIME_DECAY_PER_YEAR = 0.693
DC_REF_YEAR = 2026

ATTACK_CLIP = (-0.8, 1.5)
DEFENCE_CLIP = (-1.1, 1.5)

# --- Form layer (perf-vs-expectation, last-3 WC games) ---
# Backtest (scripts/backtest_form.py) found the form layer HURTS out-of-sample
# (logloss rises monotonically with weight) because the daily refit already
# absorbs recent results — so the data-backed default is 0 (no form). Override
# with WC26_FORM_CAP to explore stronger settings (e.g. 0.45 = "strong").
FORM_SMOOTH = 1.0           # pseudo-goals added to actual & expected totals (over 3 games)
FORM_CAP = float(os.environ.get("WC26_FORM_CAP", "0.0"))  # max |delta|; 0 = form off
ET_FRACTION = 1.0 / 3.0     # extra time = 30' vs 90' regulation


COMPETITIVE_KEYWORDS = (
    "FIFA World Cup", "UEFA Euro", "UEFA Nations League", "Copa América",
    "African Cup of Nations", "AFC Asian Cup", "Gold Cup", "Confederations Cup",
    "CONCACAF", "qualification", "Nations League",
)


def is_competitive(t: str) -> bool:
    if not t or t == "Friendly":
        return False
    return any(kw.lower() in t.lower() for kw in COMPETITIVE_KEYWORDS)


def _clip(v, lo_hi):
    return max(lo_hi[0], min(lo_hi[1], v))


def main() -> None:
    # ------------------------------------------------------------------ data
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

    # ------------------------------------------------------------------- fit
    model = DixonColesModel()
    model.fit(dc_matches, time_decay_per_year=DC_TIME_DECAY_PER_YEAR, ref_year=DC_REF_YEAR)
    ha, rho = model.home_advantage, model.rho

    fd_teams = fetch_wc26_teams(force=FORCE)["teams"]
    tla_to_name = {t["tla"]: t["name"] for t in fd_teams}

    # Real R32 venues: fd.org free tier has no venue field, but martj42's CSV
    # carries a `neutral` flag that is False only when a host plays in its own
    # country. Read it raw (load_results drops the unplayed R32 rows since their
    # scores are NA) to find which R32 home teams get true host advantage.
    import pandas as pd
    raw = pd.read_csv(ROOT / "model" / "data" / "raw" / "results.csv", parse_dates=["date"])
    HOST_NAME_TO_TLA = {"Mexico": "MEX", "United States": "USA", "Canada": "CAN"}
    r32_host_home: set[str] = set()
    for r in raw[raw.date >= "2026-06-28"].itertuples(index=False):
        if not bool(r.neutral):
            tla = HOST_NAME_TO_TLA.get(r.home_team)
            if tla:
                r32_host_home.add(tla)

    # Base (pre-form) clipped ratings per TLA
    base_att: dict[str, float] = {}
    base_def: dict[str, float] = {}
    for tla, feat in features.items():
        hist = feat["name_historical"]
        if hist not in model.attack:
            base_att[tla], base_def[tla] = 0.0, 0.5
        else:
            base_att[tla] = _clip(model.attack[hist], ATTACK_CLIP)
            base_def[tla] = _clip(model.defence[hist], DEFENCE_CLIP)

    # ------------------------------------------------------- form deltas
    # For each team, accumulate actual vs base-model-expected GF/GA over its
    # three group matches, then convert to a strong bounded rating delta.
    gf_act: dict[str, float] = {}
    ga_act: dict[str, float] = {}
    gf_exp: dict[str, float] = {}
    ga_exp: dict[str, float] = {}

    def _acc(tla, gf_a, ga_a, gf_e, ga_e):
        gf_act[tla] = gf_act.get(tla, 0.0) + gf_a
        ga_act[tla] = ga_act.get(tla, 0.0) + ga_a
        gf_exp[tla] = gf_exp.get(tla, 0.0) + gf_e
        ga_exp[tla] = ga_exp.get(tla, 0.0) + ga_e

    for kr in known_results:
        h, a = kr["home"], kr["away"]
        if h not in base_att or a not in base_att:
            continue
        neutral = not is_host_home_fixture(h, "group")
        adv = 0.0 if neutral else ha
        lam_h = float(np.exp(base_att[h] + base_def[a] + adv))   # home expected GF
        mu_a = float(np.exp(base_att[a] + base_def[h]))          # away expected GF
        # Compare actual vs *calibrated* expectation so form captures genuine
        # over/under-performance rather than the model's global goal-rate bias.
        lam_h, mu_a = cal.calibrated_lambdas(lam_h, mu_a, neutral=neutral)
        hg, ag = kr["home_goals"], kr["away_goals"]
        _acc(h, hg, ag, lam_h, mu_a)   # home team: GF=hg GA=ag, exp GF=lam_h GA=mu_a
        _acc(a, ag, hg, mu_a, lam_h)   # away team: GF=ag GA=hg, exp GF=mu_a GA=lam_h

    form_att: dict[str, float] = {}
    form_def: dict[str, float] = {}
    for tla in base_att:
        if tla not in gf_exp:           # team somehow has no group games — no form signal
            form_att[tla] = 0.0
            form_def[tla] = 0.0
            continue
        # Attack over-performance: scored more than expected -> attack up.
        d_att = np.log((gf_act[tla] + FORM_SMOOTH) / (gf_exp[tla] + FORM_SMOOTH))
        # Defence over-performance: conceded more than expected -> beta up (leakier).
        d_def = np.log((ga_act[tla] + FORM_SMOOTH) / (ga_exp[tla] + FORM_SMOOTH))
        form_att[tla] = float(_clip(d_att, (-FORM_CAP, FORM_CAP)))
        form_def[tla] = float(_clip(d_def, (-FORM_CAP, FORM_CAP)))

    def adj_att(tla):
        return _clip(base_att[tla] + form_att.get(tla, 0.0), ATTACK_CLIP)

    def adj_def(tla):
        return _clip(base_def[tla] + form_def.get(tla, 0.0), DEFENCE_CLIP)

    # ----------------------------------------------------- R32 predictions
    last32 = [m for m in fd_matches if m["stage"] == "LAST_32"]
    last32.sort(key=lambda m: (m.get("utcDate", ""), m.get("id", 0)))

    predictions = []
    for m in last32:
        h = m["homeTeam"].get("tla")
        a = m["awayTeam"].get("tla")
        if not h or not a or h not in base_att or a not in base_att:
            continue
        # Venue: most R32 games are neutral, where the calibration layer applies
        # a small nominal-home edge (the group backtest showed designated-home
        # sides overperform). But where a host plays in its own country (Mexico,
        # USA), apply the full real home-advantage gamma instead of the nominal
        # edge. Calibration still applies the goal-rate scale and draw correction.
        host_home = h in r32_host_home
        pred = four_outcome_prediction(
            adj_att(h), adj_def(h), adj_att(a), adj_def(a),
            home_advantage=ha, rho=rho, host_home=host_home)
        lam, mu = pred["expected_home_goals"], pred["expected_away_goals"]
        o_a_reg = pred["a_win_regulation"]
        o_b_reg = pred["b_win_regulation"]
        o_draw_a = pred["draw_then_a_advances"]
        o_draw_b = pred["draw_then_b_advances"]
        p_a_adv = pred["p_a_advances"]
        p_b_adv = pred["p_b_advances"]

        # Confidence tier on the advance call. The group-stage backtest showed
        # accuracy climbs steeply with confidence (~70% at a 50% 1X2 floor,
        # ~77% at 60%); for a binary advance call we tier on the favourite's
        # advance probability so the user knows which picks to trust.
        conf = max(p_a_adv, p_b_adv)
        favored = (tla_to_name.get(h, h) if p_a_adv >= p_b_adv else tla_to_name.get(a, a))
        tier = confidence_tier(p_a_adv)

        predictions.append({
            "date": m.get("utcDate", "")[:10],
            "team_a": tla_to_name.get(h, h), "tla_a": h,
            "team_b": tla_to_name.get(a, a), "tla_b": a,
            "host_home_a": host_home,
            "favored": favored,
            "confidence": round(conf, 4),
            "tier": tier,
            "expected_goals_a": round(lam, 3),
            "expected_goals_b": round(mu, 3),
            "form_delta_a": {"attack": round(form_att.get(h, 0.0), 3), "defence": round(form_def.get(h, 0.0), 3)},
            "form_delta_b": {"attack": round(form_att.get(a, 0.0), 3), "defence": round(form_def.get(a, 0.0), 3)},
            "outcomes": {
                "a_win_regulation": round(o_a_reg, 4),
                "b_win_regulation": round(o_b_reg, 4),
                "draw_then_a_advances": round(o_draw_a, 4),
                "draw_then_b_advances": round(o_draw_b, 4),
            },
            "p_a_advances": round(p_a_adv, 4),
            "p_b_advances": round(p_b_adv, 4),
        })

    out = {
        "stage": "LAST_32",
        "model_notes": {
            "dc_time_decay_per_year": DC_TIME_DECAY_PER_YEAR,
            "form_metric": "performance_vs_expectation_last3_wc_group_games",
            "form_cap": FORM_CAP,
            "form_smooth": FORM_SMOOTH,
            "form_note": "backtest found form hurts; data-backed default cap=0.0",
            "venue": "neutral_except_real_host_home",
            "host_home_teams": sorted(r32_host_home),
            "home_advantage": round(ha, 4),
            "rho": round(rho, 4),
            "calibration": {
                "source": "WC26 group-stage backtest (70 honest pre-match matches)",
                "goal_scale": cal.GOAL_SCALE,
                "nominal_home_edge": cal.NOMINAL_HOME_EDGE,
                "draw_rho_extra": cal.DRAW_RHO_EXTRA,
                "rho_calibrated": round(cal.calibrated_rho(rho), 4),
            },
        },
        "predictions": predictions,
    }
    out_path = ROOT / "model" / "data" / "processed" / "r32_predictions.json"
    out_path.write_text(json.dumps(out, indent=2))

    # ------------------------------------------------------------- print
    form_label = "off" if FORM_CAP == 0.0 else f"cap={FORM_CAP}"
    print(f"WC26 Round of 32 — four-outcome predictions  (calibrated; form: {form_label})\n")
    hdr = (f"{'Match':<34}{'A win':>7}{'B win':>7}{'D→A':>7}{'D→B':>7}"
           f"{'  ':>2}{'A adv':>7}{'B adv':>7}  tier")
    print(hdr)
    print("-" * len(hdr))
    # Sort by confidence so the trustworthy calls sit at the top.
    for p in sorted(predictions, key=lambda x: -x["confidence"]):
        o = p["outcomes"]
        label = f"{p['team_a']} v {p['team_b']}"
        print(f"{label:<34}"
              f"{o['a_win_regulation']*100:>6.1f}%"
              f"{o['b_win_regulation']*100:>6.1f}%"
              f"{o['draw_then_a_advances']*100:>6.1f}%"
              f"{o['draw_then_b_advances']*100:>6.1f}%"
              f"{'  ':>2}{p['p_a_advances']*100:>6.1f}%{p['p_b_advances']*100:>6.1f}%"
              f"  {p['tier']}")
    print(f"\nSaved → {out_path.relative_to(ROOT)}")

    # Confidence-tier summary: which calls to trust.
    print("\nConfidence tiers (advance call):")
    for tier, lo in (("strong (≥70%)", "strong"), ("lean (60–70%)", "lean"), ("toss-up (<60%)", "tossup")):
        picks = [p for p in predictions if p["tier"] == lo]
        names = ", ".join(f"{p['favored']} {p['confidence']*100:.0f}%" for p in
                          sorted(picks, key=lambda x: -x["confidence"]))
        print(f"  {tier:<16} {len(picks):>2}: {names}")

    # Form-delta audit (who recent form boosted / penalised most) — only when on.
    if FORM_CAP > 0.0:
        print("\nForm deltas applied (attack / defence; +att=hotter, -def=stingier):")
        qualified = {p["tla_a"] for p in predictions} | {p["tla_b"] for p in predictions}
        rows = sorted(qualified, key=lambda t: -(form_att.get(t, 0) - form_def.get(t, 0)))
        for t in rows:
            print(f"  {tla_to_name.get(t, t):<22} att {form_att.get(t,0):+.3f}  def {form_def.get(t,0):+.3f}")


if __name__ == "__main__":
    main()
