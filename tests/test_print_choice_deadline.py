"""scripts/print_choice_deadline.py (#548 brief 2, ADR-0025 decision 4): the
instant is 23:59:59 America/New_York on the given date, printed in UTC, and the
script connects to nothing. Season ids are invented."""
import importlib
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

script = importlib.import_module("print_choice_deadline")


def run(*argv):
    lines = []
    code = script.main(list(argv), out=lines.append)
    return code, lines


class TestInstant:
    def test_a_winter_date_is_five_hours_ahead_of_utc(self):
        assert script.deadline_instant(date(2026, 11, 19)) == datetime(2026, 11, 20, 4, 59, 59, tzinfo=timezone.utc)

    def test_a_summer_date_is_four_hours_ahead_of_utc(self):
        assert script.deadline_instant(date(2026, 7, 15)) == datetime(2026, 7, 16, 3, 59, 59, tzinfo=timezone.utc)

    def test_the_day_the_clocks_change_in_autumn_ends_on_winter_time(self):
        assert script.deadline_instant(date(2026, 11, 1)) == datetime(2026, 11, 2, 4, 59, 59, tzinfo=timezone.utc)

    def test_the_day_the_clocks_change_in_spring_ends_on_summer_time(self):
        assert script.deadline_instant(date(2027, 3, 14)) == datetime(2027, 3, 15, 3, 59, 59, tzinfo=timezone.utc)


class TestStatement:
    def test_prints_one_insert_with_the_utc_instant(self):
        code, lines = run("--season", "S1", "--kind", "fa_keep", "--date", "2026-11-19")
        assert code == 0 and len(lines) == 1
        assert "'S1', 'fa_keep', timestamptz '2026-11-20 04:59:59+00'" in lines[0]
        assert lines[0].startswith("INSERT INTO ops.choice_deadline")

    def test_a_summer_date_prints_its_own_offset(self):
        _, lines = run("--season", "S1", "--kind", "resign", "--date", "2026-07-15")
        assert "timestamptz '2026-07-16 03:59:59+00'" in lines[0]

    def test_a_key_already_there_changes_the_instant_only_while_it_is_still_ahead(self):
        _, lines = run("--season", "S1", "--kind", "fa_keep", "--date", "2026-11-19")
        assert ("ON CONFLICT (season_id, choice_kind) DO UPDATE SET deadline_at = EXCLUDED.deadline_at "
                "WHERE ops.choice_deadline.deadline_at > clock_timestamp();") in lines[0]
        assert lines[0].count(";") == 1

class TestRefusals:
    @pytest.mark.parametrize("day", ["2026-13-01", "2026-11-31", "20261119", "2026-1-9", "tomorrow", ""])
    def test_a_bad_date_stops_and_prints_nothing(self, day, capsys):
        code, lines = run("--season", "S1", "--kind", "fa_keep", "--date", day)
        assert code == 1 and lines == []
        assert "--date" in capsys.readouterr().err

    @pytest.mark.parametrize("season", ["", "S1'; DROP TABLE x; --", "a b", ".S1"])
    def test_a_bad_season_stops(self, season, capsys):
        code, lines = run("--season", season, "--kind", "fa_keep", "--date", "2026-11-19")
        assert code == 1 and lines == []

    def test_a_kind_outside_the_two_is_refused_by_the_parser(self):
        with pytest.raises(SystemExit):
            run("--season", "S1", "--kind", "keep", "--date", "2026-11-19")

    def test_no_clock_time_can_be_given(self):
        with pytest.raises(SystemExit):
            run("--season", "S1", "--kind", "fa_keep", "--date", "2026-11-19", "--time", "12:00")


def test_the_script_opens_no_connection():
    source = (REPO / "scripts" / "print_choice_deadline.py").read_text(encoding="utf-8")
    for word in ("psycopg", "socket", "requests", "urllib", "etl_helpers", "environ"):
        assert word not in source
