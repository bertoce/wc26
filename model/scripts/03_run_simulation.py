"""End-to-end WC26 prediction pipeline.

Run from model/:
    .venv/bin/python scripts/03_run_simulation.py

Steps:
  1. Load historical international results (martj42)
  2. Compute Elo ratings over full history (for sanity output)
  3. Fit Dixon-Coles on recent competitive matches (2018+)
  4. Load WC26 team list, fixtures, and pattern features
  5. Build Team objects from DC fit + features
  6. Build Fixture objects from WC26 group-stage matches
  7. Run tournament simulator 20,000 times
  8. Apply pattern priors (confederation, host-continent, pedigree, market value)
  9. Print top-10 winners + most likely champion
 10. Save predictions.json
"""

import json
from collections import Counter
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env.local")

from wc26.dixon_coles import DixonColesModel  # noqa: E402
from wc26.elo import run_history  # noqa: E402
from wc26.ingest import (  # noqa: E402
    fetch_wc26_matches,
    fetch_wc26_teams,
    load_results,
    results_to_matches,
)
from wc26.injuries import (  # noqa: E402
    adjusted_squad_value,
    injury_impacts,
    load_injuries,
    out_value_for_team,
)
from wc26.priors import TeamPriorFeatures, apply_priors  # noqa: E402
from wc26.results import extract_finished_group_results, result_key  # noqa: E402
from wc26.snapshots import load_snapshots, save_snapshots, update_snapshots  # noqa: E402
from wc26.simulator import (  # noqa: E402
    Fixture,
    Team,
    predict_group_fixtures,
    simulate_tournament,
)
from wc26.venues import is_host_home_fixture  # noqa: E402

N_SIMS = 20_000
SEED = 2026
RECENT_YEAR_CUTOFF = 2018
HOST_CONTINENT = "North America"

# Time-decay weighting for the Dixon-Coles fit. ln(2) ≈ 0.693 gives a 1-year
# half-life — a match from 1 year ago counts ~50%, 2 years ~25%, 4 years ~6%,
# 8 years ~0.4%. Net effect: the model reflects the *current* generation of
# players, not the 2018 squads (Messi/Ronaldo of that era ≠ today's teams).
DC_TIME_DECAY_PER_YEAR = 0.693
DC_REF_YEAR = 2026

# Tournaments to use for Dixon-Coles fit. Friendlies excluded — too noisy.
COMPETITIVE_KEYWORDS = (
    "FIFA World Cup",
    "UEFA Euro",
    "UEFA Nations League",
    "Copa América",
    "African Cup of Nations",
    "AFC Asian Cup",
    "Gold Cup",
    "Confederations Cup",
    "CONCACAF",
    "qualification",
    "Nations League",
)


def is_competitive(tournament: str) -> bool:
    if not tournament or tournament == "Friendly":
        return False
    return any(kw.lower() in tournament.lower() for kw in COMPETITIVE_KEYWORDS)


def header(text: str) -> None:
    print()
    print("=" * 70)
    print(text)
    print("=" * 70)


def main() -> None:
    # -----------------------------------------------------------------------
    header("STEP 1: Load historical international results")
    # -----------------------------------------------------------------------
    df = load_results()
    print(f"  loaded {len(df):,} matches ({df.date.min().date()} → {df.date.max().date()})")

    # -----------------------------------------------------------------------
    header("STEP 2: Compute Elo over full history")
    # -----------------------------------------------------------------------
    all_matches = results_to_matches(df.sort_values("date"))
    elo = run_history(all_matches)
    top_elo = sorted(elo.items(), key=lambda kv: -kv[1])[:15]
    print("  Top 15 by Elo:")
    for i, (t, r) in enumerate(top_elo, 1):
        print(f"    {i:2d}. {t:<25}  {r:7.1f}")

    # -----------------------------------------------------------------------
    header("STEP 3: Fit Dixon-Coles on recent competitive matches")
    # -----------------------------------------------------------------------
    recent = df[(df.date.dt.year >= RECENT_YEAR_CUTOFF) & df.tournament.map(is_competitive)].copy()
    print(f"  using {len(recent):,} competitive matches since {RECENT_YEAR_CUTOFF}")

    # Load WC26 team list + features so we can filter to relevant matches
    features = json.loads((ROOT / "model" / "data" / "static" / "team_features.json").read_text())
    features = {k: v for k, v in features.items() if not k.startswith("_")}
    wc26_team_names = {v["name_historical"] for v in features.values()}
    print(f"  WC26 teams: {len(wc26_team_names)}")

    # Keep matches where at least one side is a WC26 team — improves param recovery for our 48
    mask = recent.home_team.isin(wc26_team_names) | recent.away_team.isin(wc26_team_names)
    recent = recent[mask].copy()
    print(f"  {len(recent):,} matches involve at least one WC26 team")

    dc_matches = [
        {
            "date": row.date.strftime("%Y-%m-%d"),
            "home": row.home_team,
            "away": row.away_team,
            "home_goals": int(row.home_score),
            "away_goals": int(row.away_score),
            "neutral": bool(row.neutral),
        }
        for row in recent.itertuples(index=False)
    ]

    print(f"  fitting Dixon-Coles with time decay "
          f"(1-yr half-life ≈ {DC_TIME_DECAY_PER_YEAR:.3f}/yr, ref={DC_REF_YEAR}) ...")
    model = DixonColesModel()
    model.fit(
        dc_matches,
        time_decay_per_year=DC_TIME_DECAY_PER_YEAR,
        ref_year=DC_REF_YEAR,
    )
    print(f"  ✓ fit done.  home_advantage γ = {model.home_advantage:+.3f}  ρ = {model.rho:+.3f}")
    print(f"  ✓ parameters for {len(model.attack)} teams")

    # Show top 10 by attack and best 10 by defence (lowest β)
    top_attack = sorted(model.attack.items(), key=lambda kv: -kv[1])[:10]
    print("\n  Top 10 attack strength (DC α):")
    for t, a in top_attack:
        in_wc = "✓" if t in wc26_team_names else " "
        print(f"    [{in_wc}]  {t:<25}  α = {a:+.3f}")

    best_defence = sorted(model.defence.items(), key=lambda kv: kv[1])[:10]
    print("\n  Best 10 defences (lowest DC β = least leaky):")
    for t, b in best_defence:
        in_wc = "✓" if t in wc26_team_names else " "
        print(f"    [{in_wc}]  {t:<25}  β = {b:+.3f}")

    # -----------------------------------------------------------------------
    header("STEP 4: Build Team + Fixture objects for the 48 WC26 sides")
    # -----------------------------------------------------------------------
    fd_teams = fetch_wc26_teams()["teams"]
    tla_to_name_fd = {t["tla"]: t["name"] for t in fd_teams}

    teams: list[Team] = []
    missing_dc = []
    # Clip DC params to a sane range to prevent data artifacts (e.g. New Zealand's
    # β = -1.7 from only-OFC-opposition) from warping the simulator.
    ATTACK_CLIP = (-0.8, 1.5)
    DEFENCE_CLIP = (-1.1, 1.5)
    clipped_count = 0
    for tla, feat in features.items():
        hist_name = feat["name_historical"]
        if hist_name not in model.attack:
            missing_dc.append((tla, hist_name))
            attack = 0.0
            defence = 0.5
        else:
            raw_a = model.attack[hist_name]
            raw_d = model.defence[hist_name]
            attack = max(ATTACK_CLIP[0], min(ATTACK_CLIP[1], raw_a))
            defence = max(DEFENCE_CLIP[0], min(DEFENCE_CLIP[1], raw_d))
            if attack != raw_a or defence != raw_d:
                clipped_count += 1
        teams.append(Team(
            code=tla,
            name=hist_name,
            attack=attack,
            defence=defence,
            confederation=feat["confederation"],
        ))
    if clipped_count:
        print(f"  ⚠ clipped DC params for {clipped_count} teams (sane-range guard "
              f"against weak-opposition artifacts)")
    if missing_dc:
        print(f"  ⚠ {len(missing_dc)} WC26 teams missing from DC fit (using neutral params):")
        for tla, name in missing_dc:
            print(f"      {tla}  {name}")

    # Fixtures: only the 72 group-stage matches.
    # force=True — during the tournament, match statuses + scores change
    # between runs; a stale cache would hide finished results.
    fd_matches = fetch_wc26_matches(force=True)["matches"]
    group_matches = [m for m in fd_matches if m["stage"] == "GROUP_STAGE"]
    print(f"  {len(group_matches)} group-stage matches scheduled")

    # Extract real results for matches already played — these get locked
    # into every simulation instead of being re-simulated.
    known_results = extract_finished_group_results(fd_matches)
    finished_keys = {
        result_key(kr["group"], kr["home"], kr["away"]) for kr in known_results
    }
    if known_results:
        print(f"  {len(known_results)} group matches FINISHED — locking real scores:")
        for kr in known_results[:6]:
            print(f"    {kr['group']}  {kr['home']} {kr['home_goals']}–{kr['away_goals']} {kr['away']}")
        if len(known_results) > 6:
            print(f"    … and {len(known_results) - 6} more")
    else:
        print("  No finished group matches yet — all 72 fixtures simulated.")

    fixtures: list[Fixture] = []
    fixture_dates: dict[tuple[str, str, str | None], str] = {}
    skipped = 0
    n_host_home = 0
    for m in group_matches:
        home_tla = m["homeTeam"].get("tla")
        away_tla = m["awayTeam"].get("tla")
        if not home_tla or not away_tla or home_tla not in features or away_tla not in features:
            skipped += 1
            continue
        group = (m.get("group") or "").replace("GROUP_", "") or None
        # Host nations (MEX/USA/CAN) play their group matches in their own
        # country and get home advantage. All other group matches and all
        # knockouts are treated as neutral.
        host_home = is_host_home_fixture(home_tla, "group")
        if host_home:
            n_host_home += 1
        fixtures.append(Fixture(
            home=home_tla,
            away=away_tla,
            neutral=not host_home,
            stage="group",
            group=group,
        ))
        fixture_dates[(home_tla, away_tla, group)] = m.get("utcDate", "")
    if skipped:
        print(f"  ⚠ skipped {skipped} matches with missing team data (likely TBD slots)")
    print(f"  {len(fixtures)} usable group fixtures across "
          f"{len({f.group for f in fixtures})} groups "
          f"({n_host_home} with host-team home advantage)")

    # -----------------------------------------------------------------------
    header("STEP 5: Run tournament simulator")
    # -----------------------------------------------------------------------
    print(f"  N = {N_SIMS:,}  seed = {SEED}")
    # 48 teams, 12 groups of 4: top 2 + best 8 thirds → 32 teams in knockout
    results = simulate_tournament(
        teams=teams,
        fixtures=fixtures,
        n_sims=N_SIMS,
        seed=SEED,
        home_advantage=model.home_advantage,
        rho=model.rho,
        qualifiers_per_group=2,
        best_thirds=8,
        known_results=known_results,
    )

    raw_probs = results["win_probability"]
    round_survival = results["round_survival"]
    matchup_distribution = results["matchup_distribution"]
    print(f"\n  Top 12 by raw simulator win probability (pre-priors):")
    for i, (tla, p) in enumerate(sorted(raw_probs.items(), key=lambda kv: -kv[1])[:12], 1):
        name = tla_to_name_fd.get(tla, tla)
        print(f"    {i:2d}. {tla}  {name:<25}  {p*100:5.1f}%")

    # -----------------------------------------------------------------------
    header("STEP 6: Apply historical-pattern priors")
    # -----------------------------------------------------------------------
    # Load injury data and adjust each team's effective squad value before
    # passing to the market-value prior. `out` players' Transfermarkt values
    # are subtracted; `doubtful` players are informational only.
    injuries = load_injuries(ROOT / "model" / "data" / "static" / "injuries.json")
    nonzero_impacts = [i for i in injury_impacts(injuries) if i.out_count > 0]
    if nonzero_impacts:
        print(f"  Applying injuries to {len(nonzero_impacts)} teams:")
        for imp in sorted(nonzero_impacts, key=lambda i: -i.out_value_eur_m):
            print(f"    {imp.team_tla}  −€{imp.out_value_eur_m:.0f}M  "
                  f"({imp.out_count} out, {imp.doubtful_count} doubtful)")
    else:
        print(f"  No active injuries reported in injuries.json — squad values unchanged.")

    # Load team chemistry ratings (hand-curated). Missing teams / "medium" → 0 bump.
    chem_path = ROOT / "model" / "data" / "static" / "team_chemistry.json"
    chemistry_data = json.loads(chem_path.read_text()) if chem_path.exists() else {}
    chemistry_data = {k: v for k, v in chemistry_data.items() if not k.startswith("_")}
    n_high = sum(1 for v in chemistry_data.values() if v.get("chemistry") == "high")
    n_low = sum(1 for v in chemistry_data.values() if v.get("chemistry") == "low")
    if n_high or n_low:
        print(f"  Chemistry overrides: {n_high} high, {n_low} low "
              f"(rest neutral or unset)")
    else:
        print(f"  No chemistry overrides set — all teams treated as neutral.")

    feat_objs = {
        tla: TeamPriorFeatures(
            confederation=f["confederation"],
            continent=f["continent"],
            prior_wins=f["prior_wins"],
            prior_semis=f["prior_semis"],
            squad_value_eur_m=adjusted_squad_value(
                f["squad_value_eur_m"], injuries, tla,
            ),
            chemistry=chemistry_data.get(tla, {}).get("chemistry"),
        )
        for tla, f in features.items()
    }
    adjusted = apply_priors(raw_probs, feat_objs, host_continent=HOST_CONTINENT)

    print(f"\n  Top 12 after pattern-prior adjustment:")
    sorted_adj = sorted(adjusted.items(), key=lambda kv: -kv[1])
    for i, (tla, p) in enumerate(sorted_adj[:12], 1):
        name = tla_to_name_fd.get(tla, tla)
        raw = raw_probs.get(tla, 0.0)
        delta = (p - raw) * 100
        sign = "+" if delta >= 0 else ""
        print(f"    {i:2d}. {tla}  {name:<25}  {p*100:5.1f}%  ({sign}{delta:.1f} vs raw)")

    # -----------------------------------------------------------------------
    header(" 🏆  WC26 PREDICTION  🏆")
    # -----------------------------------------------------------------------
    winner_tla, winner_p = sorted_adj[0]
    winner_name = tla_to_name_fd.get(winner_tla, winner_tla)
    runner_tla, runner_p = sorted_adj[1]
    runner_name = tla_to_name_fd.get(runner_tla, runner_tla)
    print(f"\n  Most likely champion:  {winner_name}  ({winner_p*100:.1f}%)")
    print(f"  Runner-up by prob:     {runner_name}  ({runner_p*100:.1f}%)")
    print()

    # -----------------------------------------------------------------------
    header("STEP 7: Per-match group-stage W/D/L predictions")
    # -----------------------------------------------------------------------
    teams_by_code = {t.code: t for t in teams}
    group_preds_raw = predict_group_fixtures(
        fixtures=fixtures,
        teams_by_code=teams_by_code,
        home_advantage=model.home_advantage,
        rho=model.rho,
    )
    group_preds = []
    for gp in group_preds_raw:
        key = (gp["home"], gp["away"], gp["group"])
        group_preds.append({
            **gp,
            "home_name": tla_to_name_fd.get(gp["home"], gp["home"]),
            "away_name": tla_to_name_fd.get(gp["away"], gp["away"]),
            "utc_date": fixture_dates.get(key, ""),
        })
    print(f"  computed {len(group_preds)} per-fixture predictions")
    # Show a few examples
    sample = sorted(group_preds, key=lambda p: p.get("utc_date", ""))[:3]
    for p in sample:
        print(f"    {p['group']:>2}  {p['home']:>3} vs {p['away']:<3}  "
              f"H/D/A = {p['p_home_win']*100:4.1f}% / {p['p_draw']*100:4.1f}% / {p['p_away_win']*100:4.1f}%  "
              f"xG = {p['expected_home_goals']:.2f}–{p['expected_away_goals']:.2f}")

    # -----------------------------------------------------------------------
    # Pre-match snapshot store: freeze predictions for finished fixtures.
    # The dashboard's "predicted vs actual" comparison uses the FROZEN
    # pre-match numbers, never the latest re-fit (which has seen the result).
    # -----------------------------------------------------------------------
    snapshots_path = ROOT / "model" / "data" / "state" / "prematch_snapshots.json"
    snapshots = load_snapshots(snapshots_path)
    snapshots = update_snapshots(snapshots, group_preds, finished_keys)
    save_snapshots(snapshots_path, snapshots)
    n_frozen = sum(1 for k in snapshots if k in finished_keys)
    print(f"  snapshot store: {len(snapshots)} fixtures tracked, {n_frozen} frozen")

    # Actual scores for finished matches, keyed like the snapshot store
    actuals: dict[str, dict] = {}
    for kr in known_results:
        actuals[result_key(kr["group"], kr["home"], kr["away"])] = kr

    def _outcome(hg: int, ag: int) -> str:
        return "H" if hg > ag else ("A" if ag > hg else "D")

    def _predicted_outcome(p: dict) -> str:
        probs = {"H": p["p_home_win"], "D": p["p_draw"], "A": p["p_away_win"]}
        return max(probs, key=probs.get)

    # Enrich each fixture entry: status, actual score, frozen pre-match probs
    enriched_preds = []
    for gp in group_preds:
        key = result_key(gp["group"], gp["home"], gp["away"])
        entry = dict(gp)
        actual = actuals.get(key)
        if actual is not None:
            snap = snapshots.get(key, {})
            # Use the FROZEN pre-match probabilities for display
            for f in ("p_home_win", "p_draw", "p_away_win",
                      "expected_home_goals", "expected_away_goals"):
                if f in snap:
                    entry[f] = snap[f]
            entry["status"] = "FINISHED"
            entry["actual_home_goals"] = actual["home_goals"]
            entry["actual_away_goals"] = actual["away_goals"]
            entry["prediction_post_hoc"] = bool(snap.get("post_hoc", False))
            entry["predicted_outcome"] = _predicted_outcome(entry)
            entry["actual_outcome"] = _outcome(actual["home_goals"], actual["away_goals"])
            entry["prediction_hit"] = entry["predicted_outcome"] == entry["actual_outcome"]
        else:
            entry["status"] = "SCHEDULED"
        enriched_preds.append(entry)
    group_preds = enriched_preds

    n_finished = sum(1 for p in group_preds if p["status"] == "FINISHED")
    if n_finished:
        n_hits = sum(1 for p in group_preds if p.get("prediction_hit"))
        print(f"  finished: {n_finished} matches — model's most-likely outcome "
              f"hit {n_hits}/{n_finished}")

    # Round-survival named for WC26 (32→R32, 16→R16, 8→QF, 4→SF, 2→F, 1→Win)
    ROUND_NAMES = {32: "reach_r32", 16: "reach_r16", 8: "reach_qf",
                   4: "reach_sf", 2: "reach_final", 1: "win"}
    round_probs: dict[str, dict[str, float]] = {}
    for tla, surv in round_survival.items():
        round_probs[tla] = {ROUND_NAMES[k]: v for k, v in surv.items() if k in ROUND_NAMES}

    # -----------------------------------------------------------------------
    header("STEP 8: Build most-likely knockout bracket")
    # -----------------------------------------------------------------------
    import numpy as np  # noqa: E402
    from wc26.dixon_coles import match_outcome_probabilities  # noqa: E402

    BRACKET_ROUND_NAMES = {32: "R32", 16: "R16", 8: "QF", 4: "SF", 2: "F"}
    knockout_bracket = []
    for round_size in [32, 16, 8, 4, 2]:
        by_match = matchup_distribution.get(round_size, {})
        if not by_match:
            continue
        round_matches = []
        for match_idx in sorted(by_match.keys()):
            matchups = by_match[match_idx]
            if not matchups:
                continue
            # Most likely matchup (specific pair) at this slot
            top_pair, top_p = max(matchups.items(), key=lambda kv: kv[1])
            home_top, away_top = top_pair
            # Marginal probability each side is the most-likely team in its slot
            home_marginal = sum(p for (h, _), p in matchups.items() if h == home_top)
            away_marginal = sum(p for (_, a), p in matchups.items() if a == away_top)
            # W/D/L for the most-likely matchup using clipped DC params (neutral venue)
            th = teams_by_code[home_top]
            ta = teams_by_code[away_top]
            lam = float(np.exp(th.attack + ta.defence))
            mu = float(np.exp(ta.attack + th.defence))
            p_h, p_d, p_a = match_outcome_probabilities(lam, mu, rho=model.rho)
            round_matches.append({
                "match_idx": match_idx,
                "home_top": home_top,
                "home_top_name": tla_to_name_fd.get(home_top, home_top),
                "p_home_top": home_marginal,
                "away_top": away_top,
                "away_top_name": tla_to_name_fd.get(away_top, away_top),
                "p_away_top": away_marginal,
                "p_matchup_top": top_p,
                "p_home_win": p_h,
                "p_draw": p_d,
                "p_away_win": p_a,
                "expected_home_goals": lam,
                "expected_away_goals": mu,
            })
        knockout_bracket.append({
            "round": BRACKET_ROUND_NAMES[round_size],
            "round_size": round_size,
            "n_matches": len(round_matches),
            "matches": round_matches,
        })
        print(f"  {BRACKET_ROUND_NAMES[round_size]:>4}  {len(round_matches)} matches  "
              f"(most likely: {round_matches[0]['home_top']} vs {round_matches[0]['away_top']} "
              f"@ {round_matches[0]['p_matchup_top']*100:.1f}%)")

    # -----------------------------------------------------------------------
    # Save predictions.json
    # -----------------------------------------------------------------------
    out = {
        "metadata": {
            "generated_at": pd.Timestamp.utcnow().isoformat(),
            "n_sims": N_SIMS,
            "seed": SEED,
            "host_continent": HOST_CONTINENT,
            "n_teams": len(teams),
            "n_group_fixtures": len(fixtures),
            "dc_home_advantage": model.home_advantage,
            "dc_rho": model.rho,
            "dc_fit_matches": len(dc_matches),
            "model_version": "0.5.0",
            "n_finished_matches": len(known_results),
        },
        "predictions": [
            {
                "tla": tla,
                "name": tla_to_name_fd.get(tla, tla),
                "win_probability_raw": raw_probs.get(tla, 0.0),
                "win_probability_adjusted": adjusted.get(tla, 0.0),
                "round_probability": round_probs.get(tla, {}),
            }
            for tla, _ in sorted_adj
        ],
        "group_matches": sorted(group_preds, key=lambda p: (p.get("group") or "", p.get("utc_date", ""))),
        "knockout_bracket": knockout_bracket,
    }
    out_path = ROOT / "model" / "data" / "processed" / "predictions.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\n  → predictions saved to {out_path.relative_to(ROOT)}")

    # Also copy into web/lib/data so the dashboard picks it up on next build
    web_path = ROOT / "web" / "lib" / "data" / "predictions.json"
    if web_path.parent.exists():
        web_path.write_text(json.dumps(out, indent=2))
        print(f"  → mirrored to {web_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
