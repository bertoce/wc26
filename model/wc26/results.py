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
            "utc_date": (m.get("utcDate") or "")[:10],
        })
    return out


def known_results_to_dc_matches(
    known_results: list[dict],
    tla_to_historical_name: dict[str, str],
    existing_matches: list[dict],
) -> list[dict]:
    """Convert finished tournament results into Dixon-Coles fit rows.

    The historical dataset (martj42 CSV) lags real matches by days. Injecting
    fd.org's finished results directly means team strengths update within
    minutes of full-time — and with the 1-year-half-life time decay they're
    the highest-weighted matches in the entire fit.

    Dedup: if a row with the same (date, home, away) already exists in the
    historical data, the result is skipped — the CSV caught up and injecting
    again would double-count the match.

    Results whose TLAs aren't in the mapping are skipped (defensive — should
    not happen for WC26 teams).
    """
    from .venues import is_host_home_fixture

    existing_keys = {
        (m.get("date"), m.get("home"), m.get("away")) for m in existing_matches
    }
    rows: list[dict] = []
    for kr in known_results:
        home_name = tla_to_historical_name.get(kr["home"])
        away_name = tla_to_historical_name.get(kr["away"])
        if not home_name or not away_name:
            continue
        date = (kr.get("utc_date") or "")[:10]
        if (date, home_name, away_name) in existing_keys:
            continue
        rows.append({
            "date": date,
            "home": home_name,
            "away": away_name,
            "home_goals": int(kr["home_goals"]),
            "away_goals": int(kr["away_goals"]),
            "neutral": not is_host_home_fixture(kr["home"], "group"),
        })
    return rows
