"""Load injuries from a static JSON file and adjust per-team squad values.

The injury system reuses the existing market-value prior: when a player is
'out', their Transfermarkt value is subtracted from the team's total squad
value. The market_value_log_odds() function then naturally produces a
smaller bump (or a bigger penalty) for that team. 'Doubtful' players are
informational only — not subtracted.

JSON schema:
    {
      "_meta": {...},
      "ARG": {
        "out":      [{"name": "Player A", "tm_value_eur_m": 200, "note": "ACL"}],
        "doubtful": [{"name": "Player B", "tm_value_eur_m": 30,  "note": "knock"}]
      },
      ...
    }

Teams not listed (or with empty lists) get no adjustment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class InjuryImpact:
    """Per-team impact of out-injuries on squad value."""
    team_tla: str
    out_count: int
    out_value_eur_m: float
    doubtful_count: int


def load_injuries(path: Path) -> dict:
    """Load and return the raw injuries.json dict. Returns {} if file missing."""
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def out_value_for_team(injuries: dict, team_tla: str) -> float:
    """Sum of tm_value_eur_m across all 'out' players for the given team.

    Returns 0 if the team isn't listed, has no 'out' list, or the list is empty.
    'doubtful' players are NOT counted — they're informational only.
    """
    entry = injuries.get(team_tla)
    if not entry:
        return 0.0
    out_players = entry.get("out") or []
    total = sum(p.get("tm_value_eur_m", 0.0) for p in out_players)
    return float(total)


def adjusted_squad_value(
    original_eur_m: float,
    injuries: dict,
    team_tla: str,
) -> float:
    """Return the team's squad value after subtracting out-injury impact.
    Floor at 0 so we never go negative on a small-budget squad with big stars out."""
    drop = out_value_for_team(injuries, team_tla)
    return max(0.0, original_eur_m - drop)


def injury_impacts(injuries: dict) -> list[InjuryImpact]:
    """Summarize per-team out / doubtful counts and total out value, for
    logging or display."""
    impacts: list[InjuryImpact] = []
    for tla, entry in injuries.items():
        if tla.startswith("_"):  # skip _meta
            continue
        out_players = entry.get("out") or []
        doubtful_players = entry.get("doubtful") or []
        impacts.append(InjuryImpact(
            team_tla=tla,
            out_count=len(out_players),
            out_value_eur_m=sum(p.get("tm_value_eur_m", 0.0) for p in out_players),
            doubtful_count=len(doubtful_players),
        ))
    return impacts
