import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_sources as cs

TODAY = date(2026, 11, 7)

CHECKED_TERMS = {
    "status": "unresolved",
    "checked": date(2026, 11, 7),
    "checked_in": "#1",
    "how": ["robots.txt allows all"],
    "evidence": [{"url": "https://example.com/robots.txt", "archive": None}],
    "licence": "none",
    "attribution": None,
    "share_alike": False,
    "upstream": [],
    "access": "public_get",
    "permission": None,
}
NEVER_TERMS = {"status": "unresolved", "checked": None, "access": "public_get"}


def _src(status, terms=None, sid="x"):
    return {
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
        "checked without evidence": {k: v for k, v in CHECKED_TERMS.items() if k != "evidence"},
        "checked without how": {**CHECKED_TERMS, "how": []},
        "evidence not a mapping": {**CHECKED_TERMS, "evidence": ["https://example.com"]},
        "share_alike not a bool": {**CHECKED_TERMS, "share_alike": "no"},
        "permission without asked date": {**CHECKED_TERMS, "permission": {"given": None}},
    }
    for label, terms in bad.items():
        assert cs.validate({"sources": [_src("planned", terms)]}, TODAY) == 1, label
        assert _errors(capsys), label


def test_next_check_is_checked_plus_six_months():
    assert cs.next_check({"checked": date(2026, 11, 7)}) == date(2027, 5, 7)
    assert cs.next_check({"checked": date(2026, 8, 31)}) == date(2027, 2, 28)
    assert cs.next_check({"checked": date(2026, 12, 15)}) == date(2027, 6, 15)
    assert cs.next_check({"checked": None}) is None


def test_source_past_next_check_is_one_advisory_and_no_failure(capsys):
    stale = dict(CHECKED_TERMS, checked=date(2026, 5, 6))
    data = {"sources": [_src("planned", stale)]}
    assert cs.validate(data, TODAY) == 0
    out = capsys.readouterr().out
    assert out.count("ADVISORY") == 1
    assert "1 source(s) due a terms check (1 past next_check, 0 never checked)" in out
    assert "FAIL" not in out
    assert cs.terms_due(data["sources"], TODAY) == {"never": [], "past": ["x"]}


def test_source_on_its_next_check_date_is_not_yet_due():
    s = _src("planned", dict(CHECKED_TERMS, checked=date(2026, 5, 7)))
    assert cs.terms_due([s], TODAY) == {"never": [], "past": []}
    assert cs.terms_due([s], date(2026, 11, 8)) == {"never": [], "past": ["x"]}


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
    assert "2026-11-07" in rows[0] and "2027-05-07" in rows[0]
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
