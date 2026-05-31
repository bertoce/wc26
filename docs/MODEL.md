# The model

How predictions get made, end-to-end. Four layers, each one's job, the math
behind it, and the calibration choices.

```
┌───────────────────────────────────────────────────────────┐
│  Layer 1 — Per-match model                                │
│  Dixon-Coles Poisson with 1-year half-life time decay     │
│  Output: P(home win), P(draw), P(away win), λ_home, λ_away │
└───────────────────────────────────┬───────────────────────┘
                                    │
┌───────────────────────────────────▼───────────────────────┐
│  Layer 2 — Tournament simulator                           │
│  20,000 Monte Carlo runs through group stage + bracket    │
│  Output: P(champion), P(reach each round), matchup dist   │
└───────────────────────────────────┬───────────────────────┘
                                    │
┌───────────────────────────────────▼───────────────────────┐
│  Layer 3 — Pattern priors + chemistry                     │
│  Multiplicative log-odds adjustment to the final outcome  │
│  Output: adjusted P(champion)                             │
└───────────────────────────────────┬───────────────────────┘
                                    │
┌───────────────────────────────────▼───────────────────────┐
│  Layer 4 — Dashboard surfacing                            │
│  predictions.json → Next.js static prerender              │
└───────────────────────────────────────────────────────────┘
```

---

## Layer 1 — Per-match model (Dixon-Coles)

### What it does

For any matchup, predicts the joint distribution over scorelines. Each team
has an attack strength and a defence strength; the model produces expected
goals for both sides, draws from independent Poissons, and applies the
Dixon-Coles low-score correction.

```
λ_home = exp(α_home + β_away + γ · I[non-neutral])
λ_away = exp(α_away + β_home)
P(home=h, away=a) = Poisson(h; λ_home) · Poisson(a; λ_away) · τ(h, a, ρ)
```

Where:
- **`α_team`** — attack strength (higher = scores more)
- **`β_team`** — defensive leakiness (higher = concedes more; Dixon-Coles convention)
- **`γ`** — global home advantage; applied only when fixture is non-neutral
- **`ρ`** — low-score correlation parameter

### The τ correction

```
τ(0,0) = 1 - λμρ           ← inflated when ρ < 0
τ(0,1) = 1 + λρ            ← deflated when ρ < 0
τ(1,0) = 1 + μρ            ← deflated when ρ < 0
τ(1,1) = 1 - ρ             ← inflated when ρ < 0
τ(h,a) = 1 otherwise
```

Empirically ρ fits to small negative values for real football (ours: −0.05
to −0.07 depending on fit). Why this matches reality:

- **0-0 and 1-1 happen more often** than independent Poissons predict.
  Tactical correlation (cagey matches stay cagey), late-game equalizers
  (1-0 leads turning into 1-1 finals), and game-state effects all push the
  same direction.
- **1-0 and 0-1 happen slightly less often** — some of those would-be
  one-goal wins regress to draws.

### Fit procedure

- **Data**: ~2,400 competitive international matches since 2018 that involve
  at least one WC26 team. Friendlies excluded — too noisy (countries field
  B-teams). Tournaments included: WC qualifiers, Euros, Copa, Nations
  Leagues, Gold Cup, AFCON, AFC Asian Cup.
- **Method**: maximum likelihood via `scipy.optimize.minimize` (L-BFGS-B).
- **Free parameters**: ~410 — α and β for each of ~205 teams + γ + ρ.
  Identifiability constraint: sum(α) = 0.
- **Time decay**: exponential with **1-year half-life** (`time_decay_per_year = ln 2 ≈ 0.693`).
  Weights: 0yr → 1.00, 1yr → 0.50, 2yr → 0.25, 4yr → 0.06, 8yr → 0.004.
  Reflects the *current* generation of players, not 2018 squads.

### Output

Given a Team H and Team A and a neutral-venue flag, `predict_match`
returns `(p_home_win, p_draw, p_away_win)` summing to 1.0. The 72 group
fixtures' predictions are computed deterministically by
`predict_group_fixtures()` and saved into `predictions.json` for the
dashboard's group-stage section.

### Tests (`test_dixon_coles.py`, 14)

- `τ` corrections inflate low draws, deflate one-goal results
- Parameter recovery from synthetic data (top-3 ranking overlap ≥ 2)
- Recovers known home-advantage γ from synthetic data
- Predicted probabilities sum to 1, all in [0,1]
- Neutral-venue removes home advantage
- Time decay: zero decay equals no decay (regression); decay shifts
  estimates toward recent matches when team strength changes over time;
  decay-fit is strictly closer to recent truth than no-decay-fit

### References

- Dixon, M.J. & Coles, S.G. (1997). *Modelling Association Football Scores
  and Inefficiencies in the Football Betting Market*. Applied Statistics 46: 265-280.

---

## Layer 2 — Tournament simulator

### What it does

Runs the per-match model through 20,000 simulated tournaments. Tracks per
sim: champion, who survived each round, every match's specific pairing.

### Group stage

- 12 groups of 4, round-robin (72 matches total)
- Each fixture: draw scoreline from independent Poissons around the DC λs
- Rank each group by **FIFA tiebreakers**: points → goal difference → goals
  for → alphabetic tiebreak
- **Host home advantage**: if home team is MEX/USA/CAN and stage is "group",
  the fixture is non-neutral (γ applies). 6 of 72 group fixtures qualify.
  Knockouts always neutral (venues become mixed across the three host
  countries once the bracket plays out; we don't have per-match venue data).

### Bracket seeding

- Top 2 from each group → 24 teams
- 8 best 3rd-place teams (ranked across all 12 groups by same tiebreakers) → 8 teams
- 32 total advancers, seeded into three tiers:
  - **Tier 1**: group winners, sorted by points/GD/GF
  - **Tier 2**: runners-up
  - **Tier 3**: best thirds
- Standard 32-team tournament seeding: seed 1 vs 32, 16 vs 17, 8 vs 25, etc.
- Same-group rematches in R32 are swapped to a different in-half pairing
  (no team plays a group rival before QF)

> **Caveat:** This is realistic tournament seeding, not FIFA's *exact*
> published 48-team bracket. The official slot mapping uses fixed
> rules like "1A vs 3rd-of-CDEF" that depend on which 8 of 12 possible
> third-place teams qualify. I don't have verified specs for that mapping.
> Standard seeding is meaningfully closer to reality than naive adjacent
> pairing was, but not bit-perfect.

### Knockout matches

Each match:
1. Simulate 90 minutes with full DC λs
2. If drawn after regulation: extra time at 1/3 of regulation λs (30 min / 90 min)
3. If still drawn after extra time: **50/50 coin flip** for penalty shootout

The 50/50 shootout assumption is a deliberate simplification — actual
shootout outcomes are notoriously hard to predict and roughly even across
even-matched teams in the data.

### Outputs from the simulator

For every team, across all 20k sims:

- `win_probability[tla]` — P(champion)
- `round_survival[tla][k]` — P(team was alive when k teams remained), k in {32, 16, 8, 4, 2, 1}
- `matchup_distribution[round_size][match_idx][(home, away)]` — P(this exact
  matchup occurred at this bracket slot); aggregated to build the
  most-likely-bracket forecast

### Tests (`test_simulator.py`, 28)

- FIFA tiebreakers (points > GD > GF)
- Group standings update correctly across simulated matches
- Knockout always returns a winner (no draws survive shootout)
- Equal teams in shootout → ~50/50 outcome
- Dominant team wins ≥35% in small fixture, weak team <10%
- Determinism: same seed → identical results
- Per-fixture predictions sum to 1; expected goals positive
- Round survival monotonically non-increasing
- Final-round survival equals win probability
- Matchup distribution sums to 1 per slot per sim
- Dominant team appears in deep rounds disproportionately often
- Standard bracket seeding pairs adjacent seed-order entries (1-32, 16-17, etc.)
- Top seeds in opposite halves (only meet in final)
- Same-group R32 rematches < 5% of pairings (was 75% with naive adjacent pairing)

---

## Layer 3 — Pattern priors + chemistry

### What they do

After the simulator produces raw win probabilities, four signals from the
historical record nudge them. Each signal contributes a log-odds bump;
they're summed, exponentiated, multiplied into the raw probabilities, then
renormalised.

```
log_adjusted[i] = log_raw[i] + conf[i] + host[i] + pedigree[i] + market[i] + chemistry[i]
adjusted[i] = exp(log_adjusted[i]) / Σ_j exp(log_adjusted[j])    (renormalise)
```

### The five signals

| Signal | Magnitude | Rationale |
|---|---|---|
| **Confederation** | UEFA +0.25, CONMEBOL +0.20, AFC/CAF/CONCACAF −1.0, OFC −1.4 | 22/22 WCs won by UEFA or CONMEBOL teams |
| **Host continent** | +0.15 if team's continent matches host (2026 = N. America) | UEFA wins ~70% of European-hosted WCs; CONMEBOL ~70% in S. America. Small for 2026 — no NA team has ever won a NA-hosted WC. |
| **Title pedigree** | tanh-scaled, saturates around +0.55. Brazil maxes out (5 wins, 11 semis); first-timers get 0 | Only 8 nations have ever won. Mean reversion is weak. |
| **Squad market value** | (squad_value_eur_m − 400) / 1000 | Transfermarkt total. Proxy for player quality. Centered on €400M. |
| **Team chemistry** | high +0.10, medium 0, low −0.10 | Hand-curated; defaults to medium. No quantitative source exists for this. |

### Tunable magnitudes (calibration)

The coefficients above are hand-calibrated to produce predictions in line
with plausible bookmaker spreads — they were *not* fit to historical WC
outcomes. A meaningful future upgrade: Groll et al. 2019-style learning of
these weights from past WCs via a regularised regression on the prior-adjusted
log-odds gap vs. observed champion.

### Injuries (data-driven adjustment to market value)

Separate from the priors themselves: `injuries.json` lists per-team
"out" players with their Transfermarkt values. Before applying the
market-value prior, `adjusted_squad_value()` subtracts the sum of out-value
from the team's `squad_value_eur_m`. The market-value prior then naturally
penalises the team for the missing star.

`doubtful` is informational only — not subtracted.

**Current state**: `injuries.json` ships with empty per-team entries.
Until you populate them, the feature is dormant. See
[`OPERATIONS.md`](OPERATIONS.md#editing-injuries).

### Tests (`test_priors.py` 20 + `test_injuries.py` 15)

- Confederation: UEFA + CONMEBOL positive; AFC/CAF/CONCACAF/OFC negative
- Host: matching continent positive; non-matching 0
- Pedigree: monotonic in wins/semis, saturates
- Market value: monotonic; median ~0
- Chemistry: high > 0 > low; missing = 0; magnitude bounded
- Apply: normalised; UEFA + pedigree gains relative share over AFC + nothing
- Chemistry shifts otherwise-identical teams; default doesn't shift
- Injuries: out-value subtracted, doubtful not subtracted; floored at 0;
  monotonic (more out = more reduction); _meta key ignored

### References

- Groll, A., Ley, C., Schauberger, G., Van Eetvelde, H. (2019). *A
  hybrid random forest to predict soccer matches in international
  tournaments*. Journal of Quantitative Analysis in Sports.
- Hvattum, L.M. & Arntzen, H. (2010). *Using ELO ratings for match result
  prediction in association football*. International Journal of Forecasting.

---

## Layer 4 — Dashboard surfacing

The pipeline writes `predictions.json` with everything the frontend needs;
a Next.js Server Component imports it at build time and statically
prerenders all pages.

| Dashboard section | Comes from |
|---|---|
| Winner card + Top-12 bar chart | `predictions[*].win_probability_adjusted` (Layer 3 output) |
| Compounding-probability explainer | Layer 2 `round_survival` chain × Layer 3 prior bump |
| Most-likely knockout bracket | Layer 2 `matchup_distribution` → pick top matchup per slot, apply Layer 1 W/D/L |
| Group-stage match cards (72) | Layer 1 deterministic `predict_group_fixtures` output |
| Round-by-round table | Raw round_survival for R32–F columns; **adjusted** for Win column (with footnote) |
| Win-prob decomposition table | Raw vs adjusted side-by-side, delta column |

Static prerender means no runtime DB or fetch — every visitor gets the
same pre-built HTML, served from Vercel's edge CDN. Updates happen via
fresh deploys (one per day from the cron, or manually triggered).

---

## End-to-end pipeline

`scripts/03_run_simulation.py`, ~90 seconds:

1. Load 49k historical matches from `martj42/international_results`
2. Compute Elo ratings (used for sanity output only; not in prediction chain)
3. Filter to 2,393 competitive matches since 2018 involving at least one WC26 team
4. Fit Dixon-Coles with 1-year half-life time decay
5. Build 48 Team objects (DC params, clipped to sane range to avoid weak-opposition artifacts)
6. Pull WC26 fixtures from football-data.org
7. Build 72 Fixture objects, marking host-team group matches as non-neutral
8. Run 20,000 Monte Carlo tournaments
9. Compute per-fixture W/D/L (deterministic, from DC params)
10. Apply pattern priors + injuries adjustment + chemistry
11. Build most-likely knockout bracket from matchup_distribution
12. Write `predictions.json` to `model/data/processed/` + mirror to `web/lib/data/`

---

## Honest limitations

1. **Tournament seeding is realistic but not FIFA's exact slot mapping** — see Layer 2 caveat above.
2. **Injuries dormant** — `injuries.json` ships empty. Manual edits work today; automated source TBD (API-Football free tier doesn't cover WC26).
3. **Chemistry dormant** — `team_chemistry.json` all "medium". Manual edits work; LLM news-sentiment automation deferred.
4. **Pattern priors hand-calibrated** — not fit to past WC outcomes. Groll et al. style learning would be a meaningful upgrade.
5. **Squad market values are a hand-curated May 2026 snapshot** — not from a live Transfermarkt scrape.
6. **No suspensions, fatigue, weather, travel** — all could matter at the margins.
7. **All knockout matches treated as fully neutral** — no home advantage for hosts beyond group stage even when they're playing in-country.
