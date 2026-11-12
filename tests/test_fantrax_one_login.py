"""One Fantrax login per Daily Run, counted in ops.etl_run_log (#525).

Every logged-in step is its own process. The run's temp folder carries the
session and the login count from one step to the next. Fakes only: no
browser, no network, no real login, no real secret.
"""
import dataclasses
import importlib
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import etl_run_log as rl  # noqa: E402
import run_pipeline as rp  # noqa: E402
from test_run_log import pipe  # noqa: E402,F401  (the fixture)

fx = importlib.import_module("04a_fantrax_weekly_scrape")

FAKE_EMAIL = "FAKE-LOGIN-NAME-55512"
FAKE_PASSWORD = "FAKE-PASSWORD-91827"
LOGIN_URL = "https://fantrax.invalid/login"
HOME_URL = "https://fantrax.invalid/home"
STEPS = ["04s_fantrax_inseason_capture.py", "04a_fantrax_weekly_scrape.py",
         "04t_fantrax_transaction_history.py", "04a_fantrax_weekly_scrape.py",
         "04v_minor_contracts.py"]


class FakeServer:
    """Accepts only a cookie its own login issued."""

    def __init__(self):
        self.valid = set()
        self.logins = 0

    def issue(self, ctx):
        self.logins += 1
        token = f"FAKE-SESSION-{self.logins}"
        self.valid.add(token)
        ctx.jar.append({"name": "sid", "value": token, "domain": ".fantrax.invalid",
                        "path": "/", "expires": -1, "httpOnly": True, "secure": True})
        return token


class FakeResponse:
    ok = True
    status = 200

    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


class FakeContext:
    """A fresh browser context: the profile kept no cookie (the worst case)."""

    def __init__(self, server):
        self.server = server
        self.jar = []
        self.request = self

    def post(self, url, data=None, headers=None):
        if any(c["value"] in self.server.valid for c in self.jar):
            return FakeResponse({"responses": [{"data": {}}]})
        return FakeResponse({"pageError": {"code": "WARNING_NOT_LOGGED_IN"}})

    def cookies(self):
        return list(self.jar)

    def add_cookies(self, cookies):
        self.jar.extend(cookies)


class FakeLocator:
    def __init__(self, page, kind):
        self.page = page
        self.kind = kind

    @property
    def first(self):
        return self

    def fill(self, value):
        pass

    def press(self, key):
        if self.kind == "password" and key == "Enter":
            self.page.url = HOME_URL
            self.page.server.issue(self.page.ctx)

    def is_visible(self):
        return False


class FakePage:
    def __init__(self, ctx):
        self.ctx = ctx
        self.server = ctx.server
        self.url = LOGIN_URL

    def goto(self, url, **kwargs):
        pass

    def locator(self, selector, has_text=None):
        return FakeLocator(self, "password" if "password" in selector else "other")

    def wait_for_url(self, test, timeout=None):
        pass

    def wait_for_timeout(self, ms):
        pass

    def screenshot(self, path=None):
        pass


@pytest.fixture
def scrape(monkeypatch, tmp_path):
    monkeypatch.delenv(fx.FantraxScraper.SESSION_DIR_ENV, raising=False)
    monkeypatch.setattr(fx.FantraxScraper, "_creds", lambda self: (FAKE_EMAIL, FAKE_PASSWORD))
    cfg = dataclasses.replace(fx.CFG, user_data_dir=str(tmp_path / "profile"),
                              raw_dir=str(tmp_path / "raw"), login_url=LOGIN_URL)
    server = FakeServer()

    def step(script):
        monkeypatch.setattr(sys, "argv", [script])
        scraper = fx.FantraxScraper(cfg)
        ctx = FakeContext(server)
        raw = scraper._post_json(ctx, {}, "fake call")
        if scraper._session_dead(raw):
            scraper._login(FakePage(ctx))
            raw = scraper._post_json(ctx, {}, "fake call")
        assert not scraper._session_dead(raw)

    return server, step


def test_the_constants_the_two_sides_share_agree():
    assert rp.FANTRAX_SESSION_DIR_ENV == fx.FantraxScraper.SESSION_DIR_ENV
    assert rp.FANTRAX_LOGIN_LEDGER == fx.FantraxScraper.LOGIN_LEDGER


def test_a_hand_run_with_no_folder_is_unchanged_and_each_step_logs_in(scrape):
    server, step = scrape
    for script in STEPS:
        step(script)
    assert server.logins == len(STEPS)


def test_five_steps_in_one_run_log_in_once(scrape):
    server, step = scrape
    folder = rp.open_fantrax_session()
    try:
        for script in STEPS:
            step(script)
        assert server.logins == 1
        assert rp.fantrax_logins(folder) == [STEPS[0]]
    finally:
        rp.close_fantrax_session(folder)


def test_a_session_the_server_kills_mid_run_is_a_second_counted_login(scrape):
    server, step = scrape
    folder = rp.open_fantrax_session()
    try:
        step(STEPS[0])
        server.valid.clear()
        step(STEPS[1])
        step(STEPS[2])
        assert server.logins == 2
        assert rp.fantrax_logins(folder) == [STEPS[0], STEPS[1]]
    finally:
        rp.close_fantrax_session(folder)


def test_a_third_login_in_one_run_is_refused_and_its_step_fails(scrape):
    server, step = scrape
    folder = rp.open_fantrax_session()
    try:
        step(STEPS[0])
        server.valid.clear()
        step(STEPS[1])
        server.valid.clear()
        with pytest.raises(fx.LoginCapReached):
            step(STEPS[2])
        assert server.logins == 2
        assert rp.fantrax_logins(folder) == [STEPS[0], STEPS[1]]
        assert rp.fantrax_blocked(folder) == [STEPS[2]]
    finally:
        rp.close_fantrax_session(folder)


def test_a_step_with_a_live_session_still_runs_after_the_cap_is_reached(scrape):
    server, step = scrape
    folder = rp.open_fantrax_session()
    try:
        step(STEPS[0])
        server.valid.clear()
        step(STEPS[1])
        step(STEPS[2])
        step(STEPS[4])
        assert server.logins == 2
        assert rp.fantrax_blocked(folder) == []
    finally:
        rp.close_fantrax_session(folder)


def test_a_blocked_login_touches_no_page(scrape):
    server, step = scrape
    folder = rp.open_fantrax_session()
    try:
        for _ in range(2):
            server.valid.clear()
            step(STEPS[0])
        server.valid.clear()
        scraper = fx.FantraxScraper(dataclasses.replace(
            fx.CFG, user_data_dir=str(folder / "p"), raw_dir=str(folder / "r")))

        class NoPage:
            def __getattr__(self, name):
                raise AssertionError("the blocked login touched the page")
        with pytest.raises(fx.LoginCapReached) as caught:
            scraper._login(NoPage())
        assert FAKE_PASSWORD not in str(caught.value)
    finally:
        rp.close_fantrax_session(folder)


def test_a_run_with_no_ledger_counts_zero():
    folder = rp.open_fantrax_session()
    try:
        assert rp.fantrax_logins(folder) == []
    finally:
        rp.close_fantrax_session(folder)
    assert rp.fantrax_logins(None) == []


def test_no_credential_value_reaches_the_ledger_or_the_output(scrape, capsys):
    server, step = scrape
    folder = rp.open_fantrax_session()
    try:
        for script in STEPS:
            step(script)
        ledger = (folder / rp.FANTRAX_LOGIN_LEDGER).read_text(encoding="utf-8")
    finally:
        rp.close_fantrax_session(folder)
    shown = capsys.readouterr()
    for hidden in (FAKE_EMAIL, FAKE_PASSWORD, "FAKE-SESSION-1"):
        assert hidden not in ledger
        assert hidden not in shown.out + shown.err


def test_the_folder_and_the_variable_are_gone_when_the_run_closes():
    folder = rp.open_fantrax_session()
    assert os.environ[rp.FANTRAX_SESSION_DIR_ENV] == str(folder)
    assert folder.is_dir()
    rp.close_fantrax_session(folder)
    assert rp.FANTRAX_SESSION_DIR_ENV not in os.environ
    assert not folder.exists()


class Recorder:
    def __init__(self, monkeypatch):
        self.updates = []
        monkeypatch.setattr(rl, "enabled", lambda: True)
        monkeypatch.setattr(rl, "_count", lambda sql: 0)
        monkeypatch.setattr(rl, "_write", self._write)

    def _write(self, sql, params):
        if sql.startswith("UPDATE"):
            self.updates.append((sql, params))


@pytest.fixture
def logged(monkeypatch, pipe):
    rec = Recorder(monkeypatch)
    seen = {}

    def steps_log_in(n):
        def mid_run():
            folder = Path(os.environ[rp.FANTRAX_SESSION_DIR_ENV])
            seen["folder"] = folder
            with (folder / rp.FANTRAX_LOGIN_LEDGER).open("a", encoding="utf-8") as f:
                f.write("04a_fantrax_weekly_scrape.py\n" * n)
        pipe.mid_run = mid_run

    return rec, seen, steps_log_in


def test_the_run_log_row_carries_the_count(pipe, logged):
    rec, seen, steps_log_in = logged
    steps_log_in(1)
    assert pipe.run() == 0
    sql, params = rec.updates[-1]
    assert "fantrax_logins = %s" in sql
    assert params[-2] == 1
    assert not seen["folder"].exists()
    assert rp.FANTRAX_SESSION_DIR_ENV not in os.environ
    assert not pipe.notified[0].startswith("⚠️")


def test_a_run_with_no_login_writes_zero(pipe, logged):
    rec, seen, steps_log_in = logged
    steps_log_in(0)
    assert pipe.run() == 0
    assert rec.updates[-1][1][-2] == 0


def test_a_second_login_is_counted_and_warned(pipe, logged):
    rec, seen, steps_log_in = logged
    steps_log_in(2)
    assert pipe.run() == 0
    assert rec.updates[-1][1][-2] == 2
    assert "2 Fantrax logins" in pipe.notified[0]


def test_a_run_that_raises_still_writes_the_count_and_cleans_up(pipe, logged):
    rec, seen, steps_log_in = logged
    steps_log_in(1)
    boom = pipe.mid_run

    def raising():
        boom()
        raise RuntimeError("step blew up")
    pipe.mid_run = raising
    with pytest.raises(RuntimeError):
        pipe.run()
    sql, params = rec.updates[-1]
    assert params[1] == "failed"
    assert params[-2] == 1
    assert not seen["folder"].exists()
    assert rp.FANTRAX_SESSION_DIR_ENV not in os.environ


def test_a_blocked_step_holds_its_chain_and_the_run_log_names_the_cap(pipe, logged):
    rec, seen, steps_log_in = logged
    pipe.results = [{"name": "s1", "status": "failed", "detail": ""}]

    def mid_run():
        folder = Path(os.environ[rp.FANTRAX_SESSION_DIR_ENV])
        (folder / rp.FANTRAX_LOGIN_LEDGER).write_text("a.py\nb.py\n", encoding="utf-8")
        (folder / rp.FANTRAX_BLOCKED_LEDGER).write_text("04t_fantrax_transaction_history.py\n",
                                                       encoding="utf-8")
    pipe.mid_run = mid_run
    assert pipe.run() == 1
    sql, params = rec.updates[-1]
    assert params[1] == "failed"
    assert "Fantrax login cap reached (1 step(s) blocked)" in params[4]
    assert "step s1 failed" in params[4]
    assert params[-2] == 2
    assert pipe.committed[0]["publish"] == []
    assert pipe.committed[0]["restore"] == ["dim_a"]
    assert pipe.notified[0].startswith("⚠️ Fantrax login cap reached")


def test_failure_summary_names_the_cap_with_no_script_name():
    text = rl.failure_summary([], None, "", ["04t_fantrax_transaction_history.py"])
    assert text == "Fantrax login cap reached (1 step(s) blocked)"


def test_a_dry_run_makes_no_folder(pipe, logged):
    rec, seen, steps_log_in = logged
    pipe.mid_run = lambda: seen.update(env=os.environ.get(rp.FANTRAX_SESSION_DIR_ENV))
    assert pipe.run("--dry-run") == 0
    assert seen["env"] is None
    assert rec.updates == []
