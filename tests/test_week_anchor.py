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

    def test_no_table_is_off_season(self, no_tables):
        assert etl.scoring_period_on(date(2026, 9, 16)) is None
        assert etl.week_anchor(date(2026, 9, 16)) == date(2026, 9, 20)

    def test_the_anchor_is_always_a_sunday_off_season(self):
        day = date(2027, 1, 8)
        for i in range(60):
            assert etl.week_anchor(day + timedelta(days=i), PERIODS).weekday() == 6

    def test_the_stored_table_is_read_when_none_is_given(self, stored_periods):
        assert etl.week_anchor(date(2026, 9, 16)) == date(2026, 9, 17)
        assert etl.week_anchor() is not None


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
