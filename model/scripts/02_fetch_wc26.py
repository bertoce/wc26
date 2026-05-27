"""Fetch WC26 competition info, teams, and fixtures from football-data.org.

Run from model/:
    .venv/bin/python scripts/02_fetch_wc26.py
"""

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env.local")

from wc26.ingest import (  # noqa: E402
    fetch_wc26_competition,
    fetch_wc26_teams,
    fetch_wc26_matches,
    fetch_wc26_standings,
)


def main() -> None:
    print("Fetching WC26 competition metadata...")
    comp = fetch_wc26_competition()
    season = comp.get("currentSeason", {})
    print(f"  name: {comp.get('name')}")
    print(f"  season: {season.get('startDate')} → {season.get('endDate')}")
    print()

    print("Fetching qualified teams...")
    teams_resp = fetch_wc26_teams()
    teams = teams_resp.get("teams", [])
    print(f"  {len(teams)} teams")
    for t in teams[:5]:
        print(f"    {t.get('tla', '???')} — {t.get('name')}")
    if len(teams) > 5:
        print(f"    ... and {len(teams) - 5} more")
    print()

    print("Fetching fixtures...")
    matches_resp = fetch_wc26_matches()
    matches = matches_resp.get("matches", [])
    print(f"  {len(matches)} matches scheduled")
    # Stage breakdown
    stages = {}
    for m in matches:
        s = m.get("stage", "UNKNOWN")
        stages[s] = stages.get(s, 0) + 1
    for stage, n in stages.items():
        print(f"    {stage}: {n}")
    print()

    print("Fetching standings (will be empty pre-tournament)...")
    standings_resp = fetch_wc26_standings()
    standings = standings_resp.get("standings", [])
    print(f"  {len(standings)} standings groups")


if __name__ == "__main__":
    main()
