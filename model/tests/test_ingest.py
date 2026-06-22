"""Tests for football-data.org TLA normalization.

football-data.org reports Uruguay as tla="URU", but every static data file
(team_features.json, injuries.json, team_chemistry.json) keys Uruguay as
"URY". Left unnormalized, the mismatch makes the pipeline treat Uruguay's
fixtures as "missing team data" and drop them entirely.
"""

from wc26.ingest import normalize_fd_matches, normalize_fd_teams, normalize_fd_tla


class TestNormalizeFdTla:
    def test_known_alias_is_rewritten(self):
        assert normalize_fd_tla("URU") == "URY"

    def test_unmapped_code_passes_through(self):
        assert normalize_fd_tla("ESP") == "ESP"

    def test_none_passes_through(self):
        assert normalize_fd_tla(None) is None


class TestNormalizeFdTeams:
    def test_rewrites_aliased_team(self):
        data = {"teams": [{"tla": "URU", "name": "Uruguay"}]}
        out = normalize_fd_teams(data)
        assert out["teams"][0]["tla"] == "URY"

    def test_leaves_other_teams_untouched(self):
        data = {"teams": [{"tla": "ESP", "name": "Spain"}]}
        out = normalize_fd_teams(data)
        assert out["teams"][0]["tla"] == "ESP"

    def test_handles_missing_teams_key(self):
        assert normalize_fd_teams({}) == {}


class TestNormalizeFdMatches:
    def _match(self, home_tla, away_tla):
        return {
            "homeTeam": {"tla": home_tla, "name": home_tla},
            "awayTeam": {"tla": away_tla, "name": away_tla},
        }

    def test_rewrites_home_team(self):
        data = {"matches": [self._match("URU", "ESP")]}
        out = normalize_fd_matches(data)
        assert out["matches"][0]["homeTeam"]["tla"] == "URY"
        assert out["matches"][0]["awayTeam"]["tla"] == "ESP"

    def test_rewrites_away_team(self):
        data = {"matches": [self._match("KSA", "URU")]}
        out = normalize_fd_matches(data)
        assert out["matches"][0]["homeTeam"]["tla"] == "KSA"
        assert out["matches"][0]["awayTeam"]["tla"] == "URY"

    def test_handles_missing_team_tla(self):
        data = {"matches": [{"homeTeam": {"tla": None}, "awayTeam": {}}]}
        out = normalize_fd_matches(data)
        assert out["matches"][0]["homeTeam"]["tla"] is None

    def test_handles_missing_matches_key(self):
        assert normalize_fd_matches({}) == {}
