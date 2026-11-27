"""scripts/load_owner_crosswalk.py (#548 brief 3, ADR-0025 decisions 5 and 7).
Every team, id and tab is invented here; the reader is a monkeypatched
`etl.read_sheet_tab`, so no workbook is read, no sign-in is tried and nothing
connects to a database. No real name and no real Discord id is in this file."""
import importlib
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))
import etl_helpers as etl  # noqa: E402

loader = importlib.import_module("load_owner_crosswalk")

HEADERS = ["Team Name", "Team ID", "Fantrax-TeamId", "Roster", "Discord"]
TEAMS = pd.DataFrame({"team_key": ["T1", "T2", "T3"],
                      "team_name": ["Test Team One", "Test Team Two", "Test Team Three"]})
ID_A, ID_B, ID_C, ID_D = "10000000000000001", "20000000000000002", "30000000000000003", "400000000000000004"
SECRETS = (ID_A, ID_B, ID_C, ID_D, "Test Team One", "Test Team Two", "Test Team Three", "Renamed On The Tab")


def frame(team_ids, ids, names=None):
    """The owner tab as the sheet has it: the five real headers, the loader asks for two."""
    count = len(team_ids)
    return pd.DataFrame({"Team Name": names if names is not None else ["Some Name"] * count,
                         "Team ID": team_ids,
                         "Fantrax-TeamId": ["f"] * count,
                         "Roster": ["r"] * count,
                         "Discord": ids})


GOOD = frame(["T1", "T1", "T2", "T3"], [ID_A, ID_B, ID_C, ID_D],
             ["Test Team One", "Test Team One", "Test Team Two", "Test Team Three"])


@pytest.fixture
def reader(monkeypatch):
    """Patch the sheet reader; `reader.frame` is what it returns, `reader.calls` its arguments."""
    state = type("Reader", (), {"frame": GOOD, "calls": [], "kwargs": [], "error": None})()

    def fake(sheet_id, gid, columns, optional=(), **kw):
        state.calls.append((sheet_id, gid, list(columns)))
        state.kwargs.append(kw)
        if state.error is not None:
            raise state.error
        return state.frame
    monkeypatch.setattr(etl, "read_sheet_tab", fake)
    monkeypatch.delenv("ETL_STORAGE", raising=False)
    return state


@pytest.fixture
def place(tmp_path):
    folder = tmp_path / "crosswalk"
    folder.mkdir()
    return folder


def run(place, name="out.sql", **kw):
    lines = []
    out = place / name
    code = loader.load(out, tables=kw.pop("tables", {"teams": TEAMS}), out=lines.append, **kw)
    return code, lines, out


class TestTheReadAndTheFile:
    def test_it_reads_the_owner_tab_through_the_sheet_reader_on_the_two_columns(self, place, reader):
        run(place)
        assert reader.calls == [(etl.CFG.team_sheet_id, etl.CFG.owner_sheet_gid, ["Team ID", "Discord"])]

    def test_the_id_column_is_asked_for_as_text(self, place, reader):
        run(place)
        assert reader.kwargs == [{"text": ["Discord"]}]

    def test_a_team_name_that_differs_from_the_dim_loads_when_its_team_id_matches(self, place, reader):
        reader.frame = frame(["T1", "T2"], [ID_A, ID_B], ["Renamed On The Tab", "Test Team Two"])
        code, lines, out = run(place)
        assert code == 0 and f"('T1', '{ID_A}')" in out.read_text(encoding="utf-8")
        assert "rows: 2" in lines and not [s for s in SECRETS if s in "\n".join(lines)]

    def test_the_team_name_is_never_matched(self, place, reader):
        reader.frame = frame(["No Such Key", "T2"], [ID_A, ID_B], ["Test Team One", "Test Team Two"])
        code, lines, out = run(place)
        assert code == 1 and not out.exists()
        assert any("Team ID is not in the team list (rows 2)" in line for line in lines)

    def test_the_owner_tab_has_its_own_gid_beside_the_team_tab(self):
        assert etl.CFG.owner_sheet_gid == "1895987887" and etl.CFG.owner_sheet_gid != etl.CFG.team_sheet_gid

    def test_one_transaction_deletes_then_inserts_and_ends_in_a_row_count(self, place, reader):
        code, _, out = run(place)
        sql = out.read_text(encoding="utf-8")
        assert code == 0
        assert sql.startswith("BEGIN;\nDELETE FROM shared.owner_crosswalk;\nINSERT INTO shared.owner_crosswalk")
        assert sql.index("DELETE FROM") < sql.index("INSERT INTO")
        assert sql.endswith("SELECT count(*) AS rows_loaded, count(DISTINCT team_key) AS teams "
                            "FROM shared.owner_crosswalk;\nCOMMIT;\n")
        assert sql.count("BEGIN;") == 1 and sql.count("COMMIT;") == 1
        assert f"('T1', '{ID_A}')" in sql and f"('T1', '{ID_B}')" in sql
        assert f"('T2', '{ID_C}')" in sql and f"('T3', '{ID_D}')" in sql

    def test_a_second_run_with_the_same_tab_writes_the_same_file(self, place, reader):
        _, _, one = run(place, "one.sql")
        _, _, two = run(place, "two.sql")
        assert one.read_text(encoding="utf-8") == two.read_text(encoding="utf-8")

    def test_the_rows_are_written_in_one_order_whatever_the_tab_order(self, place, reader):
        reader.frame = GOOD.iloc[::-1].reset_index(drop=True)
        _, _, out = run(place)
        reader.frame = GOOD
        _, _, again = run(place, "again.sql")
        assert out.read_text(encoding="utf-8") == again.read_text(encoding="utf-8")

    def test_it_prints_the_path_and_the_counts_and_never_an_id_or_a_name(self, place, reader):
        code, lines, out = run(place)
        text = "\n".join(lines)
        assert code == 0
        assert f"wrote: {out}" in lines
        assert "rows: 4" in lines and "teams: 3" in lines and "co-owned teams: 1" in lines
        assert not [s for s in SECRETS if s in text]

    def test_a_user_owning_two_teams_is_two_rows(self, place, reader):
        reader.frame = frame(["T1", "T2"], [ID_A, ID_A])
        code, lines, out = run(place)
        assert code == 0 and "rows: 2" in lines and "teams: 2" in lines and "co-owned teams: 0" in lines

    def test_cells_are_trimmed(self, place, reader):
        reader.frame = frame(["  T1 ", "T2"], [f" {ID_A} ", ID_B])
        code, _, out = run(place)
        assert code == 0 and f"('T1', '{ID_A}')" in out.read_text(encoding="utf-8")

    def test_a_completely_blank_row_is_skipped(self, place, reader):
        reader.frame = frame(["T1", None], [ID_A, None], ["Test Team One", None])
        code, lines, _ = run(place)
        assert code == 0 and "rows: 1" in lines

    def test_the_default_team_source_is_the_team_list_of_the_two_list_tabs(self, place, reader, monkeypatch):
        asked = []
        monkeypatch.setattr(loader, "team_list", lambda: asked.append(True) or (TEAMS, []))
        lines = []
        assert loader.load(place / "out.sql", out=lines.append) == 0 and asked == [True]

    def test_the_team_list_holds_every_leagues_teams_from_the_league_and_team_tabs(self, monkeypatch):
        import league_lists
        monkeypatch.setattr(league_lists, "read_leagues", lambda: pd.DataFrame(
            {"Sport": ["Football", "Baseball"], "League Name": ["LF", "LB"],
             "League ID": [etl.CFG.fantrax_league_id, "made-up"]}))
        monkeypatch.setattr(league_lists, "read_teams", lambda: pd.DataFrame(
            {"League Name": ["LF", "LB"], "Division": ["D1", "D2"], "Team Name": ["n1", "n2"],
             "Team ID": ["T1", "B1"], "Fantrax-TeamId": ["f1", "f2"]}))
        teams, problems = loader.team_list()
        assert problems == [] and sorted(teams["team_key"]) == ["B1", "T1"]

    def test_a_stop_on_a_list_tab_writes_nothing_and_names_the_tab(self, place, reader, monkeypatch):
        monkeypatch.setattr(loader, "team_list", lambda: (None, ["team tab: 1 row(s) repeating a Team ID (rows 3)"]))
        lines = []
        assert loader.load(place / "out.sql", out=lines.append) == 1 and not (place / "out.sql").exists()
        assert lines == ["stopped: team tab: 1 row(s) repeating a Team ID (rows 3)", "nothing was written"]

    def test_a_row_with_no_id_is_skipped_and_counted(self, place, reader):
        reader.frame = frame(["T1", "T2", "T3"], [ID_A, None, "unowned for now"])
        code, lines, out = run(place)
        assert code == 0 and "rows: 1" in lines and "rows with no id, skipped: 2" in lines
        sql = out.read_text(encoding="utf-8")
        assert f"('T1', '{ID_A}')" in sql and "T2" not in sql and "unowned" not in sql


class TestEveryStopWritesNothing:
    def stops(self, place, reader, expected):
        code, lines, out = run(place)
        assert code == 1 and not out.exists() and lines[-1] == "nothing was written"
        assert any(expected in line for line in lines), lines
        assert not [s for s in SECRETS if s in "\n".join(lines)]
        return lines

    def test_a_team_id_that_is_not_in_the_dim(self, place, reader):
        reader.frame = frame(["T1", "T9"], [ID_A, ID_B])
        lines = self.stops(place, reader, "Team ID is not in the team list (rows 3)")
        assert lines[0].startswith("stopped: 1 row(s)")

    def test_a_team_id_matches_exactly_not_by_case(self, place, reader):
        reader.frame = frame(["t1"], [ID_A])
        self.stops(place, reader, "Team ID is not in the team list (rows 2)")

    @pytest.mark.parametrize("bad", ["1" * 16, "1" * 21, "1" * 16 + "a", "12 34567890123456", "１" * 17, "-" + "1" * 17])
    def test_an_id_that_is_not_seventeen_to_twenty_digits(self, place, reader, bad):
        reader.frame = frame(["T1", "T2"], [ID_A, bad])
        self.stops(place, reader, "not 17 to 20 digits (rows 3)")

    def test_a_repeated_pair(self, place, reader):
        reader.frame = frame(["T1", "T1", "T2"], [ID_A, ID_A, ID_A])
        self.stops(place, reader, "repeating a team and id pair (rows 3)")

    def test_an_id_with_a_blank_team(self, place, reader):
        reader.frame = frame(["T1", None, "T2"], [ID_A, ID_B, None])
        self.stops(place, reader, "with an id and a blank team (rows 3)")

    @pytest.mark.parametrize("bad", ["call 555 0100", "id 12345", "1"])
    def test_a_cell_with_digits_that_is_not_an_id_is_malformed_not_skipped(self, place, reader, bad):
        reader.frame = frame(["T1", "T2"], [ID_A, bad])
        self.stops(place, reader, "not 17 to 20 digits (rows 3)")

    def test_an_empty_tab(self, place, reader):
        reader.frame = frame([], [])
        self.stops(place, reader, "has no rows")

    def test_a_tab_with_only_blank_rows(self, place, reader):
        reader.frame = frame([None, None], [None, None], [None, None])
        self.stops(place, reader, "has no rows")

    def test_a_missing_column(self, place, reader):
        reader.frame = GOOD.drop(columns=["Discord"])
        self.stops(place, reader, "lacks the column(s) Discord")
        reader.frame = GOOD.drop(columns=["Team ID"])
        self.stops(place, reader, "lacks the column(s) Team ID")
        reader.frame = pd.DataFrame()
        self.stops(place, reader, "lacks the column(s) Team ID, Discord")

    @pytest.mark.parametrize("ids,kind", [
        ([123456789012345000, 123456789012346000], "i"),
        ([float(ID_A), float(ID_B)], "f"),
        ([float(ID_A), None], "f"),
        ([18446744073709551615, 18446744073709551614], "u")])
    def test_ids_that_arrive_as_numbers_are_refused_whatever_their_digits(self, place, reader, ids, kind):
        reader.frame = frame(["T1", "T2"], ids)
        assert reader.frame["Discord"].dtype.kind == kind
        lines = self.stops(place, reader, "stored as numbers")
        assert lines[0] == ("stopped: " + loader.AS_NUMBERS)
        assert "Format, Number, Plain text" in lines[0] and "15 significant digits" in lines[0]
        assert "Discord" in lines[0]

    def test_an_id_that_is_a_number_among_text_in_one_column_is_refused(self, place, reader):
        reader.frame = GOOD.iloc[:2].copy()
        reader.frame["Discord"] = pd.Series([ID_A, 123456789012345000], dtype=object)
        self.stops(place, reader, "stored as numbers")

    def test_a_number_is_refused_even_when_a_team_would_not_resolve(self, place, reader):
        reader.frame = frame(["No Such Key"], [123456789012345000])
        lines = self.stops(place, reader, "stored as numbers")
        assert len([line for line in lines if line.startswith("stopped:")]) == 1

    def test_an_id_column_with_no_value_at_all_stops_as_no_row_with_an_id(self, place, reader):
        reader.frame = frame(["T1", "T2"], [None, None])
        self.stops(place, reader, "the owner tab has no row with an id")

    def test_every_problem_is_listed_in_one_stop(self, place, reader):
        reader.frame = frame(["T1", "No Such Key", "T2"], [ID_A, ID_B, "12"])
        code, lines, out = run(place)
        assert code == 1 and not out.exists()
        assert len([line for line in lines if line.startswith("stopped:")]) == 2

    def test_a_number_cell_the_reader_reports_prints_the_plain_text_line_and_its_rows(self, place, reader):
        reader.error = etl.SheetsNumberCells("Discord", [3, 5])
        code, lines, out = run(place)
        assert code == 1 and not out.exists()
        assert lines == ["stopped: " + loader.AS_NUMBERS,
                         "stopped: Google Sheets: 2 cell(s) of column Discord are stored as numbers (rows 3, 5)",
                         "nothing was written"]

    def test_a_sign_in_failure_prints_its_one_line_and_nothing_more(self, place, reader):
        reader.error = etl.SheetsAuthError("Sheets sign-in: GOOGLE_SHEETS_KEY_FILE is not set in .env.")
        code, lines, out = run(place)
        assert code == 1 and not out.exists()
        assert lines == ["stopped: Sheets sign-in: GOOGLE_SHEETS_KEY_FILE is not set in .env.", "nothing was written"]

    def test_an_api_failure_prints_its_first_line(self, place, reader):
        reader.error = RuntimeError("Google Sheets API: HTTP 403 (PERMISSION_DENIED)\nmore")
        code, lines, out = run(place)
        assert code == 1 and not out.exists()
        assert lines == ["stopped: Google Sheets API: HTTP 403 (PERMISSION_DENIED)", "nothing was written"]


class TestThroughTheRealReader:
    """The loader on the reader itself, with only the sheet's network side faked:
    what a real plain-text id column and a real number cell do end to end."""

    @pytest.fixture
    def sheet(self, monkeypatch):
        from test_sheets_read_text import Session
        monkeypatch.delenv("ETL_STORAGE", raising=False)
        monkeypatch.setattr(etl, "_sheets_token", lambda: "tok")

        def make(rows):
            session = Session(rows, header=HEADERS, gid=etl.CFG.owner_sheet_gid)
            monkeypatch.setattr(etl, "_make_session", lambda *a, **k: session)
            monkeypatch.setattr(loader, "team_list", lambda: (TEAMS, []))
            return session
        return make

    def test_a_text_id_column_loads_in_full(self, place, sheet):
        sheet([["Test Team One", "T1", "f1", "r", ID_A], ["Test Team One", "T1", "f1", "r", ID_B],
               ["Renamed On The Tab", "T2", "f2", "r", ID_D]])
        lines = []
        out = place / "out.sql"
        assert loader.load(out, out=lines.append) == 0
        sql = out.read_text(encoding="utf-8")
        assert f"('T1', '{ID_A}')" in sql and f"('T1', '{ID_B}')" in sql and f"('T2', '{ID_D}')" in sql
        assert "rows: 3" in lines and not [s for s in SECRETS if s in "\n".join(lines)]

    def test_any_number_cell_refuses_the_run_and_writes_nothing(self, place, sheet):
        sheet([["Test Team One", "T1", "f1", "r", ID_A], ["Test Team Two", "T2", "f2", "r", 123456789012345000]])
        lines = []
        out = place / "out.sql"
        assert loader.load(out, out=lines.append) == 1 and not out.exists()
        assert lines[0] == "stopped: " + loader.AS_NUMBERS and "(rows 3)" in lines[1]
        assert "123456789012345000" not in "\n".join(lines)

    def test_a_whole_column_stored_as_numbers_is_refused(self, place, sheet):
        sheet([["Test Team One", "T1", "f1", "r", int(ID_A)], ["Test Team Two", "T2", "f2", "r", int(ID_B)]])
        lines = []
        out = place / "out.sql"
        assert loader.load(out, out=lines.append) == 1 and not out.exists()
        assert lines[0] == "stopped: " + loader.AS_NUMBERS

    def test_a_blank_id_cell_is_skipped_and_counted(self, place, sheet):
        sheet([["Test Team One", "T1", "f1", "r", ID_A], ["Test Team Two", "T2", "f2", "r", ""]])
        lines = []
        out = place / "out.sql"
        assert loader.load(out, out=lines.append) == 0
        assert "rows: 1" in lines and "rows with no id, skipped: 1" in lines


class TestTheOutputPath:
    def test_a_path_inside_the_repository_is_refused_before_anything_is_read(self, reader):
        target = REPO / "tests" / "never_written_crosswalk.sql"
        lines = []
        assert loader.load(target, tables={"teams": TEAMS}, out=lines.append) == 1
        assert not target.exists() and reader.calls == []
        assert any("inside a git repository" in line for line in lines)

    def test_a_path_inside_the_repository_folder_that_does_not_exist_is_refused_too(self, reader):
        target = REPO / "no_such_folder" / "out.sql"
        assert loader.load(target, tables={"teams": TEAMS}, out=lambda _: None) == 1
        assert not target.parent.exists() and reader.calls == []

    def test_a_file_that_exists_is_never_overwritten(self, place, reader):
        (place / "out.sql").write_text("earlier", encoding="utf-8")
        code, lines, _ = run(place)
        assert code == 1 and (place / "out.sql").read_text(encoding="utf-8") == "earlier"
        assert reader.calls == [] and any("already exists" in line for line in lines)

    def test_a_folder_that_does_not_exist_is_refused(self, place, reader):
        code, lines, out = run(place / "missing", "out.sql")
        assert code == 1 and reader.calls == [] and any("does not exist" in line for line in lines)


class TestTheDatabaseIsNeverTouched:
    @pytest.mark.parametrize("value", ["postgres", "supabase", "parquet", "anything"])
    def test_it_reads_only_the_sheet_so_the_storage_setting_of_the_shell_does_not_matter(
            self, place, reader, monkeypatch, value):
        monkeypatch.setenv("ETL_STORAGE", value)
        code, lines, out = run(place)
        assert code == 0 and out.exists() and len(reader.calls) == 1
        assert not any("ETL_STORAGE" in line for line in lines)

    def test_the_script_names_no_database_client(self):
        text = (REPO / "scripts" / "load_owner_crosswalk.py").read_text(encoding="utf-8")
        for word in ("psycopg", "sqlalchemy", "DATABASE_URL", "connect("):
            assert word not in text


class TestMain:
    def test_main_writes_the_file_and_returns_zero(self, place, reader, monkeypatch, capsys):
        monkeypatch.setattr(loader, "team_list", lambda: (TEAMS, []))
        assert loader.main(["--out", str(place / "out.sql")]) == 0
        printed = capsys.readouterr().out
        assert "rows: 4" in printed and not [s for s in SECRETS if s in printed]

    def test_an_unexpected_error_prints_its_type_and_no_detail(self, place, reader, monkeypatch, capsys):
        def boom():
            raise ValueError(f"row holds {ID_A}")
        monkeypatch.setattr(loader, "team_list", boom)
        assert loader.main(["--out", str(place / "out.sql")]) == 1
        printed = capsys.readouterr().out
        assert "ValueError" in printed and ID_A not in printed and not (place / "out.sql").exists()

    def test_the_out_argument_is_required(self):
        with pytest.raises(SystemExit):
            loader.main([])
