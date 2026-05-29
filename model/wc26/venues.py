"""Host-venue home-advantage policy for WC26.

The 2026 World Cup is co-hosted by USA, Canada, and Mexico (16 cities total —
11 in USA, 3 in Mexico, 2 in Canada). Each host plays its three group-stage
matches in its own country, so it gets the standard home-advantage bump.

Knockout fixtures are venue-mixed (a Mexico R16 might end up in USA, depending
on the bracket draw) and we don't have per-match venue data from
football-data.org's free tier. For v1 they stay neutral — better to under-claim
home advantage than to falsely apply it.

If/when per-match venue data becomes available (paid fd.org tier, or a manual
schedule lookup), this module is where the lookup logic belongs.
"""

from __future__ import annotations

HOST_TLAS: frozenset[str] = frozenset({"MEX", "USA", "CAN"})


def is_host_home_fixture(home_tla: str, stage: str) -> bool:
    """Return True if this fixture should be treated as a home match for the
    home team — i.e., apply the Dixon-Coles home-advantage γ.

    Currently true only when:
      - home_team is one of the three co-hosts (MEX/USA/CAN), AND
      - the match is a group-stage fixture (where hosts always play in-country).

    Knockouts return False (venue-mixed) until per-match venue data is wired in.
    """
    if not home_tla or not stage:
        return False
    return home_tla in HOST_TLAS and stage == "group"
