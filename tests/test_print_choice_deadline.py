"""scripts/print_choice_deadline.py (#548 brief 2, ADR-0025 decision 4; #661, ADR-0026
decision 6): each instant is 23:59:59 America/New_York on the given date, printed
in UTC, the final date must be later than the deadline date, and the script
connects to nothing. Season ids are invented."""
import importlib
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

script = importlib.import_module("print_choice_deadline")

FINAL = "2027-02-28"


def run(*argv):
    lines = []
    code = script.main(list(argv), out=lines.append)
    return code, lines


def args(season="S1", kind="fa_keep", day="2026-11-19", final=FINAL):
    return ("--season", season, "--kind", kind, "--date", day, "--final-date", final)


class TestInstant:
    def test_a_winter_date_is_five_hours_ahead_of_utc(self):
        assert script.deadline_instant(date(2026, 11, 19)) == datetime(2026, 11, 20, 4, 59, 59, tzinfo=timezone.utc)

    def test_a_summer_date_is_four_hours_ahead_of_utc(self):
        assert script.deadline_instant(date(2026, 7, 15)) == datetime(2026, 7, 16, 3, 59, 59, tzinfo=timezone.utc)

    def test_the_day_the_clocks_change_in_autumn_ends_on_winter_time(self):
        assert script.deadline_instant(date(2026, 11, 1)) == datetime(2026, 11, 2, 4, 59, 59, tzinfo=timezone.utc)

    def test_the_day_the_clocks_change_in_spring_ends_on_summer_time(self):
        assert script.deadline_instant(date(2027, 3, 14)) == datetime(2027, 3, 15, 3, 59, 59, tzinfo=timezone.utc)

    def test_the_seasons_last_day_is_the_instant_the_owner_set_for_the_existing_row(self):
        assert script.deadline_instant(date(2027, 2, 28)) == datetime(2027, 3, 1, 4, 59, 59, tzinfo=timezone.utc)


class TestStatement:
    def test_prints_one_insert_with_both_utc_instants(self):
        code, lines = run(*args())
        assert code == 0 and len(lines) == 1
        assert lines[0].startswith("INSERT INTO ops.choice_deadline (season_id, choice_kind, deadline_at, final_at)")
        assert ("VALUES ('S1', 'fa_keep', timestamptz '2026-11-20 04:59:59+00', "
                "timestamptz '2027-03-01 04:59:59+00')") in lines[0]

    def test_a_summer_date_prints_its_own_offset(self):
        _, lines = run(*args(kind="resign", day="2026-07-15", final="2026-07-16"))
        assert "timestamptz '2026-07-16 03:59:59+00', timestamptz '2026-07-17 03:59:59+00'" in lines[0]

    def test_a_key_already_there_changes_both_instants_only_while_the_deadline_is_still_ahead(self):
        _, lines = run(*args())
        assert ("ON CONFLICT (season_id, choice_kind) DO UPDATE SET deadline_at = EXCLUDED.deadline_at, "
                "final_at = EXCLUDED.final_at "
                "WHERE ops.choice_deadline.deadline_at > clock_timestamp();") in lines[0]
        assert lines[0].count(";") == 1


class TestRefusals:
    @pytest.mark.parametrize("day", ["2026-13-01", "2026-11-31", "20261119", "2026-1-9", "tomorrow", ""])
    def test_a_bad_date_stops_and_prints_nothing(self, day, capsys):
        code, lines = run(*args(day=day))
        assert code == 1 and lines == []
        assert "--date" in capsys.readouterr().err

    @pytest.mark.parametrize("final", ["2027-13-01", "2027-02-30", "20270228", "2027-2-8", "later", ""])
    def test_a_bad_final_date_stops_and_prints_nothing(self, final, capsys):
        code, lines = run(*args(final=final))
        assert code == 1 and lines == []
        assert "--final-date" in capsys.readouterr().err

    @pytest.mark.parametrize("final", ["2026-11-19", "2026-11-18", "2025-01-01"])
    def test_a_final_date_not_later_than_the_deadline_date_stops(self, final, capsys):
        code, lines = run(*args(day="2026-11-19", final=final))
        assert code == 1 and lines == []
        assert "not later than" in capsys.readouterr().err

    def test_the_day_after_is_enough(self):
        code, lines = run(*args(day="2026-11-19", final="2026-11-20"))
        assert code == 0 and "timestamptz '2026-11-21 04:59:59+00'" in lines[0]

    def test_the_final_date_is_required(self):
        with pytest.raises(SystemExit):
            run("--season", "S1", "--kind", "fa_keep", "--date", "2026-11-19")

    @pytest.mark.parametrize("season", ["", "S1'; DROP TABLE x; --", "a b", ".S1"])
    def test_a_bad_season_stops(self, season, capsys):
        code, lines = run(*args(season=season))
        assert code == 1 and lines == []

    def test_a_kind_outside_the_two_is_refused_by_the_parser(self):
        with pytest.raises(SystemExit):
            run(*args(kind="keep"))

    def test_no_clock_time_can_be_given(self):
        with pytest.raises(SystemExit):
            run(*args(), "--time", "12:00")


def test_the_script_opens_no_connection():
    source = (REPO / "scripts" / "print_choice_deadline.py").read_text(encoding="utf-8")
    for word in ("psycopg", "socket", "requests", "urllib", "etl_helpers", "environ"):
        assert word not in source
