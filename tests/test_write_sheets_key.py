"""The Sheets key writer (#643), on a fake key with no real private key."""
import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import check_sheets_key  # noqa: E402
import etl_helpers as etl  # noqa: E402
import write_sheets_key as w  # noqa: E402

PLANTED = "PLANTED-FAKE-PRIVATE-KEY-TEXT"
KEY = {"type": "service_account", "client_email": "FAKE-SERVICE-ACCOUNT-ID", "private_key": PLANTED}
GOOD = json.dumps(KEY, indent=2)


def _run(monkeypatch, tmp_path, raw):
    out = tmp_path / "key.json"
    if raw is None:
        monkeypatch.delenv(w.SECRET_ENV, raising=False)
    else:
        monkeypatch.setenv(w.SECRET_ENV, raw)
    return w.main(["write_sheets_key.py", str(out)]), out


@pytest.mark.parametrize("raw", [
    GOOD, "﻿" + GOOD, GOOD.replace("\n", "\r\n"), GOOD + "\n", "  \n" + GOOD + "\r\n\r\n",
])
def test_good_key_variants_are_written_clean(raw, monkeypatch, tmp_path, capsys):
    code, out = _run(monkeypatch, tmp_path, raw)
    assert code == 0
    assert json.loads(out.read_text(encoding="utf-8")) == KEY
    assert not out.read_bytes().startswith(b"\xef\xbb\xbf")
    assert PLANTED not in capsys.readouterr().out
    if os.name != "nt":
        assert out.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("raw,needle", [
    (None, "empty"),
    ("", "empty"),
    ("﻿ \n", "empty"),
    ("{" + PLANTED + " not json", "not JSON"),
    ("[1, 2]", "not an object"),
    (json.dumps({k: v for k, v in KEY.items() if k != "private_key"}), "private_key"),
    (json.dumps({k: v for k, v in KEY.items() if k != "client_email"}), "client_email"),
    (json.dumps({k: v for k, v in KEY.items() if k != "type"}), "type"),
    (json.dumps({**KEY, "private_key": ""}), "private_key"),
    (json.dumps({**KEY, "type": PLANTED}), "type"),
])
def test_bad_key_names_the_check_and_prints_no_value(raw, needle, monkeypatch, tmp_path, capsys):
    code, out = _run(monkeypatch, tmp_path, raw)
    text = capsys.readouterr()
    assert code == 1
    assert not out.exists()
    line = text.out.strip()
    assert needle in line and "\n" not in line
    assert PLANTED not in text.out and PLANTED not in text.err
    assert "FAKE-SERVICE-ACCOUNT-ID" not in text.out


def test_json_error_gives_line_column_and_position_only(monkeypatch, tmp_path, capsys):
    code, _ = _run(monkeypatch, tmp_path, '{\n"a": ' + PLANTED)
    line = capsys.readouterr().out
    assert code == 1
    assert "line 2, column 6, char 7" in line
    assert PLANTED not in line


def test_no_output_path_stops(monkeypatch, capsys):
    monkeypatch.delenv(w.PATH_ENV, raising=False)
    monkeypatch.setenv(w.SECRET_ENV, GOOD)
    assert w.main(["write_sheets_key.py"]) == 1
    assert PLANTED not in capsys.readouterr().out


def test_unwritable_path_stops_without_the_path_or_value(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv(w.SECRET_ENV, GOOD)
    bad = tmp_path / "no-dir" / "key.json"
    assert w.main(["write_sheets_key.py", str(bad)]) == 1
    out = capsys.readouterr().out
    assert str(tmp_path) not in out and PLANTED not in out


def test_sheets_token_json_error_names_line_and_column_only(monkeypatch, tmp_path):
    key = tmp_path / "key.json"
    key.write_text("x", encoding="utf-8")
    monkeypatch.setenv(etl.SHEETS_KEY_ENV, str(key))

    def loader(path, scopes):
        json.loads("{\n" + PLANTED)

    import types
    google = types.ModuleType("google")
    auth = types.ModuleType("google.auth")
    transport = types.ModuleType("google.auth.transport")
    requests_mod = types.ModuleType("google.auth.transport.requests")
    requests_mod.Request = lambda: None
    oauth2 = types.ModuleType("google.oauth2")
    sa = types.ModuleType("google.oauth2.service_account")
    sa.Credentials = types.SimpleNamespace(from_service_account_file=loader)
    oauth2.service_account = sa
    for name, mod in {"google": google, "google.auth": auth, "google.auth.transport": transport,
                      "google.auth.transport.requests": requests_mod, "google.oauth2": oauth2,
                      "google.oauth2.service_account": sa}.items():
        monkeypatch.setitem(sys.modules, name, mod)
    with pytest.raises(etl.SheetsAuthError) as info:
        etl._sheets_token()
    msg = str(info.value)
    assert "line 2 column" in msg and etl.SHEETS_KEY_ENV in msg
    assert PLANTED not in msg and "\n" not in msg


def test_check_script_prints_ok_and_a_count_only(monkeypatch, capsys):
    import pandas as pd
    df = pd.DataFrame({c: [PLANTED] * 3 for c in check_sheets_key.COLUMNS})
    monkeypatch.setattr(etl, "read_sheet_tab", lambda *a, **k: df)
    assert check_sheets_key.main() == 0
    out = capsys.readouterr().out
    assert out.startswith("ok") and "3 rows" in out and PLANTED not in out


@pytest.mark.parametrize("exc,needle", [
    (etl.SheetsAuthError("Sheets sign-in: no."), "Sheets sign-in"),
    (RuntimeError("Google Sheets API: HTTP 403 (PERMISSION_DENIED)"), "403"),
    (KeyError(PLANTED), "KeyError"),
])
def test_check_script_names_one_failing_check(exc, needle, monkeypatch, capsys):
    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(etl, "read_sheet_tab", boom)
    assert check_sheets_key.main() == 1
    out = capsys.readouterr().out
    assert needle in out and PLANTED not in out and out.startswith("FAIL")
