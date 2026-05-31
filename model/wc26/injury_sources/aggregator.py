"""Combine RawInjury lists from multiple sources into the injuries.json structure.

The aggregator's job:
  1. Dedupe within each team (same player from multiple sources → one row)
  2. Resolve severity conflicts (out > doubtful when sources disagree)
  3. Track which source(s) reported each player (for transparency)
  4. Emit the JSON schema the pipeline already consumes

Currently used by Phase 1 (single source, trivial pass-through). Phase 2
adds SofaScore as a second source and the cross-validation logic earns
its keep.
"""

from __future__ import annotations

from collections import defaultdict

from .base import RawInjury, InjurySeverity


# Higher number = more severe
_SEVERITY_RANK: dict[InjurySeverity, int] = {"doubtful": 1, "out": 2}


def _normalize_name(name: str) -> str:
    """Compare player names case-insensitively + strip whitespace.
    Doesn't handle Unicode normalization variants (e.g. Mbappé vs Mbappe) yet —
    keep an eye on this when adding sources with different encodings."""
    return name.strip().lower()


def merge_injuries(
    *sources: list[RawInjury],
) -> dict[str, dict[str, list[dict]]]:
    """Merge multiple sources' RawInjury lists into the injuries.json structure.

    Returns a dict keyed by team_tla, each value of shape:
        {
          "out":      [{"name": ..., "tm_value_eur_m": ..., "note": ..., "sources": [...]}],
          "doubtful": [...]
        }

    Sources are listed in `note` for transparency. tm_value_eur_m is the
    first non-None value across sources (defaults to 0 → no market penalty).
    """
    # team_tla → normalized_name → list of RawInjury claims
    claims: dict[str, dict[str, list[RawInjury]]] = defaultdict(lambda: defaultdict(list))
    # Preserve the first-seen display name (so we don't lower-case in output)
    display_name: dict[tuple[str, str], str] = {}

    for source_list in sources:
        for inj in source_list:
            key = _normalize_name(inj.player_name)
            claims[inj.team_tla][key].append(inj)
            display_name.setdefault((inj.team_tla, key), inj.player_name.strip())

    out: dict[str, dict[str, list[dict]]] = {}
    for team_tla, by_player in claims.items():
        team_out: list[dict] = []
        team_doubtful: list[dict] = []
        for player_key, all_claims in by_player.items():
            # Resolve severity: take the most severe claim
            severity: InjurySeverity = max(
                (c.severity for c in all_claims),
                key=lambda s: _SEVERITY_RANK[s],
            )
            # tm_value: first non-None across sources
            tm_value = next(
                (c.tm_value_eur_m for c in all_claims if c.tm_value_eur_m is not None),
                None,
            )
            # Reasons: dedupe non-empty across sources
            reasons = sorted({c.reason for c in all_claims if c.reason})
            note = "; ".join(reasons) if reasons else ""

            entry = {
                "name": display_name[(team_tla, player_key)],
                "tm_value_eur_m": tm_value if tm_value is not None else 0,
                "note": note,
                "sources": sorted({c.source for c in all_claims}),
            }
            if severity == "out":
                team_out.append(entry)
            else:
                team_doubtful.append(entry)

        # Sort each list by player name for stable JSON output
        team_out.sort(key=lambda e: e["name"].lower())
        team_doubtful.sort(key=lambda e: e["name"].lower())
        out[team_tla] = {"out": team_out, "doubtful": team_doubtful}

    return out
