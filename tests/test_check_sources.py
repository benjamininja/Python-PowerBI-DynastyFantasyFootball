import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_sources as cs

TODAY = date(2026, 11, 7)

DOC = {
    "kind": "terms",
    "url": "https://example.com/terms",
    "reached_from": {"page": "https://example.com/", "place": "footer", "link_text": "Terms of Service"},
    "read": date(2026, 11, 7),
    "page_date": None,
    "read_by": "agent",
    "method": "http_get",
    "unread": None,
    "archive": None,
    "capture_sha256": None,
    "clauses": [{"section": "4", "topic": "automated access", "verbatim": True, "quote": "No robots."}],
}
SIGNALS = {"robots": {"url": "https://example.com/robots.txt", "code": 404, "read": date(2026, 11, 7)}}
CHECKED_TERMS = {
    "status": "unresolved",
    "checked": date(2026, 11, 7),
    "checked_in": "#1",
    "how": ["robots.txt allows all"],
    "documents": [DOC],
    "not_found": [],
    "signals": SIGNALS,
    "operator": None,
    "licence": "none",
    "attribution": None,
    "share_alike": False,
    "upstream": [],
    "access": "public_get",
    "permission": None,
}
LEGACY_TERMS = {
    **{k: v for k, v in CHECKED_TERMS.items() if k not in ("documents", "not_found", "signals", "operator")},
    "evidence": [{"url": "https://example.com/robots.txt", "archive": None}],
}
NEVER_TERMS = {"status": "unresolved", "checked": None, "access": "public_get"}
SECURITY = {
    "checked": date(2026, 11, 7),
    "host": "example.com",
    "controls": {"malware": 2, "phishing": 2, "unwanted": 2, "shape_ok": True},
    "safe_browsing": {"via": "transparency_report", "code": 1, "google_scan": date(2026, 11, 6)},
    "dns": "resolves",
    "tls": {"ok": True, "issuer": "CA", "not_after": date(2027, 2, 1), "version": "TLSv1.3"},
    "hsts": {"max_age": 31536000, "preloaded": False},
    "registered": date(2010, 1, 1),
    "flags": [],
    "confirmed": {"by": "owner", "date": date(2026, 11, 7)},
}


def _src(status, terms=None, sid="x", security=SECURITY):
    s = {
        "id": sid,
        "name": "X",
        "status": status,
        "locator": "l",
        "purpose": "p",
        "auth": "a",
        "cadence": "c",
        "feeds": [],
        "match": [],
        "terms": dict(CHECKED_TERMS) if terms is None else terms,
    }
    if security is not None:
        s["security"] = dict(security)
    return s


def _errors(capsys):
    return [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("FAIL")]


def test_rejected_status_is_valid(capsys):
    assert cs.validate({"sources": [_src("rejected")]}, TODAY) == 0


def test_unknown_status_fails(capsys):
    assert cs.validate({"sources": [_src("maybe")]}, TODAY) == 1
    assert "status must be one of" in capsys.readouterr().out


def test_rejected_gets_its_own_table():
    data = {"sources": [_src("rejected")]}
    assert "**X**" in cs._table(data["sources"], "rejected")
    assert "**X**" not in cs._table(data["sources"], "planned")


def test_source_without_terms_block_fails(capsys):
    s = _src("planned")
    del s["terms"]
    assert cs.validate({"sources": [s]}, TODAY) == 1
    assert "missing required field 'terms'" in capsys.readouterr().out


def test_checked_block_and_never_checked_block_are_valid(capsys):
    data = {"sources": [_src("planned", sid="a"), _src("planned", dict(NEVER_TERMS), sid="b")]}
    assert cs.validate(data, TODAY) == 0


def test_bad_terms_blocks_fail(capsys):
    bad = {
        "bad status": {**NEVER_TERMS, "status": "cleared"},
        "bad access": {**NEVER_TERMS, "access": "scrape"},
        "no access": {"status": "unresolved", "checked": None},
        "unknown field": {**NEVER_TERMS, "notes": "x"},
        "string date": {**CHECKED_TERMS, "checked": "2026-11-07"},
        "verdict with no date": {**NEVER_TERMS, "status": "rejected"},
        "checked without any record": {k: v for k, v in CHECKED_TERMS.items() if k not in ("documents", "not_found")},
        "checked without how": {**CHECKED_TERMS, "how": []},
        "evidence not a mapping": {**LEGACY_TERMS, "evidence": ["https://example.com"]},
        "share_alike not a bool": {**CHECKED_TERMS, "share_alike": "no"},
        "permission without asked date": {**CHECKED_TERMS, "permission": {"given": None}},
    }
    for label, terms in bad.items():
        assert cs.validate({"sources": [_src("planned", terms)]}, TODAY) == 1, label
        assert _errors(capsys), label


def test_next_check_is_the_first_of_the_next_check_month():
    assert cs.next_check({"checked": date(2026, 11, 7)}) == date(2027, 5, 1)
    assert cs.next_check({"checked": date(2027, 5, 10)}) == date(2028, 5, 1)
    assert cs.next_check({"checked": date(2027, 4, 30)}) == date(2027, 5, 1)
    assert cs.next_check({"checked": date(2027, 5, 1)}) == date(2028, 5, 1)
    assert cs.next_check({"checked": date(2026, 1, 2)}) == date(2026, 5, 1)
    assert cs.next_check({"checked": None}) is None


def test_next_check_follows_the_cfg_month(monkeypatch):
    monkeypatch.setattr(cs.CFG, "source_check_month", 9)
    assert cs.next_check({"checked": date(2026, 11, 7)}) == date(2027, 9, 1)
    assert cs.next_check({"checked": date(2026, 8, 31)}) == date(2026, 9, 1)
    assert cs.security_next_check({"checked": date(2026, 9, 1)}) == date(2027, 9, 1)


def test_cfg_default_check_month_is_may():
    assert cs.etl.LeagueConfig().source_check_month == 5


def test_security_next_check_uses_the_same_rule():
    assert cs.security_next_check({"checked": date(2026, 11, 7)}) == date(2027, 5, 1)
    assert cs.security_next_check({"checked": None}) is None
    assert cs.security_next_check(None) is None


def test_source_past_next_check_is_one_advisory_and_no_failure(capsys):
    stale = dict(CHECKED_TERMS, checked=date(2025, 5, 6))
    data = {"sources": [_src("planned", stale)]}
    assert cs.validate(data, TODAY) == 0
    out = capsys.readouterr().out
    assert out.count("ADVISORY") == 1
    assert "1 source(s) due a terms check (1 past next_check, 0 never checked)" in out
    assert "FAIL" not in out
    assert cs.terms_due(data["sources"], TODAY) == {"never": [], "past": ["x"]}


def test_source_on_its_next_check_date_is_not_yet_due():
    s = _src("planned", dict(CHECKED_TERMS, checked=date(2025, 5, 7)))
    assert cs.terms_due([s], date(2026, 5, 1)) == {"never": [], "past": []}
    assert cs.terms_due([s], date(2026, 5, 2)) == {"never": [], "past": ["x"]}


def test_never_checked_source_is_one_advisory_and_no_failure(capsys):
    data = {"sources": [_src("planned", dict(NEVER_TERMS))]}
    assert cs.validate(data, TODAY) == 0
    out = capsys.readouterr().out
    assert out.count("ADVISORY") == 1
    assert "1 source(s) due a terms check (0 past next_check, 1 never checked)" in out
    assert "FAIL" not in out
    assert cs.terms_due(data["sources"], TODAY) == {"never": ["x"], "past": []}


def test_many_due_sources_still_print_one_advisory_line(capsys):
    stale = dict(CHECKED_TERMS, checked=date(2026, 1, 1))
    data = {
        "sources": [
            _src("planned", dict(NEVER_TERMS), sid="a"),
            _src("planned", dict(NEVER_TERMS), sid="b"),
            _src("planned", stale, sid="c"),
            _src("planned", dict(CHECKED_TERMS), sid="d"),
        ]
    }
    assert cs.validate(data, TODAY) == 0
    out = capsys.readouterr().out
    assert out.count("ADVISORY") == 1
    assert "3 source(s) due a terms check (1 past next_check, 2 never checked)" in out
    assert cs.terms_due_count(data, TODAY) == 3


def test_no_advisory_when_nothing_is_due(capsys):
    assert cs.validate({"sources": [_src("planned")]}, TODAY) == 0
    assert "ADVISORY" not in capsys.readouterr().out
    assert cs.terms_advisory({"sources": [_src("planned")]}, TODAY) is None


def test_terms_table_lists_every_source_with_its_dates():
    table = cs._terms_table([_src("planned", sid="a"), _src("planned", dict(NEVER_TERMS), sid="b")])
    rows = table.splitlines()[2:]
    assert len(rows) == 2
    assert "2026-11-07" in rows[0] and "2027-05-01" in rows[0]
    assert "never" in rows[1]


def test_real_manifest_every_source_has_a_valid_terms_block():
    data = cs.load_yaml()
    sources = data["sources"]
    assert sources
    for s in sources:
        assert cs.check_terms(s) == [], s["id"]
        assert s.get("terms"), s["id"]


def test_real_manifest_starting_values():
    by_id = {s["id"]: s["terms"] for s in cs.load_yaml()["sources"]}
    for sid, status in {
        "pff": "rejected",
        "fantasypros": "rejected",
        "keeptradecut": "rejected",
        "nflverse": "permitted",
        "walterfootball": "unresolved",
        "draftsharks": "unresolved",
    }.items():
        assert by_id[sid]["status"] == status, sid
        assert by_id[sid]["checked"] == date(2026, 11, 7), sid
    for sid, access in {
        "fantrax_playerstats_grid": "owner_login",
        "fantrax_inseason_scoring": "owner_login",
        "fantrax_public_fxea": "public_get",
        "fantrax_public_rosters": "public_get",
    }.items():
        assert by_id[sid]["status"] == "unresolved", sid
        assert by_id[sid]["checked"] == date(2026, 11, 7), sid
        assert by_id[sid]["access"] == access, sid
    fantrax = {sid: t for sid, t in by_id.items() if sid.startswith("fantrax_")}
    assert len(fantrax) == 10
    for sid, t in fantrax.items():
        urls = [e["url"] for e in t["evidence"]]
        assert "https://www.fantrax.com/terms-of-service" in urls, sid
        assert (
            "https://www.fantrax.com/developer" in urls
        ) == sid.startswith("fantrax_public_"), sid
        assert any("fantrax.com/developer" in h for h in t["how"]) == sid.startswith("fantrax_public_"), sid
    assert by_id["collegefootballdata"]["status"] == "permitted"
    assert by_id["collegefootballdata"]["checked"] == date(2026, 11, 7)
    assert by_id["fantrax_draftpicks_go"]["checked"] == date(2026, 11, 7)
    assert by_id["dynastysharks"]["status"] == "unresolved"
    assert by_id["dynastysharks"]["checked"] == date(2026, 11, 7)
    assert by_id["dynastysharks"]["checked_in"] == "#400"
    assert by_id["dynastysharks"]["access"] == "manual_file"
    assert by_id["dynastysharks"]["evidence"] == by_id["draftsharks"]["evidence"]
    assert cs.terms_due(cs.load_yaml()["sources"], date(2026, 11, 7))["never"] == [
        "google_sheet_team_manifest",
        "manual_excel_misc",
        "google_sheet_manifest_write",
    ]


def test_real_manifest_render_is_current():
    current = cs.SOURCES_MD.read_text(encoding="utf-8")
    assert cs.render_md(cs.load_yaml(), current) == current


def test_real_manifest_advisory_counts():
    data = cs.load_yaml()
    sources = data["sources"]
    assert cs.terms_due(sources, TODAY) == {
        "never": ["google_sheet_team_manifest", "manual_excel_misc", "google_sheet_manifest_write"],
        "past": [],
    }
    assert len(cs.recite_due(sources)) == 27
    assert len(cs.security_due(sources, TODAY)) == 25
    assert [ln.split()[1] for ln in cs.advisories(data, TODAY)] == ["3", "27", "25"]


def _bad(terms_changes, **kw):
    return _src("planned", {**CHECKED_TERMS, **terms_changes}, **kw)


def _fails(capsys, source, needle):
    assert cs.validate({"sources": [source]}, TODAY) == 1
    out = capsys.readouterr().out
    assert needle in out, out


def _doc(**changes):
    return {**DOC, **changes}


def test_valid_new_shape_block_passes(capsys):
    assert cs.validate({"sources": [_src("planned")]}, TODAY) == 0
    out = capsys.readouterr().out
    assert "ADVISORY" not in out and "FAIL" not in out


def test_new_shape_block_with_only_not_found_passes(capsys):
    nf = {"kind": "terms", "looked": ["footer", "menu"], "date": date(2026, 11, 7), "by": "script"}
    s = _bad({"documents": None, "not_found": [nf]})
    assert cs.validate({"sources": [s]}, TODAY) == 0


def test_verified_verdict_on_verbatim_clauses_passes(capsys):
    s = _bad({"status": "permitted"})
    assert cs.validate({"sources": [s]}, TODAY) == 0


def test_place_off_the_list_fails(capsys):
    rf = {**DOC["reached_from"], "place": "guess"}
    _fails(capsys, _bad({"documents": [_doc(reached_from=rf)]}), "reached_from.place must be one of")


def test_unread_off_the_list_fails(capsys):
    _fails(capsys, _bad({"documents": [_doc(unread="shy")]}), ".unread must be null or one of")


def test_rate_limited_is_a_valid_unread_reason(capsys):
    s = _bad({"documents": [_doc(unread="rate_limited")]})
    assert cs.validate({"sources": [s]}, TODAY) == 0


def test_verdict_needs_a_verbatim_deciding_document(capsys):
    summary = [{"section": "4", "topic": "t", "verbatim": False, "quote": "a summary"}]
    privacy = _doc(kind="privacy")
    for label, docs in {
        "summary clause": [_doc(clauses=summary)],
        "no clauses": [_doc(clauses=[])],
        "privacy only": [privacy],
        "mixed clauses": [_doc(clauses=summary + DOC["clauses"])],
    }.items():
        for verdict in ("permitted", "rejected"):
            s = _bad({"status": verdict, "documents": docs})
            assert cs.validate({"sources": [s]}, TODAY) == 1, (label, verdict)
            assert "all verbatim: true" in capsys.readouterr().out, (label, verdict)


def test_unresolved_may_rest_on_a_summary(capsys):
    summary = [{"section": None, "topic": "t", "verbatim": False, "quote": "a summary"}]
    assert cs.validate({"sources": [_bad({"documents": [_doc(clauses=summary)]})]}, TODAY) == 0


def test_owner_paste_needs_a_capture_hash(capsys):
    paste = _doc(read_by="owner", method="owner_paste")
    _fails(capsys, _bad({"documents": [paste]}), "needs a capture_sha256")
    ok = _doc(read_by="owner", method="owner_paste", capture_sha256="a" * 64)
    assert cs.validate({"sources": [_bad({"documents": [ok]})]}, TODAY) == 0


def test_capture_hash_must_be_64_hex(capsys):
    _fails(capsys, _bad({"documents": [_doc(capture_sha256="abc")]}), "64 hex characters")


def test_not_found_needs_looked_and_date(capsys):
    good = {"kind": "terms", "looked": ["footer"], "date": date(2026, 11, 7), "by": "agent"}
    for label, nf in {
        "no looked": {k: v for k, v in good.items() if k != "looked"},
        "empty looked": {**good, "looked": []},
        "looked off the list": {**good, "looked": ["guess"]},
        "no date": {k: v for k, v in good.items() if k != "date"},
    }.items():
        s = _bad({"documents": None, "not_found": [nf]})
        assert cs.validate({"sources": [s]}, TODAY) == 1, label
        assert "terms.not_found[0]" in capsys.readouterr().out, label


def test_checked_new_shape_block_needs_the_robots_code(capsys):
    _fails(capsys, _bad({"signals": {}}), "signals.robots.code is required")
    _fails(capsys, _bad({"signals": None}), "signals.robots.code is required")
    _fails(capsys, _bad({"signals": {"robots": {"code": "404"}}}), "robots.code must be an integer")


def test_block_with_evidence_and_documents_fails(capsys):
    both = {**CHECKED_TERMS, "evidence": LEGACY_TERMS["evidence"]}
    _fails(capsys, _src("planned", both), "holds both evidence and documents")
    half = {**both, "documents": None, "not_found": [
        {"kind": "terms", "looked": ["footer"], "date": date(2026, 11, 7), "by": "agent"}
    ]}
    _fails(capsys, _src("planned", half), "holds both evidence and documents")


def test_checked_new_shape_block_needs_an_entry(capsys):
    _fails(capsys, _bad({"documents": [], "not_found": []}), "at least one documents or not_found entry")


def test_bad_document_fields_fail(capsys):
    for label, doc in {
        "kind": _doc(kind="faq"),
        "read_by": _doc(read_by="bot"),
        "method": _doc(method="curl"),
        "read": _doc(read="2026-11-07"),
        "page_date": _doc(page_date="2026"),
        "unknown field": _doc(guess=True),
        "no url": {k: v for k, v in DOC.items() if k != "url"},
        "clause shape": _doc(clauses=[{"quote": "x"}]),
        "verbatim not bool": _doc(clauses=[{**DOC["clauses"][0], "verbatim": "yes"}]),
    }.items():
        assert cs.validate({"sources": [_bad({"documents": [doc]})]}, TODAY) == 1, label
        assert "terms.documents[0]" in capsys.readouterr().out, label


def test_bad_signals_and_operator_fail(capsys):
    _fails(capsys, _bad({"signals": {**SIGNALS, "ai": 1}}), "terms.signals has unknown field")
    _fails(capsys, _bad({"signals": {**SIGNALS, "tdmrep": {"x": 1}}}), "terms.signals.tdmrep")
    _fails(capsys, _bad({"operator": 5}), "terms.operator must be text or null")


def test_security_block_is_optional_and_shape_checked(capsys):
    assert cs.validate({"sources": [_src("planned", security=None)]}, TODAY) == 0
    capsys.readouterr()
    for label, changes in {
        "not a mapping": "yes",
        "unknown field": {**SECURITY, "score": 9},
        "no checked": {k: v for k, v in SECURITY.items() if k != "checked"},
        "no confirmed": {k: v for k, v in SECURITY.items() if k != "confirmed"},
        "checked not a date": {**SECURITY, "checked": "2026-11-07"},
        "unknown flag": {**SECURITY, "flags": ["spooky"]},
        "flags not a list": {**SECURITY, "flags": "young_domain"},
        "control not int": {**SECURITY, "controls": {**SECURITY["controls"], "malware": "2"}},
        "controls missing key": {**SECURITY, "controls": {"malware": 2}},
        "safe browsing via": {**SECURITY, "safe_browsing": {**SECURITY["safe_browsing"], "via": "api"}},
        "safe browsing code": {**SECURITY, "safe_browsing": {**SECURITY["safe_browsing"], "code": "1"}},
        "dns value": {**SECURITY, "dns": "slow"},
        "tls shape": {**SECURITY, "tls": {"ok": True}},
        "hsts shape": {**SECURITY, "hsts": {"max_age": "long", "preloaded": None}},
        "registered": {**SECURITY, "registered": "2010"},
        "confirmed shape": {**SECURITY, "confirmed": {"by": "owner"}},
    }.items():
        s = _src("planned", security=None)
        s["security"] = changes
        assert cs.validate({"sources": [s]}, TODAY) == 1, label
        assert "security" in capsys.readouterr().out, label


def test_security_flags_include_the_ruled_additions():
    assert {"tls_failed", "age_unknown", "young_domain", "controls_failed"} <= cs.SECURITY_FLAGS
    s = _src("planned")
    s["security"]["flags"] = ["tls_failed", "age_unknown"]
    assert cs.check_security(s) == []


def test_held_host_block_with_null_probes_is_valid():
    s = _src("planned")
    s["security"].update(tls=None, hsts=None, registered=None, flags=["age_unknown"], confirmed={"by": None, "date": None})
    assert cs.check_security(s) == []


def test_evidence_block_is_valid_and_counts_once_as_re_cite_due(capsys):
    data = {"sources": [_src("planned", dict(LEGACY_TERMS))]}
    assert cs.validate(data, TODAY) == 0
    out = capsys.readouterr().out
    assert out.count("ADVISORY") == 1
    assert "ADVISORY  1 source(s) due a re-cite (old evidence field)" in out
    assert "FAIL" not in out
    assert cs.recite_due(data["sources"]) == ["x"]


def test_only_checked_evidence_blocks_are_re_cite_due_whatever_their_status():
    never = _src("planned", dict(NEVER_TERMS), sid="a")
    new = _src("planned", sid="b")
    legacy_rejected = _src("rejected", dict(LEGACY_TERMS), sid="c")
    assert cs.recite_due([never, new, legacy_rejected]) == ["c"]
    assert cs.recite_advisory({"sources": [never, new]}) is None


def test_re_cite_advisory_is_one_line_for_many_sources(capsys):
    data = {"sources": [_src("planned", dict(LEGACY_TERMS), sid=str(i)) for i in range(4)]}
    assert cs.validate(data, TODAY) == 0
    out = capsys.readouterr().out
    assert out.count("ADVISORY") == 1 and "4 source(s) due a re-cite" in out


def test_security_advisory_is_one_line_and_never_a_failure(capsys):
    data = {"sources": [_src("planned", sid=str(i), security=None) for i in range(3)]}
    assert cs.validate(data, TODAY) == 0
    out = capsys.readouterr().out
    assert out.count("ADVISORY") == 1
    assert "3 source(s) due a security check" in out
    assert "FAIL" not in out


def test_security_due_reasons():
    def planned(sid, sec, access="public_get", status="planned"):
        terms = {**CHECKED_TERMS, "access": access}
        s = _src(status, terms, sid=sid, security=None)
        if sec is not None:
            s["security"] = sec
        return s

    stale = {**SECURITY, "checked": date(2025, 5, 6)}
    flagged = {**SECURITY, "flags": ["sb_stale"]}
    unconfirmed = {**SECURITY, "confirmed": {"by": None, "date": None}}
    sources = [
        planned("clean", SECURITY),
        planned("no_block", None),
        planned("stale", stale),
        planned("flagged", flagged),
        planned("manual", None, access="manual_file"),
        planned("not_read", None, access="none"),
        planned("api", None, access="api_key"),
        planned("login", None, access="owner_login"),
        planned("rejected", None, status="rejected"),
        planned("planned_unconfirmed", unconfirmed),
        planned("live_unconfirmed", unconfirmed, status="live"),
        planned("live_confirmed", SECURITY, status="live"),
    ]
    assert cs.security_due(sources, TODAY) == [
        "no_block", "stale", "flagged", "api", "login", "live_unconfirmed",
    ]


def test_planned_source_with_access_none_is_not_security_due():
    s = _src("planned", {**CHECKED_TERMS, "access": "none"}, security=None)
    assert cs.security_due([s], TODAY) == []
    assert cs.security_advisory({"sources": [s]}, TODAY) is None


def test_check_prints_the_same_advisory_lines(capsys, monkeypatch, tmp_path):
    md = tmp_path / "SOURCES.md"
    md.write_text("tables", encoding="utf-8")
    monkeypatch.setattr(cs, "SOURCES_MD", md)
    monkeypatch.setattr(cs, "load_yaml", lambda: {"sources": [_src("planned", dict(LEGACY_TERMS), security=None)]})
    monkeypatch.setattr(sys, "argv", ["check_sources.py", "--check"])
    monkeypatch.setattr(cs, "render_md", lambda data, current: current)
    assert cs.main() == 0
    out = capsys.readouterr().out
    assert "due a re-cite" in out and "due a security check" in out
