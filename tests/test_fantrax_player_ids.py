"""#519: Fantrax player identity from the public getPlayerIds call.

The fixture is shaped like the documented response, with invented values only.
No network: the session is swapped for one that returns a canned reply.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))

import pandas as pd
import pytest

import etl_helpers as etl

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fantrax" / "public_playerids.json"
SMALL = 1


class _FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code, self._body = status_code, body

    def json(self):
        return self._body


@pytest.fixture
def body():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class TestParsePlayerIds:
    def test_keeps_the_player_rows_as_the_four_identity_columns(self, body):
        df = etl.parse_player_ids(body, minimum=SMALL)
        assert list(df.columns) == ["scorer_id", "player_name", "position_raw", "nfl_team"]
        assert list(df["scorer_id"]) == ["aaa01", "aaa02", "aaa03", "aaa04", "aaa05"]
        row = df.set_index("scorer_id").loc["aaa01"]
        assert (row["player_name"], row["position_raw"], row["nfl_team"]) == ("Alpha Tester", "QB", "DAL")

    def test_team_defense_rows_are_dropped(self, body):
        df = etl.parse_player_ids(body, minimum=SMALL)
        assert not df["scorer_id"].str.contains("#").any()
        assert not df["position_raw"].isin(["DST", "TmD", "ST", "Tm", "TO"]).any()

    def test_the_team_level_rows_with_a_team_and_no_team_name_are_dropped_by_position(self, body):
        df = etl.parse_player_ids(body, minimum=SMALL)
        assert "bbb01" in body and "bbb02" in body
        assert not df["scorer_id"].isin(["bbb01", "bbb02"]).any()

    def test_a_row_with_the_no_team_form_keeps_it(self, body):
        df = etl.parse_player_ids(body, minimum=SMALL).set_index("scorer_id")
        assert df.loc["aaa02", "nfl_team"] == etl.NO_TEAM == "(N/A)"

    def test_a_player_with_no_team_key_gets_the_no_team_form(self, body):
        del body["aaa01"]["team"]
        df = etl.parse_player_ids(body, minimum=SMALL).set_index("scorer_id")
        assert df.loc["aaa01", "nfl_team"] == "(N/A)"

    def test_an_unexplained_position_code_is_kept(self, body):
        df = etl.parse_player_ids(body, minimum=SMALL).set_index("scorer_id")
        assert df.loc["aaa04", "position_raw"] == "Default"

    def test_the_optional_outside_ids_are_not_columns(self, body):
        assert {"rotowireId", "sportRadarId", "statsIncId"}.isdisjoint(etl.parse_player_ids(body, minimum=SMALL).columns)

    @pytest.mark.parametrize("field", ["fantraxId", "name", "position"])
    def test_a_record_missing_a_required_field_raises(self, body, field):
        del body["aaa03"][field]
        with pytest.raises(RuntimeError, match=field):
            etl.parse_player_ids(body, minimum=SMALL)

    def test_a_record_that_is_not_an_object_raises(self, body):
        body["aaa03"] = "text"
        with pytest.raises(RuntimeError, match="not an object"):
            etl.parse_player_ids(body, minimum=SMALL)

    def test_an_id_that_differs_from_its_key_raises(self, body):
        body["aaa03"]["fantraxId"] = "zzz99"
        with pytest.raises(RuntimeError, match="differs from its key"):
            etl.parse_player_ids(body, minimum=SMALL)

    def test_a_body_with_too_few_players_raises(self, body):
        with pytest.raises(RuntimeError, match="fewer than the 1000"):
            etl.parse_player_ids(body)


class TestFantraxPlayerIds:
    @pytest.fixture
    def reply(self, monkeypatch):
        calls = []

        def install(response):
            class Session:
                def get(self, url, params=None, timeout=None, headers=None):
                    calls.append((url, params))
                    if isinstance(response, Exception):
                        raise response
                    return response
            monkeypatch.setattr(etl, "_make_session", lambda: Session())
            return calls
        return install

    def test_asks_getplayerids_for_nfl_with_no_league(self, reply, body):
        calls = reply(_FakeResponse(body=body))
        df = etl.fantrax_player_ids(minimum=SMALL)
        url, params = calls[0]
        assert url.endswith("/fxea/general/getPlayerIds")
        assert params == {"sport": "NFL"}
        assert len(df) == 5

    def test_an_error_body_on_a_200_raises(self, reply):
        reply(_FakeResponse(body={"error": {"code": "WARNING"}}))
        with pytest.raises(RuntimeError, match="error body"):
            etl.fantrax_player_ids()

    def test_a_non_200_raises(self, reply):
        reply(_FakeResponse(status_code=503, body={}))
        with pytest.raises(RuntimeError, match="HTTP 503"):
            etl.fantrax_player_ids()

    def test_reads_a_saved_copy_with_no_request(self, reply):
        calls = reply(RuntimeError("no request expected"))
        df = etl.fantrax_player_ids(raw_path=FIXTURE, minimum=SMALL)
        assert calls == [] and len(df) == 5

    def test_a_saved_error_body_raises(self, tmp_path):
        path = tmp_path / "saved.json"
        path.write_text(json.dumps({"error": {"code": "WARNING"}}), encoding="utf-8")
        with pytest.raises(RuntimeError, match="not a player-id body"):
            etl.fantrax_player_ids(raw_path=path)


class TestApplyPlayerIds:
    IDS = pd.DataFrame({"scorer_id": ["a", "b"], "player_name": ["New A", "New B"],
                        "position_raw": ["LB", "WR"], "nfl_team": ["DAL", "(N/A)"]})

    def universe(self):
        return pd.DataFrame({"scorer_id": ["a", "b", "c"], "player_name": ["Old A", "Old B", "Old C"],
                             "position_raw": ["LB,DB", "TE", "QB"], "nfl_team": ["XXX", "YYY", "ZZZ"],
                             "is_rookie": [True, False, True]})

    def test_the_identity_columns_come_from_the_call_and_the_rest_stay(self):
        out, counts = etl.apply_player_ids(self.universe(), self.IDS)
        by = out.set_index("scorer_id")
        assert (by.loc["a", "player_name"], by.loc["a", "position_raw"], by.loc["a", "nfl_team"]) == ("New A", "LB", "DAL")
        assert by.loc["b", "nfl_team"] == "(N/A)"
        assert list(out.columns) == list(self.universe().columns)
        assert list(out["is_rookie"]) == [True, False, True]

    def test_an_id_the_call_lacks_keeps_its_own_row(self):
        out, counts = etl.apply_player_ids(self.universe(), self.IDS)
        row = out.set_index("scorer_id").loc["c"]
        assert (row["player_name"], row["position_raw"], row["nfl_team"]) == ("Old C", "QB", "ZZZ")

    def test_counts(self):
        _, counts = etl.apply_player_ids(self.universe(), self.IDS)
        assert counts == {"from_player_ids": 2, "not_in_player_ids": 1, "multi_position_made_single": 1}

    def test_the_input_frame_is_not_changed(self):
        universe = self.universe()
        etl.apply_player_ids(universe, self.IDS)
        assert universe.loc[0, "player_name"] == "Old A"
