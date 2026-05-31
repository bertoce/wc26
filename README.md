# WC26 — World Cup 2026 win-probability model

A Dixon-Coles Poisson goals model fit on competitive international matches
since 2018 (with 1-year half-life time decay), simulated 20,000 times through
a properly seeded 48-team bracket with FIFA tiebreakers and penalty
shootouts, then adjusted by four historical-pattern priors (confederation,
host-continent, title pedigree, squad market value) and a hand-curated
team-chemistry signal. Published as a Next.js dashboard on Vercel.

**Live:** [wc26-dusky.vercel.app](https://wc26-dusky.vercel.app)
**Repo:** [github.com/bertoce/wc26](https://github.com/bertoce/wc26)
**Model version:** v0.4.0

---

## Current prediction

| # | Team | Adjusted win prob | Notes |
|---|---|---:|---|
| 1 | 🇦🇷 Argentina | **25.6%** | Recent dominance — WC22 + Copa 24, top of DC fit under time decay |
| 2 | 🇧🇷 Brazil    | **23.6%** | Best combined attack + defence, strongest pedigree |
| 3 | 🏴󠁧󠁢󠁥󠁮󠁧󠁿 England   | **15.5%** | Highest squad market value (~€1.4B) |
| 4 | 🇪🇸 Spain     | **8.1%** | Top DC attack rating |
| 5 | 🇨🇴 Colombia  | **7.2%** | Recent strong CONMEBOL form |

Italy did not qualify. France slid from #4 (v0.3.0) to #7 (v0.4.0) when
time decay reduced the weight of their 2018–2022 peak. Full table on the
[dashboard](https://wc26-dusky.vercel.app).

---

## Read the docs

| Doc | What's in it |
|---|---|
| [`docs/MODEL.md`](docs/MODEL.md) | The prediction model in depth — four layers, math, references, calibration choices |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | Runbook: setup, daily maintenance, manual data edits, troubleshooting, extending the model |
| [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | Version history with rationale for each release |

---

## Repo layout

```
wc26/
├── model/                              Python — ingest, fit, simulate, export
│   ├── wc26/
│   │   ├── elo.py                     World Football Elo (sanity / reference)
│   │   ├── dixon_coles.py             Poisson goals MLE fit with optional time decay
│   │   ├── simulator.py               Group stage + seeded 32-team bracket + shootouts
│   │   ├── priors.py                  Confederation / pedigree / market value / chemistry
│   │   ├── venues.py                  Host-nation home-advantage policy
│   │   ├── injuries.py                Squad-value adjustment from manual injuries.json
│   │   ├── ingest.py                  martj42 GitHub + football-data.org
│   │   └── injury_sources/            Pluggable injury data sources (API-Football wired)
│   ├── scripts/
│   │   ├── 01_check_ingest.py         Smoke-test historical data load
│   │   ├── 02_fetch_wc26.py           Pull WC26 fixtures + teams
│   │   ├── 03_run_simulation.py       End-to-end prediction pipeline
│   │   ├── 04_discover_api_football_team_ids.py   One-time team-ID lookup
│   │   └── 05_refresh_injuries.py     Daily injury refresh (paid plan required)
│   ├── tests/                         136 pytest tests
│   ├── data/static/                   Hand-curated per-team data
│   └── data/{raw,processed}/          Caches + outputs (gitignored)
│
├── web/                                Next.js 16 dashboard (statically prerendered)
│   ├── app/page.tsx
│   ├── components/                    WinnerCard, BracketView, TopChart,
│   │                                  GroupMatches, RoundProbabilities,
│   │                                  CompoundExplainer, PredictionsTable
│   └── lib/data/predictions.json      Mirrored from the model output
│
├── .github/workflows/predict.yml       Daily cron — re-runs pipeline, commits, deploys
└── docs/                               This documentation set
```

---

## Quick start

```bash
# Python model
python3 -m venv .venv
source .venv/bin/activate
cd model
pip install -r requirements.txt
pip install -e .

# macOS only — runtime needed by xgboost (transitive dep, even though we don't use it)
brew install libomp

# Frontend
cd ../web
pnpm install
pnpm dev          # http://localhost:3000

# Run the model once locally
cd ../model
../.venv/bin/python scripts/03_run_simulation.py
```

API keys go in `.env.local` at the repo root — `FOOTBALL_DATA_API_KEY`
(required) and optionally `API_FOOTBALL_KEY` (currently dormant; see
[`docs/OPERATIONS.md`](docs/OPERATIONS.md#injury-data-sources)).

---

## Tests

```bash
cd model
../.venv/bin/python -m pytest -q     # 136 passed
```

TDD throughout — every model component, prior, simulator behaviour, parser,
aggregator, and venue policy has tests pinning down its expected behaviour.

---

## Status

| Feature | State |
|---|---|
| Dixon-Coles fit with 1-year half-life time decay | ✅ |
| 20,000-sim tournament with seeded 32-team bracket + FIFA tiebreakers | ✅ |
| Pattern priors: confederation, host-continent, pedigree, market value | ✅ |
| Team chemistry prior (data scaffold, defaults to medium) | ✅ |
| Host home advantage for MEX/USA/CAN group matches | ✅ |
| Per-match W/D/L predictions for 72 group fixtures | ✅ |
| Per-team round-survival probabilities | ✅ |
| Most-likely knockout bracket forecast | ✅ |
| Dashboard with chart, bracket viewer, compounding explainer, tables | ✅ |
| Daily auto-refresh via GitHub Actions + Vercel deploy | ✅ |
| Manual injury data scaffold (`injuries.json`) | ✅ infrastructure ready |
| Automated injury fetching | ⏸ deferred — API-Football free tier doesn't cover WC26 |
| LLM news-sentiment chemistry scoring | ⏸ deferred — design ready, not built |
| FIFA's exact 48-team slot mapping | ❌ not done — using standard tournament seeding |
| Per-team detail pages | ❌ not done |

See [`docs/CHANGELOG.md`](docs/CHANGELOG.md) for version history and
[`docs/OPERATIONS.md`](docs/OPERATIONS.md) for how to pick up any deferred work.

---

## License & credit

Personal project. Data sources cited inline above and in `docs/MODEL.md`.
Built end-to-end during May 2026 ahead of the tournament's June 11 kickoff.
