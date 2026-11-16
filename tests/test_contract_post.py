"""The daily admin post of the commissioners' contract lists (#545).

A fake sender stands in for the webhook in every test: nothing is posted, no
network is opened, and no real webhook value is read or needed.
"""
import http.client
import json
import sys
from types import SimpleNamespace
from datetime import date
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import etl_contract_moves as ecm
import run_pipeline as rp

HOOK = "https://discord.example.invalid/api/webhooks/123/tokenvalue"
DAY = date(2026, 11, 16)
SOON, NOW = ecm.DUE_SOON, ecm.DUE_NOW


def row(list_name="decision", conf="A", team="t1", scorer="s1", status=SOON, **kw):
    base = {"list_name": list_name, "conference": conf, "division": "East", "team_key": team,
            "scorer_id": scorer, "gsis_id": "00-1", "player_name": f"Player {scorer}",
            "position": "WR", "nfl_team": "KC", "contract_now": "FA", "move_to": "Re-sign",
            "reason": "why", "nfl_games": 10, "roster_slot": "Active", "salary": 1000.0,
            "status": status}
    base.update(kw)
    return base


def frame(*rows):
    return pd.DataFrame(list(rows), columns=ecm.COLUMNS) if rows else ecm.empty()


TEAMS = pd.DataFrame({"team_key": ["t1", "t2"], "team_name": ["Alpha", "Bravo"]})


class Sender:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def __call__(self, url, content, filename, data):
        self.calls.append({"url": url, "content": content, "filename": filename, "data": data})
        if self.fail:
            raise self.fail


def post(previous, current, sender, webhook=HOOK):
    return rp.post_contract_moves(previous, current, TEAMS, webhook, sender=sender, today=DAY)


class TestChangeKey:
    def test_the_key_is_list_conference_team_player_status(self):
        assert ecm.CHANGE_KEY == ["list_name", "conference", "team_key", "scorer_id", "status"]

    def test_a_row_new_in_any_part_of_the_key_posts(self):
        previous = frame(row())
        for changed in (row(list_name="expiring"), row(conf="B"), row(team="t2"),
                        row(scorer="s2"), row(status=NOW)):
            sender = Sender()
            post(previous, frame(row(), changed), sender)
            assert len(sender.calls) == 1

    def test_a_column_outside_the_key_never_posts(self):
        sender = Sender()
        out = post(frame(row()), frame(row(move_to="Other text", salary=5.0, nfl_games=3)), sender)
        assert sender.calls == [] and "no new row" in out

    def test_the_message_counts_only_the_new_rows(self):
        sender = Sender()
        post(frame(row(scorer="s1")), frame(row(scorer="s1"), row(scorer="s2", status=NOW),
                                            row(scorer="s3", list_name="minor-to-1st")), sender)
        text = sender.calls[0]["content"]
        assert "2 new" in text and "1 due now" in text and "1 due within 7 days" in text


class TestWhenItPosts:
    def test_an_empty_list_posts_nothing(self):
        sender = Sender()
        out = post(frame(row()), ecm.empty(), sender)
        assert sender.calls == [] and "no post" in out

    def test_no_new_row_posts_nothing(self):
        sender = Sender()
        same = frame(row(), row(scorer="s2"))
        out = post(same, same.copy(), sender)
        assert sender.calls == [] and "no new row" in out

    def test_a_commissioner_fix_alone_posts_nothing(self):
        sender = Sender()
        post(frame(row(), row(scorer="s2")), frame(row()), sender)
        assert sender.calls == []

    def test_the_first_run_posts_everything(self):
        sender = Sender()
        current = frame(row(scorer="s1"), row(scorer="s2", conf="B", team="t2"), row(scorer="s3"))
        out = post(ecm.empty(), current, sender)
        assert len(sender.calls) == 1 and "3 new" in sender.calls[0]["content"]
        assert "3 new row(s)" in out

    def test_a_status_move_from_due_soon_to_due_now_posts(self):
        sender = Sender()
        post(frame(row(status=SOON)), frame(row(status=NOW)), sender)
        assert len(sender.calls) == 1
        assert "1 new" in sender.calls[0]["content"] and "1 due now" in sender.calls[0]["content"]

    def test_the_post_holds_the_xlsx_of_the_whole_current_list(self):
        sender = Sender()
        current = frame(row(scorer="s1"), row(scorer="s2", conf="B", team="t2"))
        post(frame(row(scorer="s1")), current, sender)
        call = sender.calls[0]
        assert call["filename"] == "contract-moves-2026-11-16.xlsx"
        book = load_workbook(BytesIO(call["data"]))
        assert book.sheetnames == ["Conference A", "Conference B"]
        counts = [book[n].max_row - 1 for n in book.sheetnames]
        assert counts == [1, 1]
        assert book[book.sheetnames[0]]["A2"].value == "Alpha"
        assert book[book.sheetnames[1]]["A2"].value == "Bravo"

    def test_the_message_names_no_team_and_no_player(self):
        sender = Sender()
        post(ecm.empty(), frame(row()), sender)
        text = sender.calls[0]["content"]
        assert "Alpha" not in text and "Player" not in text and "@" not in text


class TestUnsetAndFailed:
    @pytest.mark.parametrize("webhook", [None, ""])
    def test_an_unset_variable_logs_a_skip_and_does_not_fail(self, webhook):
        sender = Sender()
        out = post(ecm.empty(), frame(row()), sender, webhook=webhook)
        assert sender.calls == []
        assert "skipped" in out and rp.CONTRACT_WEBHOOK_ENV in out

    def test_a_failed_post_is_caught_and_the_url_is_scrubbed(self):
        sender = Sender(fail=OSError(f"cannot reach {HOOK}"))
        out = post(ecm.empty(), frame(row()), sender)
        assert out.startswith("[warn]") and "not retried" in out
        assert HOOK not in out and "tokenvalue" not in out

    @pytest.mark.parametrize("exc", [
        http.client.InvalidURL("URL can't contain control characters. '/api/webhooks/123/tokenvalue x' "
                               "(found at least ' ')"),
        ValueError("unknown url type: 'discord.example.invalid/api/webhooks/123/tokenvalue '"),
        OSError("cannot reach 123/tokenvalue"),
        ValueError("cell holds 'Secret Player Name'"),
    ])
    def test_a_failed_post_logs_the_exception_type_and_no_part_of_its_text(self, exc):
        sender = Sender(fail=exc)
        out = post(ecm.empty(), frame(row()), sender)
        assert out == f"[warn] contract-moves post failed, not retried: {type(exc).__name__}"
        for part in ("tokenvalue", "discord.example", "api/webhooks", "123", "Secret Player Name"):
            assert part not in out

    def test_a_failed_post_is_not_retried_until_the_list_gains_a_row(self):
        published = frame(row(), row(scorer="s2"))
        failing = Sender(fail=OSError("down"))
        post(frame(row()), published, failing)
        assert len(failing.calls) == 1
        again = Sender()
        post(published, published.copy(), again)
        assert again.calls == []
        post(published, frame(row(), row(scorer="s2"), row(scorer="s3")), again)
        assert len(again.calls) == 1

    def test_a_list_that_could_not_be_read_posts_nothing(self):
        sender = Sender()
        assert "skipped" in post(None, frame(row()), sender)
        assert "skipped" in post(frame(row()), None, sender)
        assert sender.calls == []


class TestGoodRun:
    def test_a_merged_data_pr_without_a_stop_flag_is_due(self):
        assert rp.contract_post_due(False, False, "committed + merged 3 parquet file(s) via data PR #9")

    def test_the_exit_code_is_not_part_of_the_gate(self):
        import inspect
        assert "code" not in inspect.signature(rp.contract_post_due).parameters

    @pytest.mark.parametrize("dry,nocommit,line", [
        (True, False, "committed + merged 3 parquet file(s) via data PR #9"),
        (False, True, "committed + merged 3 parquet file(s) via data PR #9"),
        (False, False, "no data changes — commit skipped"),
        (False, False, "committed 3 file(s), push skipped (--no-push)"),
        (False, False, "ABORTED: data PR #9 left open, merge refused (x)"),
        (False, False, "commit skipped (flag)"),
    ])
    def test_any_other_run_posts_nothing(self, dry, nocommit, line):
        assert not rp.contract_post_due(dry, nocommit, line)


class TestSnapshotRead:
    def test_a_missing_file_is_the_first_run(self, tmp_path):
        out = rp.read_contract_list(tmp_path)
        assert out is not None and out.empty

    def test_a_file_is_read_as_published(self, tmp_path):
        frame(row(), row(scorer="s2")).to_parquet(tmp_path / "fact_contract_move.parquet")
        assert len(rp.read_contract_list(tmp_path)) == 2

    def test_an_unreadable_file_is_none_not_an_empty_list(self, tmp_path, capsys):
        (tmp_path / "fact_contract_move.parquet").write_bytes(b"not a parquet file")
        assert rp.read_contract_list(tmp_path) is None
        assert "skipped" in capsys.readouterr().out

    def test_missing_team_names_fall_back_to_keys_in_the_file(self, tmp_path):
        sender = Sender()
        names = rp.read_team_names(tmp_path)
        rp.post_contract_moves(ecm.empty(), frame(row()), names, HOOK, sender=sender, today=DAY)
        book = load_workbook(BytesIO(sender.calls[0]["data"]))
        assert book[book.sheetnames[0]]["A2"].value == "t1"


class TestWebhookRequest:
    def test_a_plain_multipart_post_with_the_file_and_no_mention(self, monkeypatch, capsys):
        seen = {}
        monkeypatch.setattr(rp.urllib.request, "urlopen",
                            lambda req, timeout=None: seen.update(req=req, timeout=timeout))
        rp.send_webhook_file(HOOK, "hello", "list.xlsx", b"PK-bytes")
        req = seen["req"]
        assert req.full_url == HOOK
        assert req.get_header("Content-type").startswith("multipart/form-data; boundary=")
        assert req.get_header("User-agent").startswith("DiscordBot (https://github.com/")
        body = req.data
        assert b"PK-bytes" in body and b'filename="list.xlsx"' in body
        payload = body.split(b"\r\n\r\n", 1)[1].split(b"\r\n--", 1)[0]
        assert json.loads(payload) == {"content": "hello", "allowed_mentions": {"parse": []},
                                       "attachments": [{"id": 0, "filename": "list.xlsx"}]}
        assert HOOK not in capsys.readouterr().out

    def test_the_message_is_cut_to_discords_limit(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(rp.urllib.request, "urlopen",
                            lambda req, timeout=None: seen.update(req=req))
        rp.send_webhook_file(HOOK, "x" * 5000, "list.xlsx", b"")
        payload = seen["req"].data.split(b"\r\n\r\n", 1)[1].split(b"\r\n--", 1)[0]
        assert len(json.loads(payload)["content"]) == 1900


class TestWiring:
    def test_the_formatter_is_the_bots_own_file_with_no_discord_import(self):
        fmt = rp.contract_formatter()
        assert Path(fmt.__file__) == REPO / "discord_bot" / "contract_moves.py"
        assert not hasattr(fmt, "discord")
        text = (REPO / "discord_bot" / "contract_moves.py").read_text(encoding="utf-8")
        assert "import discord" not in text and "from discord" not in text

    def test_the_workflow_maps_the_admin_secret_by_name_only(self):
        text = (REPO / ".github" / "workflows" / "etl-daily.yml").read_text(encoding="utf-8")
        assert "DISCORD_WEBHOOK_URL_ADMIN: ${{ secrets.DISCORD_WEBHOOK_URL_ADMIN }}" in text

    def test_the_post_reads_the_environment_not_a_dotenv_file(self):
        src = (REPO / "scripts" / "run_pipeline.py").read_text(encoding="utf-8")
        assert "os.environ.get(CONTRACT_WEBHOOK_ENV)" in src
        assert 'env_value("DISCORD_WEBHOOK_URL_ADMIN"' not in src


class TestKeyEdges:
    def test_a_null_key_part_is_the_same_key_every_run_so_it_never_reposts(self):
        sender = Sender()
        gap = frame(row(conf=None), row(scorer="s2", team=None))
        post(gap, gap.copy(), sender)
        assert sender.calls == []

    def test_a_player_on_two_teams_is_two_keys(self):
        sender = Sender()
        post(frame(row(team="t1")), frame(row(team="t1"), row(team="t2", conf="B")), sender)
        assert len(sender.calls) == 1 and "1 new" in sender.calls[0]["content"]

    def test_a_traded_player_is_new_on_the_receiving_team(self):
        sender = Sender()
        post(frame(row(team="t1")), frame(row(team="t2")), sender)
        assert len(sender.calls) == 1

    def test_a_previous_list_missing_rows_posts_them_once_not_twice(self):
        sender = Sender()
        full = frame(row(), row(scorer="s2"))
        post(frame(row()), full, sender)
        post(full, full.copy(), sender)
        assert len(sender.calls) == 1


class TestMainWiring:
    """main() end to end on stubs: the order of the reads, the guards, and that
    only a fake urlopen can ever send."""

    def run(self, monkeypatch, tmp_path, capsys, argv=(), publish=("fact_contract_move",),
            step_status="ok", commit_line="committed + merged 1 parquet file(s) via data PR #9",
            previous=None, current=None, hook=HOOK):
        events, sent = [], []
        lists = iter([previous if previous is not None else ecm.empty(),
                      current if current is not None else frame(row())])

        def read_list(data_dir=None):
            events.append("read")
            return next(lists)

        class RunLog:
            run_id, warning = None, None

            def __init__(self, trigger):
                pass

            def start(self, sha):
                pass

            def finish(self, *a, **k):
                pass

        plan = {"passed": ["fantrax_core"], "failed": {}, "publish": list(publish), "restore": [],
                "unpublished": [], "notes": []}
        stubs = {
            "resolve_storage_env": lambda *a, **k: "parquet",
            "open_fantrax_session": lambda: None, "close_fantrax_session": lambda s: None,
            "fantrax_logins": lambda s: [], "fantrax_blocked": lambda s: [],
            "_load_04a": lambda: SimpleNamespace(derive_week_label=lambda cfg: "1", CFG=None),
            "build_steps": lambda profile: [], "league_today": lambda: DAY,
            "close_day_state": lambda today: {},
            "apply_cadence": lambda steps, *a, **k: (steps, {"week_key": None, "done": []}),
            "cadence_line": lambda c: "",
            "run_steps": lambda *a, **k: events.append("steps") or
                                        [{"name": "x", "status": step_status, "detail": ""}],
            "plan_publish": lambda *a, **k: plan, "review_counts": lambda: {},
            "commit_data": lambda *a, **k: events.append("commit") or commit_line,
            "summarize": lambda *a, **k: "summary", "notify": lambda text: None,
            "read_contract_list": read_list, "read_team_names": lambda: TEAMS,
            "OUT_DIR": tmp_path,
        }
        for name, value in stubs.items():
            monkeypatch.setattr(rp, name, value)
        monkeypatch.setattr(rp.etl_run_log, "RunLog", RunLog)
        monkeypatch.setattr(rp.etl_run_log, "head_sha", lambda repo: None)
        monkeypatch.setattr(rp.etl_run_log, "row_counts", lambda tables: {})
        monkeypatch.setattr(rp.etl_checks, "load_registry", lambda: {})
        monkeypatch.setattr(rp.etl_checks, "chain_tables", lambda reg: {})
        monkeypatch.setattr(rp.etl_checks, "run_suite", lambda *a, **k: [])
        monkeypatch.setattr(rp.etl_checks, "file_review", lambda *a, **k: {})
        monkeypatch.setattr(rp.urllib.request, "urlopen",
                            lambda req, timeout=None: sent.append(req.full_url))
        monkeypatch.delenv("ETL_STORAGE", raising=False)
        if hook:
            monkeypatch.setenv(rp.CONTRACT_WEBHOOK_ENV, hook)
        else:
            monkeypatch.delenv(rp.CONTRACT_WEBHOOK_ENV, raising=False)
        monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--phase", "INSEASON", *argv])
        code = rp.main()
        return code, events, sent, capsys.readouterr().out

    def test_a_good_merged_run_reads_before_and_after_and_posts_once(self, monkeypatch, tmp_path, capsys):
        code, events, sent, out = self.run(monkeypatch, tmp_path, capsys)
        assert code == 0
        assert events == ["read", "steps", "read", "commit"]
        assert sent == [HOOK] and HOOK not in out and "contract-moves post sent" in out

    def test_no_new_row_sends_nothing(self, monkeypatch, tmp_path, capsys):
        code, events, sent, out = self.run(monkeypatch, tmp_path, capsys,
                                           previous=frame(row()), current=frame(row()))
        assert sent == [] and "no new row" in out

    def test_a_nonzero_run_with_the_table_published_and_merged_still_posts(self, monkeypatch, tmp_path, capsys):
        code, events, sent, out = self.run(monkeypatch, tmp_path, capsys, step_status="failed")
        assert code == 1
        assert events == ["read", "steps", "read", "commit"]
        assert sent == [HOOK] and "contract-moves post sent" in out and HOOK not in out

    def test_a_nonzero_run_with_the_table_out_of_the_plan_posts_nothing(self, monkeypatch, tmp_path, capsys):
        code, events, sent, out = self.run(monkeypatch, tmp_path, capsys, step_status="failed", publish=())
        assert code == 1 and events == ["read", "steps", "commit"]
        assert sent == [] and "no list to compare" in out

    @pytest.mark.parametrize("line", ["no data changes — commit skipped",
                                      "ABORTED: data PR #9 left open, merge refused (x)"])
    def test_a_run_that_did_not_land_its_data_sends_nothing(self, monkeypatch, tmp_path, capsys, line):
        code, events, sent, out = self.run(monkeypatch, tmp_path, capsys, commit_line=line)
        assert sent == [] and "contract-moves post" not in out

    def test_a_run_that_did_not_publish_the_table_reads_once_and_says_why(self, monkeypatch, tmp_path, capsys):
        code, events, sent, out = self.run(monkeypatch, tmp_path, capsys, publish=())
        assert events == ["read", "steps", "commit"]
        assert sent == [] and "no list to compare" in out and "could not be read" not in out

    def test_no_commit_reads_nothing_and_sends_nothing(self, monkeypatch, tmp_path, capsys):
        code, events, sent, out = self.run(monkeypatch, tmp_path, capsys, argv=["--no-commit"])
        assert events == ["steps"] and sent == [] and "contract-moves" not in out

    def test_an_unset_variable_logs_the_skip_and_the_run_passes(self, monkeypatch, tmp_path, capsys):
        code, events, sent, out = self.run(monkeypatch, tmp_path, capsys, hook="")
        assert code == 0 and sent == [] and f"{rp.CONTRACT_WEBHOOK_ENV} is not set" in out
