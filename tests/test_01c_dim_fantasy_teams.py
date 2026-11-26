import importlib
import json
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent


class _Cfg:
    total_cap = 500
    num_teams = 28


def _load(name="build_dim_fantasy_teams"):
    nb = json.loads((REPO / "notebooks" / "01c_dim_fantasy_teams_seed.ipynb").read_text(encoding="utf-8"))
    cell = next(c for c in nb["cells"] if c["id"] == "39c742bb")
    src = cell["source"] if isinstance(cell["source"], str) else "".join(cell["source"])
    ns = {"pd": pd, "LeagueConfig": object}
    exec(src[: src.index("dim_fantasy_teams = build_dim_fantasy_teams")], ns)
    return ns[name]


def _load_build():
    return _load()


def _sheet(with_abbr=False):
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


COLS = ["team_key", "team_name", "fantrax_team_id",
        "conference", "division", "original_cap", "reinvestment_cap"]


def test_the_table_has_no_abbreviation_column():
    out = _load_build()(_sheet(), _Cfg())
    assert len(out) == 28
    assert list(out.columns) == COLS


def test_a_sheet_abbreviation_column_is_not_carried():
    out = _load_build()(_sheet(with_abbr=True), _Cfg())
    assert list(out.columns) == COLS


@pytest.mark.parametrize("n", [27, 29])
def test_wrong_row_count_exits_with_both_counts(n):
    sheet = _sheet()
    sheet = sheet.iloc[:n] if n < 28 else pd.concat([sheet, sheet.iloc[[0]].assign(**{"Team ID": "A99", "Fantrax-TeamId": "fx99"})])
    with pytest.raises(SystemExit) as e:
        _load_build()(sheet, _Cfg())
    msg = str(e.value)
    assert f"{n} rows" in msg and "28 teams" in msg and "team-manifest" in msg
    assert "\n" not in msg


def test_null_team_key_exits():
    sheet = _sheet()
    sheet.loc[3, "Team ID"] = None
    with pytest.raises(SystemExit, match="Team ID is blank on 1 rows"):
        _load_build()(sheet, _Cfg())


def test_duplicate_team_key_exits():
    sheet = _sheet()
    sheet.loc[3, "Team ID"] = sheet.loc[2, "Team ID"]
    with pytest.raises(SystemExit, match="repeated on 1"):
        _load_build()(sheet, _Cfg())


def test_other_required_column_still_required():
    with pytest.raises(ValueError, match="missing expected columns"):
        _load_build()(_sheet().drop(columns=["Team Name"]), _Cfg())


# -- Three leagues in one workbook (#724) --------------------------------------
# Made-up frames shaped like the workbook: three leagues of 28 teams, six divisions,
# and a League Associations tab with a helper column and blank rows.
FB_ID = "fb-made-up-id"
FB, HOOPS, BALL = "Made Up Football", "Made Up Hoops", "Made Up Ball"


def _other_league(name, divs, tag):
    return pd.DataFrame([{
        "Division": divs[i // 14],
        "Team Name": f"{tag} Team {i}",
        "Team ID": f"{tag}{i:02d}",
        "Fantrax-TeamId": f"{tag}fx{i}",
        "Roster": "x",
        "League Name": name,
    } for i in range(28)])


def _workbook():
    fb = _sheet().assign(**{"League Name": FB})
    hoops = _other_league(HOOPS, ["North", "South"], "H")
    ball = _other_league(BALL, ["East", "West"], "K")
    return pd.concat([hoops, fb, ball], ignore_index=True)


def _leagues(rows=None):
    rows = rows if rows is not None else [
        ("Football", FB, FB_ID), ("Basketball", HOOPS, "hoops-id"), ("Baseball", BALL, "ball-id")]
    blank = {"Sport": None, "League Name": None, "League ID": None, "Helper": None}
    out = [blank]
    for sport, name, lid in rows:
        out += [{"Sport": sport, "League Name": name, "League ID": lid, "Helper": "h"}, blank]
    return pd.DataFrame(out)


def _keep(teams, leagues=None):
    return _load("keep_league_rows")(teams, _leagues() if leagues is None else leagues, FB_ID)


def test_the_football_league_rows_are_kept_and_built(capsys):
    kept = _keep(_workbook())
    assert len(kept) == 28
    assert set(kept["League Name"]) == {FB}
    out = _load_build()(kept, _Cfg())
    assert list(out.columns) == COLS
    assert set(out["division"]) == {"Riddell", "Wilson"}
    printed = capsys.readouterr().out
    assert "skipped 56 rows of 2 other leagues" in printed and "[28, 28]" in printed
    assert HOOPS not in printed and BALL not in printed


def test_the_league_is_found_by_id_not_by_sport():
    leagues = _leagues([("Football", FB, FB_ID), ("Football", HOOPS, "hoops-id"),
                        ("Baseball", BALL, "ball-id")])
    assert set(_keep(_workbook(), leagues)["League Name"]) == {FB}


def test_with_the_other_leagues_absent_it_builds_as_before():
    only_fb = _sheet().assign(**{"League Name": FB})
    before = _load_build()(_sheet(), _Cfg())
    after = _load_build()(_keep(only_fb, _leagues([("Football", FB, FB_ID)])), _Cfg())
    pd.testing.assert_frame_equal(before, after)


@pytest.mark.parametrize("rows, n", [
    ([("Basketball", HOOPS, "hoops-id"), ("Baseball", BALL, "ball-id")], 0),
    ([("Football", FB, FB_ID), ("Football", HOOPS, FB_ID), ("Baseball", BALL, "ball-id")], 2),
])
def test_the_configured_id_needs_exactly_one_league_row(rows, n):
    with pytest.raises(SystemExit) as e:
        _keep(_workbook(), _leagues(rows))
    msg = str(e.value)
    assert f"League Associations has {n} rows" in msg and "\n" not in msg
    assert FB_ID not in msg and FB not in msg


def test_a_blank_league_name_on_the_id_row_stops():
    with pytest.raises(SystemExit, match="League Name is blank on the row"):
        _keep(_workbook(), _leagues([("Football", None, FB_ID), ("Basketball", HOOPS, "hoops-id"),
                                     ("Baseball", BALL, "ball-id")]))


def test_a_blank_team_league_name_stops():
    wb = _workbook()
    wb.loc[[0, 40], "League Name"] = [None, "  "]
    with pytest.raises(SystemExit, match="League Name is blank on 2 rows and not listed in League Associations on 0"):
        _keep(wb)


def test_an_unlisted_team_league_name_stops():
    wb = _workbook()
    wb.loc[5, "League Name"] = "Made Up Hockey"
    with pytest.raises(SystemExit) as e:
        _keep(wb)
    msg = str(e.value)
    assert "blank on 0 rows and not listed in League Associations on 1" in msg
    assert "Hockey" not in msg


def test_a_missing_league_column_stops_with_its_name():
    with pytest.raises(SystemExit, match="League Associations League ID"):
        _keep(_workbook(), _leagues().drop(columns=["League ID"]))
    with pytest.raises(SystemExit, match="team tab League Name"):
        _keep(_workbook().drop(columns=["League Name"]))


def test_an_unknown_division_in_the_kept_rows_still_stops():
    wb = _workbook()
    wb.loc[wb["League Name"].eq(FB).idxmax(), "Division"] = "North"
    with pytest.raises(ValueError, match="Unknown divisions"):
        _load_build()(_keep(wb), _Cfg())


def test_a_repeated_team_id_in_the_kept_rows_still_stops():
    wb = _workbook()
    fb_rows = wb.index[wb["League Name"].eq(FB)]
    wb.loc[fb_rows[3], "Team ID"] = wb.loc[fb_rows[2], "Team ID"]
    with pytest.raises(SystemExit, match="repeated on 1"):
        _load_build()(_keep(wb), _Cfg())


def test_a_blank_team_id_in_the_kept_rows_still_stops():
    wb = _workbook()
    wb.loc[wb.index[wb["League Name"].eq(FB)][3], "Team ID"] = None
    with pytest.raises(SystemExit, match="Team ID is blank on 1 rows"):
        _load_build()(_keep(wb), _Cfg())


def test_a_wrong_football_count_still_stops():
    wb = _workbook()
    wb = wb.drop(index=wb.index[wb["League Name"].eq(FB)][0])
    with pytest.raises(SystemExit, match="team-manifest has 27 rows"):
        _load_build()(_keep(wb), _Cfg())


def test_the_fantrax_league_id_has_one_home():
    import etl_helpers as etl
    fx = importlib.import_module("04a_fantrax_weekly_scrape")
    league_id = etl.CFG.fantrax_league_id
    assert fx.CFG.league_id == league_id
    assert f"/league/{league_id}/" in fx.CFG.players_ref_url
    assert f"/league/{league_id}/" in fx.CFG.ref_url
    src = (REPO / "notebooks" / "04a_fantrax_weekly_scrape.py").read_text(encoding="utf-8")
    code = [ln for ln in src.splitlines() if league_id in ln and not ln.lstrip().startswith("#")]
    assert code == []
