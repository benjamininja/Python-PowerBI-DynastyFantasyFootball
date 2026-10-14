"""FantraxScraper._login answers the second-factor code prompt (#230), on a
fake page. No browser, no network, no login, no real secret."""
import dataclasses
import importlib
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

fx = importlib.import_module("04a_fantrax_weekly_scrape")

FAKE_SECRET = "FAKEFAKEFAKEFAKE"
NOW = 1_700_000_025
ENV = "FANTRAX_TOTP_SECRET"
LOGIN_URL = "https://fantrax.invalid/login"
HOME_URL = "https://fantrax.invalid/home"


def fake_code(at):
    return f"{(int(at) // 30) % 1_000_000:06d}"


class FakeTOTP:
    interval = 30
    seen = []

    def __init__(self, secret):
        FakeTOTP.seen.append(secret)

    def at(self, when):
        return fake_code(when)


def fake_pyotp_module():
    mod = types.ModuleType("pyotp")
    mod.TOTP = FakeTOTP
    return mod


class FakeLocator:
    def __init__(self, page, kind):
        self.page = page
        self.kind = kind

    @property
    def first(self):
        return self

    def fill(self, value):
        self.page.filled.append(self.kind)

    def press(self, key):
        if self.kind == "password" and key == "Enter":
            self.page.after_password()

    def is_visible(self):
        if self.kind == "code":
            return self.page.code_visible
        return True

    def count(self):
        return 1 if self.page.code_visible else 0

    def is_enabled(self):
        self.page.enabled_checks += 1
        return bool(self.page.entered) and self.page.enabled_checks > self.page.enable_after

    def click(self, timeout=None):
        if self.kind == "button":
            self.page.clicks += 1
            self.page.submit(self.page.entered)

    def press_sequentially(self, text, delay=None):
        self.page.typed.append(text)
        self.page.entered = text
        if len(text) == 6 and self.page.self_submit:
            self.page.submit(text)


class FakePage:
    def __init__(self, prompt=True, valid_code=None, self_submit=False, enable_after=0,
                 appear_after=2):
        self.prompt = prompt
        self.valid_code = valid_code
        self.self_submit = self_submit
        self.enable_after = enable_after
        self.appear_after = appear_after
        self.url = LOGIN_URL
        self.code_visible = False
        self.entered = ""
        self.typed = []
        self.filled = []
        self.waits = []
        self.screenshots = []
        self.clicks = 0
        self.enabled_checks = 0
        self.password_sent = False

    def locator(self, selector, has_text=None):
        if selector == fx.FantraxScraper.CODE_FIELD:
            return FakeLocator(self, "code")
        if selector == fx.FantraxScraper.CODE_BUTTON:
            assert has_text == fx.FantraxScraper.CODE_BUTTON_TEXT
            return FakeLocator(self, "button")
        if "password" in selector:
            return FakeLocator(self, "password")
        return FakeLocator(self, "email")

    def goto(self, url, **kwargs):
        assert url == fx.CFG.login_url

    def after_password(self):
        self.password_sent = True
        if not self.prompt:
            self.url = HOME_URL

    def wait_for_timeout(self, ms):
        self.waits.append(ms)
        if self.password_sent and self.prompt and len(self.waits) >= self.appear_after:
            self.code_visible = True

    def wait_for_url(self, predicate, timeout=None):
        if not predicate(self.url):
            raise TimeoutError("url did not leave /login")

    def screenshot(self, path=None):
        self.screenshots.append(path)

    def submit(self, code):
        if code == self.valid_code:
            self.code_visible = False
            self.url = HOME_URL
        else:
            self.entered = ""


@pytest.fixture
def scraper(tmp_path, monkeypatch):
    cfg = dataclasses.replace(
        fx.CFG, raw_dir=str(tmp_path / "raw"), user_data_dir=str(tmp_path / "profile"))
    s = fx.FantraxScraper(cfg)
    s._creds = lambda: ("fake-user", "fake-pass")
    FakeTOTP.seen = []
    monkeypatch.setitem(sys.modules, "pyotp", fake_pyotp_module())
    monkeypatch.setattr(fx, "_now", lambda: NOW)
    monkeypatch.setenv(ENV, FAKE_SECRET)
    return s


def written_files(scraper):
    return [p for p in Path(scraper.cfg.raw_dir).rglob("*") if p.is_file()]


class TestPromptWithSecret:
    def test_types_code_and_clicks_verify_once_enabled(self, scraper):
        page = FakePage(valid_code=fake_code(NOW), enable_after=3)
        scraper._login(page)
        assert page.typed == [fake_code(NOW)]
        assert page.clicks == 1
        assert page.url == HOME_URL
        assert page.screenshots == []

    def test_form_that_submits_itself_is_not_clicked(self, scraper):
        page = FakePage(valid_code=fake_code(NOW), self_submit=True)
        scraper._login(page)
        assert page.typed == [fake_code(NOW)]
        assert page.clicks == 0
        assert page.url == HOME_URL

    def test_code_is_computed_from_the_secret_the_variable_holds(self, scraper):
        scraper._login(FakePage(valid_code=fake_code(NOW)))
        assert FakeTOTP.seen == [FAKE_SECRET]

    def test_a_code_about_to_expire_waits_for_the_next_window(self, scraper, monkeypatch):
        late = 1_700_000_039
        monkeypatch.setattr(fx, "_now", lambda: late)
        page = FakePage(valid_code=fake_code(late))
        scraper._login(page)
        assert 2000 in page.waits


class TestPromptWithoutSecret:
    def test_stops_with_an_error_that_names_the_variable(self, scraper, monkeypatch):
        monkeypatch.delenv(ENV, raising=False)
        page = FakePage()
        with pytest.raises(fx.TotpSecretMissing) as err:
            scraper._login(page)
        assert ENV in str(err.value)
        assert page.typed == []
        assert page.clicks == 0

    def test_a_blank_variable_counts_as_not_set(self, scraper, monkeypatch):
        monkeypatch.setenv(ENV, "   ")
        with pytest.raises(fx.TotpSecretMissing):
            scraper._login(FakePage())


class TestNoPrompt:
    def test_login_without_a_prompt_needs_no_secret_and_types_no_code(self, scraper, monkeypatch):
        monkeypatch.delenv(ENV, raising=False)
        page = FakePage(prompt=False)
        scraper._login(page)
        assert page.typed == []
        assert page.clicks == 0
        assert page.url == HOME_URL
        assert FakeTOTP.seen == []


class TestRefusedCode:
    def test_one_code_one_attempt_then_a_plain_error(self, scraper):
        page = FakePage(valid_code="not-the-code", enable_after=1)
        with pytest.raises(fx.TotpCodeRefused):
            scraper._login(page)
        assert page.typed == [fake_code(NOW)]
        assert page.clicks == 1
        assert page.screenshots == []

    def test_a_self_submitting_form_that_refuses_is_also_one_attempt(self, scraper):
        page = FakePage(valid_code="not-the-code", self_submit=True)
        with pytest.raises(fx.TotpCodeRefused):
            scraper._login(page)
        assert page.typed == [fake_code(NOW)]
        assert page.clicks == 0


class TestNothingLeaks:
    @pytest.mark.parametrize("outcome", ["accepted", "refused", "no_secret"])
    def test_neither_secret_nor_code_reaches_output_errors_or_files(
            self, scraper, monkeypatch, capsys, caplog, outcome):
        if outcome == "no_secret":
            monkeypatch.delenv(ENV, raising=False)
        valid = fake_code(NOW) if outcome == "accepted" else "not-the-code"
        page = FakePage(valid_code=valid)
        message = ""
        try:
            scraper._login(page)
        except fx.TotpLoginError as exc:
            message = str(exc) + repr(exc) + repr(exc.__cause__) + repr(exc.__context__)
        out = capsys.readouterr()
        seen = message + out.out + out.err + caplog.text
        assert FAKE_SECRET not in seen
        assert fake_code(NOW) not in seen
        assert written_files(scraper) == []
        assert page.screenshots == []

    def test_an_unusable_key_is_reported_without_the_key(self, scraper, monkeypatch):
        def boom(secret):
            raise ValueError(secret)
        monkeypatch.setattr(FakeTOTP, "__init__", lambda self, secret: boom(secret))
        with pytest.raises(fx.TotpLoginError) as err:
            scraper._login(FakePage())
        assert FAKE_SECRET not in str(err.value) + repr(err.value.__cause__)
        assert ENV in str(err.value)


class TestRealPyotp:
    def test_code_from_the_real_library_is_what_gets_typed(self, scraper, monkeypatch):
        pyotp = pytest.importorskip("pyotp")
        monkeypatch.setitem(sys.modules, "pyotp", pyotp)
        expected = pyotp.TOTP(FAKE_SECRET).at(NOW)
        page = FakePage(valid_code=expected, self_submit=True)
        scraper._login(page)
        assert page.typed == [expected]
        assert len(expected) == 6 and expected.isdigit()

