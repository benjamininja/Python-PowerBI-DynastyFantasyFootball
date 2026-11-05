"""notify() sends a Discord-form User-Agent and never prints the webhook URL (#362).

urlopen is mocked in every test; nothing is posted.
"""
import io
import json
import sys
import urllib.error
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import run_pipeline as rp

URL = "https://discord.example.invalid/api/webhooks/123/tokenvalue"


def test_notify_sends_user_agent_and_json_body(monkeypatch, capsys):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", URL)
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["req"] = req
        return None

    monkeypatch.setattr(rp.urllib.request, "urlopen", fake_urlopen)
    rp.notify("hello")
    req = seen["req"]
    ua = req.get_header("User-agent")
    assert ua.startswith("DiscordBot (https://github.com/")
    assert req.get_header("Content-type") == "application/json"
    assert json.loads(req.data.decode("utf-8")) == {"content": "hello"}
    out = capsys.readouterr().out
    assert "[ok]" in out and URL not in out


def test_notify_http_error_is_caught_and_url_not_printed(monkeypatch, capsys):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", URL)

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(URL, 403, "Forbidden", {}, io.BytesIO(b""))

    monkeypatch.setattr(rp.urllib.request, "urlopen", fake_urlopen)
    rp.notify("hello")
    out = capsys.readouterr().out
    assert "[warn] webhook failed" in out
    assert "403" in out
    assert URL not in out and "tokenvalue" not in out


def test_notify_error_text_holding_url_is_scrubbed(monkeypatch, capsys):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", URL)

    def fake_urlopen(req, timeout=None):
        raise OSError(f"cannot reach {URL}")

    monkeypatch.setattr(rp.urllib.request, "urlopen", fake_urlopen)
    rp.notify("hello")
    out = capsys.readouterr().out
    assert "[warn]" in out and URL not in out
