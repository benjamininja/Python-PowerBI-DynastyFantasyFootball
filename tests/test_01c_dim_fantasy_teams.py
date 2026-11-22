import json
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent


class _Cfg:
    total_cap = 500
    num_teams = 28


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
    assert str(out["team_abbr"].dtype) == "string"


@pytest.mark.parametrize("n", [27, 29])
def test_wrong_row_count_exits_with_both_counts(n):
    sheet = _sheet(True)
    sheet = sheet.iloc[:n] if n < 28 else pd.concat([sheet, sheet.iloc[[0]].assign(**{"Team ID": "A99", "Fantrax-TeamId": "fx99"})])
    with pytest.raises(SystemExit) as e:
        _load_build()(sheet, _Cfg())
    msg = str(e.value)
    assert f"{n} rows" in msg and "28 teams" in msg and "team-manifest" in msg
    assert "\n" not in msg


def test_null_team_key_exits():
    sheet = _sheet(True)
    sheet.loc[3, "Team ID"] = None
    with pytest.raises(SystemExit, match="Team ID is blank on 1 rows"):
        _load_build()(sheet, _Cfg())


def test_duplicate_team_key_exits():
    sheet = _sheet(True)
    sheet.loc[3, "Team ID"] = sheet.loc[2, "Team ID"]
    with pytest.raises(SystemExit, match="repeated on 1"):
        _load_build()(sheet, _Cfg())


def test_other_required_column_still_required():
    with pytest.raises(ValueError, match="missing expected columns"):
        _load_build()(_sheet(False).drop(columns=["Team Name"]), _Cfg())
