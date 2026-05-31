"""Shared types across injury data sources.

A RawInjury is one source's *claim* about one player. The aggregator (later)
combines multiple sources' claims into a confirmed list."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

InjurySeverity = Literal["out", "doubtful"]
InjurySource = Literal["api_football", "sofascore", "manual"]


@dataclass(frozen=True)
class RawInjury:
    """A single source's report of a single player's injury status.

    `tm_value_eur_m` may be None when the source doesn't provide it; the
    aggregator can fill from another source or leave 0 (no market-value penalty
    for an unknown-valued player)."""
    player_name: str
    team_tla: str
    severity: InjurySeverity
    reason: str = ""                 # short free-text ("ACL", "fitness", etc.)
    source: InjurySource = "manual"
    tm_value_eur_m: float | None = None
