import socket
import sys
from datetime import date, timedelta
from pathlib import Path
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
