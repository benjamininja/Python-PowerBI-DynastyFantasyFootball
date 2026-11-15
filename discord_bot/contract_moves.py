"""The commissioners' contract lists, as an xlsx and as table lines (#545).

One formatter for both outputs, built only from the published
`fact_contract_move` snapshot and `dim_fantasy_teams` (for the team name). No
`discord` import and no ETL import: the bot's deploy root cannot reach
`notebooks/`, and the post step of PR 3 imports this module too.
"""

from __future__ import annotations

import math
from datetime import date
from io import BytesIO

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

LIST_LABELS = {"minor-to-1st": "Minor → 1st", "expiring": "Expiring", "decision": "Decision"}
LISTS = tuple(LIST_LABELS)
_LIST_NOUNS = {
    "minor-to-1st": "Minor-to-1st moves",
    "expiring": "Expiring contracts",
    "decision": "Decision-table contracts",
}

CONFERENCES = ("A", "B")
OTHER_TAB = "Unassigned"

XLSX_COLUMNS = [
    ("Team", "team"), ("Division", "division"), ("Player", "player_name"), ("Pos", "position"),
    ("NFL Team", "nfl_team"), ("List", "list_label"), ("Contract now", "contract_now"),
    ("Move to", "move_to"), ("Why", "reason"), ("NFL games", "nfl_games"),
    ("Roster slot", "roster_slot"), ("Salary", "salary"), ("Status", "status"),
]
_NUMBER_FORMATS = {"nfl_games": "0", "salary": "$#,##0"}
_MAX_COL_WIDTH = 60

TABLE_COLUMNS = [
    ("Team", "team", 12), ("Player", "player_name", 18), ("Pos", "position", 3),
    ("Contract now", "contract_now", 12), ("Move to", "move_to", None), ("Status", "status", None),
]
FIELD_LIMIT = 1024
_FENCE = len("```\n") + len("\n```")


def text(value: object) -> str:
    """A cell as text: a missing value (NaN, NA, None) is blank, never 'nan'."""
    return "" if value is None or pd.isna(value) else str(value)


def number(value: object) -> int | float | None:
    if value is None or pd.isna(value):
        return None
    out = float(value)
    if not math.isfinite(out):
        return None
    return int(out) if out.is_integer() else out


def prepare(lists: pd.DataFrame, teams: pd.DataFrame, list_name: str | None = None,
            team_key: str | None = None) -> pd.DataFrame:
    """The published rows with the team name beside them, optionally one list and
    one team, in a fixed order: conference, team, list, player."""
    out = lists.copy()
    if list_name is not None:
        out = out[out["list_name"] == list_name]
    if team_key is not None:
        out = out[out["team_key"] == team_key]
    names = teams.drop_duplicates("team_key").set_index("team_key")["team_name"]
    out["team"] = out["team_key"].map(names).fillna(out["team_key"])
    out["list_label"] = out["list_name"].map(LIST_LABELS).fillna(out["list_name"])
    order = {name: i for i, name in enumerate(LISTS)}
    out["_list_order"] = out["list_name"].map(order).fillna(len(order))
    out["_player"] = out["player_name"].map(text).str.lower()
    out = out.sort_values(["conference", "team", "_list_order", "_player"],
                          kind="stable", na_position="last")
    return out.drop(columns=["_list_order", "_player"]).reset_index(drop=True)


def empty_message(list_name: str, team_name: str | None = None,
                  opens: date | None = None, today: date | None = None) -> str:
    """What a list says when it has no rows. Before its window opens it says
    when; once open it says only that nothing is due."""
    if opens is not None and today is not None and today < opens:
        return f"Nothing due yet. {_LIST_NOUNS[list_name]} appear from {opens.isoformat()}."
    label = LIST_LABELS[list_name]
    if team_name:
        return f"Nothing due for {team_name} on the {label} list."
    return f"Nothing due on the {label} list."


def status_summary(rows: pd.DataFrame) -> str:
    """`Due now 3 · Due within 7 days 9`, from the status values in the rows."""
    counts = rows["status"].map(text).value_counts()
    return " · ".join(f"{status} {n}" for status, n in counts.items() if status)


def _tabs(rows: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    tabs = [(f"Conference {c}", rows[rows["conference"] == c]) for c in CONFERENCES]
    rest = rows[~rows["conference"].isin(CONFERENCES)]
    if len(rest):
        tabs.append((OTHER_TAB, rest))
    return tabs


def _cell(row: pd.Series, source: str) -> object:
    value = row[source]
    return number(value) if source in _NUMBER_FORMATS else text(value)


def _write_tab(ws, rows: pd.DataFrame, table_name: str) -> None:
    headers = [header for header, _ in XLSX_COLUMNS]
    ws.append(headers)
    for _, row in rows.iterrows():
        ws.append([_cell(row, source) for _, source in XLSX_COLUMNS])
    last_col, last_row = get_column_letter(len(headers)), len(rows) + 1
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for i, (_, source) in enumerate(XLSX_COLUMNS, start=1):
        width = max(len(str(c.value)) for c in ws[get_column_letter(i)] if c.value is not None)
        ws.column_dimensions[get_column_letter(i)].width = min(width + 2, _MAX_COL_WIDTH)
        if source in _NUMBER_FORMATS:
            for c in ws[get_column_letter(i)][1:]:
                c.number_format = _NUMBER_FORMATS[source]
                c.alignment = Alignment(horizontal="right")
    ws.freeze_panes = "A2"
    if len(rows):
        table = Table(displayName=table_name, ref=f"A1:{last_col}{last_row}")
        table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        ws.add_table(table)
    else:
        ws.auto_filter.ref = f"A1:{last_col}1"


def xlsx_bytes(rows: pd.DataFrame) -> bytes:
    """One tab per conference (A, B), each an Excel table with filters, one row
    per roster copy. A tab with no rows holds its header only, since Excel
    rejects a table with no data row. Rows of a team in neither conference are
    never dropped: they get a third tab."""
    book = Workbook()
    book.remove(book.active)
    for name, part in _tabs(rows):
        _write_tab(book.create_sheet(name), part, name.replace(" ", ""))
    out = BytesIO()
    book.save(out)
    return out.getvalue()


def table_chunks(rows: pd.DataFrame) -> list[list[str]]:
    """The table lines (Team, Player, Pos, Contract now, Move to, Status), cut
    into chunks whose code block fits one embed field. Every chunk repeats the
    header so a field reads on its own."""
    if rows.empty:
        return []
    widths = []
    for header, source, cap in TABLE_COLUMNS:
        longest = max([len(header)] + [len(text(v)) for v in rows[source]])
        widths.append(min(longest, cap) if cap else longest)

    def line(values: list[str]) -> str:
        cells = [v[:w].ljust(w) for v, w in zip(values, widths)]
        return " ".join(cells).rstrip()

    header = line([h for h, _, _ in TABLE_COLUMNS])
    body = [line([text(row[source]) for _, source, _ in TABLE_COLUMNS])
            for _, row in rows.iterrows()]
    chunks: list[list[str]] = []
    current: list[str] = []
    size = _FENCE + len(header)
    for entry in body:
        if current and size + 1 + len(entry) > FIELD_LIMIT:
            chunks.append(current)
            current, size = [], _FENCE + len(header)
        current.append(entry)
        size += 1 + len(entry)
    chunks.append(current)
    return [[header] + chunk for chunk in chunks]
