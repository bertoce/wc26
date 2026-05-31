"""Tests for the API-Football injury source.

We don't make real API calls in tests — the response JSON shape is documented
at https://www.api-football.com/documentation-v3#tag/Injuries. We test the
pure parser against representative mocked payloads.
"""

import pytest
from wc26.injury_sources.api_football import (
    parse_injuries_response,
    classify_severity,
)
from wc26.injury_sources.base import RawInjury


class TestClassifySeverity:
    """API-Football's `type` field uses a fixed vocabulary."""

    @pytest.mark.parametrize("type_str", [
        "Missing Fixture",
        "missing fixture",
        "MISSING FIXTURE",
        "Not in squad",
    ])
    def test_missing_fixture_is_out(self, type_str: str):
        assert classify_severity(type_str) == "out"

    @pytest.mark.parametrize("type_str", [
        "Questionable",
        "Doubtful",
        "questionable",
    ])
    def test_questionable_is_doubtful(self, type_str: str):
        assert classify_severity(type_str) == "doubtful"

    @pytest.mark.parametrize("type_str", ["", "Unknown", "Fit", None])
    def test_unknown_returns_none(self, type_str):
        """Unrecognised types should return None so the aggregator can skip them."""
        assert classify_severity(type_str) is None


class TestParseInjuriesResponse:
    def test_empty_response_returns_empty_list(self):
        assert parse_injuries_response({"response": []}, team_tla="ARG") == []

    def test_missing_response_key_returns_empty(self):
        assert parse_injuries_response({}, team_tla="ARG") == []

    def test_single_out_player(self):
        payload = {
            "response": [{
                "player": {"id": 521, "name": "Kylian Mbappé"},
                "team": {"id": 2, "name": "France"},
                "fixture": {"id": 12345, "date": "2026-06-15T20:00:00+00:00"},
                "league": {"id": 1, "season": 2026, "name": "World Cup"},
                "type": "Missing Fixture",
                "reason": "Hamstring strain",
            }]
        }
        result = parse_injuries_response(payload, team_tla="FRA")
        assert len(result) == 1
        assert result[0] == RawInjury(
            player_name="Kylian Mbappé",
            team_tla="FRA",
            severity="out",
            reason="Hamstring strain",
            source="api_football",
            tm_value_eur_m=None,
        )

    def test_doubtful_player(self):
        payload = {
            "response": [{
                "player": {"id": 99, "name": "Player X"},
                "team": {"id": 2, "name": "France"},
                "fixture": {"id": 1, "date": "2026-06-15"},
                "league": {"id": 1, "season": 2026},
                "type": "Questionable",
                "reason": "knock",
            }]
        }
        result = parse_injuries_response(payload, team_tla="FRA")
        assert len(result) == 1
        assert result[0].severity == "doubtful"

    def test_skips_unknown_severity(self):
        payload = {
            "response": [
                {  # included — "out"
                    "player": {"name": "Out Player"},
                    "team": {"name": "X"},
                    "type": "Missing Fixture",
                    "reason": "ACL",
                },
                {  # skipped — unrecognised type
                    "player": {"name": "Fit Player"},
                    "team": {"name": "X"},
                    "type": "Fit",
                    "reason": "back from injury",
                },
                {  # included — "doubtful"
                    "player": {"name": "Maybe Player"},
                    "team": {"name": "X"},
                    "type": "Doubtful",
                    "reason": "fitness test",
                },
            ]
        }
        result = parse_injuries_response(payload, team_tla="ARG")
        assert len(result) == 2
        names = [r.player_name for r in result]
        assert "Out Player" in names
        assert "Maybe Player" in names
        assert "Fit Player" not in names

    def test_deduplicates_same_player_multiple_fixtures(self):
        """API-Football returns one row per affected fixture. If a player is
        out for 3 upcoming matches, we should only count them once per team."""
        payload = {
            "response": [
                {
                    "player": {"name": "Star Player"},
                    "team": {"name": "X"},
                    "type": "Missing Fixture",
                    "reason": "ACL",
                    "fixture": {"id": 1},
                },
                {
                    "player": {"name": "Star Player"},
                    "team": {"name": "X"},
                    "type": "Missing Fixture",
                    "reason": "ACL",
                    "fixture": {"id": 2},
                },
                {
                    "player": {"name": "Star Player"},
                    "team": {"name": "X"},
                    "type": "Missing Fixture",
                    "reason": "ACL",
                    "fixture": {"id": 3},
                },
            ]
        }
        result = parse_injuries_response(payload, team_tla="BRA")
        assert len(result) == 1
        assert result[0].player_name == "Star Player"

    def test_missing_player_name_is_skipped(self):
        """Malformed entries shouldn't crash the parser."""
        payload = {
            "response": [
                {"player": {}, "type": "Missing Fixture", "reason": ""},
                {"player": {"name": "Valid"}, "type": "Missing Fixture", "reason": ""},
            ]
        }
        result = parse_injuries_response(payload, team_tla="BRA")
        assert len(result) == 1
        assert result[0].player_name == "Valid"

    def test_source_tag_always_api_football(self):
        payload = {
            "response": [{
                "player": {"name": "X"},
                "team": {"name": "Y"},
                "type": "Missing Fixture",
                "reason": "",
            }]
        }
        result = parse_injuries_response(payload, team_tla="ARG")
        assert result[0].source == "api_football"
