"""Look-only run of the Table Gates and domain checks against a snapshot folder.

Usage: look_only_checks.py SNAPSHOT

SNAPSHOT is a folder of <table>.parquet files (an export of the published
snapshot). Reads only; files nothing; no database. Prints every finding and
the total, so a reviewer can read the Review checks that a Green run counts.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

if __name__ == "__main__":
    os.environ["ETL_STORAGE"] = "parquet"

REPO = Path(__file__).resolve().parent.parent
for _p in (REPO / "scripts", REPO / "notebooks"):
    sys.path.insert(0, str(_p))

import etl_checks  # noqa: E402

ALWAYS_SHOWN = ("salary_remaining", "roster_membership")


def run(snapshot: Path, registry: dict | None = None, out=print) -> int:
    results = etl_checks.run_suite(
        accepted_shrink=[], registry=registry, data_dir=Path(snapshot),
        head_rows=lambda table: None)
    total = 0
    for r in results:
        total += len(r.findings)
        if r.check in ALWAYS_SHOWN or r.findings or (r.tier == "gate" and not r.ok):
            out(r.tier, r.check, r.table, "ran" if r.ran else "notran",
                "findings=%d" % len(r.findings), "detail=", r.detail)
            for key, detail in r.findings[:10]:
                out("   ", key, "|", str(detail)[:300])
    out("TOTAL findings", total)
    return total


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: look_only_checks.py SNAPSHOT", file=sys.stderr)
        return 2
    snapshot = Path(argv[1])
    if not snapshot.is_dir():
        print(f"not a folder: {snapshot}", file=sys.stderr)
        return 2
    run(snapshot)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
