"""One-time discovery: look up each WC26 team's API-Football team ID and
write to data/static/api_football_team_ids.json.

Strategy (rewritten v2):
  1. Make ONE call to /fixtures?league=1&season=2026 — returns all WC26
     matches, each containing the home + away team's API-Football ID + name.
  2. Build a name → id map by collecting unique teams from all fixtures.
  3. Match our 48 TLAs against that map via name + alias lookup.
  4. Report any TLAs we couldn't match.

API budget: 1 request. Stays well under both the 100/day daily quota
and the 10/min per-minute throttle.

If the fixtures endpoint returns 0 teams (WC26 hasn't been populated by
API-Football yet), we fall back to per-team name search with a 7-second
delay between requests to respect the per-minute throttle.

Run AFTER API_FOOTBALL_KEY is set:
    cd model
    ../.venv/bin/python scripts/04_discover_api_football_team_ids.py

Re-run only if:
  - team_features.json adds/removes a team
  - API-Football updates a team's ID (very rare)
"""

from __future__ import annotations  # local Python is 3.9 — needed for `int | None`

import json
import os
import sys
import time
import unicodedata
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env.local")

STATIC_DIR = ROOT / "model" / "data" / "static"
TEAM_FEATURES = STATIC_DIR / "team_features.json"
TEAM_IDS = STATIC_DIR / "api_football_team_ids.json"

API_BASE = "https://v3.football.api-sports.io"
WC_LEAGUE_ID = 1     # API-Football's league ID for the FIFA World Cup
WC_SEASON = 2026

# Map our `name_historical` value → alternative names API-Football might use.
# Add entries as new "no match found" cases appear.
NAME_ALIASES: dict[str, list[str]] = {
    "Czech Republic":   ["Czechia"],
    "South Korea":      ["Korea Republic", "Republic of Korea"],
    "United States":    ["USA"],
    "DR Congo":         ["Congo DR", "Democratic Republic of the Congo", "Congo"],
    "Ivory Coast":      ["Côte d'Ivoire", "Cote d'Ivoire"],
    "Cape Verde":       ["Cape Verde Islands", "Cabo Verde"],
    "Bosnia and Herzegovina": ["Bosnia-Herzegovina", "Bosnia Herzegovina"],
    "Iran":             ["IR Iran", "Islamic Republic of Iran"],
    "Curaçao":          ["Curacao"],
}


def _normalize(s: str) -> str:
    """Lowercase, strip diacritics, collapse spaces for fuzzy matching."""
    nfkd = unicodedata.normalize("NFKD", s)
    no_diac = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(no_diac.lower().split())


def collect_team_map_from_fixtures(headers: dict) -> dict[str, int]:
    """Single API call: fetch all WC26 fixtures, build {normalized_name: id}."""
    r = requests.get(
        f"{API_BASE}/fixtures",
        headers=headers,
        params={"league": WC_LEAGUE_ID, "season": WC_SEASON},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    teams: dict[str, int] = {}
    for entry in data.get("response", []):
        for side in ("home", "away"):
            team = (entry.get("teams") or {}).get(side) or {}
            name = team.get("name")
            tid = team.get("id")
            if name and tid is not None:
                teams[_normalize(name)] = int(tid)
    return teams


def match_tla_to_id(historical_name: str, team_map: dict[str, int]) -> int | None:
    """Try the canonical name, then any registered aliases, against the
    normalized-name map returned from the fixtures endpoint."""
    candidates = [historical_name] + NAME_ALIASES.get(historical_name, [])
    for cand in candidates:
        nid = team_map.get(_normalize(cand))
        if nid is not None:
            return nid
    return None


def main() -> None:
    key = os.environ.get("API_FOOTBALL_KEY")
    if not key:
        print("ERROR: API_FOOTBALL_KEY not set. Add to .env.local or export.")
        sys.exit(1)
    headers = {"x-apisports-key": key, "Accept": "application/json"}

    print("Fetching WC26 fixtures from API-Football (1 request)...")
    try:
        team_map = collect_team_map_from_fixtures(headers)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 429:
            print("  ⚠ rate-limited. The per-minute throttle is 10/min on the free tier.")
            print("  Wait 60 seconds, then re-run this script.")
            sys.exit(2)
        raise
    print(f"  found {len(team_map)} unique teams across WC26 fixtures")

    if not team_map:
        print("  ⚠ Empty fixture response — API-Football may not yet have WC26 populated.")
        print("    Check your account is active and the season parameter is correct.")
        sys.exit(2)

    features = json.loads(TEAM_FEATURES.read_text())
    features = {k: v for k, v in features.items() if not k.startswith("_")}

    ids = json.loads(TEAM_IDS.read_text())
    found_new = 0
    already_had = 0
    still_missing: list[tuple[str, str]] = []

    for tla, feat in features.items():
        if ids.get(tla) is not None:
            already_had += 1
            continue
        name = feat["name_historical"]
        team_id = match_tla_to_id(name, team_map)
        if team_id is None:
            still_missing.append((tla, name))
            print(f"  {tla}  no match for {name!r}  (will need manual lookup)")
        else:
            print(f"  {tla}  {name:<30}  → {team_id}")
            ids[tla] = team_id
            found_new += 1

    # Preserve _meta + write back
    out = {"_meta": ids.get("_meta", {})}
    for k, v in ids.items():
        if k != "_meta":
            out[k] = v
    out["_meta"]["as_of"] = time.strftime("%Y-%m-%d")
    TEAM_IDS.write_text(json.dumps(out, indent=2))

    total_mapped = already_had + found_new
    print(f"\n  ✓ Newly mapped: {found_new}.  Already had: {already_had}.  "
          f"Total: {total_mapped}/{len(features)}")
    if still_missing:
        print(f"\n  Still missing ({len(still_missing)} teams):")
        for tla, name in still_missing:
            print(f"    {tla}  {name}")
        print("\n  These can be filled in by:")
        print("  - Checking https://dashboard.api-football.com/ → Teams search")
        print("  - Or adding name aliases to NAME_ALIASES in this script + re-running")
        print("  - Or editing api_football_team_ids.json by hand")


if __name__ == "__main__":
    main()
