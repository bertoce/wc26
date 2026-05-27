# WC26 — World Cup 2026 win-probability model

Predictor for the 2026 FIFA World Cup. Fits a Dixon-Coles Poisson goals model
on 2,400 competitive matches since 2018, simulates the tournament 20,000
times with proper bracket seeding, applies historical-pattern priors
(confederation, host-continent, title pedigree, squad market value), and
publishes per-match, per-team, and per-bracket-slot probabilities to a
Next.js dashboard on Vercel.

**Live:** [wc26-dusky.vercel.app](https://wc26-dusky.vercel.app) (or any production alias)

## Current prediction (model v0.3.0)

| # | Team | Win prob | Notes |
|---|---|---:|---|
| 1 | 🇧🇷 Brazil    | 19.9% | Top combined attack + defence in DC fit; strongest pedigree |
| 2 | 🏴󠁧󠁢󠁥󠁮󠁧󠁿 England   | 16.0% | Highest squad market value (~€1.4B) |
| 3 | 🇪🇸 Spain     | 13.5% | Top DC attack rating |
| 4 | 🇫🇷 France    | 12.2% | Deep squad value, recent title |
| 5 | 🇦🇷 Argentina | 11.8% | Defending champions |

## Architecture

```
wc26/
├── model/                       Python — ingest, fit, simulate, export
│   ├── wc26/
│   │   ├── elo.py              World Football Elo ratings
│   │   ├── dixon_coles.py      Poisson goals MLE fit
│   │   ├── simulator.py        Group stage + seeded bracket + shootouts
│   │   ├── priors.py           Confederation / pedigree / market value
│   │   └── ingest.py           martj42 GitHub + football-data.org
│   ├── scripts/03_run_simulation.py    End-to-end pipeline
│   ├── tests/                  64 pytest tests
│   └── data/
│       ├── static/             Pattern-feature data per team
│       ├── raw/                Cached API + CSV downloads (gitignored)
│       └── processed/          predictions.json output (gitignored)
│
├── web/                         Next.js 16 dashboard
│   ├── app/page.tsx
│   ├── components/             WinnerCard, BracketView, GroupMatches,
│   │                           RoundProbabilities, CompoundExplainer, …
│   └── lib/data/predictions.json   Mirrored from model output
│
└── .github/workflows/predict.yml   Daily cron re-run of the pipeline
```

## Data sources

| Source | What | Auth |
|---|---|---|
| [`martj42/international_results`](https://github.com/martj42/international_results) | 49k historical international matches since 1872 | None |
| [football-data.org](https://www.football-data.org/) | WC26 fixtures, teams, in-tournament results | Free API key |
| `model/data/static/team_features.json` | Confederation, prior wins/semis, squad market value | Hand-curated snapshot |

## Local setup

```bash
# 1. Python model
python3 -m venv .venv
source .venv/bin/activate
cd model
pip install -r requirements.txt
pip install -e .

# (macOS only — XGBoost runtime, even though we don't use XGBoost directly,
# some other dep depends on libomp)
brew install libomp

# 2. Frontend
cd ../web
pnpm install
pnpm dev    # http://localhost:3000
```

Put your football-data.org API key in `.env.local` at the repo root
(see `.env.example`). Get a free key at
[football-data.org/client/register](https://www.football-data.org/client/register).

## Running the pipeline

```bash
cd model
.venv/bin/python scripts/03_run_simulation.py
```

The script: loads 49k historical matches → fits Dixon-Coles on ~2,400
competitive matches since 2018 → builds Team + Fixture objects for the 48
qualified teams → simulates 20,000 tournaments → applies pattern priors →
writes `model/data/processed/predictions.json` and mirrors it to
`web/lib/data/predictions.json` for the dashboard.

Re-runs take ~90 seconds end-to-end.

## Tests

```bash
cd model
.venv/bin/python -m pytest -q
# 64 passed
```

Covers Elo math + K-factor weighting, Dixon-Coles parameter recovery from
synthetic data, group-stage tiebreakers, knockout shootouts, bracket
seeding (standard 32-team layout, same-group separation), per-match W/D/L
predictions, round-survival monotonicity, and pattern-prior log-odds shifts.

## Live updates (during the tournament)

The dashboard refreshes from the pipeline output on every Vercel deploy.
To automate re-runs during the WC26 window (June 11 – July 19, 2026):

1. **Push this repo to GitHub** (any visibility).
2. **Connect the Vercel project to the GitHub repo:**
   Vercel dashboard → Project → Settings → Git → Connect GitHub repo.
   From then on, every push to `main` triggers a fresh deploy.
3. **Add the API key as a GitHub secret:**
   Repo Settings → Secrets and variables → Actions → New repository secret →
   `FOOTBALL_DATA_API_KEY = <your key>`.
4. **Grant the workflow push permission:**
   Repo Settings → Actions → General → Workflow permissions →
   "Read and write permissions" → Save.
5. **Done.** `.github/workflows/predict.yml` runs daily at 12:00 UTC, re-runs
   the pipeline, and commits the updated `predictions.json` only when actual
   numbers (not just the timestamp) move. Each commit triggers a Vercel deploy.

Crank up the cron during match windows by editing the workflow:
```yaml
# every 30 min, 12:00–23:30 UTC, June–July
- cron: '*/30 12-23 * 6-7 *'
```

### Why GitHub Actions and not Vercel Cron?

The pipeline takes ~90s (Dixon-Coles MLE fit + 20k Monte Carlo sims).
Vercel Hobby has a 60s function timeout that would fail; the Pro plan
(300s) would work but isn't required for this project. GH Actions has a
6-hour job limit and apt access for system deps like `libomp`. If the
pipeline ever shrinks below 60s, migrating to Vercel Cron + Blob would
be cleaner.

## Caveats

1. **Bracket seeding is realistic but not exactly FIFA's.** Standard 32-team
   tournament seeding (top vs bottom, same-group separation in R32). The
   official FIFA 48-team bracket uses fixed slot mappings I don't have
   verified specs for; my seeded version is meaningfully better than
   adjacent pairing but isn't bit-perfect to FIFA's draw rules.
2. **No injury or suspension data.** Vinícius pulling out the week before
   would shift probabilities materially and the model wouldn't know.
3. **Pattern priors are hand-calibrated** to match plausible bookmaker
   spreads, not fit to historical WC outcomes. Calibrating to past WCs
   (Groll et al. 2019 style) would be a meaningful upgrade.
4. **Squad market values are my best estimates** for the 48 teams as of
   May 2026, not pulled from a live Transfermarkt scrape.
5. **All matches treated as neutral.** Mexico, USA, and Canada (co-hosts)
   actually get a small home-crowd effect we're not capturing.

## Status

- [x] Pass 1: Pre-tournament static dashboard
- [x] Per-match W/D/L for the 72 group fixtures
- [x] Per-team round-survival probabilities
- [x] Most-likely knockout bracket with matchup confidence
- [x] Real tournament seeding (top vs bottom, same-group separation)
- [x] Live-update workflow ready (GH Actions — needs one-time setup above)
- [ ] FIFA's exact 48-team bracket slot mapping
- [ ] Per-team detail pages
