import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "pbi/mouserat2/Mouserat2.SemanticModel/definition/tables"
MEASURES = (TABLES / "_Measures.tmdl").read_text(encoding="utf-8")
FANTASY_TEAMS = (TABLES / "Fact_FantasyTeams.tmdl").read_text(encoding="utf-8")
DERIVE_02E = (ROOT / "notebooks/02e_fact_fantasy_teams_derive.py").read_text(encoding="utf-8")
ETL_CAP = (ROOT / "notebooks/etl_cap.py").read_text(encoding="utf-8")

ACTIVE_DEAD_MONEY = (
    "Dead Money - Active - Current Year",
    "Dead Money - Active - Next Year",
    "Dead Money - Active - Total",
)
EXEMPT_SLOT_MEASURES = ("Active Roster Salary", "Remaining Salary Cap")


def _body(name: str) -> str:
    m = re.search(
        r"\tmeasure '" + re.escape(name) + r"' =(.*?)(?=\n\t(?:///|measure |column ))",
        MEASURES, re.S)
    assert m, f"measure {name!r} not found in _Measures.tmdl"
    return m.group(1)


def _exempt_slots() -> set:
    for node in ast.parse(ETL_CAP).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "EXEMPT_SLOTS" for t in node.targets):
            return set(ast.literal_eval(node.value.args[0]))
    raise AssertionError("EXEMPT_SLOTS not found in etl_cap.py")


def test_exempt_slot_literals_are_the_slots_the_cap_module_exempts():
    """The DAX compares RosterSlot with literals. A literal that is not one of
    etl_cap's exempt slots would charge that slot again, or exempt another."""
    for name in EXEMPT_SLOT_MEASURES:
        literals = set(re.findall(r'RosterSlot\]\s*<>\s*"([^"]+)"', _body(name)))
        assert literals == _exempt_slots(), f"{name}: exempt slots are {literals}"


def test_active_dead_money_measures_read_fact_dead_money():
    for name in ACTIVE_DEAD_MONEY:
        body = _body(name)
        assert "Fact_DeadMoney[DeadMoney]" in body, name
        assert "Fact_FantasyTeams" not in body, name
        assert "Status" not in body, name


def test_status_column_is_retired():
    assert "sourceColumn: status" not in FANTASY_TEAMS
    assert '"status":' not in DERIVE_02E


def test_roster_slot_replaces_roster_status():
    assert "sourceColumn: roster_slot" in FANTASY_TEAMS
    assert "roster_status" not in FANTASY_TEAMS and "roster_status" not in DERIVE_02E
    assert "RosterStatus" not in MEASURES
