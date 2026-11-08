import socket
import sys
from datetime import date
from pathlib import Path

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


def test_a_403_on_a_later_page_is_unread_for_that_read_only():
    f, t, _ = build({A_ROBOTS: resp(404), A_TERMS: resp(403),
                     "https://a.example/privacy": resp(200, "p")})
    assert f.get(A_TERMS).unread == sc.UNREAD_REFUSED_STATUS
    assert f.get("https://a.example/privacy").outcome == "ok"
    assert t.count(A_TERMS) == 1


def test_retry_after_parses_seconds_and_dates():
    assert sc.retry_after_seconds({"retry-after": "120"}) == 120.0
    assert sc.retry_after_seconds({}) is None
    assert sc.retry_after_seconds({"retry-after": "soon"}) is None
    assert sc.retry_after_seconds({"retry-after": "Wed, 21 Oct 2015 07:28:00 GMT"}) == 0.0
