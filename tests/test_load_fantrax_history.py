"""scripts/load_fantrax_history.py (#761), on a made-up download.

Every name, team and date below is invented; the headers are the real ones.
The loader runs against a throwaway data dir: dim_contract and dim_season are
copied from data/, the rest is built here, and every path the loader and 02d
write is pointed at the temp dir.
"""
import csv
import importlib.util
import os
import shutil
import socket
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import pandas as pd
import pytest

_spec = importlib.util.spec_from_file_location("load_fantrax_history",
                                               REPO / "scripts" / "load_fantrax_history.py")
lf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lf)
rt = lf.rt
_spec = importlib.util.spec_from_file_location("load_team_names", REPO / "scripts" / "load_team_names.py")
ln = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ln)
etl = lf.etl

SEASON = "2026-2027"
TEAMS = {"A01": ("f1", "Team Alpha"), "A02": ("f2", "Team Bravo"), "A03": ("f3", "Team Charlie")}
PLAYERS = [("s1", "Alex Drafted", "KC", "WR"), ("s2", "Blake Drafted", "DAL", "RB"),
           ("s3", "Sam Same", "BUF", "QB"), ("s4", "Sam Same", "NYJ", "LB"),
           ("s5", "Pat Claimer", "MIA", "WR")]
CLAIM_ROWS = [
    ["Pat Claimer", "MIA", "WR", "Claim", "Team Alpha", "$5.00", "Wed Sep 16, 2026, 8:00AM", "2"],
    ["Alex Drafted", "KC", "WR", "Drop", "Team Alpha", "", "Wed Sep 16, 2026, 8:00AM", "2"],
    ["Sam Same", "NYJ", "LB", "Claim", "Team Bravo", "", "Thu Sep 17, 2026, 2:15PM", "2"],
    ["Nobody Known", "SEA", "TE", "Claim", "Team Charlie", "", "Thu Sep 17, 2026, 3:00PM", "2"],
    ["Sam Same", "NYJ", "LB", "Lineup Change", "Team Bravo", "", "Fri Sep 18, 2026, 9:00AM", "2"],
]
TRADE_ROWS = [
    ["Blake Drafted", "DAL", "RB", "Team Bravo", "Team Charlie", "Fri Sep 25, 2026, 3:30PM", "3"],
    ["2027 Draft Pick, Round 1 (Team Charlie)", "", "", "Team Charlie", "Team Bravo",
     "Fri Sep 25, 2026, 3:30PM", "3"],
]
LATE_CLAIM = ["Sam Same", "BUF", "QB", "Claim", "Team Charlie", "$1.00",
              "Wed Oct 07, 2026, 8:00AM", "5"]
# The same claims, Team Bravo's under a one-letter slip (a guess of 90 or
# more), and a claim by a name no stored name is near (the owner's list).
ZULU = ["Sam Same", "BUF", "QB", "Claim", "Zulu Club", "", "Thu Sep 17, 2026, 4:00PM", "2"]
RENAMED = CLAIM_ROWS[:2] + [CLAIM_ROWS[2][:4] + ["Team Bravoo"] + CLAIM_ROWS[2][5:]] + CLAIM_ROWS[3:] + [ZULU]


def write_csv(path: Path, view: str, rows: list):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, quoting=csv.QUOTE_ALL)
        writer.writerow(lf.HEADER[view])
        writer.writerows(rows)
    return path


def download(raw: Path, stamp: str, claims=CLAIM_ROWS, trades=TRADE_ROWS):
    """One download of both views, named as the site names them plus `_hhmm`."""
    write_csv(raw / f"Fantrax-Transaction-History-Claims+Drops-Made Up League-{stamp}.csv",
              "CLAIM_DROP", claims)
    write_csv(raw / f"Fantrax-Transaction-History-Trade-Made Up League-{stamp}.csv",
              "TRADE", trades)


def write_store(data: Path):
    for dim in ("dim_contract", "dim_season"):
        shutil.copy(REPO / "data" / f"{dim}.parquet", data / f"{dim}.parquet")
    pd.DataFrame([(k, f, n, "A") for k, (f, n) in TEAMS.items()],
                 columns=["team_key", "fantrax_team_id", "team_name", "conference"]
                 ).to_parquet(data / "dim_fantasy_teams.parquet", index=False)
    pd.DataFrame([(s, n, p, t, None, None) for s, n, t, p in PLAYERS],
                 columns=["scorer_id", "player_name", "position_raw", "nfl_team", "gsis_id",
                          "player_key"]).to_parquet(data / "dim_fantrax_crosswalk.parquet", index=False)
    pd.DataFrame([(f"{SEASON}|D1|S{i:03d}", SEASON, "D1", 1, i, i, k, k, True, "Startup")
                  for i, k in enumerate(TEAMS, 1)],
                 columns=["pick_ref", "draft_season", "division_id", "round", "pick_in_round",
                          "overall_slot", "current_owner", "original_owner", "is_made", "draft_type"]
                 ).to_parquet(data / "fact_draft_pick.parquet", index=False)
    pd.DataFrame([(f"2027|{k}|1", "2027-2028", 1, k, k) for k in TEAMS],
                 columns=["pick_ref", "draft_season", "round", "original_owner", "current_owner"]
                 ).to_parquet(data / "fact_draft_pick_future.parquet", index=False)
    pd.DataFrame([(1, "player", "s1", None, None, None), (2, "player", "s2", None, None, None)],
                 columns=rt.ASSET_COLS).to_parquet(data / "dim_roster_asset.parquet", index=False)
    startup = pd.DataFrame([
        {"transaction_id": f"{SEASON}|D1|S00{i}", "season_id": SEASON, "event_type": rt.EVENT_TYPE,
         "team_key": team, "asset_id": i, "event_seq": i,
         "event_date": pd.Timestamp("2026-06-09"), "period": 1, "contract_id": "1st",
         "contract_year": 1.0, "contract_value": 3_000_000.0, "contract_source": "default",
         "status": "active", "scorer_id": sid, "gsis_id": None, "draft_round": 1.0,
         "pick_in_round": float(i), "pick_overall": float(i), "source": rt.SOURCE,
         "claim_method": None, "claim_bid": None}
        for i, (sid, team) in enumerate((("s1", "A01"), ("s2", "A02")), 1)])
    startup["period"] = startup["period"].astype("Int64")
    rt.claim_dtypes(startup)[rt.LEDGER_COLS].to_parquet(
        data / "fact_roster_transactions.parquet", index=False)


@pytest.fixture
def data(tmp_path, monkeypatch):
    """A temp store and raw folder, with the loader and 02d pointed at them."""
    store, raw, review = tmp_path / "data", tmp_path / "raw", tmp_path / "review"
    for d in (store, raw, review):
        d.mkdir()
    write_store(store)
    monkeypatch.setattr(rt.CFG, "data_dir", str(store))
    for name, value in list(vars(rt).items()):
        if name.endswith("_PATH"):
            monkeypatch.setattr(rt, name, review / Path(value).name)
    monkeypatch.setattr(lf, "REVIEW_PATH", review / lf.REVIEW_PATH.name)
    monkeypatch.setattr(lf, "TEAM_REVIEW_PATH", review / lf.TEAM_REVIEW_PATH.name)
    monkeypatch.setattr(lf, "SHADOW_DIR", review / "shadow")
    return tmp_path


def run(data, *flags):
    return lf.main(["--raw-dir", str(data / "raw"), "--shadow-dir", str(data / "review" / "shadow"),
                    *flags])


def table(data, name, shadow=False):
    folder = data / "review" / "shadow" if shadow else data / "data"
    return pd.read_parquet(folder / f"{name}.parquet")


def moves(ledger):
    return ledger[ledger["event_type"].isin(rt.TXN_EVENT_TYPES)]


class TestFiles:
    def test_the_newest_download_is_picked_by_the_stamp_in_its_name(self, tmp_path):
        old = write_csv(tmp_path / "Fantrax-Transaction-History-Trade-L-20261121_0800.csv", "TRADE", [])
        new = write_csv(tmp_path / "Fantrax-Transaction-History-Trade-L-20261128_0753.csv", "TRADE", [])
        os.utime(new, (1, 1))                      # older on disk; the name still wins
        assert lf.newest_file(tmp_path, "TRADE") == new
        assert lf.newest_file(tmp_path, "CLAIM_DROP") is None
        assert old.exists()

    def test_an_unstamped_download_newer_on_disk_is_named(self, tmp_path):
        stamped = write_csv(tmp_path / "Fantrax-Transaction-History-Trade-L-20261128_0753.csv", "TRADE", [])
        os.utime(stamped, (1, 1))
        write_csv(tmp_path / "Fantrax-Transaction-History-Trade-L-20261128 (1).csv", "TRADE", [])
        assert lf.newest_file(tmp_path, "TRADE") == stamped
        assert lf.unstamped_newer(tmp_path, "TRADE", stamped) == 1
        assert lf.stamp_of(stamped) == "20261128_0753"

    def test_a_changed_header_stops_the_load(self, tmp_path):
        path = tmp_path / "x.csv"
        path.write_text('"Player","Team","When"\n', encoding="utf-8")
        with pytest.raises(SystemExit, match="header"):
            lf.read_view(path, "TRADE")

    def test_columns_are_read_by_position(self, tmp_path):
        path = write_csv(tmp_path / "c.csv", "CLAIM_DROP", CLAIM_ROWS[:1])
        frame = lf.read_view(path, "CLAIM_DROP")
        assert list(frame.columns) == lf.COLUMNS["CLAIM_DROP"] + ["line"]
        assert frame.loc[0, "team"] == "Team Alpha" and frame.loc[0, "nfl_team"] == "MIA"


class TestNames:
    def names(self, roster=(), twin=True):
        teams = pd.DataFrame([(k, f, n) for k, (f, n) in TEAMS.items()]
                             + ([("A04", "f4", "team alpha ")] if twin else []),
                             columns=["team_key", "fantrax_team_id", "team_name"])
        cross = pd.DataFrame([(s, n, t, p) for s, n, t, p in PLAYERS],
                             columns=["scorer_id", "player_name", "nfl_team", "position_raw"])
        return lf.Names(teams, cross, set(roster))

    def test_a_team_name_two_teams_share_is_not_guessed(self):
        names = self.names()
        assert names.team("Team Bravo") == ("A02", "f2")
        assert names.team("TEAM ALPHA") == (None, "ambiguous_team")
        assert names.team("Team Zulu") == (None, "unknown_team")

    def test_a_shared_name_is_narrowed_by_nfl_team_then_position(self):
        names = self.names()
        assert names.player("Sam Same", "NYJ", "LB", "A02") == ("s4", None)
        assert names.player("Sam Same", "FA", "QB", "A02") == ("s3", None)

    def test_roster_state_narrows_what_team_and_position_leave(self):
        names = self.names(roster={("A02", "s4")})
        assert names.player("Sam Same", "FA", "", "A02") == ("s4", None)

    def test_an_unknown_or_unsplit_name_goes_to_review(self):
        names = self.names()
        assert names.player("Nobody Known", "SEA", "TE", "A01") == (None, "unknown_player")
        assert names.player("Sam Same", "FA", "", "A01") == (None, "ambiguous_player")


class TestIds:
    def names(self):
        return TestNames().names(twin=False)

    def test_a_minted_id_is_the_same_for_the_same_parts(self):
        assert lf.mint("a", 1) == lf.mint("a", 1) != lf.mint("a", 2)
        assert lf.mint("a", 1).startswith(lf.MINTED)

    def test_a_stored_claim_keeps_its_id_and_its_drop_is_minted(self):
        frame = pd.DataFrame([r + [i] for i, r in enumerate(CLAIM_ROWS[:2], 2)],
                             columns=lf.COLUMNS["CLAIM_DROP"] + ["line"])
        at = pd.Timestamp("2026-09-16 08:00")
        counts, review = {}, []
        rows = lf.claim_drop_rows(frame, self.names(), {(rt.CLAIM_EVENT, "s5", "A01", at): "fx1"},
                                  review, counts)
        assert [r["txSetId"] for r in rows][0] == "fx1"
        assert rows[1]["txSetId"].startswith(lf.MINTED)
        assert counts == {"reused": 1, "minted": 1, "unsure_pairing": 0} and not review

    def test_a_drop_among_several_moves_of_its_minute_is_counted(self):
        extra = ["Sam Same", "BUF", "QB", "Claim", "Team Alpha", "", CLAIM_ROWS[0][6], "2"]
        frame = pd.DataFrame([r + [i] for i, r in enumerate(CLAIM_ROWS[:2] + [extra], 2)],
                             columns=lf.COLUMNS["CLAIM_DROP"] + ["line"])
        counts = {}
        lf.claim_drop_rows(frame, self.names(), {}, [], counts)
        assert counts["unsure_pairing"] == 1

    def test_legs_of_one_minute_group_by_the_teams_they_connect(self):
        other = ["Sam Same", "BUF", "QB", "Team Alpha", "Team Zulu", TRADE_ROWS[0][5], "3"]
        frame = pd.DataFrame([r + [i] for i, r in enumerate(TRADE_ROWS + [other], 2)],
                             columns=lf.COLUMNS["TRADE"] + ["line"])
        review, counts = [], {}
        rows = lf.trade_rows(frame, self.names(), {}, {}, review, counts)
        assert rows[0]["txSetId"] == rows[1]["txSetId"]
        assert review == [("TRADE", 4, "Sam Same", "Team Alpha", "unknown_team")]
        assert rows[1]["draftPickDisplayParts"]["roundInfo"] == "Round <b>1</b> (Team Charlie)"

    def test_a_minute_the_store_holds_as_two_trades_is_counted_not_merged(self):
        frame = pd.DataFrame([r + [i] for i, r in enumerate(TRADE_ROWS, 2)],
                             columns=lf.COLUMNS["TRADE"] + ["line"])
        at = pd.Timestamp("2026-09-25 15:30")
        counts = {}
        rows = lf.trade_rows(frame, self.names(), {(rt.TRADE_IN, "s2", "A03", at): "fx1"},
                             {(2027, 1, 0, "A03", "A02", at): "fx2"}, [], counts)
        assert [r["txSetId"] for r in rows] == ["fx1", "fx2"]
        assert counts.get("ungroupable_legs", 0) == 0 and counts["reused"] == 2


class TestLoad:
    def test_a_shadow_load_writes_only_the_shadow(self, data):
        download(data / "raw", "20261128_0752")
        before = (data / "data" / "fact_roster_transactions.parquet").read_bytes()
        rt.PICK_REVIEW_PATH.write_text("a real review file", encoding="utf-8")
        result = run(data)
        assert (data / "data" / "fact_roster_transactions.parquet").read_bytes() == before
        assert rt.PICK_REVIEW_PATH.read_text(encoding="utf-8") == "a real review file"
        shadow = moves(table(data, "fact_roster_transactions", shadow=True))
        assert sorted(shadow["event_type"]) == ["claim", "claim", "drop", "trade", "trade_away"]
        assert result["review"] == 1 and result["ledger"]["new"] == 5
        assert pd.read_csv(data / "review" / lf.REVIEW_PATH.name)["reason"].tolist() == ["unknown_player"]
        log = table(data, "fact_trade_log", shadow=True)
        assert sorted(log["asset_kind"]) == ["pick", "player"] and log["transaction_id"].nunique() == 1

    def test_what_the_files_hold_reaches_the_ledger(self, data):
        download(data / "raw", "20261128_0752")
        run(data, "--write")
        ledger = moves(table(data, "fact_roster_transactions")).set_index(["event_type", "scorer_id"])
        assert ledger.loc[("claim", "s5"), "claim_method"] == rt.CLAIM_WAIVER
        assert ledger.loc[("claim", "s5"), "claim_bid"] == 5.0
        assert ledger.loc[("claim", "s4"), "claim_method"] == rt.CLAIM_FREE_AGENT
        assert ledger.loc[("drop", "s1"), "claim_method"] == rt.CLAIM_WAIVER   # paired by minute
        assert ledger.loc[("trade_away", "s2"), "team_key"] == "A02"
        assert ledger.loc[("trade", "s2"), "period"] == 3
        assert ledger["transaction_id"].str.startswith(lf.MINTED).all()

    def test_the_same_files_twice_change_nothing(self, data):
        download(data / "raw", "20261128_0752")
        run(data, "--write")
        first = {n: table(data, n) for n in lf.SHADOW_TABLES}
        result = run(data, "--write")
        for name, frame in first.items():
            pd.testing.assert_frame_equal(table(data, name), frame)
        assert result["ledger"] == {"same": 5, "changed": 0, "new": 0, "gone": 0}
        assert result["store_only"] == 0 and result["reused"] == 5 and "minted" not in result

    def test_a_newer_download_adds_only_the_new_move(self, data):
        download(data / "raw", "20261121_0800")
        run(data, "--write")
        download(data / "raw", "20261128_0752", claims=CLAIM_ROWS + [LATE_CLAIM])
        result = run(data, "--write")
        assert result["ledger"] == {"same": 5, "changed": 0, "new": 1, "gone": 0}
        assert result["minted"] == 1

    def test_write_refuses_a_download_that_lacks_a_stored_move(self, data, capsys):
        download(data / "raw", "20261121_0800")
        run(data, "--write")
        before = table(data, "fact_roster_transactions")
        download(data / "raw", "20261128_0752", claims=CLAIM_ROWS[1:])
        with pytest.raises(SystemExit, match="nothing written"):
            run(data, "--write")
        pd.testing.assert_frame_equal(table(data, "fact_roster_transactions"), before)
        capsys.readouterr()
        assert run(data)["store_only"] == 1                # a shadow load still reports it
        assert f"by season {{'{SEASON}': 1}}" in capsys.readouterr().out

    def test_write_refuses_a_download_that_lacks_a_stored_pick_leg(self, data):
        download(data / "raw", "20261121_0800")
        run(data, "--write")
        before = table(data, "fact_trade_log")
        download(data / "raw", "20261128_0752", trades=TRADE_ROWS[:1])
        with pytest.raises(SystemExit, match="nothing written"):
            run(data, "--write")
        pd.testing.assert_frame_equal(table(data, "fact_trade_log"), before)
        result = run(data)
        assert result["store_only"] == 0 and result["trade_log"]["gone"] == 1

    def test_a_blank_week_stops_the_load_naming_no_scorer(self, data):
        download(data / "raw", "20261128_0752", trades=[TRADE_ROWS[0][:6] + [""]])
        with pytest.raises(RuntimeError) as err:
            run(data)
        assert "s2" not in str(err.value) and "1 transaction leg(s)" in str(err.value)

    def test_the_output_names_no_scorer_team_or_player(self, data, capsys):
        download(data / "raw", "20261128_0752")
        run(data)
        out = capsys.readouterr().out
        for value in ("s1", "s2", "s4", "s5", "A01", "A02", "A03", "Team ", "Drafted", "Claimer"):
            assert value not in out

    def test_the_output_names_no_listed_or_guessed_team(self, data, capsys):
        download(data / "raw", "20261128_0752", claims=RENAMED)
        run(data)
        out = capsys.readouterr().out
        for value in ("Bravoo", "Zulu", "f2", "f3"):
            assert value not in out

    def test_no_network_request(self, data, monkeypatch):
        def refuse(*args, **kwargs):
            raise AssertionError("the loader opened a network connection")
        monkeypatch.setattr(socket.socket, "connect", refuse)
        monkeypatch.setattr(socket, "create_connection", refuse)
        download(data / "raw", "20261128_0752")
        run(data)


def alias(*rows):
    """Crosswalk rows (name_clean, fantrax_team_id, decision) into the temp store."""
    etl.write_table(etl.TEAM_ALIAS_TABLE, ln._frame(
        [(n, t, d, None, "test", pd.Timestamp("2026-11-28", tz="UTC")) for n, t, d in rows]))


class TestTeamNameCrosswalk:
    def test_an_old_name_resolves_through_the_crosswalk(self, data):
        alias(("old bravo", "f2", "owner"))
        claims = CLAIM_ROWS[:2] + [CLAIM_ROWS[2][:4] + ["Old  BRAVO"] + CLAIM_ROWS[2][5:]] + CLAIM_ROWS[3:]
        download(data / "raw", "20261128_0752", claims=claims)
        result = run(data)
        assert result["team_names"]["crosswalk"] == 1 and result["team_names"]["listed"] == 0
        assert result["review"] == 1                       # the unknown player only
        shadow = moves(table(data, "fact_roster_transactions", shadow=True)).set_index(["event_type", "scorer_id"])
        assert shadow.loc[("claim", "s4"), "team_key"] == "A02"
        assert not lf.TEAM_REVIEW_PATH.exists()

    def test_a_guess_is_used_in_the_shadow_and_listed_after_the_names_that_need_the_owner(self, data):
        download(data / "raw", "20261128_0752", claims=RENAMED)
        result = run(data)
        assert result["team_names"] == {"crosswalk": 0, "current": 3, "guess": 1, "listed": 1}
        listed = pd.read_csv(lf.TEAM_REVIEW_PATH, dtype=str)
        assert list(listed.columns) == etl.TEAM_NAME_REVIEW_COLS
        assert listed["reason"].tolist() == ["no_guess", "guess_90"]
        assert listed.loc[0, "name"] == "Zulu Club" and pd.isna(listed.loc[0, "fantrax_team_id"])
        assert listed.loc[1, "fantrax_team_id"] == "f2" and listed.loc[1, "best_guess_team_key"] == "A02"
        reasons = pd.read_csv(lf.REVIEW_PATH)["reason"].tolist()
        assert sorted(reasons) == ["unknown_player", "unknown_team"]
        shadow = moves(table(data, "fact_roster_transactions", shadow=True)).set_index(["event_type", "scorer_id"])
        assert shadow.loc[("claim", "s4"), "team_key"] == "A02"

    def test_write_refuses_while_a_name_resolves_only_by_a_guess(self, data):
        download(data / "raw", "20261128_0752", claims=RENAMED)
        before = table(data, "fact_roster_transactions")
        with pytest.raises(SystemExit, match="guess not yet applied"):
            run(data, "--write")
        pd.testing.assert_frame_equal(table(data, "fact_roster_transactions"), before)

    def test_the_owner_list_applied_resolves_every_name_and_write_goes_through(self, data, monkeypatch):
        download(data / "raw", "20261128_0752", claims=RENAMED)
        run(data)
        listed = pd.read_csv(lf.TEAM_REVIEW_PATH, dtype=str)
        listed.loc[listed["name"] == "Zulu Club", "fantrax_team_id"] = "f3"
        listed.to_csv(lf.TEAM_REVIEW_PATH, index=False)
        monkeypatch.setattr(ln, "REVIEW_PATH", lf.TEAM_REVIEW_PATH)
        assert ln.main(["--apply"])["owner"] == 1
        result = run(data, "--write")
        assert result["team_names"] == {"crosswalk": 2, "current": 3, "guess": 0, "listed": 0}
        ledger = moves(table(data, "fact_roster_transactions")).set_index(["event_type", "scorer_id"])
        assert ledger.loc[("claim", "s3"), "team_key"] == "A03"
        assert not lf.TEAM_REVIEW_PATH.exists()

    def test_a_pick_hint_is_a_team_name_too(self):
        names = TestIds().names()
        names.known = etl.team_names(pd.DataFrame([(k, f, n) for k, (f, n) in TEAMS.items()],
                                                  columns=["team_key", "fantrax_team_id", "team_name"]),
                                     pd.DataFrame([("old charlie", "f3")], columns=["name_clean", "fantrax_team_id"]))
        frame = pd.DataFrame([["2027 Draft Pick, Round 1 (Old Charlie)"] + TRADE_ROWS[1][1:] + [2],
                              ["2027 Draft Pick, Round 2 (Zulu Club)"] + TRADE_ROWS[1][1:] + [3]],
                             columns=lf.COLUMNS["TRADE"] + ["line"])
        lf.trade_rows(frame, names, {}, {}, [], {})
        assert names.pick_hints()["old charlie"] == "A03"
        assert names.review_frame()["name"].tolist() == ["Zulu Club"]

    def test_a_left_out_pick_leg_of_the_same_year_and_round_explains_a_gap(self, data):
        shadow = data / "review" / "shadow"
        shadow.mkdir()
        pd.DataFrame([("2027|A01|1", "A01", "A02"), (f"{SEASON}|D1|S001", "A01", "A03")],
                     columns=rt.PICK_OWNER_REVIEW_COLS).to_csv(shadow / rt.PICK_OWNER_REVIEW_PATH.name, index=False)
        assert lf.pick_gaps(shadow, [(2027, 1)]) == {"explained": 1, "not_explained": 1}
        left = []
        frame = pd.DataFrame([["2027 Draft Pick, Round 1 (Team Charlie)", "", "", "Zulu Club", "Team Bravo",
                               TRADE_ROWS[1][5], "3", 2]], columns=lf.COLUMNS["TRADE"] + ["line"])
        lf.trade_rows(frame, TestIds().names(), {}, {}, [], {}, left)
        assert left == [(2027, 1)]
