#!/usr/bin/env python
"""check_pii.py — fail if owner PII (email addresses) would be published.

This repo is PUBLIC. Owner PII (manager emails, Fantrax usernames, names) lives
only in Supabase shared.owner (grill #87) — never in git. This gate catches the
mechanically detectable part: email-shaped strings.

  check_pii.py FILE...   scan the given files (pre-commit passes staged files)
  check_pii.py --all     scan every tracked file (CI)

Checks:
  text files      email-shaped strings not on ALLOWLIST
  *.parquet       string values that are email-shaped, or an "email" column
  OUTPUT_FREE     notebooks that read the owner sheet must have no saved outputs

Only email shape is detectable — names and Fantrax usernames still need review.
Exit 1 on any hit. Hits are reported by file:line only, never echoed.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")

# Exact addresses, then domain suffixes, that are safe to publish.
ALLOW_EXACT = {"noreply@anthropic.com"}
ALLOW_DOMAIN_SUFFIX = ("users.noreply.github.com", "example.com", "example.org", "example.net")

# Notebooks that read the owner registry sheet: outputs would republish it.
OUTPUT_FREE = {"notebooks/01c_dim_fantasy_teams_seed.ipynb"}


def _allowed(addr: str) -> bool:
    addr = addr.lower()
    domain = addr.rsplit("@", 1)[1]
    return addr in ALLOW_EXACT or any(
        domain == d or domain.endswith("." + d) for d in ALLOW_DOMAIN_SUFFIX)


def _scan_text(rel: str, raw: bytes) -> list[str]:
    if b"\0" in raw[:8192]:
        return []  # binary
    hits = []
    for n, line in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
        bad = [a for a in EMAIL_RE.findall(line) if not _allowed(a)]
        if bad:
            hits.append(f"{rel}:{n}: {len(bad)} email-shaped string(s)")
    return hits


def _scan_parquet(rel: str, path: Path) -> list[str]:
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    hits = [f"{rel}: column '{c}' looks like PII" for c in table.column_names if "email" in c.lower()]
    for name in table.column_names:
        col = table.column(name)
        if not (pa.types.is_string(col.type) or pa.types.is_large_string(col.type)):
            continue
        vals = pc.unique(pc.drop_null(col)).to_pylist()
        bad = sum(1 for v in vals for a in EMAIL_RE.findall(v) if not _allowed(a))
        if bad:
            hits.append(f"{rel}: column '{name}' has {bad} email-shaped value(s)")
    return hits


def _scan_outputs(rel: str, raw: bytes) -> list[str]:
    nb = json.loads(raw)
    n = sum(1 for c in nb["cells"] if c.get("outputs"))
    return [f"{rel}: {n} cell(s) with saved outputs (run nbstripout)"] if n else []


def scan(rel: str) -> list[str]:
    path = REPO / rel
    if not path.is_file():
        return []  # deleted in this commit
    if rel.endswith(".parquet"):
        return _scan_parquet(rel, path)
    raw = path.read_bytes()
    hits = _scan_text(rel, raw)
    if rel in OUTPUT_FREE:
        hits += _scan_outputs(rel, raw)
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--all", action="store_true", help="scan every tracked file")
    args = ap.parse_args()

    if args.all:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, check=True,
                             capture_output=True).stdout
        files = [f for f in out.decode().split("\0") if f]
    else:
        files = [Path(f).resolve().relative_to(REPO).as_posix() for f in args.files]

    hits = [h for f in files for h in scan(f)]
    for h in hits:
        print(f"PII: {h}")
    if hits:
        print("\nOwner PII must not be committed to this public repo "
              "(it lives in Supabase shared.owner). Remove it, or extend "
              "ALLOW_EXACT / ALLOW_DOMAIN_SUFFIX in scripts/check_pii.py only "
              "for non-personal addresses.")
        return 1
    print(f"check_pii: {len(files)} file(s) clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
