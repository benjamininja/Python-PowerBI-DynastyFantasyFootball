"""scripts/load_app_roles.py (#662, ADR-0026 decision 2). Every id and tab is
invented here; the reader is a monkeypatched `etl.read_sheet_tab`, so no workbook
is read, no sign-in is tried and nothing connects to a database. No real Discord
id is in this file."""
import importlib
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))
import etl_helpers as etl  # noqa: E402
import generate_migrations as gm  # noqa: E402

loader = importlib.import_module("load_app_roles")

GID = "123456"
ID_A, ID_B, ID_C = "10000000000000001", "20000000000000002", "300000000000000003"
SECRETS = (ID_A, ID_B, ID_C)


def frame(ids, roles):
    return pd.DataFrame({"Discord": ids, "Role": roles})


GOOD = frame([ID_A, ID_B, ID_B], ["commissioner", "commissioner", "site_admin"])


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
    folder = tmp_path / "roles"
    folder.mkdir()
    return folder


def run(place, name="out.sql", gid=GID):
    lines = []
    out = place / name
    code = loader.load(out, gid, out=lines.append)
    return code, lines, out


class TestTheReadAndTheFile:
    def test_it_reads_the_named_tab_of_the_team_workbook_on_the_two_columns_with_the_id_as_text(self, place, reader):
        run(place)
        assert reader.calls == [(etl.CFG.team_sheet_id, GID, ["Discord", "Role"])]
        assert reader.kwargs == [{"text": ["Discord"]}]

    def test_one_transaction_deletes_every_row_then_inserts_and_ends_in_a_count(self, place, reader):
        code, _, out = run(place)
        sql = out.read_text(encoding="utf-8")
        assert code == 0
        assert sql.startswith("BEGIN;\nDELETE FROM shared.app_role;\nINSERT INTO shared.app_role")
        assert sql.index("DELETE FROM") < sql.index("INSERT INTO")
        assert sql.endswith("SELECT count(*) AS rows_loaded, count(DISTINCT discord_user_id) AS people "
                            "FROM shared.app_role;\nCOMMIT;\n")
        assert sql.count("BEGIN;") == 1 and sql.count("COMMIT;") == 1

    def test_a_commissioner_row_holds_the_one_league_and_a_site_admin_row_holds_every_league(self, place, reader):
        _, _, out = run(place)
        sql = out.read_text(encoding="utf-8")
        assert f"('{ID_A}', 'commissioner', 'main')" in sql
        assert f"('{ID_B}', 'commissioner', 'main')" in sql
        assert f"('{ID_B}', 'site_admin', '*')" in sql

    def test_the_league_values_come_from_the_generators_constants(self):
        assert loader.LEAGUE_OF == {"commissioner": gm.LEAGUE_PLACEHOLDER, "site_admin": gm.ALL_LEAGUES}
        assert gm.LEAGUE_PLACEHOLDER in gm.COMMISSIONER_FUNCTION_SQL
        assert gm.ALL_LEAGUES in gm.ADMIN_FUNCTION_SQL

    def test_a_person_with_both_roles_is_two_rows_and_one_person(self, place, reader):
        code, lines, _ = run(place)
        assert code == 0
        assert "rows: 3" in lines and "people: 2" in lines
        assert "commissioners: 2" in lines and "site admins: 1" in lines

    def test_a_second_run_with_the_same_tab_writes_the_same_file(self, place, reader):
        _, _, one = run(place, "one.sql")
        _, _, two = run(place, "two.sql")
        assert one.read_text(encoding="utf-8") == two.read_text(encoding="utf-8")

    def test_the_rows_are_written_in_one_order_whatever_the_tab_order(self, place, reader):
        _, _, one = run(place, "one.sql")
        reader.frame = GOOD.iloc[::-1].reset_index(drop=True)
        _, _, two = run(place, "two.sql")
        assert one.read_text(encoding="utf-8") == two.read_text(encoding="utf-8")

    def test_it_prints_the_path_and_the_counts_and_never_an_id(self, place, reader):
        code, lines, out = run(place)
        assert code == 0 and f"wrote: {out}" in lines
        assert not [s for s in SECRETS if s in "\n".join(lines)]

    def test_cells_are_trimmed_and_a_blank_row_is_skipped(self, place, reader):
        reader.frame = frame([f" {ID_A} ", None], [" commissioner ", None])
        code, lines, out = run(place)
        assert code == 0 and "rows: 1" in lines
        assert f"('{ID_A}', 'commissioner', 'main')" in out.read_text(encoding="utf-8")

    def test_every_row_is_replaced_so_a_removed_role_is_gone(self, place, reader):
        reader.frame = frame([ID_A], ["site_admin"])
        _, _, out = run(place)
        sql = out.read_text(encoding="utf-8")
        assert sql.count("DELETE FROM shared.app_role;") == 1 and ID_B not in sql


class TestEveryStopWritesNothing:
    def stops(self, place, expected):
        code, lines, out = run(place)
        assert code == 1 and not out.exists() and lines[-1] == "nothing was written"
        assert any(expected in line for line in lines), lines
        assert not [s for s in SECRETS if s in "\n".join(lines)]
        return lines

    @pytest.mark.parametrize("bad", ["1" * 16, "1" * 21, "1" * 16 + "a", "12 34567890123456", "１" * 17, "-" + "1" * 17])
    def test_an_id_that_is_not_seventeen_to_twenty_digits(self, place, reader, bad):
        reader.frame = frame([ID_A, bad], ["commissioner", "commissioner"])
        self.stops(place, "not 17 to 20 digits (rows 3)")

    @pytest.mark.parametrize("role", ["Commissioner", "admin", "owner", "site admin", "commissioner,site_admin"])
    def test_a_role_that_is_neither_word_exactly(self, place, reader, role):
        reader.frame = frame([ID_A, ID_B], ["commissioner", role])
        self.stops(place, "neither commissioner nor site_admin (rows 3)")

    def test_a_repeated_id_and_role_pair(self, place, reader):
        reader.frame = frame([ID_A, ID_A], ["commissioner", "commissioner"])
        self.stops(place, "repeating an id and role pair (rows 3)")

    def test_a_blank_id_or_a_blank_role(self, place, reader):
        reader.frame = frame([ID_A, None, ID_B], ["commissioner", "commissioner", None])
        self.stops(place, "blank id or role (rows 3, 4)")

    def test_an_empty_tab_and_a_tab_with_only_blank_rows(self, place, reader):
        reader.frame = frame([], [])
        self.stops(place, "has no rows")
        reader.frame = frame([None, None], [None, None])
        self.stops(place, "has no rows")

    def test_a_missing_column(self, place, reader):
        reader.frame = GOOD.drop(columns=["Role"])
        self.stops(place, "lacks the column(s) Role")
        reader.frame = GOOD.drop(columns=["Discord"])
        self.stops(place, "lacks the column(s) Discord")
        reader.frame = pd.DataFrame()
        self.stops(place, "lacks the column(s) Discord, Role")

    @pytest.mark.parametrize("ids", [[123456789012345000, 123456789012346000], [float(ID_A), float(ID_B)]])
    def test_ids_that_arrive_as_numbers_are_refused(self, place, reader, ids):
        reader.frame = frame(ids, ["commissioner", "site_admin"])
        lines = self.stops(place, "stored as numbers")
        assert lines[0] == "stopped: " + loader.AS_NUMBERS

    def test_every_problem_is_listed_in_one_stop(self, place, reader):
        reader.frame = frame([ID_A, "12", ID_B], ["commissioner", "commissioner", "owner"])
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

    @pytest.mark.parametrize("gid", ["", "abc", "12 3", "-5", "１２"])
    def test_a_gid_that_is_not_digits_is_refused_before_anything_is_read(self, place, reader, gid):
        code, lines, out = run(place, gid=gid)
        assert code == 1 and not out.exists() and reader.calls == []
        assert any("--gid is not the digits" in line for line in lines)


class TestTheOutputPath:
    def test_a_path_inside_the_repository_is_refused_before_anything_is_read(self, reader):
        target = REPO / "tests" / "never_written_roles.sql"
        lines = []
        assert loader.load(target, GID, out=lines.append) == 1
        assert not target.exists() and reader.calls == []
        assert any("inside a git repository" in line for line in lines)

    def test_a_file_that_exists_is_never_overwritten(self, place, reader):
        (place / "out.sql").write_text("earlier", encoding="utf-8")
        code, lines, _ = run(place)
        assert code == 1 and (place / "out.sql").read_text(encoding="utf-8") == "earlier"
        assert reader.calls == [] and any("already exists" in line for line in lines)

    def test_a_folder_that_does_not_exist_is_refused(self, place, reader):
        code, lines, _ = run(place / "missing")
        assert code == 1 and reader.calls == [] and any("does not exist" in line for line in lines)


class TestTheDatabaseIsNeverTouched:
    @pytest.mark.parametrize("value", ["postgres", "supabase", "anything"])
    def test_it_stops_when_the_shell_selects_the_database_and_reads_nothing(self, place, reader, monkeypatch, value):
        monkeypatch.setenv("ETL_STORAGE", value)
        code, lines, out = run(place)
        assert code == 1 and not out.exists() and reader.calls == []
        assert any("ETL_STORAGE selects the database" in line for line in lines)

    def test_parquet_or_unset_is_fine(self, place, reader, monkeypatch):
        monkeypatch.setenv("ETL_STORAGE", "parquet")
        assert run(place)[0] == 0

    def test_the_script_names_no_database_client(self):
        text = (REPO / "scripts" / "load_app_roles.py").read_text(encoding="utf-8")
        for word in ("psycopg", "sqlalchemy", "DATABASE_URL", "connect("):
            assert word not in text


class TestMain:
    def test_main_writes_the_file_and_returns_zero(self, place, reader, capsys):
        assert loader.main(["--gid", GID, "--out", str(place / "out.sql")]) == 0
        printed = capsys.readouterr().out
        assert "rows: 3" in printed and not [s for s in SECRETS if s in printed]

    def test_an_unexpected_error_prints_its_type_and_no_detail(self, place, reader, monkeypatch, capsys):
        def boom(*args, **kw):
            raise ValueError(f"row holds {ID_A}")
        monkeypatch.setattr(etl, "read_sheet_tab", boom)
        assert loader.main(["--gid", GID, "--out", str(place / "out.sql")]) == 1
        printed = capsys.readouterr().out
        assert "ValueError" in printed and ID_A not in printed and not (place / "out.sql").exists()

    def test_the_arguments_are_required(self):
        with pytest.raises(SystemExit):
            loader.main([])
        with pytest.raises(SystemExit):
            loader.main(["--gid", GID])
