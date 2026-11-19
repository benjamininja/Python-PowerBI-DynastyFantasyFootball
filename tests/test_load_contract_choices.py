"""scripts/load_contract_choices.py (#548 brief 2, #612, ADR-0025 decision 7).
Every team, ID, roster, price list and workbook is invented here; no real name
is read or committed, and nothing connects to a database."""
import importlib
import sys
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))
import etl_helpers as etl  # noqa: E402

loader = importlib.import_module("load_contract_choices")

SEASON = "S2026"
TEAMS = pd.DataFrame({"team_key": ["T1", "T2", "T3"],
                      "team_name": ["Test Team One", "Test Team Two", "Test Team Three"]})
ROSTER = pd.DataFrame({
    "team_key": ["T1", "T1", "T1", "T2", "T2", "T3"],
    "scorer_id": ["s1", "s2", "s3", "s4", "s5", "s6"],
    "contract_id": ["FA", "FA", "Y2", "FA", "FA", "FA"]})
SEASONS = pd.DataFrame({"season_id": [SEASON, "S2025"], "season_start_year": [2026, 2025]})
PRICES = pd.Series({"s1": 2_000_000.0, "s2": 3_500_000.0, "s4": 1_250_000.5, "s5": 4_000_000.0, "s6": 2_000_000.0})

HEAD = ("Team Name", "Fantrax ID", "Resign")
RIDDELL = [("Test Team One", "s1", "Yes"), ("Test Team One", "s2", "No"),
           ("Test Team Two", "s4", "yes "), ("Test Team Two", "s5", " NO")]
WILSON = [("Test Team Three", "s6", None)]
BOOK = {"Riddell": RIDDELL, "Wilson": WILSON, "Other": [("ignored", "x", "maybe")]}


def tables(**over):
    base = {"teams": TEAMS, "roster": ROSTER, "seasons": SEASONS, "prices": PRICES}
    base.update(over)
    return base


def make_book(path, book=None, header=HEAD):
    book = BOOK if book is None else book
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for tab, rows in book.items():
        ws = wb.create_sheet(tab)
        ws.append(list(header))
        for row in rows:
            ws.append(list(row))
    wb.save(path)
    return path


@pytest.fixture
def place(tmp_path):
    folder = tmp_path / "keep"
    folder.mkdir()
    return folder


def run(place, book=None, season=SEASON, out_name="out.sql", header=HEAD, **kw):
    lines = []
    out_path = place / out_name
    code = loader.load(make_book(place / "book.xlsx", book, header), season, out_path,
                       tables=kw.pop("tables", tables()), out=lines.append, **kw)
    return code, lines, out_path


class TestTheMapping:
    def test_yes_is_keep_and_no_is_let_go_whatever_the_case_or_spacing(self, place):
        code, _, out = run(place)
        sql = out.read_text(encoding="utf-8")
        assert code == 0
        assert "('S2026', 'T1', 's1', 'fa_keep', 'keep', 2000000.0, 'loader', NULL)" in sql
        assert "('S2026', 'T1', 's2', 'fa_keep', 'let_go', 3500000.0, 'loader', NULL)" in sql
        assert "('S2026', 'T2', 's4', 'fa_keep', 'keep', 1250000.5, 'loader', NULL)" in sql
        assert "('S2026', 'T2', 's5', 'fa_keep', 'let_go', 4000000.0, 'loader', NULL)" in sql
        assert sql.count(", 'loader', NULL)") == 4

    def test_a_blank_writes_no_row(self, place):
        _, _, out = run(place)
        assert "'s6'" not in out.read_text(encoding="utf-8")

    def test_the_team_column_is_found_by_the_header_prefix(self, place):
        code, _, out = run(place, header=("Team", "Fantrax ID", "Resign"))
        assert code == 0 and out.read_text(encoding="utf-8").count("'fa_keep'") == 4

    def test_columns_are_found_in_any_order_and_among_others(self, tmp_path):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Riddell"
        ws.append(["Pos", "Resign", "Team (owner)", "Fantrax ID", "Notes"])
        ws.append(["QB", "Yes", "Test Team One", "s1", "x"])
        wb.create_sheet("Wilson").append(["Resign", "Fantrax ID", "Team"])
        path = tmp_path / "b.xlsx"
        wb.save(path)
        out = tmp_path / "o.sql"
        assert loader.load(path, SEASON, out, tables=tables(), out=lambda _l: None) == 0
        assert out.read_text(encoding="utf-8").count("'fa_keep'") == 1

    def test_only_the_named_tabs_are_read(self, place):
        book = {"Riddell": RIDDELL, "Wilson": WILSON, "Extra": [("Test Team Three", "s6", "Yes")]}
        _, _, out = run(place, book=book)
        assert "'s6'" not in out.read_text(encoding="utf-8")
        _, _, out2 = run(place, book=book, tabs="Extra", out_name="two.sql")
        assert "'s6'" in out2.read_text(encoding="utf-8")

    def test_the_same_id_on_two_teams_is_two_copies(self, place):
        roster = pd.DataFrame({"team_key": ["T1", "T2"], "scorer_id": ["s1", "s1"], "contract_id": ["FA", "FA"]})
        book = {"Riddell": [("Test Team One", "s1", "Yes")], "Wilson": [("Test Team Two", "s1", "No")]}
        code, _, out = run(place, book=book, tables=tables(roster=roster))
        sql = out.read_text(encoding="utf-8")
        assert code == 0 and "'T1', 's1', 'fa_keep', 'keep'" in sql and "'T2', 's1', 'fa_keep', 'let_go'" in sql

    def test_the_file_holds_no_name(self, place):
        _, _, out = run(place)
        sql = out.read_text(encoding="utf-8")
        for word in ("Test Team", "Riddell"):
            assert word not in sql

    def test_rows_come_out_in_one_order_whatever_the_sheet_order(self, place):
        _, _, a = run(place, out_name="a.sql")
        _, _, b = run(place, book={"Riddell": list(reversed(RIDDELL)), "Wilson": WILSON}, out_name="b.sql")
        assert a.read_bytes() == b.read_bytes()

    def test_the_locked_value_is_the_price_for_the_season_after(self, monkeypatch):
        asked = []

        def fake_prices(year):
            asked.append(year)
            return PRICES

        monkeypatch.setattr(etl, "read_table", lambda name, cols=None: {
            "dim_season": SEASONS, "dim_fantasy_teams": TEAMS, "fact_fantasy_teams": ROSTER}[name])
        monkeypatch.setattr(etl, "price_list", fake_prices)
        read = loader.read_tables(SEASON)
        assert asked == [2027] and read["prices"] is PRICES and "names" not in read

    def test_an_empty_price_list_reads_as_no_prices(self, monkeypatch):
        def no_prices(year):
            raise etl.TableNotFound("no rows")

        monkeypatch.setattr(etl, "read_table", lambda name, cols=None: {
            "dim_season": SEASONS, "dim_fantasy_teams": TEAMS, "fact_fantasy_teams": ROSTER}[name])
        monkeypatch.setattr(etl, "price_list", no_prices)
        assert loader.read_tables(SEASON)["prices"] is None


class TestTheSqlFile:
    def test_writes_one_transaction_of_inserts_that_update_on_a_key_already_there(self, place):
        _, _, out = run(place)
        sql = out.read_text(encoding="utf-8")
        assert sql.startswith("BEGIN;\nWITH written AS (\nINSERT INTO app.contract_choices ")
        assert sql.rstrip().endswith("COMMIT;")
        assert sql.count("INSERT INTO") == 1
        assert ("ON CONFLICT (season_id, team_key, scorer_id, choice_kind) DO UPDATE SET "
                "choice = EXCLUDED.choice, locked_value = EXCLUDED.locked_value\n") in sql

    def test_a_key_an_owners_row_holds_is_left_alone_and_counted(self, place):
        _, _, out = run(place)
        sql = out.read_text(encoding="utf-8")
        assert "WHERE contract_choices.origin = 'loader'\nRETURNING 1\n)" in sql
        assert "SELECT count(*) AS rows_written, 4 - count(*) AS keys_left_alone FROM written;" in sql
        assert "SET origin" not in sql and "changed_by =" not in sql

    def test_run_twice_it_writes_the_same_file(self, place):
        _, _, first = run(place, out_name="one.sql")
        _, _, second = run(place, out_name="two.sql")
        assert first.read_bytes() == second.read_bytes()


class TestTheCounts:
    def test_prints_counts_only(self, place):
        code, lines, _ = run(place)
        assert code == 0
        assert lines == ["read: 5 row(s)",
                         "no choice (blank Resign): 1 row(s)",
                         "skipped (No on a copy no longer an FA copy on that team): 0 row(s)",
                         "wrote: 4 row(s) to the file",
                         "FA copies on the roster that the workbook does not list: 0",
                         "when run, the file returns rows_written and keys_left_alone "
                         "(keys an owner's own row holds)"]

    def test_a_copy_the_workbook_does_not_list_is_counted_and_gets_no_row(self, place):
        _, lines, out = run(place, book={"Riddell": RIDDELL[:2], "Wilson": []})
        assert out.read_text(encoding="utf-8").count("'fa_keep'") == 2
        assert "FA copies on the roster that the workbook does not list: 3" in lines

    def test_a_blank_counts_as_no_choice_and_the_copy_is_listed(self, place):
        _, lines, _ = run(place, book={"Riddell": [("Test Team One", "s1", None), ("Test Team One", "s2", "  ")],
                                        "Wilson": []})
        assert "no choice (blank Resign): 2 row(s)" in lines
        assert "wrote: 0 row(s) to the file" in lines
        assert "FA copies on the roster that the workbook does not list: 3" in lines

    def test_a_moot_no_is_skipped_and_counted(self, place):
        code, lines, out = run(place, book={"Riddell": RIDDELL + [("Test Team One", "s3", "No"),
                                                                   ("Test Team One", "gone", "No")],
                                            "Wilson": WILSON})
        assert code == 0
        assert "skipped (No on a copy no longer an FA copy on that team): 2 row(s)" in lines
        assert "wrote: 4 row(s) to the file" in lines
        assert "'s3'" not in out.read_text(encoding="utf-8")

    def test_no_line_names_a_team_an_id_or_a_value(self, place):
        _, lines, _ = run(place, book={"Riddell": [("No Such Team", "zz9", "keep")], "Wilson": []})
        text = "".join(lines)
        for word in ("No Such", "zz9", "keep", "Test Team"):
            assert word not in text


class TestStops:
    def stopped(self, place, rows, want, **kw):
        code, lines, out = run(place, book={"Riddell": rows, "Wilson": WILSON}, **kw)
        assert code == 1
        assert any(want in line for line in lines), lines
        assert lines[-1] == "nothing was written"
        assert not out.exists()
        text = "".join(lines)
        for word in ("No Such", "zz9", "Test Team", "maybe"):
            assert word not in text
        return lines

    def test_a_yes_on_a_copy_that_is_no_longer_an_fa_copy_stops(self, place):
        self.stopped(place, [("Test Team One", "s3", "Yes")],
                     "tab Riddell: 1 row(s) with Yes on a copy that is not an FA copy on that team (rows 2)")

    def test_a_yes_on_a_copy_that_is_not_on_the_team_stops(self, place):
        self.stopped(place, [("Test Team One", "s4", "Yes")], "with Yes on a copy that is not an FA copy")

    def test_a_pair_listed_twice_stops_at_its_second_row(self, place):
        self.stopped(place, RIDDELL + [RIDDELL[0]],
                     "tab Riddell: 1 row(s) listing a copy already listed (rows 6)")

    def test_a_pair_listed_on_two_tabs_stops(self, place):
        code, lines, _ = run(place, book={"Riddell": [("Test Team One", "s1", "Yes")],
                                          "Wilson": [("Test Team One", "s1", "No")]})
        assert code == 1 and "stopped: tab Wilson: 1 row(s) listing a copy already listed (rows 2)" in lines

    def test_a_value_other_than_yes_no_or_blank_stops(self, place):
        self.stopped(place, [("Test Team One", "s1", "maybe")],
                     "tab Riddell: 1 row(s) whose Resign is not Yes, No or blank (rows 2)")

    def test_a_team_that_does_not_resolve_stops(self, place):
        self.stopped(place, [("No Such Team", "s1", "Yes")],
                     "tab Riddell: 1 row(s) whose team does not resolve to one team (rows 2)")

    def test_a_team_name_two_teams_share_stops(self, place):
        twin = pd.DataFrame({"team_key": ["T1", "T2"], "team_name": ["Same", "Same"]})
        self.stopped(place, [("Same", "s1", "Yes")], "team does not resolve", tables=tables(teams=twin))

    @pytest.mark.parametrize("cell", [4123, 4123.0])
    def test_a_numeric_fantrax_id_cell_stops_with_its_tab_and_row(self, place, cell):
        roster = pd.DataFrame({"team_key": ["T1"], "scorer_id": ["4123"], "contract_id": ["FA"]})
        lines = self.stopped(place, [("Test Team One", "s1", "Yes"), ("Test Team One", cell, "No")],
                             "tab Riddell: 1 row(s) whose Fantrax ID is not text (rows 3)",
                             tables=tables(roster=roster))
        assert not any("skipped" in line for line in lines)

    def test_a_team_name_is_matched_exactly_after_a_trim_only(self, place):
        self.stopped(place, [("Test  Team One", "s1", "Yes")], "team does not resolve")
        code, _, out = run(place, book={"Riddell": [("  Test Team One ", " s1 ", "Yes")], "Wilson": []})
        assert code == 0 and "'T1', 's1'" in out.read_text(encoding="utf-8")

    def test_a_row_with_no_id_stops(self, place):
        self.stopped(place, [("Test Team One", None, "Yes")], "tab Riddell: 1 row(s) with no Fantrax ID (rows 2)")

    def test_a_copy_with_no_price_list_row_stops(self, place):
        self.stopped(place, [("Test Team One", "s1", "Yes")], "1 row(s) whose copy has no price-list row",
                     tables=tables(prices=PRICES.drop("s1")))

    def test_a_price_list_with_no_row_for_the_season_stops(self, place):
        self.stopped(place, RIDDELL, "4 row(s) whose copy has no price-list row", tables=tables(prices=None))

    def test_a_blank_with_no_price_does_not_stop(self, place):
        code, _, _ = run(place, book={"Riddell": [("Test Team One", "s1", None)], "Wilson": []},
                         tables=tables(prices=None))
        assert code == 0

    def test_a_season_dim_season_does_not_hold(self, place):
        self.stopped(place, RIDDELL, "--season is not a season of dim_season", season="S1999")

    def test_a_workbook_with_no_row_stops(self, place):
        code, lines, out = run(place, book={"Riddell": [], "Wilson": []})
        assert code == 1 and not out.exists()
        assert "stopped: the workbook holds no row on the named tabs" in lines

    def test_every_problem_is_listed_with_the_row_numbers_per_tab(self, place):
        code, lines, out = run(place, book={
            "Riddell": [("Test Team One", "s1", "Yes"), ("No Such Team", "zz9", "Yes"),
                        ("Test Team One", "s2", "maybe"), ("Also None", "zz9", "Yes")],
            "Wilson": [("Test Team Three", "s6", "perhaps")]})
        assert code == 1 and not out.exists()
        assert "stopped: tab Riddell: 2 row(s) whose team does not resolve to one team (rows 3, 5)" in lines
        assert "stopped: tab Riddell: 1 row(s) whose Resign is not Yes, No or blank (rows 4)" in lines
        assert "stopped: tab Wilson: 1 row(s) whose Resign is not Yes, No or blank (rows 2)" in lines

    def test_a_row_after_a_blank_row_keeps_its_own_number(self, place):
        _, lines, _ = run(place, book={"Riddell": [("Test Team One", "s1", "Yes"), (None, None, None),
                                                   ("No Such Team", "zz9", "Yes")], "Wilson": []})
        assert any("(rows 4)" in line for line in lines)


class TestTheWorkbookShape:
    def test_a_missing_tab_stops_and_names_the_tab_only(self, place):
        code, lines, out = run(place, book={"Riddell": RIDDELL})
        assert code == 1 and not out.exists()
        assert "stopped: tab Wilson: the tab is not in the workbook" in lines
        assert lines[-1] == "nothing was written"

    def test_a_tab_named_by_tabs_that_is_not_there_stops(self, place):
        code, lines, _ = run(place, tabs="Riddell,Nope")
        assert code == 1 and "stopped: tab Nope: the tab is not in the workbook" in lines

    @pytest.mark.parametrize("header,word", [(("Team", "Fantrax ID", "Pick"), "Resign"),
                                             (("Team", "ID", "Resign"), "Fantrax ID"),
                                             (("Squad", "Fantrax ID", "Resign"), "Team")])
    def test_a_missing_column_stops_and_names_the_tab(self, place, header, word):
        code, lines, out = run(place, header=header)
        assert code == 1 and not out.exists()
        assert any(line.startswith("stopped: tab Riddell: missing ") and word in line for line in lines)
        assert lines[-1] == "nothing was written"

    def test_two_columns_starting_with_team_stop(self, place):
        code, lines, _ = run(place, header=("Team", "Team Name", "Fantrax ID", "Resign"),
                             book={"Riddell": [], "Wilson": []})
        assert code == 1 and any("single column whose header starts with Team" in line for line in lines)

    def test_an_empty_tabs_argument_stops(self, place):
        code, lines, out = run(place, tabs=" , ")
        assert code == 1 and not out.exists() and "stopped: --tabs names no tab" in lines


class TestTheStorageAndTheOutFile:
    def test_a_database_storage_setting_stops_the_run_and_writes_nothing(self, place, monkeypatch):
        monkeypatch.setenv("ETL_STORAGE", "postgres")
        code, lines, out = run(place)
        assert code == 1 and not out.exists()
        assert "stopped: ETL_STORAGE selects the database; the loader reads the published snapshot only" in lines
        assert lines[-1] == "nothing was written"

    def test_the_parquet_setting_runs_as_usual(self, place, monkeypatch):
        monkeypatch.setenv("ETL_STORAGE", "parquet")
        assert run(place)[0] == 0

    def test_an_out_path_that_exists_is_refused_and_left_as_it_was(self, place):
        target = place / "out.sql"
        target.write_text("EARLIER RUN", encoding="utf-8")
        code, lines, _ = run(place, out_name="out.sql")
        assert code == 1 and target.read_text(encoding="utf-8") == "EARLIER RUN"
        assert any("--out already exists" in line for line in lines)

    def test_an_out_path_that_is_a_folder_is_refused(self, place):
        (place / "dir").mkdir()
        code, lines, _ = run(place, out_name="dir")
        assert code == 1 and any("--out already exists" in line for line in lines)

    def test_a_failed_run_after_a_good_one_leaves_no_file_at_a_new_path(self, place):
        _, _, first = run(place, out_name="one.sql")
        code, _, second = run(place, book={"Riddell": [("No Such Team", "s1", "Yes")], "Wilson": []},
                              out_name="two.sql")
        assert first.exists() and code == 1 and not second.exists()


class TestTheOutPath:
    def test_a_path_inside_a_git_repository_is_refused(self, tmp_path):
        repo = tmp_path / "work"
        (repo / ".git").mkdir(parents=True)
        (repo / "deep").mkdir()
        keep = make_book(tmp_path / "book.xlsx")
        lines = []
        code = loader.load(keep, SEASON, repo / "deep" / "out.sql", tables=tables(), out=lines.append)
        assert code == 1 and not (repo / "deep" / "out.sql").exists()
        assert any("inside a git repository" in line for line in lines)

    def test_a_worktree_git_file_counts_as_a_repository(self, tmp_path):
        repo = tmp_path / "wt"
        repo.mkdir()
        (repo / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
        keep = make_book(tmp_path / "book.xlsx")
        code = loader.load(keep, SEASON, repo / "out.sql", tables=tables(), out=lambda _l: None)
        assert code == 1 and not (repo / "out.sql").exists()

    def test_the_real_repository_is_refused(self, tmp_path):
        keep = make_book(tmp_path / "book.xlsx")
        code = loader.load(keep, SEASON, REPO / "builder-state" / "out.sql", tables=tables(), out=lambda _l: None)
        assert code == 1

    def test_a_missing_folder_is_refused(self, tmp_path):
        keep = make_book(tmp_path / "book.xlsx")
        lines = []
        code = loader.load(keep, SEASON, tmp_path / "nope" / "out.sql", tables=tables(), out=lines.append)
        assert code == 1 and any("folder of --out does not exist" in line for line in lines)

    def test_a_bad_season_id_is_refused(self, place):
        code, lines, out = run(place, season="S1'; DROP TABLE x")
        assert code == 1 and not out.exists()

    def test_a_path_that_is_not_a_file_is_refused(self, tmp_path):
        code = loader.load(tmp_path / "nope.xlsx", SEASON, tmp_path / "out.sql", tables=tables(), out=lambda _l: None)
        assert code == 1


class TestTheScriptConnectsToNothing:
    def test_it_imports_no_database_driver_reads_no_env_file_and_no_crosswalk(self):
        source = (REPO / "scripts" / "load_contract_choices.py").read_text(encoding="utf-8")
        for word in ("psycopg", "SUPABASE_DB_URL", "use_env_file", "write_table", "_backend",
                     "dim_fantrax_crosswalk", "clean_player_name"):
            assert word not in source

    def test_main_reads_through_the_seam_and_prints_a_stop_without_a_value(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path / "empty"))
        (tmp_path / "empty").mkdir()
        keep = make_book(tmp_path / "book.xlsx")
        code = loader.main([str(keep), "--season", SEASON, "--out", str(tmp_path / "out.sql")])
        assert code == 1 and not (tmp_path / "out.sql").exists()
        assert "Test Team" not in capsys.readouterr().out

    def test_main_passes_the_tabs_argument(self, tmp_path, monkeypatch):
        seen = {}
        monkeypatch.setattr(loader, "load", lambda x, s, o, tabs=None, **k: seen.update(tabs=tabs) or 0)
        assert loader.main(["b.xlsx", "--season", SEASON, "--out", "o.sql", "--tabs", "A,B"]) == 0
        assert seen["tabs"] == "A,B"
