#!/usr/bin/env python
"""check_sources.py — validate and render the external-input manifest.

docs/sources.yml is the SSOT for every external data source. This script:

  validate (default)  schema-check all sources; assert each LIVE source's feed
                      notebooks exist and contain >=1 match token; warn on
                      reverse-drift (notebook hosts not registered / ignored).
                      Exit 1 on any HARD failure (reverse-drift is WARN only).
                      Every source also needs a `terms` block (ADR-0022): a
                      malformed block is a hard failure, but a source never
                      checked or past its next_check is only ONE advisory line
                      with a count, never a failure.
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
import calendar
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

REQUIRED_FIELDS = ("id", "name", "status", "locator", "purpose", "auth", "cadence", "feeds", "terms")
VALID_STATUS = {"live", "planned", "rejected"}

TERMS_STATUS = {"unresolved", "permitted", "rejected"}
TERMS_ACCESS = {"public_get", "api_key", "owner_login", "manual_file", "none"}
TERMS_KEYS = {
    "status", "checked", "checked_in", "how", "evidence", "licence",
    "attribution", "share_alike", "upstream", "access", "permission",
}
TERMS_ALWAYS = ("status", "checked", "access")
TERMS_ONCE_CHECKED = ("checked_in", "how", "evidence", "licence", "share_alike")
TERMS_RECHECK_MONTHS = 6
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


def add_months(d: date, months: int) -> date:
    year, month0 = divmod(d.month - 1 + months, 12)
    year += d.year
    month = month0 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def next_check(terms: object) -> date | None:
    checked = terms.get("checked") if isinstance(terms, dict) else None
    return add_months(checked, TERMS_RECHECK_MONTHS) if _is_date(checked) else None


def _is_text(v: object) -> bool:
    return isinstance(v, str) and bool(v.strip())


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

    if _is_date(checked):
        for key in TERMS_ONCE_CHECKED:
            if terms.get(key) is None:
                errs.append(f"[{tag}] terms.{key} is required once checked has a date")
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
    advisory = terms_advisory(data, today)
    if advisory:
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
        advisory = terms_advisory(data)
        if advisory:
            print(advisory)
        return 0

    return validate(data)


if __name__ == "__main__":
    sys.exit(main())
