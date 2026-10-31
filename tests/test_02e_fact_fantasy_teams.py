"""02e: fact_fantasy_teams from the saved current roster, with ledger
provenance and the cap charge; and the roster_membership Review check (#97).
main() runs on a temp data dir with hand-built tables and raw files."""
import importlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))

import pandas as pd
import pytest

import etl_checks
import etl_helpers

fe = importlib.import_module("02e_fact_fantasy_teams_derive")

SEASON = "2026-2027"
READ = "2026-10-14T22:12:00+00:00"
LEDGER_AT = pd.Timestamp("2026-10-14 23:00", tz="UTC")

TEAMS = pd.DataFrame({"team_key": ["A01", "B01"], "fantrax_team_id": ["ta", "tb"],
                      "conference": ["A", "B"], "original_cap": [300.0, 300.0],
                      "reinvestment_cap": [0.0, 0.0]})
CONTRACTS = pd.DataFrame({
    "contract_id": ["1st", "FA", "Minor"],
    "contract_year": pd.array([1, pd.NA, pd.NA], dtype="Int64"),
    "total_years": pd.array([3, pd.NA, pd.NA], dtype="Int64")})
ASSETS = pd.DataFrame({"asset_id": [1, 2, 3], "asset_type": ["player", "player", "pick"],
                       "scorer_id": ["p1", "p2", None], "gsis_id": ["g1", None, None],
                       "player_key": [None, "k2", None]})
CROSSWALK = pd.DataFrame({"scorer_id": ["p2", "p4"], "gsis_id": ["g2", "g4"],
                          "player_key": ["x2", "k4"]})
LEDGER = pd.DataFrame({
    "event_seq": [1, 2, 100_000, 100_001, 100_002],
    "team_key": ["A01", "A01", "A01", "B01", "A01"],
    "scorer_id": ["p1", "p2", "p3", "p1", "p2"],
    "event_type": ["startup_draft", "startup_draft", "claim", "startup_draft", "drop"],
    "event_date": pd.to_datetime(["2026-06-11 00:00", "2026-06-11 00:00", "2026-10-14 08:00",
                                  "2026-06-20 00:00", "2026-10-14 08:00"]).astype("datetime64[us]"),
    "season_id": [SEASON] * 5,
    "contract_id": ["1st", "1st", "FA", "1st", "1st"],
    "contract_value": [10.0, 20.0, 2.0, 11.0, 20.0],
})
DEAD = pd.DataFrame({"transaction_id": ["t1", "t1"], "scorer_id": ["p2", "p2"],
                     "team_key": ["A01", "A01"], "season_id": [SEASON, "2027-2028"],
                     "dead_money": [10.0, 8.0]})


def periods(first):
    starts = [first + pd.Timedelta(weeks=n) for n in range(3)]
    return pd.DataFrame({"season_id": SEASON, "period": [1, 2, 3],
                         "start_at": pd.Series(starts, dtype="datetime64[us, UTC]"),
                         "end_at": pd.Series([s + pd.Timedelta(weeks=1) for s in starts],
                                             dtype="datetime64[us, UTC]")})


def item(sid, status, salary, contract):
    return {"id": sid, "status": status, "salary": salary, "contract": {"name": contract}}


REPLY = {"captured_at": READ, "season_id": SEASON, "period": 6, "rosters": {
    "ta": {"rosterItems": [item("p1", "ACTIVE", 10.0, "1st"),
                           item("p3", "INJURED_RESERVE", 2.0, "FA"),
                           item("p4", "MINORS", 5.0, "Minor")]},
    "tb": {"rosterItems": [item("p1", "RESERVE", 11.0, "1st")]}}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    data, raw = tmp_path / "data", tmp_path / "raw"
    data.mkdir(); raw.mkdir()
    now = pd.Timestamp.now(tz="UTC").floor("s")
    tables = {"fact_roster_transactions": LEDGER, "dim_roster_asset": ASSETS,
              "dim_fantasy_teams": TEAMS, "dim_contract": CONTRACTS,
              "dim_fantrax_crosswalk": CROSSWALK, "fact_dead_money": DEAD,
              "dim_scoring_period": periods(now - pd.Timedelta(weeks=1))}
    for name, df in tables.items():
        df.to_parquet(data / f"{name}.parquet", index=False)
    (raw / "fantrax_public_rosters_2026_p06.json").write_text(json.dumps(REPLY), encoding="utf-8")
    (raw / "fantrax_public_rosters_2026_p05.json").write_text(
        json.dumps({**REPLY, "period": 5, "rosters": {}}), encoding="utf-8")
    txn = raw / "fantrax_txn_history_2026.json"
    txn.write_text("[]", encoding="utf-8")
    os.utime(txn, (LEDGER_AT.timestamp(), LEDGER_AT.timestamp()))
    monkeypatch.setattr(etl_helpers.CFG, "data_dir", str(data))
    return data, raw


def run(raw):
    assert fe.main(["--raw-dir", str(raw)]) == 0


def published(data):
    return etl_helpers.read_table("fact_fantasy_teams").set_index(["team_key", "scorer_id"])


class TestFromReply:
    def test_rows_are_the_reply_with_its_slots_salary_and_contract(self, env):
        data, raw = env
        run(raw)
        df = published(data)
        assert sorted(df.index) == [("A01", "p1"), ("A01", "p3"), ("A01", "p4"), ("B01", "p1")]
        assert df.loc[("A01", "p3"), "roster_slot"] == "IR"
        assert df.loc[("B01", "p1"), "roster_slot"] == "Bench"
        assert df.loc[("A01", "p3"), "contract_value"] == 2.0
        assert (df["season"] == SEASON).all()

    def test_minors_and_ir_are_exempt_and_charge_nothing(self, env):
        data, raw = env
        run(raw)
        df = published(data)
        assert df["cap_exempt"].to_dict() == {("A01", "p1"): False, ("A01", "p3"): True,
                                              ("A01", "p4"): True, ("B01", "p1"): False}
        assert df["cap_hit"].to_dict() == {("A01", "p1"): 10.0, ("A01", "p3"): 0.0,
                                           ("A01", "p4"): 0.0, ("B01", "p1"): 11.0}

    def test_provenance_is_the_move_that_opened_the_stint_else_unknown(self, env):
        data, raw = env
        run(raw)
        df = published(data)
        assert df["acquired_method"].to_dict() == {
            ("A01", "p1"): "startup_draft", ("A01", "p3"): "claim",
            ("A01", "p4"): "unknown", ("B01", "p1"): "startup_draft"}
        assert df.loc[("A01", "p3"), "acquired_date"] == pd.Timestamp("2026-10-14 08:00")
        assert pd.isna(df.loc[("A01", "p4"), "acquired_date"])

    def test_identity_from_the_asset_then_the_crosswalk(self, env):
        data, raw = env
        run(raw)
        df = published(data)
        assert df.loc[("A01", "p1"), "gsis_id"] == "g1"
        assert df.loc[("A01", "p4"), "gsis_id"] == "g4"
        assert df.loc[("A01", "p4"), "player_key"] == "k4"
        assert pd.isna(df.loc[("A01", "p3"), "gsis_id"])       # on no asset or crosswalk

    def test_the_two_capture_instants(self, env):
        data, raw = env
        run(raw)
        df = published(data)
        assert (df["roster_captured_at"] == pd.Timestamp(READ)).all()
        assert (df["ledger_captured_at"] == LEDGER_AT).all()

    def test_contract_year_from_dim_contract(self, env):
        data, raw = env
        run(raw)
        df = published(data)
        assert df.loc[("A01", "p1"), "contract_year"] == 1.0
        assert pd.isna(df.loc[("A01", "p4"), "contract_year"])

    def test_a_second_run_is_byte_identical(self, env):
        data, raw = env
        run(raw)
        first = (data / "fact_fantasy_teams.parquet").read_bytes()
        run(raw)
        assert (data / "fact_fantasy_teams.parquet").read_bytes() == first

    def test_a_reply_missing_a_team_fails_and_publishes_nothing(self, env):
        data, raw = env
        partial = {**REPLY, "rosters": {"ta": REPLY["rosters"]["ta"]}}
        (raw / "fantrax_public_rosters_2026_p06.json").write_text(
            json.dumps(partial), encoding="utf-8")
        with pytest.raises(ValueError, match="missing"):
            fe.main(["--raw-dir", str(raw)])
        assert not (data / "fact_fantasy_teams.parquet").exists()

    def test_the_table_matches_the_registry(self, env):
        data, raw = env
        run(raw)
        entry = {t["name"]: t for t in etl_checks.load_registry().values()}["fact_fantasy_teams"]
        stored = etl_helpers.read_stored("fact_fantasy_teams")
        assert etl_checks.schema_errors(entry, {c: str(d) for c, d in stored.dtypes.items()}) == []


class TestNoReply:
    def test_in_season_the_run_fails(self, env):
        data, raw = env
        for p in raw.glob("fantrax_public_rosters_*.json"):
            p.unlink()
        with pytest.raises(FileNotFoundError, match="run 04r"):
            fe.main(["--raw-dir", str(raw)])
        assert not (data / "fact_fantasy_teams.parquet").exists()

    def test_out_of_season_it_builds_from_the_replay_with_slots_blank(self, env):
        data, raw = env
        for p in raw.glob("fantrax_public_rosters_*.json"):
            p.unlink()
        periods(pd.Timestamp("2025-09-01", tz="UTC")).to_parquet(
            data / "dim_scoring_period.parquet", index=False)
        run(raw)
        df = published(data)
        assert sorted(df.index) == [("A01", "p1"), ("A01", "p3"), ("B01", "p1")]
        assert df["roster_slot"].isna().all() and not df["cap_exempt"].any()
        assert df["cap_hit"].tolist() == df["contract_value"].tolist()
        assert df["roster_captured_at"].isna().all()


class TestCapSummary:
    def test_dead_money_is_this_seasons_only(self):
        fact = pd.DataFrame({"team_key": ["A01", "B01"], "cap_hit": [10.0, 11.0],
                             "season": [SEASON, SEASON]})
        out = fe.cap_summary(fact, DEAD, TEAMS).set_index("team_key")
        assert out.loc["A01", "dead_money"] == 10.0          # not 10 + 8
        assert out.loc["A01", "cap_room"] == 300.0 - 10.0 - 10.0
        assert out.loc["B01", "cap_room"] == 289.0

    def test_a_team_exactly_at_the_cap_is_not_over(self):
        teams = TEAMS.assign(original_cap=300_000_000.0)
        fact = pd.DataFrame({"team_key": ["A01"] * 3 + ["B01"],
                             "cap_hit": [100_000_000.1, 100_000_000.2, 99_999_999.7, 0.0],
                             "season": [SEASON] * 4})
        out = fe.cap_summary(fact, None, teams).set_index("team_key")
        assert out.loc["A01", "cap_room"] == 0.0


class TestRosterMembership:
    def findings(self, data):
        return etl_checks.roster_membership_findings(
            etl_helpers.read_stored("fact_fantasy_teams"),
            etl_helpers.read_stored("fact_roster_transactions"))

    def test_a_fresh_ledger_files_each_difference(self, env):
        data, raw = env
        run(raw)
        assert sorted(self.findings(data)) == [
            ("A01|p4", "p4 is on A01's roster with no open stint on the ledger")]

    def test_an_open_stint_off_the_roster_is_filed(self, env):
        data, raw = env
        REPLY_NO_P3 = json.loads(json.dumps(REPLY))
        REPLY_NO_P3["rosters"]["ta"]["rosterItems"] = [
            i for i in REPLY_NO_P3["rosters"]["ta"]["rosterItems"] if i["id"] != "p3"]
        (raw / "fantrax_public_rosters_2026_p06.json").write_text(
            json.dumps(REPLY_NO_P3), encoding="utf-8")
        run(raw)
        assert ("A01|p3", "the ledger has p3 on A01, the roster does not") in self.findings(data)

    def test_a_stale_ledger_holds_the_rows_back_with_one_finding(self, env):
        data, raw = env
        old = (pd.Timestamp(READ) - pd.Timedelta(hours=1)).timestamp()
        os.utime(raw / "fantrax_txn_history_2026.json", (old, old))
        run(raw)
        got = self.findings(data)
        assert len(got) == 1 and got[0][0] == "ledger_stale"
        assert "the ledger is stale" in got[0][1]

    def test_a_replay_build_files_one_finding(self, env):
        data, raw = env
        for p in raw.glob("fantrax_public_rosters_*.json"):
            p.unlink()
        periods(pd.Timestamp("2025-09-01", tz="UTC")).to_parquet(
            data / "dim_scoring_period.parquet", index=False)
        run(raw)
        assert [k for k, _ in self.findings(data)] == ["replay"]

    def test_the_check_is_registered_as_review(self):
        dc = next(d for d in etl_checks.DOMAIN_CHECKS if d.name == "roster_membership")
        assert (dc.tier, dc.table) == ("review", "fact_fantasy_teams")
