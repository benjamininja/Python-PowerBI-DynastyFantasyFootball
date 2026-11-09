"""Source checks, fetch layer (#454 Brief B1): the only network path in the
script, and the RobotsGate every request must pass. GET only, one product
token on every request, no cookies, no auth. The security check (B2) and the
reading section (B3: robots and page signals, document discovery) sit on top of
this layer. Later briefs add the render and the evidence.

Never run live by an agent; tests inject the transport, clock and sleep.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import re
import socket
import ssl
import sys
import threading
import time
from dataclasses import dataclass, field, fields, replace
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from http.cookiejar import CookiePolicy
from pathlib import Path
from typing import Callable, Container
from urllib.parse import quote, urljoin, urlsplit

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
import etl_helpers  # noqa: E402
import requests  # noqa: E402
import yaml  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402
from protego import Protego  # noqa: E402

USER_AGENT = etl_helpers.ETL_USER_AGENT
PRODUCT_TOKEN = USER_AGENT.split("/", 1)[0]
CLAUDE_TOKENS = ("ClaudeBot", "Claude-User", "Claude-SearchBot", "anthropic-ai", "Claude-Web")
UNMATCHED_AGENT = "no-such-agent-zz"

SERVICE_HOSTS = frozenset({
    "transparencyreport.google.com",
    "data.iana.org",
    "hstspreload.org",
    "archive.org",
    "web.archive.org",
})

UNREAD_REFUSED_STATUS = "refused_status"
UNREAD_ROBOTS_BLOCKS_AGENT = "robots_blocks_agent"
UNREAD_RATE_LIMITED = "rate_limited"

ROBOTS_PATH = "/robots.txt"
MAX_ROBOTS_BYTES = 500 * 1024
MAX_PAGE_BYTES = 5 * 1024 * 1024
ROBOTS_MAX_AGE = 24 * 3600
MIN_DELAY = 5.0
SEGMENT_DELAY = 30.0
MAX_HOPS = 5
RATE_LIMIT_TRIES = 3
RATE_LIMIT_WAITS = (60.0, 300.0)
RETRY_AFTER_STOP = 600.0
REQUEST_TIMEOUT = 30
REDIRECT_CODES = (301, 302, 303, 307, 308)


class TransportError(Exception):
    pass


class TransportTimeout(TransportError):
    pass


class RobotsNotRead(Exception):
    pass


@dataclass
class Request:
    url: str
    headers: dict
    max_bytes: int


@dataclass
class Response:
    status: int
    headers: dict
    body: bytes = b""


class _NoCookies(CookiePolicy):
    netscape = True
    rfc2965 = False
    hide_cookie2 = False

    def set_ok(self, cookie, request):
        return False

    def return_ok(self, cookie, request):
        return False

    def domain_return_ok(self, domain, request):
        return False

    def path_return_ok(self, path, request):
        return False


class RequestsTransport:
    """The real transport: one GET, no redirects, no retries, no cookies, no
    env-derived auth. Not used by tests."""

    def __init__(self, timeout: float = REQUEST_TIMEOUT):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.cookies.set_policy(_NoCookies())
        self.session.trust_env = False

    def __call__(self, request: Request) -> Response:
        try:
            resp = self.session.get(request.url, headers=request.headers,
                                    timeout=self.timeout, allow_redirects=False, stream=True)
        except requests.Timeout as exc:
            raise TransportTimeout(str(exc)) from exc
        except requests.RequestException as exc:
            raise TransportError(f"{type(exc).__name__}: {exc}") from exc
        try:
            body = b""
            for chunk in resp.iter_content(65536):
                body += chunk
                if len(body) >= request.max_bytes:
                    break
        except requests.RequestException as exc:
            raise TransportError(f"{type(exc).__name__}: {exc}") from exc
        finally:
            resp.close()
        headers = {k.lower(): v for k, v in resp.headers.items()}
        return Response(resp.status_code, headers, body[:request.max_bytes])


def host_of(url: str) -> str | None:
    return urlsplit(url).hostname


def claude_groups(text: str) -> list[str]:
    names = set()
    for line in text.splitlines():
        m = re.match(r"\s*user-agent\s*:\s*(\S+)", line.split("#", 1)[0], re.IGNORECASE)
        if m:
            names.add(m.group(1).lower())
    return [t for t in CLAUDE_TOKENS if t.lower() in names]


def retry_after_seconds(headers: dict) -> float | None:
    raw = headers.get("retry-after")
    if raw is None:
        return None
    raw = raw.strip()
    if raw.isdigit():
        return float(raw)
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


@dataclass
class GateDecision:
    allowed: bool
    reason: str | None = None
    blocked_by: list = field(default_factory=list)
    detail: str = ""


@dataclass
class RobotsResult:
    host: str
    url: str
    code: int | None
    read: date
    outcome: str  # rules | no_rules | stop | disallow_all
    reason: str | None = None
    detail: str = ""
    claude_groups: list = field(default_factory=list)
    blocks_agent: bool = False
    crawl_delay: float | None = None
    sha256: str | None = None
    strict_transport_security: str | None = None
    fetched_at: float = 0.0
    rules: Protego | None = field(default=None, repr=False, compare=False)
    text: str | None = field(default=None, repr=False, compare=False)

    def blocked_tokens(self, url: str) -> list:
        if self.rules is None:
            return []
        blocked = []
        if not self.rules.can_fetch(url, PRODUCT_TOKEN):
            blocked.append(PRODUCT_TOKEN)
        if not self.rules.can_fetch(url, UNMATCHED_AGENT):
            blocked.append("*")
        for token in self.claude_groups:
            if not self.rules.can_fetch(url, token):
                blocked.append(token)
        return blocked


class RobotsGate:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.results: dict[str, RobotsResult] = {}

    def record(self, result: RobotsResult) -> None:
        result.fetched_at = self.clock()
        self.results[result.host] = result

    def result(self, host: str) -> RobotsResult | None:
        return self.results.get(host)

    def fresh(self, host: str) -> bool:
        res = self.results.get(host)
        return res is not None and self.clock() - res.fetched_at < ROBOTS_MAX_AGE

    def decide(self, url: str) -> GateDecision:
        host = host_of(url)
        if host is None or not self.fresh(host):
            raise RobotsNotRead(f"robots.txt for {host} has not been read: {url}")
        res = self.results[host]
        if res.outcome in ("stop", "disallow_all"):
            return GateDecision(False, res.reason, [], res.detail)
        blocked = res.blocked_tokens(url)
        if blocked:
            return GateDecision(False, UNREAD_ROBOTS_BLOCKS_AGENT, blocked,
                                "robots.txt disallows: " + ", ".join(blocked))
        return GateDecision(True)

    def allowed(self, url: str) -> bool:
        return self.decide(url).allowed


@dataclass
class FetchResult:
    url: str
    outcome: str = "failed"  # ok | unread | deferred | failed
    status: int | None = None
    headers: dict = field(default_factory=dict)
    body: bytes = b""
    final_url: str | None = None
    hops: list = field(default_factory=list)
    stopped_at: str | None = None
    unread: str | None = None
    detail: str = ""
    method: str = "http_get"
    render_allowed: list = field(default_factory=list)
    render_aborted: list = field(default_factory=list)

    def fill(self, other: "FetchResult") -> None:
        for f in fields(self):
            setattr(self, f.name, getattr(other, f.name))


@dataclass
class _Stop:
    reason: str
    code: int | None
    date: date
    detail: str


@dataclass
class _Host:
    last_request: float | None = None
    segmented: bool = False
    saw_429: bool = False
    robots_deferred: bool = False
    rate_limited: _Stop | None = None
    refused: _Stop | None = None


@dataclass
class _Refusal:
    outcome: str  # failed | unread | deferred
    reason: str | None
    detail: str


@dataclass
class _Followed:
    kind: str  # ok | exhausted | long_retry | transport | too_many_redirects | refused
    response: Response | None = None
    hops: list = field(default_factory=list)
    detail: str = ""
    saw_429: bool = False
    refused_at: str | None = None
    refusal: _Refusal | None = None


@dataclass
class _Deferred:
    url: str
    result: FetchResult
    tries: int


class Fetcher:
    def __init__(self, transport: Callable[[Request], Response] | None = None, *,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 today: Callable[[], date] = date.today):
        self.transport = transport if transport is not None else RequestsTransport()
        self.clock = clock
        self.sleep = sleep
        self.today = today
        self.gate = RobotsGate(clock)
        self.service_hosts = set(SERVICE_HOSTS)
        self.secure_hosts: set[str] = set()
        self.hosts: dict[str, _Host] = {}
        self._deferred: list[_Deferred] = []
        self._ran_deferred = False

    def mark_secure(self, host: str) -> None:
        self.secure_hosts.add(host.lower())

    def register_rdap_host(self, base_url: str) -> None:
        parts = urlsplit(base_url)
        if parts.scheme != "https" or not parts.hostname:
            raise ValueError(f"RDAP base URL must be https: {base_url}")
        self.service_hosts.add(parts.hostname)

    def robots(self, host: str) -> RobotsResult | None:
        return self.gate.result(host)

    def get(self, url: str) -> FetchResult:
        return self._fetch(url, tries=RATE_LIMIT_TRIES, allow_defer=True)

    def read_robots(self, host: str) -> RobotsResult | None:
        host = host.lower()
        if host not in self.service_hosts and host not in self.secure_hosts:
            raise RobotsNotRead(f"security check not passed for {host}")
        if not self._host(host).robots_deferred and not self.gate.fresh(host):
            self._read_robots(host, tries=RATE_LIMIT_TRIES)
        return self.gate.result(host)

    def run_deferred(self) -> None:
        if self._ran_deferred:
            return
        self._ran_deferred = True
        queue, self._deferred = self._deferred, []
        for host, state in list(self.hosts.items()):
            if state.robots_deferred:
                state.robots_deferred = False
                fol = self._follow(f"https://{host}{ROBOTS_PATH}", robots_read=True,
                                   tries=1, max_bytes=MAX_ROBOTS_BYTES)
                self._settle_robots(host, fol, deferred_try=True)
        for item in queue:
            item.result.fill(self._fetch(item.url, tries=item.tries, allow_defer=False))

    def _host(self, host: str) -> _Host:
        return self.hosts.setdefault(host, _Host())

    def _pace(self, host: str) -> None:
        state = self._host(host)
        res = self.gate.result(host)
        delay = res.crawl_delay if res is not None and res.crawl_delay is not None else MIN_DELAY
        if state.segmented:
            delay = max(delay, SEGMENT_DELAY)
        if state.last_request is not None:
            wait = state.last_request + delay - self.clock()
            if wait > 0:
                self.sleep(wait)
        state.last_request = self.clock()

    def _send(self, url: str, max_bytes: int) -> Response:
        self._pace(host_of(url))
        return self.transport(Request(url=url, headers={"User-Agent": USER_AGENT},
                                      max_bytes=max_bytes))

    def _get_once(self, url: str, max_bytes: int, tries: int):
        count_429 = 0
        for attempt in range(tries):
            resp = self._send(url, max_bytes)
            if resp.status != 429:
                return "ok", resp, count_429
            count_429 += 1
            wait = retry_after_seconds(resp.headers)
            if wait is not None and wait > RETRY_AFTER_STOP:
                return "long_retry", resp, count_429
            if attempt == tries - 1:
                return "exhausted", resp, count_429
            self.sleep(wait if wait is not None else RATE_LIMIT_WAITS[attempt])

    def _admit(self, url: str, *, robots_read: bool) -> _Refusal | None:
        parts = urlsplit(url)
        host = parts.hostname
        if parts.scheme != "https" or not host:
            return _Refusal("failed", None, f"only https URLs are fetched: {url}")
        if host not in self.service_hosts and host not in self.secure_hosts:
            return _Refusal("failed", None, f"security check not passed for {host}")
        if parts.path == ROBOTS_PATH:
            return None
        if robots_read:
            return _Refusal("failed", None, "robots.txt redirected away from /robots.txt")
        state = self._host(host)
        if not state.robots_deferred and not self.gate.fresh(host):
            refusal = self._read_robots(host, tries=RATE_LIMIT_TRIES)
            if refusal is not None:
                return refusal
        if state.robots_deferred:
            return _Refusal("deferred", None, f"robots.txt for {host} is deferred")
        if state.refused is not None:
            return _Refusal("unread", UNREAD_REFUSED_STATUS, state.refused.detail)
        if state.rate_limited is not None:
            return _Refusal("unread", UNREAD_RATE_LIMITED, state.rate_limited.detail)
        decision = self.gate.decide(url)
        if not decision.allowed:
            return _Refusal("unread", decision.reason, decision.detail)
        return None

    def _follow(self, url: str, *, robots_read: bool, tries: int, max_bytes: int) -> _Followed:
        hops: list = []
        saw_429 = False
        current = url
        for hop in range(MAX_HOPS + 1):
            refusal = self._admit(current, robots_read=robots_read)
            if refusal is not None:
                return _Followed("refused", None, hops, refusal.detail, saw_429, current, refusal)
            hops.append(current)
            try:
                kind, resp, count_429 = self._get_once(current, max_bytes, tries)
            except TransportError as exc:
                return _Followed("transport", None, hops, f"{type(exc).__name__}: {exc}", saw_429)
            saw_429 = saw_429 or count_429 > 0
            if count_429:
                self._host(host_of(current)).saw_429 = True
            if kind != "ok":
                return _Followed(kind, resp, hops, "", saw_429)
            if resp.status in REDIRECT_CODES and resp.headers.get("location"):
                if hop == MAX_HOPS:
                    return _Followed("too_many_redirects", resp, hops,
                                     f"more than {MAX_HOPS} redirects", saw_429)
                current = urljoin(current, resp.headers["location"])
                continue
            return _Followed("ok", resp, hops, "", saw_429)

    def _read_robots(self, host: str, *, tries: int) -> _Refusal | None:
        fol = self._follow(f"https://{host}{ROBOTS_PATH}", robots_read=True, tries=tries,
                           max_bytes=MAX_ROBOTS_BYTES)
        return self._settle_robots(host, fol, deferred_try=False)

    def _settle_robots(self, host: str, fol: _Followed, *, deferred_try: bool) -> _Refusal | None:
        state = self._host(host)
        url = f"https://{host}{ROBOTS_PATH}"
        if fol.kind == "refused":
            return fol.refusal
        if fol.kind == "exhausted":
            if deferred_try:
                self._store_robots(host, url, None, "stop", UNREAD_RATE_LIMITED, 429,
                                   "429 on the deferred try")
            else:
                state.robots_deferred = True
            return None
        if fol.kind == "long_retry":
            wait = retry_after_seconds(fol.response.headers)
            self._store_robots(host, url, fol.response, "stop", UNREAD_RATE_LIMITED, 429,
                               f"Retry-After {wait:.0f} s is over {RETRY_AFTER_STOP:.0f} s")
        elif fol.kind in ("transport", "too_many_redirects"):
            self._store_robots(host, url, None, "disallow_all", UNREAD_REFUSED_STATUS, None, fol.detail)
        else:
            self._settle_response(host, url, fol.response)
        if deferred_try or fol.saw_429:
            state.segmented = True
        return None

    def _settle_response(self, host: str, url: str, resp: Response) -> None:
        code = resp.status
        if 200 <= code < 300:
            self._parse_robots(host, url, resp)
        elif code in (401, 403):
            self._store_robots(host, url, resp, "stop", UNREAD_REFUSED_STATUS, code,
                               f"robots.txt answered {code}")
        elif 500 <= code < 600:
            self._store_robots(host, url, resp, "disallow_all", UNREAD_REFUSED_STATUS, code,
                               f"robots.txt answered {code}: complete disallow")
        elif 400 <= code < 500:
            self._store_robots(host, url, resp, "no_rules", None, code, f"robots.txt answered {code}")
        else:
            self._store_robots(host, url, resp, "disallow_all", UNREAD_REFUSED_STATUS, code,
                               f"robots.txt answered {code}: complete disallow")

    def _store_robots(self, host, url, resp, outcome, reason, code, detail) -> RobotsResult:
        result = RobotsResult(
            host=host, url=url, code=code, read=self.today(), outcome=outcome, reason=reason,
            detail=detail,
            strict_transport_security=resp.headers.get("strict-transport-security") if resp else None)
        self.gate.record(result)
        return result

    def _parse_robots(self, host: str, url: str, resp: Response) -> None:
        raw = resp.body[:MAX_ROBOTS_BYTES]
        text = raw.decode("utf-8-sig", errors="replace")
        rules = Protego.parse(text)
        delay = rules.crawl_delay(PRODUCT_TOKEN)
        result = self._store_robots(host, url, resp, "rules", None, resp.status, "")
        result.rules = rules
        result.text = text
        result.claude_groups = claude_groups(text)
        result.crawl_delay = float(delay) if delay is not None else None
        if result.crawl_delay is not None and result.crawl_delay > RETRY_AFTER_STOP:
            self._rate_limit(host, f"Crawl-delay {result.crawl_delay:g} s is over "
                                   f"{RETRY_AFTER_STOP:.0f} s")
        result.sha256 = hashlib.sha256(raw).hexdigest()
        result.blocks_agent = bool(result.blocked_tokens(f"https://{host}/"))

    def _rate_limit(self, host: str, detail: str) -> None:
        self._host(host).rate_limited = _Stop(UNREAD_RATE_LIMITED, 429, self.today(), detail)

    def _fetch(self, url: str, *, tries: int, allow_defer: bool) -> FetchResult:
        res = FetchResult(url=url)
        fol = self._follow(url, robots_read=False, tries=tries, max_bytes=MAX_PAGE_BYTES)
        res.hops = list(fol.hops)
        if fol.kind == "refused":
            refusal = fol.refusal
            res.stopped_at = fol.refused_at
            res.detail = refusal.detail
            if refusal.outcome == "deferred" and allow_defer:
                res.outcome = "deferred"
                self._deferred.append(_Deferred(url, res, RATE_LIMIT_TRIES))
            elif refusal.outcome == "unread":
                res.outcome = "unread"
                res.unread = refusal.reason
            else:
                res.outcome = "failed"
            return res
        if fol.kind in ("transport", "too_many_redirects"):
            res.detail = fol.detail
            return res
        host = host_of(fol.hops[-1])
        if fol.kind == "long_retry":
            wait = retry_after_seconds(fol.response.headers)
            res.detail = f"Retry-After {wait:.0f} s is over {RETRY_AFTER_STOP:.0f} s"
            self._rate_limit(host, res.detail)
            res.outcome, res.unread = "unread", UNREAD_RATE_LIMITED
            return res
        if fol.kind == "exhausted":
            if allow_defer:
                res.outcome = "deferred"
                res.detail = "429 on all tries; one deferred try at the end of the run"
                self._deferred.append(_Deferred(url, res, 1))
            else:
                res.detail = "429 on the deferred try"
                self._rate_limit(host, res.detail)
                res.outcome, res.unread = "unread", UNREAD_RATE_LIMITED
            return res
        resp = fol.response
        res.status, res.headers, res.body = resp.status, resp.headers, resp.body
        res.final_url = fol.hops[-1]
        if resp.status in (401, 403):
            res.outcome, res.unread = "unread", UNREAD_REFUSED_STATUS
            res.detail = f"answered {resp.status}"
            self._host(host).refused = _Stop(
                UNREAD_REFUSED_STATUS, resp.status, self.today(),
                f"an earlier read of {host} answered {resp.status}")
        else:
            res.outcome = "ok"
        return res


SB_STATUS_URL = "https://transparencyreport.google.com/transparencyreport/api/v3/safebrowsing/status?site="
SB_CONTROLS = {
    "malware": "testsafebrowsing.appspot.com/s/malware.html",
    "phishing": "testsafebrowsing.appspot.com/s/phishing.html",
    "unwanted": "testsafebrowsing.appspot.com/s/unwanted.html",
}
SB_PREFIX = ")]}'"
SB_ITEMS = 10
SB_FIRST = "sb.ssr"
SB_CLEAN = 1
SB_UNSAFE = 2
SB_STALE_DAYS = 30
TLS_EXPIRING_DAYS = 7
YOUNG_DAYS = 365
IANA_BOOTSTRAP_URL = "https://data.iana.org/rdap/dns.json"
HSTS_PRELOAD_URL = "https://hstspreload.org/api/v2/status?domain="
MANIFEST = REPO / "docs" / "sources.yml"

FLAG_ORDER = ("young_domain", "age_unknown", "tls_expiring", "tls_failed", "sb_unsafe",
              "sb_no_verdict", "sb_stale", "nxdomain", "controls_failed")
NEVER_READ_FLAGS = frozenset({"controls_failed", "sb_unsafe", "nxdomain", "tls_failed"})
HELD_FLAGS = frozenset({"young_domain", "age_unknown", "sb_no_verdict"})
NAME_NOT_FOUND = frozenset(
    code for code in (getattr(socket, "EAI_NONAME", None), getattr(socket, "EAI_NODATA", None), 11001)
    if code is not None)


@dataclass
class SafeBrowsing:
    code: int
    scan: date


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_safe_browsing(body: bytes) -> SafeBrowsing | None:
    text = body.decode("utf-8-sig", errors="replace").lstrip()
    if not text.startswith(SB_PREFIX):
        return None
    try:
        data = json.loads(text[len(SB_PREFIX):])
    except ValueError:
        return None
    if not isinstance(data, list) or len(data) != 1:
        return None
    row = data[0]
    if not isinstance(row, list) or len(row) != SB_ITEMS or row[0] != SB_FIRST:
        return None
    code, stamp = row[1], row[7]
    if not _is_int(code) or not _is_int(stamp):
        return None
    try:
        scan = datetime.fromtimestamp(stamp / 1000, tz=timezone.utc).date()
    except (OverflowError, OSError, ValueError):
        return None
    return SafeBrowsing(code, scan)


def safe_browsing_url(site: str) -> str:
    return SB_STATUS_URL + quote(site, safe="/")


@dataclass
class Controls:
    malware: int | None
    phishing: int | None
    unwanted: int | None
    shape_ok: bool

    @property
    def passed(self) -> bool:
        return self.shape_ok and all(
            code == SB_UNSAFE for code in (self.malware, self.phishing, self.unwanted))

    def block(self) -> dict:
        return {"malware": self.malware, "phishing": self.phishing,
                "unwanted": self.unwanted, "shape_ok": self.shape_ok}


def parse_hsts_max_age(value: str | None) -> int | None:
    if not value:
        return None
    m = re.search(r"max-age\s*=\s*\"?(\d+)", value, re.IGNORECASE)
    return int(m.group(1)) if m else None


def tls_fields(cert: dict, version: str | None) -> dict:
    issuer = None
    for rdn in cert.get("issuer", ()):
        for key, value in rdn:
            if key == "organizationName":
                issuer = value
            elif key == "commonName" and issuer is None:
                issuer = value
    not_after = None
    if cert.get("notAfter"):
        stamp = ssl.cert_time_to_seconds(cert["notAfter"])
        not_after = datetime.fromtimestamp(stamp, tz=timezone.utc).date()
    return {"ok": True, "issuer": issuer, "not_after": not_after, "version": version}


def default_tls_probe(host: str, port: int = 443, timeout: float = REQUEST_TIMEOUT) -> dict:
    context = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=timeout) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                return tls_fields(tls.getpeercert(), tls.version())
    except OSError as exc:
        return {"ok": False, "issuer": None, "not_after": None, "version": None,
                "error": f"{type(exc).__name__}: {exc}"}


def registration_date(body: bytes) -> date | None:
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    events = data.get("events") if isinstance(data, dict) else None
    if not isinstance(events, list):
        return None
    for event in events:
        if isinstance(event, dict) and event.get("eventAction") == "registration":
            stamp = event.get("eventDate")
            if isinstance(stamp, str):
                try:
                    return date.fromisoformat(stamp[:10])
                except ValueError:
                    return None
    return None


def load_confirmed_hosts(path: Path = MANIFEST) -> set[str]:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    hosts = set()
    for source in data.get("sources") or []:
        security = source.get("security") if isinstance(source, dict) else None
        if not isinstance(security, dict):
            continue
        confirmed = security.get("confirmed")
        host = security.get("host")
        if (isinstance(host, str) and isinstance(confirmed, dict)
                and confirmed.get("by") and confirmed.get("date") is not None):
            hosts.add(host.lower())
    return hosts


@dataclass
class SecurityResult:
    host: str
    checked: date
    controls: dict | None = None
    safe_browsing: dict | None = None
    dns: str | None = None
    tls: dict | None = None
    hsts: dict | None = None
    registered: date | None = None
    flags: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    readable: bool = False
    held: bool = False
    failed: str | None = None

    def block(self) -> dict | None:
        if self.failed is not None:
            return None
        return {
            "checked": self.checked, "host": self.host, "controls": self.controls,
            "safe_browsing": self.safe_browsing, "dns": self.dns, "tls": self.tls,
            "hsts": self.hsts, "registered": self.registered, "flags": list(self.flags),
        }


class SecurityChecker:
    def __init__(self, fetcher: Fetcher, *,
                 resolver: Callable = socket.getaddrinfo,
                 tls_probe: Callable = default_tls_probe,
                 confirmed: Container[str] = (),
                 today: Callable[[], date] | None = None):
        self.fetcher = fetcher
        self.resolver = resolver
        self.tls_probe = tls_probe
        self.confirmed = confirmed
        self.today = today if today is not None else fetcher.today
        self._controls: Controls | None = None
        self._bootstrap: list | None = None
        self._bootstrap_read = False

    def controls(self) -> Controls:
        if self._controls is None:
            codes, shape_ok = {}, True
            for name, site in SB_CONTROLS.items():
                kind, reading = self._safe_browsing(site)
                codes[name] = reading.code if reading is not None else None
                shape_ok = shape_ok and kind != "bad_shape"
            self._controls = Controls(codes["malware"], codes["phishing"], codes["unwanted"], shape_ok)
        return self._controls

    def _safe_browsing(self, site: str) -> tuple[str, SafeBrowsing | None]:
        res = self.fetcher.get(safe_browsing_url(site))
        if res.outcome != "ok" or res.status != 200:
            return "unavailable", None
        reading = parse_safe_browsing(res.body)
        if reading is None:
            return "bad_shape", None
        return "ok", reading

    def check(self, host: str) -> SecurityResult:
        host = host.lower()
        result = SecurityResult(host=host, checked=self.today())
        controls = self.controls()
        result.controls = controls.block()
        if not controls.passed:
            result.safe_browsing = {"via": "transparency_report", "code": None, "google_scan": None}
            result.flags.append("controls_failed")
            return self._finish(result)
        answer = self._resolves(host, result)
        if answer is None:
            return self._finish(result)
        if not answer:
            result.dns = "nxdomain"
            result.flags.append("nxdomain")
            return self._finish(result)
        result.dns = "resolves"
        self._host_safe_browsing(host, result)
        self._host_registration(host, result)
        if not self._blocked(result) and not self._held(result):
            self._host_tls(host, result)
        return self._finish(result)

    def _blocked(self, result: SecurityResult) -> bool:
        return any(flag in NEVER_READ_FLAGS for flag in result.flags)

    def _held(self, result: SecurityResult) -> bool:
        return (any(flag in HELD_FLAGS for flag in result.flags)
                and result.host not in self.confirmed)

    def _finish(self, result: SecurityResult) -> SecurityResult:
        result.flags = [flag for flag in FLAG_ORDER if flag in result.flags]
        result.held = self._held(result)
        result.readable = (not self._blocked(result) and not result.held
                           and result.tls is not None)
        if result.readable:
            self.fetcher.mark_secure(result.host)
            self._host_hsts(result.host, result)
        return result

    def _resolves(self, host: str, result: SecurityResult) -> bool | None:
        try:
            answers = self.resolver(host, 443)
        except socket.gaierror as exc:
            if exc.errno in NAME_NOT_FOUND:
                result.notes.append(f"dns: {exc}")
                return False
            result.failed = f"dns: {exc}"
            result.notes.append(result.failed)
            return None
        return bool(answers)

    def _host_safe_browsing(self, host: str, result: SecurityResult) -> None:
        kind, reading = self._safe_browsing(host)
        scan = reading.scan if reading is not None else None
        result.safe_browsing = {"via": "transparency_report",
                                "code": reading.code if reading is not None else None,
                                "google_scan": scan}
        if kind == "bad_shape":
            result.flags.append("controls_failed")
            result.notes.append("safe browsing: response shape changed")
        elif reading is None:
            result.flags.append("sb_no_verdict")
        elif reading.code == SB_UNSAFE:
            result.flags.append("sb_unsafe")
        elif reading.code != SB_CLEAN:
            result.flags.append("sb_no_verdict")
        if scan is not None and (self.today() - scan).days > SB_STALE_DAYS:
            result.flags.append("sb_stale")

    def _host_registration(self, host: str, result: SecurityResult) -> None:
        result.registered = self._registered(host, result)
        if result.registered is None:
            result.flags.append("age_unknown")
        elif (self.today() - result.registered).days < YOUNG_DAYS:
            result.flags.append("young_domain")

    def _host_tls(self, host: str, result: SecurityResult) -> None:
        probe = self.tls_probe(host)
        tls = {key: probe.get(key) for key in ("ok", "issuer", "not_after", "version")}
        result.tls = tls
        if probe.get("error"):
            result.notes.append(f"tls: {probe['error']}")
        not_after = tls["not_after"]
        if not tls["ok"] or not_after is None or not_after < self.today():
            tls["ok"] = False
            result.flags.append("tls_failed")
        elif (not_after - self.today()).days < TLS_EXPIRING_DAYS:
            result.flags.append("tls_expiring")

    def _host_hsts(self, host: str, result: SecurityResult) -> None:
        robots = self.fetcher.read_robots(host)
        header = robots.strict_transport_security if robots is not None else None
        result.hsts = {"max_age": parse_hsts_max_age(header), "preloaded": self._preloaded(host)}

    def _preloaded(self, host: str) -> bool | None:
        res = self.fetcher.get(HSTS_PRELOAD_URL + quote(host, safe=""))
        if res.outcome != "ok" or res.status != 200:
            return None
        try:
            data = json.loads(res.body.decode("utf-8", errors="replace"))
        except ValueError:
            return None
        if not isinstance(data, dict) or not isinstance(data.get("status"), str):
            return None
        return data["status"] == "preloaded"

    def _rdap_base(self, tld: str) -> str | None:
        if not self._bootstrap_read:
            self._bootstrap_read = True
            res = self.fetcher.get(IANA_BOOTSTRAP_URL)
            if res.outcome == "ok" and res.status == 200:
                try:
                    data = json.loads(res.body.decode("utf-8", errors="replace"))
                    services = data.get("services")
                    self._bootstrap = services if isinstance(services, list) else None
                except (ValueError, AttributeError):
                    self._bootstrap = None
        for entry in self._bootstrap or []:
            if not (isinstance(entry, list) and len(entry) == 2):
                continue
            tlds, urls = entry
            if tld in [str(t).lower() for t in tlds]:
                for url in urls:
                    if str(url).startswith("https://"):
                        self.fetcher.register_rdap_host(url)
                        return url
        return None

    def _registered(self, host: str, result: SecurityResult) -> date | None:
        labels = host.split(".")
        if len(labels) < 2:
            return None
        base = self._rdap_base(labels[-1])
        if base is None:
            result.notes.append(f"rdap: no server for .{labels[-1]}")
            return None
        for i in range(len(labels) - 1):
            name = ".".join(labels[i:])
            res = self.fetcher.get(base.rstrip("/") + "/domain/" + name)
            if res.outcome != "ok":
                result.notes.append(f"rdap: {res.outcome}")
                return None
            if res.status == 200:
                return registration_date(res.body)
            if res.status not in (400, 404):
                result.notes.append(f"rdap: answered {res.status}")
                return None
        return None


ESSENTIAL_KINDS = ("terms", "privacy")
STAGES = ("footer", "menu", "sitemap", "legal_hub", "linked_from_doc", "operator_domain")
SITEMAP_PATHS = ("/sitemap.xml", "/wp-sitemap.xml")
TDMREP_PATH = "/.well-known/tdmrep.json"
LLMS_PATH = "/llms.txt"
MAX_DOCUMENTS = 6
MAX_HUBS = 2
MAX_OPERATOR_LINKS = 3
MAX_CHILD_SITEMAPS = 3
MAX_SITEMAP_SEGMENTS = 2
MAX_SITEMAP_WORDS = 5
TDMREP_MAX_CHARS = 64 * 1024
CONTENT_SIGNAL_KEYS = ("search", "ai-input", "ai-train")
CONTENT_USAGE_KEYS = ("train-ai", "ai-use", "search")
NOAI_TOKENS = ("noai", "noimageai")
UNREAD_TOOL_REFUSED = "tool_refused"
UNREAD_DNS = "dns"
UNREAD_JS_RENDERED = "js_rendered"
STOP_UNREAD = (UNREAD_REFUSED_STATUS, UNREAD_RATE_LIMITED)

DATE_LINE = re.compile(
    r"\b(?:last\s+(?:updated|modified|revised)|effective(?:\s+date)?|updated|revised)\b", re.IGNORECASE)
MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})


def classify_link(text: str) -> str | None:
    t = text.lower()
    if re.search(r"\bapi\b", t):
        return "api_terms" if re.search(r"terms|licen[cs]e|polic|legal|conditions", t) else None
    if "terms" in t:
        return "terms"
    if "privacy" in t:
        return "privacy"
    if re.search(r"licen[cs]e", t):
        return "licence"
    if re.search(r"legal|polic(?:y|ies)", t):
        return "hub"
    return None


def classify_path(url: str) -> str | None:
    segments = [s for s in urlsplit(url).path.split("/") if s]
    words = [w for s in segments for w in re.split(r"[^a-z0-9]+", s.lower()) if w]
    if not segments or len(segments) > MAX_SITEMAP_SEGMENTS or len(words) > MAX_SITEMAP_WORDS:
        return None
    return classify_link(" ".join(words))


def same_site(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return a.lower().removeprefix("www.") == b.lower().removeprefix("www.")


def parse_date_text(text: str) -> date | None:
    patterns = (
        (r"(\d{4})-(\d{2})-(\d{2})", lambda m: (m[1], m[2], m[3])),
        (r"([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", lambda m: (m[3], m[1], m[2])),
        (r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})", lambda m: (m[3], m[2], m[1])),
    )
    for pattern, order in patterns:
        m = re.search(pattern, text)
        if not m:
            continue
        year, month, day = order(m)
        try:
            month_no = int(month) if month.isdigit() else MONTHS[month.lower()]
            return date(int(year), month_no, int(day))
        except (KeyError, ValueError):
            continue
    return None


@dataclass
class RobotsGroup:
    agents: list = field(default_factory=list)
    content_signal: list = field(default_factory=list)
    content_usage: list = field(default_factory=list)
    crawl_delay: list = field(default_factory=list)
    sealed: bool = False


def parse_robots_groups(text: str) -> tuple[list, list]:
    groups: list[RobotsGroup] = []
    sitemaps: list[str] = []
    current: RobotsGroup | None = None
    for raw in text.splitlines():
        line = raw.strip()
        name, sep, value = line.split("#", 1)[0].partition(":")
        if not sep:
            continue
        key, value = name.strip().lower(), value.strip()
        if key == "sitemap":
            if value:
                sitemaps.append(value)
            continue
        if key == "user-agent":
            if current is None or current.sealed:
                current = RobotsGroup()
                groups.append(current)
            current.agents.append(value)
            continue
        if current is None:
            current = RobotsGroup()
            groups.append(current)
        current.sealed = True
        if key == "content-signal":
            current.content_signal.append(line)
        elif key == "content-usage":
            current.content_usage.append(line)
        elif key == "crawl-delay":
            current.crawl_delay.append(line)
    return groups, sitemaps


def interpret_signal_line(line: str, defined: tuple) -> tuple[dict, dict]:
    known: dict = {}
    unknown: dict = {}
    for part in line.split("#", 1)[0].partition(":")[2].split(","):
        part = part.strip()
        if not part:
            continue
        key, sep, value = part.partition("=")
        key = key.strip().lower()
        (known if key in defined else unknown)[key] = value.strip() if sep else None
    return known, unknown


def _signal_entries(groups: list, attr: str, defined: tuple | None) -> list:
    entries = []
    for group in groups:
        for line in getattr(group, attr):
            entry = {"agents": list(group.agents), "line": line}
            if defined is not None:
                entry["known"], entry["unknown"] = interpret_signal_line(line, defined)
            entries.append(entry)
    return entries


@dataclass
class RobotsSignals:
    url: str
    code: int | None
    read: date
    outcome: str
    claude_groups: list
    blocks_agent: bool
    sha256: str | None
    content_signal: list
    content_usage: list
    crawl_delay: list
    sitemaps: list

    def block(self) -> dict:
        return {
            "url": self.url, "code": self.code, "read": self.read,
            "claude_groups": list(self.claude_groups), "blocks_agent": self.blocks_agent,
            "content_signal": self.content_signal or None,
            "content_usage": self.content_usage or None,
            "crawl_delay": self.crawl_delay or None, "sha256": self.sha256,
        }


def robots_signals(result: RobotsResult) -> RobotsSignals:
    groups, sitemaps = parse_robots_groups(result.text or "")
    return RobotsSignals(
        url=result.url, code=result.code, read=result.read, outcome=result.outcome,
        claude_groups=list(result.claude_groups), blocks_agent=result.blocks_agent,
        sha256=result.sha256,
        content_signal=_signal_entries(groups, "content_signal", CONTENT_SIGNAL_KEYS),
        content_usage=_signal_entries(groups, "content_usage", CONTENT_USAGE_KEYS),
        crawl_delay=_signal_entries(groups, "crawl_delay", None), sitemaps=sitemaps)


@dataclass
class PageSignals:
    url: str
    x_robots_tag: str | None = None
    content_usage: str | None = None
    tdm_reservation: str | None = None
    tdm_policy: str | None = None
    meta_robots: str | None = None
    meta_tdm_reservation: str | None = None
    meta_tdm_policy: str | None = None
    noai: list = field(default_factory=list)


def _meta(soup, name: str) -> str | None:
    if soup is None:
        return None
    for tag in soup.find_all("meta"):
        if str(tag.get("name") or "").strip().lower() == name and tag.get("content") is not None:
            return str(tag.get("content"))
    return None


def page_signals(url: str, headers: dict, soup) -> PageSignals:
    h = {k.lower(): v for k, v in headers.items()}
    signals = PageSignals(
        url=url, x_robots_tag=h.get("x-robots-tag"), content_usage=h.get("content-usage"),
        tdm_reservation=h.get("tdm-reservation"), tdm_policy=h.get("tdm-policy"),
        meta_robots=_meta(soup, "robots"), meta_tdm_reservation=_meta(soup, "tdm-reservation"),
        meta_tdm_policy=_meta(soup, "tdm-policy"))
    for value in (signals.x_robots_tag, signals.meta_robots):
        for token in re.split(r"[\s,]+", value or ""):
            if token.lower() in NOAI_TOKENS:
                signals.noai.append(token)
    return signals


@dataclass(frozen=True)
class Link:
    url: str
    text: str
    region: str


@dataclass
class ParsedPage:
    url: str
    content_type: str
    html: bool
    links: list
    signals: PageSignals
    copyright_line: str | None = None
    date_line: str | None = None
    date: date | None = None


_LEAF_BLOCKS = ["p", "small", "div", "li", "span", "address", "footer"]


def _marks(tag) -> str:
    return " ".join([tag.get("id") or ""] + list(tag.get("class") or [])).lower()


def _region(tag) -> str:
    menu = False
    for parent in tag.parents:
        marks = _marks(parent)
        if parent.name == "footer" or "footer" in marks:
            return "footer"
        if parent.name in ("nav", "header") or re.search(r"(?:^|[\s_-])(?:nav|menu)", marks):
            menu = True
    return "menu" if menu else "body"


def _link_text(tag) -> str:
    text = " ".join(tag.get_text(" ", strip=True).split())
    return text or " ".join(str(tag.get("aria-label") or tag.get("title") or "").split())


def extract_links(soup, base_url: str) -> list:
    links, seen = [], set()
    for tag in soup.find_all("a", href=True):
        href = str(tag["href"]).strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        url = urljoin(base_url, href).split("#", 1)[0]
        text = _link_text(tag)
        key = (url, text)
        if key in seen:
            continue
        seen.add(key)
        links.append(Link(url, text, _region(tag)))
    return links


def _copyright_line(soup) -> str | None:
    footers = [t for t in soup.find_all(True) if t.name == "footer" or "footer" in _marks(t)]
    for footer in footers:
        for tag in footer.find_all(_LEAF_BLOCKS) + [footer]:
            if tag is not footer and tag.find(_LEAF_BLOCKS):
                continue
            text = " ".join(tag.get_text(" ", strip=True).split())
            if text and re.search(r"©|copyright|all rights reserved", text, re.IGNORECASE):
                return text
    return None


def _date_line(soup) -> str | None:
    for text in (" ".join(chunk.split()) for chunk in soup.get_text("\n").splitlines()):
        if text and len(text) <= 200 and DATE_LINE.search(text):
            return text
    return None


def is_html_response(res: FetchResult) -> bool:
    content_type = res.headers.get("content-type", "")
    return "html" in content_type.lower() or (
        not content_type and res.body.lstrip()[:1] == b"<")


def parse_page(url: str, res: FetchResult) -> ParsedPage:
    content_type = res.headers.get("content-type", "")
    if not is_html_response(res):
        return ParsedPage(url, content_type, False, [], page_signals(url, res.headers, None))
    soup = BeautifulSoup(res.body, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    line = _date_line(soup)
    return ParsedPage(
        url=url, content_type=content_type, html=True, links=extract_links(soup, url),
        signals=page_signals(url, res.headers, soup), copyright_line=_copyright_line(soup),
        date_line=line, date=parse_date_text(line) if line else None)


@dataclass
class Candidate:
    kind: str
    url: str
    text: str | None
    place: str
    page: str


@dataclass
class DocumentFind:
    kind: str
    url: str
    page: str
    place: str
    link_text: str | None
    read: date
    fetch: FetchResult | None = None
    parsed: ParsedPage | None = None
    unread_reason: str | None = None
    note: str = ""

    @property
    def unread(self) -> str | None:
        if self.unread_reason is not None:
            return self.unread_reason
        if self.fetch is not None and self.fetch.outcome == "unread":
            return self.fetch.unread
        return None

    def block(self) -> dict:
        return {
            "kind": self.kind, "url": self.url,
            "reached_from": {"page": self.page, "place": self.place, "link_text": self.link_text},
            "read": self.read, "page_date": self.parsed.date if self.parsed else None,
            "read_by": "script", "method": self.fetch.method if self.fetch is not None else "http_get",
            "unread": self.unread,
            "archive": None, "capture_sha256": None,
        }


@dataclass
class NotFound:
    kind: str
    looked: list
    date: date
    copyright_line: str | None = None

    def block(self) -> dict:
        return {"kind": self.kind, "looked": list(self.looked), "date": self.date, "by": "script"}


@dataclass
class HostReading:
    host: str
    start_url: str
    read: date
    skipped: str | None = None
    robots: RobotsSignals | None = None
    home: FetchResult | None = None
    pages: list = field(default_factory=list)
    documents: list = field(default_factory=list)
    not_found: list = field(default_factory=list)
    looked: list = field(default_factory=list)
    broken: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    pending: list = field(default_factory=list)
    stopped: list = field(default_factory=list)
    js_unread: list = field(default_factory=list)
    tdmrep_code: int | None = None
    tdmrep_body: str | None = None
    llms_txt_code: int | None = None
    copyright_line: str | None = None
    incomplete: bool = False

    def home_signals(self) -> PageSignals | None:
        return self.pages[0].signals if self.pages else None

    def documents_block(self) -> list:
        return [d.block() for d in self.documents
                if d.unread_reason is not None
                or (d.fetch is not None and d.fetch.outcome in ("ok", "unread"))]

    def not_found_block(self) -> list:
        return [n.block() for n in self.not_found]

    def signals_block(self) -> dict:
        home = self.home_signals()
        return {
            "robots": self.robots.block() if self.robots is not None else None,
            "tdmrep": {"well_known": self.tdmrep_code,
                       "header": home.tdm_reservation if home else None,
                       "meta": home.meta_tdm_reservation if home else None},
            "x_robots_tag": home.x_robots_tag if home else None,
            "meta_robots": home.meta_robots if home else None,
        }


class SourceReader:
    def __init__(self, fetcher: Fetcher, checker: SecurityChecker | None = None,
                 page_renderer: "PageRenderer | None" = None):
        self.fetcher = fetcher
        self.checker = checker
        self.page_renderer = page_renderer
        self.today = fetcher.today
        self._cache: dict[str, FetchResult] = {}
        self._clearance: dict[str, tuple[str, str]] = {}

    def read(self, host: str) -> HostReading:
        host = host.lower()
        reading = HostReading(host=host, start_url=f"https://{host}/", read=self.today())
        if not self._cleared(host):
            reading.skipped = "security_not_cleared"
            return reading
        self.fetcher.read_robots(host)
        home = self._get(reading, reading.start_url)
        reading.home = home
        rob = self.fetcher.robots(host)
        reading.robots = robots_signals(rob) if rob is not None else None
        if home.outcome == "ok" and home.status == 200:
            self._read_site(reading, home)
        elif home.outcome in ("failed", "unread"):
            self._note_unsettled(reading, reading.start_url, "entry", home)
        reading.pending = [u for u in reading.pending if self._cache[u].outcome == "deferred"]
        reading.incomplete = reading.incomplete or bool(reading.pending)
        return reading

    def _cleared(self, host: str) -> bool:
        return host in self.fetcher.secure_hosts or host in self.fetcher.service_hosts

    def _host_clearance(self, host: str) -> tuple[str, str]:
        if self._cleared(host):
            return "ok", ""
        if host in self._clearance:
            return self._clearance[host]
        if self.checker is None:
            answer = (UNREAD_TOOL_REFUSED, "no security check is available for this host")
        else:
            result = self.checker.check(host)
            if result.readable and self._cleared(host):
                answer = ("ok", "")
            elif result.dns == "nxdomain":
                answer = (UNREAD_DNS, "nxdomain")
            else:
                why = result.failed or ", ".join(result.flags) or "not cleared"
                answer = (UNREAD_TOOL_REFUSED, f"security check: {why}")
        self._clearance[host] = answer
        return answer

    def _get(self, reading: HostReading, url: str) -> FetchResult:
        res = self._cache.get(url)
        if res is None:
            res = self.fetcher.get(url)
            if self.page_renderer is not None:
                res = self.page_renderer.consider(res)
            self._cache[url] = res
        if res.outcome == "deferred" and url not in reading.pending:
            reading.pending.append(url)
        return res

    def _note_unsettled(self, reading, url, place, res) -> None:
        if res.outcome == "failed":
            reading.failed.append({"url": url, "place": place, "detail": res.detail,
                                   "stopped_at": res.stopped_at})
            reading.incomplete = True
        elif res.outcome == "unread" and res.unread in STOP_UNREAD:
            reading.stopped.append({"url": url, "place": place, "unread": res.unread,
                                    "detail": res.detail})
            reading.incomplete = True
        elif res.outcome == "unread" and res.unread == UNREAD_JS_RENDERED:
            reading.js_unread.append({"url": url, "place": place, "detail": res.detail})
            reading.incomplete = True
        elif res.outcome == "deferred":
            reading.incomplete = True

    def _read_site(self, reading: HostReading, home: FetchResult) -> None:
        page = parse_page(home.final_url or reading.start_url, home)
        reading.pages.append(page)
        reading.copyright_line = page.copyright_line
        found = {"offsite": [], "hubs": [], "pages": [page]}
        self._links(reading, page, "footer", found)
        reading.looked.append("footer")
        self._take(reading, found, "footer")
        if self._missing(reading):
            reading.looked.append("menu")
            self._links(reading, page, "menu", found)
            self._take(reading, found, "menu")
        for stage in STAGES[2:]:
            if not self._missing(reading):
                break
            getattr(self, f"_stage_{stage}")(reading, found)
        missing_terms = not any(d.kind == "terms" for d in reading.documents)
        if missing_terms and reading.looked and not reading.incomplete:
            reading.not_found.append(NotFound("terms", list(reading.looked), self.today(),
                                              reading.copyright_line))
        self._optional(reading)

    def _missing(self, reading: HostReading) -> list:
        have = {d.kind for d in reading.documents}
        return [k for k in ESSENTIAL_KINDS if k not in have]

    def _links(self, reading, page: ParsedPage, region: str, found: dict) -> None:
        for link in page.links:
            if link.region != region:
                continue
            kind = classify_link(link.text)
            if kind is None:
                continue
            found.setdefault("cands", []).append((kind, link, page.url))

    def _take(self, reading, found: dict, place: str, cands: list | None = None) -> None:
        host = reading.host
        have = {d.kind for d in reading.documents}
        pool = cands if cands is not None else found.pop("cands", [])
        todo: list[Candidate] = []
        for kind, link, page_url in pool:
            target = host_of(link.url)
            if kind == "hub":
                if same_site(target, host):
                    found["hubs"].append(Candidate(kind, link.url, link.text, place, page_url))
                continue
            if not same_site(target, host):
                found["offsite"].append(Candidate(kind, link.url, link.text, "operator_domain", page_url))
                continue
            if kind in have or any(c.url == link.url for c in todo) \
                    or any(d.url == link.url for d in reading.documents):
                continue
            todo.append(Candidate(kind, link.url, link.text, place, page_url))
        self._read_candidates(reading, found, todo)

    def _read_candidates(self, reading, found: dict, todo: list) -> None:
        for cand in todo:
            if len(reading.documents) >= MAX_DOCUMENTS:
                return
            doc = self._document(reading, cand)
            if doc is None:
                continue
            reading.documents.append(doc)
            if doc.parsed is not None:
                found["pages"].append(doc.parsed)
            if doc.fetch is not None:
                self._note_unsettled(reading, doc.url, doc.place, doc.fetch)

    def _document(self, reading: HostReading, cand: Candidate) -> DocumentFind | None:
        doc = DocumentFind(kind=cand.kind, url=cand.url, page=cand.page, place=cand.place,
                           link_text=cand.text, read=self.today())
        status, note = self._host_clearance(host_of(cand.url) or "")
        if status != "ok":
            doc.unread_reason, doc.note = status, note
            return doc
        res = self._get(reading, cand.url)
        doc.fetch = res
        if res.outcome == "ok":
            if res.status != 200:
                reading.broken.append({"url": cand.url, "status": res.status, "place": cand.place,
                                       "page": cand.page})
                return None
            doc.parsed = parse_page(res.final_url or cand.url, res)
        return doc

    def _stage_sitemap(self, reading: HostReading, found: dict) -> None:
        urls = [u for u in (reading.robots.sitemaps if reading.robots else [])
                if same_site(host_of(u), reading.host)]
        urls += [f"https://{reading.host}{p}" for p in SITEMAP_PATHS]
        seen, reads = set(), []
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            matches = self._sitemap_matches(reading, url, reads)
            cands, kinds = [], set()
            for kind, loc in matches:
                if kind in self._missing(reading) and kind not in kinds:
                    kinds.add(kind)
                    cands.append(Candidate(kind, loc, None, "sitemap", url))
            if cands:
                self._read_candidates(reading, found, cands)
                break
        if self._searched(reads):
            reading.looked.append("sitemap")

    @staticmethod
    def _searched(reads: list) -> bool:
        return any(r.outcome == "ok" for r in reads) and all(
            r.outcome == "ok" or (r.outcome == "unread" and r.unread == UNREAD_ROBOTS_BLOCKS_AGENT)
            for r in reads)

    def _sitemap_matches(self, reading, url: str, reads: list) -> list:
        res = self._get(reading, url)
        reads.append(res)
        self._note_unsettled(reading, url, "sitemap", res)
        if res.outcome != "ok" or res.status != 200 or url.endswith(".gz"):
            return []
        text = res.body.decode("utf-8", errors="replace")
        locs = [u.strip() for u in re.findall(r"<loc>\s*(.*?)\s*</loc>", text, re.DOTALL)]
        if "<sitemapindex" in text.lower():
            children = [u for u in locs if "page" in u.lower() and not u.endswith(".gz")
                        and same_site(host_of(u), reading.host)][:MAX_CHILD_SITEMAPS]
            locs = []
            for child in children:
                child_res = self._get(reading, child)
                reads.append(child_res)
                self._note_unsettled(reading, child, "sitemap", child_res)
                if child_res.outcome == "ok" and child_res.status == 200:
                    locs += [u.strip() for u in re.findall(
                        r"<loc>\s*(.*?)\s*</loc>", child_res.body.decode("utf-8", errors="replace"),
                        re.DOTALL)]
        matches = []
        for loc in locs:
            kind = classify_path(loc)
            if kind and kind != "hub" and same_site(host_of(loc), reading.host):
                matches.append((kind, loc))
        return matches

    def _stage_legal_hub(self, reading: HostReading, found: dict) -> None:
        hubs, found["hubs"] = found["hubs"][:MAX_HUBS], []
        read_any = False
        for hub in hubs:
            status, _ = self._host_clearance(host_of(hub.url) or "")
            if status != "ok":
                continue
            res = self._get(reading, hub.url)
            self._note_unsettled(reading, hub.url, "legal_hub", res)
            if res.outcome != "ok" or res.status != 200:
                continue
            read_any = True
            page = parse_page(res.final_url or hub.url, res)
            found["pages"].append(page)
            cands = [(classify_link(link.text), link, page.url) for link in page.links]
            self._take(reading, found, "legal_hub", [c for c in cands if c[0] is not None])
        if read_any:
            reading.looked.append("legal_hub")

    def _stage_linked_from_doc(self, reading: HostReading, found: dict) -> None:
        pages = [d.parsed for d in reading.documents if d.parsed is not None]
        if not pages:
            return
        cands = []
        for page in pages:
            cands += [(classify_link(link.text), link, page.url) for link in page.links]
        self._take(reading, found, "linked_from_doc", [c for c in cands if c[0] is not None])
        reading.looked.append("linked_from_doc")

    def _stage_operator_domain(self, reading: HostReading, found: dict) -> None:
        offsite, seen = [], set()
        for cand in found["offsite"]:
            if cand.kind in self._missing(reading) and cand.url not in seen:
                seen.add(cand.url)
                offsite.append(cand)
        if not offsite:
            return
        self._read_candidates(reading, found, offsite[:MAX_OPERATOR_LINKS])
        reading.looked.append("operator_domain")

    def _optional(self, reading: HostReading) -> None:
        if reading.stopped:
            return
        res = self._get(reading, f"https://{reading.host}{TDMREP_PATH}")
        self._note_unsettled(reading, res.url, "tdmrep", res)
        if res.outcome == "ok":
            reading.tdmrep_code = res.status
            if res.status == 200:
                reading.tdmrep_body = res.body.decode("utf-8", errors="replace")[:TDMREP_MAX_CHARS]
        res = self._get(reading, f"https://{reading.host}{LLMS_PATH}")
        self._note_unsettled(reading, res.url, "llms_txt", res)
        if res.outcome == "ok":
            reading.llms_txt_code = res.status


RENDER_MIN_CHARS = 500
RENDER_TIMEOUT_MS = 30000
RENDER_IDLE_MS = 10000
METHOD_RENDER = "browser_render"
RENDER_SKIP_TAGS = ["script", "style", "noscript", "template", "head"]
RENDER_BLOCKED_TYPES = frozenset({"image", "media", "font", "stylesheet"})
RENDER_NO_REQUEST_SCHEMES = frozenset({"data", "blob"})
RENDER_SAME_HOST_CAP = 50


class RenderError(Exception):
    pass


@dataclass
class RenderRequest:
    url: str
    user_agent: str
    allow: Callable[..., bool]
    storage_state: None = None


@dataclass
class RenderedPage:
    html: str
    status: int | None = None
    final_url: str | None = None


def visible_text(html: bytes | str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(RENDER_SKIP_TAGS):
        tag.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())


class RenderGuard:
    def __init__(self, fetcher: Fetcher, page_host: str | None = None,
                 same_host_cap: int = RENDER_SAME_HOST_CAP):
        self.fetcher = fetcher
        self.page_host = page_host
        self.same_host_cap = same_host_cap
        self.same_host_count = 0
        self.allowed: list = []
        self.aborted: list = []

    def decide(self, url: str, resource_type: str | None = None) -> str | None:
        parts = urlsplit(url)
        if parts.scheme in RENDER_NO_REQUEST_SCHEMES:
            return None
        host = parts.hostname
        if parts.scheme != "https" or not host:
            return "not_https"
        if resource_type in RENDER_BLOCKED_TYPES:
            return "resource_type"
        fetcher = self.fetcher
        if host not in fetcher.secure_hosts and host not in fetcher.service_hosts:
            return "host_not_checked"
        state = fetcher.hosts.get(host)
        if state is not None and (state.refused or state.rate_limited or state.robots_deferred):
            return "host_stopped"
        if not fetcher.gate.fresh(host):
            return "robots_not_read"
        decision = fetcher.gate.decide(url)
        if not decision.allowed:
            return decision.reason or UNREAD_ROBOTS_BLOCKS_AGENT
        if host == self.page_host and self.same_host_count >= self.same_host_cap:
            return "request_cap"
        return None

    def __call__(self, url: str, resource_type: str | None = None) -> bool:
        why = self.decide(url, resource_type)
        if why is None:
            if urlsplit(url).scheme in RENDER_NO_REQUEST_SCHEMES:
                return True
            if urlsplit(url).hostname == self.page_host:
                self.same_host_count += 1
            self.allowed.append(url)
            return True
        self.aborted.append((url, why))
        return False


class PlaywrightRenderer:
    """The real renderer. Never started by a test or by an agent."""

    def __init__(self, timeout_ms: int = RENDER_TIMEOUT_MS, idle_ms: int = RENDER_IDLE_MS):
        self.timeout_ms = timeout_ms
        self.idle_ms = idle_ms
        self._playwright = None
        self._browser = None

    def __enter__(self) -> "PlaywrightRenderer":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def _start(self):
        if self._browser is None:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
        return self._browser

    def __call__(self, request: RenderRequest) -> RenderedPage:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        try:
            context = self._start().new_context(
                user_agent=request.user_agent, storage_state=request.storage_state,
                accept_downloads=False, service_workers="block")
            try:
                context.route("**/*", lambda route: route.continue_()
                              if request.allow(route.request.url, route.request.resource_type)
                              else route.abort())
                if hasattr(context, "route_web_socket"):
                    context.route_web_socket("**/*", lambda socket_route: socket_route.close())
                page = context.new_page()
                response = page.goto(request.url, wait_until="load", timeout=self.timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=self.idle_ms)
                except PlaywrightTimeout:
                    pass
                return RenderedPage(page.content(), response.status if response else None, page.url)
            finally:
                context.close()
        except PlaywrightError as exc:
            raise RenderError(f"{type(exc).__name__}: {exc}") from exc


class PageRenderer:
    def __init__(self, fetcher: Fetcher, renderer: Callable[[RenderRequest], RenderedPage]):
        self.fetcher = fetcher
        self.renderer = renderer
        self.skipped: dict[str, str] = {}
        self._locks: dict[str, threading.Lock] = {}

    def skip_reason(self, res: FetchResult) -> str | None:
        if res.outcome != "ok":
            return "not_read"
        if res.status != 200:
            return "not_200"
        if not is_html_response(res):
            return "not_html"
        url = res.final_url or res.url
        host = host_of(url)
        fetcher = self.fetcher
        state = fetcher.hosts.get(host)
        if state is not None and (state.saw_429 or state.rate_limited):
            return "rate_limited"
        if state is not None and state.refused:
            return "refused_status"
        if host not in fetcher.secure_hosts and host not in fetcher.service_hosts:
            return "host_not_cleared"
        if not fetcher.gate.fresh(host):
            return "robots_not_read"
        if not fetcher.gate.decide(url).allowed:
            return UNREAD_ROBOTS_BLOCKS_AGENT
        if len(visible_text(res.body)) >= RENDER_MIN_CHARS:
            return "has_text"
        return None

    def consider(self, res: FetchResult) -> FetchResult:
        why = self.skip_reason(res)
        if why is not None:
            self.skipped[res.url] = why
            return res
        return self._render(res)

    def _render(self, res: FetchResult) -> FetchResult:
        host = host_of(res.final_url or res.url)
        with self._locks.setdefault(host, threading.Lock()):
            try:
                return self._run_render(res, host)
            finally:
                self.fetcher._host(host).last_request = self.fetcher.clock()

    def _run_render(self, res: FetchResult, host: str) -> FetchResult:
        url = res.final_url or res.url
        guard = RenderGuard(self.fetcher, host)
        self.fetcher._pace(host)
        try:
            page = self.renderer(RenderRequest(url=url, user_agent=USER_AGENT, allow=guard))
        except RenderError as exc:
            return replace(res, outcome="failed", method=METHOD_RENDER, detail=f"render failed: {exc}",
                           render_allowed=list(guard.allowed), render_aborted=list(guard.aborted))
        out = replace(res, method=METHOD_RENDER, render_allowed=list(guard.allowed),
                      render_aborted=list(guard.aborted))
        if page.status in (401, 403):
            out.outcome, out.unread, out.status = "unread", UNREAD_REFUSED_STATUS, page.status
            out.detail = f"the render answered {page.status}"
            self.fetcher._host(host).refused = _Stop(
                UNREAD_REFUSED_STATUS, page.status, self.fetcher.today(),
                f"a render of {host} answered {page.status}")
        elif page.status == 429:
            out.outcome, out.unread, out.status = "unread", UNREAD_RATE_LIMITED, 429
            out.detail = "the render answered 429"
            self.fetcher._rate_limit(host, out.detail)
        elif page.status != 200:
            out.outcome, out.status = "failed", page.status
            out.detail = f"the render answered {page.status}"
        else:
            out.body = page.html.encode("utf-8")
            out.final_url = page.final_url or url
            chars = len(visible_text(page.html))
            if chars < RENDER_MIN_CHARS:
                out.outcome, out.unread = "unread", UNREAD_JS_RENDERED
                out.detail = f"the page drew {chars} characters after the render"
            else:
                out.outcome, out.unread, out.detail = "ok", None, ""
        return out
