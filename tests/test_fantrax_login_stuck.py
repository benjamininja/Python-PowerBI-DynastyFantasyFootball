"""A Fantrax login that never finishes is named, not hidden (#721).

The scheduled run's login stayed on /login from 2026-11-23: 04s stopped with
the not-logged-in error, 04a with KeyError: 'data', and the log said nothing of
what the page showed. Fakes only: no browser, no network, no real login, no
real secret.
"""
import dataclasses
import importlib
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

fx = importlib.import_module("04a_fantrax_weekly_scrape")

FAKE_EMAIL = "FAKE-LOGIN-NAME-72101"
FAKE_PASSWORD = "FAKE-PASSWORD-72102"
LOGIN_URL = "https://fantrax.invalid/login"
HOME_URL = "https://fantrax.invalid/home"
DEAD = {"pageError": {"code": "WARNING_NOT_LOGGED_IN"}}
LIVE = {"responses": [{"data": {"paginatedResultSet": {"totalNumPages": 1}}}]}


class FakeResponse:
    ok = True
    status = 200

    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


class FakeContext:
    def __init__(self, live_after_login=False):
        self.live = False
        self.live_after_login = live_after_login
        self.posts = 0
        self.closed = False
        self.request = self

    def post(self, url, data=None, headers=None):
        self.posts += 1
        return FakeResponse(LIVE if self.live else DEAD)

    def cookies(self):
        return []

    def add_cookies(self, cookies):
        pass

    def new_page(self):
        return FakePage(self)

    def close(self):
        self.closed = True


class FakeLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    @property
    def first(self):
        return self

    def fill(self, value):
        pass

    def press(self, key):
        if "password" in self.selector and key == "Enter" and self.page.ctx.live_after_login:
            self.page.ctx.live = True
            self.page.url = HOME_URL

    def is_visible(self):
        if self.selector in self.page.broken:
            raise RuntimeError("locator failed")
        return self.selector in self.page.visible


class FakePage:
    """A login page that keeps the browser on /login unless the context goes live."""

    def __init__(self, ctx, visible=(), title="Fantrax", broken=()):
        self.ctx = ctx
        self.url = LOGIN_URL
        self.visible = set(visible)
        self.broken = set(broken)
        self._title = title
        self.waits = 0

    def goto(self, url, **kwargs):
        pass

    def locator(self, selector, has_text=None):
        return FakeLocator(self, selector)

    def title(self):
        return self._title

    def wait_for_timeout(self, ms):
        self.waits += 1

    def wait_for_url(self, test, timeout=None):
        pass

    def set_default_timeout(self, ms):
        pass

    def screenshot(self, path=None):
        pass


@pytest.fixture
def scraper(monkeypatch, tmp_path):
    monkeypatch.delenv(fx.FantraxScraper.SESSION_DIR_ENV, raising=False)
    monkeypatch.setattr(fx.FantraxScraper, "_creds", lambda self: (FAKE_EMAIL, FAKE_PASSWORD))
    cfg = dataclasses.replace(fx.CFG, user_data_dir=str(tmp_path / "profile"),
                              raw_dir=str(tmp_path / "raw"), login_url=LOGIN_URL)
    return fx.FantraxScraper(cfg)


PASSWORD = "input[formcontrolname='password']"
ERROR = "mat-error, [role='alert']"


def test_a_reply_still_not_logged_in_after_the_login_raises_the_named_error(scraper):
    ctx = FakeContext()
    with pytest.raises(fx.SessionStillDead) as caught:
        scraper._post_authed(ctx, FakePage(ctx), {}, "fake call")
    assert "WARNING_NOT_LOGGED_IN" in str(caught.value)
    assert ctx.posts == 2


def test_a_login_that_works_returns_the_live_reply(scraper):
    ctx = FakeContext(live_after_login=True)
    assert scraper._post_authed(ctx, FakePage(ctx), {}, "fake call") == LIVE
    assert ctx.posts == 2


def test_a_live_session_needs_no_login(scraper):
    ctx = FakeContext()
    ctx.live = True

    class NoPage:
        def __getattr__(self, name):
            raise AssertionError("a live session touched the login page")
    assert scraper._post_authed(ctx, NoPage(), {}, "fake call") == LIVE
    assert ctx.posts == 1


def test_the_player_grid_stops_with_the_named_error_not_a_key_error(scraper, monkeypatch):
    ctx = FakeContext()

    class Chromium:
        def launch_persistent_context(self, *args, **kwargs):
            return ctx

    class Playwright:
        chromium = Chromium()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    fake = types.ModuleType("playwright.sync_api")
    fake.sync_playwright = Playwright
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake)
    with pytest.raises(fx.SessionStillDead):
        scraper.fetch_player_stats("FAKE_CODE", "FAKE_TIMEFRAME", "fake")
    assert ctx.posts == 2


def test_a_login_stuck_on_the_login_page_prints_what_the_page_showed(scraper, capsys):
    ctx = FakeContext()
    scraper._login(FakePage(ctx, visible={PASSWORD, ERROR}))
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.startswith("[warn] Fantrax login")]
    assert len(lines) == 1
    line = lines[0]
    assert "still on the login page after 30 s" in line
    for flag in ("Cloudflare challenge no", "captcha frame no", "error message yes",
                 "code prompt no", "login form yes"):
        assert flag in line


def test_a_cloudflare_holding_page_is_named_by_its_title(scraper, capsys):
    ctx = FakeContext()
    scraper._login(FakePage(ctx, title="Just a moment..."))
    assert "Cloudflare challenge yes" in capsys.readouterr().out


def test_a_check_that_fails_is_reported_unknown_not_raised(scraper, capsys):
    ctx = FakeContext()
    scraper._login(FakePage(ctx, broken={ERROR}))
    assert "error message unknown" in capsys.readouterr().out


def test_a_login_that_leaves_the_login_page_prints_nothing(scraper, capsys):
    ctx = FakeContext(live_after_login=True)
    scraper._login(FakePage(ctx))
    assert "[warn]" not in capsys.readouterr().out


def test_no_credential_reaches_the_output_or_the_error(scraper, capsys):
    ctx = FakeContext()
    with pytest.raises(fx.SessionStillDead) as caught:
        scraper._post_authed(ctx, FakePage(ctx, visible={PASSWORD}), {}, "fake call")
    shown = capsys.readouterr()
    seen = shown.out + shown.err + str(caught.value)
    assert FAKE_EMAIL not in seen
    assert FAKE_PASSWORD not in seen
