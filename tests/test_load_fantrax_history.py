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
        assert counts == {"reused": 1, "minted": 1} and not review

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
        result = run(data)
        assert (data / "data" / "fact_roster_transactions.parquet").read_bytes() == before
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

    def test_write_refuses_a_download_that_lacks_a_stored_move(self, data):
        download(data / "raw", "20261121_0800")
        run(data, "--write")
        before = table(data, "fact_roster_transactions")
        download(data / "raw", "20261128_0752", claims=CLAIM_ROWS[1:])
        with pytest.raises(SystemExit, match="nothing written"):
            run(data, "--write")
        pd.testing.assert_frame_equal(table(data, "fact_roster_transactions"), before)
        assert run(data)["store_only"] == 1                # a shadow load still reports it

    def test_no_network_request(self, data, monkeypatch):
        def refuse(*args, **kwargs):
            raise AssertionError("the loader opened a network connection")
        monkeypatch.setattr(socket.socket, "connect", refuse)
        monkeypatch.setattr(socket, "create_connection", refuse)
        download(data / "raw", "20261128_0752")
        run(data)
