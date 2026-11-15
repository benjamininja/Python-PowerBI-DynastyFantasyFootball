"""The yearly price list: its loader (scripts/load_price_list.py) and its lookup
(etl_helpers.price_list), #554. The export is built here from invented values,
shaped like the owner's Players export; no real export is read or committed."""
import importlib
import sys
from pathlib import Path

import openpyxl
import pandas as pd
import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))
import etl_helpers as etl  # noqa: E402

loader = importlib.import_module("load_price_list")

HEADER = ["Player", "Team", "Pos", "ID", "Salary", "Status"]
PLAYERS = [
    ("Test Player A", "AAA", "QB", "*0aaa1*", 2_000_000, "FA"),
    ("Test Player B", "BBB", "RB", "0bbb2", "$15,460,000", "T1"),
    ("Test Player C", "CCC", "WR", " *0ccc3* ", "3,250,000", "FA"),
    ("Test Player D", "DDD", "CB", "*0ddd4*", 2_000_000.0, "FA"),
]


def make_export(path, rows=PLAYERS, header=HEADER, title_rows=1, trailing_blank=2):
    wb = openpyxl.Workbook()
    ws = wb.active
    for i in range(title_rows):
        ws.append([f"Players export, invented title row {i}"])
    ws.append(header)
    for row in rows:
        ws.append(["Test Player", "AAA", "QB", *row, "FA"] if len(row) == 2 else list(row))
    for _ in range(trailing_blank):
        ws.append([None] * len(header))
    wb.save(path)
    return path


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("ETL_STORAGE", raising=False)
    monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    return tmp_path


@pytest.fixture
def export(store):
    return make_export(store / "players.xlsx")


def run(path, season=2027, pulled_on="2026-11-12", **kw):
    lines = []
    code = loader.load(path, season, pulled_on, out=lines.append, **kw)
    return code, lines


class TestReadExport:
    def test_keeps_only_id_and_salary_whatever_sits_above_and_beside(self, export):
        raw = loader.read_export(export)
        assert list(raw.columns) == ["scorer_id", "salary"]
        assert len(raw) == len(PLAYERS)

    def test_no_header_row_with_both_columns_is_none(self, store):
        path = make_export(store / "x.xlsx", header=["Player", "ID", "Cost"])
        assert loader.read_export(path) is None

    def test_header_case_and_spaces_do_not_matter(self, store):
        path = make_export(store / "x.xlsx", header=["Player", " id ", "SALARY"],
                           rows=[("n", "*0aaa1*", 5)])
        assert len(loader.read_export(path)) == 1


class TestCleaning:
    @pytest.mark.parametrize("value,want", [("*0aaa1*", "0aaa1"), (" 0aaa1 ", "0aaa1"),
                                            (" *0aaa1* ", "0aaa1"), ("0aaa1", "0aaa1")])
    def test_id(self, value, want):
        assert loader.clean_id(value) == want

    @pytest.mark.parametrize("value", [None, float("nan"), "", "  ", "**"])
    def test_blank_id_is_none(self, value):
        assert loader.clean_id(value) is None

    @pytest.mark.parametrize("value,want", [(2_000_000, 2_000_000.0), ("$15,460,000", 15_460_000.0),
                                            ("3,250,000", 3_250_000.0), (2.5, 2.5), (" 7 ", 7.0)])
    def test_salary(self, value, want):
        assert loader.parse_salary(value) == want

    @pytest.mark.parametrize("value", [None, float("nan"), "", "free", True, "2M?"])
    def test_unreadable_salary_is_nan(self, value):
        assert pd.isna(loader.parse_salary(value))


class TestLoad:
    def test_loads_every_player_row_once(self, export, store):
        code, lines = run(export)
        assert code == 0
        table = etl.read_table(etl.PRICE_LIST_TABLE)
        assert sorted(table["scorer_id"]) == ["0aaa1", "0bbb2", "0ccc3", "0ddd4"]
        assert set(table["season"]) == {2027}
        assert set(table["pulled_on"]) == {"2026-11-12"}
        assert table.set_index("scorer_id")["salary"].to_dict() == {
            "0aaa1": 2_000_000.0, "0bbb2": 15_460_000.0, "0ccc3": 3_250_000.0, "0ddd4": 2_000_000.0}
        assert any("4 row(s) for season 2027" in line for line in lines)

    def test_output_holds_no_id_and_no_salary(self, export):
        _, lines = run(export)
        text = "\n".join(lines)
        for secret in ("0aaa1", "0bbb2", "15460000", "15,460,000", "Test Player"):
            assert secret not in text

    def test_check_writes_nothing(self, export, store):
        code, lines = run(export, check_only=True)
        assert code == 0
        assert not etl.table_exists(etl.PRICE_LIST_TABLE)
        assert any("--check" in line for line in lines)

    def test_a_season_already_loaded_is_refused_and_left_alone(self, export, store):
        assert run(export)[0] == 0
        before = etl.read_table(etl.PRICE_LIST_TABLE)
        other = make_export(store / "again.xlsx", rows=[("*0zzz9*", 9_000_000)])
        code, lines = run(other)
        assert code == 1
        assert any("already holds rows for season 2027" in line for line in lines)
        pd.testing.assert_frame_equal(etl.read_table(etl.PRICE_LIST_TABLE), before)

    def test_a_season_that_lands_after_the_first_look_is_refused_not_replaced(self, export, store,
                                                                              monkeypatch):
        """A second run that passed its first look before the first run committed:
        the check inside the write catches the season, so nothing is replaced."""
        assert run(export)[0] == 0
        before = etl.read_table(etl.PRICE_LIST_TABLE)
        other = make_export(store / "again.xlsx", rows=[("*0zzz9*", 9_000_000)])
        real, looks = loader.held_problems, []

        def blind_at_first(season, stored):
            looks.append(1)
            return [] if len(looks) == 1 else real(season, stored)

        monkeypatch.setattr(loader, "held_problems", blind_at_first)
        code, lines = run(other)
        assert code == 1
        assert len(looks) == 2
        assert any("already holds rows for season 2027" in line for line in lines)
        assert lines[-1] == "nothing was written"
        pd.testing.assert_frame_equal(etl.read_table(etl.PRICE_LIST_TABLE), before)

    def test_a_first_load_into_the_shipped_empty_table(self, export, store):
        etl.write_table(etl.PRICE_LIST_TABLE, etl.empty_frame(etl._table_entry(etl.PRICE_LIST_TABLE)))
        code, lines = run(export)
        assert code == 0
        assert len(etl.read_table(etl.PRICE_LIST_TABLE)) == len(PLAYERS)

    def test_a_later_season_adds_beside_the_first(self, export, store):
        assert run(export)[0] == 0
        later = make_export(store / "next.xlsx", rows=[("*0aaa1*", 4_000_000)])
        assert run(later, season=2028, pulled_on="2027-11-10")[0] == 0
        table = etl.read_table(etl.PRICE_LIST_TABLE)
        assert sorted(zip(table["season"], table["scorer_id"])) == [
            (2027, "0aaa1"), (2027, "0bbb2"), (2027, "0ccc3"), (2027, "0ddd4"), (2028, "0aaa1")]

    @pytest.mark.parametrize("rows,fragment", [
        ([(None, 5)], "1 row(s) with a Salary and no ID"),
        ([("*0aaa1*", None)], "1 row(s) whose Salary is blank or not a number"),
        ([("*0aaa1*", "free")], "1 row(s) whose Salary is blank or not a number"),
        ([("*0aaa1*", -5)], "1 row(s) with a negative Salary"),
        ([("*0aaa1*", 5), ("0aaa1", 6)], "2 row(s) share an ID with another row"),
        ([], "the export holds no player row"),
    ])
    def test_each_stop_writes_nothing_and_counts_only(self, store, rows, fragment):
        path = make_export(store / "bad.xlsx", rows=rows)
        code, lines = run(path)
        assert code == 1
        assert any(fragment in line for line in lines)
        assert "nothing was written" in lines[-1]
        assert not etl.table_exists(etl.PRICE_LIST_TABLE)
        assert not any("0aaa1" in line for line in lines)

    def test_no_header_stops(self, store):
        path = make_export(store / "bad.xlsx", header=["Player", "ID", "Cost"])
        code, lines = run(path)
        assert code == 1
        assert any("no header row" in line for line in lines)

    def test_a_missing_file_stops(self, store):
        code, lines = run(store / "nope.xlsx")
        assert code == 1
        assert lines == ["stopped: the export path is not a file"]

    @pytest.mark.parametrize("pulled_on", ["12-11-2026", "2026-13-01", "2026-11-1", "2024-11-12"])
    def test_a_bad_or_off_year_date_stops(self, export, store, pulled_on):
        code, lines = run(export, pulled_on=pulled_on)
        assert code == 1
        assert not etl.table_exists(etl.PRICE_LIST_TABLE)

    def test_ids_missing_from_the_crosswalk_are_counted_not_stopped(self, export, store, monkeypatch):
        real_exists, real_read = etl.table_exists, etl.read_table
        monkeypatch.setattr(etl, "table_exists",
                            lambda name: name == loader.CROSSWALK_TABLE or real_exists(name))
        monkeypatch.setattr(etl, "read_table", lambda name, columns=None: (
            pd.DataFrame({"scorer_id": ["0aaa1", "0bbb2"]}) if name == loader.CROSSWALK_TABLE
            else real_read(name, columns)))
        code, lines = run(export)
        assert code == 0
        assert "info: 2 id(s) not in dim_fantrax_crosswalk" in lines

    def test_no_crosswalk_means_no_info_line(self, export):
        _, lines = run(export)
        assert not any(line.startswith("info:") for line in lines)


class TestLookup:
    def load_two(self, store):
        run(make_export(store / "a.xlsx", rows=[("*0aaa1*", 2_000_000), ("*0bbb2*", 8_000_000)]))
        run(make_export(store / "b.xlsx", rows=[("*0aaa1*", 3_000_000)]),
            season=2028, pulled_on="2027-11-10")

    def test_a_named_season(self, store):
        self.load_two(store)
        prices = etl.price_list(2027)
        assert prices.to_dict() == {"0aaa1": 2_000_000.0, "0bbb2": 8_000_000.0}

    def test_no_season_is_the_newest(self, store):
        self.load_two(store)
        assert etl.price_list().to_dict() == {"0aaa1": 3_000_000.0}

    def test_a_player_the_pull_did_not_hold_is_absent(self, store):
        self.load_two(store)
        assert "0bbb2" not in etl.price_list(2028).index

    def test_a_season_with_no_rows_raises(self, store):
        self.load_two(store)
        with pytest.raises(etl.TableNotFound):
            etl.price_list(2030)

    def test_no_table_raises(self, store):
        with pytest.raises(etl.TableNotFound):
            etl.price_list()

    def test_a_table_with_no_rows_raises_for_the_newest_and_for_a_season(self, store):
        etl.write_table(etl.PRICE_LIST_TABLE, etl.empty_frame(etl._table_entry(etl.PRICE_LIST_TABLE)))
        assert etl.table_exists(etl.PRICE_LIST_TABLE)
        with pytest.raises(etl.TableNotFound, match="no rows"):
            etl.price_list()
        with pytest.raises(etl.TableNotFound, match="no rows for season 2027"):
            etl.price_list(2027)


class TestRegistry:
    ENTRY = next(t for t in yaml.safe_load((REPO / "docs" / "data_model.yml").read_text(encoding="utf-8"))["tables"]
                 if t["name"] == etl.PRICE_LIST_TABLE)

    def test_manual_only_and_published(self):
        assert "chain" not in self.ENTRY
        assert not etl.is_private(self.ENTRY)

    def test_grain_is_season_and_player(self):
        assert self.ENTRY["pk"] == ["season", "scorer_id"]

    def test_the_loader_builds_the_registry_columns(self):
        built, _ = loader.build_table(pd.DataFrame({"scorer_id": ["*0aaa1*"], "salary": [5]}),
                                      2027, "2026-11-12")
        assert list(built.columns) == [c["name"] for c in self.ENTRY["columns"]]
        for c in self.ENTRY["columns"]:
            assert str(built[c["name"]].dtype) in (c["dtype"], "object" if c["dtype"] == "str" else c["dtype"])
