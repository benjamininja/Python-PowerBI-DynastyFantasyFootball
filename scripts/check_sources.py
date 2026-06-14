#!/usr/bin/env python
"""check_sources.py — validate and render the external-input manifest.

docs/sources.yml is the SSOT for every external data source. This script:

  validate (default)  schema-check all sources; assert each LIVE source's feed
                      notebooks exist and contain >=1 match token; warn on
                      reverse-drift (notebook hosts not registered / ignored).
                      Exit 1 on any HARD failure (reverse-drift is WARN only).
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
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
SOURCES_YML = REPO / "docs" / "sources.yml"
SOURCES_MD = REPO / "docs" / "SOURCES.md"
NOTEBOOK_DIR = REPO / "notebooks"

REQUIRED_FIELDS = ("id", "name", "status", "locator", "purpose", "auth", "cadence", "feeds")
VALID_STATUS = {"live", "planned"}
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


# --- validation ------------------------------------------------------------
def validate(data: dict) -> int:
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


def render_md(data: dict, current: str) -> str:
    sources = data.get("sources", []) or []
    out = current
    for group in ("live", "planned"):
        begin, end = _markers(group)
        block = f"{begin}\n{_table(sources, group)}\n{end}"
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
        return 0

    return validate(data)


if __name__ == "__main__":
    sys.exit(main())
