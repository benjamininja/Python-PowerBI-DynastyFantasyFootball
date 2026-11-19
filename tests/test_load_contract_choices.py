"""scripts/load_contract_choices.py (#548 brief 2, ADR-0025 decision 7). Every
roster, price list and keep file is invented here; no real name is read or
committed, and nothing connects to a database."""
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
NAMES = pd.DataFrame({
    "scorer_id": ["s1", "s2", "s3", "s4", "s5", "s6"],
    "player_name": ["Alpha One", "Bravo Two", "Charlie Three", "Delta Four", "Echo Five", "Foxtrot Six"]})
SEASONS = pd.DataFrame({"season_id": [SEASON, "S2025"], "season_start_year": [2026, 2025]})
PRICES = pd.Series({"s1": 2_000_000.0, "s2": 3_500_000.0, "s4": 1_250_000.5, "s5": 4_000_000.0, "s6": 2_000_000.0})

FILE_ROWS = [("Test Team One", "Alpha One", "keep"), ("Test Team One", "Bravo Two", "let go"),
             ("Test Team Two", "Delta Four", "Keep"), ("Test Team Two", "Echo Five", "LET GO")]


def tables(**over):
    base = {"teams": TEAMS, "roster": ROSTER, "names": NAMES, "seasons": SEASONS, "prices": PRICES}
    base.update(over)
    return base


def make_file(path, rows=FILE_ROWS, header=("team", "player", "choice")):
    wb = openpyxl.Workbook()
    ws = wb.active
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


def run(place, rows=FILE_ROWS, season=SEASON, out_name="out.sql", header=("team", "player", "choice"), **kw):
    lines = []
    out_path = place / out_name
    code = loader.load(make_file(place / "keep.xlsx", rows, header), season, out_path,
                       tables=kw.pop("tables", tables()), out=lines.append, **kw)
    return code, lines, out_path


class TestTheFile:
    def test_writes_one_transaction_of_inserts_that_update_on_a_key_already_there(self, place):
        code, lines, out = run(place)
        sql = out.read_text(encoding="utf-8")
        assert code == 0
        assert sql.startswith("BEGIN;\nINSERT INTO app.contract_choices ")
        assert sql.rstrip().endswith("COMMIT;")
        assert sql.count("INSERT INTO") == 1
        assert ("ON CONFLICT (season_id, team_key, scorer_id, choice_kind) DO UPDATE SET "
                "choice = EXCLUDED.choice, locked_value = EXCLUDED.locked_value;") in sql

    def test_each_row_is_fa_keep_from_the_loader_with_no_changed_by(self, place):
        _, _, out = run(place)
        sql = out.read_text(encoding="utf-8")
        assert ("('S2026', 'T1', 's1', 'fa_keep', 'keep', 2000000.0, 'loader', NULL)") in sql
        assert ("('S2026', 'T1', 's2', 'fa_keep', 'let_go', 3500000.0, 'loader', NULL)") in sql
        assert ("('S2026', 'T2', 's4', 'fa_keep', 'keep', 1250000.5, 'loader', NULL)") in sql
        assert ("('S2026', 'T2', 's5', 'fa_keep', 'let_go', 4000000.0, 'loader', NULL)") in sql
        assert sql.count("'loader'") == 4

    def test_the_file_holds_no_name(self, place):
        _, _, out = run(place)
        sql = out.read_text(encoding="utf-8")
        for name in ("Alpha", "Bravo", "Test Team"):
            assert name not in sql

    def test_run_twice_it_writes_the_same_file(self, place):
        _, _, first = run(place, out_name="one.sql")
        _, _, second = run(place, out_name="two.sql")
        assert first.read_bytes() == second.read_bytes()

    def test_rows_come_out_in_one_order_whatever_the_file_order(self, place):
        _, _, a = run(place, rows=FILE_ROWS, out_name="a.sql")
        _, _, b = run(place, rows=list(reversed(FILE_ROWS)), out_name="b.sql")
        assert a.read_bytes() == b.read_bytes()

    def test_the_locked_value_is_the_price_for_the_season_after(self, monkeypatch):
        asked = []

        def fake_prices(year):
            asked.append(year)
            return PRICES

        monkeypatch.setattr(etl, "read_table", lambda name, cols=None: {
            "dim_season": SEASONS, "dim_fantasy_teams": TEAMS, "fact_fantasy_teams": ROSTER,
            "dim_fantrax_crosswalk": NAMES}[name])
        monkeypatch.setattr(etl, "price_list", fake_prices)
        read = loader.read_tables(SEASON)
        assert asked == [2027] and read["prices"] is PRICES

    def test_an_empty_price_list_reads_as_no_prices(self, monkeypatch):
        def no_prices(year):
            raise etl.TableNotFound("no rows")

        monkeypatch.setattr(etl, "read_table", lambda name, cols=None: {
            "dim_season": SEASONS, "dim_fantasy_teams": TEAMS, "fact_fantasy_teams": ROSTER,
            "dim_fantrax_crosswalk": NAMES}[name])
        monkeypatch.setattr(etl, "price_list", no_prices)
        assert loader.read_tables(SEASON)["prices"] is None


class TestTheCounts:
    def test_prints_counts_only(self, place):
        code, lines, _ = run(place)
        assert code == 0
        assert lines == ["read: 4 row(s)", "wrote: 4 row(s) to the file",
                         "FA copies on the roster that the file does not list: 1"]

    def test_a_copy_the_file_does_not_list_gets_no_row(self, place):
        _, lines, out = run(place, rows=FILE_ROWS[:2])
        sql = out.read_text(encoding="utf-8")
        assert sql.count("'fa_keep'") == 2
        assert lines[-1] == "FA copies on the roster that the file does not list: 3"

    def test_no_line_names_a_player_a_team_or_a_value(self, place):
        _, lines, _ = run(place, rows=[("Test Team One", "Nobody Here", "keep")])
        assert "".join(lines).count("Nobody") == 0 and "Test Team" not in "".join(lines)


class TestStops:
    def stopped(self, place, rows, want, **kw):
        code, lines, out = run(place, rows=rows, **kw)
        assert code == 1
        assert any(want in line for line in lines)
        assert lines[-1] == "nothing was written"
        assert not out.exists()
        assert "Nobody" not in "".join(lines) and "Test Team" not in "".join(lines)

    def test_a_team_that_does_not_resolve(self, place):
        self.stopped(place, [("No Such Team", "Alpha One", "keep")], "1 row(s) whose team does not resolve")

    def test_a_team_name_two_teams_share(self, place):
        twin = pd.DataFrame({"team_key": ["T1", "T2"], "team_name": ["Same", "same "]})
        self.stopped(place, [("Same", "Alpha One", "keep")], "team does not resolve", tables=tables(teams=twin))

    def test_a_player_that_does_not_resolve(self, place):
        self.stopped(place, [("Test Team One", "Nobody Here", "keep")], "1 row(s) whose player is not on")

    def test_a_player_on_another_teams_roster_does_not_resolve(self, place):
        self.stopped(place, [("Test Team One", "Delta Four", "keep")], "player is not on")

    def test_a_blank_player_does_not_resolve(self, place):
        self.stopped(place, [("Test Team One", None, "keep")], "player is not on")

    def test_a_player_that_resolves_to_two_copies(self, place):
        names = NAMES.assign(player_name=["Alpha One", "Alpha One", "Charlie Three", "Delta Four",
                                          "Echo Five", "Foxtrot Six"])
        self.stopped(place, [("Test Team One", "Alpha One", "keep")], "matches two FA copies",
                     tables=tables(names=names))

    def test_a_copy_listed_twice(self, place):
        self.stopped(place, FILE_ROWS + [FILE_ROWS[0]], "listing a copy already listed")

    def test_a_copy_that_is_not_an_fa_contract(self, place):
        self.stopped(place, [("Test Team One", "Charlie Three", "keep")], "not as an FA contract")

    def test_a_choice_other_than_keep_or_let_go(self, place):
        self.stopped(place, [("Test Team One", "Alpha One", "resign")], "choice is not keep or let go")

    def test_a_blank_choice(self, place):
        self.stopped(place, [("Test Team One", "Alpha One", None)], "choice is not keep or let go")

    def test_a_copy_with_no_price_list_row(self, place):
        self.stopped(place, [("Test Team One", "Alpha One", "keep")], "1 row(s) whose copy has no price-list row",
                     tables=tables(prices=PRICES.drop("s1")))

    def test_a_price_list_with_no_row_for_the_season(self, place):
        self.stopped(place, FILE_ROWS, "4 row(s) whose copy has no price-list row", tables=tables(prices=None))

    def test_a_season_dim_season_does_not_hold(self, place):
        self.stopped(place, FILE_ROWS, "--season is not a season of dim_season", season="S1999")

    def test_a_file_with_no_row(self, place):
        self.stopped(place, [], "the file holds no row")

    def test_a_file_with_a_missing_header(self, place):
        code, lines, out = run(place, header=("team", "player", "pick"))
        assert code == 1 and not out.exists()
        assert any("no team, player, choice header row" in line for line in lines)

    def test_every_problem_is_listed_and_nothing_is_written(self, place):
        code, lines, out = run(place, rows=[("No Such Team", "x", "keep"), ("Test Team One", "Nobody Here", "maybe")])
        assert code == 1 and not out.exists()
        assert sum(line.startswith("stopped:") for line in lines) == 3


class TestTheOutPath:
    def test_a_path_inside_a_git_repository_is_refused(self, tmp_path):
        repo = tmp_path / "work"
        (repo / ".git").mkdir(parents=True)
        (repo / "deep").mkdir()
        keep = make_file(tmp_path / "keep.xlsx")
        lines = []
        code = loader.load(keep, SEASON, repo / "deep" / "out.sql", tables=tables(), out=lines.append)
        assert code == 1 and not (repo / "deep" / "out.sql").exists()
        assert any("inside a git repository" in line for line in lines)

    def test_a_worktree_git_file_counts_as_a_repository(self, tmp_path):
        repo = tmp_path / "wt"
        repo.mkdir()
        (repo / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
        keep = make_file(tmp_path / "keep.xlsx")
        code = loader.load(keep, SEASON, repo / "out.sql", tables=tables(), out=lambda _l: None)
        assert code == 1 and not (repo / "out.sql").exists()

    def test_the_real_repository_is_refused(self, tmp_path):
        keep = make_file(tmp_path / "keep.xlsx")
        code = loader.load(keep, SEASON, REPO / "builder-state" / "out.sql", tables=tables(), out=lambda _l: None)
        assert code == 1

    def test_a_missing_folder_is_refused(self, tmp_path):
        keep = make_file(tmp_path / "keep.xlsx")
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
    def test_it_imports_no_database_driver_and_reads_no_env_file(self):
        source = (REPO / "scripts" / "load_contract_choices.py").read_text(encoding="utf-8")
        for word in ("psycopg", "SUPABASE_DB_URL", "use_env_file", "write_table", "environ"):
            assert word not in source

    def test_main_reads_through_the_seam_and_prints_a_stop_without_a_value(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path / "empty"))
        (tmp_path / "empty").mkdir()
        keep = make_file(tmp_path / "keep.xlsx")
        code = loader.main([str(keep), "--season", SEASON, "--out", str(tmp_path / "out.sql")])
        assert code == 1 and not (tmp_path / "out.sql").exists()
        assert "Test Team" not in capsys.readouterr().out
