"""scripts/runner_spike.py and its workflow, on fakes only (#225). No browser,
no network, no login."""
import dataclasses
import importlib.util
import re
import types
from contextlib import contextmanager
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("runner_spike", REPO / "scripts" / "runner_spike.py")
rs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rs)

WORKFLOW = REPO / ".github" / "workflows" / "fantrax-runner-spike.yml"
PAGE = REPO / "docs" / "research" / "fantrax-runner-spike.md"
CODE_FIELD = "input[name='two-factor-key']"
SENTINEL = "Zebediah Quillfeather"
SECRET_NAMES = {"FANTRAX_EMAIL", "FANTRAX_PASSWORD", "FANTRAX_TOTP_SECRET"}
READ_NAMES = ["getPlayerStats", "getLiveScoringStats", "getTeamRosterInfo",
              "getTransactionDetailsHistory"]

GOOD = (200, {}, {"responses": [{"data": {"rows": [SENTINEL]}}]})
DEAD = (200, {}, {"responses": [{"pageError": {"code": "WARNING_NOT_LOGGED_IN", "text": SENTINEL}}]})
DENIED = (200, {}, {"responses": [{"pageError": {"code": "ERR_NOT_ALLOWED", "text": SENTINEL}}]})
CF = (403, {"cf-mitigated": "challenge", "x-sentinel": SENTINEL}, None)


def session_dead(body):
    return "WARNING_NOT_LOGGED_IN" in str(body)


def page_error(body):
    return (body.get("responses") or [{}])[0].get("pageError")


def judge(status, headers, body):
    return rs.judge_reply(status, headers, body, session_dead=session_dead, page_error=page_error)


class FakeSession:
    def __init__(self, signals=None, replies=(), scraper=None, login_error=None):
        self.signals = signals or rs.PageSignals()
        self.replies = list(replies)
        self.login_error = login_error
        self.scraper = scraper
        self.posted = []

    def login(self):
        return self.signals

    def post(self, payload):
        self.posted.append(payload)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def reads():
    return [rs.Read(name, {"msgs": [{"method": name}]}) for name in READ_NAMES]


def spike(session, **kwargs):
    return rs.run_spike(session, kwargs.get("reads", reads()), judge, sleep=lambda s: None)


class TestJudgeReply:
    def test_ok(self):
        assert judge(*GOOD) == (rs.OK, None)

    def test_no_response(self):
        assert judge(None, {}, None) == (rs.NO_RESPONSE, None)

    def test_cloudflare_header_wins_over_status(self):
        assert judge(*CF) == (rs.CF_CHALLENGE, None)

    def test_http_error(self):
        assert judge(500, {}, {}) == (rs.HTTP_ERROR, None)

    def test_body_that_is_not_a_dict(self):
        assert judge(200, {}, None) == (rs.BAD_BODY, None)

    def test_dead_session_beats_page_error(self):
        assert judge(*DEAD) == (rs.NOT_LOGGED_IN, None)

    def test_page_error_keeps_a_code_shaped_value_only(self):
        assert judge(*DENIED) == (rs.PAGE_ERROR, "ERR_NOT_ALLOWED")
        odd = (200, {}, {"responses": [{"pageError": {"code": SENTINEL}}]})
        assert judge(*odd) == (rs.PAGE_ERROR, "other")


class TestLoginOutcome:
    def test_challenge_signal(self):
        assert rs.login_outcome(rs.PageSignals(cf_challenge=True)) == rs.CHALLENGED

    def test_code_prompt(self):
        assert rs.login_outcome(rs.PageSignals(code_prompt=True)) == rs.NEEDS_CODE

    def test_challenge_beats_code_prompt(self):
        both = rs.PageSignals(cf_challenge=True, code_prompt=True)
        assert rs.login_outcome(both) == rs.CHALLENGED

    def test_probe_decides_when_no_signal(self):
        clean = rs.PageSignals()
        assert rs.login_outcome(clean, rs.OK) == rs.PASSED
        assert rs.login_outcome(clean, rs.PAGE_ERROR) == rs.PASSED
        assert rs.login_outcome(clean, rs.NOT_LOGGED_IN) == rs.FAILED
        assert rs.login_outcome(clean, rs.CF_CHALLENGE) == rs.CHALLENGED
        assert rs.login_outcome(clean, None) == rs.FAILED


class FakeProbePage:
    def __init__(self, code_visible):
        self.code_visible = code_visible
        self.selectors = []

    def title(self):
        return "Fantrax"

    def locator(self, selector):
        self.selectors.append(selector)
        return FakeProbeLocator(self, selector)


class FakeProbeLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    def count(self):
        return 0

    @property
    def first(self):
        return self

    def is_visible(self):
        return self.page.code_visible and self.selector == CODE_FIELD


class TestCodePromptSignal:
    @pytest.mark.parametrize("visible, verdict", [(True, rs.NEEDS_CODE), (False, None)])
    def test_needs_code_keys_on_the_code_field(self, visible, verdict):
        scraper = types.SimpleNamespace(cfg=types.SimpleNamespace(), CODE_FIELD=CODE_FIELD)
        session = rs.PlaywrightSession(scraper)
        session.page = FakeProbePage(visible)
        signals = session.signals()
        assert signals.code_prompt is visible
        assert rs.early_stop(signals) == verdict
        assert CODE_FIELD in session.page.selectors


class TestRunSpike:
    def test_challenged_runner_makes_no_read(self):
        session = FakeSession(rs.PageSignals(cf_challenge=True), [GOOD])
        report = spike(session)
        assert report.login == rs.CHALLENGED and report.reads == [] and session.posted == []

    def test_code_prompt_makes_no_read(self):
        session = FakeSession(rs.PageSignals(code_prompt=True), [GOOD])
        report = spike(session)
        assert report.login == rs.NEEDS_CODE and session.posted == []

    def test_passed_makes_all_four_reads_in_order(self):
        session = FakeSession(replies=[GOOD, GOOD, DENIED, GOOD])
        report = spike(session)
        assert report.login == rs.PASSED
        assert [r.name for r in report.reads] == READ_NAMES
        assert [r.verdict for r in report.reads] == [rs.OK, rs.OK, rs.PAGE_ERROR, rs.OK]
        assert [r.http_status for r in report.reads] == [200, 200, 200, 200]

    def test_dead_probe_stops_after_one_read(self):
        session = FakeSession(replies=[DEAD, GOOD])
        report = spike(session)
        assert report.login == rs.FAILED and len(report.reads) == 1

    def test_cloudflare_on_the_probe_is_a_challenge(self):
        session = FakeSession(replies=[CF, GOOD])
        report = spike(session)
        assert report.login == rs.CHALLENGED and len(report.reads) == 1

    def test_a_read_that_raises_is_reported_by_class_name(self):
        session = FakeSession(replies=[GOOD, RuntimeError(SENTINEL), GOOD, GOOD])
        report = spike(session)
        second = report.reads[1]
        assert (second.verdict, second.note, second.http_status) == (rs.NO_RESPONSE, "RuntimeError", None)
        assert len(report.reads) == 4

    def test_an_empty_payload_is_skipped_not_posted(self):
        listed = reads()
        listed[2] = rs.Read("getTeamRosterInfo", {})
        session = FakeSession(replies=[GOOD, GOOD, GOOD])
        report = spike(session, reads=listed)
        assert report.reads[2].verdict == rs.SKIPPED and len(session.posted) == 3

    def test_login_step_exception_is_kept_as_a_class_name(self):
        session = FakeSession(rs.PageSignals(code_prompt=True), login_error="TimeoutError")
        assert spike(session).login_note == "TimeoutError"


class TestCodeSentBy:
    @pytest.mark.parametrize("held, line", [
        ("self_submit", "Code sent by: self_submit"),
        ("verify_click", "Code sent by: verify_click"),
        (None, "Code sent by: none"),
        (SENTINEL, "Code sent by: none"),
    ])
    def test_one_summary_line_with_one_of_three_words(self, held, line):
        scraper = types.SimpleNamespace(code_sent_by=held)
        report = spike(FakeSession(replies=[GOOD] * 4, scraper=scraper))
        text = rs.render(report)
        assert text.count("Code sent by:") == 1
        assert line in text.splitlines()
        assert SENTINEL not in text

    def test_the_line_is_there_when_the_run_stopped_early(self):
        scraper = types.SimpleNamespace(code_sent_by="verify_click")
        session = FakeSession(rs.PageSignals(code_prompt=True), scraper=scraper)
        assert "Code sent by: verify_click" in rs.render(spike(session))


class TestRender:
    def build(self):
        session = FakeSession(replies=[GOOD, DENIED, DEAD, RuntimeError(SENTINEL)],
                              login_error="TimeoutError")
        report = spike(session)
        report.secrets = {"FANTRAX_EMAIL": True, "FANTRAX_TOTP_SECRET": False}
        report.steps = [("install chromium", 41.0)]
        return report

    def test_report_holds_only_verdicts(self):
        text = rs.render(self.build())
        assert SENTINEL not in text
        assert "getPlayerStats" in text and "ERR_NOT_ALLOWED" in text
        assert "FANTRAX_TOTP_SECRET NO" in text
        assert "| install chromium | 41 |" in text

    def test_each_login_outcome_has_a_headline(self):
        for outcome in (rs.PASSED, rs.CHALLENGED, rs.NEEDS_CODE, rs.FAILED):
            assert f"**Login: {rs.LOGIN_TEXT[outcome]}**" in rs.render(rs.Report(login=outcome))


class TestTimings:
    def test_good_lines_are_kept_and_the_rest_dropped(self, tmp_path):
        path = tmp_path / "t.tsv"
        path.write_text(f"install chromium\t41\n{SENTINEL}\t3\nbad\tx\ninstall python packages\t12\n",
                        encoding="utf-8")
        assert rs.read_timings(path) == [("install chromium", 41.0), ("install python packages", 12.0)]

    def test_a_missing_file_is_empty(self, tmp_path):
        assert rs.read_timings(tmp_path / "none.tsv") == []
        assert rs.read_timings(None) == []


class TestBuildReads:
    @pytest.fixture
    def modules(self):
        return rs.load_modules()

    def scraper(self, fx, tmp_path):
        cfg = dataclasses.replace(fx.CFG, user_data_dir=str(tmp_path / "p"),
                                  raw_dir=str(tmp_path / "r"), players_page_size=1)
        return fx.FantraxScraper(cfg)

    def test_four_named_reads_each_sending_its_own_method(self, modules, tmp_path):
        fx, fs, ft = modules
        built = rs.build_reads(fx, fs, ft, self.scraper(fx, tmp_path), "team123")
        assert [r.name for r in built] == READ_NAMES
        for r in built:
            assert [m["method"] for m in r.payload["msgs"]] == [r.name]

    def test_each_read_asks_for_one_row(self, modules, tmp_path):
        fx, fs, ft = modules
        built = {r.name: r.payload["msgs"][0]["data"]
                 for r in rs.build_reads(fx, fs, ft, self.scraper(fx, tmp_path), "team123")}
        assert built["getPlayerStats"]["maxResultsPerPage"] == "1"
        assert built["getTransactionDetailsHistory"]["maxResultsPerPage"] == "1"
        assert built["getTeamRosterInfo"]["teamId"] == "team123"

    def test_no_team_id_skips_the_roster_read(self, modules, tmp_path):
        fx, fs, ft = modules
        built = rs.build_reads(fx, fs, ft, self.scraper(fx, tmp_path), None)
        assert built[2].payload == {}


class TestMain:
    ENV = {"GITHUB_ACTIONS": "true", "FANTRAX_EMAIL": "x", "FANTRAX_PASSWORD": "y"}

    @staticmethod
    def explode(*args, **kwargs):
        raise AssertionError("a session was opened")

    def test_refuses_off_actions(self, capsys):
        code = rs.main([], env={"FANTRAX_EMAIL": "x", "FANTRAX_PASSWORD": "y"},
                       open_session=self.explode)
        assert code == 2 and "Refusing" in capsys.readouterr().out

    def test_missing_secret_stops_before_any_session(self, capsys):
        env = {"GITHUB_ACTIONS": "true", "FANTRAX_EMAIL": "x", "FANTRAX_PASSWORD": ""}
        code = rs.main([], env=env, open_session=self.explode)
        out = capsys.readouterr().out
        assert code == 1 and "FANTRAX_PASSWORD NO" in out and "Nothing was run" in out

    def test_full_run_on_a_fake_session(self, capsys, tmp_path):
        summary = tmp_path / "summary.md"
        env = {**self.ENV, "GITHUB_STEP_SUMMARY": str(summary)}

        @contextmanager
        def fake_open(fx, work_dir):
            cfg = dataclasses.replace(fx.CFG, user_data_dir=str(work_dir / "p"),
                                      raw_dir=str(work_dir / "r"), players_page_size=1)
            yield FakeSession(replies=[GOOD] * 4, scraper=fx.FantraxScraper(cfg))

        code = rs.main([], env=env, open_session=fake_open)
        out = capsys.readouterr().out
        assert code == 0
        assert "**Login: passed**" in out
        assert out.count("| 200 | ok |") == 4
        assert SENTINEL not in out
        assert summary.read_text(encoding="utf-8") == out

    def test_a_driver_exception_is_reported_by_class_name(self, capsys):
        @contextmanager
        def broken(fx, work_dir):
            raise OSError(SENTINEL)
            yield

        code = rs.main([], env=self.ENV, open_session=broken)
        out = capsys.readouterr().out
        assert code == 1 and "OSError" in out and SENTINEL not in out


class TestWorkflow:
    @pytest.fixture
    def wf(self):
        return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))

    def test_fires_by_hand_only(self, wf):
        triggers = wf.get("on", wf.get(True))
        assert set(triggers) == {"workflow_dispatch"}
        assert not (triggers["workflow_dispatch"] or {}).get("inputs")

    def test_job_is_fenced(self, wf):
        job = wf["jobs"]["spike"]
        assert job["runs-on"] == "ubuntu-latest"
        assert job["environment"] == "fantrax-spike"
        assert "refs/heads/main" in job["if"]
        assert wf["permissions"] == {"contents": "read"}
        assert job["timeout-minutes"] <= 30

    def test_nothing_is_uploaded_or_cached(self, wf):
        uses = [s.get("uses", "") for s in wf["jobs"]["spike"]["steps"]]
        assert not any("upload-artifact" in u or "cache" in u for u in uses)

    def test_only_the_three_named_secrets_and_only_in_the_last_step(self, wf):
        steps = wf["jobs"]["spike"]["steps"]
        used = set(re.findall(r"secrets\.([A-Z_]+)", WORKFLOW.read_text(encoding="utf-8")))
        assert used == SECRET_NAMES
        assert set(steps[-1]["env"]) == SECRET_NAMES
        assert not any("secrets." in str(s) for s in steps[:-1])

    def test_last_step_runs_the_driver(self, wf):
        assert "scripts/runner_spike.py" in wf["jobs"]["spike"]["steps"][-1]["run"]


class TestPage:
    def test_page_names_the_secrets_and_the_environment(self):
        text = PAGE.read_text(encoding="utf-8")
        for name in SECRET_NAMES | {"fantrax-spike", "fantrax-runner-spike"}:
            assert name in text

    def test_page_holds_no_email_shaped_string(self):
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", PAGE.read_text(encoding="utf-8"))
