"""A retired table's name stays out of the code (#117, ADR-0016).

Roster State (`fact_roster_state`, 04r) replaced the dated roster snapshot
04v used to write. Nothing that runs, ships or tests may still name the old
table: a reader that does would be reading a parquet nobody writes.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCANNED = ("notebooks", "discord_bot", "mouserat_trade-bud", "scripts", "tests")
SKIP_DIRS = {"__pycache__", ".ipynb_checkpoints", "_site"}

# Built by concatenation so this file does not match itself.
RETIRED = ("fact_roster_" + "placement",)


def _text(path: Path) -> str | None:
    """A file's text, or None for a binary file."""
    data = path.read_bytes()
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _scanned_files():
    for top in SCANNED:
        for path in sorted((REPO / top).rglob("*")):
            if path.is_file() and not SKIP_DIRS & set(path.relative_to(REPO).parts):
                yield path


def test_no_code_names_a_retired_table():
    hits = []
    for path in _scanned_files():
        text = _text(path)
        if text is None:
            continue
        hits += [f"{path.relative_to(REPO).as_posix()}: {name}"
                 for name in RETIRED if name in text]
    assert hits == []


def test_the_scan_reads_the_code():
    # Guards the walk itself: an empty or mis-rooted scan would pass vacuously.
    seen = {p.relative_to(REPO).as_posix() for p in _scanned_files()}
    assert {"notebooks/etl_checks.py", "discord_bot/capmath.py",
            "scripts/make_fixtures.py", "tests/test_etl_checks.py"} <= seen
    assert _text(REPO / "notebooks" / "etl_checks.py")
