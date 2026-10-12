import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "pbi/mouserat2/Mouserat2.SemanticModel/definition/tables"
MEASURES = (TABLES / "_Measures.tmdl").read_text(encoding="utf-8")
FANTASY_TEAMS = (TABLES / "Fact_FantasyTeams.tmdl").read_text(encoding="utf-8")
DERIVE_02E = (ROOT / "notebooks/02e_fact_fantasy_teams_derive.py").read_text(encoding="utf-8")

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


def _slot_to_status() -> dict:
    for node in ast.parse(DERIVE_02E).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "SLOT_TO_STATUS" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("SLOT_TO_STATUS not found in 02e")


def test_exempt_slot_literals_are_values_02e_writes():
    """The DAX compares RosterStatus with literals. When #110 renames the
    column's values, a literal that 02e no longer writes would silently charge
    that slot again."""
    written = set(_slot_to_status().values())
    for name in EXEMPT_SLOT_MEASURES:
        literals = set(re.findall(r'RosterStatus\]\s*<>\s*"([^"]+)"', _body(name)))
        assert literals == {"Minors", "Inj Res"}, f"{name}: exempt slots are {literals}"
        assert literals <= written, f"{name}: {literals - written} not written by 02e"


def test_active_dead_money_measures_read_fact_dead_money():
    for name in ACTIVE_DEAD_MONEY:
        body = _body(name)
        assert "Fact_DeadMoney[DeadMoney]" in body, name
        assert "Fact_FantasyTeams" not in body, name
        assert "Status" not in body, name


def test_status_column_is_retired():
    assert "sourceColumn: status" not in FANTASY_TEAMS
    assert '"status":' not in DERIVE_02E
