"""04m: fact_matchup's Team Scores from public getMatchupScores, in shadow
beside the fxpa build (#520).

The fixture is hand-written from the documented shape with invented ids and
scores (no capture is cut into the repo). No test calls Fantrax: the fetch
and the table reads and writes are faked.
"""
import copy
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))

import pandas as pd
import pytest

import etl_checks as ec
import run_pipeline as rp

mm = importlib.import_module("04m_fantrax_matchup_scores")

FIXTURE = REPO / "tests" / "fixtures" / "fantrax" / "public_matchup_scores.json"
SEASON = "2026-2027"
DAY = pd.Timestamp("2026-11-28")
TEAMS = pd.DataFrame({"fantrax_team_id": ["t01", "t02", "t03", "t04"],
                      "team_key": ["T1", "T2", "T3", "T4"]})


def reply():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def frame(body=None, period=9):
    return mm.matchups_to_frame(body or reply(), TEAMS, SEASON, period, DAY)


class TestMatchupsToFrame:
    def test_two_mirrored_rows_per_matchup(self):
        by = frame().set_index("team_key")[["opponent_team_key", "is_home",
                                            "fpts_for", "fpts_against"]]
        assert by.loc["T1"].tolist() == ["T2", False, 15.5, 10.0]       # away first
        assert by.loc["T2"].tolist() == ["T1", True, 10.0, 15.5]
        assert by.loc["T3"].tolist() == ["T4", False, 1234.5, -2.4]
        assert by.loc["T4"].tolist() == ["T3", True, -2.4, 1234.5]
        assert ec.mirror_errors(frame()) == []

    def test_period_season_and_day(self):
        df = frame()
        assert len(df) == 4
        assert (df["period"] == 9).all() and (df["season_id"] == SEASON).all()
        assert (df["capture_date"] == DAY).all()

    def test_schema_matches_the_registry(self):
        want = {c["name"]: c["dtype"] for c in ec.load_registry()["fact_matchup"]["columns"]}
        assert {c: str(t) for c, t in frame().dtypes.items()} == want

    def test_a_reply_for_another_period_raises(self):
        with pytest.raises(ValueError, match="period=8 echoed period 9"):
            frame(period=8)

    def test_a_missing_team_raises(self):
        more = pd.concat([TEAMS, pd.DataFrame({"fantrax_team_id": ["t05"], "team_key": ["T5"]})])
        with pytest.raises(ValueError, match="4 teams, expected 5"):
            mm.matchups_to_frame(reply(), more, SEASON, 9, DAY)

    def test_a_team_the_dim_lacks_raises(self):
        body = reply()
        body["matchups"][1]["home"]["teamId"] = "zz"
        with pytest.raises(ValueError, match="not in dim_fantasy_teams"):
            frame(body)

    def test_a_team_listed_twice_raises(self):
        body = reply()
        body["matchups"].append(copy.deepcopy(body["matchups"][0]))
        with pytest.raises(ValueError, match="do not hold each of 4 teams once"):
            frame(body)

    @pytest.mark.parametrize("score", ["15.5", None, True])
    def test_a_score_that_is_not_a_number_raises(self, score):
        body = reply()
        body["matchups"][0]["away"]["score"] = score
        with pytest.raises(ValueError, match="is not a number"):
            frame(body)


class TestShadowDiff:
    def test_the_same_rows_differ_nowhere(self):
        d = mm.shadow_diff(frame(), frame())
        assert d == {"compared": 4, **dict.fromkeys(mm.DIFF_COUNTS, 0)}
        assert not mm.differs(d)

    def test_a_score_beyond_a_cent_differs_and_within_does_not(self):
        fxpa = frame()
        fxpa.loc[fxpa["team_key"] == "T1", "fpts_for"] += 0.005
        assert not mm.differs(mm.shadow_diff(frame(), fxpa))
        fxpa.loc[fxpa["team_key"] == "T2", "fpts_against"] += 0.5
        d = mm.shadow_diff(frame(), fxpa)
        assert (d["fpts_for"], d["fpts_against"]) == (0, 1) and mm.differs(d)

    def test_home_side_opponent_and_missing_teams_are_counted(self):
        fxpa = frame()
        fxpa.loc[fxpa["team_key"] == "T3", "is_home"] = True
        fxpa.loc[fxpa["team_key"] == "T4", "opponent_team_key"] = "T1"
        fxpa = fxpa[fxpa["team_key"] != "T1"]
        d = mm.shadow_diff(frame(), fxpa)
        assert d == {"compared": 3, "only_fxea": 1, "only_fxpa": 0, "opponent": 1,
                     "is_home": 1, "fpts_for": 0, "fpts_against": 0}

    def test_a_period_with_no_rows_on_hand_is_not_compared(self):
        on_hand = frame().assign(period=8)
        assert mm.compare(frame(), on_hand) == {9: None}
        assert mm.report({9: None}) == ["[shadow] period 9: no fxpa rows on hand, nothing compared"]

    def test_the_report_names_each_count(self):
        line = mm.report(mm.compare(frame(), frame()))[0]
        assert line.startswith("[shadow] period 9: 4 teams compared; only_fxea 0")
        assert line.endswith("-- matches")


class TestPeriodsToRead:
    def test_ended_open_regular_season_periods_only(self):
        utc = lambda s: pd.Timestamp(s, tz="UTC")
        periods = pd.DataFrame({
            "period": [8, 9, 10, 11, 13],
            "is_playoff": [False, False, False, False, True],
            "end_at": [utc("2026-11-05"), utc("2026-11-12"), utc("2026-11-19"),
                       utc("2026-12-03"), utc("2026-11-20")],
            "update_set_state": ["closed", "closing", "open", "open", "open"],
        })
        assert mm.periods_to_read(periods, utc("2026-11-28")) == [9, 10]


class TestRun:
    """run() with the fetch, the table on hand and the write faked."""

    @pytest.fixture
    def world(self, monkeypatch, tmp_path):
        calls, writes = [], []

        def fetch(method, league_id, expect=(), **params):
            calls.append((method, params))
            return reply()

        monkeypatch.setattr(mm, "FX_CFG", SimpleNamespace(raw_dir=str(tmp_path), league_id="L"))
        monkeypatch.setattr(mm, "fantrax_public_get", fetch)
        monkeypatch.setattr(mm, "write_table",
                            lambda name, df, mode, keys: writes.append((name, df)) or len(df))
        monkeypatch.setattr(mm.time, "sleep", lambda s: None)
        return SimpleNamespace(calls=calls, writes=writes, raw=tmp_path,
                               on_hand=lambda df: monkeypatch.setattr(mm, "on_hand_rows", lambda: df))

    def go(self, live, asked=(9,), due=(9,)):
        return mm.run(list(asked), list(due), TEAMS, SEASON, 2026,
                      pd.Timestamp("2026-11-28 12:00", tz="UTC"), live)

    def test_shadow_compares_and_writes_nothing(self, world, capsys):
        world.on_hand(frame())
        assert self.go(live=False) == 0
        assert world.calls == [("getMatchupScores", {"period": 9})]
        assert world.writes == []
        assert "period 9: 4 teams compared" in capsys.readouterr().out
        saved = json.loads((world.raw / "fantrax_fxea_matchupscores_2026_p09.json").read_text())
        assert saved["season_id"] == SEASON and saved["captured_at"] and saved["period"] == 9

    def test_shadow_with_a_difference_still_exits_0(self, world, capsys):
        world.on_hand(frame().assign(fpts_for=0.0))
        assert self.go(live=False) == 0
        assert world.writes == [] and "DIFFERS" in capsys.readouterr().out

    def test_live_writes_when_nothing_differs(self, world):
        world.on_hand(frame())
        assert self.go(live=True) == 0
        [(name, df)] = world.writes
        assert name == "fact_matchup" and len(df) == 4 and (df["period"] == 9).all()

    def test_live_writes_a_period_none_holds_yet(self, world):
        world.on_hand(pd.DataFrame(columns=mm.MATCHUP_COLUMNS))
        assert self.go(live=True) == 0
        assert len(world.writes) == 1

    def test_live_writes_nothing_and_fails_when_a_period_differs(self, world, capsys):
        world.on_hand(frame().assign(is_home=False))
        assert self.go(live=True) == 1
        assert world.writes == [] and "nothing written" in capsys.readouterr().out

    def test_live_never_writes_a_period_that_is_not_due(self, world, capsys):
        world.on_hand(frame())
        assert self.go(live=True, due=()) == 0
        assert world.writes == []

    def test_no_period_due_calls_nothing(self, world):
        assert self.go(live=False, asked=()) == 0
        assert world.calls == [] and world.writes == []


class TestMain:
    def test_shadow_swallows_an_error_and_exits_0(self, monkeypatch, capsys):
        def boom(*a, **k):
            raise RuntimeError("Fantrax public getLeagueInfo: HTTP 503")
        monkeypatch.setattr(mm, "read_table", lambda name: TEAMS)
        monkeypatch.setattr(mm, "table_exists", lambda name: False)
        monkeypatch.setattr(mm, "fantrax_public_get", boom)
        assert mm.main([]) == 0
        assert "[shadow] getMatchupScores failed" in capsys.readouterr().out

    def test_live_raises_the_error(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("HTTP 503")
        monkeypatch.setattr(mm, "read_table", lambda name: TEAMS)
        monkeypatch.setattr(mm, "table_exists", lambda name: False)
        monkeypatch.setattr(mm, "fantrax_public_get", boom)
        with pytest.raises(RuntimeError, match="HTTP 503"):
            mm.main(["--live"])

    def test_raw_compares_a_saved_reply_with_no_call_and_no_write(self, monkeypatch, tmp_path, capsys):
        path = tmp_path / "saved.json"
        path.write_text(json.dumps(reply()), encoding="utf-8")
        tables = {"dim_fantasy_teams": TEAMS,
                  "dim_scoring_period": pd.DataFrame({"season_id": ["2025-2026", SEASON]}),
                  "fact_matchup": frame()}
        monkeypatch.setattr(mm, "read_table", tables.__getitem__)
        monkeypatch.setattr(mm, "table_exists", lambda name: name in tables)
        monkeypatch.setattr(mm, "fantrax_public_get", lambda *a, **k: pytest.fail("no call"))
        monkeypatch.setattr(mm, "write_table", lambda *a, **k: pytest.fail("no write"))
        assert mm.main(["--raw", str(path)]) == 0
        assert "period 9: 4 teams compared" in capsys.readouterr().out

    def test_raw_and_live_do_not_go_together(self):
        with pytest.raises(SystemExit):
            mm.main(["--raw", "x.json", "--live"])


class TestPipelineStep:
    STEPS = rp.build_steps(None)

    def test_it_runs_in_season_after_the_fxpa_build_in_the_core_chain(self):
        names = [s["name"] for s in self.STEPS]
        step = self.STEPS[names.index("04m_matchup_scores")]
        assert step["phases"] == {"INSEASON"}
        assert (step["chain"], step["needs"]) == ("fantrax_core", ["04p_league_info"])
        assert step["cmd"][-1].endswith("04m_fantrax_matchup_scores.py")
        assert names.index("04s_scoring") < names.index("04m_matchup_scores")

    def test_it_runs_in_shadow(self):
        step = next(s for s in self.STEPS if s["name"] == "04m_matchup_scores")
        assert "--live" not in step["cmd"]
