"""Tests for the injury-source aggregator."""

import pytest
from wc26.injury_sources.aggregator import merge_injuries
from wc26.injury_sources.base import RawInjury


def _inj(name: str, team: str, severity, source="api_football",
         reason="", tm_value=None) -> RawInjury:
    return RawInjury(
        player_name=name, team_tla=team, severity=severity,
        source=source, reason=reason, tm_value_eur_m=tm_value,
    )


class TestMergeSingleSource:
    def test_empty_input_yields_empty_dict(self):
        assert merge_injuries() == {}
        assert merge_injuries([]) == {}

    def test_single_player_single_source(self):
        result = merge_injuries([_inj("Mbappé", "FRA", "out", reason="ACL")])
        assert "FRA" in result
        assert len(result["FRA"]["out"]) == 1
        assert result["FRA"]["doubtful"] == []
        assert result["FRA"]["out"][0]["name"] == "Mbappé"
        assert result["FRA"]["out"][0]["note"] == "ACL"
        assert result["FRA"]["out"][0]["sources"] == ["api_football"]

    def test_multiple_teams(self):
        result = merge_injuries([
            _inj("Player A", "FRA", "out"),
            _inj("Player B", "BRA", "doubtful"),
        ])
        assert set(result.keys()) == {"FRA", "BRA"}
        assert len(result["FRA"]["out"]) == 1
        assert len(result["BRA"]["doubtful"]) == 1

    def test_output_sorted_by_name(self):
        result = merge_injuries([
            _inj("Zalazar", "URY", "out"),
            _inj("Araújo", "URY", "out"),
            _inj("Bentancur", "URY", "out"),
        ])
        names = [e["name"] for e in result["URY"]["out"]]
        assert names == ["Araújo", "Bentancur", "Zalazar"]


class TestMergeMultipleSources:
    def test_same_player_two_sources_dedupes(self):
        """Two sources reporting the same player → one row, both sources listed."""
        result = merge_injuries(
            [_inj("Mbappé", "FRA", "out", source="api_football", reason="ACL")],
            [_inj("Mbappé", "FRA", "out", source="sofascore", reason="knee surgery")],
        )
        assert len(result["FRA"]["out"]) == 1
        entry = result["FRA"]["out"][0]
        assert entry["sources"] == ["api_football", "sofascore"]
        assert "ACL" in entry["note"]
        assert "knee surgery" in entry["note"]

    def test_severity_conflict_takes_more_severe(self):
        """API says doubtful, SofaScore says out → marked out (cautious choice)."""
        result = merge_injuries(
            [_inj("X", "ARG", "doubtful", source="api_football")],
            [_inj("X", "ARG", "out",      source="sofascore")],
        )
        assert len(result["ARG"]["out"]) == 1
        assert result["ARG"]["doubtful"] == []
        assert set(result["ARG"]["out"][0]["sources"]) == {"api_football", "sofascore"}

    def test_case_insensitive_name_matching(self):
        result = merge_injuries(
            [_inj("Vinícius Júnior", "BRA", "out", source="api_football")],
            [_inj("VINÍCIUS JÚNIOR", "BRA", "out", source="sofascore")],
        )
        assert len(result["BRA"]["out"]) == 1

    def test_tm_value_taken_from_first_non_none(self):
        result = merge_injuries(
            [_inj("Star", "ENG", "out", source="api_football", tm_value=None)],
            [_inj("Star", "ENG", "out", source="manual",       tm_value=180.0)],
        )
        assert result["ENG"]["out"][0]["tm_value_eur_m"] == 180.0

    def test_missing_tm_value_defaults_to_zero(self):
        """If no source provides tm_value, default to 0 (no market-value penalty)."""
        result = merge_injuries(
            [_inj("X", "ARG", "out", source="api_football", tm_value=None)],
        )
        assert result["ARG"]["out"][0]["tm_value_eur_m"] == 0

    def test_reason_deduped_across_sources(self):
        """If both sources give the same reason text, don't duplicate it in note."""
        result = merge_injuries(
            [_inj("X", "ENG", "out", source="api_football", reason="hamstring")],
            [_inj("X", "ENG", "out", source="sofascore",    reason="hamstring")],
        )
        assert result["ENG"]["out"][0]["note"] == "hamstring"
