"""Per-step cadence in scripts/run_pipeline.py (#372, ADR-0020).

Mocks only: a made-up dim_scoring_period, a fake run-log record, no login, no
network, no database. Dates: 2026-09-10 is a Thursday; period 1 runs
09-10 to 09-17, period 2 to 09-24, period 3 (a playoff) to 10-01. A Close Day
is the day after a period ends: 09-18, 09-25, 10-02 (Fridays).
"""
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import etl_helpers  # noqa: E402
import etl_run_log as rl  # noqa: E402
import run_pipeline as rp  # noqa: E402

ROOKIE = ["03b_walterfootball", "03d_draftsharks_rookie"]
REJECTED = ["03a_fantasypros", "03c_ktc_rookie", "04b_ktc_dynasty", "04b_ktc_dynasty_p"]
THURSDAY = 3


def periods():
    rows = [("2026-2027", 1, "2026-09-10", "2026-09-17", False),
            ("2026-2027", 2, "2026-09-17", "2026-09-24", False),
            ("2026-2027", 3, "2026-09-24", "2026-10-01", True)]
    return pd.DataFrame(rows, columns=["season_id", "period", "start_date", "end_date", "is_playoff"]) \
        .astype({"start_date": "datetime64[ns]", "end_date": "datetime64[ns]"})


def plan(phase, today, record, cadence="due", only=None, groups=None, table=None):
    """What apply_cadence decides on `today`; `record` is the set steps_done
    returns for any week (None: the log cannot be read)."""
    state = rp.close_day_state(today, periods() if table is None else table, THURSDAY)
    asked = []

    def done_for(key):
        asked.append(key)
        return record
    kept, report = rp.apply_cadence(rp.build_steps(None), phase, only, groups,
                                    cadence, state, today, done_for)
    report["asked"] = asked
    return [s["name"] for s in kept if rp._selected(s, phase, only, groups)], report


class TestStepTable:
    STEPS = rp.build_steps(None)

    def test_close_day_steps_are_the_two_kept_rookie_scrapes(self):
        close = {s["name"] for s in self.STEPS if s["cadence"] == "close_day"}
        assert close == set(ROOKIE)

    def test_the_rejected_sites_are_in_no_step_in_any_profile(self):
        for profile in (None, "dynasty"):
            names = {s["name"] for s in rp.build_steps(profile)}
            assert not names & set(REJECTED), profile
        assert not rp.CLOSE_DAY_STEPS & set(REJECTED)

    @pytest.mark.parametrize("phase", ["INSEASON", "PRESEASON", "OFFSEASON"])
    @pytest.mark.parametrize("day", [date(2026, 9, 22), date(2026, 9, 25), date(2027, 2, 11)])
    @pytest.mark.parametrize("profile", [None, "dynasty"])
    def test_cadence_all_lists_none_of_the_rejected_steps(self, phase, day, profile):
        state = rp.close_day_state(day, periods(), THURSDAY)
        kept, report = rp.apply_cadence(rp.build_steps(profile), phase, None, None,
                                        "all", state, day, lambda key: set())
        listed = {s["name"] for s in kept if rp._selected(s, phase, None, None)}
        assert not listed & set(REJECTED)
        assert not set(report["ran"] + report["deferred"]) & set(REJECTED)

    def test_every_step_has_a_cadence_in_both_profiles(self):
        for profile in (None, "dynasty"):
            assert {s["cadence"] for s in rp.build_steps(profile)} == {"daily", "close_day"}

    def test_04s_is_a_daily_in_season_step(self):
        step = next(s for s in self.STEPS if s["name"] == "04s_scoring")
        assert (step["cadence"], step["phases"]) == ("daily", {"INSEASON"})

    def test_04t_runs_before_02d_which_needs_it(self):
        names = [s["name"] for s in self.STEPS]
        txn, ledger = (self.STEPS[names.index(n)] for n in ("04t_txn_history", "02d_ledger"))
        assert names.index("04t_txn_history") < names.index("02d_ledger")
        assert "04t_txn_history" in ledger["needs"]
        assert (txn["cadence"], txn["chain"]) == ("daily", "fantrax_core")
        assert txn["phases"] == {"INSEASON", "PRESEASON", "OFFSEASON"}
        assert txn["cmd"][-1].endswith("04t_fantrax_transaction_history.py")

    def test_04z_sees_the_same_run_transaction_capture(self):
        names = [s["name"] for s in self.STEPS]
        by_name = {s["name"]: s for s in self.STEPS}
        assert names.index("04a_scrape") < names.index("04t_txn_history") < names.index("04z_crosswalk")
        assert names.index("04z_crosswalk") < names.index("04v_minor_contracts") < names.index("02d_ledger")
        assert by_name["04t_txn_history"]["needs"] == ["04a_scrape"]
        assert by_name["04z_crosswalk"]["needs"] == ["04a_scrape", "04t_txn_history", "04a_backfill_gp"]
        assert by_name["04v_minor_contracts"]["needs"] == ["04z_crosswalk"]
        assert by_name["02d_ledger"]["needs"] == ["04v_minor_contracts", "04t_txn_history"]

    def test_04z_follows_the_gp_backfill_in_season_and_is_unchanged_elsewhere(self):
        def selected(phase):
            return [s["name"] for s in self.STEPS if rp._selected(s, phase, None, None)]
        inseason = selected("INSEASON")
        assert inseason.index("04a_backfill_gp") < inseason.index("04z_crosswalk")
        for phase in ("PRESEASON", "OFFSEASON"):
            names = selected(phase)
            assert "04a_backfill_gp" not in names
            assert names.index("04t_txn_history") < names.index("04z_crosswalk") < names.index("04v_minor_contracts")

    def test_04z_runs_in_off_phases_though_its_backfill_need_is_not_scheduled(self):
        steps = [s for s in self.STEPS if s["name"] in ("04a_scrape", "04t_txn_history", "04a_backfill_gp", "04z_crosswalk")]
        results = rp.run_steps(steps, "OFFSEASON", None, dry_run=True)
        assert [(r["name"], r["status"]) for r in results] == [
            ("04a_scrape", "dry-run"), ("04t_txn_history", "dry-run"), ("04z_crosswalk", "dry-run")]

    def test_a_failed_gp_backfill_skips_04z_in_season(self):
        steps = [s for s in self.STEPS if s["name"] in ("04a_backfill_gp", "04z_crosswalk")]
        steps = [{**s, "cmd": [sys.executable, "-c", "raise SystemExit(1)"], "needs": []} if s["name"] == "04a_backfill_gp"
                 else {**s, "needs": ["04a_backfill_gp"]} for s in steps]
        results = rp.run_steps(steps, "INSEASON", None, dry_run=False)
        assert [(r["name"], r["status"]) for r in results] == [
            ("04a_backfill_gp", "failed"), ("04z_crosswalk", "skipped")]

    @pytest.mark.parametrize("profile", [None, "dynasty"])
    def test_needs_are_acyclic_and_every_dependency_is_earlier(self, profile):
        steps = rp.build_steps(profile)
        position = {s["name"]: i for i, s in enumerate(steps)}
        assert len(position) == len(steps)
        for s in steps:
            for dep in s["needs"]:
                assert dep in position, f"{s['name']} needs {dep}, which is not a step"
                assert position[dep] < position[s["name"]], f"{s['name']} needs {dep}, which runs later"

    def test_a_failed_04t_skips_02d_and_holds_its_chain(self):
        steps = [s for s in self.STEPS if s["name"] in ("04t_txn_history", "02d_ledger")]
        steps[0] = {**steps[0], "cmd": [sys.executable, "-c", "raise SystemExit(1)"], "needs": []}
        results = rp.run_steps(steps, "OFFSEASON", None, dry_run=False)
        assert [(r["name"], r["status"]) for r in results] == [
            ("04t_txn_history", "failed"), ("02d_ledger", "skipped")]
        held = rp.plan_publish(self.STEPS, results, [], {"fantrax_core": ["t"]})
        assert held["failed"] == {"fantrax_core": ["step 04t_txn_history failed", "step 02d_ledger skipped"]}


def _day_by_day(table, weekday=THURSDAY):
    day = date(2026, 8, 1)
    while day <= date(2027, 3, 1):
        yield day, rp.close_day_state(day, table, weekday), etl_helpers.close_state(day, table, weekday)
        day += timedelta(days=1)


class TestCloseDay:
    """run_pipeline.close_day_state is etl_helpers.close_state in the shape
    apply_cadence reads; the week is defined there and nowhere else."""

    def test_a_day_inside_a_period_is_not_a_close_day(self):
        state = rp.close_day_state(date(2026, 9, 22), periods(), THURSDAY)
        assert (state["reason"], state["mode"], state["week_key"], state["close_day"]) == (
            "owed", "period", "2026-2027-p01", date(2026, 9, 18))

    def test_the_day_after_a_period_ends_is_its_close_day(self):
        state = rp.close_day_state(date(2026, 9, 25), periods(), THURSDAY)
        assert (state["week_key"], state["close_day"]) == ("2026-2027-p02", date(2026, 9, 25))

    def test_the_evening_a_period_ends_is_not_yet_its_close_day(self):
        state = rp.close_day_state(date(2026, 9, 17), periods(), THURSDAY)
        assert (state["week_key"], state["close_day"], state["reason"]) == (None, None, "not_yet")

    def test_before_the_first_close_day_no_week_is_owed(self):
        state = rp.close_day_state(date(2026, 9, 14), periods(), THURSDAY)
        assert (state["mode"], state["week_key"], state["reason"]) == (None, None, "not_yet")

    def test_a_playoff_period_has_a_close_day_too(self):
        state = rp.close_day_state(date(2026, 10, 2), periods(), THURSDAY)
        assert (state["week_key"], state["close_day"], state["is_playoff"]) == (
            "2026-2027-p03", date(2026, 10, 2), True)

    def test_off_season_it_is_the_config_weekday_and_the_iso_week(self):
        thursday = rp.close_day_state(date(2027, 2, 11), periods(), THURSDAY)
        assert (thursday["mode"], thursday["week_key"], thursday["close_day"]) == (
            "weekday", "2027-W06", date(2027, 2, 11))
        assert rp.close_day_state(date(2027, 2, 15), periods(), THURSDAY)["week_key"] == "2027-W06"
        assert rp.close_day_state(date(2027, 2, 18), periods(), THURSDAY)["week_key"] == "2027-W07"

    def test_the_weekday_comes_from_the_argument_not_from_the_code(self):
        state = rp.close_day_state(date(2027, 2, 11), periods(), 0)
        assert state["close_day"] == date(2027, 2, 8)

    def test_the_week_after_the_last_close_day_is_covered_by_its_run(self):
        state = rp.close_day_state(date(2026, 10, 3), periods(), THURSDAY)
        assert (state["week_key"], state["reason"]) == (None, "covered")

    def test_the_default_weekday_is_thursday(self):
        assert etl_helpers.CFG.close_day_weekday == THURSDAY == date(2026, 9, 10).weekday()
        assert rp.close_day_state(date(2027, 2, 11), periods())["close_day"] == date(2027, 2, 11)

    def test_it_matches_close_state_on_every_day(self):
        for day, got, owed in _day_by_day(periods()):
            week = owed.week
            assert got == {"week_key": week and week.key, "close_day": week and week.close_day,
                           "mode": week and week.mode, "is_playoff": bool(week and week.is_playoff),
                           "reason": owed.reason}, day

    def test_the_stored_table_is_read_when_none_is_given(self, monkeypatch):
        monkeypatch.setattr(etl_helpers, "stored_scoring_periods", periods)
        state = rp.close_day_state(date(2026, 9, 25))
        assert (state["reason"], state["week_key"]) == ("owed", "2026-2027-p02")

    def test_run_pipeline_holds_no_week_arithmetic_of_its_own(self):
        source = (REPO / "scripts" / "run_pipeline.py").read_text(encoding="utf-8")
        for needle in ("isocalendar", "ONE_DAY", "load_periods", "itertuples", "closed[-1]"):
            assert needle not in source, needle


class TestUnreadableCalendar:
    """No calendar, no week and no ISO guess: the daily steps run, the
    close_day steps are skipped and the summary warns."""

    @pytest.mark.parametrize("table", [None, periods().iloc[0:0]])
    def test_there_is_no_week_and_no_guess_on_any_day(self, table, monkeypatch):
        monkeypatch.setattr(etl_helpers, "stored_scoring_periods", lambda: None)
        for day in (date(2026, 9, 22), date(2026, 9, 25), date(2027, 2, 11), date(2027, 2, 14)):
            state = rp.close_day_state(day, table, THURSDAY)
            assert (state["week_key"], state["close_day"], state["reason"]) == (None, None, "unreadable"), day

    def test_the_daily_steps_run_and_the_close_day_steps_are_skipped(self):
        kept, report = plan("INSEASON", date(2026, 9, 25), set(), table=periods().iloc[0:0])
        assert not set(kept) & set(ROOKIE)
        assert {"04a_scrape", "04t_txn_history", "02d_ledger", "04s_scoring"} <= set(kept)
        assert (report["ran"], report["deferred"], report["reason"]) == ([], ROOKIE, "unreadable")
        assert report["asked"] == []

    def test_off_season_it_skips_the_same_steps(self):
        kept, report = plan("OFFSEASON", date(2027, 2, 11), set(), table=periods().iloc[0:0])
        assert "04b_ktc_dynasty" not in kept
        assert report["deferred"] == ROOKIE

    def test_cadence_all_skips_them_too_and_the_warning_stays(self):
        kept, report = plan("INSEASON", date(2026, 9, 25), set(), cadence="all", table=periods().iloc[0:0])
        assert not set(kept) & set(ROOKIE)
        assert (report["ran"], report["deferred"], report["filter"]) == ([], ROOKIE, "all")
        assert "04a_scrape" in kept and "04t_txn_history" in kept
        assert "close_day steps skipped" in rp.cadence_warning(report)

    def test_cadence_all_off_season_skips_them_too(self):
        kept, report = plan("OFFSEASON", date(2027, 2, 11), set(), cadence="all", table=periods().iloc[0:0])
        assert "04b_ktc_dynasty" not in kept and not set(kept) & set(ROOKIE)
        assert report["deferred"] == ROOKIE

    def test_cadence_all_on_a_quiet_day_with_a_readable_calendar_still_runs_them(self):
        _, report = plan("INSEASON", date(2026, 9, 14), set(), cadence="all")
        assert report["ran"] == ROOKIE and rp.cadence_warning(report) is None

    def test_the_warning_names_the_skipped_steps(self):
        _, report = plan("INSEASON", date(2026, 9, 25), set(), table=periods().iloc[0:0])
        warning = rp.cadence_warning(report)
        assert warning.startswith("⚠️ dim_scoring_period could not be read: close_day steps skipped")
        assert all(n in warning for n in ROOKIE)

    @pytest.mark.parametrize("reason_day", [date(2026, 9, 14), date(2026, 10, 3), date(2026, 9, 25)])
    def test_a_quiet_day_is_not_a_warning(self, reason_day):
        _, report = plan("INSEASON", reason_day, set(ROOKIE))
        assert rp.cadence_warning(report) is None

    def test_the_cadence_line_says_why_no_week(self):
        for day, text in ((date(2026, 9, 14), "no Close Day yet"),
                          (date(2026, 10, 3), "week covered by the last period's run")):
            _, report = plan("INSEASON", day, set(ROOKIE))
            assert text in rp.cadence_line(report)
        _, report = plan("INSEASON", date(2026, 9, 25), set(), table=periods().iloc[0:0])
        assert "calendar unreadable, no week" in rp.cadence_line(report)


class TestInSeason:
    def test_a_day_that_is_not_a_close_day_runs_no_close_day_step_and_04s_runs(self):
        kept, report = plan("INSEASON", date(2026, 9, 22), set(ROOKIE))
        assert not set(kept) & set(ROOKIE)
        assert "04s_scoring" in kept
        assert (report["ran"], report["deferred"]) == ([], ROOKIE)

    def test_a_close_day_runs_every_close_day_step(self):
        kept, report = plan("INSEASON", date(2026, 9, 25), set())
        assert [n for n in kept if n in ROOKIE] == ROOKIE
        assert report["ran"] == ROOKIE and report["deferred"] == []
        assert report["asked"] == ["2026-2027-p02"]

    def test_a_missed_close_day_is_caught_up_the_next_day(self):
        kept, report = plan("INSEASON", date(2026, 9, 26), set())
        assert report["ran"] == ROOKIE and [n for n in kept if n in ROOKIE] == ROOKIE

    def test_a_catch_up_runs_only_what_has_no_success_for_the_week(self):
        _, report = plan("INSEASON", date(2026, 9, 27), {"03b_walterfootball"})
        assert report["ran"] == ["03d_draftsharks_rookie"]
        assert report["deferred"] == ["03b_walterfootball"]

    def test_a_success_in_an_earlier_week_does_not_count(self):
        keys = []

        def done_for(key):
            keys.append(key)
            return set(ROOKIE) if key == "2026-2027-p01" else set()
        state = rp.close_day_state(date(2026, 9, 25), periods(), THURSDAY)
        _, report = rp.apply_cadence(rp.build_steps(None), "INSEASON", None, None, "due",
                                     state, date(2026, 9, 25), done_for)
        assert keys == ["2026-2027-p02"] and report["ran"] == ROOKIE

    def test_a_playoff_periods_close_day_runs_them(self):
        kept, report = plan("INSEASON", date(2026, 10, 2), set())
        assert report["ran"] == ROOKIE and report["week_key"] == "2026-2027-p03"
        assert report["is_playoff"] is True

    def test_with_no_record_to_read_only_the_close_day_itself_runs_them(self):
        _, on_the_day = plan("INSEASON", date(2026, 9, 25), None)
        _, next_day = plan("INSEASON", date(2026, 9, 26), None)
        assert on_the_day["ran"] == ROOKIE
        assert (next_day["ran"], next_day["deferred"]) == ([], ROOKIE)

    def test_before_the_first_close_day_nothing_is_owed_and_the_log_is_not_read(self):
        _, report = plan("INSEASON", date(2026, 9, 14), set())
        assert (report["ran"], report["deferred"], report["asked"]) == ([], ROOKIE, [])

    def test_04b_is_not_deferred_in_season_it_is_out_of_phase(self):
        _, report = plan("INSEASON", date(2026, 9, 22), set(ROOKIE))
        assert "04b_ktc_dynasty" not in report["ran"] + report["deferred"]


class TestOffSeason:
    THURSDAY_OFF = date(2027, 2, 11)

    def test_a_thursday_runs_the_rookie_scrapes_and_never_04s_or_04b(self):
        kept, report = plan("OFFSEASON", self.THURSDAY_OFF, set())
        assert "04b_ktc_dynasty" not in kept and "04s_scoring" not in kept
        assert report["ran"] == ROOKIE
        assert report["week_key"] == "2027-W06" and report["mode"] == "weekday"

    def test_another_weekday_with_the_week_done_runs_none(self):
        kept, report = plan("OFFSEASON", date(2027, 2, 13), set(ROOKIE))
        assert not set(kept) & set(ROOKIE)
        assert report["ran"] == []

    def test_a_missed_thursday_is_caught_up_on_a_later_day(self):
        _, report = plan("OFFSEASON", date(2027, 2, 14), {"03b_walterfootball"})
        assert report["ran"] == ["03d_draftsharks_rookie"] and report["deferred"] == ["03b_walterfootball"]


class TestOverrides:
    def test_cadence_all_runs_every_close_day_step_on_any_day(self):
        kept, report = plan("INSEASON", date(2026, 9, 22), set(ROOKIE), cadence="all")
        assert report["ran"] == ROOKIE and report["deferred"] == [] and report["filter"] == "all"
        assert report["asked"] == []
        every = {s["name"] for s in rp.build_steps(None) if "INSEASON" in s["phases"]}
        assert set(kept) == every

    def test_cadence_all_off_season_runs_the_rookie_scrapes(self):
        _, report = plan("OFFSEASON", date(2027, 2, 12), set(ROOKIE), cadence="all")
        assert report["ran"] == ROOKIE

    def test_steps_combine_with_the_cadence_by_and(self):
        kept, report = plan("INSEASON", date(2026, 9, 22), set(ROOKIE),
                            only={"03b_walterfootball", "04a_scrape"})
        assert kept == ["04a_scrape"] and report["deferred"] == ["03b_walterfootball"]
        _, due = plan("INSEASON", date(2026, 9, 25), set(), only={"03b_walterfootball", "04a_scrape"})
        assert due["ran"] == ["03b_walterfootball"] and due["deferred"] == []

    def test_group_combines_with_the_cadence_by_and(self):
        kept, report = plan("INSEASON", date(2026, 9, 25), set(), groups={"regular_season"})
        assert report["ran"] == [] and report["deferred"] == []
        assert not set(kept) & set(ROOKIE)
        kept, report = plan("INSEASON", date(2026, 9, 25), set(), groups={"rookie"})
        assert report["ran"] == ROOKIE

    def test_a_daily_step_is_never_dropped(self):
        every = [s["name"] for s in rp.build_steps(None) if s["cadence"] == "daily"]
        kept, _ = plan("INSEASON", date(2026, 9, 22), set(ROOKIE))
        assert [n for n in every if "INSEASON" in next(
            s["phases"] for s in rp.build_steps(None) if s["name"] == n)] == [
                n for n in kept if n in every]


class TestRecord:
    STEPS = rp.build_steps(None)
    REPORT = {"ran": ROOKIE}
    PASSED = {"passed": ["rookie", "fantrax_core"], "failed": {}}
    OK = [{"name": n, "status": "ok", "detail": ""} for n in ROOKIE]
    LANDED = "committed + merged 1 parquet file(s) via data PR #7"

    def done(self, results=None, plan_=None, line=None):
        return rp.close_steps_done(self.REPORT, self.OK if results is None else results,
                                   self.STEPS, self.PASSED if plan_ is None else plan_,
                                   self.LANDED if line is None else line)

    def test_ok_steps_of_a_passing_chain_in_a_landed_run_count(self):
        assert self.done() == ROOKIE
        assert self.done(line="no data changes — commit skipped") == ROOKIE
        assert self.done(line="committed 1 file(s), push skipped (--no-push)") == ROOKIE

    def test_a_failed_step_does_not_count(self):
        results = [{**r, "status": "failed"} if r["name"] == "03b_walterfootball" else r for r in self.OK]
        assert self.done(results) == [n for n in ROOKIE if n != "03b_walterfootball"]

    def test_a_held_chain_does_not_count(self):
        assert self.done(plan_={"passed": ["fantrax_core"], "failed": {"rookie": ["x"]}}) == []

    def test_a_withheld_chain_does_not_count(self):
        assert self.done(plan_={**self.PASSED, "unpublished": ["rookie"]}) == []

    @pytest.mark.parametrize("line", ["ABORTED: data PR #7 left open, merge refused",
                                      "commit skipped (flag)",
                                      "commit skipped: on branch 'x', not main"])
    def test_a_run_whose_data_did_not_land_counts_for_nothing(self, line):
        assert self.done(line=line) == []

    def test_a_step_that_did_not_run_for_the_cadence_does_not_count(self):
        results = self.OK + [{"name": "04a_scrape", "status": "ok", "detail": ""}]
        assert self.done(results) == ROOKIE

    def test_no_plan_no_record(self):
        assert rp.close_steps_done(self.REPORT, self.OK, self.STEPS, None, self.LANDED) == []


class TestStepsDone:
    def test_no_database_url_is_no_record(self, monkeypatch):
        monkeypatch.setattr(rl, "enabled", lambda: False)
        monkeypatch.setattr(rl, "_rows", lambda *a: pytest.fail("connected"))
        assert rl.steps_done("2026-2027-p01") is None

    def test_the_names_the_log_holds_come_back_as_a_set(self, monkeypatch):
        seen = []
        monkeypatch.setattr(rl, "enabled", lambda: True)
        monkeypatch.setattr(rl, "_rows", lambda sql, params: seen.append((sql, params)) or
                            [("03d_draftsharks_rookie",), ("03b_walterfootball",)])
        assert rl.steps_done("2026-2027-p01") == {"03d_draftsharks_rookie", "03b_walterfootball"}
        assert seen == [(rl.STEPS_DONE, ("2026-2027-p01",))]
        assert "status <> 'running'" in rl.STEPS_DONE

    def test_a_failed_read_is_no_record_and_never_raises(self, monkeypatch, capsys):
        def refused(sql, params):
            raise OSError("server closed the connection")
        monkeypatch.setattr(rl, "enabled", lambda: True)
        monkeypatch.setattr(rl, "_rows", refused)
        assert rl.steps_done("w") is None
        assert "[warn] close_day record not read: server closed the connection" in capsys.readouterr().out

    def test_finish_writes_the_cadence_as_json(self, monkeypatch):
        sent = []
        monkeypatch.setattr(rl, "_write", lambda sql, params: sent.append((sql, params)))
        log = rl.RunLog("daily")
        log.run_id = "r"
        log.finish("published", cadence={"filter": "due", "done": ["03d_draftsharks_rookie"]})
        sql, params = sent[0]
        assert "cadence = %s::jsonb" in sql
        assert params[-4] == '{"filter": "due", "done": ["03d_draftsharks_rookie"]}' and params[-1] == "r"
        assert params[-2] is None

    def test_finish_without_cadence_writes_null(self, monkeypatch):
        sent = []
        monkeypatch.setattr(rl, "_write", lambda sql, params: sent.append(params))
        log = rl.RunLog("daily")
        log.run_id = "r"
        log.finish("failed", error="x")
        assert sent[0][-2] is None


class TestMain:
    @pytest.fixture
    def run(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(rp, "_load_04a", lambda: SimpleNamespace(
            CFG=None, derive_week_label=lambda cfg: "03"))
        monkeypatch.setattr(rp, "derive_phase", lambda: "INSEASON")
        monkeypatch.setattr(etl_helpers, "stored_scoring_periods", periods)
        monkeypatch.setattr(rp, "review_counts", lambda: {})
        monkeypatch.setattr(rp, "OUT_DIR", tmp_path)
        monkeypatch.setattr(rp, "resolve_storage_env", lambda env_file=None: "parquet")
        monkeypatch.setattr(rl, "steps_done", lambda key: set())

        def go(today, *argv):
            monkeypatch.setattr(rp, "league_today", lambda: today)
            monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--dry-run", *argv])
            assert rp.main() == 0
            return capsys.readouterr().out
        return go

    def test_a_dry_run_on_a_close_day_lists_the_close_day_steps(self, run):
        out = run(date(2026, 9, 25))
        assert "[cadence] filter=due (week 2026-2027-p02, Close Day 2026-09-25)" in out
        assert all(f"[step] {n} " in out for n in ROOKIE)
        assert f"close_day ran: {', '.join(ROOKIE)}; deferred: none" in out

    def test_a_dry_run_on_another_day_names_what_it_deferred(self, run, monkeypatch):
        monkeypatch.setattr(rl, "steps_done", lambda key: set(ROOKIE))
        out = run(date(2026, 9, 22))
        assert not any(f"[step] {n} " in out for n in ROOKIE)
        assert "[step] 04s_scoring " in out
        assert f"close_day ran: none; deferred: {', '.join(ROOKIE)}" in out

    def test_cadence_all_lists_every_step(self, run, monkeypatch):
        monkeypatch.setattr(rl, "steps_done", lambda key: set(ROOKIE))
        out = run(date(2026, 9, 22), "--cadence", "all")
        assert "filter=all" in out
        every = [s["name"] for s in rp.build_steps(None) if "INSEASON" in s["phases"]]
        assert all(f"[step] {n} " in out for n in every)

    def test_the_summary_carries_the_cadence_line(self, run, tmp_path):
        run(date(2026, 9, 25))
        assert "🗓️ filter=due (week 2026-2027-p02" in (tmp_path / "pipeline_summary.md").read_text(encoding="utf-8")

    def test_an_unreadable_calendar_runs_the_daily_steps_skips_the_close_day_steps_and_warns(
            self, run, monkeypatch, tmp_path):
        monkeypatch.setattr(etl_helpers, "stored_scoring_periods", lambda: None)
        monkeypatch.setattr(rl, "steps_done", lambda key: pytest.fail("a week was guessed"))
        out = run(date(2026, 9, 25))
        assert not any(f"[step] {n} " in out for n in ROOKIE)
        assert all(f"[step] {n} " in out for n in ("04a_scrape", "04t_txn_history", "02d_ledger", "04s_scoring"))
        assert "calendar unreadable, no week" in out
        warning = ("⚠️ dim_scoring_period could not be read: close_day steps skipped "
                   f"({', '.join(ROOKIE)}); they run once the calendar reads")
        assert warning in (tmp_path / "pipeline_summary.md").read_text(encoding="utf-8").splitlines()

    def test_cadence_all_with_an_unreadable_calendar_skips_the_close_day_steps_and_warns(
            self, run, monkeypatch, tmp_path):
        monkeypatch.setattr(etl_helpers, "stored_scoring_periods", lambda: None)
        monkeypatch.setattr(rl, "steps_done", lambda key: pytest.fail("a week was guessed"))
        out = run(date(2026, 9, 25), "--cadence", "all")
        assert "filter=all" in out
        assert not any(f"[step] {n} " in out for n in ROOKIE)
        assert all(f"[step] {n} " in out for n in ("04a_scrape", "04t_txn_history", "02d_ledger", "04s_scoring"))
        warning = ("⚠️ dim_scoring_period could not be read: close_day steps skipped "
                   f"({', '.join(ROOKIE)}); they run once the calendar reads")
        assert warning in (tmp_path / "pipeline_summary.md").read_text(encoding="utf-8").splitlines()

    def test_a_bad_cadence_is_refused(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--cadence", "weekly"])
        with pytest.raises(SystemExit) as stopped:
            rp.main()
        assert stopped.value.code == 2
