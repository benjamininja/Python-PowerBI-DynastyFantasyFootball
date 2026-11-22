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

TEAMS = pd.DataFrame({"team_key": ["T1", "T2", "T3", "T4", "T5"],
                      "team_name": ["Test Team One", "Test Team Two", "Test Team Three", "Twin", "Twin"]})
ID_A, ID_B, ID_C, ID_D = "10000000000000001", "20000000000000002", "30000000000000003", "400000000000000004"
SECRETS = (ID_A, ID_B, ID_C, ID_D, "Test Team One", "Test Team Two", "Test Team Three")
GOOD = pd.DataFrame({"team": ["Test Team One", "Test Team One", "Test Team Two", "Test Team Three"],
                     "discord_user_id": [ID_A, ID_B, ID_C, ID_D]})


@pytest.fixture
def reader(monkeypatch):
    """Patch the sheet reader; `reader.frame` is what it returns, `reader.calls` its arguments."""
    state = type("Reader", (), {"frame": GOOD, "calls": [], "error": None})()

    def fake(sheet_id, gid, columns, optional=(), **kw):
        state.calls.append((sheet_id, gid, list(columns)))
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


def frame(team, ids):
    return pd.DataFrame({"team": team, "discord_user_id": ids})


class TestTheReadAndTheFile:
    def test_it_reads_the_owner_tab_through_the_sheet_reader_on_the_two_columns(self, place, reader):
        run(place)
        assert reader.calls == [(etl.CFG.team_sheet_id, etl.CFG.owner_sheet_gid, ["team", "discord_user_id"])]

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
        reader.frame = frame(["Test Team One", "Test Team Two"], [ID_A, ID_A])
        code, lines, out = run(place)
        assert code == 0 and "rows: 2" in lines and "teams: 2" in lines and "co-owned teams: 0" in lines

    def test_ids_read_back_as_whole_numbers_are_written_in_full(self, place, reader):
        reader.frame = frame(["Test Team One", "Test Team Two"], [int(ID_A), int(ID_B)])
        assert reader.frame["discord_user_id"].dtype.kind == "i"
        code, _, out = run(place)
        sql = out.read_text(encoding="utf-8")
        assert code == 0 and f"'{ID_A}'" in sql and f"'{ID_B}'" in sql

    def test_cells_are_trimmed(self, place, reader):
        reader.frame = frame(["  Test Team One ", "Test Team Two"], [f" {ID_A} ", ID_B])
        code, _, out = run(place)
        assert code == 0 and f"('T1', '{ID_A}')" in out.read_text(encoding="utf-8")

    def test_a_completely_blank_row_is_skipped(self, place, reader):
        reader.frame = frame(["Test Team One", None], [ID_A, None])
        code, lines, _ = run(place)
        assert code == 0 and "rows: 1" in lines

    def test_the_default_team_source_is_the_published_dim_through_the_seam(self, place, reader, monkeypatch):
        asked = []
        monkeypatch.setattr(etl, "read_table", lambda name, columns=None: asked.append((name, list(columns))) or TEAMS)
        lines = []
        assert loader.load(place / "out.sql", out=lines.append) == 0
        assert asked == [("dim_fantasy_teams", ["team_key", "team_name"])]


class TestEveryStopWritesNothing:
    def stops(self, place, reader, expected):
        code, lines, out = run(place)
        assert code == 1 and not out.exists() and lines[-1] == "nothing was written"
        assert any(expected in line for line in lines), lines
        assert not [s for s in SECRETS if s in "\n".join(lines)]
        return lines

    def test_a_team_name_that_does_not_resolve(self, place, reader):
        reader.frame = frame(["Test Team One", "No Such Team"], [ID_A, ID_B])
        lines = self.stops(place, reader, "does not resolve to one team (rows 3)")
        assert lines[0].startswith("stopped: 1 row(s)")

    def test_a_team_name_two_teams_carry(self, place, reader):
        reader.frame = frame(["Twin"], [ID_A])
        self.stops(place, reader, "does not resolve to one team (rows 2)")

    @pytest.mark.parametrize("bad", ["1" * 16, "1" * 21, "1" * 16 + "a", "12 34567890123456", "１" * 17, "-" + "1" * 17])
    def test_an_id_that_is_not_seventeen_to_twenty_digits(self, place, reader, bad):
        reader.frame = frame(["Test Team One", "Test Team Two"], [ID_A, bad])
        self.stops(place, reader, "not 17 to 20 digits (rows 3)")

    def test_a_repeated_pair(self, place, reader):
        reader.frame = frame(["Test Team One", "Test Team One", "Test Team Two"], [ID_A, ID_A, ID_A])
        self.stops(place, reader, "repeating a team and id pair (rows 3)")

    def test_a_blank_team_or_a_blank_id(self, place, reader):
        reader.frame = frame(["Test Team One", None, "Test Team Two"], [ID_A, ID_B, None])
        self.stops(place, reader, "blank team or id (rows 3, 4)")

    def test_an_empty_tab(self, place, reader):
        reader.frame = pd.DataFrame({"team": [], "discord_user_id": []})
        self.stops(place, reader, "has no rows")

    def test_a_tab_with_only_blank_rows(self, place, reader):
        reader.frame = frame([None, None], [None, None])
        self.stops(place, reader, "has no rows")

    def test_a_missing_column(self, place, reader):
        reader.frame = pd.DataFrame({"team": ["Test Team One"]})
        self.stops(place, reader, "lacks the column(s) discord_user_id")
        reader.frame = pd.DataFrame()
        self.stops(place, reader, "lacks the column(s) team, discord_user_id")

    def test_ids_that_read_back_as_floating_point(self, place, reader):
        reader.frame = frame(["Test Team One", "Test Team Two"], [float(ID_A), None])
        assert reader.frame["discord_user_id"].dtype.kind == "f"
        self.stops(place, reader, "read back as numbers with gaps")

    def test_every_problem_is_listed_in_one_stop(self, place, reader):
        reader.frame = frame(["Test Team One", "No Such Team", "Test Team Two"], [ID_A, ID_B, "12"])
        code, lines, out = run(place)
        assert code == 1 and not out.exists()
        assert len([line for line in lines if line.startswith("stopped:")]) == 2

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
        text = (REPO / "scripts" / "load_owner_crosswalk.py").read_text(encoding="utf-8")
        for word in ("psycopg", "sqlalchemy", "DATABASE_URL", "connect("):
            assert word not in text


class TestMain:
    def test_main_writes_the_file_and_returns_zero(self, place, reader, monkeypatch, capsys):
        monkeypatch.setattr(etl, "read_table", lambda name, columns=None: TEAMS)
        assert loader.main(["--out", str(place / "out.sql")]) == 0
        printed = capsys.readouterr().out
        assert "rows: 4" in printed and not [s for s in SECRETS if s in printed]

    def test_an_unexpected_error_prints_its_type_and_no_detail(self, place, reader, monkeypatch, capsys):
        def boom(name, columns=None):
            raise ValueError(f"row holds {ID_A}")
        monkeypatch.setattr(etl, "read_table", boom)
        assert loader.main(["--out", str(place / "out.sql")]) == 1
        printed = capsys.readouterr().out
        assert "ValueError" in printed and ID_A not in printed and not (place / "out.sql").exists()

    def test_the_out_argument_is_required(self):
        with pytest.raises(SystemExit):
            loader.main([])
