"""Refresh injuries.json from configured external sources.

Currently uses one source: API-Football (Phase 1).
Phase 2 will add SofaScore as a cross-validator (same aggregator interface).

Run:
    cd model
    ../.venv/bin/python scripts/05_refresh_injuries.py

In CI: the GH Actions workflow runs this before the prediction pipeline.
Gracefully no-ops if API_FOOTBALL_KEY is missing — the pipeline then runs
against whatever injuries.json was last committed.

API budget: 1 request per team = ~48/day, well under the 100/day free tier.
"""

from __future__ import annotations  # local Python is 3.9 — needed for new-style type hints

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env.local")

from wc26.injury_sources.aggregator import merge_injuries  # noqa: E402
from wc26.injury_sources.api_football import fetch_team_injuries  # noqa: E402

STATIC_DIR = ROOT / "model" / "data" / "static"
TEAM_IDS_PATH = STATIC_DIR / "api_football_team_ids.json"
INJURIES_PATH = STATIC_DIR / "injuries.json"


def main() -> None:
    if not os.environ.get("API_FOOTBALL_KEY"):
        print("API_FOOTBALL_KEY not set — skipping injury refresh, using last "
              "committed injuries.json as-is.")
        sys.exit(0)

    team_ids = json.loads(TEAM_IDS_PATH.read_text())
    team_ids = {k: v for k, v in team_ids.items() if not k.startswith("_")}

    # Fetch from API-Football
    af_injuries = []
    missing_ids = []
    errors = []
    for tla, api_team_id in team_ids.items():
        if api_team_id is None:
            missing_ids.append(tla)
            continue
        try:
            rows = fetch_team_injuries(team_tla=tla, api_football_team_id=api_team_id)
            af_injuries.extend(rows)
        except Exception as e:
            errors.append((tla, str(e)))
        time.sleep(0.3)  # polite pacing

    print(f"API-Football fetch: {len(af_injuries)} injury reports across "
          f"{len(team_ids) - len(missing_ids)} teams "
          f"({len(missing_ids)} missing team IDs, {len(errors)} errors)")
    if missing_ids:
        print(f"  missing IDs: {', '.join(sorted(missing_ids))}")
        print(f"  → run 04_discover_api_football_team_ids.py to fill them in")
    for tla, err in errors:
        print(f"  ERROR {tla}: {err}")

    # SAFETY: if no source returned any injury data, do NOT touch
    # injuries.json. This preserves manual edits — otherwise a cron run with
    # an empty fetch would wipe a user-curated file.
    #
    # API-Football's free plan returns 0 injuries for WC26 (the tournament is
    # on a paid season). Until we get a working source, we treat empty fetches
    # as "no info" rather than "no injuries".
    if not af_injuries:
        print("  No injury data from any source — leaving injuries.json untouched.")
        print("  (Manual edits to injuries.json are preserved.)")
        return

    merged = merge_injuries(af_injuries)

    # Preserve _meta block from the existing injuries.json (schema docs, etc.)
    existing = json.loads(INJURIES_PATH.read_text()) if INJURIES_PATH.exists() else {}
    meta = existing.get("_meta", {})
    meta["last_refreshed_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    meta["sources_used"] = ["api_football"]

    out = {"_meta": meta}
    out.update(merged)

    INJURIES_PATH.write_text(json.dumps(out, indent=2))
    n_out = sum(len(v.get("out", [])) for k, v in merged.items())
    n_doubt = sum(len(v.get("doubtful", [])) for k, v in merged.items())
    print(f"  ✓ wrote {INJURIES_PATH.relative_to(ROOT)} — {n_out} out, {n_doubt} doubtful")


if __name__ == "__main__":
    main()
