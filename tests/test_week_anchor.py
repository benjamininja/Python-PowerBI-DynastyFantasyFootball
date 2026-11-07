"""The week anchor and the Scoring Period week label (#378, ADR-0020 decisions
4, 7 and 8).

Fixtures only: a made-up dim_scoring_period of 17 periods that turn over on a
Thursday at 20:15 Eastern, and a throwaway parquet file for the slice cases. No
table in data/ is read, no login, no network.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import etl_helpers as etl  # noqa: E402
import run_pipeline as rp  # noqa: E402

ET = "America/New_York"
FIRST_TURNOVER = pd.Timestamp("2026-09-10 20:15")


def make_periods(n: int = 17) -> pd.DataFrame:
    """Period k runs from a Thursday 20:15 Eastern to the next one."""
    starts = [(FIRST_TURNOVER + pd.Timedelta(days=7 * i)).tz_localize(ET) for i in range(n + 1)]
    rows = []
    for i in range(n):
        rows.append({
            "season_id": "2026-2027", "period": i + 1,
            "start_date": pd.Timestamp(starts[i].date()), "end_date": pd.Timestamp(starts[i + 1].date()),
            "start_at": starts[i].tz_convert("UTC"), "end_at": starts[i + 1].tz_convert("UTC"),
            "is_playoff": i + 1 > 14,
        })
    return pd.DataFrame(rows)


PERIODS = make_periods()


def at(text: str) -> pd.Timestamp:
    """A wall-clock time on the league's Eastern clock."""
    return pd.Timestamp(text).tz_localize(ET)


@pytest.fixture
def stored_periods(monkeypatch):
    """read_table serves the fixture periods; any other table is not there."""
    def fake(name, columns=None):
        if name == "dim_scoring_period":
            return PERIODS.copy()
        raise etl.TableNotFound(f"{name}: not in the fixture")
    monkeypatch.setattr(etl, "read_table", fake)


@pytest.fixture
def no_tables(monkeypatch):
    def fake(name, columns=None):
        raise etl.TableNotFound(f"{name}: not in the fixture")
    monkeypatch.setattr(etl, "read_table", fake)


class TestAnchorInSeason:
    def test_midweek_day_anchors_to_the_end_of_its_period(self):
        assert etl.week_anchor(date(2026, 9, 16), PERIODS) == date(2026, 9, 17)
        assert etl.week_anchor(date(2026, 9, 14), PERIODS) == date(2026, 9, 17)

    def test_turnover_thursday_belongs_to_the_period_ending(self):
        assert etl.week_anchor(date(2026, 9, 17), PERIODS) == date(2026, 9, 17)

    def test_friday_after_the_turnover_is_the_next_period(self):
        assert etl.week_anchor(date(2026, 9, 18), PERIODS) == date(2026, 9, 24)

    def test_wednesday_thursday_friday_across_a_boundary(self):
        got = [etl.week_anchor(date(2026, 9, d), PERIODS) for d in (16, 17, 18)]
        assert got == [date(2026, 9, 17), date(2026, 9, 17), date(2026, 9, 24)]

    def test_eastern_instants_around_the_turnover(self):
        before = etl.week_anchor(at("2026-09-17 19:00"), PERIODS)
        after = etl.week_anchor(at("2026-09-17 21:00"), PERIODS)
        assert (before, after) == (date(2026, 9, 17), date(2026, 9, 24))

    def test_the_instant_is_placed_by_exact_bounds_not_the_utc_date(self):
        late_wednesday = at("2026-09-16 23:30")
        assert late_wednesday.tz_convert("UTC").date() == date(2026, 9, 17)
        assert etl.week_anchor(late_wednesday, PERIODS) == date(2026, 9, 17)
        thursday_night = at("2026-09-17 21:00")
        assert thursday_night.tz_convert("UTC").date() == date(2026, 9, 18)
        assert etl.week_anchor(thursday_night, PERIODS) == date(2026, 9, 24)

    def test_the_turnover_instant_starts_the_new_period(self):
        turnover = at("2026-09-17 20:15")
        assert etl.week_anchor(turnover - pd.Timedelta(seconds=1), PERIODS) == date(2026, 9, 17)
        assert etl.week_anchor(turnover, PERIODS) == date(2026, 9, 24)

    def test_first_and_last_day_of_the_season(self):
        assert etl.week_anchor(date(2026, 9, 10), PERIODS) == date(2026, 9, 17)
        assert etl.week_anchor(date(2027, 1, 7), PERIODS) == date(2027, 1, 7)

    def test_a_dst_change_inside_the_season_moves_nothing(self):
        assert etl.week_anchor(at("2026-10-29 21:00"), PERIODS) == date(2026, 11, 5)
        assert etl.week_anchor(at("2026-11-04 12:00"), PERIODS) == date(2026, 11, 5)


class TestAnchorOffSeason:
    @pytest.mark.parametrize("day, sunday", [
        (date(2027, 2, 10), date(2027, 2, 14)),
        (date(2027, 2, 14), date(2027, 2, 14)),
        (date(2027, 2, 15), date(2027, 2, 21)),
        (date(2026, 8, 12), date(2026, 8, 16)),
        (date(2027, 1, 8), date(2027, 1, 10)),
    ])
    def test_the_iso_weeks_sunday(self, day, sunday):
        assert etl.week_anchor(day, PERIODS) == sunday

    def test_sunday_evening_eastern_is_still_that_sunday(self):
        late_sunday = at("2027-02-14 22:00")
        assert late_sunday.tz_convert("UTC").date() == date(2027, 2, 15)
        assert etl.week_anchor(late_sunday, PERIODS) == date(2027, 2, 14)

    def test_no_table_places_no_period(self, no_tables):
        assert etl.scoring_period_on(date(2026, 9, 16)) is None

    def test_the_anchor_is_always_a_sunday_off_season(self):
        day = date(2027, 1, 8)
        for i in range(60):
            assert etl.week_anchor(day + timedelta(days=i), PERIODS).weekday() == 6

    def test_the_stored_table_is_read_when_none_is_given(self, stored_periods):
        assert etl.week_anchor(date(2026, 9, 16)) == date(2026, 9, 17)
        assert etl.week_anchor() is not None


THURSDAY = 3
NO_PERIODS = PERIODS.iloc[0:0]
SHORT = PERIODS.iloc[:1]


class TestWeek:
    def test_an_in_season_week_has_a_key_an_anchor_and_a_close_day(self):
        week = etl.week_of(date(2026, 9, 16), PERIODS)
        assert week == etl.Week("2026-2027-p01", date(2026, 9, 17), date(2026, 9, 18), "period", False)

    def test_the_key_zero_pads_the_period(self):
        assert etl.week_of(date(2026, 11, 4), PERIODS).key == "2026-2027-p08"

    def test_a_playoff_period_is_a_week_too(self):
        week = etl.week_of(date(2026, 12, 20), PERIODS)
        assert week == etl.Week("2026-2027-p15", date(2026, 12, 24), date(2026, 12, 25), "period", True)

    def test_the_close_day_is_the_day_after_the_period_ends(self):
        week = etl.week_of(date(2026, 9, 17), PERIODS)
        assert week.close_day == week.anchor + timedelta(days=1)
        assert week.close_day.weekday() == 4

    def test_an_off_season_week_is_the_iso_week(self):
        week = etl.week_of(date(2027, 2, 10), PERIODS)
        assert week == etl.Week("2027-W06", date(2027, 2, 14), date(2027, 2, 11), "weekday", False)

    def test_the_off_season_close_day_follows_the_configured_weekday(self):
        week = etl.week_of(date(2027, 2, 10), PERIODS, close_day_weekday=0)
        assert (week.key, week.close_day) == ("2027-W06", date(2027, 2, 8))

    def test_the_default_weekday_is_the_configs_thursday(self):
        assert etl.CFG.close_day_weekday == THURSDAY
        assert etl.week_of(date(2027, 2, 10), PERIODS).close_day.weekday() == THURSDAY

    @pytest.mark.parametrize("day, key, anchor", [
        (date(2026, 12, 31), "2026-W53", date(2027, 1, 3)),
        (date(2027, 1, 1), "2026-W53", date(2027, 1, 3)),
        (date(2027, 1, 4), "2027-W01", date(2027, 1, 10)),
    ])
    def test_the_iso_year_comes_from_the_iso_week(self, day, key, anchor):
        week = etl.week_of(day, SHORT)
        assert (week.key, week.anchor, week.mode) == (key, anchor, "weekday")

    def test_the_anchor_is_week_anchor(self):
        day = date(2026, 9, 16)
        assert etl.week_anchor(day, PERIODS) == etl.week_of(day, PERIODS).anchor
        assert etl.week_anchor(date(2027, 2, 10), PERIODS) == etl.week_of(date(2027, 2, 10), PERIODS).anchor

    def test_no_table_is_no_week(self, no_tables):
        assert etl.week_of(date(2026, 9, 16)) is None

    def test_the_week_is_read_from_the_stored_table(self, stored_periods):
        assert etl.week_of(date(2026, 9, 16)).key == "2026-2027-p01"
        assert etl.closed_week(date(2026, 9, 25)).key == "2026-2027-p02"


class TestClosedWeek:
    def test_inside_a_period_it_is_the_last_period_to_have_closed(self):
        week = etl.closed_week(date(2026, 9, 22), PERIODS)
        assert (week.key, week.close_day) == ("2026-2027-p01", date(2026, 9, 18))

    def test_the_day_after_a_period_ends_it_is_that_period(self):
        week = etl.closed_week(date(2026, 9, 25), PERIODS)
        assert (week.key, week.close_day) == ("2026-2027-p02", date(2026, 9, 25))

    def test_the_day_a_period_ends_it_is_not_closed_yet(self):
        assert etl.closed_week(date(2026, 9, 17), PERIODS) is None
        assert etl.closed_week(date(2026, 9, 12), PERIODS) is None

    def test_a_playoff_period_closes_too(self):
        week = etl.closed_week(date(2026, 12, 26), PERIODS)
        assert (week.key, week.is_playoff) == ("2026-2027-p15", True)

    def test_the_last_period_closes_the_day_after_it_ends(self):
        assert etl.closed_week(date(2027, 1, 8), PERIODS).key == "2026-2027-p17"

    def test_off_season_it_is_the_iso_week_of_the_latest_close_day(self):
        assert etl.closed_week(date(2027, 2, 11), PERIODS).key == "2027-W06"
        assert etl.closed_week(date(2027, 2, 15), PERIODS).key == "2027-W06"
        assert etl.closed_week(date(2027, 2, 18), PERIODS).key == "2027-W07"

    def test_before_the_calendar_the_weekday_week_is_owed_with_no_cover_rule(self):
        got = etl.close_state(date(2026, 8, 13), PERIODS, THURSDAY)
        assert (got.reason, got.week.key, got.week.close_day) == ("owed", "2026-W33", date(2026, 8, 13))
        assert etl.close_state(date(2026, 9, 3), PERIODS, THURSDAY).reason == "owed"


class TestSeasonEndHandover:
    """The last period's Close Day is 2027-01-08, so 2027-W01 (Close Day
    2027-01-07) is covered by its run (owner, 2026-11-06)."""

    def test_the_last_periods_close_day_runs_it(self):
        got = etl.close_state(date(2027, 1, 8), PERIODS, THURSDAY)
        assert (got.reason, got.week.key, got.week.close_day) == ("owed", "2026-2027-p17", date(2027, 1, 8))

    @pytest.mark.parametrize("day", [date(2027, 1, 9), date(2027, 1, 10), date(2027, 1, 11),
                                     date(2027, 1, 12), date(2027, 1, 13)])
    def test_the_days_after_it_owe_no_close_day_step(self, day):
        got = etl.close_state(day, PERIODS, THURSDAY)
        assert (got.week, got.reason) == (None, "covered")
        assert etl.closed_week(day, PERIODS, THURSDAY) is None

    def test_the_first_off_season_close_day_is_the_following_thursday(self):
        got = etl.close_state(date(2027, 1, 14), PERIODS, THURSDAY)
        assert (got.reason, got.week.key, got.week.close_day, got.week.mode) == (
            "owed", "2027-W02", date(2027, 1, 14), "weekday")
        assert etl.close_state(date(2027, 1, 15), PERIODS, THURSDAY).week.key == "2027-W02"

    def test_a_week_whose_close_day_is_after_the_last_close_day_is_not_covered(self):
        got = etl.close_state(date(2027, 1, 21), PERIODS, THURSDAY)
        assert (got.reason, got.week.key, got.week.close_day) == ("owed", "2027-W03", date(2027, 1, 21))
        assert etl.close_state(date(2027, 1, 20), PERIODS, THURSDAY).week.key == "2027-W02"

    def test_the_cover_follows_the_configured_weekday(self):
        monday = etl.close_state(date(2027, 1, 11), PERIODS, 0)
        assert (monday.reason, monday.week.key, monday.week.close_day) == ("owed", "2027-W02", date(2027, 1, 11))
        assert etl.close_state(date(2027, 1, 10), PERIODS, 0).reason == "covered"

    def test_a_short_calendar_is_covered_the_same_way(self):
        assert etl.close_state(date(2026, 9, 19), SHORT, THURSDAY).reason == "covered"
        assert etl.close_state(date(2026, 9, 25), SHORT, THURSDAY).week.key == "2026-W39"


class TestUnreadableCalendar:
    """dim_scoring_period cannot be read: no week and no ISO guess (owner,
    2026-11-06). The caller runs its daily steps, skips close_day steps and
    warns in its summary; catch-up runs them once the calendar reads."""

    def test_a_missing_table_is_no_week_with_a_reason_and_a_warning(self, no_tables, capsys):
        got = etl.close_state(date(2026, 9, 22), None, THURSDAY)
        assert (got.week, got.reason) == (None, "unreadable")
        assert "[warn] dim_scoring_period not read (TableNotFound)" in capsys.readouterr().out

    def test_a_read_error_is_unreadable_too(self, monkeypatch, capsys):
        def broken(name, columns=None):
            raise OSError("disk read failed")
        monkeypatch.setattr(etl, "read_table", broken)
        assert etl.close_state(date(2026, 9, 22), None, THURSDAY) == etl.Owed(None, "unreadable")
        assert "[warn] dim_scoring_period not read (OSError): disk read failed" in capsys.readouterr().out

    def test_an_empty_calendar_is_unreadable(self):
        assert etl.close_state(date(2026, 9, 22), NO_PERIODS, THURSDAY) == etl.Owed(None, "unreadable")

    def test_it_never_guesses_an_iso_key_on_any_day(self, no_tables):
        day = date(2026, 8, 1)
        while day <= date(2027, 3, 1):
            assert etl.close_state(day, None, THURSDAY).week is None, day
            assert etl.week_of(day) is None, day
            day += timedelta(days=1)

    def test_the_stored_table_is_read_once_per_call(self, stored_periods):
        assert etl.close_state(date(2026, 9, 25)).reason == "owed"

    def test_a_snapshot_is_never_keyed_on_a_guess(self, no_tables):
        with pytest.raises(etl.CalendarUnreadable):
            etl.week_anchor(date(2026, 9, 22))
        with pytest.raises(etl.CalendarUnreadable):
            etl.week_anchor(date(2026, 9, 22), NO_PERIODS)

    def test_a_week_closes_into_itself_on_its_close_day(self):
        day = date(2026, 9, 10)
        while day <= date(2027, 3, 1):
            week = etl.week_of(day, PERIODS)
            if week.mode == "weekday" and day <= date(2027, 1, 10):
                day += timedelta(days=1)
                continue
            assert etl.closed_week(week.close_day, PERIODS).key == week.key, day
            day += timedelta(days=1)


ENTRY = {
    "name": "fixture_snapshot", "grain": "(snapshot_date, source_name, player)",
    "columns": [{"name": "snapshot_date", "dtype": "datetime64[us]", "sql_type": "timestamp"},
                {"name": "source_name", "dtype": "str", "sql_type": "text"},
                {"name": "player", "dtype": "str", "sql_type": "text"},
                {"name": "value", "dtype": "float64", "sql_type": "double precision"}],
}


def run(path, day, value, source="KTC"):
    """One daily run of a snapshot_date table: the anchor, then replace_partition."""
    frame = pd.DataFrame({
        "snapshot_date": pd.Timestamp(etl.week_anchor(day, PERIODS)),
        "source_name": source, "player": ["a", "b"], "value": [value, value + 1.0]})
    etl._write_parquet(path, frame, "replace_partition", ("snapshot_date", "source_name"), None, ENTRY)
    return pd.read_parquet(path)


class TestSlices:
    def test_two_runs_in_one_week_write_one_slice(self, tmp_path):
        path = tmp_path / "t.parquet"
        run(path, date(2026, 9, 14), 1.0)
        out = run(path, date(2026, 9, 16), 2.0)
        assert out["snapshot_date"].nunique() == 1
        assert len(out) == 2
        assert out["value"].tolist() == [2.0, 3.0]

    def test_a_run_after_the_period_ends_starts_a_new_slice(self, tmp_path):
        path = tmp_path / "t.parquet"
        run(path, date(2026, 9, 16), 1.0)
        out = run(path, date(2026, 9, 18), 5.0)
        assert list(pd.to_datetime(sorted(out["snapshot_date"].unique()))) == [
            pd.Timestamp("2026-09-17"), pd.Timestamp("2026-09-24")]
        old = out[out["snapshot_date"] == pd.Timestamp("2026-09-17")]
        assert old["value"].tolist() == [1.0, 2.0]

    def test_a_thursday_night_run_starts_the_new_slice(self, tmp_path):
        path = tmp_path / "t.parquet"
        run(path, at("2026-09-17 06:00"), 1.0)
        out = run(path, at("2026-09-17 21:00"), 9.0)
        assert out["snapshot_date"].nunique() == 2

    def test_another_source_in_the_same_week_is_kept(self, tmp_path):
        path = tmp_path / "t.parquet"
        run(path, date(2026, 9, 14), 1.0, source="KTC")
        out = run(path, date(2026, 9, 16), 7.0, source="DynastySharks")
        assert sorted(out["source_name"]) == ["DynastySharks", "DynastySharks", "KTC", "KTC"]
        assert out["snapshot_date"].nunique() == 1

    def test_off_season_runs_in_one_iso_week_share_a_slice(self, tmp_path):
        path = tmp_path / "t.parquet"
        run(path, date(2027, 2, 8), 1.0)
        out = run(path, date(2027, 2, 12), 2.0)
        assert out["snapshot_date"].nunique() == 1
        out = run(path, date(2027, 2, 16), 3.0)
        assert out["snapshot_date"].nunique() == 2


def code_of(notebook: str) -> str:
    import json
    cells = json.loads((REPO / "notebooks" / notebook).read_text(encoding="utf-8"))["cells"]
    return "\n".join("".join(c["source"]) for c in cells if c["cell_type"] == "code")


class TestNotebooksWriteTheAnchor:
    @pytest.mark.parametrize("notebook", [
        "04b_ktc_dynasty_rankings.ipynb", "04d_draftpick_value_curve.ipynb",
        "04e_dim_position_ceiling.ipynb", "04f_draftsharks_two_tree.ipynb",
        "04x_manual_dynasty_rankings.ipynb"])
    def test_snapshot_date_comes_from_the_anchor(self, notebook):
        code = code_of(notebook)
        assert "etl.week_anchor()" in code
        for line in code.splitlines():
            if "snapshot_date" in line and "=" in line and "etl.week_anchor" not in line:
                assert "TODAY" not in line and "date.today" not in line, line
        assert "SNAPSHOT_DATE = date.today" not in code
        assert "pd.Timestamp(etl.TODAY)" not in code

    @pytest.mark.parametrize("notebook", [
        "04b_ktc_dynasty_rankings.ipynb", "04d_draftpick_value_curve.ipynb"])
    def test_raw_captures_keep_the_run_date(self, notebook):
        code = code_of(notebook)
        assert "{RUN_DATE}.json" in code
        assert "{SNAPSHOT_DATE}.json" not in code

    def test_the_composite_follows_the_dates_it_reads(self):
        code = code_of("04y_composite_dynasty_metrics.ipynb")
        assert "date.today" not in code and "etl.TODAY" not in code
        assert 'groupby(["snapshot_date", "format", "gsis_id"])' in code


S1, S2, S3 = (pd.Timestamp(d).as_unit("us") for d in ("2026-09-17", "2026-09-24", "2026-10-01"))
FACT = "fact_dynasty_ranking_metrics"
COMPOSITE_CELLS = ("8c565462", "e468dc6d", "e2cad8c9", "9e5c69c0")


def notebook_cell(notebook: str, cell_id: str) -> str:
    import json
    cells = json.loads((REPO / "notebooks" / notebook).read_text(encoding="utf-8"))["cells"]
    return "".join(next(c for c in cells if c.get("id") == cell_id)["source"])


def fixture_fact() -> pd.DataFrame:
    """Three weeks of KTC and DynastySharks ADP, and a Composite slice (77.0
    everywhere, a value the notebook never computes) for the first two."""
    rows = []

    def add(snap, source, key, pid, gsis, num):
        rows.append({"snapshot_date": snap, "source_name": source, "source_player_id": pid,
                     "format": "SF", "source_uid": f"{source}|{pid}", "gsis_id": gsis,
                     "metric_key": key, "metric_num": num, "metric_text": None})
    for snap in (S1, S2, S3):
        for pid, gsis, ktc, ds in (("1", "g1", 1.0, 1.05), ("2", "g2", 2.0, 2.05), ("3", "g3", 3.0, 3.05)):
            add(snap, "KTC", "ktc_adp", pid, gsis, ktc)
            add(snap, "DynastySharks", "ds_adp", pid, gsis, ds)
    for snap in (S1, S2):
        for gsis in ("g1", "g2", "g3"):
            for key in ("composite_adp", "sources_count"):
                add(snap, "Composite", key, gsis, gsis, 77.0)
    frame = pd.DataFrame(rows)
    frame["snapshot_date"] = frame["snapshot_date"].astype("datetime64[us]")
    return frame


class CompositeStore:
    """fact_dynasty_ranking_metrics in a throwaway parquet file, read and
    written through the seam's own parquet writer."""

    def __init__(self, tmp_path, monkeypatch, anchor):
        self.path = tmp_path / "fact.parquet"
        self.entry = etl._table_entry(FACT)
        etl._write_parquet(self.path, fixture_fact(), "replace", None, None, self.entry)
        monkeypatch.setattr(etl, "read_table", lambda name, columns=None: pd.read_parquet(self.path))
        monkeypatch.setattr(etl, "write_table", self.write)
        monkeypatch.setattr(etl, "week_anchor", lambda *a, **k: anchor)

    def write(self, name, df, *, mode="replace", keys=None, partition=None):
        assert name == FACT
        return len(etl._write_parquet(self.path, df, mode, keys, partition, self.entry))

    def rows(self, source=None, before=None):
        out = pd.read_parquet(self.path)
        if source:
            out = out[out["source_name"] == source]
        if before is not None:
            out = out[out["snapshot_date"] < before]
        return out.sort_values(etl.table_grain(self.entry)).reset_index(drop=True)

    def run(self):
        ns = {"__name__": "composite_nb"}
        for cell_id in COMPOSITE_CELLS:
            exec(compile(notebook_cell("04y_composite_dynasty_metrics.ipynb", cell_id), cell_id, "exec"), ns)
        return ns


def parquet_bytes(frame: pd.DataFrame) -> bytes:
    import io
    buf = io.BytesIO()
    frame.to_parquet(buf, index=False)
    return buf.getvalue()


class TestCompositeFreezesPastWeeks:
    def test_a_run_leaves_earlier_snapshots_byte_identical(self, tmp_path, monkeypatch):
        monkeypatch.delenv("COMPOSITE_REBUILD_HISTORY", raising=False)
        store = CompositeStore(tmp_path, monkeypatch, date(2026, 10, 1))
        before = store.rows(before=S3)
        store.run()
        after = store.rows(before=S3)
        pd.testing.assert_frame_equal(before, after)
        assert parquet_bytes(before) == parquet_bytes(after)
        assert set(after[after["source_name"] == "Composite"]["metric_num"]) == {77.0}

    def test_the_current_week_gets_its_composite_slice(self, tmp_path, monkeypatch):
        monkeypatch.delenv("COMPOSITE_REBUILD_HISTORY", raising=False)
        store = CompositeStore(tmp_path, monkeypatch, date(2026, 10, 1))
        store.run()
        current = store.rows(source="Composite")
        current = current[current["snapshot_date"] == S3]
        assert len(current) == 6
        ranks = current[current["metric_key"] == "composite_adp"].set_index("gsis_id")["metric_num"]
        assert sorted(ranks) == [1.0, 2.0, 3.0]

    def test_a_second_run_in_the_week_rewrites_only_that_slice(self, tmp_path, monkeypatch):
        monkeypatch.delenv("COMPOSITE_REBUILD_HISTORY", raising=False)
        store = CompositeStore(tmp_path, monkeypatch, date(2026, 10, 1))
        store.run()
        once = store.rows()
        store.run()
        pd.testing.assert_frame_equal(once, store.rows())

    def test_rebuilding_history_is_opt_in(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COMPOSITE_REBUILD_HISTORY", "1")
        store = CompositeStore(tmp_path, monkeypatch, date(2026, 10, 1))
        store.run()
        past = store.rows(source="Composite", before=S3)
        assert 77.0 not in set(past["metric_num"])
        assert set(past["snapshot_date"]) == {S1, S2}

    def test_off_by_default(self, tmp_path, monkeypatch):
        monkeypatch.delenv("COMPOSITE_REBUILD_HISTORY", raising=False)
        store = CompositeStore(tmp_path, monkeypatch, date(2026, 10, 1))
        assert store.run()["REBUILD_HISTORY"] is False

    def test_a_week_with_no_adp_rows_fails_loudly_and_writes_nothing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("COMPOSITE_REBUILD_HISTORY", raising=False)
        store = CompositeStore(tmp_path, monkeypatch, date(2026, 10, 8))
        before = store.rows()
        with pytest.raises(RuntimeError, match="no ADP rows at the current week's snapshot_date 2026-10-08"):
            store.run()
        pd.testing.assert_frame_equal(before, store.rows())


def load_04a():
    return rp._load_04a()


def old_label(cfg, run_dt):
    """derive_week_label as it was before #378: the Monday turnover."""
    week1_monday = date.fromisoformat(cfg.week1_thursday) + timedelta(days=4)
    if run_dt < week1_monday:
        return cfg.preseason_label
    weeks = (run_dt - week1_monday).days // 7 + 1
    return f"{max(1, min(18, weeks)):02d}"


class TestWeekLabel:
    def test_before_the_first_monday_is_pre(self, stored_periods):
        fx = load_04a()
        assert fx.derive_week_label(fx.CFG, date(2026, 9, 13)) == "PRE"
        assert fx.derive_week_label(fx.CFG, date(2026, 8, 1)) == "PRE"

    def test_in_season_it_is_the_scoring_period(self, stored_periods):
        fx = load_04a()
        got = [fx.derive_week_label(fx.CFG, date(2026, 9, d)) for d in (14, 16, 17, 18, 24, 25)]
        assert got == ["01", "01", "01", "02", "02", "03"]

    def test_it_departs_from_the_monday_turnover_on_thursday_to_monday(self, stored_periods):
        fx = load_04a()
        friday = date(2026, 9, 18)
        assert old_label(fx.CFG, friday) == "01"
        assert fx.derive_week_label(fx.CFG, friday) == "02"

    def test_the_playoff_periods_are_labelled_too(self, stored_periods):
        fx = load_04a()
        assert fx.derive_week_label(fx.CFG, date(2027, 1, 5)) == "17"

    def test_the_override_still_wins(self, stored_periods, monkeypatch):
        fx = load_04a()
        monkeypatch.setattr(fx.CFG, "snapshot_week", 4)
        assert fx.derive_week_label(fx.CFG, date(2026, 9, 18)) == "04"
        monkeypatch.setattr(fx.CFG, "snapshot_week", "YTD")
        assert fx.derive_week_label(fx.CFG, date(2026, 9, 18)) == "YTD"
        monkeypatch.setattr(fx.CFG, "snapshot_week", "PRE")
        assert fx.derive_week_label(fx.CFG, date(2026, 9, 18)) == "PRE"

    def test_with_no_period_table_it_falls_back_to_the_monday_count(self, no_tables):
        fx = load_04a()
        for day in (date(2026, 9, 14), date(2026, 9, 18), date(2026, 12, 20), date(2027, 3, 1)):
            assert fx.derive_week_label(fx.CFG, day) == old_label(fx.CFG, day)

    def test_after_the_last_period_it_falls_back_to_the_monday_count(self, stored_periods):
        fx = load_04a()
        day = date(2027, 3, 1)
        assert fx.derive_week_label(fx.CFG, day) == old_label(fx.CFG, day) == "18"

    def test_the_stat_timeframe_follows_the_label(self, stored_periods):
        fx = load_04a()
        assert fx.resolve_season_or_projection(fx.CFG, date(2026, 9, 13)) == fx.CFG.projection_code
        assert fx.resolve_season_or_projection(fx.CFG, date(2026, 9, 18)) == fx.CFG.ytd_code


class TestDerivePhaseUnchanged:
    def phases(self, monkeypatch, label):
        fx = load_04a()
        monkeypatch.setattr(fx, "derive_week_label", label)
        day, end, out = date(2026, 1, 1), date(2027, 4, 30), {}
        while day <= end:
            out[day] = rp.derive_phase(day)
            day += timedelta(days=1)
        return out

    def test_the_same_phase_on_every_date_of_the_season(self, stored_periods, monkeypatch):
        fx = load_04a()
        real = fx.derive_week_label
        new = self.phases(monkeypatch, real)
        old = self.phases(monkeypatch, old_label)
        assert new == old
        assert {"PRESEASON", "INSEASON", "OFFSEASON"} <= set(new.values())

    def test_the_same_phase_with_no_period_table(self, no_tables, monkeypatch):
        fx = load_04a()
        real = fx.derive_week_label
        assert self.phases(monkeypatch, real) == self.phases(monkeypatch, old_label)

    def test_the_label_differs_somewhere_so_the_phase_check_is_not_vacuous(self, stored_periods):
        fx = load_04a()
        days = [date(2026, 9, 14) + timedelta(days=i) for i in range(120)]
        assert any(fx.derive_week_label(fx.CFG, d) != old_label(fx.CFG, d) for d in days)
