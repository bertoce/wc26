"""Pluggable injury data sources.

Each source module exposes:
    fetch_team_injuries(team_tla: str, ...) -> list[RawInjury]

The aggregator combines outputs from multiple sources into the final
injuries.json structure consumed by the pipeline.
"""

from .base import RawInjury

__all__ = ["RawInjury"]
