"""API-Football injury data source.

API docs: https://www.api-football.com/documentation-v3#tag/Injuries

This module exposes two pieces:

  - parse_injuries_response(...)   — pure transformer (mocked in tests)
  - fetch_team_injuries(...)       — HTTP wrapper (requires API key)

The pure parser is what TDD covers. The HTTP wrapper is a thin shim and
exercised end-to-end during the actual workflow runs.
"""

from __future__ import annotations

import os
from typing import Iterable

import requests

from .base import RawInjury, InjurySeverity


API_BASE = "https://v3.football.api-sports.io"

# Map of API-Football's `type` strings (case-insensitive) → our severity bucket.
# Unknown types return None and are skipped.
_SEVERITY_MAP: dict[str, InjurySeverity] = {
    "missing fixture": "out",
    "not in squad":    "out",
    "doubtful":        "doubtful",
    "questionable":    "doubtful",
}


def classify_severity(type_str: str | None) -> InjurySeverity | None:
    """Map an API-Football injury `type` to our severity bucket. None for unknown."""
    if not type_str:
        return None
    return _SEVERITY_MAP.get(type_str.strip().lower())


def parse_injuries_response(payload: dict, team_tla: str) -> list[RawInjury]:
    """Transform an API-Football /injuries response into a deduplicated list
    of RawInjury for the given team.

    `payload` is the JSON-decoded response (top-level dict with "response" key).
    `team_tla` is our TLA for the team — used verbatim on the output rows.

    Deduplicates by player_name (one row per player, even if injured for
    multiple upcoming fixtures). Skips entries with unrecognised types or
    missing player names.
    """
    rows: list[RawInjury] = []
    seen: set[str] = set()

    for entry in payload.get("response", []):
        player = entry.get("player") or {}
        name = (player.get("name") or "").strip()
        if not name or name in seen:
            continue

        severity = classify_severity(entry.get("type"))
        if severity is None:
            continue

        rows.append(RawInjury(
            player_name=name,
            team_tla=team_tla,
            severity=severity,
            reason=(entry.get("reason") or "").strip(),
            source="api_football",
            tm_value_eur_m=None,  # API-Football doesn't supply market value
        ))
        seen.add(name)

    return rows


# ---------------------------------------------------------------------------
# HTTP wrapper — exercised in integration runs, not unit tests
# ---------------------------------------------------------------------------

def _headers(api_key: str | None = None) -> dict[str, str]:
    key = api_key or os.environ.get("API_FOOTBALL_KEY")
    if not key:
        raise RuntimeError(
            "API_FOOTBALL_KEY not set. Add it to .env.local locally or as a "
            "GitHub Actions secret for CI."
        )
    return {"x-apisports-key": key, "Accept": "application/json"}


def fetch_team_injuries(
    team_tla: str,
    api_football_team_id: int,
    season: int = 2026,
    api_key: str | None = None,
    timeout: int = 30,
) -> list[RawInjury]:
    """Fetch + parse current injuries for one team. ~1 API request."""
    r = requests.get(
        f"{API_BASE}/injuries",
        headers=_headers(api_key),
        params={"team": api_football_team_id, "season": season},
        timeout=timeout,
    )
    r.raise_for_status()
    return parse_injuries_response(r.json(), team_tla=team_tla)
