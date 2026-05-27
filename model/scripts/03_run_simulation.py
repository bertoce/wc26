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
from wc26.priors import TeamPriorFeatures, apply_priors  # noqa: E402
from wc26.simulator import Fixture, Team, simulate_tournament  # noqa: E402

N_SIMS = 20_000
SEED = 2026
RECENT_YEAR_CUTOFF = 2018
HOST_CONTINENT = "North America"

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

    print("  fitting Dixon-Coles (this may take 30-60s)...")
    model = DixonColesModel()
    model.fit(dc_matches)
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

    # Fixtures: only the 72 group-stage matches
    fd_matches = fetch_wc26_matches()["matches"]
    group_matches = [m for m in fd_matches if m["stage"] == "GROUP_STAGE"]
    print(f"  {len(group_matches)} group-stage matches scheduled")

    fixtures: list[Fixture] = []
    skipped = 0
    for m in group_matches:
        home_tla = m["homeTeam"].get("tla")
        away_tla = m["awayTeam"].get("tla")
        if not home_tla or not away_tla or home_tla not in features or away_tla not in features:
            skipped += 1
            continue
        group = (m.get("group") or "").replace("GROUP_", "") or None
        fixtures.append(Fixture(
            home=home_tla,
            away=away_tla,
            neutral=True,  # tournament played in USA/Canada/Mexico — treat all as neutral
            stage="group",
            group=group,
        ))
    if skipped:
        print(f"  ⚠ skipped {skipped} matches with missing team data (likely TBD slots)")
    print(f"  {len(fixtures)} usable group fixtures across "
          f"{len({f.group for f in fixtures})} groups")

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
    )

    raw_probs = results["win_probability"]
    print(f"\n  Top 12 by raw simulator win probability (pre-priors):")
    for i, (tla, p) in enumerate(sorted(raw_probs.items(), key=lambda kv: -kv[1])[:12], 1):
        name = tla_to_name_fd.get(tla, tla)
        print(f"    {i:2d}. {tla}  {name:<25}  {p*100:5.1f}%")

    # -----------------------------------------------------------------------
    header("STEP 6: Apply historical-pattern priors")
    # -----------------------------------------------------------------------
    feat_objs = {
        tla: TeamPriorFeatures(
            confederation=f["confederation"],
            continent=f["continent"],
            prior_wins=f["prior_wins"],
            prior_semis=f["prior_semis"],
            squad_value_eur_m=f["squad_value_eur_m"],
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
            "model_version": "0.1.0",
        },
        "predictions": [
            {
                "tla": tla,
                "name": tla_to_name_fd.get(tla, tla),
                "win_probability_raw": raw_probs.get(tla, 0.0),
                "win_probability_adjusted": adjusted.get(tla, 0.0),
            }
            for tla, _ in sorted_adj
        ],
    }
    out_path = ROOT / "model" / "data" / "processed" / "predictions.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    print(f"  → predictions saved to {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
