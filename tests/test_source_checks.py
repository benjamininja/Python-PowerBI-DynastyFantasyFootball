import hashlib
import json
import socket
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote, urlsplit

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import source_checks as sc

TODAY = date(2026, 11, 8)
UA = sc.USER_AGENT
A_ROBOTS = "https://a.example/robots.txt"
A_TERMS = "https://a.example/terms"
B_ROBOTS = "https://b.example/robots.txt"
B_TERMS = "https://b.example/terms"
ALLOW_ALL = "User-agent: *\nAllow: /\n"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a test made a real network call")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)


class Clock:
    def __init__(self):
        self.t = 1000.0
        self.sleeps = []

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += seconds

    def long_waits(self):
        return [s for s in self.sleeps if s > sc.MIN_DELAY]


class FakeTransport:
    def __init__(self, routes, clock):
        self.routes = {u: (list(v) if isinstance(v, list) else [v]) for u, v in routes.items()}
        self.clock = clock
        self.calls = []

    def __call__(self, request):
        self.calls.append((request.url, dict(request.headers), self.clock()))
        queue = self.routes.get(request.url)
        assert queue is not None, f"unexpected request to {request.url}"
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item

    def urls(self):
        return [c[0] for c in self.calls]

    def times(self, url):
        return [c[2] for c in self.calls if c[0] == url]

    def count(self, url):
        return len(self.times(url))


def resp(status=200, body="", **headers):
    return sc.Response(status, {k.replace("_", "-"): v for k, v in headers.items()},
                       body.encode())


def build(routes, secure=("a.example",)):
    clock = Clock()
    transport = FakeTransport(routes, clock)
    fetcher = sc.Fetcher(transport, clock=clock, sleep=clock.sleep, today=lambda: TODAY)
    for host in secure:
        fetcher.mark_secure(host)
    return fetcher, transport, clock


def test_fixture_blocks_real_connections():
    with pytest.raises(AssertionError):
        socket.socket().connect(("127.0.0.1", 9))


def test_user_agent_is_the_shared_constant():
    assert UA == sc.etl_helpers.ETL_USER_AGENT
    assert sc.PRODUCT_TOKEN == "MouseratDynastyETL"


def test_longest_match_allow_beats_disallow_all():
    f, t, _ = build({A_ROBOTS: resp(200, "User-agent: *\nDisallow: /\nAllow: /public/\n"),
                     "https://a.example/public/x": resp(200, "x")})
    assert f.get("https://a.example/public/x").outcome == "ok"
    assert f.get("https://a.example/private").unread == sc.UNREAD_ROBOTS_BLOCKS_AGENT


def test_end_anchored_wildcard_disallows_pdf():
    f, t, _ = build({A_ROBOTS: resp(200, "User-agent: *\nDisallow: /*.pdf$\n")})
    res = f.get("https://a.example/a.pdf")
    assert res.outcome == "unread"
    assert res.unread == sc.UNREAD_ROBOTS_BLOCKS_AGENT
    assert "*" in f.gate.decide("https://a.example/a.pdf").blocked_by
    assert t.urls() == [A_ROBOTS]


@pytest.mark.parametrize("code", [400, 404, 410, 418])
def test_status_that_means_no_rules_allows(code):
    f, t, _ = build({A_ROBOTS: resp(code), A_TERMS: resp(200, "terms")})
    assert f.get(A_TERMS).outcome == "ok"
    assert f.robots("a.example").outcome == "no_rules"
    assert f.robots("a.example").code == code


@pytest.mark.parametrize("answer", [resp(500), resp(502), resp(503), sc.TransportTimeout("slow"),
                                    sc.TransportError("reset")])
def test_server_error_or_timeout_is_a_complete_disallow(answer):
    f, t, _ = build({A_ROBOTS: answer, A_TERMS: resp(200, "terms")})
    res = f.get(A_TERMS)
    assert res.outcome == "unread"
    assert res.unread == sc.UNREAD_REFUSED_STATUS
    assert f.robots("a.example").outcome == "disallow_all"
    assert t.urls() == [A_ROBOTS]


@pytest.mark.parametrize("code", [401, 403])
def test_401_and_403_stop_after_one_request(code):
    f, t, clock = build({A_ROBOTS: resp(code), A_TERMS: resp(200, "terms")})
    first = f.get(A_TERMS)
    second = f.get("https://a.example/privacy")
    assert first.unread == second.unread == sc.UNREAD_REFUSED_STATUS
    assert t.urls() == [A_ROBOTS]
    robots = f.robots("a.example")
    assert (robots.outcome, robots.code, robots.read) == ("stop", code, TODAY)
    assert clock.sleeps == []


def test_a_403_host_does_not_change_the_user_agent_for_other_hosts():
    f, t, _ = build({A_ROBOTS: resp(403), B_ROBOTS: resp(404), B_TERMS: resp(200, "t")},
                    secure=("a.example", "b.example"))
    f.get(A_TERMS)
    f.get(B_TERMS)
    assert len(t.calls) == 3
    for _, headers, _ in t.calls:
        assert headers == {"User-Agent": UA}
        assert "cookie" not in {k.lower() for k in headers}


def test_request_before_robots_raises():
    gate = sc.RobotsGate()
    with pytest.raises(sc.RobotsNotRead):
        gate.allowed(A_TERMS)
    with pytest.raises(sc.RobotsNotRead):
        gate.decide(A_TERMS)


def test_robots_cache_lasts_under_24_hours():
    f, t, clock = build({A_ROBOTS: resp(200, ALLOW_ALL), A_TERMS: resp(200, "t")})
    f.get(A_TERMS)
    clock.t += sc.ROBOTS_MAX_AGE - 10
    f.get(A_TERMS)
    assert t.count(A_ROBOTS) == 1
    clock.t += 20
    f.get(A_TERMS)
    assert t.count(A_ROBOTS) == 2


def test_transport_has_no_cookies_and_no_env_auth():
    transport = sc.RequestsTransport()
    assert transport.session.trust_env is False
    policy = transport.session.cookies._policy
    assert policy.set_ok(None, None) is False
    assert policy.return_ok(None, None) is False


def chain(hops):
    routes = {A_ROBOTS: resp(404)}
    for i in range(hops):
        routes[f"https://a.example/p{i}"] = resp(302, location=f"/p{i + 1}")
    routes[f"https://a.example/p{hops}"] = resp(200, "done")
    return routes


def test_five_redirect_hops_are_followed():
    f, t, _ = build(chain(5))
    res = f.get("https://a.example/p0")
    assert res.outcome == "ok"
    assert res.final_url == "https://a.example/p5"
    assert len(res.hops) == 6


def test_a_sixth_redirect_hop_is_refused():
    f, t, _ = build(chain(6))
    res = f.get("https://a.example/p0")
    assert res.outcome == "failed"
    assert "5 redirects" in res.detail
    assert "https://a.example/p6" not in t.urls()


def test_each_redirect_hop_passes_the_gate():
    routes = chain(5)
    routes[A_ROBOTS] = resp(200, "User-agent: *\nDisallow: /p3\n")
    f, t, _ = build(routes)
    res = f.get("https://a.example/p0")
    assert res.outcome == "unread"
    assert res.unread == sc.UNREAD_ROBOTS_BLOCKS_AGENT
    assert res.stopped_at == "https://a.example/p3"
    assert "https://a.example/p3" not in t.urls()


def test_redirect_to_another_host_reads_that_hosts_robots_first():
    routes = {A_ROBOTS: resp(404), "https://a.example/go": resp(302, location="https://b.example/terms"),
              B_ROBOTS: resp(404), B_TERMS: resp(200, "t")}
    f, t, _ = build(routes, secure=("a.example", "b.example"))
    assert f.get("https://a.example/go").outcome == "ok"
    assert t.urls() == [A_ROBOTS, "https://a.example/go", B_ROBOTS, B_TERMS]


def test_redirect_to_a_host_without_a_security_check_is_stopped_and_recorded():
    routes = {A_ROBOTS: resp(404), "https://a.example/go": resp(302, location="https://b.example/terms")}
    f, t, _ = build(routes)
    res = f.get("https://a.example/go")
    assert res.outcome == "failed"
    assert res.stopped_at == B_TERMS
    assert "security check not passed for b.example" in res.detail
    assert all("b.example" not in u for u in t.urls())


def test_redirect_to_a_host_whose_robots_disallow_is_unread():
    routes = {A_ROBOTS: resp(404), "https://a.example/go": resp(302, location="https://b.example/terms"),
              B_ROBOTS: resp(200, "User-agent: *\nDisallow: /terms\n")}
    f, t, _ = build(routes, secure=("a.example", "b.example"))
    res = f.get("https://a.example/go")
    assert (res.outcome, res.unread, res.stopped_at) == ("unread", sc.UNREAD_ROBOTS_BLOCKS_AGENT, B_TERMS)


def test_plain_http_is_never_fetched():
    routes = {A_ROBOTS: resp(404), "https://a.example/go": resp(302, location="http://a.example/terms")}
    f, t, _ = build(routes)
    assert f.get("http://a.example/terms").outcome == "failed"
    res = f.get("https://a.example/go")
    assert res.outcome == "failed"
    assert res.stopped_at == "http://a.example/terms"


def test_a_host_without_a_security_check_gets_no_request():
    f, t, _ = build({}, secure=())
    res = f.get(A_TERMS)
    assert res.outcome == "failed"
    assert t.calls == []


def test_apex_and_www_are_checked_on_their_own():
    routes = {"https://example.com/robots.txt": resp(404),
              "https://example.com/terms": resp(200, "t")}
    f, t, _ = build(routes, secure=("www.example.com",))
    assert f.get("https://example.com/terms").outcome == "failed"
    assert t.calls == []
    f.mark_secure("example.com")
    assert f.get("https://example.com/terms").outcome == "ok"


def test_service_hosts_need_no_security_check_but_pass_robots():
    routes = {"https://transparencyreport.google.com/robots.txt": resp(200, "User-agent: *\nDisallow:\n"),
              "https://transparencyreport.google.com/status": resp(200, "x"),
              "https://data.iana.org/robots.txt": resp(200, "User-agent: *\nDisallow: /rdap/\n")}
    f, t, _ = build(routes, secure=())
    assert f.get("https://transparencyreport.google.com/status").outcome == "ok"
    res = f.get("https://data.iana.org/rdap/dns.json")
    assert (res.outcome, res.unread) == ("unread", sc.UNREAD_ROBOTS_BLOCKS_AGENT)


def test_a_host_off_the_service_list_is_not_a_service_host():
    f, t, _ = build({}, secure=())
    assert f.get("https://rdap.verisign.com/com/v1/domain/example.com").outcome == "failed"
    with pytest.raises(ValueError):
        f.register_rdap_host("http://rdap.verisign.com/com/v1/")
    f.register_rdap_host("https://rdap.verisign.com/com/v1/")
    assert "rdap.verisign.com" in f.service_hosts


@pytest.mark.parametrize("robots, blocked", [
    ("User-agent: ClaudeBot\nDisallow: /\n", ["ClaudeBot"]),
    ("User-agent: Claude-User\nDisallow: /terms\n", ["Claude-User"]),
    ("User-agent: Claude-SearchBot\nDisallow: /\n", ["Claude-SearchBot"]),
    ("User-agent: anthropic-ai\nDisallow: /\n", ["anthropic-ai"]),
    ("User-agent: Claude-Web\nDisallow: /\n", ["Claude-Web"]),
    ("User-agent: MouseratDynastyETL\nDisallow: /terms\n", ["MouseratDynastyETL"]),
    ("User-agent: *\nDisallow: /terms\n", ["MouseratDynastyETL", "*"]),
    ("User-agent: MouseratDynastyETL\nAllow: /\n\nUser-agent: *\nDisallow: /\n", ["*"]),
])
def test_gate_stops_on_our_token_the_star_group_or_a_claude_token(robots, blocked):
    f, t, _ = build({A_ROBOTS: resp(200, robots), A_TERMS: resp(200, "t")})
    res = f.get(A_TERMS)
    assert (res.outcome, res.unread) == ("unread", sc.UNREAD_ROBOTS_BLOCKS_AGENT)
    for token in blocked:
        assert token in f.gate.decide(A_TERMS).blocked_by
    assert t.urls() == [A_ROBOTS]


def test_other_agents_rules_do_not_stop_us():
    robots = "User-agent: Googlebot\nDisallow: /\n\nUser-agent: GPTBot\nDisallow: /\n"
    f, t, _ = build({A_ROBOTS: resp(200, robots), A_TERMS: resp(200, "t")})
    assert f.get(A_TERMS).outcome == "ok"
    assert f.robots("a.example").claude_groups == []
    assert f.robots("a.example").blocks_agent is False


def test_robots_record_holds_groups_hash_delay_and_hsts():
    body = "User-agent: ClaudeBot\nDisallow: /private\n\nUser-agent: *\nCrawl-delay: 7\n"
    f, t, _ = build({A_ROBOTS: resp(200, body, strict_transport_security="max-age=86400"),
                     A_TERMS: resp(200, "t")})
    f.get(A_TERMS)
    robots = f.robots("a.example")
    assert robots.claude_groups == ["ClaudeBot"]
    assert robots.blocks_agent is False
    assert robots.crawl_delay == 7.0
    assert robots.sha256 == sc.hashlib.sha256(body.encode()).hexdigest()
    assert robots.strict_transport_security == "max-age=86400"
    assert robots.code == 200 and robots.read == TODAY


def test_a_claude_group_that_blocks_the_root_sets_blocks_agent():
    f, t, _ = build({A_ROBOTS: resp(200, "User-agent: ClaudeBot\nDisallow: /\n")})
    assert f.get(A_TERMS).unread == sc.UNREAD_ROBOTS_BLOCKS_AGENT
    assert f.robots("a.example").blocks_agent is True


def test_only_the_first_500_kib_of_robots_is_parsed():
    body = "User-agent: *\nAllow: /\n" + "#" * (600 * 1024) + "\nDisallow: /late\n"
    f, t, _ = build({A_ROBOTS: resp(200, body), "https://a.example/late": resp(200, "x")})
    assert f.get("https://a.example/late").outcome == "ok"


def test_default_pacing_is_five_seconds_per_host():
    f, t, _ = build({A_ROBOTS: resp(200, ALLOW_ALL), A_TERMS: resp(200, "t"),
                     "https://a.example/privacy": resp(200, "p")})
    f.get(A_TERMS)
    f.get("https://a.example/privacy")
    times = [c[2] for c in t.calls]
    assert [b - a for a, b in zip(times, times[1:])] == [5.0, 5.0]


@pytest.mark.parametrize("delay", [1, 12])
def test_crawl_delay_is_honoured(delay):
    f, t, _ = build({A_ROBOTS: resp(200, f"User-agent: *\nCrawl-delay: {delay}\n"),
                     A_TERMS: resp(200, "t"), "https://a.example/privacy": resp(200, "p")})
    f.get(A_TERMS)
    f.get("https://a.example/privacy")
    times = [c[2] for c in t.calls]
    assert [b - a for a, b in zip(times, times[1:])] == [float(delay), float(delay)]


def test_429_on_robots_three_tries_then_deferred_try_after_other_hosts_then_stop():
    f, t, clock = build({A_ROBOTS: resp(429), B_ROBOTS: resp(404), B_TERMS: resp(200, "t")},
                        secure=("a.example", "b.example"))
    held = f.get(A_TERMS)
    assert held.outcome == "deferred"
    assert t.urls() == [A_ROBOTS] * 3
    assert clock.long_waits() == [60.0, 300.0]
    assert f.get(B_TERMS).outcome == "ok"
    f.run_deferred()
    assert t.urls() == [A_ROBOTS] * 3 + [B_ROBOTS, B_TERMS, A_ROBOTS]
    robots = f.robots("a.example")
    assert (robots.outcome, robots.reason, robots.code) == ("stop", sc.UNREAD_RATE_LIMITED, 429)
    assert (held.outcome, held.unread) == ("unread", sc.UNREAD_RATE_LIMITED)


def test_429_wait_uses_retry_after_when_given():
    f, t, clock = build({A_ROBOTS: [resp(429, retry_after="10"), resp(429, retry_after="20"),
                                    resp(200, ALLOW_ALL)],
                         A_TERMS: resp(200, "t")})
    assert f.get(A_TERMS).outcome == "ok"
    assert clock.sleeps[:2] == [10.0, 20.0]


def test_robots_429_that_clears_segments_the_hosts_later_reads():
    f, t, _ = build({A_ROBOTS: [resp(429), resp(200, ALLOW_ALL)], A_TERMS: resp(200, "t"),
                     "https://a.example/privacy": resp(200, "p")})
    f.get(A_TERMS)
    f.get("https://a.example/privacy")
    page_times = t.times(A_TERMS) + t.times("https://a.example/privacy")
    assert page_times[1] - page_times[0] >= sc.SEGMENT_DELAY
    assert page_times[0] - t.times(A_ROBOTS)[-1] >= sc.SEGMENT_DELAY


def test_robots_deferred_try_that_succeeds_releases_the_held_reads():
    f, t, _ = build({A_ROBOTS: [resp(429)] * 3 + [resp(200, ALLOW_ALL)], A_TERMS: resp(200, "t")})
    held = f.get(A_TERMS)
    assert held.outcome == "deferred"
    f.run_deferred()
    assert (held.outcome, held.status, held.body) == ("ok", 200, b"t")


def test_retry_after_over_600_on_robots_is_a_stop_at_once():
    f, t, clock = build({A_ROBOTS: resp(429, retry_after="601"), A_TERMS: resp(200, "t")})
    res = f.get(A_TERMS)
    assert (res.outcome, res.unread) == ("unread", sc.UNREAD_RATE_LIMITED)
    assert t.urls() == [A_ROBOTS]
    assert f.robots("a.example").outcome == "stop"
    f.run_deferred()
    assert t.urls() == [A_ROBOTS]
    assert clock.long_waits() == []


def test_retry_after_of_600_is_still_waited():
    f, t, clock = build({A_ROBOTS: [resp(429, retry_after="600"), resp(200, ALLOW_ALL)],
                         A_TERMS: resp(200, "t")})
    assert f.get(A_TERMS).outcome == "ok"
    assert clock.sleeps[:1] == [600.0]


def test_429_on_a_later_read_three_tries_deferred_try_then_rate_limited_for_the_host():
    f, t, clock = build({A_ROBOTS: resp(404), A_TERMS: resp(429),
                         "https://a.example/privacy": resp(200, "p")})
    held = f.get(A_TERMS)
    assert held.outcome == "deferred"
    assert t.count(A_TERMS) == 3
    assert clock.long_waits() == [60.0, 300.0]
    f.run_deferred()
    assert t.count(A_TERMS) == 4
    assert (held.outcome, held.unread) == ("unread", sc.UNREAD_RATE_LIMITED)
    calls = len(t.calls)
    later = f.get("https://a.example/privacy")
    assert (later.outcome, later.unread) == ("unread", sc.UNREAD_RATE_LIMITED)
    assert len(t.calls) == calls


def test_deferred_try_that_succeeds_fills_the_read():
    f, t, _ = build({A_ROBOTS: resp(404), A_TERMS: [resp(429)] * 3 + [resp(200, "t")]})
    held = f.get(A_TERMS)
    f.run_deferred()
    assert (held.outcome, held.status, held.body) == ("ok", 200, b"t")


def test_retry_after_over_600_on_a_later_read_marks_the_host_at_once():
    f, t, clock = build({A_ROBOTS: resp(404), A_TERMS: resp(429, retry_after="601"),
                         "https://a.example/privacy": resp(200, "p")})
    res = f.get(A_TERMS)
    assert (res.outcome, res.unread) == ("unread", sc.UNREAD_RATE_LIMITED)
    assert t.count(A_TERMS) == 1
    assert f.get("https://a.example/privacy").unread == sc.UNREAD_RATE_LIMITED
    f.run_deferred()
    assert t.urls() == [A_ROBOTS, A_TERMS]
    assert clock.long_waits() == []


def test_dtc_case_robots_403_is_one_request_and_a_recorded_stop():
    f, t, _ = build({"https://dtc.example/robots.txt": resp(403, "You do not have permission")},
                    secure=("dtc.example",))
    for path in ("/", "/privacy-policy/", "/terms"):
        res = f.get("https://dtc.example" + path)
        assert (res.outcome, res.unread) == ("unread", sc.UNREAD_REFUSED_STATUS)
    assert t.urls() == ["https://dtc.example/robots.txt"]
    robots = f.robots("dtc.example")
    assert (robots.outcome, robots.code, robots.read) == ("stop", 403, TODAY)


@pytest.mark.parametrize("code", [401, 403])
def test_a_401_or_403_on_a_later_read_stops_the_host(code):
    f, t, clock = build({A_ROBOTS: resp(404), A_TERMS: resp(code),
                         "https://a.example/privacy": resp(200, "p")})
    first = f.get(A_TERMS)
    assert (first.outcome, first.unread, first.status) == ("unread", sc.UNREAD_REFUSED_STATUS, code)
    calls = len(t.calls)
    for path in ("/privacy", "/terms", "/sitemap.xml"):
        later = f.get("https://a.example" + path)
        assert (later.outcome, later.unread) == ("unread", sc.UNREAD_REFUSED_STATUS)
        assert str(code) in later.detail
    assert len(t.calls) == calls
    assert t.count(A_TERMS) == 1
    f.run_deferred()
    assert len(t.calls) == calls
    assert clock.long_waits() == []


def test_a_later_read_stop_on_one_host_leaves_other_hosts_readable():
    f, t, _ = build({A_ROBOTS: resp(404), A_TERMS: resp(403), B_ROBOTS: resp(404),
                     B_TERMS: resp(200, "t")}, secure=("a.example", "b.example"))
    f.get(A_TERMS)
    assert f.get(B_TERMS).outcome == "ok"


def test_crawl_delay_over_600_stops_the_host_with_no_further_request():
    f, t, clock = build({A_ROBOTS: resp(200, "User-agent: *\nCrawl-delay: 601\n"),
                         A_TERMS: resp(200, "t")})
    res = f.get(A_TERMS)
    assert (res.outcome, res.unread) == ("unread", sc.UNREAD_RATE_LIMITED)
    assert "Crawl-delay" in res.detail
    assert f.get("https://a.example/privacy").unread == sc.UNREAD_RATE_LIMITED
    assert t.urls() == [A_ROBOTS]
    assert f.robots("a.example").crawl_delay == 601.0
    assert clock.sleeps == []


def test_crawl_delay_of_600_is_honoured_as_written():
    f, t, _ = build({A_ROBOTS: resp(200, "User-agent: *\nCrawl-delay: 600\n"),
                     A_TERMS: resp(200, "t"), "https://a.example/privacy": resp(200, "p")})
    assert f.get(A_TERMS).outcome == "ok"
    assert f.get("https://a.example/privacy").outcome == "ok"
    times = [c[2] for c in t.calls]
    assert [b - a for a, b in zip(times, times[1:])] == [600.0, 600.0]


def test_retry_after_parses_seconds_and_dates():
    assert sc.retry_after_seconds({"retry-after": "120"}) == 120.0
    assert sc.retry_after_seconds({}) is None
    assert sc.retry_after_seconds({"retry-after": "soon"}) is None
    assert sc.retry_after_seconds({"retry-after": "Wed, 21 Oct 2015 07:28:00 GMT"}) == 0.0


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "source_checks"
SERVICES = ("transparencyreport.google.com", "data.iana.org", "rdap.verisign.com", "hstspreload.org")
RDAP_BASE = "https://rdap.verisign.com/com/v1/domain/"
OLD = (TODAY - date(1999, 7, 9)).days
MALWARE = sc.SB_CONTROLS["malware"]


def fx(name):
    return (FIXTURES / name).read_bytes()


def raw(body, status=200, **headers):
    return sc.Response(status, {k.replace("_", "-"): v for k, v in headers.items()}, body)


def controls_bodies():
    return {sc.SB_CONTROLS["malware"]: fx("sb_control_malware.txt"),
            sc.SB_CONTROLS["phishing"]: fx("sb_control_phishing.txt"),
            sc.SB_CONTROLS["unwanted"]: fx("sb_control_unwanted.txt")}


def rdap_body(days_ago, today=TODAY):
    registered = (today - timedelta(days=days_ago)).isoformat()
    return fx("rdap_domain.json").replace(b"__REGISTERED__", registered.encode())


class Dns:
    def __init__(self, missing=(), code=socket.EAI_NONAME):
        self.missing = set(missing)
        self.code = code
        self.calls = []

    def __call__(self, host, port):
        self.calls.append(host)
        if host in self.missing:
            raise socket.gaierror(self.code, "resolver error")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", port))]


class Tls:
    def __init__(self, today=TODAY, **override):
        self.calls = []
        self.answer = {"ok": True, "issuer": "Amazon", "not_after": today + timedelta(days=197),
                       "version": "TLSv1.3"}
        self.answer.update(override)

    def __call__(self, host):
        self.calls.append(host)
        return dict(self.answer)


class World:
    def __init__(self, host="footballguys.com", *, sb=None, controls=None, days_ago=OLD,
                 rdap=None, tls=None, dns=None, confirmed=(), today=TODAY, hsts="max-age=86400",
                 preload=b'{"name": "footballguys.com", "status": "unknown"}', extra=None,
                 service_robots=None):
        self.host = host
        self.today = today
        routes = {f"https://{h}/robots.txt": resp(404) for h in SERVICES}
        routes.update(service_robots or {})
        for site, body in (controls or controls_bodies()).items():
            routes[sc.safe_browsing_url(site)] = raw(body)
        routes[sc.safe_browsing_url(host)] = raw(sb if sb is not None else fx("sb_footballguys.txt"))
        routes[sc.IANA_BOOTSTRAP_URL] = raw(fx("iana_dns_bootstrap.json"))
        labels = host.split(".")
        for i in range(len(labels) - 1):
            routes[RDAP_BASE + ".".join(labels[i:])] = rdap if rdap is not None else raw(rdap_body(days_ago, today))
        routes[f"https://{host}/robots.txt"] = resp(404, strict_transport_security=hsts) if hsts else resp(404)
        routes[sc.HSTS_PRELOAD_URL + quote(host, safe="")] = raw(preload)
        routes.update(extra or {})
        self.clock = Clock()
        self.transport = FakeTransport(routes, self.clock)
        self.fetcher = sc.Fetcher(self.transport, clock=self.clock, sleep=self.clock.sleep,
                                  today=lambda: today)
        self.dns = dns or Dns()
        self.tls = tls or Tls(today)
        self.confirmed = set(confirmed)
        self.checker = sc.SecurityChecker(self.fetcher, resolver=self.dns, tls_probe=self.tls,
                                          confirmed=self.confirmed, today=lambda: today)

    def check(self, host=None):
        return self.checker.check(host or self.host)

    def host_requests(self, host=None):
        host = host or self.host
        return [u for u in self.transport.urls() if urlsplit(u).hostname == host]


def test_fixtures_are_the_owners_five_reads():
    readings = {name: sc.parse_safe_browsing(fx(name)) for name in (
        "sb_control_malware.txt", "sb_control_phishing.txt", "sb_control_unwanted.txt",
        "sb_footballguys.txt", "sb_google_code4.txt")}
    assert [r.code for r in readings.values()] == [2, 2, 2, 1, 4]
    assert readings["sb_footballguys.txt"].scan == date(2026, 11, 8)
    assert readings["sb_google_code4.txt"].scan == date(2026, 10, 5)
    assert fx("sb_footballguys.txt").replace(b"\r\n", b"\n").startswith(b")]}'\n\n[[")


def test_all_three_controls_two_means_a_clean_host_is_possible():
    w = World()
    result = w.check()
    assert result.controls == {"malware": 2, "phishing": 2, "unwanted": 2, "shape_ok": True}
    assert w.checker.controls().passed
    assert result.safe_browsing == {"via": "transparency_report", "code": 1,
                                    "google_scan": date(2026, 11, 8)}
    assert result.flags == []
    assert result.readable and not result.held


def test_footballguys_shaped_fixture_gives_no_flags():
    w = World()
    result = w.check()
    assert result.flags == []
    assert result.dns == "resolves"
    assert result.tls == {"ok": True, "issuer": "Amazon", "not_after": TODAY + timedelta(days=197),
                          "version": "TLSv1.3"}
    assert result.hsts == {"max_age": 86400, "preloaded": False}
    assert result.registered == date(1999, 7, 9)
    assert "footballguys.com" in w.fetcher.secure_hosts
    assert w.host_requests() == ["https://footballguys.com/robots.txt"]
    for _, headers, _ in w.transport.calls:
        assert headers == {"User-Agent": UA}


def test_result_block_is_facts_and_flags_only():
    block = World().check().block()
    assert set(block) == {"checked", "host", "controls", "safe_browsing", "dns", "tls", "hsts",
                          "registered", "flags"}
    assert block["checked"] == TODAY and block["host"] == "footballguys.com"


@pytest.mark.parametrize("which", ["malware", "phishing", "unwanted"])
def test_any_control_not_two_means_controls_failed_and_no_host_reads_clean(which):
    controls = controls_bodies()
    controls[sc.SB_CONTROLS[which]] = fx("sb_footballguys.txt")
    w = World(controls=controls)
    first = w.check()
    second = w.check("other.example")
    for result in (first, second):
        assert result.flags == ["controls_failed"]
        assert result.safe_browsing["code"] is None
        assert not result.readable
    assert first.controls[which] == 1 and first.controls["shape_ok"] is True
    assert sc.safe_browsing_url("footballguys.com") not in w.transport.urls()
    assert w.dns.calls == [] and w.tls.calls == []
    assert w.fetcher.secure_hosts == set()
    for url in (sc.safe_browsing_url(site) for site in sc.SB_CONTROLS.values()):
        assert w.transport.count(url) == 1


MALFORMED = {
    "wrong prefix": b'{"a": 1}\n[["sb.ssr",2,true,false,true,false,false,1794143672856,"x",false]]',
    "no prefix": b'[["sb.ssr",2,true,false,true,false,false,1794143672856,"x",false]]',
    "wrong length": b')]}\'\n\n[["sb.ssr",2,true,false,true,false,false,1794143672856,"x"]]',
    "wrong first element": b')]}\'\n\n[["sb.xyz",2,true,false,true,false,false,1794143672856,"x",false]]',
    "two rows": b')]}\'\n\n[["sb.ssr",2,true,false,true,false,false,1794143672856,"x",false],'
                b'["sb.ssr",2,true,false,true,false,false,1794143672856,"y",false]]',
    "not json": b")]}'\n\n<html>blocked</html>",
    "code is text": b')]}\'\n\n[["sb.ssr","2",true,false,true,false,false,1794143672856,"x",false]]',
    "empty": b"",
}


@pytest.mark.parametrize("name", list(MALFORMED))
def test_a_malformed_control_response_means_controls_failed(name):
    controls = controls_bodies()
    controls[MALWARE] = MALFORMED[name]
    w = World(controls=controls)
    result = w.check()
    assert result.flags == ["controls_failed"]
    assert result.controls["shape_ok"] is False
    assert result.controls["malware"] is None
    assert not result.readable
    assert sc.parse_safe_browsing(MALFORMED[name]) is None


def test_a_malformed_response_for_a_host_is_controls_failed_for_that_host():
    w = World(sb=MALFORMED["wrong length"])
    result = w.check()
    assert "controls_failed" in result.flags
    assert result.safe_browsing["code"] is None
    assert not result.readable
    assert w.tls.calls == []


def test_code_four_is_no_verdict_and_keeps_the_code():
    w = World("google.com", sb=fx("sb_google_code4.txt"), today=date(2026, 10, 20),
              preload=b'{"status": "unknown"}')
    result = w.check()
    assert result.safe_browsing == {"via": "transparency_report", "code": 4,
                                    "google_scan": date(2026, 10, 5)}
    assert result.flags == ["sb_no_verdict"]
    assert result.held and not result.readable


def test_a_code_four_host_gets_no_connection_until_it_is_confirmed():
    w = World("google.com", sb=fx("sb_google_code4.txt"), today=date(2026, 10, 20),
              preload=b'{"status": "unknown"}', extra={"https://google.com/terms": resp(200, "t")})
    before = w.check()
    assert before.flags == ["sb_no_verdict"]
    assert before.held and not before.readable
    assert w.host_requests() == []
    assert w.tls.calls == []
    assert w.fetcher.get("https://google.com/terms").outcome == "failed"
    assert w.host_requests() == []

    w.confirmed.add("google.com")
    after = w.check()
    assert after.flags == ["sb_no_verdict"]
    assert after.readable and not after.held
    assert w.host_requests() == ["https://google.com/robots.txt"]
    assert w.fetcher.get("https://google.com/terms").outcome == "ok"


@pytest.mark.parametrize("answer", [raw(b"", 500), raw(b"", 403), raw(b"", 429)])
def test_a_host_safe_browsing_failure_is_no_verdict_and_held(answer):
    w = World()
    w.transport.routes[sc.safe_browsing_url("footballguys.com")] = [answer]
    result = w.check()
    assert result.flags == ["sb_no_verdict"]
    assert result.safe_browsing["code"] is None
    assert result.held and not result.readable
    assert w.host_requests() == [] and w.tls.calls == []


def test_stale_and_expiring_flags_do_not_hold_a_host():
    w = World(sb=fx("sb_footballguys.txt"), today=date(2026, 12, 20),
              tls=Tls(today=date(2026, 12, 20), not_after=date(2026, 12, 22)))
    result = w.check()
    assert result.flags == ["tls_expiring", "sb_stale"]
    assert result.readable and not result.held


def test_an_old_scan_is_stale():
    w = World("google.com", sb=fx("sb_google_code4.txt"), preload=b'{"status": "unknown"}')
    result = w.check()
    assert result.flags == ["sb_no_verdict", "sb_stale"]
    assert result.safe_browsing["google_scan"] == date(2026, 10, 5)


@pytest.mark.parametrize("today,stale", [(date(2026, 12, 8), False), (date(2026, 12, 9), True)])
def test_stale_starts_after_thirty_days(today, stale):
    w = World(today=today, controls=controls_bodies())
    assert ("sb_stale" in w.check().flags) is stale


def test_code_two_is_unsafe_and_nothing_is_opened():
    w = World(sb=fx("sb_control_malware.txt"))
    result = w.check()
    assert result.flags == ["sb_unsafe"]
    assert not result.readable
    assert w.tls.calls == []
    assert w.host_requests() == []
    assert "footballguys.com" not in w.fetcher.secure_hosts


def test_nxdomain_means_no_further_request():
    w = World(dns=Dns(missing=["footballguys.com"]))
    result = w.check()
    assert result.flags == ["nxdomain"]
    assert result.dns == "nxdomain"
    assert not result.readable
    assert w.tls.calls == []
    assert w.host_requests() == []
    assert sc.safe_browsing_url("footballguys.com") not in w.transport.urls()
    assert not any(u.startswith(RDAP_BASE) for u in w.transport.urls())
    assert sc.IANA_BOOTSTRAP_URL not in w.transport.urls()


NX_CODES = [c for c in (socket.EAI_NONAME, 11001, getattr(socket, "EAI_NODATA", None)) if c is not None]


@pytest.mark.parametrize("code", NX_CODES)
def test_only_a_name_not_found_answer_is_nxdomain(code):
    w = World(dns=Dns(missing=["footballguys.com"], code=code))
    result = w.check()
    assert result.flags == ["nxdomain"]
    assert result.dns == "nxdomain"
    assert result.block()["dns"] == "nxdomain"
    assert w.host_requests() == []


@pytest.mark.parametrize("code", [getattr(socket, "EAI_AGAIN", -3), getattr(socket, "EAI_FAIL", -4), 0])
def test_any_other_resolver_error_stops_the_host_with_no_block(code):
    w = World(dns=Dns(missing=["footballguys.com"], code=code))
    result = w.check()
    assert result.failed and result.failed.startswith("dns:")
    assert result.block() is None
    assert result.flags == [] and result.dns is None
    assert not result.readable and not result.held
    assert w.tls.calls == []
    assert w.host_requests() == []
    assert sc.safe_browsing_url("footballguys.com") not in w.transport.urls()
    assert not any(u.startswith(RDAP_BASE) for u in w.transport.urls())
    assert "footballguys.com" not in w.fetcher.secure_hosts


def test_a_failed_dns_check_is_tried_again_by_the_next_run():
    w = World(dns=Dns(missing=["footballguys.com"], code=getattr(socket, "EAI_AGAIN", -3)))
    assert w.check().failed
    w.dns.missing.clear()
    again = w.check()
    assert again.failed is None and again.flags == [] and again.readable


@pytest.mark.parametrize("days,flags", [(6, ["tls_expiring"]), (7, []), (0, ["tls_expiring"])])
def test_tls_under_seven_days_is_expiring(days, flags):
    w = World(tls=Tls(not_after=TODAY + timedelta(days=days)))
    result = w.check()
    assert result.flags == flags
    assert result.readable


@pytest.mark.parametrize("answer", [
    {"ok": False, "not_after": None, "issuer": None, "version": None, "error": "hostname mismatch"},
    {"not_after": TODAY - timedelta(days=1)},
])
def test_a_failed_or_expired_tls_is_tls_failed_and_no_request_follows(answer):
    w = World(tls=Tls(**answer))
    result = w.check()
    assert result.flags == ["tls_failed"]
    assert result.tls["ok"] is False
    assert not result.readable
    assert w.host_requests() == []
    assert "footballguys.com" not in w.fetcher.secure_hosts
    assert w.fetcher.get("https://footballguys.com/terms").outcome == "failed"


def test_registered_300_days_ago_is_young_and_nothing_is_requested_before_confirmation():
    w = World("young.example.com", days_ago=300,
              preload=b'{"status": "unknown"}', extra={
                  "https://young.example.com/terms": resp(200, "terms")})
    before = w.check()
    assert before.flags == ["young_domain"]
    assert before.registered == TODAY - timedelta(days=300)
    assert before.held and not before.readable
    assert w.host_requests() == []
    assert w.tls.calls == []
    assert w.fetcher.get("https://young.example.com/terms").outcome == "failed"
    assert w.host_requests() == []
    assert before.hsts is None

    w.confirmed.add("young.example.com")
    after = w.check()
    assert after.flags == ["young_domain"]
    assert after.readable and not after.held
    assert w.tls.calls == ["young.example.com"]
    assert w.host_requests() == ["https://young.example.com/robots.txt"]
    assert w.fetcher.get("https://young.example.com/terms").outcome == "ok"


def test_a_year_old_domain_is_not_young():
    assert World(days_ago=365).check().flags == []
    assert World(days_ago=364).check().flags == ["young_domain"]


@pytest.mark.parametrize("rdap", [
    resp(404),
    resp(500),
    raw(b'{"objectClassName": "domain", "events": [{"eventAction": "expiration", "eventDate": "2030-01-01T00:00:00Z"}]}'),
    raw(b"not json"),
])
def test_no_registration_answer_is_age_unknown_and_held(rdap):
    w = World(rdap=rdap)
    result = w.check()
    assert result.flags == ["age_unknown"]
    assert result.registered is None
    assert result.held and not result.readable
    assert w.host_requests() == []
    w.confirmed.add("footballguys.com")
    assert w.check().readable


def test_rdap_tries_shorter_names_for_a_subdomain():
    w = World("www.footballguys.com", extra={
        RDAP_BASE + "www.footballguys.com": resp(404),
        RDAP_BASE + "footballguys.com": raw(rdap_body(OLD)),
        sc.safe_browsing_url("www.footballguys.com"): raw(fx("sb_footballguys.txt"))},
        preload=b'{"status": "unknown"}')
    result = w.check()
    assert result.registered == date(1999, 7, 9)
    assert w.transport.urls().count(RDAP_BASE + "www.footballguys.com") == 1
    assert w.transport.urls().count(RDAP_BASE + "footballguys.com") == 1


def test_rdap_server_comes_from_the_bootstrap_and_is_a_service_host():
    w = World()
    assert "rdap.verisign.com" not in w.fetcher.service_hosts
    w.check()
    assert "rdap.verisign.com" in w.fetcher.service_hosts
    urls = w.transport.urls()
    assert urls.index("https://rdap.verisign.com/robots.txt") < urls.index(RDAP_BASE + "footballguys.com")


def test_a_tld_missing_from_the_bootstrap_is_age_unknown():
    w = World("a.example.io", extra={sc.safe_browsing_url("a.example.io"): raw(fx("sb_footballguys.txt"))})
    result = w.check()
    assert result.flags == ["age_unknown"]
    assert not any(u.startswith(RDAP_BASE) for u in w.transport.urls())


def test_every_service_host_passes_its_robots_first():
    w = World()
    w.check()
    urls = w.transport.urls()
    for host in SERVICES:
        own = [i for i, u in enumerate(urls) if urlsplit(u).hostname == host]
        assert urls[own[0]] == f"https://{host}/robots.txt"
        assert own == sorted(own)


def test_a_service_host_that_disallows_us_stops_the_controls():
    w = World(service_robots={"https://transparencyreport.google.com/robots.txt":
                              resp(200, "User-agent: *\nDisallow: /\n")})
    result = w.check()
    assert result.flags == ["controls_failed"]
    assert not any("safebrowsing" in u for u in w.transport.urls())


def test_hsts_comes_from_the_robots_response_and_preload_from_hstspreload():
    w = World(hsts="max-age=31536000; includeSubDomains; preload",
              preload=b'{"name": "footballguys.com", "status": "preloaded"}')
    result = w.check()
    assert result.hsts == {"max_age": 31536000, "preloaded": True}
    assert w.host_requests() == ["https://footballguys.com/robots.txt"]
    assert result.flags == []


def test_hsts_absent_and_preload_unavailable_are_null_and_never_a_flag():
    w = World(hsts=None, preload=b"not json")
    result = w.check()
    assert result.hsts == {"max_age": None, "preloaded": None}
    assert result.flags == []


@pytest.mark.parametrize("value,expected", [
    ("max-age=86400", 86400), ("max-age=0", 0), ("MAX-AGE=10; includeSubDomains", 10),
    ('max-age="300"', 300), ("includeSubDomains", None), (None, None), ("", None)])
def test_hsts_max_age_parsing(value, expected):
    assert sc.parse_hsts_max_age(value) == expected


def test_tls_fields_reads_the_certificate_shape_ssl_returns():
    cert = {"issuer": ((("countryName", "US"),), (("organizationName", "Amazon"),),
                       (("commonName", "Amazon RSA 2048 M01"),)),
            "notAfter": "May 17 23:59:59 2027 GMT"}
    assert sc.tls_fields(cert, "TLSv1.3") == {"ok": True, "issuer": "Amazon",
                                              "not_after": date(2027, 5, 17), "version": "TLSv1.3"}


def test_read_robots_refuses_a_host_that_has_not_passed_the_check():
    f, t, _ = build({A_ROBOTS: resp(404)}, secure=())
    with pytest.raises(sc.RobotsNotRead):
        f.read_robots("a.example")
    assert t.calls == []


def test_the_security_result_never_holds_status_or_confirmed():
    result = World().check()
    assert not hasattr(result, "status") and not hasattr(result, "confirmed")


def test_confirmed_hosts_are_read_only_from_security_confirmed(tmp_path):
    manifest = tmp_path / "sources.yml"
    manifest.write_text(
        "sources:\n"
        "  - id: a\n    security: {host: Young.Example.com, confirmed: {by: owner, date: 2026-11-08}}\n"
        "  - id: b\n    security: {host: b.example, confirmed: {by: owner, date: null}}\n"
        "  - id: c\n    security: {host: c.example, confirmed: {by: null, date: 2026-11-08}}\n"
        "  - id: d\n    security: {host: d.example}\n"
        "  - id: e\n    terms: {status: unresolved}\n", encoding="utf-8")
    assert sc.load_confirmed_hosts(manifest) == {"young.example.com"}


def test_the_real_manifest_loads_as_a_set_of_hosts():
    hosts = sc.load_confirmed_hosts()
    assert isinstance(hosts, set) and all(isinstance(h, str) for h in hosts)


A_HOME = "https://a.example/"
A_TDMREP = "https://a.example/.well-known/tdmrep.json"
A_LLMS = "https://a.example/llms.txt"
A_SITEMAP = "https://a.example/sitemap.xml"
A_WP_SITEMAP = "https://a.example/wp-sitemap.xml"
UNLINKED = {A_ROBOTS, A_HOME, A_SITEMAP, A_WP_SITEMAP, A_TDMREP, A_LLMS}
DOC_KEYS = {"kind", "url", "reached_from", "read", "page_date", "read_by", "method", "unread",
            "archive", "capture_sha256"}
COPYRIGHT = "Copyright © 2022"


def html_page(name, **headers):
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return resp(200, text, content_type="text/html; charset=utf-8", **headers)


def inline(body, status=200):
    return resp(status, f"<!doctype html><html><body>{body}</body></html>", content_type="text/html")


def reader(routes, secure=("a.example",), checker=None):
    fetcher, transport, clock = build(routes, secure)
    if checker is not None:
        checker.fetcher = fetcher
    return sc.SourceReader(fetcher, checker), fetcher, transport, clock


def site(extra=None, **overrides):
    routes = {A_ROBOTS: resp(404), A_HOME: html_page("site_home.html"),
              "https://a.example/terms": html_page("site_terms.html"),
              "https://a.example/privacy-policy": html_page("site_privacy.html"),
              A_TDMREP: resp(404), A_LLMS: resp(404)}
    routes.update(overrides)
    routes.update(extra or {})
    return routes


def only_linked(transport, *linked):
    assert set(transport.urls()) <= UNLINKED | set(linked)


def places(reading):
    return [(d.kind, d.place, d.link_text, d.page) for d in reading.documents]


def test_footballguys_shaped_site_gives_both_documents_from_the_footer():
    rd, f, t, _ = reader(site())
    r = rd.read("a.example")
    assert places(r) == [
        ("terms", "footer", "Terms of Service", A_HOME),
        ("privacy", "footer", "Privacy Policy", A_HOME)]
    assert t.urls() == [A_ROBOTS, A_HOME, "https://a.example/terms",
                        "https://a.example/privacy-policy", A_TDMREP, A_LLMS]
    assert r.not_found == [] and not r.incomplete and r.skipped is None
    assert r.copyright_line == "Copyright © 2022 Example Fantasy LLC. All Rights Reserved."
    assert r.signals_block() == {
        "robots": {"url": A_ROBOTS, "code": 404, "read": TODAY, "claude_groups": [],
                   "blocks_agent": False, "content_signal": None, "content_usage": None,
                   "crawl_delay": None, "sha256": None},
        "tdmrep": {"well_known": 404, "header": None, "meta": None},
        "x_robots_tag": None, "meta_robots": None}
    for _, headers, _ in t.calls:
        assert headers == {"User-Agent": UA}


def test_a_document_block_has_the_a2_fields_and_no_clauses_or_status():
    rd, *_ = reader(site())
    r = rd.read("a.example")
    first = r.documents_block()[0]
    assert set(first) == DOC_KEYS
    assert first == {
        "kind": "terms", "url": "https://a.example/terms",
        "reached_from": {"page": A_HOME, "place": "footer", "link_text": "Terms of Service"},
        "read": TODAY, "page_date": date(2026, 11, 4), "read_by": "script", "method": "http_get",
        "unread": None, "archive": None, "capture_sha256": None}
    assert r.documents_block()[1]["page_date"] == date(2026, 10, 1)
    assert not hasattr(r, "status") and not hasattr(r, "clauses")


def test_a_menu_link_is_found_in_the_menu():
    rd, f, t, _ = reader({
        A_ROBOTS: resp(404), A_HOME: html_page("home_nav.html"),
        "https://a.example/terms-and-conditions": html_page("site_terms.html"),
        "https://a.example/privacy": html_page("site_privacy.html"), A_TDMREP: resp(404),
        A_LLMS: resp(404)})
    r = rd.read("a.example")
    assert places(r) == [
        ("terms", "menu", "Terms and Conditions", A_HOME), ("privacy", "menu", "Privacy", A_HOME)]
    assert r.looked == ["footer", "menu"]
    assert A_SITEMAP not in t.urls()


def test_a_sitemap_entry_is_found_in_the_sitemap_with_no_link_text():
    rd, f, t, _ = reader({
        A_ROBOTS: resp(404), A_HOME: inline("<p>nothing linked</p>"),
        A_SITEMAP: resp(200, (FIXTURES / "sitemap_terms.xml").read_text(encoding="utf-8"),
                        content_type="application/xml"),
        "https://a.example/terms-of-use": html_page("site_terms.html"),
        "https://a.example/privacy": html_page("site_privacy.html"), A_TDMREP: resp(404),
        A_LLMS: resp(404)})
    r = rd.read("a.example")
    assert places(r) == [("terms", "sitemap", None, A_SITEMAP), ("privacy", "sitemap", None, A_SITEMAP)]
    assert "sitemap" in r.looked
    assert A_WP_SITEMAP not in t.urls()
    only_linked(t, "https://a.example/terms-of-use", "https://a.example/privacy")


def test_the_robots_sitemap_line_is_read_before_the_default_sitemaps():
    robots = ("User-agent: *\nAllow: /\nSitemap: https://a.example/map.xml\n"
              "Sitemap: https://other.example/elsewhere.xml\n")
    rd, f, t, _ = reader({
        A_ROBOTS: resp(200, robots), A_HOME: inline("<p>nothing linked</p>"),
        "https://a.example/map.xml": resp(200, (FIXTURES / "sitemap_terms.xml").read_text(
            encoding="utf-8"), content_type="application/xml"),
        "https://a.example/terms-of-use": html_page("site_terms.html"),
        "https://a.example/privacy": html_page("site_privacy.html"), A_TDMREP: resp(404),
        A_LLMS: resp(404)})
    r = rd.read("a.example")
    assert r.documents[0].page == "https://a.example/map.xml"
    assert A_SITEMAP not in t.urls()
    assert "https://other.example/elsewhere.xml" not in t.urls()


def test_a_legal_hub_page_is_followed_for_the_documents_it_links():
    rd, f, t, _ = reader({
        A_ROBOTS: resp(404), A_HOME: html_page("home_hub.html"), A_SITEMAP: resp(404),
        A_WP_SITEMAP: resp(404), "https://a.example/legal": html_page("legal_hub.html"),
        "https://a.example/legal/terms": html_page("site_terms.html"),
        "https://a.example/legal/privacy": html_page("site_privacy.html"), A_TDMREP: resp(404),
        A_LLMS: resp(404)})
    r = rd.read("a.example")
    hub = "https://a.example/legal"
    assert places(r) == [("terms", "legal_hub", "Terms of Use", hub),
                         ("privacy", "legal_hub", "Privacy Policy", hub)]
    assert "legal_hub" in r.looked


def test_a_link_inside_a_found_document_is_followed():
    rd, f, t, _ = reader({
        A_ROBOTS: resp(404), A_HOME: html_page("home_privacy_only.html"), A_SITEMAP: resp(404),
        A_WP_SITEMAP: resp(404), "https://a.example/privacy": html_page("site_privacy.html"),
        "https://a.example/terms-of-use": html_page("site_terms.html"), A_TDMREP: resp(404),
        A_LLMS: resp(404)})
    r = rd.read("a.example")
    assert places(r) == [
        ("privacy", "footer", "Privacy Policy", A_HOME),
        ("terms", "linked_from_doc", "Terms of Use", "https://a.example/privacy")]
    assert r.not_found == []


def test_a_site_with_only_a_privacy_link_gives_a_not_found_for_terms_and_no_guessed_request():
    rd, f, t, _ = reader({
        A_ROBOTS: resp(404), A_HOME: html_page("home_privacy_only.html"),
        "https://a.example/privacy": inline("<p>No links here.</p>"), A_SITEMAP: resp(404),
        A_WP_SITEMAP: resp(404), A_TDMREP: resp(404), A_LLMS: resp(404)})
    r = rd.read("a.example")
    assert [d.kind for d in r.documents] == ["privacy"]
    assert len(r.not_found) == 1
    found = r.not_found[0]
    assert found.block() == {"kind": "terms", "looked": ["footer", "menu", "sitemap", "linked_from_doc"],
                             "date": TODAY, "by": "script"}
    assert found.copyright_line == "Copyright © 2022 | Example Fantasy | All Rights Reserved"
    assert r.not_found_block() == [found.block()]
    only_linked(t, "https://a.example/privacy")
    assert not any(u.endswith(("/terms", "/tos", "/terms-of-use", "/legal")) for u in t.urls())


def test_a_failed_read_never_becomes_a_not_found():
    rd, f, t, _ = reader({
        A_ROBOTS: resp(404), A_HOME: html_page("home_privacy_only.html"),
        "https://a.example/privacy": inline("<p>No links here.</p>"),
        A_SITEMAP: sc.TransportError("boom"), A_WP_SITEMAP: resp(404), A_TDMREP: resp(404),
        A_LLMS: resp(404)})
    r = rd.read("a.example")
    assert r.not_found == [] and r.incomplete
    assert [x["url"] for x in r.failed] == [A_SITEMAP]
    assert "sitemap" not in r.looked


def test_a_broken_link_is_not_a_document():
    rd, f, t, _ = reader(site({"https://a.example/terms": resp(404), A_SITEMAP: resp(404),
                               A_WP_SITEMAP: resp(404),
                               "https://a.example/privacy-policy": inline("<p>No links.</p>")}))
    r = rd.read("a.example")
    assert [d.kind for d in r.documents] == ["privacy"]
    assert r.broken == [{"url": "https://a.example/terms", "status": 404, "place": "footer",
                         "page": A_HOME}]
    assert r.not_found[0].kind == "terms"


def test_a_403_on_a_document_stops_the_host_and_reads_nothing_more():
    rd, f, t, _ = reader(site({"https://a.example/terms": resp(403)}))
    r = rd.read("a.example")
    assert [(d.kind, d.unread) for d in r.documents] == [
        ("terms", sc.UNREAD_REFUSED_STATUS), ("privacy", sc.UNREAD_REFUSED_STATUS)]
    assert "https://a.example/privacy-policy" not in t.urls()
    assert A_TDMREP not in t.urls() and A_LLMS not in t.urls()
    assert r.incomplete and r.stopped and r.not_found == []


def test_a_robots_403_is_one_request_and_nothing_is_discovered():
    rd, f, t, _ = reader({A_ROBOTS: resp(403)})
    r = rd.read("a.example")
    assert t.urls() == [A_ROBOTS]
    assert (r.home.outcome, r.home.unread) == ("unread", sc.UNREAD_REFUSED_STATUS)
    assert r.robots.code == 403 and r.documents == [] and r.not_found == []
    assert r.signals_block()["robots"]["code"] == 403


def test_a_robots_disallow_for_the_entry_page_is_unread_and_not_a_not_found():
    rd, f, t, _ = reader({A_ROBOTS: resp(200, "User-agent: *\nDisallow: /\n")})
    r = rd.read("a.example")
    assert t.urls() == [A_ROBOTS]
    assert r.home.unread == sc.UNREAD_ROBOTS_BLOCKS_AGENT
    assert r.not_found == [] and r.documents == []


def test_a_host_that_has_not_passed_the_security_check_gets_no_request():
    rd, f, t, _ = reader(site(), secure=())
    r = rd.read("a.example")
    assert r.skipped == "security_not_cleared"
    assert t.calls == [] and r.documents == []


def test_robots_signals_are_kept_verbatim_with_unknown_keys_apart():
    text = (FIXTURES / "robots_signals.txt").read_text(encoding="utf-8")
    f, t, _ = build({A_ROBOTS: resp(200, text)})
    f.read_robots("a.example")
    sig = sc.robots_signals(f.robots("a.example"))
    assert sig.content_signal == [{
        "agents": ["*"], "line": "Content-Signal: search=yes, ai-train=no, ai-input=no, fancy-new=maybe",
        "known": {"search": "yes", "ai-train": "no", "ai-input": "no"},
        "unknown": {"fancy-new": "maybe"}}]
    assert sig.content_usage == [
        {"agents": ["ClaudeBot", "Claude-User"], "line": "Content-Usage: train-ai=n, ai-use=y, search=y",
         "known": {"train-ai": "n", "ai-use": "y", "search": "y"}, "unknown": {}},
        {"agents": ["GPTBot"], "line": "Content-Usage: ai-use=n, made-up",
         "known": {"ai-use": "n"}, "unknown": {"made-up": None}}]
    assert sig.crawl_delay == [{"agents": ["ClaudeBot", "Claude-User"], "line": "Crawl-delay: 7"}]
    assert sig.sitemaps == ["https://a.example/sitemap-main.xml", "https://a.example/sitemap-news.xml"]
    assert sig.sha256 == hashlib.sha256(text.encode()).hexdigest()
    assert sig.claude_groups == ["ClaudeBot", "Claude-User"] and sig.blocks_agent is False
    assert set(sig.block()) == {"url", "code", "read", "claude_groups", "blocks_agent", "content_signal",
                                "content_usage", "crawl_delay", "sha256"}


def test_only_the_defined_keys_of_each_vocabulary_are_interpreted():
    known, unknown = sc.interpret_signal_line("Content-Signal: ai-use=y, search=n", sc.CONTENT_SIGNAL_KEYS)
    assert known == {"search": "n"} and unknown == {"ai-use": "y"}
    known, unknown = sc.interpret_signal_line("Content-Usage: ai-input=n", sc.CONTENT_USAGE_KEYS)
    assert known == {} and unknown == {"ai-input": "n"}


def test_robots_without_signals_has_null_signal_fields():
    f, t, _ = build({A_ROBOTS: resp(200, ALLOW_ALL)})
    f.read_robots("a.example")
    block = sc.robots_signals(f.robots("a.example")).block()
    assert block["content_signal"] is None and block["content_usage"] is None
    assert block["crawl_delay"] is None and block["code"] == 200


def test_page_signals_are_collected_from_headers_meta_and_the_well_known_file():
    rd, f, t, _ = reader(site(
        {A_HOME: html_page("home_signals.html", x_robots_tag="noai", content_usage="ai-use=n",
                           tdm_reservation="1", tdm_policy="https://a.example/p.json"),
         A_TDMREP: resp(200, '[{"location": "/", "tdm-reservation": 1}]'),
         "https://a.example/privacy": html_page("site_privacy.html")}))
    r = rd.read("a.example")
    sig = r.home_signals()
    assert (sig.x_robots_tag, sig.content_usage, sig.tdm_reservation, sig.tdm_policy) == (
        "noai", "ai-use=n", "1", "https://a.example/p.json")
    assert sig.meta_robots == "noindex, noai, NoImageAI"
    assert (sig.meta_tdm_reservation, sig.meta_tdm_policy) == ("1", "https://a.example/tdm-policy.json")
    assert sig.noai == ["noai", "noai", "NoImageAI"]
    assert r.tdmrep_code == 200 and r.tdmrep_body == '[{"location": "/", "tdm-reservation": 1}]'
    assert r.signals_block()["tdmrep"] == {"well_known": 200, "header": "1", "meta": "1"}
    assert r.signals_block()["x_robots_tag"] == "noai"
    assert r.signals_block()["meta_robots"] == "noindex, noai, NoImageAI"
    assert r.llms_txt_code == 404


def test_a_segmented_host_reads_the_essentials_before_the_optional_reads():
    rd, f, t, _ = reader(site({A_ROBOTS: [resp(429), resp(200, ALLOW_ALL)]}))
    r = rd.read("a.example")
    urls = t.urls()
    assert urls == [A_ROBOTS, A_ROBOTS, A_HOME, "https://a.example/terms",
                    "https://a.example/privacy-policy", A_TDMREP, A_LLMS]
    assert len(r.documents) == 2
    times = [t.times(u)[0] for u in urls[2:]]
    assert all(b - a >= sc.SEGMENT_DELAY for a, b in zip(times, times[1:]))


def test_a_deferred_entry_page_is_continued_from_the_cache_after_the_deferred_try():
    routes = site({A_HOME: [resp(429)] * 3 + [html_page("site_home.html")]})
    rd, f, t, _ = reader(routes)
    first = rd.read("a.example")
    assert first.pending == [A_HOME] and first.incomplete and first.documents == []
    assert first.not_found == []
    f.run_deferred()
    second = rd.read("a.example")
    assert [d.kind for d in second.documents] == ["terms", "privacy"]
    assert second.pending == [] and not second.incomplete
    assert t.count(A_HOME) == 4


def test_an_operator_domain_link_gets_its_own_security_check_before_a_read():
    home = inline('<footer><a href="https://ops.example/terms">Terms of Service</a>'
                  '<a href="/privacy">Privacy Policy</a></footer>')
    routes = {A_ROBOTS: resp(404), A_HOME: home, "https://a.example/privacy": inline("<p>p</p>"),
              A_SITEMAP: resp(404), A_WP_SITEMAP: resp(404),
              "https://ops.example/robots.txt": resp(404),
              "https://ops.example/terms": html_page("site_terms.html"), A_TDMREP: resp(404),
              A_LLMS: resp(404)}
    checker = FakeChecker("ok")
    rd, f, t, _ = reader(routes, checker=checker)
    r = rd.read("a.example")
    assert checker.calls == ["ops.example"]
    assert ("terms", "operator_domain", "Terms of Service", A_HOME) in places(r)
    assert t.urls().index("https://ops.example/robots.txt") < t.urls().index("https://ops.example/terms")
    assert "operator_domain" in r.looked and r.not_found == []


@pytest.mark.parametrize("outcome,reason", [("held", sc.UNREAD_TOOL_REFUSED),
                                            ("nxdomain", sc.UNREAD_DNS)])
def test_an_operator_host_that_fails_or_is_held_gets_no_request(outcome, reason):
    home = inline('<footer><a href="https://ops.example/terms">Terms of Service</a></footer>')
    routes = {A_ROBOTS: resp(404), A_HOME: home, A_SITEMAP: resp(404), A_WP_SITEMAP: resp(404),
              A_TDMREP: resp(404), A_LLMS: resp(404)}
    checker = FakeChecker(outcome)
    rd, f, t, _ = reader(routes, checker=checker)
    r = rd.read("a.example")
    doc = r.documents[0]
    assert (doc.kind, doc.place, doc.unread, doc.fetch) == ("terms", "operator_domain", reason, None)
    assert not any(urlsplit(u).hostname == "ops.example" for u in t.urls())
    assert r.documents_block()[0]["unread"] == reason


def test_an_other_host_link_with_no_security_check_available_is_not_read():
    home = inline('<footer><a href="https://ops.example/terms">Terms of Service</a></footer>')
    rd, f, t, _ = reader({A_ROBOTS: resp(404), A_HOME: home, A_SITEMAP: resp(404),
                          A_WP_SITEMAP: resp(404), A_TDMREP: resp(404), A_LLMS: resp(404)})
    r = rd.read("a.example")
    assert r.documents[0].unread == sc.UNREAD_TOOL_REFUSED
    assert not any(urlsplit(u).hostname == "ops.example" for u in t.urls())


def test_the_www_host_of_a_site_is_its_own_host_with_its_own_check():
    home = inline('<footer><a href="https://www.a.example/terms">Terms of Service</a></footer>')
    routes = {A_ROBOTS: resp(404), A_HOME: home, A_SITEMAP: resp(404), A_WP_SITEMAP: resp(404),
              "https://www.a.example/robots.txt": resp(404),
              "https://www.a.example/terms": html_page("site_terms.html"), A_TDMREP: resp(404),
              A_LLMS: resp(404)}
    checker = FakeChecker("ok")
    rd, f, t, _ = reader(routes, checker=checker)
    r = rd.read("a.example")
    assert checker.calls == ["www.a.example"]
    assert places(r)[0] == ("terms", "footer", "Terms of Service", A_HOME)


class FakeChecker:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []
        self.fetcher = None

    def check(self, host):
        self.calls.append(host)
        if self.outcome == "ok":
            self.fetcher.mark_secure(host)
            return SimpleNamespace(readable=True, dns="resolves", flags=[], failed=None)
        if self.outcome == "nxdomain":
            return SimpleNamespace(readable=False, dns="nxdomain", flags=["nxdomain"], failed=None)
        return SimpleNamespace(readable=False, dns="resolves", flags=["young_domain"], failed=None)


@pytest.mark.parametrize("text,kind", [
    ("Terms of Service", "terms"), ("Terms & Conditions", "terms"), ("Terms", "terms"),
    ("Privacy Policy", "privacy"), ("Privacy", "privacy"), ("Licence", "licence"),
    ("License Agreement", "licence"), ("Legal", "hub"), ("Cookie Policy", "hub"),
    ("API Terms of Use", "api_terms"), ("API", None), ("Developer API", None),
    ("Contact Us", None), ("Rankings", None), ("", None)])
def test_link_text_is_classified_on_terms_privacy_legal_policy_licence_and_api(text, kind):
    assert sc.classify_link(text) == kind


@pytest.mark.parametrize("url,kind", [
    ("https://a.example/terms-of-use", "terms"), ("https://a.example/legal/privacy", "privacy"),
    ("https://a.example/legal/terms", "terms"), ("https://a.example/api", None),
    ("https://a.example/", None),
    ("https://a.example/blog/2026/11/why-the-terms-of-a-trade-matter", None),
    ("https://a.example/blog/terms-of-a-trade-that-matters-in-dynasty-leagues", None)])
def test_sitemap_paths_match_only_short_legal_looking_addresses(url, kind):
    assert sc.classify_path(url) == kind


@pytest.mark.parametrize("html,region", [
    ('<footer><nav><a href="/terms">Terms</a></nav></footer>', "footer"),
    ('<div class="site-Footer"><a href="/terms">Terms</a></div>', "footer"),
    ('<header><a href="/terms">Terms</a></header>', "menu"),
    ('<div id="main_menu"><a href="/terms">Terms</a></div>', "menu"),
    ('<p><a href="/terms">Terms</a></p>', "body")])
def test_a_link_region_is_footer_then_menu_then_body(html, region):
    links = sc.extract_links(sc.BeautifulSoup(html, "html.parser"), "https://a.example/")
    assert [(link.url, link.text, link.region) for link in links] == [
        ("https://a.example/terms", "Terms", region)]


def test_links_skip_fragments_scripts_and_mail():
    html = ('<a href="#top">Terms</a><a href="javascript:void(0)">Terms</a>'
            '<a href="mailto:x@example.com">Terms</a><a href="/terms#section-2">Terms</a>')
    links = sc.extract_links(sc.BeautifulSoup(html, "html.parser"), "https://a.example/page")
    assert [link.url for link in links] == ["https://a.example/terms"]


@pytest.mark.parametrize("text,expected", [
    ("Last updated: November 4, 2026", date(2026, 11, 4)),
    ("Effective 4 November 2026", date(2026, 11, 4)),
    ("Updated 2026-10-01", date(2026, 10, 1)),
    ("Last updated Nov. 4th, 2026", date(2026, 11, 4)),
    ("Effective date: someday", None), ("Last updated: 13/14/2026", None),
    ("Last updated: February 31, 2026", None)])
def test_a_candidate_page_date_is_parsed_only_when_unambiguous(text, expected):
    assert sc.parse_date_text(text) == expected


def test_a_non_html_document_is_recorded_without_parsing():
    pdf = sc.Response(200, {"content-type": "application/pdf"}, b"%PDF-1.7 Terms of Service")
    rd, f, t, _ = reader(site({"https://a.example/terms": pdf}))
    r = rd.read("a.example")
    assert r.documents[0].parsed.html is False and r.documents[0].parsed.links == []
    assert r.documents_block()[0]["page_date"] is None


def test_every_request_of_a_full_read_carries_the_user_agent_and_no_cookie():
    rd, f, t, _ = reader(site())
    rd.read("a.example")
    for _, headers, _ in t.calls:
        assert headers == {"User-Agent": UA}


def test_the_reader_has_no_network_path_of_its_own():
    rd, f, t, _ = reader(site())
    assert rd.fetcher is f
    rd.read("a.example")
    only_linked(t, "https://a.example/terms", "https://a.example/privacy-policy")


A_PAGE = "https://a.example/app"
B_LIB = "https://b.example/lib.js"
THIN_92 = "w" * 92
FULL_TEXT = " ".join(["word"] * 120)
LONG_ENOUGH = "x" * 500


def page(text):
    return inline(f"<p>{text}</p>")


class FakeRenderer:
    def __init__(self, html=None, status=200, subrequests=(), error=None, pages=None, clock=None,
                 advance=0):
        self.advance = advance
        self.html = html if html is not None else f"<html><body><p>{FULL_TEXT}</p></body></html>"
        self.status = status
        self.subrequests = list(subrequests)
        self.error = error
        self.pages = pages or {}
        self.clock = clock
        self.requests = []
        self.times = []
        self.verdicts = {}

    def __call__(self, request):
        self.requests.append(request)
        self.times.append(self.clock() if self.clock else None)
        for item in self.subrequests:
            url, kind = item if isinstance(item, tuple) else (item, None)
            self.verdicts[url] = request.allow(url, kind)
        if self.advance:
            self.clock.t += self.advance
        if self.error is not None:
            raise self.error
        return sc.RenderedPage(self.pages.get(request.url, self.html), self.status, request.url)


def renderer_for(routes, renderer=None, secure=("a.example",)):
    fetcher, transport, clock = build(routes, secure)
    fake = renderer if renderer is not None else FakeRenderer(clock=clock)
    fake.clock = fake.clock or clock
    return sc.PageRenderer(fetcher, fake), fetcher, transport, clock, fake


def fetched(routes, url=A_PAGE, **kw):
    pr, f, t, clock, fake = renderer_for({A_ROBOTS: resp(404), **routes}, **kw)
    return pr, pr.consider(f.get(url)), f, t, clock, fake


def test_a_200_with_92_characters_renders():
    pr, out, f, t, _, fake = fetched({A_PAGE: page(THIN_92)})
    assert len(fake.requests) == 1
    assert out.method == sc.METHOD_RENDER == "browser_render"
    assert out.outcome == "ok" and out.status == 200 and out.unread is None
    assert FULL_TEXT in out.body.decode()
    assert pr.skipped == {}


def test_a_200_with_full_text_does_not_render():
    pr, out, f, t, _, fake = fetched({A_PAGE: page(FULL_TEXT)})
    assert fake.requests == []
    assert out.method == "http_get" and out.outcome == "ok"
    assert pr.skipped == {A_PAGE: "has_text"}


def test_a_body_of_only_loading_renders():
    pr, out, f, t, _, fake = fetched({A_PAGE: inline("<div>Loading...</div><script>boot()</script>")})
    assert len(fake.requests) == 1 and out.method == "browser_render"


def test_the_limit_is_500_visible_characters_and_scripts_and_styles_do_not_count():
    pr, out, *_, fake = fetched({A_PAGE: page(LONG_ENOUGH[:-1])})
    assert len(fake.requests) == 1
    pr, out, *_, fake = fetched({A_PAGE: page(LONG_ENOUGH)})
    assert fake.requests == []
    hidden = "<script>" + "y" * 900 + "</script><style>" + "z" * 900 + "</style>"
    pr, out, *_, fake = fetched({A_PAGE: inline(hidden + "<p>short</p>")})
    assert len(fake.requests) == 1


def test_a_403_never_renders():
    pr, out, f, t, _, fake = fetched({A_PAGE: resp(403, "no")})
    assert fake.requests == []
    assert out.outcome == "unread" and out.unread == sc.UNREAD_REFUSED_STATUS and out.status == 403
    assert t.count(A_PAGE) == 1


def test_a_401_never_renders():
    pr, out, f, t, _, fake = fetched({A_PAGE: resp(401, "no")})
    assert fake.requests == [] and out.unread == sc.UNREAD_REFUSED_STATUS


def test_a_429_followed_by_a_200_never_renders():
    pr, out, f, t, _, fake = fetched({A_PAGE: [resp(429), resp(200, "<html><body>" + THIN_92 + "</body></html>",
                                                              content_type="text/html")]})
    assert out.outcome == "ok" and out.status == 200
    assert fake.requests == []
    assert out.method == "http_get"
    assert pr.skipped == {A_PAGE: "rate_limited"}


def test_a_robots_429_that_cleared_never_renders_a_page_of_that_host():
    pr, f, t, _, fake = renderer_for({
        A_ROBOTS: [resp(429), resp(200, ALLOW_ALL)], A_PAGE: page(THIN_92)})
    out = pr.consider(f.get(A_PAGE))
    assert out.outcome == "ok" and fake.requests == []
    assert pr.skipped == {A_PAGE: "rate_limited"}


def test_a_young_domain_never_renders_before_confirmation():
    host = "young.example.com"
    url = f"https://{host}/app"
    w = World(host, days_ago=300, preload=b'{"status": "unknown"}',
              extra={url: page(THIN_92)})
    fake = FakeRenderer(clock=w.clock)
    pr = sc.PageRenderer(w.fetcher, fake)
    before = w.check()
    assert before.held and not before.readable
    stray = sc.FetchResult(url=url, outcome="ok", status=200,
                           headers={"content-type": "text/html"}, body=b"<p>" + THIN_92.encode() + b"</p>",
                           final_url=url)
    assert pr.consider(stray) is stray
    assert fake.requests == [] and pr.skipped == {url: "host_not_cleared"}
    assert w.host_requests() == []

    w.confirmed.add(host)
    assert w.check().readable
    out = pr.consider(w.fetcher.get(url))
    assert len(fake.requests) == 1 and out.method == "browser_render" and out.outcome == "ok"


def test_a_robots_block_never_renders():
    pr, f, t, _, fake = renderer_for({A_ROBOTS: resp(200, "User-agent: *\nDisallow: /app\n"),
                                     A_PAGE: page(THIN_92)})
    f.read_robots("a.example")
    stray = sc.FetchResult(url=A_PAGE, outcome="ok", status=200,
                           headers={"content-type": "text/html"}, body=b"<p>short</p>",
                           final_url=A_PAGE)
    assert pr.consider(stray) is stray
    assert pr.skipped == {A_PAGE: sc.UNREAD_ROBOTS_BLOCKS_AGENT}
    out = pr.consider(f.get(A_PAGE))
    assert out.unread == sc.UNREAD_ROBOTS_BLOCKS_AGENT and fake.requests == []


def test_a_non_html_200_is_not_a_page_that_drew_nothing():
    pr, out, f, t, _, fake = fetched({A_PAGE: resp(200, "{}", content_type="application/json")})
    assert fake.requests == [] and pr.skipped == {A_PAGE: "not_html"}


def test_a_host_that_has_not_passed_its_check_never_renders():
    pr, out, f, t, _, fake = fetched({}, secure=())
    assert out.outcome == "failed" and fake.requests == []
    assert t.urls() == []


def test_the_renderer_is_called_with_the_user_agent_and_no_storage_state():
    pr, out, f, t, _, fake = fetched({A_PAGE: page(THIN_92)})
    (request,) = fake.requests
    assert request.user_agent == UA == sc.etl_helpers.ETL_USER_AGENT
    assert request.storage_state is None
    assert request.url == A_PAGE
    assert t.urls() == [A_ROBOTS, A_PAGE]


def test_the_page_url_passes_the_gate_before_the_renderer_is_called():
    pr, f, t, _, fake = renderer_for({A_ROBOTS: resp(200, "User-agent: *\nDisallow: /app\n"),
                                     A_PAGE: page(THIN_92)})
    out = pr.consider(f.get(A_PAGE))
    assert fake.requests == [] and t.urls() == [A_ROBOTS]
    assert out.unread == sc.UNREAD_ROBOTS_BLOCKS_AGENT


def test_the_render_navigation_is_spaced_like_any_request_to_the_host():
    pr, out, f, t, clock, fake = fetched({A_PAGE: page(THIN_92)})
    assert fake.times[0] - t.times(A_PAGE)[0] >= sc.MIN_DELAY


def test_a_page_that_still_draws_nothing_is_unread_js_rendered():
    pr, out, f, t, _, fake = fetched({A_PAGE: page(THIN_92)}, renderer=FakeRenderer(
        html="<html><body><div>Loading...</div></body></html>"))
    assert len(fake.requests) == 1
    assert out.outcome == "unread" and out.unread == sc.UNREAD_JS_RENDERED
    assert out.method == "browser_render"
    assert "Loading..." in out.detail or "characters" in out.detail


def test_a_same_host_subrequest_blocked_by_robots_is_aborted():
    renderer = FakeRenderer(subrequests=["https://a.example/api/data.json", "https://a.example/private/x.json"])
    pr, f, t, clock, fake = renderer_for(
        {A_ROBOTS: resp(200, "User-agent: *\nDisallow: /private/\n"), A_PAGE: page(THIN_92)},
        renderer=renderer)
    out = pr.consider(f.get(A_PAGE))
    assert fake.verdicts == {"https://a.example/api/data.json": True,
                             "https://a.example/private/x.json": False}
    assert out.render_aborted == [("https://a.example/private/x.json", sc.UNREAD_ROBOTS_BLOCKS_AGENT)]
    assert out.render_allowed == ["https://a.example/api/data.json"]
    assert t.urls() == [A_ROBOTS, A_PAGE]


def test_a_subrequest_to_an_unchecked_host_is_aborted_and_starts_no_check():
    renderer = FakeRenderer(subrequests=["https://c.example/cdn.js"])
    pr, f, t, _, fake = renderer_for({A_ROBOTS: resp(404), A_PAGE: page(THIN_92)}, renderer=renderer)
    out = pr.consider(f.get(A_PAGE))
    assert fake.verdicts == {"https://c.example/cdn.js": False}
    assert out.render_aborted == [("https://c.example/cdn.js", "host_not_checked")]
    assert t.urls() == [A_ROBOTS, A_PAGE]


def test_a_subrequest_to_a_host_that_passed_is_let_through():
    renderer = FakeRenderer(subrequests=[B_LIB])
    pr, f, t, _, fake = renderer_for(
        {A_ROBOTS: resp(404), B_ROBOTS: resp(404), A_PAGE: page(THIN_92)},
        renderer=renderer, secure=("a.example", "b.example"))
    f.read_robots("b.example")
    before = list(t.urls())
    out = pr.consider(f.get(A_PAGE))
    assert fake.verdicts == {B_LIB: True}
    assert out.render_allowed == [B_LIB] and out.render_aborted == []
    assert before == [B_ROBOTS]
    assert t.urls() == [B_ROBOTS, A_ROBOTS, A_PAGE]


def test_a_checked_host_whose_robots_were_not_read_is_aborted_and_not_read_mid_render():
    renderer = FakeRenderer(subrequests=[B_LIB])
    pr, f, t, _, fake = renderer_for(
        {A_ROBOTS: resp(404), A_PAGE: page(THIN_92)}, renderer=renderer,
        secure=("a.example", "b.example"))
    out = pr.consider(f.get(A_PAGE))
    assert fake.verdicts == {B_LIB: False}
    assert out.render_aborted == [(B_LIB, "robots_not_read")]
    assert B_ROBOTS not in t.urls()


def test_a_checked_host_whose_robots_disallow_the_path_is_aborted():
    renderer = FakeRenderer(subrequests=[B_LIB, "https://b.example/open.js"])
    pr, f, t, _, fake = renderer_for(
        {A_ROBOTS: resp(404), B_ROBOTS: resp(200, "User-agent: *\nDisallow: /lib.js\n"),
         A_PAGE: page(THIN_92)}, renderer=renderer, secure=("a.example", "b.example"))
    f.read_robots("b.example")
    pr.consider(f.get(A_PAGE))
    assert fake.verdicts == {B_LIB: False, "https://b.example/open.js": True}


def test_a_host_that_has_stopped_us_is_aborted():
    renderer = FakeRenderer(subrequests=[B_LIB])
    pr, f, t, _, fake = renderer_for(
        {A_ROBOTS: resp(404), B_ROBOTS: resp(404), "https://b.example/page": resp(403),
         A_PAGE: page(THIN_92)}, renderer=renderer, secure=("a.example", "b.example"))
    f.get("https://b.example/page")
    pr.consider(f.get(A_PAGE))
    assert fake.verdicts == {B_LIB: False}


@pytest.mark.parametrize("url", ["http://a.example/app.js", "ws://a.example/socket", "wss://a.example/socket",
                                 "ftp://a.example/file"])
def test_a_request_that_is_not_https_and_not_inline_is_aborted(url):
    renderer = FakeRenderer(subrequests=[url])
    pr, f, t, _, fake = renderer_for({A_ROBOTS: resp(404), A_PAGE: page(THIN_92)}, renderer=renderer)
    out = pr.consider(f.get(A_PAGE))
    assert fake.verdicts == {url: False}
    assert out.render_aborted == [(url, "not_https")]


@pytest.mark.parametrize("url", ["data:text/plain,hello", "blob:https://c.example/x"])
def test_data_and_blob_urls_make_no_request_and_pass(url):
    renderer = FakeRenderer(subrequests=[url])
    pr, f, t, _, fake = renderer_for({A_ROBOTS: resp(404), A_PAGE: page(THIN_92)}, renderer=renderer)
    out = pr.consider(f.get(A_PAGE))
    assert fake.verdicts == {url: True}
    assert out.render_aborted == [] and out.render_allowed == []
    assert t.urls() == [A_ROBOTS, A_PAGE]


@pytest.mark.parametrize("kind", ["image", "media", "font", "stylesheet"])
def test_an_image_media_font_or_stylesheet_request_is_aborted(kind):
    url = "https://a.example/asset"
    renderer = FakeRenderer(subrequests=[(url, kind)])
    pr, f, t, _, fake = renderer_for({A_ROBOTS: resp(404), A_PAGE: page(THIN_92)}, renderer=renderer)
    out = pr.consider(f.get(A_PAGE))
    assert fake.verdicts == {url: False}
    assert out.render_aborted == [(url, "resource_type")]


@pytest.mark.parametrize("kind", ["document", "script", "xhr", "fetch"])
def test_a_document_script_xhr_or_fetch_request_passes_under_the_gate(kind):
    url = "https://a.example/asset"
    renderer = FakeRenderer(subrequests=[(url, kind)])
    pr, f, t, _, fake = renderer_for({A_ROBOTS: resp(404), A_PAGE: page(THIN_92)}, renderer=renderer)
    out = pr.consider(f.get(A_PAGE))
    assert fake.verdicts == {url: True} and out.render_allowed == [url]


def test_an_image_on_another_host_is_aborted_too():
    renderer = FakeRenderer(subrequests=[(B_LIB, "image")])
    pr, f, t, _, fake = renderer_for(
        {A_ROBOTS: resp(404), B_ROBOTS: resp(404), A_PAGE: page(THIN_92)},
        renderer=renderer, secure=("a.example", "b.example"))
    f.read_robots("b.example")
    pr.consider(f.get(A_PAGE))
    assert fake.verdicts == {B_LIB: False}


def test_the_51st_same_host_request_is_aborted():
    urls = [f"https://a.example/chunk{i}.js" for i in range(51)]
    renderer = FakeRenderer(subrequests=[(u, "script") for u in urls])
    pr, f, t, _, fake = renderer_for({A_ROBOTS: resp(404), A_PAGE: page(THIN_92)}, renderer=renderer)
    out = pr.consider(f.get(A_PAGE))
    assert [fake.verdicts[u] for u in urls] == [True] * 50 + [False]
    assert out.render_aborted == [(urls[50], "request_cap")]
    assert len(out.render_allowed) == 50


def test_requests_to_other_hosts_and_aborted_ones_do_not_count_toward_the_cap():
    others = [(f"https://b.example/lib{i}.js", "script") for i in range(30)]
    images = [(f"https://a.example/pic{i}.png", "image") for i in range(30)]
    same = [(f"https://a.example/chunk{i}.js", "script") for i in range(50)]
    renderer = FakeRenderer(subrequests=others + images + same)
    pr, f, t, _, fake = renderer_for(
        {A_ROBOTS: resp(404), B_ROBOTS: resp(404), A_PAGE: page(THIN_92)},
        renderer=renderer, secure=("a.example", "b.example"))
    f.read_robots("b.example")
    out = pr.consider(f.get(A_PAGE))
    assert all(fake.verdicts[u] for u, _ in others + same)
    assert not any(fake.verdicts[u] for u, _ in images)
    assert [u for u, why in out.render_aborted if why == "request_cap"] == []


def test_the_cap_is_per_render():
    urls = [(f"https://a.example/chunk{i}.js", "script") for i in range(50)]
    renderer = FakeRenderer(subrequests=urls)
    pr, f, t, _, fake = renderer_for(
        {A_ROBOTS: resp(404), A_PAGE: page(THIN_92), "https://a.example/two": page(THIN_92)},
        renderer=renderer)
    pr.consider(f.get(A_PAGE))
    out = pr.consider(f.get("https://a.example/two"))
    assert out.render_aborted == [] and len(out.render_allowed) == 50


def test_the_next_request_to_the_host_waits_its_spacing_after_the_render_ends():
    renderer = FakeRenderer(advance=20)
    pr, f, t, clock, fake = renderer_for(
        {A_ROBOTS: resp(404), A_PAGE: page(THIN_92), "https://a.example/next": page(FULL_TEXT)},
        renderer=renderer)
    pr.consider(f.get(A_PAGE))
    ended = clock.t
    f.get("https://a.example/next")
    assert t.times("https://a.example/next")[0] - ended >= sc.MIN_DELAY


def test_the_apex_and_www_are_different_hosts_to_the_render():
    renderer = FakeRenderer(subrequests=["https://www.a.example/x.js"])
    pr, f, t, _, fake = renderer_for({A_ROBOTS: resp(404), A_PAGE: page(THIN_92)}, renderer=renderer)
    pr.consider(f.get(A_PAGE))
    assert fake.verdicts == {"https://www.a.example/x.js": False}


def test_a_render_that_meets_a_403_stops_the_host():
    pr, out, f, t, _, fake = fetched({A_PAGE: page(THIN_92), "https://a.example/other": page(FULL_TEXT)},
                                     renderer=FakeRenderer(status=403))
    assert out.outcome == "unread" and out.unread == sc.UNREAD_REFUSED_STATUS and out.status == 403
    later = f.get("https://a.example/other")
    assert later.unread == sc.UNREAD_REFUSED_STATUS
    assert t.count("https://a.example/other") == 0


def test_a_render_that_meets_a_429_stops_the_host():
    pr, out, f, t, _, fake = fetched({A_PAGE: page(THIN_92), "https://a.example/other": page(FULL_TEXT)},
                                     renderer=FakeRenderer(status=429))
    assert out.unread == sc.UNREAD_RATE_LIMITED
    assert f.get("https://a.example/other").unread == sc.UNREAD_RATE_LIMITED
    assert t.count("https://a.example/other") == 0


def test_a_render_error_is_a_failed_read_to_try_again_not_a_finding():
    pr, out, f, t, _, fake = fetched({A_PAGE: page(THIN_92)},
                                     renderer=FakeRenderer(error=sc.RenderError("browser crashed")))
    assert out.outcome == "failed" and out.unread is None
    assert "browser crashed" in out.detail


def test_a_render_with_no_response_is_a_failed_read():
    pr, out, *_ = fetched({A_PAGE: page(THIN_92)}, renderer=FakeRenderer(status=None))
    assert out.outcome == "failed"


def test_the_real_renderer_is_not_started_by_building_it():
    real = sc.PlaywrightRenderer()
    assert real._browser is None and real._playwright is None
    real.close()


def padded(name):
    return (FIXTURES / name).read_text(encoding="utf-8") + f"<p>{FULL_TEXT}</p>"


def reader_with_render(routes, renderer):
    fetcher, transport, clock = build(routes)
    renderer.clock = renderer.clock or clock
    pr = sc.PageRenderer(fetcher, renderer)
    return sc.SourceReader(fetcher, None, pr), fetcher, transport, renderer


def test_a_rendered_document_is_recorded_as_browser_render():
    renderer = FakeRenderer(pages={A_HOME: padded("site_home.html"),
                                   "https://a.example/terms": padded("site_terms.html"),
                                   "https://a.example/privacy-policy": padded("site_privacy.html")})
    rd, f, t, fake = reader_with_render(site(), renderer)
    r = rd.read("a.example")
    assert [d["method"] for d in r.documents_block()] == ["browser_render", "browser_render"]
    assert {d["read_by"] for d in r.documents_block()} == {"script"}
    assert [d["unread"] for d in r.documents_block()] == [None, None]
    assert r.documents_block()[0]["page_date"] == date(2026, 11, 4)
    assert t.urls() == [A_ROBOTS, A_HOME, "https://a.example/terms",
                        "https://a.example/privacy-policy", A_TDMREP, A_LLMS]
    assert r.js_unread == [] and not r.incomplete


def test_a_document_that_still_draws_nothing_is_unread_js_rendered_and_not_a_not_found():
    renderer = FakeRenderer(pages={A_HOME: padded("site_home.html"),
                                   "https://a.example/terms": "<html><body>Loading...</body></html>",
                                   "https://a.example/privacy-policy": padded("site_privacy.html")})
    rd, f, t, fake = reader_with_render(site(), renderer)
    r = rd.read("a.example")
    blocks = {d["kind"]: d for d in r.documents_block()}
    assert blocks["terms"]["unread"] == "js_rendered" and blocks["terms"]["method"] == "browser_render"
    assert blocks["privacy"]["unread"] is None
    assert [j["url"] for j in r.js_unread] == ["https://a.example/terms"]
    assert r.incomplete and r.not_found == []


def test_a_home_page_that_still_draws_nothing_gives_no_documents_and_no_not_found():
    renderer = FakeRenderer(html="<html><body>Loading...</body></html>")
    rd, f, t, fake = reader_with_render(site(), renderer)
    r = rd.read("a.example")
    assert r.documents == [] and r.not_found == []
    assert [j["url"] for j in r.js_unread] == [A_HOME]
    assert r.incomplete
    assert t.urls() == [A_ROBOTS, A_HOME]


def test_without_a_renderer_a_thin_page_is_read_as_before():
    rd, f, t, _ = reader(site())
    r = rd.read("a.example")
    assert {d["method"] for d in r.documents_block()} == {"http_get"}


FG = "footballguys.com"
WWW = "www.footballguys.com"
DTC = "dynastytradecalculator.com"
ARCHIVE_HOSTS = ("archive.org", "web.archive.org")
SNAPSHOT = "https://web.archive.org/web/20261101000000/https://footballguys.com/terms"
VERDICT_WORDS = {"status", "permission", "clauses", "confirmed"}


def security_routes(host, robots, *, days_ago=OLD):
    routes = {f"https://{h}/robots.txt": resp(404) for h in SERVICES + ARCHIVE_HOSTS}
    for control, body in controls_bodies().items():
        routes[sc.safe_browsing_url(control)] = raw(body)
    routes[sc.safe_browsing_url(host)] = raw(fx("sb_footballguys.txt"))
    routes[sc.IANA_BOOTSTRAP_URL] = raw(fx("iana_dns_bootstrap.json"))
    labels = host.split(".")
    for i in range(len(labels) - 1):
        routes[RDAP_BASE + ".".join(labels[i:])] = raw(rdap_body(days_ago))
    routes[f"https://{host}/robots.txt"] = robots
    routes[sc.HSTS_PRELOAD_URL + quote(host, safe="")] = raw(b'{"name": "x", "status": "unknown"}')
    return routes


def site_routes(host, **overrides):
    base = f"https://{host}"
    routes = {f"{base}/": html_page("site_home.html"), f"{base}/terms": html_page("site_terms.html"),
              f"{base}/privacy-policy": html_page("site_privacy.html"),
              f"{base}/.well-known/tdmrep.json": resp(404), f"{base}/llms.txt": resp(404)}
    routes.update(overrides)
    return routes


def wayback_answer(archive=None):
    closest = {"available": True, "url": archive, "timestamp": "20261101000000", "status": "200"}
    snapshots = {"closest": closest} if archive else {}
    return raw(json.dumps({"url": "x", "archived_snapshots": snapshots}).encode())


def wayback_routes(host, terms=None, privacy=None):
    return {sc.wayback_url(f"https://{host}/terms"): wayback_answer(terms),
            sc.wayback_url(f"https://{host}/privacy-policy"): wayback_answer(privacy)}


class E2E:
    def __init__(self, tmp_path, routes, *, confirmed=(), renderer=None, dns=None):
        self.clock = Clock()
        self.transport = FakeTransport(routes, self.clock)
        self.fetcher = sc.Fetcher(self.transport, clock=self.clock, sleep=self.clock.sleep,
                                  today=lambda: TODAY)
        self.dns = dns or Dns()
        self.tls = Tls()
        self.out = tmp_path / "source_checks"
        self.policies = tmp_path / "policies"
        self.run = sc.build_run(self.fetcher, resolver=self.dns, tls_probe=self.tls,
                                confirmed=set(confirmed), renderer=renderer, out_dir=self.out,
                                captures_root=self.policies)

    def go(self, *hosts):
        return self.run.run(list(hosts))

    def requests_to(self, host):
        return [u for u in self.transport.urls() if urlsplit(u).hostname == host]

    def body_of(self, url):
        return self.transport.routes[url][0].body


def full_renderer(host):
    return FakeRenderer(pages={f"https://{host}/": padded("site_home.html"),
                               f"https://{host}/terms": padded("site_terms.html"),
                               f"https://{host}/privacy-policy": padded("site_privacy.html")})


def load(output):
    return json.loads(output.path.read_text(encoding="utf-8"))


def words_in(value):
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(key)
            found |= words_in(item)
    elif isinstance(value, list):
        for item in value:
            found |= words_in(item)
    return found


def fg_routes(host=FG, robots=None, **site_overrides):
    routes = security_routes(host, robots or resp(404, strict_transport_security="max-age=86400"))
    routes.update(site_routes(host, **site_overrides))
    routes.update(wayback_routes(host, terms=SNAPSHOT))
    return routes


def test_a_capture_is_named_by_read_date_and_hash_and_its_file_hash_is_the_recorded_one(tmp_path):
    world = E2E(tmp_path, fg_routes())
    payload = load(world.go(FG)[0])
    docs = payload["terms"]["documents"]
    files = {d["url"]: d["capture_file"] for d in payload["run"]["documents_read"]}
    for doc in docs:
        sent = world.body_of(doc["url"])
        saved = (world.policies / files[doc["url"]]).read_bytes()
        assert saved == sent
        assert hashlib.sha256(saved).hexdigest() == doc["capture_sha256"]
        assert files[doc["url"]] == f"{FG}/{TODAY.isoformat()}_{doc['capture_sha256']}.html"
    assert len(docs) == 2 and len({d["capture_sha256"] for d in docs}) == 2


def test_a_rendered_document_is_captured_as_the_rendered_html(tmp_path):
    fake = FakeRenderer(pages={f"https://{FG}/": padded("site_home.html"),
                               f"https://{FG}/terms": padded("site_terms.html"),
                               f"https://{FG}/privacy-policy": padded("site_privacy.html")})
    world = E2E(tmp_path, fg_routes(), renderer=fake)
    payload = load(world.go(FG)[0])
    terms = payload["terms"]["documents"][0]
    rendered = padded("site_terms.html").encode("utf-8")
    assert terms["method"] == "browser_render"
    assert terms["capture_sha256"] == hashlib.sha256(rendered).hexdigest()
    assert terms["capture_sha256"] != hashlib.sha256(world.body_of(terms["url"])).hexdigest()
    saved = [p for p in (world.policies / FG).iterdir() if terms["capture_sha256"] in p.name]
    assert len(saved) == 1 and saved[0].read_bytes() == rendered


def test_a_capture_is_not_rewritten_when_the_same_bytes_are_read_again(tmp_path):
    first = sc.write_capture(tmp_path, "a.example", TODAY, b"same", "html")
    path = tmp_path / first[1]
    stamp = path.stat().st_mtime_ns
    assert sc.write_capture(tmp_path, "a.example", TODAY, b"same", "html") == first
    assert path.stat().st_mtime_ns == stamp
    assert first[0] == hashlib.sha256(b"same").hexdigest()


def test_a_wayback_miss_goes_on_the_missing_list_and_makes_no_save_call(tmp_path):
    routes = fg_routes()
    routes.update(wayback_routes(FG))
    world = E2E(tmp_path, routes)
    out = world.go(FG)[0]
    payload = load(out)
    terms_url, privacy_url = f"https://{FG}/terms", f"https://{FG}/privacy-policy"
    assert out.missing_path is not None and out.missing_path.parent == out.path.parent
    assert out.missing_path.read_text(encoding="utf-8").splitlines() == [terms_url, privacy_url]
    assert payload["run"]["missing_archive"] == [terms_url, privacy_url]
    assert payload["run"]["missing_list"] == out.missing_path.name
    assert [d["archive"] for d in payload["terms"]["documents"]] == [None, None]
    assert not any("/save/" in u for u in world.transport.urls())
    assert world.requests_to("web.archive.org") == []
    assert world.requests_to("archive.org")[0] == "https://archive.org/robots.txt"


def test_a_wayback_copy_is_recorded_and_not_listed_as_missing(tmp_path):
    world = E2E(tmp_path, fg_routes())
    out = world.go(FG)[0]
    docs = load(out)["terms"]["documents"]
    assert docs[0]["archive"] == SNAPSHOT and docs[1]["archive"] is None
    assert out.missing_path.read_text(encoding="utf-8") == f"https://{FG}/privacy-policy\n"


def test_a_wayback_lookup_that_failed_is_listed_as_failed_not_as_missing(tmp_path):
    routes = fg_routes()
    routes[sc.wayback_url(f"https://{FG}/privacy-policy")] = raw(b"", 500)
    world = E2E(tmp_path, routes)
    out = world.go(FG)[0]
    payload = load(out)
    assert out.missing_path is None and "missing_list" not in payload["run"]
    assert payload["run"]["missing_archive"] == []
    assert [f["url"] for f in payload["run"]["archive_lookup_failed"]] == [f"https://{FG}/privacy-policy"]


@pytest.mark.parametrize("body,kind", [
    (json.dumps({"archived_snapshots": {}}), "none"),
    (json.dumps({"archived_snapshots": {"closest": {"available": False}}}), "none"),
    (json.dumps({"archived_snapshots": {"closest": {"available": True, "url": SNAPSHOT}}}), "copy"),
    (json.dumps({"archived_snapshots": {"closest": {
        "available": True, "url": "http://web.archive.org/web/2026/https://a.example/"}}}), "copy"),
    (json.dumps({"archived_snapshots": {"closest": {"available": True, "url": "https://evil.example/"}}}),
     "unknown"),
    (json.dumps({"other": 1}), "unknown"), ("not json", "unknown"), ("[]", "unknown")])
def test_the_wayback_answer_is_read_strictly(body, kind):
    assert sc.parse_wayback(body.encode()).kind == kind


def test_save_saves_only_the_listed_urls_through_the_gate(tmp_path):
    listed = [f"https://{FG}/terms", f"https://{FG}/privacy-policy"]
    approved = tmp_path / "approved.txt"
    approved.write_text("# approved by the owner\n" + "\n".join(listed) + "\n\n" + listed[0]
                        + "\nhttp://plain.example/x\nftp://old.example/y\n", encoding="utf-8")
    routes = {"https://web.archive.org/robots.txt": resp(404),
              sc.SAVE_URL + listed[0]: resp(200, "<html>archived</html>", content_type="text/html"),
              sc.SAVE_URL + listed[1]: resp(429, "", retry_after="5000")}
    world = E2E(tmp_path, routes)
    path, payload = sc.run_save(world.fetcher, approved, world.out)
    assert world.transport.urls() == ["https://web.archive.org/robots.txt", sc.SAVE_URL + listed[0],
                                      sc.SAVE_URL + listed[1]]
    assert [(s["url"], s["result"]) for s in payload["saved"]] == [
        (listed[0], "saved"), (listed[1], "unread")]
    assert payload["rejected"] == ["http://plain.example/x", "ftp://old.example/y"]
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(
        json.dumps(payload, default=str))
    assert not world.requests_to(FG) and not world.requests_to("plain.example")


def test_save_goes_through_the_gate_and_carries_the_user_agent(tmp_path):
    approved = tmp_path / "approved.txt"
    approved.write_text(f"https://{FG}/terms\n", encoding="utf-8")
    routes = {"https://web.archive.org/robots.txt": resp(200, "User-agent: *\nDisallow: /save/\n")}
    world = E2E(tmp_path, routes)
    _, payload = sc.run_save(world.fetcher, approved, world.out)
    assert payload["saved"][0]["result"] == "unread"
    assert "robots_blocks_agent" in payload["saved"][0]["detail"]
    assert world.transport.urls() == ["https://web.archive.org/robots.txt"]
    for _, headers, _ in world.transport.calls:
        assert headers == {"User-Agent": UA}


def test_a_check_never_saves_and_a_save_never_checks(tmp_path):
    world = E2E(tmp_path, fg_routes())
    world.go(FG)
    assert not any(u.startswith(sc.SAVE_URL) for u in world.transport.urls())
    approved = tmp_path / "approved.txt"
    approved.write_text(f"https://{FG}/terms\n", encoding="utf-8")
    routes = {"https://web.archive.org/robots.txt": resp(404), sc.SAVE_URL + f"https://{FG}/terms": resp(200)}
    other = E2E(tmp_path / "other", routes)
    sc.run_save(other.fetcher, approved, other.out)
    assert not any("safebrowsing" in u or "rdap" in u or u.startswith(f"https://{FG}") for u in other.transport.urls())
    assert other.dns.calls == [] and other.tls.calls == []


def test_the_output_never_holds_status_permission_clauses_or_confirmed(tmp_path):
    world = E2E(tmp_path, {**fg_routes(), **security_routes(DTC, resp(403))})
    for out in world.go(FG, DTC):
        payload = load(out)
        assert not words_in(payload) & VERDICT_WORDS
        assert set(payload) <= {"host", "run_date", "security", "terms", "run"}
        assert set(payload["security"]) == {"checked", "host", "controls", "safe_browsing", "dns",
                                            "tls", "hsts", "registered", "flags"}
        if "terms" in payload:
            assert set(payload["terms"]) == {"checked", "documents", "not_found", "signals", "operator"}
            assert payload["terms"]["operator"] is None
            for doc in payload["terms"]["documents"]:
                assert doc["read_by"] == "script"


def test_the_writer_refuses_a_verdict_key_and_writes_nothing(tmp_path):
    target = tmp_path / "x.json"
    with pytest.raises(ValueError, match="verdict keys"):
        sc.write_json(target, {"terms": [{"status": "permitted"}]})
    assert not target.exists()


def test_a_run_leaves_docs_sources_yml_byte_for_byte_unchanged(tmp_path, capsys):
    before = sc.MANIFEST.read_bytes()
    world = E2E(tmp_path, fg_routes())
    world.go(FG)
    code = sc.main(["check", "--host", FG], fetcher=E2E(tmp_path / "again", fg_routes()).fetcher,
                   resolver=Dns(), tls_probe=Tls(), confirmed=set(), renderer=full_renderer(FG),
                   out_dir=tmp_path / "cli_out", captures_root=tmp_path / "cli_caps")
    assert code == 0
    assert sc.MANIFEST.read_bytes() == before
    assert not any(p.suffix in (".yml", ".yaml") for p in tmp_path.rglob("*"))


def test_footballguys_shaped_run_is_a_full_record(tmp_path):
    world = E2E(tmp_path, fg_routes())
    out = world.go(FG)[0]
    payload = load(out)
    assert out.path.parent == world.out and out.path.name == f"{FG}_{TODAY.isoformat()}.json"
    security = payload["security"]
    assert security["host"] == FG and security["flags"] == [] and security["dns"] == "resolves"
    assert security["controls"] == {"malware": 2, "phishing": 2, "unwanted": 2, "shape_ok": True}
    assert security["safe_browsing"] == {"via": "transparency_report", "code": 1,
                                         "google_scan": "2026-11-08"}
    assert security["tls"]["ok"] and security["hsts"] == {"max_age": 86400, "preloaded": False}
    assert security["registered"] == "1999-07-09" and security["checked"] == TODAY.isoformat()
    terms = payload["terms"]
    assert terms["checked"] == TODAY.isoformat() and terms["not_found"] == []
    assert [(d["kind"], d["reached_from"]["place"], d["reached_from"]["link_text"])
            for d in terms["documents"]] == [("terms", "footer", "Terms of Service"),
                                             ("privacy", "footer", "Privacy Policy")]
    for doc in terms["documents"]:
        assert doc["read"] == TODAY.isoformat() and doc["read_by"] == "script"
        assert doc["method"] == "http_get" and doc["unread"] is None
        assert len(doc["capture_sha256"]) == 64
    assert terms["documents"][0]["page_date"] == "2026-11-04"
    assert terms["documents"][0]["archive"] == SNAPSHOT and terms["documents"][1]["archive"] is None
    robots = terms["signals"]["robots"]
    assert robots["code"] == 404 and robots["url"] == f"https://{FG}/robots.txt"
    assert robots["blocks_agent"] is False and robots["claude_groups"] == []
    assert terms["signals"]["tdmrep"] == {"well_known": 404, "header": None, "meta": None}
    run = payload["run"]
    assert run["read"] == "read" and run["incomplete"] is False
    assert run["failed"] == run["stopped"] == run["pending"] == run["js_unread"] == []
    assert run["copyright_line"] == "Copyright © 2022 Example Fantasy LLC. All Rights Reserved."
    assert run["page_signals"]["url"] == f"https://{FG}/"
    assert set(run["security_checks"]) == {FG} and run["security_checks"][FG]["block"] == security
    assert len(run["captures"]) == 2
    assert world.requests_to(FG) == [f"https://{FG}/robots.txt", f"https://{FG}/",
                                     f"https://{FG}/terms", f"https://{FG}/privacy-policy",
                                     f"https://{FG}/.well-known/tdmrep.json", f"https://{FG}/llms.txt"]
    for _, headers, _ in world.transport.calls:
        assert headers == {"User-Agent": UA}


def test_dtc_shaped_run_is_one_request_and_a_recorded_stop(tmp_path):
    routes = security_routes(DTC, resp(403, strict_transport_security="max-age=63072000"))
    world = E2E(tmp_path, routes)
    out = world.go(DTC)[0]
    payload = load(out)
    assert world.requests_to(DTC) == [f"https://{DTC}/robots.txt"]
    assert payload["security"]["flags"] == [] and payload["security"]["hsts"]["max_age"] == 63072000
    terms = payload["terms"]
    assert terms["signals"]["robots"]["code"] == 403
    assert terms["documents"] == [] and terms["not_found"] == []
    stopped = payload["run"]["stopped"]
    assert [(s["place"], s["unread"]) for s in stopped] == [("entry", "refused_status")]
    assert payload["run"]["incomplete"] is True and payload["run"]["captures"] == []
    assert out.missing_path is None


def test_two_hosts_in_one_run_go_one_host_at_a_time(tmp_path):
    routes = {**fg_routes(), **security_routes(DTC, resp(403))}
    world = E2E(tmp_path, routes)
    outputs = world.go(FG, DTC)
    order = [urlsplit(u).hostname for u in world.transport.urls() if urlsplit(u).hostname in (FG, DTC)]
    assert order == [FG] * 6 + [DTC]
    assert [o.host for o in outputs] == [FG, DTC]
    assert outputs[0].path.name != outputs[1].path.name
    assert world.dns.calls == [FG, DTC]
    assert [load(o)["host"] for o in outputs] == [FG, DTC]


def test_a_host_named_twice_is_run_once(tmp_path):
    world = E2E(tmp_path, fg_routes())
    assert len(world.go(FG, FG.upper())) == 1
    assert world.dns.calls == [FG]


def test_a_second_run_on_the_same_day_never_overwrites_the_first(tmp_path):
    world = E2E(tmp_path, fg_routes())
    first = world.go(FG)[0]
    second = E2E(tmp_path, fg_routes()).go(FG)[0]
    assert first.path.name == f"{FG}_{TODAY.isoformat()}.json"
    assert second.path.name == f"{FG}_{TODAY.isoformat()}_2.json"
    assert first.path.exists() and second.path.exists()


def test_a_failed_read_leaves_not_found_empty_and_is_listed_as_failed(tmp_path):
    world = E2E(tmp_path, fg_routes(**{f"https://{FG}/": sc.TransportError("connection reset")}))
    out = world.go(FG)[0]
    payload = load(out)
    assert payload["terms"]["documents"] == [] and payload["terms"]["not_found"] == []
    failed = payload["run"]["failed"]
    assert [(f["url"], f["place"]) for f in failed] == [(f"https://{FG}/", "entry")]
    assert "connection reset" in failed[0]["detail"]
    assert payload["run"]["incomplete"] is True
    assert payload["run"]["captures"] == [] and out.missing_path is None
    assert not any(u.startswith("https://archive.org/wayback") for u in world.transport.urls())


def test_a_young_host_writes_only_its_security_block_and_nothing_is_read(tmp_path):
    routes = {**fg_routes(), **security_routes("younghost.com", resp(404), days_ago=300)}
    routes.update(site_routes("younghost.com"))
    world = E2E(tmp_path, routes)
    out = world.go("younghost.com")[0]
    payload = load(out)
    assert out.read == "held" and set(payload) == {"host", "run_date", "security", "run"}
    assert payload["security"]["flags"] == ["young_domain"]
    assert payload["security"]["registered"] == (TODAY - timedelta(days=300)).isoformat()
    assert payload["security"]["tls"] is None and payload["security"]["hsts"] is None
    assert payload["run"]["read"] == "held" and "captures" not in payload["run"]
    assert world.requests_to("younghost.com") == [] and world.tls.calls == []
    assert out.missing_path is None


def test_a_young_host_is_read_in_the_next_run_once_the_manifest_confirms_it(tmp_path):
    routes = {**security_routes("younghost.com", resp(404), days_ago=300), **site_routes("younghost.com")}
    routes.update(wayback_routes("younghost.com"))
    held = E2E(tmp_path, routes).go("younghost.com")[0]
    assert load(held)["run"]["read"] == "held"
    world = E2E(tmp_path, routes, confirmed={"younghost.com"})
    payload = load(world.go("younghost.com")[0])
    assert payload["run"]["read"] == "read"
    assert [d["kind"] for d in payload["terms"]["documents"]] == ["terms", "privacy"]
    assert payload["security"]["flags"] == ["young_domain"]
    assert world.requests_to("younghost.com")[0] == "https://younghost.com/robots.txt"


def test_a_host_whose_check_could_not_finish_is_listed_as_failed_with_no_block(tmp_path):
    dns = Dns(missing={FG}, code=getattr(socket, "EAI_AGAIN", -3))
    world = E2E(tmp_path, fg_routes(), dns=dns)
    out = world.go(FG)[0]
    payload = load(out)
    assert out.read == "check_failed" and payload["security"] is None
    record = payload["run"]["security_checks"][FG]
    assert record["block"] is None and record["failed"].startswith("dns:")
    assert world.requests_to(FG) == []


def hop_routes(*, www_days=OLD, robots_location=f"https://{WWW}/robots.txt"):
    routes = security_routes(WWW, resp(404, strict_transport_security="max-age=86400"), days_ago=www_days)
    routes.update(security_routes(FG, resp(301, location=robots_location)))
    routes[f"https://{FG}/"] = resp(301, location=f"https://{WWW}/")
    routes[f"https://{FG}/.well-known/tdmrep.json"] = resp(301, location=f"https://{WWW}/.well-known/tdmrep.json")
    routes[f"https://{FG}/llms.txt"] = resp(301, location=f"https://{WWW}/llms.txt")
    routes.update(site_routes(WWW))
    routes.update(wayback_routes(WWW, terms=SNAPSHOT))
    return routes


def test_an_apex_robots_redirect_to_a_www_host_that_clears_is_followed(tmp_path):
    world = E2E(tmp_path, hop_routes())
    out = world.go(FG)[0]
    payload = load(out)
    assert {FG, WWW} <= world.fetcher.secure_hosts
    assert world.dns.calls == [FG, WWW] and world.tls.calls == [FG, WWW]
    urls = world.transport.urls()
    assert urls.index(sc.safe_browsing_url(WWW)) < urls.index(f"https://{WWW}/robots.txt")
    assert payload["security"]["host"] == WWW and payload["security"]["flags"] == []
    assert set(payload["run"]["security_checks"]) == {FG, WWW}
    assert payload["run"]["security_checks"][FG]["block"]["host"] == FG
    assert payload["run"]["security_checks"][WWW]["block"] == payload["security"]
    robots = payload["terms"]["signals"]["robots"]
    assert robots["url"] == f"https://{WWW}/robots.txt" and robots["code"] == 404
    docs = payload["terms"]["documents"]
    assert [d["kind"] for d in docs] == ["terms", "privacy"]
    assert {d["reached_from"]["page"] for d in docs} == {f"https://{WWW}/"}
    assert docs[0]["url"] == f"https://{WWW}/terms"
    assert payload["run"]["failed"] == [] and payload["run"]["incomplete"] is False


def test_an_apex_robots_redirect_to_a_www_host_that_is_held_stops_the_read_with_no_request(tmp_path):
    world = E2E(tmp_path, hop_routes(www_days=300))
    out = world.go(FG)[0]
    payload = load(out)
    assert world.requests_to(WWW) == []
    assert WWW not in world.tls.calls and WWW not in world.fetcher.secure_hosts
    held = payload["run"]["security_checks"][WWW]
    assert held["held"] is True and held["block"]["flags"] == ["young_domain"]
    assert held["block"]["tls"] is None
    assert payload["terms"]["documents"] == [] and payload["terms"]["not_found"] == []
    failed = payload["run"]["failed"]
    assert failed and all(WWW in f["detail"] for f in failed)
    assert payload["run"]["incomplete"] is True
    assert payload["security"]["host"] == FG
    assert not any(u.startswith("https://archive.org/wayback") for u in world.transport.urls())


def test_an_apex_robots_redirect_to_a_host_that_fails_its_check_stops_the_read(tmp_path):
    routes = hop_routes()
    routes[sc.safe_browsing_url(WWW)] = raw(fx("sb_control_malware.txt"))
    world = E2E(tmp_path, routes)
    payload = load(world.go(FG)[0])
    assert world.requests_to(WWW) == []
    assert WWW not in world.tls.calls
    assert payload["run"]["security_checks"][WWW]["block"]["flags"] == ["sb_unsafe"]
    assert payload["run"]["security_checks"][WWW]["held"] is False
    assert payload["terms"]["documents"] == [] and payload["run"]["failed"]


def test_a_redirect_to_a_different_site_is_stopped_with_no_check_of_that_site(tmp_path):
    routes = security_routes(FG, resp(301, location="https://other.example/robots.txt"))
    world = E2E(tmp_path, routes)
    payload = load(world.go(FG)[0])
    assert "other.example" not in world.dns.calls and world.requests_to("other.example") == []
    assert set(payload["run"]["security_checks"]) == {FG}
    assert payload["terms"]["documents"] == [] and payload["terms"]["not_found"] == []
    assert payload["run"]["failed"] and "other.example" in payload["run"]["failed"][0]["detail"]


def test_a_page_redirect_within_the_site_runs_the_hop_hosts_own_check_first(tmp_path):
    routes = security_routes(FG, resp(404, strict_transport_security="max-age=86400"))
    routes.update(security_routes(WWW, resp(404)))
    routes.update(site_routes(FG, **{f"https://{FG}/terms": resp(301, location=f"https://{WWW}/terms")}))
    routes[f"https://{WWW}/terms"] = html_page("site_terms.html")
    routes.update(wayback_routes(FG))
    routes[sc.wayback_url(f"https://{FG}/terms")] = wayback_answer()
    world = E2E(tmp_path, routes)
    payload = load(world.go(FG)[0])
    urls = world.transport.urls()
    assert urls.index(sc.safe_browsing_url(WWW)) < urls.index(f"https://{WWW}/robots.txt") \
        < urls.index(f"https://{WWW}/terms")
    assert set(payload["run"]["security_checks"]) == {FG, WWW}
    assert payload["terms"]["documents"][0]["kind"] == "terms"


def test_the_hop_hook_is_not_called_for_a_host_that_already_passed(tmp_path):
    world = E2E(tmp_path, hop_routes())
    world.go(FG)
    assert world.dns.calls.count(WWW) == 1


def test_the_cli_takes_check_with_repeatable_hosts_and_save_with_a_list():
    parser = sc.build_parser()
    args = parser.parse_args(["check", "--host", "Footballguys.com", "--host", DTC])
    assert args.command == "check" and args.host == [FG, DTC]
    args = parser.parse_args(["save", "--list", "approved.txt"])
    assert args.command == "save" and args.list_file == Path("approved.txt")


@pytest.mark.parametrize("argv", [
    [], ["check"], ["save"], ["check", "--host", "https://footballguys.com/terms"],
    ["check", "--host", "footballguys.com/terms"], ["check", "--host", "localhost"],
    ["check", "--host", "a b.example"], ["check", "--all"], ["season"]])
def test_the_cli_refuses_anything_but_bare_hosts_and_a_list(argv):
    with pytest.raises(SystemExit) as exc:
        sc.build_parser().parse_args(argv)
    assert exc.value.code == 2


def test_the_cli_runs_two_hosts_and_reports_the_files(tmp_path, capsys):
    routes = {**fg_routes(), **security_routes(DTC, resp(403))}
    world = E2E(tmp_path, routes)
    code = sc.main(["check", "--host", FG, "--host", DTC], fetcher=world.fetcher, resolver=world.dns,
                   tls_probe=world.tls, confirmed=set(), renderer=full_renderer(FG),
                   out_dir=world.out, captures_root=world.policies)
    printed = capsys.readouterr().out
    assert code == 0
    assert sorted(p.name for p in world.out.glob("*.json")) == [
        f"{DTC}_{TODAY.isoformat()}.json", f"{FG}_{TODAY.isoformat()}.json"]
    assert f"{FG}: read" in printed and f"{DTC}: read" in printed
    assert "missing archive list" in printed


def test_the_cli_returns_one_when_a_check_could_not_finish(tmp_path, capsys):
    dns = Dns(missing={FG}, code=getattr(socket, "EAI_AGAIN", -3))
    world = E2E(tmp_path, fg_routes(), dns=dns)
    code = sc.main(["check", "--host", FG], fetcher=world.fetcher, resolver=dns, tls_probe=world.tls,
                   confirmed=set(), renderer=full_renderer(FG), out_dir=world.out,
                   captures_root=world.policies)
    assert code == 1 and "check_failed" in capsys.readouterr().out


def test_the_cli_save_reads_the_list_and_writes_a_result_file(tmp_path, capsys):
    approved = tmp_path / "approved.txt"
    approved.write_text(f"https://{FG}/terms\n", encoding="utf-8")
    routes = {"https://web.archive.org/robots.txt": resp(404),
              sc.SAVE_URL + f"https://{FG}/terms": resp(200, "ok", content_type="text/html")}
    world = E2E(tmp_path, routes)
    code = sc.main(["save", "--list", str(approved)], fetcher=world.fetcher, out_dir=world.out)
    assert code == 0 and "1 listed URL(s)" in capsys.readouterr().out
    assert [p.name for p in world.out.glob("save_*.json")] == [f"save_{TODAY.isoformat()}.json"]
