"""Check the Sheets key signs in and reads the team-manifest tab (#643).

Signs in through etl_helpers (the path 01c uses) and reads the tab. Prints
`ok` and a row count, or one line naming the failing check. It prints no
cell, no value and no upstream message, writes no data and touches no store.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))
import etl_helpers as etl  # noqa: E402

COLUMNS = ["Team ID", "Team Name", "Fantrax-TeamId", "Division"]


def run() -> str:
    try:
        df = etl.read_sheet_tab(etl.CFG.team_sheet_id, etl.CFG.team_sheet_gid, columns=COLUMNS)
    except (etl.SheetsAuthError, RuntimeError) as e:
        return f"FAIL: {e}"
    except Exception as e:
        return f"FAIL: reading the team-manifest tab raised {type(e).__name__}."
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        return f"FAIL: the tab is missing {len(missing)} expected column(s)."
    return f"ok: signed in and read the team-manifest tab, {len(df)} rows."


def main() -> int:
    line = run()
    print(line)
    return 0 if line.startswith("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
