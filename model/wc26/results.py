"""Extract finished match results from football-data.org match data.

During the tournament, fd.org flips matches from status TIMED to FINISHED
and fills score.fullTime with the actual goals. These become "known results"
that the simulator locks in instead of re-simulating.
"""

from __future__ import annotations


def result_key(group: str | None, home_tla: str, away_tla: str) -> str:
    """Stable unique key for a group fixture: 'A:MEX-RSA'.

    Home/away order matters — it's part of fixture identity in the fd.org
    schedule (each pairing only occurs once in a WC group).
    """
    return f"{group or '?'}:{home_tla}-{away_tla}"


def extract_finished_group_results(fd_matches: list[dict]) -> list[dict]:
    """Return known-result dicts for every FINISHED group-stage match.

    Skips: knockout matches (handled separately once pairings are real),
    unfinished matches (any status other than FINISHED), and records with
    missing team TLAs or scores.

    Output dicts: {home, away, group, home_goals, away_goals}
    with group normalised to its letter ('GROUP_A' → 'A').
    """
    out: list[dict] = []
    for m in fd_matches:
        if m.get("status") != "FINISHED":
            continue
        if m.get("stage") != "GROUP_STAGE":
            continue
        home_tla = (m.get("homeTeam") or {}).get("tla")
        away_tla = (m.get("awayTeam") or {}).get("tla")
        if not home_tla or not away_tla:
            continue
        full_time = ((m.get("score") or {}).get("fullTime")) or {}
        hg, ag = full_time.get("home"), full_time.get("away")
        if hg is None or ag is None:
            continue
        group = (m.get("group") or "").replace("GROUP_", "") or None
        out.append({
            "home": home_tla,
            "away": away_tla,
            "group": group,
            "home_goals": int(hg),
            "away_goals": int(ag),
        })
    return out
