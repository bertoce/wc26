"""Tests for injury-driven squad-value adjustments."""

import json
import pytest
from pathlib import Path
from wc26.injuries import (
    InjuryImpact,
    adjusted_squad_value,
    injury_impacts,
    load_injuries,
    out_value_for_team,
)


class TestLoadInjuries:
    def test_missing_file_returns_empty(self, tmp_path: Path):
        nonexistent = tmp_path / "nope.json"
        assert load_injuries(nonexistent) == {}

    def test_loads_json(self, tmp_path: Path):
        p = tmp_path / "injuries.json"
        p.write_text(json.dumps({"ARG": {"out": [{"name": "X", "tm_value_eur_m": 100}]}}))
        loaded = load_injuries(p)
        assert "ARG" in loaded


class TestOutValueForTeam:
    def test_team_not_in_file_returns_zero(self):
        injuries = {"ARG": {"out": [{"name": "X", "tm_value_eur_m": 100}]}}
        assert out_value_for_team(injuries, "BRA") == 0.0

    def test_no_out_list_returns_zero(self):
        injuries = {"ARG": {}}
        assert out_value_for_team(injuries, "ARG") == 0.0

    def test_empty_out_list_returns_zero(self):
        injuries = {"ARG": {"out": []}}
        assert out_value_for_team(injuries, "ARG") == 0.0

    def test_sums_out_player_values(self):
        injuries = {
            "BRA": {
                "out": [
                    {"name": "Vinicius Jr", "tm_value_eur_m": 200},
                    {"name": "Rodrygo", "tm_value_eur_m": 120},
                ]
            }
        }
        assert out_value_for_team(injuries, "BRA") == 320.0

    def test_doubtful_not_counted(self):
        """Doubtful players are informational only — they don't reduce squad value."""
        injuries = {
            "ARG": {
                "out":      [{"name": "Player A", "tm_value_eur_m": 100}],
                "doubtful": [{"name": "Player B", "tm_value_eur_m": 50}],
            }
        }
        assert out_value_for_team(injuries, "ARG") == 100.0

    def test_player_missing_value_treated_as_zero(self):
        """Missing tm_value_eur_m is handled gracefully."""
        injuries = {
            "ARG": {"out": [{"name": "X"}, {"name": "Y", "tm_value_eur_m": 80}]}
        }
        assert out_value_for_team(injuries, "ARG") == 80.0


class TestAdjustedSquadValue:
    def test_no_injuries_returns_original(self):
        assert adjusted_squad_value(500.0, {}, "ARG") == 500.0

    def test_subtracts_out_value(self):
        injuries = {"BRA": {"out": [{"name": "X", "tm_value_eur_m": 200}]}}
        assert adjusted_squad_value(1050.0, injuries, "BRA") == 850.0

    def test_floors_at_zero(self):
        """A squad shouldn't go negative even if injured-out value exceeds total."""
        injuries = {"WK": {"out": [{"name": "Star", "tm_value_eur_m": 500}]}}
        assert adjusted_squad_value(50.0, injuries, "WK") == 0.0

    def test_unaffected_team_unchanged(self):
        injuries = {"BRA": {"out": [{"name": "X", "tm_value_eur_m": 200}]}}
        assert adjusted_squad_value(1300.0, injuries, "ENG") == 1300.0

    def test_more_injuries_means_more_reduction(self):
        """Monotonicity: adding another out-player must further reduce."""
        one_out = {"BRA": {"out": [{"name": "A", "tm_value_eur_m": 100}]}}
        two_out = {"BRA": {"out": [
            {"name": "A", "tm_value_eur_m": 100},
            {"name": "B", "tm_value_eur_m": 80},
        ]}}
        assert adjusted_squad_value(1000, one_out, "BRA") > adjusted_squad_value(1000, two_out, "BRA")


class TestInjuryImpacts:
    def test_skips_meta_keys(self):
        impacts = injury_impacts({
            "_meta": {"description": "test"},
            "ARG": {"out": [{"name": "X", "tm_value_eur_m": 100}]},
        })
        assert len(impacts) == 1
        assert impacts[0].team_tla == "ARG"

    def test_returns_counts_and_value(self):
        impacts = injury_impacts({
            "BRA": {
                "out":      [{"name": "A", "tm_value_eur_m": 200}],
                "doubtful": [{"name": "B", "tm_value_eur_m": 30}, {"name": "C", "tm_value_eur_m": 20}],
            }
        })
        assert impacts[0] == InjuryImpact(
            team_tla="BRA",
            out_count=1,
            out_value_eur_m=200.0,
            doubtful_count=2,
        )
