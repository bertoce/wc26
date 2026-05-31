"""One-time discovery: look up each WC26 team's API-Football team ID and
write to data/static/api_football_team_ids.json.

Run AFTER API_FOOTBALL_KEY is set:
    cd model
    ../.venv/bin/python scripts/04_discover_api_football_team_ids.py

Uses ~48 API requests (one per team). The result is cached in the static
JSON so the daily refresh doesn't have to re-discover.

Re-run only if:
  - team_features.json adds/removes a team
  - API-Football changes a team's ID (very rare)
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env.local")

STATIC_DIR = ROOT / "model" / "data" / "static"
TEAM_FEATURES = STATIC_DIR / "team_features.json"
TEAM_IDS = STATIC_DIR / "api_football_team_ids.json"

API_BASE = "https://v3.football.api-sports.io"


def lookup_team_id(name: str, headers: dict) -> int | None:
    """Search API-Football for a national team by country name. Returns
    None if no match is found (call site logs a warning)."""
    r = requests.get(
        f"{API_BASE}/teams",
        headers=headers,
        params={"name": name, "code": ""},  # 'name' search across team names
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    for entry in data.get("response", []):
        team = entry.get("team", {})
        if team.get("national"):  # only national teams
            return int(team["id"])
    # Fall back to looking up by country (e.g. "England" rather than "England national football team")
    r = requests.get(
        f"{API_BASE}/teams",
        headers=headers,
        params={"country": name},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    for entry in data.get("response", []):
        team = entry.get("team", {})
        if team.get("national"):
            return int(team["id"])
    return None


def main() -> None:
    key = os.environ.get("API_FOOTBALL_KEY")
    if not key:
        print("ERROR: API_FOOTBALL_KEY not set. Add to .env.local or export.")
        sys.exit(1)
    headers = {"x-apisports-key": key, "Accept": "application/json"}

    features = json.loads(TEAM_FEATURES.read_text())
    features = {k: v for k, v in features.items() if not k.startswith("_")}

    ids = json.loads(TEAM_IDS.read_text())
    found = 0
    missing = []

    for tla, feat in features.items():
        existing = ids.get(tla)
        if existing is not None:
            print(f"  {tla}  already mapped → {existing} (skipping)")
            found += 1
            continue
        name = feat["name_historical"]
        try:
            team_id = lookup_team_id(name, headers)
        except Exception as e:
            print(f"  {tla}  ERROR fetching {name!r}: {e}")
            time.sleep(2)  # backoff on error
            continue
        if team_id is None:
            print(f"  {tla}  no match found for {name!r}")
            missing.append((tla, name))
        else:
            print(f"  {tla}  {name:<30}  → {team_id}")
            ids[tla] = team_id
            found += 1
        time.sleep(0.5)  # be polite — free tier is 100/day, plenty of headroom

    # Preserve _meta + write back
    out = {"_meta": ids.get("_meta", {})}
    for k, v in ids.items():
        if k != "_meta":
            out[k] = v
    out["_meta"]["as_of"] = time.strftime("%Y-%m-%d")
    TEAM_IDS.write_text(json.dumps(out, indent=2))
    print(f"\n  ✓ Mapped {found}/{len(features)} teams.  "
          f"Missing: {len(missing)}")
    for tla, name in missing:
        print(f"      {tla}  {name}  — fill in manually if API-Football has a non-standard ID")


if __name__ == "__main__":
    main()
