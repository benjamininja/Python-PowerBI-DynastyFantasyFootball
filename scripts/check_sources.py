#!/usr/bin/env python
"""check_sources.py — validate and render the external-input manifest.

docs/sources.yml is the SSOT for every external data source. This script:

  validate (default)  schema-check all sources; assert each LIVE source's feed
                      notebooks exist and contain >=1 match token; warn on
                      reverse-drift (notebook hosts not registered / ignored).
                      Exit 1 on any HARD failure (reverse-drift is WARN only).
                      Every source also needs a `terms` block (ADR-0022): a
                      malformed block (or a malformed `security` block) is a
                      hard failure, but a source never checked or past its
                      next_check, a block still on the old `evidence` field,
                      and a missing or stale security check are each only ONE
                      advisory line with a count, never a failure.
  --render            regenerate the table regions in docs/SOURCES.md from the
                      yaml (between the BEGIN/END GENERATED markers).
  --check             render in-memory and diff against SOURCES.md; exit 1 if
                      stale (CI guard against a hand-edited / forgotten table).

Run via the .venv (PyYAML lives there):
    .\\run.ps1 scripts/check_sources.py
    .\\run.ps1 scripts/check_sources.py --render
    .\\run.ps1 scripts/check_sources.py --check
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
SOURCES_YML = REPO / "docs" / "sources.yml"
SOURCES_MD = REPO / "docs" / "SOURCES.md"
NOTEBOOK_DIR = REPO / "notebooks"

sys.path.insert(0, str(NOTEBOOK_DIR))
import etl_helpers as etl  # noqa: E402

CFG = etl.CFG

REQUIRED_FIELDS = ("id", "name", "status", "locator", "purpose", "auth", "cadence", "feeds", "terms")
VALID_STATUS = {"live", "planned", "rejected"}

TERMS_STATUS = {"unresolved", "permitted", "rejected"}
TERMS_ACCESS = {"public_get", "api_key", "owner_login", "manual_file", "none"}
TERMS_KEYS = {
    "status", "checked", "checked_in", "how", "evidence", "licence",
    "attribution", "share_alike", "upstream", "access", "permission",
    "documents", "not_found", "signals", "operator",
}
TERMS_ALWAYS = ("status", "checked", "access")
TERMS_ONCE_CHECKED = ("checked_in", "how", "licence", "share_alike")

DOC_KINDS = {"terms", "api_terms", "licence", "privacy", "copyright"}
DECIDING_KINDS = {"terms", "api_terms", "licence"}
PLACES = {
    "footer", "menu", "sitemap", "legal_hub", "linked_from_doc",
    "operator_domain", "robots_txt", "api_docs", "owner_supplied",
}
READ_BY = {"agent", "owner", "script"}
METHODS = {"http_get", "browser_render", "owner_paste"}
UNREAD = {
    "js_rendered", "refused_status", "robots_blocks_agent", "login",
    "paywall", "dns", "tool_refused", "rate_limited",
}
DOC_KEYS = {
    "kind", "url", "reached_from", "read", "page_date", "read_by", "method",
    "unread", "archive", "capture_sha256", "clauses",
}
DOC_REQUIRED = ("kind", "url", "reached_from", "read", "read_by", "method")
ROBOTS_KEYS = {
    "url", "code", "read", "claude_groups", "blocks_agent", "content_signal",
    "content_usage", "crawl_delay", "sha256",
}
SIGNAL_KEYS = {"robots", "tdmrep", "x_robots_tag", "meta_robots"}
SECURITY_KEYS = {
    "checked", "host", "controls", "safe_browsing", "dns", "tls", "hsts",
    "registered", "flags", "confirmed",
}
SECURITY_REQUIRED = ("checked", "host", "flags", "confirmed")
SECURITY_FLAGS = {
    "young_domain", "age_unknown", "tls_expiring", "tls_failed", "sb_unsafe",
    "sb_no_verdict", "sb_stale", "nxdomain", "controls_failed",
}
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
HOST_RE = re.compile(r"https?://([^/\s\"'\\)]+)", re.IGNORECASE)

# --- markers ---------------------------------------------------------------
def _markers(group: str) -> tuple[str, str]:
    begin = f"<!-- BEGIN GENERATED sources-table:{group} — regen: python scripts/check_sources.py --render -->"
    end = f"<!-- END GENERATED sources-table:{group} -->"
    return begin, end


# --- io --------------------------------------------------------------------
def load_yaml() -> dict:
    with SOURCES_YML.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def notebook_source_text(path: Path) -> str:
    """Concatenated code+markdown cell source for .ipynb; whole file for .py.

    For .ipynb we read only cell.source (never outputs) so a token cached in a
    stale execution result can't produce a false match.
    """
    if path.suffix == ".ipynb":
        nb = json.loads(path.read_text(encoding="utf-8"))
        parts: list[str] = []
        for cell in nb.get("cells", []):
            if cell.get("cell_type") in ("code", "markdown"):
                src = cell.get("source", "")
                parts.append("".join(src) if isinstance(src, list) else src)
        return "\n".join(parts)
    return path.read_text(encoding="utf-8")


# --- terms (ADR-0022) -------------------------------------------------------
def _is_date(v: object) -> bool:
    return isinstance(v, date) and not isinstance(v, datetime)


def next_season_check(checked: date) -> date:
    """The 1st of the first CFG.source_check_month month that starts after `checked`."""
    month = int(CFG.source_check_month)
    start = date(checked.year, month, 1)
    return start if start > checked else date(checked.year + 1, month, 1)


def next_check(terms: object) -> date | None:
    checked = terms.get("checked") if isinstance(terms, dict) else None
    return next_season_check(checked) if _is_date(checked) else None


def security_next_check(security: object) -> date | None:
    checked = security.get("checked") if isinstance(security, dict) else None
    return next_season_check(checked) if _is_date(checked) else None


def _is_text(v: object) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_text_or_null(v: object) -> bool:
    return v is None or _is_text(v)


def _is_date_or_null(v: object) -> bool:
    return v is None or _is_date(v)


def _check_clauses(where: str, clauses: object) -> list[str]:
    if not isinstance(clauses, list):
        return [f"{where}.clauses must be a list"]
    errs: list[str] = []
    for j, c in enumerate(clauses):
        ok = (
            isinstance(c, dict)
            and set(c) == {"section", "topic", "verbatim", "quote"}
            and _is_text_or_null(c["section"])
            and _is_text(c["topic"])
            and isinstance(c["verbatim"], bool)
            and _is_text(c["quote"])
        )
        if not ok:
            errs.append(f"{where}.clauses[{j}] must be {{section: text|null, topic: text, verbatim: bool, quote: text}}")
    return errs


def _check_documents(tag: str, docs: object) -> list[str]:
    if not isinstance(docs, list):
        return [f"[{tag}] terms.documents must be a list"]
    errs: list[str] = []
    for i, d in enumerate(docs):
        where = f"[{tag}] terms.documents[{i}]"
        if not isinstance(d, dict):
            errs.append(f"{where} must be a mapping")
            continue
        for key in sorted(set(d) - DOC_KEYS):
            errs.append(f"{where} has unknown field '{key}'")
        for key in DOC_REQUIRED:
            if d.get(key) is None:
                errs.append(f"{where} missing required field '{key}'")
        if d.get("kind") is not None and d["kind"] not in DOC_KINDS:
            errs.append(f"{where}.kind must be one of {sorted(DOC_KINDS)}, got {d['kind']!r}")
        if d.get("url") is not None and not _is_text(d["url"]):
            errs.append(f"{where}.url must be text")
        rf = d.get("reached_from")
        if rf is not None:
            if not (isinstance(rf, dict) and set(rf) <= {"page", "place", "link_text"}):
                errs.append(f"{where}.reached_from must be {{page, place, link_text}}")
            else:
                if rf.get("place") not in PLACES:
                    errs.append(f"{where}.reached_from.place must be one of {sorted(PLACES)}, got {rf.get('place')!r}")
                if not (_is_text_or_null(rf.get("page")) and _is_text_or_null(rf.get("link_text"))):
                    errs.append(f"{where}.reached_from page and link_text must be text or null")
        if "read" in d and d["read"] is not None and not _is_date(d["read"]):
            errs.append(f"{where}.read must be a date")
        if not _is_date_or_null(d.get("page_date")):
            errs.append(f"{where}.page_date must be a date or null")
        if d.get("read_by") is not None and d["read_by"] not in READ_BY:
            errs.append(f"{where}.read_by must be one of {sorted(READ_BY)}, got {d['read_by']!r}")
        if d.get("method") is not None and d["method"] not in METHODS:
            errs.append(f"{where}.method must be one of {sorted(METHODS)}, got {d['method']!r}")
        if d.get("unread") is not None and d["unread"] not in UNREAD:
            errs.append(f"{where}.unread must be null or one of {sorted(UNREAD)}, got {d['unread']!r}")
        if not _is_text_or_null(d.get("archive")):
            errs.append(f"{where}.archive must be text or null")
        sha = d.get("capture_sha256")
        if sha is not None and not (isinstance(sha, str) and SHA256_RE.match(sha)):
            errs.append(f"{where}.capture_sha256 must be 64 hex characters or null")
        if d.get("read_by") == "owner" and d.get("method") == "owner_paste" and sha is None:
            errs.append(f"{where} is an owner paste and needs a capture_sha256")
        if d.get("clauses") is not None:
            errs.extend(_check_clauses(where, d["clauses"]))
    return errs


def _check_not_found(tag: str, entries: object) -> list[str]:
    if not isinstance(entries, list):
        return [f"[{tag}] terms.not_found must be a list"]
    errs: list[str] = []
    for i, n in enumerate(entries):
        where = f"[{tag}] terms.not_found[{i}]"
        if not isinstance(n, dict):
            errs.append(f"{where} must be a mapping")
            continue
        for key in sorted(set(n) - {"kind", "looked", "date", "by"}):
            errs.append(f"{where} has unknown field '{key}'")
        if n.get("kind") not in DOC_KINDS:
            errs.append(f"{where}.kind must be one of {sorted(DOC_KINDS)}, got {n.get('kind')!r}")
        looked = n.get("looked")
        if not (isinstance(looked, list) and looked and all(p in PLACES for p in looked)):
            errs.append(f"{where}.looked must be a non-empty list of places from {sorted(PLACES)}")
        if not _is_date(n.get("date")):
            errs.append(f"{where}.date must be a date")
        if n.get("by") not in READ_BY:
            errs.append(f"{where}.by must be one of {sorted(READ_BY)}, got {n.get('by')!r}")
    return errs


def _check_signals(tag: str, signals: object) -> list[str]:
    if not isinstance(signals, dict):
        return [f"[{tag}] terms.signals must be a mapping"]
    errs: list[str] = []
    for key in sorted(set(signals) - SIGNAL_KEYS):
        errs.append(f"[{tag}] terms.signals has unknown field '{key}'")
    robots = signals.get("robots")
    if robots is not None:
        if not isinstance(robots, dict):
            errs.append(f"[{tag}] terms.signals.robots must be a mapping")
        else:
            for key in sorted(set(robots) - ROBOTS_KEYS):
                errs.append(f"[{tag}] terms.signals.robots has unknown field '{key}'")
            if "code" in robots and not _is_int(robots["code"]):
                errs.append(f"[{tag}] terms.signals.robots.code must be an integer")
            if not _is_date_or_null(robots.get("read")):
                errs.append(f"[{tag}] terms.signals.robots.read must be a date")
            if "claude_groups" in robots and not isinstance(robots["claude_groups"], list):
                errs.append(f"[{tag}] terms.signals.robots.claude_groups must be a list")
            if "blocks_agent" in robots and not isinstance(robots["blocks_agent"], bool):
                errs.append(f"[{tag}] terms.signals.robots.blocks_agent must be true or false")
    tdm = signals.get("tdmrep")
    if tdm is not None and not (isinstance(tdm, dict) and set(tdm) <= {"well_known", "header", "meta"}):
        errs.append(f"[{tag}] terms.signals.tdmrep must be {{well_known, header, meta}}")
    for key in ("x_robots_tag", "meta_robots"):
        if not _is_text_or_null(signals.get(key)):
            errs.append(f"[{tag}] terms.signals.{key} must be text or null")
    return errs


def _rests_on_verbatim(docs: object) -> bool:
    if not isinstance(docs, list):
        return False
    for d in docs:
        if not (isinstance(d, dict) and d.get("kind") in DECIDING_KINDS):
            continue
        clauses = d.get("clauses")
        if (
            isinstance(clauses, list)
            and clauses
            and all(isinstance(c, dict) and c.get("verbatim") is True for c in clauses)
        ):
            return True
    return False


def is_legacy_terms(terms: object) -> bool:
    """A checked block still on the old `evidence` field (ADR-0022 decision 15)."""
    return (
        isinstance(terms, dict)
        and _is_date(terms.get("checked"))
        and terms.get("evidence") is not None
        and terms.get("documents") is None
        and terms.get("not_found") is None
    )


def check_terms(source: dict) -> list[str]:
    tag = source.get("id", "<no id>")
    terms = source.get("terms")
    if terms is None:
        return []
    if not isinstance(terms, dict):
        return [f"[{tag}] terms must be a mapping"]

    errs: list[str] = []
    for key in sorted(set(terms) - TERMS_KEYS):
        errs.append(f"[{tag}] terms has unknown field '{key}'")
    for key in TERMS_ALWAYS:
        if key not in terms:
            errs.append(f"[{tag}] terms missing required field '{key}'")
    if "status" in terms and terms["status"] not in TERMS_STATUS:
        errs.append(f"[{tag}] terms.status must be one of {sorted(TERMS_STATUS)}, got {terms['status']!r}")
    if "access" in terms and terms["access"] not in TERMS_ACCESS:
        errs.append(f"[{tag}] terms.access must be one of {sorted(TERMS_ACCESS)}, got {terms['access']!r}")

    checked = terms.get("checked")
    if "checked" in terms and checked is not None and not _is_date(checked):
        errs.append(f"[{tag}] terms.checked must be a date or null, got {checked!r}")
    if terms.get("status") in ("permitted", "rejected") and checked is None:
        errs.append(f"[{tag}] terms.status {terms['status']} needs a checked date")

    has_evidence = terms.get("evidence") is not None
    has_documents = terms.get("documents") is not None
    has_not_found = terms.get("not_found") is not None
    new_shape = has_documents or has_not_found

    if _is_date(checked):
        for key in TERMS_ONCE_CHECKED:
            if terms.get(key) is None:
                errs.append(f"[{tag}] terms.{key} is required once checked has a date")
        if not (has_evidence or new_shape):
            errs.append(f"[{tag}] terms needs documents or not_found (or the old evidence field) once checked has a date")
    if "checked_in" in terms and terms["checked_in"] is not None and not _is_text(terms["checked_in"]):
        errs.append(f"[{tag}] terms.checked_in must be text")
    if "licence" in terms and terms["licence"] is not None and not _is_text(terms["licence"]):
        errs.append(f"[{tag}] terms.licence must be text")
    if "how" in terms and terms["how"] is not None:
        how = terms["how"]
        if not (isinstance(how, list) and how and all(_is_text(h) for h in how)):
            errs.append(f"[{tag}] terms.how must be a non-empty list of text")
    if "evidence" in terms and terms["evidence"] is not None:
        ev = terms["evidence"]
        ok = isinstance(ev, list) and bool(ev) and all(
            isinstance(e, dict)
            and _is_text(e.get("url"))
            and (e.get("archive") is None or _is_text(e.get("archive")))
            and set(e) <= {"url", "archive"}
            for e in ev
        )
        if not ok:
            errs.append(f"[{tag}] terms.evidence must be a non-empty list of {{url, archive}}")
    if "share_alike" in terms and terms["share_alike"] is not None and not isinstance(terms["share_alike"], bool):
        errs.append(f"[{tag}] terms.share_alike must be true or false")
    if terms.get("attribution") is not None and not _is_text(terms["attribution"]):
        errs.append(f"[{tag}] terms.attribution must be text or null")
    if terms.get("upstream") is not None and not isinstance(terms["upstream"], list):
        errs.append(f"[{tag}] terms.upstream must be a list")
    perm = terms.get("permission")
    if perm is not None and not (isinstance(perm, dict) and _is_date(perm.get("asked")) and set(perm) <= {"asked", "given", "link"}):
        errs.append(f"[{tag}] terms.permission must be null or {{asked: date, given: date|null, link: text|null}}")

    if has_evidence and new_shape:
        errs.append(f"[{tag}] terms holds both evidence and documents/not_found; a half-migrated record cannot pass (ADR-0022)")
    if has_documents:
        errs.extend(_check_documents(tag, terms["documents"]))
    if has_not_found:
        errs.extend(_check_not_found(tag, terms["not_found"]))
    if terms.get("signals") is not None:
        errs.extend(_check_signals(tag, terms["signals"]))
    if not _is_text_or_null(terms.get("operator")):
        errs.append(f"[{tag}] terms.operator must be text or null")

    if new_shape:
        if _is_date(checked):
            if not (terms.get("documents") or terms.get("not_found")):
                errs.append(f"[{tag}] terms needs at least one documents or not_found entry once checked has a date")
            robots = (terms.get("signals") or {}).get("robots") if isinstance(terms.get("signals"), dict) else None
            if not (isinstance(robots, dict) and _is_int(robots.get("code"))):
                errs.append(f"[{tag}] terms.signals.robots.code is required on a new-shape block with a check date")
        if terms.get("status") in ("permitted", "rejected") and not _rests_on_verbatim(terms.get("documents")):
            errs.append(
                f"[{tag}] terms.status {terms['status']} needs a terms, api_terms or licence document "
                "whose clauses are all verbatim: true"
            )
    return errs


def check_security(source: dict) -> list[str]:
    tag = source.get("id", "<no id>")
    sec = source.get("security")
    if sec is None:
        return []
    if not isinstance(sec, dict):
        return [f"[{tag}] security must be a mapping"]

    errs: list[str] = []
    for key in sorted(set(sec) - SECURITY_KEYS):
        errs.append(f"[{tag}] security has unknown field '{key}'")
    for key in SECURITY_REQUIRED:
        if key not in sec:
            errs.append(f"[{tag}] security missing required field '{key}'")
    if "checked" in sec and not _is_date(sec["checked"]):
        errs.append(f"[{tag}] security.checked must be a date")
    if "host" in sec and not _is_text(sec["host"]):
        errs.append(f"[{tag}] security.host must be text")

    c = sec.get("controls")
    if c is not None and not (
        isinstance(c, dict)
        and set(c) == {"malware", "phishing", "unwanted", "shape_ok"}
        and all(_is_int(c[k]) for k in ("malware", "phishing", "unwanted"))
        and isinstance(c["shape_ok"], bool)
    ):
        errs.append(f"[{tag}] security.controls must be {{malware, phishing, unwanted: int, shape_ok: bool}}")
    sb = sec.get("safe_browsing")
    if sb is not None and not (
        isinstance(sb, dict)
        and set(sb) == {"via", "code", "google_scan"}
        and sb["via"] == "transparency_report"
        and _is_int(sb["code"])
        and _is_date_or_null(sb["google_scan"])
    ):
        errs.append(f"[{tag}] security.safe_browsing must be {{via: transparency_report, code: int, google_scan: date|null}}")
    if sec.get("dns") is not None and sec["dns"] not in ("resolves", "nxdomain"):
        errs.append(f"[{tag}] security.dns must be resolves or nxdomain, got {sec['dns']!r}")
    tls = sec.get("tls")
    if tls is not None and not (
        isinstance(tls, dict)
        and set(tls) == {"ok", "issuer", "not_after", "version"}
        and isinstance(tls["ok"], bool)
        and _is_text_or_null(tls["issuer"])
        and _is_date_or_null(tls["not_after"])
        and _is_text_or_null(tls["version"])
    ):
        errs.append(f"[{tag}] security.tls must be {{ok: bool, issuer: text|null, not_after: date|null, version: text|null}}")
    hsts = sec.get("hsts")
    if hsts is not None and not (
        isinstance(hsts, dict)
        and set(hsts) == {"max_age", "preloaded"}
        and (hsts["max_age"] is None or _is_int(hsts["max_age"]))
        and (hsts["preloaded"] is None or isinstance(hsts["preloaded"], bool) or _is_text(hsts["preloaded"]))
    ):
        errs.append(f"[{tag}] security.hsts must be {{max_age: int|null, preloaded: bool|text|null}}")
    if not _is_date_or_null(sec.get("registered")):
        errs.append(f"[{tag}] security.registered must be a date or null")
    flags = sec.get("flags")
    if "flags" in sec and not (isinstance(flags, list) and all(f in SECURITY_FLAGS for f in flags)):
        errs.append(f"[{tag}] security.flags must be a list from {sorted(SECURITY_FLAGS)}")
    conf = sec.get("confirmed")
    if "confirmed" in sec and not (
        isinstance(conf, dict)
        and set(conf) == {"by", "date"}
        and _is_text_or_null(conf["by"])
        and _is_date_or_null(conf["date"])
    ):
        errs.append(f"[{tag}] security.confirmed must be {{by: text|null, date: date|null}}")
    return errs


def terms_due(sources: list[dict], today: date | None = None) -> dict[str, list[str]]:
    today = today or date.today()
    never: list[str] = []
    past: list[str] = []
    for s in sources:
        sid = s.get("id", "<no id>")
        due = next_check(s.get("terms"))
        if due is None:
            never.append(sid)
        elif today > due:
            past.append(sid)
    return {"never": never, "past": past}


def terms_due_count(data: dict, today: date | None = None) -> int:
    due = terms_due(data.get("sources", []) or [], today)
    return len(due["never"]) + len(due["past"])


def terms_advisory(data: dict, today: date | None = None) -> str | None:
    due = terms_due(data.get("sources", []) or [], today)
    n = len(due["never"]) + len(due["past"])
    if not n:
        return None
    return (
        f"ADVISORY  {n} source(s) due a terms check ({len(due['past'])} past next_check, "
        f"{len(due['never'])} never checked) — see docs/SOURCES.md, ADR-0022"
    )


def recite_due(sources: list[dict]) -> list[str]:
    return [s.get("id", "<no id>") for s in sources if is_legacy_terms(s.get("terms"))]


def recite_advisory(data: dict) -> str | None:
    n = len(recite_due(data.get("sources", []) or []))
    if not n:
        return None
    return f"ADVISORY  {n} source(s) due a re-cite (old evidence field) — see docs/SOURCES.md, ADR-0022"


def _reads_over_http(source: dict) -> bool:
    terms = source.get("terms")
    access = terms.get("access") if isinstance(terms, dict) else None
    return source.get("status") in ("live", "planned") and access in ("public_get", "api_key", "owner_login")


def security_due(sources: list[dict], today: date | None = None) -> list[str]:
    today = today or date.today()
    due: list[str] = []
    for s in sources:
        if not _reads_over_http(s):
            continue
        sec = s.get("security")
        if not isinstance(sec, dict):
            due.append(s.get("id", "<no id>"))
            continue
        nxt = security_next_check(sec)
        conf = sec.get("confirmed")
        unconfirmed = s.get("status") == "live" and not (isinstance(conf, dict) and _is_date(conf.get("date")))
        if nxt is None or today > nxt or sec.get("flags") or unconfirmed:
            due.append(s.get("id", "<no id>"))
    return due


def security_advisory(data: dict, today: date | None = None) -> str | None:
    n = len(security_due(data.get("sources", []) or [], today))
    if not n:
        return None
    return f"ADVISORY  {n} source(s) due a security check — see docs/SOURCES.md, ADR-0022"


def advisories(data: dict, today: date | None = None) -> list[str]:
    lines = (terms_advisory(data, today), recite_advisory(data), security_advisory(data, today))
    return [ln for ln in lines if ln]


# --- validation ------------------------------------------------------------
def validate(data: dict, today: date | None = None) -> int:
    sources = data.get("sources", []) or []
    ignore_hosts = {h.lower().lstrip("www.") for h in (data.get("ignore_hosts") or [])}
    errors: list[str] = []
    warns: list[str] = []

    # 1) schema check (all sources)
    seen_ids: set[str] = set()
    for i, s in enumerate(sources):
        tag = s.get("id", f"<index {i}>")
        for field in REQUIRED_FIELDS:
            if field not in s:
                errors.append(f"[{tag}] missing required field '{field}'")
        sid = s.get("id")
        if sid in seen_ids:
            errors.append(f"[{tag}] duplicate id")
        seen_ids.add(sid)
        if s.get("status") not in VALID_STATUS:
            errors.append(f"[{tag}] status must be one of {sorted(VALID_STATUS)}, got {s.get('status')!r}")
        if not isinstance(s.get("feeds", []), list):
            errors.append(f"[{tag}] feeds must be a list")
        errors.extend(check_terms(s))
        errors.extend(check_security(s))
        if s.get("status") == "live":
            if not s.get("match"):
                errors.append(f"[{tag}] live source has no match tokens")
            if not s.get("feeds"):
                errors.append(f"[{tag}] live source has no feeds")

    # 2) notebook-exists + 3) token-match (LIVE only)
    for s in sources:
        if s.get("status") != "live":
            continue
        tokens = [t.lower() for t in (s.get("match") or [])]
        for feed in s.get("feeds", []):
            nb_name = feed.get("notebook")
            nb_path = NOTEBOOK_DIR / nb_name
            if not nb_path.exists():
                errors.append(f"[{s['id']}] feed notebook not found: notebooks/{nb_name}")
                continue
            text = notebook_source_text(nb_path).lower()
            if tokens and not any(tok in text for tok in tokens):
                errors.append(
                    f"[{s['id']}] none of match {s.get('match')} found in notebooks/{nb_name}"
                )

    # 4) reverse-drift (WARN): notebook hosts not registered and not ignored
    registered: set[str] = set(ignore_hosts)
    for s in sources:
        for field in ("locator",):
            for host in HOST_RE.findall(str(s.get(field, ""))):
                registered.add(host.lower().lstrip("www."))
        for tok in (s.get("match") or []):
            for host in HOST_RE.findall(str(tok)):
                registered.add(host.lower().lstrip("www."))
            if "." in str(tok) and "/" not in str(tok) and " " not in str(tok):
                registered.add(str(tok).lower().lstrip("www."))

    seen_hosts: dict[str, set[str]] = {}
    for nb in sorted(NOTEBOOK_DIR.glob("*.ipynb")) + sorted(NOTEBOOK_DIR.glob("*.py")):
        for host in HOST_RE.findall(notebook_source_text(nb)):
            h = host.lower().lstrip("www.")
            seen_hosts.setdefault(h, set()).add(nb.name)
    for host, nbs in sorted(seen_hosts.items()):
        if not any(host == r or host.endswith("." + r) for r in registered):
            warns.append(f"unregistered host '{host}' in {', '.join(sorted(nbs))}")

    # report
    for w in warns:
        print(f"WARN  {w}")
    for advisory in advisories(data, today):
        print(advisory)
    for e in errors:
        print(f"FAIL  {e}")
    n_live = sum(1 for s in sources if s.get("status") == "live")
    if errors:
        print(f"\n{len(errors)} failure(s), {len(warns)} warning(s) — {n_live} live sources checked.")
        return 1
    print(f"OK — {n_live} live sources validated, {len(warns)} warning(s).")
    return 0


# --- render ----------------------------------------------------------------
def _cell(v: str) -> str:
    return str(v).replace("|", "\\|").strip()


def _table(sources: list[dict], status: str) -> str:
    rows = [
        "| Source | URL / locator | Purpose | Auth | Feeds (notebook → table) | Cadence |",
        "|---|---|---|---|---|---|",
    ]
    for s in sources:
        if s.get("status") != status:
            continue
        feeds = "<br>".join(
            f"`{f.get('notebook')}` → `{f.get('table')}`" for f in (s.get("feeds") or [])
        ) or "—"
        rows.append(
            "| "
            + " | ".join(
                [
                    f"**{_cell(s['name'])}**",
                    _cell(s["locator"]),
                    _cell(s["purpose"]),
                    _cell(s["auth"]),
                    feeds,
                    _cell(s["cadence"]),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def _terms_table(sources: list[dict]) -> str:
    rows = [
        "| Source | Manifest status | Terms | Checked | Next check | Licence | Access | Evidence |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in sources:
        t = s.get("terms") if isinstance(s.get("terms"), dict) else {}
        due = next_check(t)
        rows.append(
            "| "
            + " | ".join(
                [
                    f"**{_cell(s['name'])}**",
                    _cell(s.get("status", "—")),
                    _cell(t.get("status", "—")),
                    _cell(t["checked"]) if t.get("checked") else "never",
                    _cell(due) if due else "—",
                    _cell(t.get("licence") or "—"),
                    _cell(t.get("access", "—")),
                    _cell(t.get("checked_in") or "—"),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def render_md(data: dict, current: str) -> str:
    sources = data.get("sources", []) or []
    out = current
    for group in ("live", "planned", "rejected", "terms"):
        begin, end = _markers(group)
        table = _terms_table(sources) if group == "terms" else _table(sources, group)
        block = f"{begin}\n{table}\n{end}"
        pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
        if not pattern.search(out):
            raise SystemExit(f"marker pair for '{group}' not found in {SOURCES_MD.name}")
        out = pattern.sub(lambda _m, b=block: b, out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--render", action="store_true", help="regenerate the SOURCES.md table regions")
    ap.add_argument("--check", action="store_true", help="fail if SOURCES.md tables are stale vs the yaml")
    args = ap.parse_args()

    data = load_yaml()

    if args.render:
        new = render_md(data, SOURCES_MD.read_text(encoding="utf-8"))
        SOURCES_MD.write_text(new, encoding="utf-8", newline="\n")
        print(f"rendered tables into {SOURCES_MD.relative_to(REPO)}")
        return 0

    if args.check:
        current = SOURCES_MD.read_text(encoding="utf-8")
        if render_md(data, current) != current:
            print("FAIL  SOURCES.md tables are stale — run: python scripts/check_sources.py --render")
            return 1
        print("OK — SOURCES.md tables match sources.yml.")
        for advisory in advisories(data):
            print(advisory)
        return 0

    return validate(data)


if __name__ == "__main__":
    sys.exit(main())
