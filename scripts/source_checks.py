"""Source checks, fetch layer (#454 Brief B1): the only network path in the
script, and the RobotsGate every request must pass. GET only, one product
token on every request, no cookies, no auth. Later briefs add the security
check, signals, discovery, render and evidence on top of this layer.

Never run live by an agent; tests inject the transport, clock and sleep.
"""
from __future__ import annotations

import hashlib
import json
import re
import socket
import ssl
import sys
import time
from dataclasses import dataclass, field, fields
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
