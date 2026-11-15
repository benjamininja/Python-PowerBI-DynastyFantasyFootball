"""The daily admin post of the commissioners' contract lists (#545).

A fake sender stands in for the webhook in every test: nothing is posted, no
network is opened, and no real webhook value is read or needed.
"""
import json
import sys
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
    def test_only_a_merged_clean_run_posts(self):
        merged = "committed + merged 3 parquet file(s) via data PR #9"
        assert rp.contract_post_due(False, False, 0, merged)

    @pytest.mark.parametrize("dry,nocommit,code,line", [
        (True, False, 0, "committed + merged 3 parquet file(s) via data PR #9"),
        (False, True, 0, "committed + merged 3 parquet file(s) via data PR #9"),
        (False, False, 1, "committed + merged 3 parquet file(s) via data PR #9"),
        (False, False, 0, "no data changes — commit skipped"),
        (False, False, 0, "committed 3 file(s), push skipped (--no-push)"),
        (False, False, 0, "ABORTED: data PR #9 left open, merge refused (x)"),
        (False, False, 0, "commit skipped (flag)"),
    ])
    def test_any_other_run_posts_nothing(self, dry, nocommit, code, line):
        assert not rp.contract_post_due(dry, nocommit, code, line)


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
