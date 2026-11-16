import json
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent


class _Cfg:
    total_cap = 500


def _load_build():
    nb = json.loads((REPO / "notebooks" / "01c_dim_fantasy_teams_seed.ipynb").read_text(encoding="utf-8"))
    cell = next(c for c in nb["cells"] if c["id"] == "39c742bb")
    src = cell["source"] if isinstance(cell["source"], str) else "".join(cell["source"])
    ns = {"pd": pd, "LeagueConfig": object}
    exec(src[: src.index("dim_fantasy_teams = build_dim_fantasy_teams")], ns)
    return ns["build_dim_fantasy_teams"]


def _sheet(with_abbr):
    rows = []
    for i in range(28):
        conf, div = ("A", "Riddell") if i < 14 else ("B", "Wilson")
        row = {
            "Division": div,
            "Team Name": f"Team {i}",
            "Team ID": f"{conf}{i % 14 + 1:02d}",
            "Fantrax-TeamId": f"fx{i}",
            "Roster": "x",
        }
        if with_abbr:
            row["Team Abbreviation"] = f"T{i}"
        rows.append(row)
    return pd.DataFrame(rows)


COLS = ["team_key", "team_name", "team_abbr", "fantrax_team_id",
        "conference", "division", "original_cap", "reinvestment_cap"]


def test_with_abbreviation_column_reads_it():
    out = _load_build()(_sheet(True), _Cfg())
    assert len(out) == 28
    assert list(out.columns) == COLS
    assert out["team_abbr"].tolist() == [f"T{i}" for i in range(28)]


def test_without_abbreviation_column_is_null():
    out = _load_build()(_sheet(False), _Cfg())
    assert len(out) == 28
    assert list(out.columns) == COLS
    assert out["team_abbr"].isna().all()


def test_other_required_column_still_required():
    with pytest.raises(ValueError, match="missing expected columns"):
        _load_build()(_sheet(False).drop(columns=["Team Name"]), _Cfg())
