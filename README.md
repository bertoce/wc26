# WC26 — World Cup 2026 win-probability model

Live-updating predictor for the 2026 FIFA World Cup. Ensembles a Dixon-Coles
Poisson goals model with an XGBoost W/D/L classifier, simulates the full
tournament 100k times, and publishes each team's path-to-the-trophy
probabilities to a Next.js dashboard on Vercel.

## Architecture

```
model/    Python — ingest, train, simulate, export predictions.json
web/      Next.js 16 — dashboard, bracket viewer, group standings
```

The Python model runs offline (and on a Vercel Cron during the tournament),
writing `predictions.json` to Vercel Blob. The frontend reads the blob with
5-minute ISR.

## Data sources

| Source | What | Auth |
|---|---|---|
| `martj42/international_results` (GitHub) | Historical match results 1872→ | None |
| eloratings.net | World Football Elo ratings | None |
| FIFA | Official rankings | None |
| Transfermarkt | Squad market values | None (scrape, fragile) |
| football-data.org | WC26 fixtures + live results | Free API key |

## Setup

```bash
# Python model
cd model
python3 -m venv ../.venv
source ../.venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ../web
pnpm install
pnpm dev
```

API keys go in `.env.local` at the repo root (see `.env.example`).

## Status

- [ ] Pass 1: Static pre-tournament dashboard (target: before June 11)
- [ ] Pass 2: Live updates during the tournament
