"""Runner spike for #92: one headless Fantrax login and four reads, from a
GitHub Actions runner, reporting verdicts only.

Run by .github/workflows/fantrax-runner-spike.yml and nowhere else: it
refuses to start unless GITHUB_ACTIONS is "true". It prints, and writes to the
step summary, only: the login outcome, each read's name, HTTP status, verdict
and seconds, and step timings. No payload, cookie, header value, page text,
exception message or account detail ever reaches the report. The report is a
public log (the repository is public).

No browser fingerprint or challenge handling is altered: a challenged runner is
reported and the run stops.
"""
import argparse
import dataclasses
import importlib
import json
import os
import re
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NOTEBOOKS = REPO / "notebooks"

REQUIRED_SECRETS = ("FANTRAX_EMAIL", "FANTRAX_PASSWORD")
OPTIONAL_SECRETS = ("FANTRAX_TOTP_SECRET",)

PASSED, CHALLENGED, NEEDS_CODE, FAILED = "passed", "challenged", "needs_code", "failed"
LOGIN_TEXT = {
    PASSED: "passed",
    CHALLENGED: "challenged by the runner's network path; stopped, no workaround tried",
    NEEDS_CODE: "stopped at the second-factor code prompt; not a network block",
    FAILED: "failed; neither a challenge nor a code prompt was seen",
}

OK, PAGE_ERROR, NOT_LOGGED_IN = "ok", "page_error", "not_logged_in"
CF_CHALLENGE, HTTP_ERROR, BAD_BODY = "cf_challenge", "http_error", "bad_body"
NO_RESPONSE, SKIPPED = "no_response", "skipped"

CODE_SENT_BY = ("self_submit", "verify_click")
SPIKE_PERIOD = 1
PAUSE_S = 1.0
CODE_PATTERN = re.compile(r"[A-Z0-9_]{3,48}")
STEP_NAME_PATTERN = re.compile(r"[a-z0-9 ._-]{1,48}")


@dataclass
class PageSignals:
    cf_challenge: bool = False
    code_prompt: bool = False


@dataclass
class Read:
    name: str
    payload: dict


@dataclass
class ReadResult:
    name: str
    http_status: int | None
    verdict: str
    code: str | None = None
    seconds: float = 0.0
    note: str | None = None


@dataclass
class Report:
    login: str = FAILED
    login_seconds: float = 0.0
    login_note: str | None = None
    code_sent_by: str | None = None
    secrets: dict = field(default_factory=dict)
    reads: list = field(default_factory=list)
    steps: list = field(default_factory=list)


def is_cf_challenge(headers) -> bool:
    return str((headers or {}).get("cf-mitigated", "")).lower() == "challenge"


def safe_code(code) -> str | None:
    if code is None:
        return None
    return code if isinstance(code, str) and CODE_PATTERN.fullmatch(code) else "other"


def judge_reply(status, headers, body, *, session_dead, page_error) -> tuple[str, str | None]:
    if status is None:
        return NO_RESPONSE, None
    if is_cf_challenge(headers):
        return CF_CHALLENGE, None
    if not 200 <= status < 300:
        return HTTP_ERROR, None
    if not isinstance(body, dict):
        return BAD_BODY, None
    if session_dead(body):
        return NOT_LOGGED_IN, None
    err = page_error(body)
    if err:
        return PAGE_ERROR, safe_code(err.get("code") if isinstance(err, dict) else None)
    return OK, None


def early_stop(signals: PageSignals) -> str | None:
    if signals.cf_challenge:
        return CHALLENGED
    if signals.code_prompt:
        return NEEDS_CODE
    return None


def login_outcome(signals: PageSignals, probe_verdict: str | None = None) -> str:
    if probe_verdict == CF_CHALLENGE:
        return CHALLENGED
    stop = early_stop(signals)
    if stop:
        return stop
    return PASSED if probe_verdict in (OK, PAGE_ERROR) else FAILED


def build_reads(fx, fs, ft, scraper, team_id) -> list[Read]:
    cfg = scraper.cfg
    stats = scraper._player_stats_payload(
        fx.resolve_season_or_projection(cfg), cfg.grid_timeframe,
        cfg.players_pos_groups[0], 1)
    method, data, ref = fs.period_requests(SPIKE_PERIOD)["live_scoring"]
    live = fs.payload(method, data, ref)
    reads = [Read("getPlayerStats", stats), Read("getLiveScoringStats", live)]
    if team_id:
        roster = fs.payload("getTeamRosterInfo",
                            {"teamId": team_id, "period": SPIKE_PERIOD},
                            f"team/roster;teamId={team_id}")
        reads.append(Read("getTeamRosterInfo", roster))
    else:
        reads.append(Read("getTeamRosterInfo", {}))
    txn = ft.txn_payload(1, "CLAIM_DROP")
    txn["msgs"][0]["data"]["maxResultsPerPage"] = "1"
    reads.append(Read("getTransactionDetailsHistory", txn))
    return reads


def run_read(read: Read, post, judge, clock=time.perf_counter) -> ReadResult:
    if not read.payload:
        return ReadResult(read.name, None, SKIPPED)
    start = clock()
    try:
        status, headers, body = post(read.payload)
    except Exception as exc:
        return ReadResult(read.name, None, NO_RESPONSE, None, clock() - start,
                          type(exc).__name__)
    verdict, code = judge(status, headers, body)
    return ReadResult(read.name, status, verdict, code, clock() - start)


def run_spike(session, reads, judge, clock=time.perf_counter, sleep=time.sleep) -> Report:
    report = Report()
    start = clock()
    signals = session.login()
    report.login_seconds = clock() - start
    report.login_note = getattr(session, "login_error", None)
    sent = getattr(getattr(session, "scraper", None), "code_sent_by", None)
    report.code_sent_by = sent if sent in CODE_SENT_BY else None
    stop = early_stop(signals)
    if stop:
        report.login = stop
        return report
    probe = run_read(reads[0], session.post, judge, clock)
    report.reads.append(probe)
    report.login = login_outcome(signals, probe.verdict)
    if report.login != PASSED:
        return report
    for read in reads[1:]:
        sleep(PAUSE_S)
        report.reads.append(run_read(read, session.post, judge, clock))
    return report


def read_timings(path) -> list[tuple[str, float]]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, TypeError):
        return []
    out = []
    for line in lines:
        name, _, seconds = line.partition("\t")
        if STEP_NAME_PATTERN.fullmatch(name) and re.fullmatch(r"\d{1,6}", seconds):
            out.append((name, float(seconds)))
    return out


def render(report: Report) -> str:
    lines = ["## Fantrax runner spike", "",
             f"**Login: {LOGIN_TEXT.get(report.login, FAILED)}** "
             f"({report.login_seconds:.1f} s)"]
    if report.login_note:
        lines.append(f"Login step raised: {report.login_note}")
    lines.append(f"Code sent by: {report.code_sent_by or 'none'}")
    lines += ["", "Secrets set (names only): " + ", ".join(
        f"{name} {'yes' if present else 'NO'}" for name, present in report.secrets.items()), ""]
    if report.reads:
        lines += ["| Read | HTTP | Verdict | Code | Seconds |", "|---|---|---|---|---|"]
        for r in report.reads:
            status = "-" if r.http_status is None else str(r.http_status)
            verdict = r.verdict + (f" ({r.note})" if r.note else "")
            lines.append(f"| {r.name} | {status} | {verdict} | {r.code or '-'} | {r.seconds:.1f} |")
    else:
        lines.append("No read was made.")
    if report.steps:
        lines += ["", "| Step | Seconds |", "|---|---|"]
        lines += [f"| {name} | {seconds:.0f} |" for name, seconds in report.steps]
    return "\n".join(lines) + "\n"


def load_modules():
    if str(NOTEBOOKS) not in sys.path:
        sys.path.insert(0, str(NOTEBOOKS))
    return (importlib.import_module("04a_fantrax_weekly_scrape"),
            importlib.import_module("04s_fantrax_inseason_capture"),
            importlib.import_module("04t_fantrax_transaction_history"))


def first_team_id(fx) -> str | None:
    try:
        teams = fx.etl.read_table("dim_fantasy_teams")
        ids = sorted(str(v) for v in teams["fantrax_team_id"].dropna().unique())
    except Exception:
        return None
    return ids[0] if ids else None


class PlaywrightSession:
    def __init__(self, scraper):
        self.scraper = scraper
        self.cfg = scraper.cfg
        self.login_error = None
        self.cf_seen = False

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self.ctx = self._pw.chromium.launch_persistent_context(
            self.cfg.user_data_dir, headless=self.cfg.headless)
        self.page = self.ctx.new_page()
        self.page.set_default_timeout(self.cfg.nav_timeout_ms)
        self.page.on("response", self._on_response)
        return self

    def __exit__(self, *exc):
        try:
            self.ctx.close()
        finally:
            self._pw.stop()

    def _on_response(self, response):
        try:
            if is_cf_challenge(response.headers):
                self.cf_seen = True
        except Exception:
            pass

    def signals(self) -> PageSignals:
        signals = PageSignals(cf_challenge=self.cf_seen)
        try:
            title = (self.page.title() or "").lower()
            signals.cf_challenge = signals.cf_challenge or title.startswith("just a moment")
            frames = self.page.locator("iframe[src*='challenges.cloudflare.com']")
            signals.cf_challenge = signals.cf_challenge or frames.count() > 0
            field = self.page.locator(self.scraper.CODE_FIELD).first
            signals.code_prompt = field.is_visible()
        except Exception:
            pass
        return signals

    def login(self) -> PageSignals:
        try:
            self.scraper._login(self.page)
        except Exception as exc:
            self.login_error = type(exc).__name__
        return self.signals()

    def post(self, payload):
        url = f"{self.cfg.endpoint}?leagueId={self.cfg.league_id}"
        resp = self.ctx.request.post(
            url, data=json.dumps(payload), headers={"Content-Type": "application/json"})
        try:
            body = resp.json()
        except Exception:
            body = None
        return resp.status, dict(resp.headers), body


@contextmanager
def real_session(fx, work_dir: Path):
    cfg = dataclasses.replace(
        fx.CFG, user_data_dir=str(work_dir / "profile"), raw_dir=str(work_dir / "raw"),
        players_page_size=1, headless=True)
    with PlaywrightSession(fx.FantraxScraper(cfg)) as session:
        yield session


def emit(text: str, env) -> None:
    sys.stdout.write(text)
    summary = env.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text)


def main(argv=None, env=None, open_session=None) -> int:
    env = os.environ if env is None else env
    if env.get("GITHUB_ACTIONS") != "true":
        sys.stdout.write("Refusing to run: this spike runs only on a GitHub Actions runner.\n")
        return 2
    parser = argparse.ArgumentParser()
    parser.add_argument("--timings", default=None)
    args = parser.parse_args(argv)

    report = Report()
    report.secrets = {name: bool(env.get(name)) for name in REQUIRED_SECRETS + OPTIONAL_SECRETS}
    report.steps = read_timings(args.timings)
    if not all(report.secrets[name] for name in REQUIRED_SECRETS):
        emit(render(report) + "\nA required secret is not set. Nothing was run.\n", env)
        return 1
    try:
        fx, fs, ft = load_modules()
        with tempfile.TemporaryDirectory() as tmp:
            with (open_session or real_session)(fx, Path(tmp)) as session:
                reads = build_reads(fx, fs, ft, session.scraper, first_team_id(fx))
                judge = lambda s, h, b: judge_reply(
                    s, h, b, session_dead=fx.FantraxScraper._session_dead,
                    page_error=fs.page_error)
                started = time.perf_counter()
                run = run_spike(session, reads, judge)
        run.secrets, run.steps = report.secrets, report.steps
        run.steps = run.steps + [("spike driver total", time.perf_counter() - started)]
    except Exception as exc:
        emit(render(report) + f"\nThe spike driver failed: {type(exc).__name__}.\n", env)
        return 1
    emit(render(run), env)
    return 0


if __name__ == "__main__":
    sys.exit(main())
