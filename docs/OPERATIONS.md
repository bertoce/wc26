# Operations runbook

How the project runs day-to-day, how to maintain it, how to extend it, and
how to debug when something breaks.

## Daily lifecycle (no human input needed)

```
12:00 UTC every day
    │
    └── GitHub Actions cron triggers .github/workflows/predict.yml
            │
            ├── Set up Python 3.11 + libomp
            ├── Install Python deps (exact-pinned)
            ├── pytest -q                      ← 136 tests
            ├── scripts/05_refresh_injuries.py ← currently no-op (no source)
            ├── scripts/03_run_simulation.py   ← ~90s, writes predictions.json
            ├── Smart-diff predictions.json
            │     │
            │     ├── No meaningful change (only generated_at moved) → exit clean, no commit
            │     └── Real change → commit + push as brto <beto.ceballos@gmail.com>
            │
            └── If commit happened OR force_deploy=true:
                  npm install pnpm@10 + vercel@latest
                  vercel pull/build/deploy --prebuilt --prod
                  Deploy lands at wc26-dusky.vercel.app within ~30s
```

## Manual triggers

### Force a redeploy with current data

GitHub UI: **Actions** → **Update WC26 predictions** → **Run workflow** →
toggle `force_deploy: true` → **Run workflow**. Deploys even if numbers
didn't change. Useful for verifying the deploy path after secret/config
changes.

Or from CLI:
```bash
gh workflow run predict.yml --repo bertoce/wc26 --field force_deploy=true
gh run watch <run_id> --repo bertoce/wc26
```

### Run the pipeline locally

```bash
cd /Users/berto/Documents/wc26/model
../.venv/bin/python scripts/03_run_simulation.py
# ~90 seconds; writes model/data/processed/predictions.json
# and mirrors to web/lib/data/predictions.json
```

### Deploy from local without going through cron

```bash
cd /Users/berto/Documents/wc26/web
pnpm build               # validates locally
vercel deploy --prod --yes
```

## Editing static data

All hand-curated data lives in `model/data/static/`. After any edit, the
next cron run (or local pipeline run) picks it up.

### Editing pattern features (`team_features.json`)

Per-team confederation, continent, prior wins/semis, baseline squad value.
Edit before kickoff if a team's market value has moved meaningfully (e.g.
a key transfer window), or to fix data errors.

Schema:
```json
"BRA": {
  "name_historical": "Brazil",
  "confederation": "CONMEBOL",
  "continent": "South America",
  "prior_wins": 5,
  "prior_semis": 11,
  "squad_value_eur_m": 1050
}
```

### Editing injuries (`injuries.json`)

Per-team list of "out" and "doubtful" players. Out-player TM values get
subtracted from squad_value_eur_m before the market-value prior fires.
Doubtful is informational only.

```json
"BRA": {
  "out": [
    { "name": "Vinicius Jr", "tm_value_eur_m": 200, "note": "ACL" }
  ],
  "doubtful": [
    { "name": "Casemiro", "tm_value_eur_m": 30, "note": "hamstring tweak" }
  ]
}
```

**The refresh script (`05_refresh_injuries.py`) preserves your manual
edits** as long as no automated source returns data (currently the case).
If you later wire up a paid source, the merge logic combines automatic +
manual entries.

### Editing team chemistry (`team_chemistry.json`)

Per-team chemistry rating. Defaults to medium (no effect). Set to high or
low for teams where you have a strong read.

```json
"ARG": {
  "chemistry": "high",
  "coach_years": 5,
  "note": "Scaloni continuity since 2018, WC + Copa winners"
}
```

Bumps are intentionally small:
- `high`: +0.10 log-odds (≈ +2-3pp at moderate baselines)
- `low`: −0.10
- `medium` or missing: 0

## Tournament-time procedure

Suggested workflow during WC26 (June 11 – July 19):

1. **Crank up cron frequency** for match windows by editing
   `.github/workflows/predict.yml`:
   ```yaml
   on:
     schedule:
       - cron: '*/30 12-23 * 6-7 *'   # every 30 min, 12:00-23:30 UTC, June–July
   ```
2. **Update `injuries.json` as news breaks.** ~2-3 minutes per edit.
   Pre-tournament squads are announced ~1 week before kickoff — that's
   your authoritative source for initial population.
3. **Review the dashboard** after each match day. Round-survival numbers
   should evolve in line with what actually happened.
4. **Watch the Actions tab** for any red runs. The workflow's smart-diff
   means most days won't even commit (nothing changed) — that's expected.

## Secrets

Set as GitHub Actions secrets via `gh secret set NAME --repo bertoce/wc26`:

| Secret | Purpose | Required? |
|---|---|---|
| `FOOTBALL_DATA_API_KEY` | Pulls WC26 fixtures + live results from football-data.org | Yes |
| `VERCEL_TOKEN` | Authenticates the deploy step | Yes |
| `VERCEL_ORG_ID` | Vercel team identifier | Yes |
| `VERCEL_PROJECT_ID` | Vercel project identifier | Yes |
| `API_FOOTBALL_KEY` | API-Football injuries (currently dormant — free tier doesn't cover WC26) | No |

To rotate any secret:
```bash
gh secret set NAME --repo bertoce/wc26
# paste new value, Enter
```

Locally, the same values live in `/Users/berto/Documents/wc26/.env.local`
(gitignored). Format:
```
FOOTBALL_DATA_API_KEY=...
API_FOOTBALL_KEY=...
```

## Injury data sources

### Today

`injuries.json` is **manually curated**. The automated refresh step
(`05_refresh_injuries.py`) runs daily but no-ops because:

- API-Football free tier ($0/mo) doesn't cover the WC league
- The `/injuries` endpoint returns 0 results across all tested seasons on the free plan

### To enable automated refresh

| Path | Cost | Effort | Reliability |
|---|---|---|---|
| **Upgrade API-Football to Pro plan** | ~$19/mo | Zero code — existing infra picks it up | High |
| **Build SofaScore scraper** (Phase 2, task #33) | Free | Several hours; fragile to layout changes | Mediocre |
| **Pay for football-data.org Tier One** (we already use them) | €30/mo | Zero code with small adapter | High |

The injury-source plugin system is in place — adding another source means
implementing one function and adding to the aggregator's source list.

## Adding a new injury source

The plugin contract is one function: given a team TLA, return a list of
`RawInjury` objects.

1. Create `model/wc26/injury_sources/yoursource.py`:
   ```python
   from .base import RawInjury

   def fetch_team_injuries(team_tla: str, ...) -> list[RawInjury]:
       # your fetching logic
       return [...]
   ```
2. Add tests in `model/tests/test_yoursource.py` with mocked responses
3. In `scripts/05_refresh_injuries.py`, fetch from your source and pass
   to `merge_injuries(api_football_results, yoursource_results)`
4. The aggregator handles dedup, severity conflicts, and source tracking

See `model/wc26/injury_sources/api_football.py` for a complete reference
implementation.

## Debugging

### "The site shows stale predictions"

1. Check production aliases:
   ```bash
   vercel alias ls --scope rtopos-projects | grep wc26
   ```
   All three should point at the same recent deployment.
2. Check the most recent successful deploy:
   ```bash
   vercel ls wc26 --scope rtopos-projects | head -3
   ```
3. Inspect what's in the live JSON:
   ```bash
   grep -E '"model_version"|"generated_at"' web/lib/data/predictions.json
   ```
4. If `model_version` is older than expected, run the pipeline locally
   and `vercel deploy --prod --yes` from `web/`.

### "The workflow is failing"

```bash
gh run list --repo bertoce/wc26 --workflow=predict.yml --limit 5
gh run view <run_id> --repo bertoce/wc26 --log-failed
```

Common causes (with prior fixes):
- **`spawn pnpm ENOENT`** — workflow needs `npm install -g pnpm@10` before
  vercel build (fixed in commit history).
- **`No Next.js version detected`** — happens if Vercel tries to build
  from the repo root instead of `web/`. Vercel-GH integration is
  disconnected on purpose; deploy goes through the workflow's vercel CLI
  step.
- **Node 20 deprecation warning** — actions/checkout@v5 + setup-python@v6
  use Node 24, so this should be silent.

### "My local pipeline fails with `int | None` TypeError"

You're on Python 3.9; the script needs `from __future__ import annotations`
at the top. All current scripts have it. If you add a new one, include it.

### "I edited `injuries.json` but the next deploy reverted it"

The refresh script preserves manual edits **when no source returns data**
(today's state). If you wire up a source later that contradicts your
manual edit, the aggregator takes the more severe view between sources.
To force preservation, mark the entry with `"source": "manual"` and the
aggregator includes it alongside other sources.

## Updating dependencies

Python deps are exact-pinned in `model/requirements.txt`. To bump:

```bash
cd model
../.venv/bin/pip install -U pandas numpy scipy        # or whatever
../.venv/bin/pip freeze | grep -E "^(pandas|numpy|scipy|...)=" > requirements.txt
../.venv/bin/python -m pytest -q                      # confirm green
```

Web deps follow Next.js's `pnpm install` flow. Bump Next:
```bash
cd web
pnpm up next@latest react@latest react-dom@latest
pnpm build                                            # confirm builds
```

Action versions: actions/checkout@v5 + actions/setup-python@v6 currently.
Bump in `.github/workflows/predict.yml` when newer majors land.

## What's NOT supported

- **Multi-tournament support** — hardcoded for WC26 (league=2000 on
  football-data.org; 48 teams; 2026 season). Adapting for a Euros would
  need new fixtures source + simpler bracket structure.
- **Multiple model versions running in parallel** — single
  `predictions.json` schema, single dashboard.
- **Historical replay** — model only predicts WC26, doesn't backtest past
  WCs. A backtest harness would be the right way to learn the pattern-prior
  coefficients (see MODEL.md References).
