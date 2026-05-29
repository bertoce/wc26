"""Tests for the host-venue home-advantage policy.

WC26 is co-hosted by USA, Canada, and Mexico. Each host plays its group
matches in its own country, so they get the standard home-advantage bump.
Knockout matches are venue-mixed (a Mexico R16 might be in USA) and stay
neutral in v1 — we don't have per-match venue data to do otherwise.
"""

import pytest
from wc26.venues import HOST_TLAS, is_host_home_fixture


class TestHostConstants:
    def test_host_tlas_are_the_three_co_hosts(self):
        assert HOST_TLAS == {"MEX", "USA", "CAN"}


class TestIsHostHomeFixture:
    @pytest.mark.parametrize("tla", ["MEX", "USA", "CAN"])
    def test_host_team_group_match_is_home(self, tla: str):
        assert is_host_home_fixture(home_tla=tla, stage="group") is True

    @pytest.mark.parametrize(
        "tla", ["BRA", "ARG", "ESP", "FRA", "ENG", "POR", "GER", "JPN"]
    )
    def test_non_host_team_group_match_is_neutral(self, tla: str):
        assert is_host_home_fixture(home_tla=tla, stage="group") is False

    @pytest.mark.parametrize("tla", ["MEX", "USA", "CAN"])
    def test_host_team_knockout_match_is_neutral(self, tla: str):
        """Knockout venues are mixed across the three countries in v1 —
        a Mexico-R16 match might be played in USA. Keep them neutral until
        we can pin per-match venue data."""
        for stage in ("r32", "r16", "qf", "sf", "final"):
            assert is_host_home_fixture(home_tla=tla, stage=stage) is False, (
                f"Host {tla} should not get home advantage in {stage}"
            )

    def test_empty_or_missing_inputs_default_to_neutral(self):
        assert is_host_home_fixture(home_tla="", stage="group") is False
        assert is_host_home_fixture(home_tla="MEX", stage="") is False
