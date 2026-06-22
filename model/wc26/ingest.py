"""Data ingestion: historical results + WC26 fixtures.

Two sources:
- martj42/international_results on GitHub — all international matches since 1872
- football-data.org — WC26 fixture list and qualified teams (free tier)
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

from .elo import Match

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

GITHUB_RESULTS_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
)
GITHUB_SHOOTOUTS_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/master/shootouts.csv"
)

FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"
WC_COMPETITION_CODE = "WC"

# football-data.org uses a handful of team codes that diverge from this
# project's canonical TLAs (team_features.json and every other static data
# file key off the ISO 3166-1 code). Normalize at the ingestion boundary so
# every downstream consumer — fixture matching, the DC fit injection,
# snapshot keys — sees one consistent code per team. Without this, fixtures
# for the affected team get silently dropped (treated as "missing team
# data") instead of appearing as scheduled/finished matches.
FD_TLA_ALIASES = {
    "URU": "URY",  # Uruguay
}


def normalize_fd_tla(tla: str | None) -> str | None:
    return FD_TLA_ALIASES.get(tla, tla)


def normalize_fd_teams(data: dict) -> dict:
    """Normalize the `tla` field of every team in a /teams response, in place."""
    for t in data.get("teams", []):
        t["tla"] = normalize_fd_tla(t.get("tla"))
    return data


def normalize_fd_matches(data: dict) -> dict:
    """Normalize homeTeam/awayTeam `tla` fields in a /matches response, in place."""
    for m in data.get("matches", []):
        for side in ("homeTeam", "awayTeam"):
            team = m.get(side)
            if team and team.get("tla"):
                team["tla"] = normalize_fd_tla(team["tla"])
    return data


# ---------------------------------------------------------------------------
# Historical match results (free, no auth)
# ---------------------------------------------------------------------------

def download_results(force: bool = False) -> Path:
    """Download results.csv from GitHub. Cached on disk."""
    path = RAW_DIR / "results.csv"
    if path.exists() and not force:
        return path
    print(f"  → fetching {GITHUB_RESULTS_URL}")
    r = requests.get(GITHUB_RESULTS_URL, timeout=60)
    r.raise_for_status()
    path.write_bytes(r.content)
    return path


def download_shootouts(force: bool = False) -> Path:
    path = RAW_DIR / "shootouts.csv"
    if path.exists() and not force:
        return path
    print(f"  → fetching {GITHUB_SHOOTOUTS_URL}")
    r = requests.get(GITHUB_SHOOTOUTS_URL, timeout=60)
    r.raise_for_status()
    path.write_bytes(r.content)
    return path


def load_results(force: bool = False) -> pd.DataFrame:
    """Load and clean the historical results CSV.

    Columns: date, home_team, away_team, home_score, away_score, tournament,
             city, country, neutral
    """
    path = download_results(force=force)
    df = pd.read_csv(path, parse_dates=["date"])
    # Drop rows missing scores
    df = df.dropna(subset=["home_score", "away_score"]).copy()
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)
    df["neutral"] = df["neutral"].astype(bool)
    return df


def results_to_matches(df: pd.DataFrame) -> list[Match]:
    """Convert a results DataFrame into a list of Match objects for the Elo runner."""
    return [
        Match(
            date=row.date.strftime("%Y-%m-%d"),
            home=row.home_team,
            away=row.away_team,
            home_goals=int(row.home_score),
            away_goals=int(row.away_score),
            tournament=row.tournament,
            neutral=bool(row.neutral),
        )
        for row in df.itertuples(index=False)
    ]


# ---------------------------------------------------------------------------
# football-data.org WC26 fixtures
# ---------------------------------------------------------------------------

def _fd_headers() -> dict:
    key = os.environ.get("FOOTBALL_DATA_API_KEY")
    if not key:
        raise RuntimeError(
            "FOOTBALL_DATA_API_KEY not set. Add it to .env.local and load with "
            "`from dotenv import load_dotenv; load_dotenv()`."
        )
    return {"X-Auth-Token": key}


def fetch_wc26_competition(force: bool = False) -> dict:
    """GET /v4/competitions/WC — basic info + current season."""
    path = RAW_DIR / "wc26_competition.json"
    if path.exists() and not force:
        return json.loads(path.read_text())
    r = requests.get(f"{FOOTBALL_DATA_BASE}/competitions/{WC_COMPETITION_CODE}",
                     headers=_fd_headers(), timeout=30)
    r.raise_for_status()
    data = r.json()
    path.write_text(json.dumps(data, indent=2))
    return data


def fetch_wc26_teams(force: bool = False) -> dict:
    """GET /v4/competitions/WC/teams — qualified teams for the current season."""
    path = RAW_DIR / "wc26_teams.json"
    if path.exists() and not force:
        return normalize_fd_teams(json.loads(path.read_text()))
    r = requests.get(f"{FOOTBALL_DATA_BASE}/competitions/{WC_COMPETITION_CODE}/teams",
                     headers=_fd_headers(), timeout=30)
    r.raise_for_status()
    data = r.json()
    path.write_text(json.dumps(data, indent=2))
    return normalize_fd_teams(data)


def fetch_wc26_matches(force: bool = False) -> dict:
    """GET /v4/competitions/WC/matches — full fixture list with groups/stages."""
    path = RAW_DIR / "wc26_matches.json"
    if path.exists() and not force:
        return normalize_fd_matches(json.loads(path.read_text()))
    r = requests.get(f"{FOOTBALL_DATA_BASE}/competitions/{WC_COMPETITION_CODE}/matches",
                     headers=_fd_headers(), timeout=30)
    r.raise_for_status()
    data = r.json()
    path.write_text(json.dumps(data, indent=2))
    return normalize_fd_matches(data)


def fetch_wc26_standings(force: bool = False) -> dict:
    """GET /v4/competitions/WC/standings — current group standings (empty pre-tournament)."""
    path = RAW_DIR / "wc26_standings.json"
    if path.exists() and not force:
        return json.loads(path.read_text())
    r = requests.get(f"{FOOTBALL_DATA_BASE}/competitions/{WC_COMPETITION_CODE}/standings",
                     headers=_fd_headers(), timeout=30)
    r.raise_for_status()
    data = r.json()
    path.write_text(json.dumps(data, indent=2))
    return data
