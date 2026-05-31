# Changelog

Version history with rationale. Versions are bumped in
`scripts/03_run_simulation.py`'s `model_version` field — visible on the
dashboard header — and don't strictly follow semver since the entire
project is one bundled artifact (model + UI shipped together).

---

## v0.4.0 — May 30, 2026

### Added
- **1-year half-life time decay** in the Dixon-Coles fit. Matches from
  1 year ago carry weight 0.5; from 8 years ago, weight 0.004. Reflects
  the *current* generation of players rather than the 2018 squads.
- **Host home advantage for MEX/USA/CAN group matches** (6 of 72
  fixtures). Knockouts stay neutral — venues become mixed across the
  three host countries once the bracket plays out.
- **`injuries.json` infrastructure** — pluggable injury data sources via
  `wc26/injury_sources/`, aggregator that combines multiple sources with
  dedup + severity-conflict resolution, refresh script that preserves
  manual edits when no source returns data. Ships empty; populate before
  tournament.
- **`team_chemistry.json` + `chemistry_log_odds` prior** — hand-curated
  high/medium/low ratings produce ±0.10 log-odds bumps. Ships all-medium
  (dormant); override teams you have strong views on.
- **API-Football integration code** (Phase 1) — parser + aggregator +
  fetch wrapper + workflow step. Wired but dormant: the free tier doesn't
  cover WC26. Upgrading to paid plan unlocks automated daily injury
  refresh with zero code changes.

### Changed
- **Argentina is now the predicted favourite (25.6%)**, displacing Brazil
  (23.6%). Time decay's effect on form weighting: their post-2022
  dominance now dominates the fit, where the 2018-2022 era of France
  previously balanced it. France slid from #4 (12.2%) to #7 (3.0%) for
  the same reason.
- DC fit hyperparameters: time_decay_per_year=ln(2), ref_year=2026

### Dependencies (pinned)
- pandas==2.3.3, numpy==2.0.2, scipy==1.13.1, pyarrow==21.0.0
- xgboost==2.1.4, scikit-learn==1.6.1
- requests==2.32.5, beautifulsoup4==4.14.3, lxml==6.1.1
- python-dotenv==1.2.1, tqdm==4.67.3, pytest==8.4.2, pytest-cov==7.1.0

Exact-pinned to avoid surprise breakage from upstream releases during the
tournament. Upgrade deliberately via `pip install -U` + `pip freeze`.

### Tests: 136 passing (+72 vs v0.3.0)
- `test_dixon_coles.py` 14 (+4 TestTimeDecay)
- `test_injuries.py` 15 (new)
- `test_priors.py` 20 (+8 chemistry-related)
- `test_simulator.py` 28 (unchanged)
- `test_venues.py` 16 (new)
- `test_api_football.py` 19 (new)
- `test_aggregator.py` 10 (new)
- `test_elo.py` 14 (unchanged)

### Infrastructure
- GH Actions workflow hardened: actions/checkout@v5 + setup-python@v6
  (Node 24, dodges 2026-06-02 Node 20 deprecation), exact-pinned Python
  deps, pytest gate before pipeline, pnpm@10 (matches Vercel's lockfile
  detection), commits authored as `brto <beto.ceballos@gmail.com>` so they
  link to GitHub profile.
- Deploys via workflow's vercel CLI (`vercel pull/build/deploy --prebuilt`)
  rather than Vercel-GH auto-deploy (which couldn't find the Next.js app
  inside `web/`).
- `force_deploy` workflow_dispatch input for on-demand redeploys.

---

## v0.3.0 — May 27, 2026

### Added
- **Most-likely knockout bracket forecast.** New
  `matchup_distribution` aggregation in the simulator: for each
  (round_size, match_idx), tracks which (home, away) pairings happened
  across all sims. Pipeline picks the modal matchup per slot, runs DC on
  it for the W/D/L, and saves to `predictions.json` as
  `knockout_bracket`.
- **`BracketView` UI** — sections for R32/R16/QF/SF/F with match cards
  showing matchup confidence %, both teams + marginal probabilities,
  W/D/L bar, predicted advancer, xG.
- **Compounding-probability explainer card** above the bracket — shows
  the top team's win prob decomposed as a chain (P(reach R32) ×
  conditional advance rate per round).

### Changed
- **Switched from naive adjacent pairing to standard 32-team tournament
  seeding** in the simulator. Same-group R32 rematches dropped from 75%
  → <5%. Top seeds now in opposite halves of the bracket. Predictions
  shifted: Brazil 23.4% → 19.9% (lost easy R32 slot), England 14.4% →
  16.0%, Argentina 12.8% → 11.8%.
- Dashboard table sort + Win column now use **adjusted** probability
  (matching the chart) instead of raw simulator output (which had Brazil
  at 12.5% while the chart showed 19.9%, confusing).
- Footnote added explaining R32–Final columns are raw simulator survival
  rates; Win* column has pattern priors applied.

### Tests: 64 passing (+9 vs v0.2.0)
- 6 new for bracket seeding (`bracket_seed_order`, same-group separation
  in R32, top seeds in opposite halves)
- 3 new for knockout matchup distribution (sums to 1, dominant team in
  deep rounds)

### Infrastructure
- GitHub repo created at github.com/bertoce/wc26 (public)
- Initial GH Actions cron set up: daily 12:00 UTC, runs pipeline, smart-
  diff commits, deploys

---

## v0.2.0 — May 27, 2026

### Added
- **Per-fixture deterministic W/D/L** for the 72 group matches via
  `predict_group_fixtures()` — uses DC directly, no Monte Carlo needed
  since pairings are known.
- **Per-team round-survival probabilities** — `simulate_tournament` now
  returns `round_survival[tla][k]` = P(team alive when k teams remained).
- `GroupMatchesSection` UI — 12 group cards × 6 matches each, with W/D/L
  stacked bars + xG.
- `RoundProbabilitiesTable` UI — 48 teams × 6 round columns, tone-coded.

### Changed
- `predictions.json` schema gained `group_matches[]` and
  `round_probability` per team.
- Pipeline mirrors `predictions.json` to `web/lib/data/` automatically.

### Tests: 55 passing (+8 vs v0.1.0)

---

## v0.1.0 — May 27, 2026 (initial release)

### Added
- Dixon-Coles MLE fit on 2,393 competitive matches since 2018
- 20,000-sim Monte Carlo tournament with group stage + knockout single-elim
- Pattern priors: confederation, host-continent, title pedigree, market value
- 48-team WC26 fixture list from football-data.org
- Hand-curated `team_features.json` with per-team confederation, prior wins/semis,
  squad market value
- Next.js 16 + Tailwind v4 + shadcn (Base UI) + Recharts dashboard
- Winner card, top-12 chart, full 48-team table
- Vercel deploy at wc26-dusky.vercel.app

### Tests: 47 passing
- Elo: 14
- Dixon-Coles: 10 (now 9 after one test was reframed in v0.4.0)
- Simulator: 11
- Priors: 12

### Initial honest caveats (most still apply)
- Simplified knockout bracket (adjacent pairing — fixed in v0.3.0)
- No injury data (infrastructure added in v0.4.0, automation deferred)
- Pattern priors hand-calibrated (still true)
- Squad market values are estimates (still true)
- All matches treated as neutral (host home for group matches added in v0.4.0)

---

## Upcoming (no version assigned)

Tracked in `gh issue list` and the in-session task tracker:

- **Phase 2: SofaScore scraper** as second injury data source — task #33
- **Phase 3: LLM news-sentiment chemistry scoring** — task #34
- **FIFA's exact 48-team bracket slot mapping** — needs verified spec source
- **Per-team detail pages** — click a team, see their group standings forecast and most likely path
- **Pattern-prior coefficients learned from past WCs** (Groll et al. 2019 style) instead of hand-calibrated
- **Live Transfermarkt squad-value scrape** instead of hand-curated snapshot
