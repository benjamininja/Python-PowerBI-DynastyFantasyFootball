"""The scheduled run's load of the four access tables (#700, #675, ADR-0026 decision 2
as amended). No database and no sheet: the readers and the connection are fakes. The
database side is proved in test_migrations_apply.py. Every id, team and league below
is made up; no printed line may hold an id."""
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import etl_helpers as etl  # noqa: E402
import load_access_tables as lat  # noqa: E402
import run_pipeline as rp  # noqa: E402
from test_run_log import pipe  # noqa: E402,F401

psycopg = pytest.importorskip("psycopg")

A, B, C = "11111111111111111", "22222222222222222", "33333333333333333"
LEAGUE_ROWS = [("baseball", "Baseball", "Made-up B", "LB"), ("football", "Football", "Made-up F", "LF")]
TEAM_ROWS = [("B01", "baseball", "fb1", "Made-up team B", "DB"), ("T01", "football", "f1", "Made-up team 1", "D1"),
             ("T02", "football", None, None, None)]
OWNER_ROWS = [("T01", A), ("T01", B), ("T02", C)]
ROLE_ROWS = [(A, "commissioner", "football"), (C, "app_admin", "*")]
PUBLISHED = pd.DataFrame({"team_key": ["T01", "T02"]})
IDS = (A, B, C)
CALLS = [lat.LEAGUES_CALL, lat.TEAMS_CALL, lat.OWNER_CALL, lat.ROLES_CALL]
GOOD_COUNTS = ((3, 3), (84, 84), (3, 3), (2, 2))


class Cursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class Conn:
    """A connection that records its calls and whether it committed."""

    def __init__(self, counts=GOOD_COUNTS, fail_on=None, error=None):
        self.counts, self.fail_on, self.error = list(counts), fail_on, error
        self.calls, self.committed = [], None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.committed = exc_type is None
        return False

    def execute(self, sql, params):
        self.calls.append((sql, params))
        if self.fail_on == len(self.calls):
            raise self.error
        return Cursor(self.counts[len(self.calls) - 1])


def run(conn=None, leagues=(LEAGUE_ROWS, []), teams=(TEAM_ROWS, []), owner=(OWNER_ROWS, [], 2),
        roles=(ROLE_ROWS, []), football=PUBLISHED, connect_to=None):
    printed, seen = [], {}
    conn = conn or Conn()

    def read(name, value):
        def reader(*args):
            seen[name] = args
            if isinstance(value, BaseException):
                raise value
            return value
        return reader
    code = lat.run(read("leagues", leagues), read("teams", teams), read("owner", owner), read("roles", roles),
                   read("football", football), connect_to or (lambda: conn), out=printed.append)
    run.seen = seen
    return code, printed, conn


def no_id(lines):
    text = "\n".join(lines)
    assert not any(i in text for i in IDS), text


GOOD_LINES = ["leagues: 3 rows before, 3 after, unchanged",
              "team list: 84 rows before, 84 after, unchanged",
              "owner crosswalk: 3 rows before, 3 after, unchanged",
              "app roles: 2 rows before, 2 after, unchanged",
              "owner tab: 2 row(s) with no id, skipped",
              "football teams: the team list and dim_fantasy_teams agree"]


class TestAGoodLoad:
    def test_the_four_functions_are_called_in_order_with_the_whole_sets_in_one_transaction(self):
        code, printed, conn = run()
        assert code == 0 and conn.committed is True
        assert [c[0] for c in conn.calls] == CALLS
        assert conn.calls[0][1] == (["baseball", "football"], ["Baseball", "Football"], ["Made-up B", "Made-up F"],
                                    ["LB", "LF"])
        assert conn.calls[1][1] == (["B01", "T01", "T02"], ["baseball", "football", "football"], ["fb1", "f1", None],
                                    ["Made-up team B", "Made-up team 1", None], ["DB", "D1", None])
        assert conn.calls[2][1] == (["T01", "T01", "T02"], [A, B, C])
        assert conn.calls[3][1] == ([A, C], ["commissioner", "app_admin"], ["football", "*"])

    def test_the_owner_tab_is_checked_against_this_runs_team_list_and_the_roles_against_its_leagues(self):
        run()
        assert run.seen["teams"] == (LEAGUE_ROWS,) and run.seen["roles"] == (LEAGUE_ROWS,)
        assert run.seen["owner"] == (TEAM_ROWS,)

    def test_the_counts_the_skipped_rows_and_the_football_agreement_are_printed(self):
        code, printed, _ = run()
        assert printed == GOOD_LINES
        no_id(printed)

    def test_a_changed_count_is_marked_changed(self):
        _, printed, _ = run(Conn(counts=((0, 3), (84, 84), (3, 4), (0, 2))))
        assert printed[:4] == ["leagues: 0 rows before, 3 after, CHANGED",
                               "team list: 84 rows before, 84 after, unchanged",
                               "owner crosswalk: 3 rows before, 4 after, CHANGED",
                               "app roles: 0 rows before, 2 after, CHANGED"]

    def test_a_football_disagreement_is_a_notice_line_and_never_a_stop(self):
        code, printed, conn = run(football=pd.DataFrame({"team_key": ["T01", "T09"]}))
        assert code == 0 and conn.committed is True
        assert printed[-1] == "football teams: 2 team key(s) differ between the team list and dim_fantasy_teams"

    def test_a_failed_read_of_the_published_teams_is_a_notice_line_and_never_a_stop(self):
        code, printed, conn = run(football=RuntimeError(f"no snapshot {A}"))
        assert code == 0 and printed[-1] == "football teams: not compared (RuntimeError)"
        no_id(printed)


class TestAFailedSheetRead:
    @pytest.mark.parametrize("which", ["leagues", "teams", "owner", "roles"])
    def test_calls_nothing_and_leaves_the_four_tables_as_they_were(self, which):
        error = RuntimeError(f"the sheet said {A}")
        code, printed, conn = run(**{which: error})
        assert code == 1 and conn.calls == [] and conn.committed is None
        assert printed[-1] == "load failed, nothing was loaded and the four tables are as they were"
        assert any("not read (RuntimeError)" in line for line in printed)
        no_id(printed)

    def test_a_league_tab_that_stops_leaves_the_tabs_that_name_its_leagues_unchecked(self):
        code, printed, conn = run(leagues=([], ["1 row(s) repeating a key or a League ID (rows 3)"]))
        assert code == 1 and conn.calls == [] and "teams" not in run.seen and "owner" not in run.seen
        assert printed == ["League Associations tab: stopped, 1 row(s) repeating a key or a League ID (rows 3)",
                           "team tab and App roles tab: not checked, they name leagues the League Associations tab gives",
                           "owner tab: not checked, it names teams the team tab gives",
                           "load failed, nothing was loaded and the four tables are as they were"]

    def test_the_sheets_sign_in_error_is_mapped_without_a_value(self):
        with pytest.raises(lat.Stop) as stop:
            lat._sheet(lambda: (_ for _ in ()).throw(etl.SheetsAuthError("Sheets sign-in: no key file")))
        assert str(stop.value) == "Sheets sign-in: no key file"

    def test_a_number_column_is_named_in_words(self):
        with pytest.raises(lat.Stop) as stop:
            lat._sheet(lambda: (_ for _ in ()).throw(etl.SheetsNumberCells("Discord", [2, 4])))
        assert "plain text" in str(stop.value) and "(rows 2, 4)" in str(stop.value)


class TestACheckThatFails:
    def test_a_bad_row_in_any_tab_loads_nothing_and_prints_row_numbers_only(self):
        code, printed, conn = run(owner=([], ["2 row(s) whose id is not 17 to 20 digits (rows 3, 5)"], 0))
        assert code == 1 and conn.calls == [] and conn.committed is None
        assert "owner tab: stopped, 2 row(s) whose id is not 17 to 20 digits (rows 3, 5)" in printed
        no_id(printed)

    def test_every_tab_that_stops_is_reported(self):
        code, printed, conn = run(teams=([], ["the team tab has no rows"]),
                                  roles=([], ["the App roles tab has no rows"]))
        assert code == 1 and conn.calls == []
        assert [line for line in printed if "stopped" in line] == [
            "team tab: stopped, the team tab has no rows",
            "App roles tab: stopped, the App roles tab has no rows"]
        assert "owner tab: not checked, it names teams the team tab gives" in printed


class TestAFunctionThatRefusesOrFails:
    def test_a_refusal_by_the_first_function_leaves_the_four_tables_as_they_were(self):
        refusal = psycopg.errors.RaiseException("League Associations tab: refused, 1 repeated key(s) or Fantrax id(s); "
                                                "nothing changed")
        code, printed, conn = run(Conn(fail_on=1, error=refusal))
        assert code == 1 and conn.committed is False and len(conn.calls) == 1
        assert printed == ["load failed, the four tables are as they were "
                           "(League Associations tab: refused, 1 repeated key(s) or Fantrax id(s); nothing changed)"]

    def test_a_refusal_by_the_last_function_rolls_back_the_first_three(self):
        refusal = psycopg.errors.RaiseException("App roles tab: refused, 1 repeated row(s); nothing changed")
        code, printed, conn = run(Conn(fail_on=4, error=refusal))
        assert code == 1 and conn.committed is False and len(conn.calls) == 4
        assert not any("rows before" in line for line in printed)
        assert "App roles tab: refused, 1 repeated row(s); nothing changed" in printed[0]

    def test_any_other_database_error_is_its_class_and_state_never_its_message(self):
        error = psycopg.errors.UniqueViolation(f"duplicate key value violates (discord_user_id)=({A})")
        code, printed, conn = run(Conn(fail_on=3, error=error))
        assert code == 1 and conn.committed is False
        assert printed == ["load failed, the four tables are as they were (UniqueViolation SQLSTATE 23505)"]
        no_id(printed)

    def test_an_unexpected_error_is_its_class_alone(self):
        code, printed, _ = run(Conn(fail_on=1, error=ValueError(f"bad value {A}")))
        assert code == 1 and printed == ["load failed, the four tables are as they were (ValueError)"]

    def test_a_missing_database_url_stops_before_any_call(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
        code, printed, _ = run(connect_to=lat.connect)
        assert code == 1
        assert printed == ["load failed, the four tables are as they were (SUPABASE_DB_URL is not set)"]


class TestThePrintedLines:
    def test_main_prefixes_every_line_and_prints_no_id_when_run_raises(self, monkeypatch, capsys):
        monkeypatch.setattr(lat, "run", lambda: (_ for _ in ()).throw(KeyError(A)))
        assert lat.main() == 1
        out = capsys.readouterr().out
        assert out == "access: load failed, the four tables are as they were (KeyError)\n"

    def test_every_line_the_step_prints_starts_with_the_marker(self, capsys):
        code, printed, _ = run()
        for line in printed:
            lat.say(line)
        assert code == 0
        assert all(line.startswith(lat.PREFIX) for line in capsys.readouterr().out.splitlines())

    def test_the_four_calls_pass_every_value_as_a_bound_parameter_never_in_the_statement(self):
        assert all("%s" in call for call in CALLS)
        _, _, conn = run()
        assert not any(i in sql for sql, _ in conn.calls for i in IDS + ("T01", "LF", "football"))


class TestTheDefaultReaders:
    """The readers the scheduled run uses, on a faked sheet reader: each reads its tab and
    hands it to the shared checks."""

    def test_each_tab_is_read_on_its_own_gid_with_the_ids_as_text(self, monkeypatch):
        calls = []
        tabs = {
            etl.CFG.league_assoc_sheet_gid: pd.DataFrame({"Sport": ["Football"], "League Name": ["F"],
                                                          "League ID": [etl.CFG.fantrax_league_id]}),
            etl.CFG.team_sheet_gid: pd.DataFrame({"League Name": ["F"], "Division": ["D"], "Team Name": ["n"],
                                                  "Team ID": ["T01"], "Fantrax-TeamId": ["f"]}),
            etl.CFG.owner_sheet_gid: pd.DataFrame({"Team ID": ["T01", "T01"], "Discord": [A, ""]}),
            etl.CFG.app_roles_sheet_gid: pd.DataFrame({"Discord": [A], "League ID": [etl.CFG.fantrax_league_id],
                                                       "Role": ["commissioner"]})}

        def fake(sheet_id, gid, columns, optional=(), **kw):
            calls.append((gid, kw.get("text")))
            return tabs[gid]
        monkeypatch.setattr(etl, "read_sheet_tab", fake)
        leagues, problems = lat.read_league_rows()
        assert problems == [] and [r[0] for r in leagues] == ["football"]
        teams, problems = lat.read_team_rows(leagues)
        assert problems == [] and teams == [("T01", "football", "f", "n", "D")]
        pairs, problems, skipped = lat.read_owner_pairs(teams)
        assert problems == [] and pairs == [("T01", A)] and skipped == 1
        rows, problems = lat.read_role_rows(leagues)
        assert problems == [] and rows == [(A, "commissioner", "football")]
        assert calls == [(etl.CFG.league_assoc_sheet_gid, ["League ID"]), (etl.CFG.team_sheet_gid, None),
                         (etl.CFG.owner_sheet_gid, ["Discord"]),
                         (etl.CFG.app_roles_sheet_gid, ["Discord", "League ID"])]


class TestTheRunStep:
    """run_pipeline.run_access_loads: not a step of any Chain, so no Chain is held."""

    @pytest.fixture(autouse=True)
    def real(self, real_access_loads):
        pass

    def fake(self, stdout="", stderr="", code=0, raises=None):
        calls = []

        def runner(cmd, **kwargs):
            calls.append((cmd, kwargs))
            if raises:
                raise raises
            return subprocess.CompletedProcess(cmd, code, stdout, stderr)
        return runner, calls

    def test_only_the_marked_lines_reach_the_notice_whatever_else_the_script_printed(self, capsys):
        runner, calls = self.fake(stdout=f"access: owner crosswalk: 3 rows before, 3 after, unchanged\nTraceback {A}\n"
                                         "access: app roles: 2 rows before, 2 after, unchanged\n",
                                  stderr=f"boom {B}")
        result = rp.run_access_loads(False, False, None, None, run=runner)
        assert result == {"name": "access_loads", "status": "ok",
                          "detail": "access: owner crosswalk: 3 rows before, 3 after, unchanged\n"
                                    "access: app roles: 2 rows before, 2 after, unchanged"}
        printed = capsys.readouterr().out
        assert A not in printed and B not in printed
        assert calls[0][0][-1].endswith("load_access_tables.py")

    def test_a_failed_script_is_failed_with_its_marked_lines(self):
        runner, _ = self.fake(stdout="access: load failed, both tables are as they were (ValueError)\n", code=1)
        result = rp.run_access_loads(False, False, None, None, run=runner)
        assert result["status"] == "failed" and result["detail"].startswith("access: load failed")

    def test_a_script_that_dies_before_it_reports_still_names_the_failure_and_no_value(self):
        runner, _ = self.fake(stdout=f"Traceback {A}", stderr=f"KeyError {B}", code=2)
        result = rp.run_access_loads(False, False, None, None, run=runner)
        assert result["status"] == "failed"
        assert "exit 2" in result["detail"] and A not in result["detail"] and B not in result["detail"]

    def test_a_timeout_is_a_failure_that_names_it(self):
        runner, _ = self.fake(raises=subprocess.TimeoutExpired("x", 1))
        result = rp.run_access_loads(False, False, None, None, run=runner)
        assert result["status"] == "failed" and "timed out" in result["detail"]

    def test_a_dry_run_prints_the_plan_and_starts_nothing(self, capsys):
        runner, calls = self.fake()
        assert rp.run_access_loads(True, False, None, None, run=runner)["status"] == "dry-run"
        assert calls == [] and "[step] access_loads (no Chain)" in capsys.readouterr().out

    def test_no_commit_skips_it_and_starts_nothing(self):
        runner, calls = self.fake()
        assert rp.run_access_loads(False, True, None, None, run=runner) is None and calls == []

    @pytest.mark.parametrize("only,groups,runs", [
        (None, None, True), ({"01c_dim_fantasy_teams"}, None, False), (None, {"rookie"}, False),
        ({"access_loads"}, None, True), ({"access_loads"}, {"rookie"}, True)])
    def test_it_runs_with_no_subset_or_when_steps_names_it(self, only, groups, runs):
        runner, calls = self.fake(stdout="access: ok\n")
        result = rp.run_access_loads(False, False, only, groups, run=runner)
        assert (result is not None) is runs and bool(calls) is runs

    def test_the_step_is_in_no_chain_and_not_in_the_step_table(self):
        assert "access_loads" not in {s["name"] for s in rp.build_steps("dynasty")}


class TestTheNotice:
    FAILED = {"name": "access_loads", "status": "failed",
              "detail": "access: load failed, both tables are as they were (UniqueViolation SQLSTATE 23505)"}
    CHANGED = {"name": "access_loads", "status": "ok",
               "detail": "access: owner crosswalk: 3 rows before, 4 after, CHANGED\n"
                         "access: app roles: 2 rows before, 2 after, unchanged"}

    def summary(self, access):
        return rp.summarize("OFFSEASON", "PRE", [{"name": "s1", "status": "ok", "detail": ""}], {}, "committed",
                            {"passed": ["c1"], "failed": {}}, None, None, access)

    def test_a_changed_count_is_flagged_in_the_notice(self):
        text = self.summary(self.CHANGED)
        assert "⚠️ access: owner crosswalk: 3 rows before, 4 after, CHANGED" in text
        assert "   access: app roles: 2 rows before, 2 after, unchanged" in text

    def test_a_failed_load_is_named_and_says_it_holds_no_chain(self):
        text = self.summary(self.FAILED)
        assert "❌ access_loads (no Chain: a failure here holds no data Chain)" in text
        assert "✅ c1: published" in text and "held" not in text.split("**Chains:**")[1]

    def test_no_access_result_adds_nothing(self):
        assert "access" not in self.summary(None)

    def test_the_run_log_error_names_the_step_and_holds_no_chain(self):
        import etl_run_log as rl
        text = rl.failure_summary([], {"failed": {}}, "committed", [], self.FAILED)
        assert text == "step access_loads failed (no Chain held)"
        assert rl.failure_summary([], {"failed": {}}, "committed", [], self.CHANGED) == "run exited non-zero"


class TestTheRunWithAFailedLoad:
    """main() end to end on the run-log test's harness: the data Chain publishes anyway."""

    @pytest.fixture(autouse=True)
    def real(self, real_access_loads):
        pass

    def test_a_failed_load_fails_the_run_but_holds_no_data_chain_and_names_itself_in_the_notice(self, pipe):
        failed = TestTheNotice.FAILED
        pipe.mp.setattr(rp, "run_access_loads", lambda *a, **k: failed)
        assert pipe.run() == 1
        assert pipe.committed and pipe.committed[0]["publish"] == ["dim_a"] and pipe.committed[0]["restore"] == []
        notice = pipe.notified[-1] if pipe.notified else (pipe.summary_file.read_text(encoding="utf-8"))
        assert "access_loads" in notice and "UniqueViolation" in notice and "🛑" not in notice

    def test_a_changed_count_in_a_good_run_is_in_the_notice_and_the_exit_is_zero(self, pipe):
        pipe.mp.setattr(rp, "run_access_loads", lambda *a, **k: TestTheNotice.CHANGED)
        assert pipe.run() == 0
        notice = pipe.notified[-1] if pipe.notified else (pipe.summary_file.read_text(encoding="utf-8"))
        assert "CHANGED" in notice
