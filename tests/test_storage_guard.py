"""Static guard for the storage seam (ADR-0014, #77).

Every dim/fact table is read and written through `etl_helpers.read_table` /
`write_table`. This test fails on any parquet I/O call in `notebooks/` or
`scripts/` (`.py` lines and `.ipynb` code cells) outside the seam section of
`etl_helpers.py`, so a new writer cannot go round the seam's schema and grain
guards, and the Postgres backend has one place to plug in.

An exception is named here with its reason. Add one only with the owner's
decision behind it.
"""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SEAM_FILE = "notebooks/etl_helpers.py"
SEAM_START = "# Storage seam (ADR-0014, #77)"
SEAM_END = "def classify_draft_type("

PANDAS_IO = re.compile(r"\b(read_parquet|to_parquet)\b")
ARROW_IO = re.compile(r"\bpq\.\w+|\bpyarrow\.parquet\.\w+\(|\bParquet(File|Writer|Dataset)\b")

# (file, pattern found on the line) -> why it may stay.
ALLOWED = {
    # The owner's decision of 2026-10-12: fact_fantasy_teams is keyed
    # (team_key, gsis_id) and the seam refuses a missing key, so a rostered
    # player with no gsis_id would stop the scheduled run. #97 rewrites 02e,
    # moves this write into the seam under (team_key, scorer_id) and deletes
    # this entry.
    ("notebooks/02e_fact_fantasy_teams_derive.py", "fact_fantasy_teams.to_parquet(FFT_PATH, index=False)"):
        "#97",
    # Not table I/O: the row count in the footer of the copy git holds at HEAD.
    ("notebooks/etl_checks.py", "pq.ParquetFile(io.BytesIO(r.stdout)).metadata.num_rows"):
        "reads git's bytes, not the store",
    # Not table I/O: the PII scan opens whatever file it is handed.
    ("scripts/check_pii.py", "pq.read_table(path)"):
        "scans a file for PII",
}


def code_lines(path: Path):
    """(line number or cell id, text) for every code line of a .py or .ipynb."""
    if path.suffix == ".py":
        yield from enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
    else:
        for cell in json.loads(path.read_text(encoding="utf-8"))["cells"]:
            if cell["cell_type"] == "code":
                for line in "".join(cell["source"]).splitlines():
                    yield cell.get("id"), line


def seam_lines() -> set[int]:
    lines = (REPO / SEAM_FILE).read_text(encoding="utf-8").splitlines()
    start = next(i for i, l in enumerate(lines, 1) if l.startswith(SEAM_START))
    end = next(i for i, l in enumerate(lines, 1) if l.startswith(SEAM_END))
    assert start < end
    return set(range(start, end))


def parquet_io():
    """Every parquet I/O call outside the seam: (file, where, line)."""
    seam = seam_lines()
    for root in ("notebooks", "scripts"):
        for path in sorted((REPO / root).rglob("*")):
            if path.suffix not in (".py", ".ipynb"):
                continue
            rel = path.relative_to(REPO).as_posix()
            for where, line in code_lines(path):
                if line.lstrip().startswith("#"):
                    continue
                if not (PANDAS_IO.search(line) or ARROW_IO.search(line)):
                    continue
                if rel == SEAM_FILE and where in seam:
                    continue
                yield rel, where, line.strip()


def test_no_parquet_io_outside_the_seam():
    strays = [(rel, where, line) for rel, where, line in parquet_io()
              if not any(rel == f and text in line for f, text in ALLOWED)]
    assert not strays, "parquet I/O outside etl_helpers' storage seam:\n" + "\n".join(
        f"  {rel}:{where}: {line}" for rel, where, line in strays)


def test_every_exception_is_still_needed():
    """A named exception whose line is gone must be deleted from ALLOWED."""
    found = {(rel, line) for rel, _, line in parquet_io()}
    stale = [key for key in ALLOWED if not any(key[0] == rel and key[1] in line for rel, line in found)]
    assert not stale, f"exceptions with no matching line: {stale}"


def test_the_seam_is_where_the_guard_thinks_it_is():
    """The seam section holds the backend's parquet calls; if it moved, the
    guard above would be excusing the wrong lines."""
    seam = seam_lines()
    calls = [i for i, line in code_lines(REPO / SEAM_FILE) if PANDAS_IO.search(line) and i in seam]
    assert len(calls) >= 3
