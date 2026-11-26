"""The service-account read of the team-manifest (#609), on fakes only.

No network, no key, no google-auth install: the Sheets API is a recording
fake session, and the google modules are injected through sys.modules.
"""
import io
import json
import sys
import types
from pathlib import Path
from urllib.parse import unquote

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))

import etl_helpers as etl

REPO = Path(__file__).resolve().parent.parent
GID = "178660131"
TITLE = "Owner's Teams"
HEADER = ["Division", "Team Name", "Team ID", "Owner Email", "Fantrax-TeamId", "Roster",
          "Team Abbreviation"]
ROWS = [
    ["Riddell", "Alpha", "A01", "a@example.com", "fx1", "x", "ALP"],
    ["Riddell", "Bravo", "A02", "b@example.com", "fx2", "x", ""],
    ["Wilson", "Charlie", "B01", "c@example.com", "fx3", "x", "CHA"],
    ["Wilson", "Delta", "B02", "d@example.com", "fx4", "", ""],
]
WANTED = ["Team ID", "Team Name", "Fantrax-TeamId", "Division"]
OPTIONAL = ["Team Abbreviation"]
TOKEN = "tok-abc"


class FakeResp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class FakeSession:
    def __init__(self, header=HEADER, rows=ROWS, gid=GID, status=200):
        self.header, self.rows, self.gid, self.status = header, rows, gid, status
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": unquote(url), "params": params, "headers": headers or {}})
        if self.status != 200:
            return FakeResp(self.status, {"error": {"status": "UNAUTHENTICATED",
                                                    "message": "secret-body-text"}})
        if url.endswith("values:batchGet"):
            value_ranges = []
            for key, rng in params:
                if key != "ranges":
                    continue
                letter = rng.rsplit("!", 1)[1].split(":")[0]
                col = [self.header[ord(letter) - 65]] + [r[ord(letter) - 65] for r in self.rows]
                while col and col[-1] == "":
                    col.pop()
                value_ranges.append({"range": rng, "values": [col]})
            return FakeResp(200, {"valueRanges": value_ranges})
        if "/values/" in unquote(url):
            return FakeResp(200, {"range": f"'{TITLE}'!1:1", "values": [self.header]})
        return FakeResp(200, {"sheets": [
            {"properties": {"sheetId": 0, "title": "Commissioners"}},
            {"properties": {"sheetId": int(self.gid), "title": TITLE}},
        ]})


def _csv_expected(header, rows, columns):
    text = "\n".join([",".join(header)] + [",".join(r) for r in rows])
    return pd.read_csv(io.StringIO(text))[columns]


def test_parse_matches_the_csv_read_of_the_same_content():
    got = etl.read_sheet_tab("SID", GID, WANTED, OPTIONAL, token=TOKEN, session=FakeSession())
    want = _csv_expected(HEADER, ROWS, ["Team ID", "Team Name", "Fantrax-TeamId", "Division",
                                        "Team Abbreviation"])
    assert list(got.columns) == list(want.columns)
    pd.testing.assert_frame_equal(got, want)


def test_only_the_wanted_columns_are_requested():
    fake = FakeSession()
    got = etl.read_sheet_tab("SID", GID, WANTED, OPTIONAL, token=TOKEN, session=fake)
    asked = [rng for call in fake.calls if call["params"] and isinstance(call["params"], list)
             for key, rng in call["params"] if key == "ranges"]
    letters = sorted(r.rsplit("!", 1)[1].split(":")[0] for r in asked)
    assert letters == ["A", "B", "C", "E", "G"]
    assert all(r.startswith("'Owner''s Teams'!") for r in asked)
    assert "Owner Email" not in got.columns and "Roster" not in got.columns
    assert not any("Commissioners" in str(c["params"]) for c in fake.calls)


def test_a_missing_optional_column_is_left_out_and_a_missing_required_one_too():
    header = [h for h in HEADER if h not in ("Team Abbreviation", "Team Name")]
    rows = [[v for h, v in zip(HEADER, r) if h in header] for r in ROWS]
    got = etl.read_sheet_tab("SID", GID, WANTED, OPTIONAL, token=TOKEN,
                             session=FakeSession(header, rows))
    assert list(got.columns) == ["Team ID", "Fantrax-TeamId", "Division"]


def test_a_gid_with_no_tab_raises():
    with pytest.raises(RuntimeError, match="no tab with gid"):
        etl.read_sheet_tab("SID", "999", WANTED, token=TOKEN, session=FakeSession())


def test_every_request_carries_the_bearer_token():
    fake = FakeSession()
    etl.read_sheet_tab("SID", GID, WANTED, OPTIONAL, token=TOKEN, session=fake)
    assert len(fake.calls) == 3
    assert all(c["headers"].get("Authorization") == f"Bearer {TOKEN}" for c in fake.calls)


@pytest.mark.parametrize("token", ["", None])
def test_no_request_leaves_without_a_token(token, monkeypatch):
    fake = FakeSession()
    monkeypatch.delenv(etl.SHEETS_KEY_ENV, raising=False)
    with pytest.raises(etl.SheetsAuthError):
        etl.read_sheet_tab("SID", GID, WANTED, token=token, session=fake)
    assert fake.calls == []


def test_an_http_error_names_the_status_and_not_the_body():
    with pytest.raises(RuntimeError) as info:
        etl.read_sheet_tab("SID", GID, WANTED, token=TOKEN, session=FakeSession(status=401))
    assert "HTTP 401 (UNAUTHENTICATED)" in str(info.value)
    assert "secret-body-text" not in str(info.value)


@pytest.mark.parametrize("body, expect, shown", [
    ({"error": {"status": "PERMISSION_DENIED", "message": "secret-body-text"}}, (), "PERMISSION_DENIED"),
    ({"error": "secret-body-text"}, (), "no status"),
    ({"range": "x"}, ("valueRanges",), "valueRanges"),
])
def test_a_200_with_an_error_key_or_a_missing_key_stops_with_no_body_text(body, expect, shown):
    class Session:
        def get(self, url, params=None, headers=None, timeout=None):
            return FakeResp(200, body)

    with pytest.raises(RuntimeError) as info:
        etl._sheets_get(Session(), TOKEN, "https://example.test/x", expect=expect)
    assert shown in str(info.value)
    assert "secret-body-text" not in str(info.value)
    assert "\n" not in str(info.value)


def _fake_google(monkeypatch, loader):
    google = types.ModuleType("google")
    auth = types.ModuleType("google.auth")
    transport = types.ModuleType("google.auth.transport")
    treq = types.ModuleType("google.auth.transport.requests")
    treq.Request = lambda: object()
    oauth2 = types.ModuleType("google.oauth2")
    sa = types.ModuleType("google.oauth2.service_account")
    sa.Credentials = types.SimpleNamespace(from_service_account_file=loader)
    oauth2.service_account = sa
    for name, mod in {"google": google, "google.auth": auth, "google.auth.transport": transport,
                      "google.auth.transport.requests": treq, "google.oauth2": oauth2,
                      "google.oauth2.service_account": sa}.items():
        monkeypatch.setitem(sys.modules, name, mod)


def _one_line_naming_the_variable(err, *forbidden):
    msg = str(err)
    assert etl.SHEETS_KEY_ENV in msg
    assert "\n" not in msg
    assert err.__cause__ is None and (err.__suppress_context__ or err.__context__ is None)
    for text in forbidden:
        assert text not in msg


def test_token_unset_variable_stops_with_one_line(monkeypatch):
    monkeypatch.delenv(etl.SHEETS_KEY_ENV, raising=False)
    with pytest.raises(etl.SheetsAuthError) as info:
        etl._sheets_token()
    _one_line_naming_the_variable(info.value)


@pytest.mark.parametrize("kind", ["missing", "directory"])
def test_token_missing_or_unreadable_file_stops_with_one_line_and_no_path(kind, monkeypatch, tmp_path):
    path = tmp_path / "no-such-key.json" if kind == "missing" else tmp_path
    monkeypatch.setenv(etl.SHEETS_KEY_ENV, str(path))
    with pytest.raises(etl.SheetsAuthError) as info:
        etl._sheets_token()
    _one_line_naming_the_variable(info.value, str(path), str(tmp_path))


def test_token_key_the_loader_rejects_never_leaks_its_content(monkeypatch, tmp_path):
    secret = "PLANTED-PRIVATE-KEY-TEXT"
    key = tmp_path / "key.json"
    key.write_text(json.dumps({"private_key": secret}), encoding="utf-8")
    monkeypatch.setenv(etl.SHEETS_KEY_ENV, str(key))

    def loader(path, scopes):
        raise ValueError(f"bad key {secret} at {path}")

    _fake_google(monkeypatch, loader)
    with pytest.raises(etl.SheetsAuthError) as info:
        etl._sheets_token()
    _one_line_naming_the_variable(info.value, secret, str(key), str(tmp_path))
    assert "ValueError" in str(info.value)


def test_token_signs_in_read_only_and_returns_the_token(monkeypatch, tmp_path):
    key = tmp_path / "key.json"
    key.write_text("{}", encoding="utf-8")
    monkeypatch.setenv(etl.SHEETS_KEY_ENV, str(key))
    seen = {}

    class Creds:
        token = None

        def refresh(self, request):
            self.token = "fresh-token"

    def loader(path, scopes):
        seen["path"], seen["scopes"] = path, scopes
        return Creds()

    _fake_google(monkeypatch, loader)
    assert etl._sheets_token() == "fresh-token"
    assert seen["scopes"] == ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    assert seen["path"] == str(key)


def _cell(cell_id):
    nb = json.loads((REPO / "notebooks" / "01c_dim_fantasy_teams_seed.ipynb").read_text(encoding="utf-8"))
    cell = next(c for c in nb["cells"] if c["id"] == cell_id)
    return cell["source"] if isinstance(cell["source"], str) else "".join(cell["source"])


LEAGUES_GID = "294450686"


def _run_read_cell(read):
    fake_etl = types.SimpleNamespace(SheetsAuthError=etl.SheetsAuthError, read_sheet_tab=read)
    cfg = types.SimpleNamespace(team_sheet_id="SID", team_sheet_gid=GID,
                                league_assoc_sheet_gid=LEAGUES_GID)
    ns = {"etl": fake_etl, "CFG": cfg}
    exec(_cell("25f3db4f"), ns)
    return ns


def test_01c_turns_a_sign_in_failure_into_a_one_line_exit():
    line = f"Sheets sign-in: {etl.SHEETS_KEY_ENV} is not set in .env."

    def read(*args, **kwargs):
        raise etl.SheetsAuthError(line)

    with pytest.raises(SystemExit) as info:
        _run_read_cell(read)
    assert str(info.value) == line
    assert info.value.__cause__ is None


def test_01c_reads_only_the_columns_its_build_cell_maps():
    seen = {}

    def read(sheet_id, gid, columns, optional=(), text=()):
        seen[gid] = dict(sheet_id=sheet_id, columns=columns, optional=optional, text=list(text))
        return pd.DataFrame({"Team ID": ["A01"]}) if gid == GID else pd.DataFrame({"League ID": ["x"]})

    ns = _run_read_cell(read)
    assert set(seen) == {GID, LEAGUES_GID}
    assert {s["sheet_id"] for s in seen.values()} == {"SID"}
    build = {"pd": pd, "LeagueConfig": object}
    src = _cell("39c742bb")
    exec(src[: src.index("dim_fantasy_teams = build_dim_fantasy_teams")], build)
    assert seen[GID]["columns"] == [*build["_COL_MAP"], "League Name"]
    assert seen[LEAGUES_GID]["columns"] == ["Sport", "League Name", "League ID"]
    assert seen[LEAGUES_GID]["text"] == ["League ID"]
    assert not seen[GID]["optional"] and not seen[LEAGUES_GID]["optional"]
    assert list(ns["teams_raw"].columns) == ["Team ID"]
    assert list(ns["leagues_raw"].columns) == ["League ID"]


def test_01c_reads_the_league_tab_named_in_league_config():
    assert etl.CFG.league_assoc_sheet_gid == LEAGUES_GID


def test_the_anonymous_csv_url_is_gone():
    assert not hasattr(etl.CFG, "team_sheet_csv_url")
    assert "export?format=csv" not in (REPO / "notebooks" / "etl_helpers.py").read_text(encoding="utf-8")
