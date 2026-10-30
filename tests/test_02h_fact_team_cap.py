"""02h: fact_team_cap, the published per-team cap table (#97), with its Gate
and the Salary Remaining Review check. Pure builders run on small frames;
main() runs on a temp data dir with hand-built tables and raw files."""
import importlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import pandas as pd
import pytest

import etl_cap as cap
import etl_checks
import etl_helpers

ft = importlib.import_module("02h_fact_team_cap")

THIS, NEXT, LATER = "2026-2027", "2027-2028", "2028-2029"
READ = "2026-10-14T22:12:00+00:00"
LEDGER_AT = pd.Timestamp("2026-10-14 23:00", tz="UTC")

TEAMS = pd.DataFrame({"team_key": ["A01", "B01"], "fantrax_team_id": ["ta", "tb"],
                      "conference": ["A", "B"], "original_cap": [300, 300],
                      "reinvestment_cap": [7, 0]})
CONTRACTS = pd.DataFrame({
    "contract_id": ["1st", "3rd", "FA", "Minor", "X"],
    "contract_year": pd.array([1, 3, 1, pd.NA, 1], dtype="Int64"),
    "total_years": pd.array([3, 3, 1, pd.NA, 1], dtype="Int64")})
SEASONS = pd.DataFrame({"season_id": [THIS, NEXT, LATER],
                        "season_start_year": [2026, 2027, 2028]})
DEAD = pd.DataFrame({"team_key": ["A01", "A01", "B01"], "season_id": [THIS, NEXT, NEXT],
                     "dead_money": [10.0, 8.0, 4.0]})


def roster(*rows, season=THIS):
    """(team_key, status, contract_id, value). cap_hit follows etl_cap's rule."""
    df = pd.DataFrame(rows, columns=["team_key", "roster_status", "contract_id", "contract_value"])
    slots = df["roster_status"].map({"Inj Res": "IR", "Minors": "Minors"})
    charge = cap.stamp_cap(slots, df["contract_value"])
    return df.assign(cap_hit=charge["cap_hit"], cap_exempt=charge["cap_exempt"], season=season,
                     scorer_id=[f"p{i}" for i in range(len(df))],
                     roster_captured_at=pd.Timestamp(READ), ledger_captured_at=LEDGER_AT)


ROSTER = roster(("A01", "Active", "1st", 50.0),     # carries
                ("A01", "Reserve", "3rd", 20.0),    # last year: does not carry
                ("A01", "Inj Res", "1st", 30.0),    # exempt now, carries in full
                ("A01", "Minors", "Minor", 5.0),    # exempt now, carries in full
                ("A01", "Inj Res", "FA", 2.0),      # exempt, does not carry
                ("B01", "Active", "X", 40.0))       # expiring


def table(r=ROSTER, dead=DEAD):
    return cap.team_cap(r, dead, TEAMS, CONTRACTS, SEASONS).set_index(["season_id", "team_key"])


class TestTeamCap:
    def test_two_rows_per_team(self):
        t = table()
        assert sorted(t.index) == [(THIS, "A01"), (THIS, "B01"), (NEXT, "A01"), (NEXT, "B01")]
        assert t["is_current_season"].to_dict() == {
            (THIS, "A01"): True, (THIS, "B01"): True, (NEXT, "A01"): False, (NEXT, "B01"): False}

    def test_each_season_charges_only_its_own_dead_money(self):
        t = table()
        assert t.loc[(THIS, "A01"), "dead_money"] == 10.0     # not 18
        assert t.loc[(NEXT, "A01"), "dead_money"] == 8.0      # not 18
        assert t.loc[(THIS, "B01"), "dead_money"] == 0.0
        assert t.loc[(NEXT, "B01"), "dead_money"] == 4.0

    def test_a_later_seasons_dead_money_reaches_neither_row(self):
        later = pd.concat([DEAD, pd.DataFrame({"team_key": ["A01"], "season_id": [LATER],
                                               "dead_money": [99.0]})])
        assert table(dead=later)["dead_money"].equals(table()["dead_money"])

    def test_ir_and_minors_salary_are_exempt_this_season(self):
        row = table().loc[(THIS, "A01")]
        assert row["charged_salary"] == 70.0
        assert row["ir_salary"] == 32.0
        assert row["minors_salary"] == 5.0

    def test_cap_room_this_season(self):
        assert table().loc[(THIS, "A01"), "cap_room"] == 300.0 - 70.0 - 10.0 - 7.0
        assert table().loc[(THIS, "B01"), "cap_room"] == 260.0

    def test_next_season_counts_every_carried_contract_with_no_slot_exempt(self):
        row = table().loc[(NEXT, "A01")]
        assert row["charged_salary"] == 50.0 + 30.0 + 5.0
        assert (row["ir_salary"], row["minors_salary"]) == (0.0, 0.0)

    def test_next_season_room_takes_its_dead_money_and_no_reinvestment(self):
        row = table().loc[(NEXT, "A01")]
        assert row["reinvestment_cap"] == 0.0
        assert row["cap_room"] == 300.0 - 85.0 - 8.0

    def test_an_expiring_roster_carries_nothing(self):
        assert table().loc[(NEXT, "B01"), "charged_salary"] == 0.0

    def test_a_team_with_no_roster_rows_still_has_both_rows(self):
        only_a = ROSTER[ROSTER["team_key"] == "A01"]
        t = table(only_a)
        assert t.loc[(THIS, "B01"), "cap_room"] == 300.0
        assert t.loc[(NEXT, "B01"), "cap_room"] == 296.0


class TestSeasonAnchor:
    def test_this_season_is_the_rosters_not_the_calendar(self):
        old = roster(("A01", "Active", "1st", 50.0), season="2028-2029")
        seasons = pd.concat([SEASONS, pd.DataFrame({"season_id": ["2029-2030"],
                                                    "season_start_year": [2029]})])
        t = cap.team_cap(old, DEAD, TEAMS, CONTRACTS, seasons)
        assert t.loc[t["is_current_season"], "season_id"].unique().tolist() == ["2028-2029"]
        assert t.loc[~t["is_current_season"], "season_id"].unique().tolist() == ["2029-2030"]

    def test_two_seasons_on_the_roster_fail(self):
        mixed = pd.concat([ROSTER, ROSTER.assign(season=NEXT)])
        with pytest.raises(ValueError, match="2 seasons"):
            cap.team_cap(mixed, DEAD, TEAMS, CONTRACTS, SEASONS)

    def test_no_season_on_the_roster_fails(self):
        with pytest.raises(ValueError, match="0 seasons"):
            cap.team_cap(ROSTER.assign(season=None), DEAD, TEAMS, CONTRACTS, SEASONS)

    def test_a_next_season_missing_from_dim_season_fails(self):
        with pytest.raises(ValueError, match="run 01f"):
            cap.team_cap(ROSTER, DEAD, TEAMS, CONTRACTS, SEASONS[SEASONS["season_id"] == THIS])


FIXTURE = json.loads((REPO / "tests" / "fixtures" / "fantrax" / "standings.json")
                     .read_text(encoding="utf-8"))
FIXTURE_IDS = [c["teamId"] for r in FIXTURE["responses"][0]["data"]["tableList"][0]["rows"]
               for c in r["fixedCells"] if "teamId" in c]
FIXTURE_TEAMS = pd.DataFrame({"fantrax_team_id": FIXTURE_IDS, "team_key": ["A01", "B01"]})


def standings(*amounts, ids=("ta", "tb")):
    return {"responses": [{"data": {"tableList": [{
        "header": {"cells": [{"key": "win"}, {"key": "salaryRem"}]},
        "rows": [{"fixedCells": [{}, {"teamId": i}], "cells": [{"content": "1"}, {"content": a}]}
                 for i, a in zip(ids, amounts)]}]}}]}


class TestParseSalaryRemaining:
    def test_the_fixture(self):
        got = ft.parse_salary_remaining(FIXTURE, FIXTURE_TEAMS)
        assert got.to_dict() == {"A01": 23_029_000.0, "B01": 67_821_000.0}

    def test_the_column_is_found_by_its_key(self):
        reply = standings("1,000", "2,000.50")
        assert ft.parse_salary_remaining(reply, TEAMS).to_dict() == {"A01": 1000.0, "B01": 2000.5}

    def test_a_negative_amount(self):
        assert ft.parse_money("-1,500") == -1500.0
        assert ft.parse_money("-$1,500") == -1500.0

    def test_a_missing_team_fails(self):
        with pytest.raises(ValueError, match="missing"):
            ft.parse_salary_remaining(standings("1,000"), TEAMS)

    def test_an_unknown_team_fails(self):
        with pytest.raises(ValueError, match="known team"):
            ft.parse_salary_remaining(standings("1", "2", ids=("ta", "zz")), TEAMS)

    def test_a_team_twice_fails(self):
        with pytest.raises(ValueError, match="twice"):
            ft.parse_salary_remaining(standings("1", "2", ids=("ta", "ta")), TEAMS)

    def test_a_non_amount_fails_without_echoing_it(self):
        with pytest.raises(ValueError) as e:
            ft.parse_salary_remaining(standings("Some Text", "2"), TEAMS)
        assert "Some Text" not in str(e.value)

    def test_no_column_fails(self):
        reply = standings("1", "2")
        reply["responses"][0]["data"]["tableList"][0]["header"]["cells"][1]["key"] = "other"
        with pytest.raises(ValueError, match="salaryRem"):
            ft.parse_salary_remaining(reply, TEAMS)


def period_file(raw, year, period, captured, *amounts):
    body = {"captured_at": captured, "period": period, "standings": standings(*amounts),
            "live_scoring": {}}
    (raw / f"fantrax_inseason_{year}_p{period:02d}.json").write_text(json.dumps(body),
                                                                     encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    data, raw = tmp_path / "data", tmp_path / "raw"
    data.mkdir(); raw.mkdir()
    tables = {"fact_fantasy_teams": ROSTER, "dim_fantasy_teams": TEAMS, "dim_contract": CONTRACTS,
              "dim_season": SEASONS, "fact_dead_money": DEAD}
    for name, df in tables.items():
        df.to_parquet(data / f"{name}.parquet", index=False)
    monkeypatch.setattr(etl_helpers.CFG, "data_dir", str(data))
    return data, raw


def run(raw):
    assert ft.main(["--raw-dir", str(raw)]) == 0
    return etl_helpers.read_table("fact_team_cap").set_index(["season_id", "team_key"])


class TestMain:
    def test_fantrax_sits_on_the_current_row_only(self, env):
        _, raw = env
        period_file(raw, 2026, 6, READ, "100", "200")
        t = run(raw)
        assert t.loc[(THIS, "A01"), "fantrax_salary_remaining"] == 100.0
        assert t.loc[(THIS, "A01"), "fantrax_period"] == 6
        assert t.loc[(THIS, "A01"), "fantrax_captured_at"] == pd.Timestamp(READ)
        assert t.loc[(THIS, "A01"), "roster_captured_at"] == pd.Timestamp(READ)
        following = t.loc[NEXT]
        assert following[["fantrax_salary_remaining", "fantrax_period", "fantrax_captured_at",
                          "roster_captured_at"]].isna().all().all()

    def test_the_newest_capture_wins_not_the_highest_period(self, env):
        _, raw = env
        period_file(raw, 2026, 6, "2026-10-01T00:00:00+00:00", "1", "1")
        period_file(raw, 2026, 5, "2026-10-09T00:00:00+00:00", "5", "5")
        t = run(raw)
        assert t.loc[(THIS, "A01"), "fantrax_salary_remaining"] == 5.0
        assert t.loc[(THIS, "A01"), "fantrax_period"] == 5

    def test_another_seasons_file_is_not_read(self, env):
        _, raw = env
        period_file(raw, 2025, 6, READ, "100", "200")
        assert run(raw)["fantrax_salary_remaining"].isna().all()

    def test_no_file_leaves_fantrax_null_and_still_builds(self, env):
        _, raw = env
        t = run(raw)
        assert t["fantrax_salary_remaining"].isna().all()
        assert t.loc[(THIS, "A01"), "cap_room"] == 213.0

    def test_a_file_with_no_standings_is_skipped(self, env):
        _, raw = env
        (raw / "fantrax_inseason_2026_p07.json").write_text(
            json.dumps({"captured_at": READ, "period": 7}), encoding="utf-8")
        assert run(raw)["fantrax_salary_remaining"].isna().all()

    def test_the_schedule_file_is_not_a_period_file(self, env):
        _, raw = env
        (raw / "fantrax_inseason_2026_schedule.json").write_text(
            json.dumps({"captured_at": READ, "standings": {}}), encoding="utf-8")
        assert run(raw)["fantrax_salary_remaining"].isna().all()

    def test_an_unreadable_reply_leaves_fantrax_null_and_still_builds(self, env, capsys):
        _, raw = env
        period_file(raw, 2026, 6, READ, "(1,000)", "200")
        t = run(raw)
        assert t["fantrax_salary_remaining"].isna().all()
        assert t["fantrax_captured_at"].isna().all()
        assert t.loc[(THIS, "A01"), "cap_room"] == 213.0
        assert "standings not read" in capsys.readouterr().out

    def test_a_truncated_file_falls_back_to_the_last_good_one(self, env):
        _, raw = env
        period_file(raw, 2026, 5, READ, "100", "200")
        (raw / "fantrax_inseason_2026_p06.json").write_text('{"captured_at": "20', encoding="utf-8")
        assert run(raw).loc[(THIS, "A01"), "fantrax_salary_remaining"] == 100.0

    def test_a_second_run_is_byte_identical(self, env):
        data, raw = env
        period_file(raw, 2026, 6, READ, "100", "200")
        run(raw)
        first = (data / "fact_team_cap.parquet").read_bytes()
        run(raw)
        assert (data / "fact_team_cap.parquet").read_bytes() == first

    def test_the_table_matches_the_registry(self, env):
        _, raw = env
        run(raw)
        entry = etl_checks.load_registry()["fact_team_cap"]
        stored = etl_helpers.read_stored("fact_team_cap")
        assert etl_checks.schema_errors(entry, {c: str(d) for c, d in stored.dtypes.items()}) == []


def published(amount_a=213.0 + 7.0 - 32.0, amount_b=260.0, fantrax_at=READ):
    """The table with Fantrax's number; the defaults agree with ours on its
    basis: A01 is 300 - 70 - 32 - 10, B01 is 300 - 40."""
    newest = (Path("x"), {"captured_at": fantrax_at, "period": 6,
                          "standings": standings(str(amount_a), str(amount_b))})
    return ft.with_fantrax(cap.team_cap(ROSTER, DEAD, TEAMS, CONTRACTS, SEASONS),
                           ROSTER, newest, TEAMS)


class TestSalaryRemainingCheck:
    def test_agreement_on_fantraxs_basis_files_nothing(self):
        assert etl_checks.salary_remaining_findings(published(), ROSTER) == []

    def test_cap_room_alone_would_not_agree(self):
        # The IR add-back and the reinvestment charge are what separate the two.
        row = published().set_index(["season_id", "team_key"]).loc[(THIS, "A01")]
        assert row["cap_room"] != row["fantrax_salary_remaining"]

    def test_a_gap_over_a_dollar_names_team_period_and_both_numbers(self):
        got = etl_checks.salary_remaining_findings(published(amount_a=186.0), ROSTER)
        assert [k for k, _ in got] == [f"{THIS}|A01"]
        detail = got[0][1]
        for part in ("A01", "period 6", "186.00", "188.00", "2026-10-14"):
            assert part in detail

    def test_a_gap_of_a_dollar_or_less_files_nothing(self):
        assert etl_checks.salary_remaining_findings(published(amount_a=187.0), ROSTER) == []
        assert etl_checks.salary_remaining_findings(published(amount_a=189.0), ROSTER) == []

    def test_another_league_day_is_not_compared(self):
        table = published(amount_a=1.0, fantrax_at="2026-10-13T12:00:00+00:00")
        with pytest.raises(etl_checks.NotComparable):
            etl_checks.salary_remaining_findings(table, ROSTER)

    def test_the_day_is_the_leagues_not_utc(self):
        # 02:00 UTC on the 15th is still the 14th on the Eastern clock, as READ is.
        table = published(amount_a=1.0, fantrax_at="2026-10-15T02:00:00+00:00")
        assert len(etl_checks.salary_remaining_findings(table, ROSTER)) == 1

    def test_the_same_utc_day_can_be_another_league_day(self):
        # 03:00 UTC on the 14th is still the 13th on the Eastern clock.
        table = published(amount_a=1.0, fantrax_at="2026-10-14T03:00:00+00:00")
        with pytest.raises(etl_checks.NotComparable):
            etl_checks.salary_remaining_findings(table, ROSTER)

    def test_no_fantrax_number_is_not_compared(self):
        table = ft.with_fantrax(cap.team_cap(ROSTER, DEAD, TEAMS, CONTRACTS, SEASONS),
                                ROSTER, None, TEAMS)
        with pytest.raises(etl_checks.NotComparable):
            etl_checks.salary_remaining_findings(table, ROSTER)

    def test_a_replay_roster_is_not_compared(self):
        replay = ROSTER.assign(roster_captured_at=pd.NaT)
        table = ft.with_fantrax(cap.team_cap(replay, DEAD, TEAMS, CONTRACTS, SEASONS), replay,
                                (Path("x"), {"captured_at": READ, "period": 6,
                                             "standings": standings("1", "2")}), TEAMS)
        with pytest.raises(etl_checks.NotComparable):
            etl_checks.salary_remaining_findings(table, replay)

    def test_a_run_that_cannot_compare_keeps_open_findings_open(self, tmp_path):
        table = published(amount_a=1.0, fantrax_at="2026-10-13T12:00:00+00:00")
        for name, df in (("fact_team_cap", table), ("fact_fantasy_teams", ROSTER),
                         ("dim_fantasy_teams", TEAMS), ("fact_dead_money", DEAD),
                         ("dim_contract", CONTRACTS), ("dim_season", SEASONS)):
            df.to_parquet(tmp_path / f"{name}.parquet", index=False)
        results = etl_checks.run_suite(["fact_team_cap"], data_dir=tmp_path,
                                       head_rows=lambda _: None)
        res = next(r for r in results if r.check == "salary_remaining")
        assert res.ok and not res.ran
        findings, ran = etl_checks.review_findings(results)
        assert ("salary_remaining", "fact_team_cap") not in ran
        opened, _ = etl_checks.file_findings(
            pd.DataFrame(columns=etl_checks.FILING_COLUMNS),
            [{"check_name": "salary_remaining", "table_name": "fact_team_cap",
              "row_key": f"{THIS}|A01", "detail": "off"}],
            {("salary_remaining", "fact_team_cap")}, "r1", "t1")
        kept, stats = etl_checks.file_findings(opened, findings, ran, "r2", "t2")
        assert stats["cleared"] == 0
        assert etl_checks._is_open(kept).sum() == 1

    def test_it_is_registered_as_review(self):
        dc = next(d for d in etl_checks.DOMAIN_CHECKS if d.name == "salary_remaining")
        assert (dc.tier, dc.table) == ("review", "fact_team_cap")


class TestTeamCapGate:
    TEAMS_28 = pd.DataFrame({"team_key": [f"T{i:02d}" for i in range(28)],
                             "fantrax_team_id": [f"id{i}" for i in range(28)],
                             "conference": ["A"] * 14 + ["B"] * 14,
                             "original_cap": [300] * 28, "reinvestment_cap": [0] * 28})
    ROSTER_28 = roster(*[(f"T{i:02d}", "Active", "1st", 10.0) for i in range(28)])
    DEAD_28 = pd.DataFrame({"team_key": ["T00", "T00"], "season_id": [THIS, NEXT],
                            "dead_money": [10.0, 8.0]})

    def table(self):
        return ft.with_fantrax(cap.team_cap(self.ROSTER_28, self.DEAD_28, self.TEAMS_28,
                                            CONTRACTS, SEASONS),
                               self.ROSTER_28, None, self.TEAMS_28)

    def errors(self, t, r=None, dead=None):
        dead = self.DEAD_28 if dead is None else dead
        return etl_checks.team_cap_errors(t, self.ROSTER_28 if r is None else r, dead,
                                          self.TEAMS_28, CONTRACTS, SEASONS)

    def test_a_good_table_passes(self):
        assert self.errors(self.table()) == []

    def test_a_figure_off_fails(self):
        t = self.table()
        t.loc[0, "cap_room"] += 1.0
        assert any("cap_room" in e for e in self.errors(t))

    def test_a_roster_rebuilt_without_02h_fails(self):
        moved = self.ROSTER_28.assign(cap_hit=self.ROSTER_28["cap_hit"] + 1.0)
        assert any("charged_salary" in e for e in self.errors(self.table(), r=moved))

    def test_dead_money_rebuilt_without_02h_fails(self):
        more = pd.concat([self.DEAD_28, pd.DataFrame({"team_key": ["T01"], "season_id": [THIS],
                                                      "dead_money": [3.0]})])
        assert any("dead_money" in e for e in self.errors(self.table(), dead=more))

    def test_a_current_row_on_the_wrong_season_fails(self):
        t = self.table()
        t["is_current_season"] = ~t["is_current_season"]
        assert any("the roster's season" in e for e in self.errors(t))

    def test_a_missing_team_fails(self):
        t = self.table()
        assert any("27 teams" in e for e in self.errors(t[t["team_key"] != "T00"]))

    def test_a_table_with_one_season_fails(self):
        t = self.table()
        assert any("expected seasons" in e for e in self.errors(t[t["is_current_season"]]))

    def test_a_table_with_a_third_season_fails(self):
        t = self.table()
        extra = t[~t["is_current_season"]].assign(season_id=LATER)
        assert any("expected seasons" in e for e in self.errors(pd.concat([t, extra])))

    def test_dead_money_on_an_unknown_team_fails(self):
        orphan = pd.concat([self.DEAD_28, pd.DataFrame({"team_key": ["ZZZ"], "season_id": [THIS],
                                                        "dead_money": [3.0]})])
        assert any("outside dim_fantasy_teams" in e for e in self.errors(self.table(), dead=orphan))

    def test_it_is_registered_as_a_gate(self):
        dc = next(d for d in etl_checks.DOMAIN_CHECKS if d.name == "team_cap")
        assert (dc.tier, dc.table) == ("gate", "fact_team_cap")
