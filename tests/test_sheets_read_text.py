"""`read_sheet_tab(..., text=[...])` (#548 brief 3): a column that must be text is
read by its stored values, kept as strings exactly as stored, and refused when a
cell is stored as a number. Fakes only: the session returns made-up JSON
payloads the way the values API shapes them, so the whole reader runs and nothing
is patched out. No network, no key and no real id."""
import sys
from pathlib import Path
from urllib.parse import unquote

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))

import etl_helpers as etl

GID = "42"
TITLE = "Owners"
HEADER = ["team", "discord_user_id", "note"]
ID_17, ID_18, ID_19 = "10000000000000001", "200000000000000002", "3000000000000000003"
TOKEN = "tok"


class Resp:
    def __init__(self, body):
        self.status_code, self._body = 200, body

    def json(self):
        return self._body


def displayed(value):
    """What the sheet shows for a cell: a text cell as it is, a number as bare digits."""
    return value if isinstance(value, str) else str(value)


class Session:
    """The values API over a tab whose cells are typed as stored (str, int, float, bool)."""

    def __init__(self, rows, header=HEADER, gid=GID):
        self.rows, self.header, self.gid, self.calls = rows, header, gid, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": unquote(url), "params": params})
        if url.endswith("values:batchGet"):
            unformatted = ("valueRenderOption", "UNFORMATTED_VALUE") in params
            ranges = []
            for key, rng in params:
                if key != "ranges":
                    continue
                index = ord(rng.rsplit("!", 1)[1].split(":")[0]) - 65
                col = [self.header[index]] + [r[index] for r in self.rows]
                if not unformatted:
                    col = [displayed(v) for v in col]
                while col and col[-1] == "":
                    col.pop()
                ranges.append({"range": rng, "values": [col]})
            return Resp({"valueRanges": ranges})
        if "/values/" in unquote(url):
            return Resp({"range": f"'{TITLE}'!1:1", "values": [self.header]})
        return Resp({"sheets": [{"properties": {"sheetId": int(self.gid), "title": TITLE}}]})


def read(rows, text=("discord_user_id",), **kw):
    session = Session(rows, **kw)
    frame = etl.read_sheet_tab("SID", GID, ["team", "discord_user_id"], text=text, token=TOKEN, session=session)
    return frame, session


def batch_calls(session):
    return [c for c in session.calls if c["url"].endswith("values:batchGet")]


class TestATextColumn:
    def test_ids_of_seventeen_to_nineteen_digits_arrive_in_full_as_strings(self):
        frame, _ = read([["A", ID_17, "x"], ["B", ID_18, "x"], ["C", ID_19, "x"]])
        assert list(frame["discord_user_id"]) == [ID_17, ID_18, ID_19]
        assert all(isinstance(v, str) for v in frame["discord_user_id"])
        assert frame["discord_user_id"].dtype.kind == "O"

    def test_a_leading_zero_and_spacing_are_kept_as_stored(self):
        frame, _ = read([["A", "0" + ID_17, "x"], ["B", " " + ID_18, "x"]])
        assert list(frame["discord_user_id"]) == ["0" + ID_17, " " + ID_18]

    def test_the_other_columns_read_as_they_always_did(self):
        frame, _ = read([["A", ID_17, "x"], ["B", ID_18, "x"]])
        assert list(frame["team"]) == ["A", "B"] and frame["team"].dtype.kind == "O"

    def test_a_blank_cell_among_ids_is_a_missing_value_and_does_not_stop_the_read(self):
        frame, _ = read([["A", ID_17, "x"], ["B", "", "x"], ["C", ID_18, "x"]])
        assert frame["discord_user_id"].isna().tolist() == [False, True, False]
        assert frame["discord_user_id"].iloc[2] == ID_18

    def test_trailing_blank_cells_the_api_leaves_out_are_missing_values(self):
        frame, _ = read([["A", ID_17, "x"], ["B", "", "x"]])
        assert len(frame) == 2 and frame["discord_user_id"].isna().tolist() == [False, True]

    def test_only_the_text_column_is_asked_for_its_stored_values(self):
        _, session = read([["A", ID_17, "x"]])
        unformatted = [c for c in batch_calls(session) if ("valueRenderOption", "UNFORMATTED_VALUE") in c["params"]]
        plain = [c for c in batch_calls(session) if c not in unformatted]
        assert len(unformatted) == 1 and len(plain) == 1
        assert [r for k, r in unformatted[0]["params"] if k == "ranges"] == [f"'{TITLE}'!B:B"]
        assert [r for k, r in plain[0]["params"] if k == "ranges"] == [f"'{TITLE}'!A:A"]
        assert not [1 for k, _ in plain[0]["params"] if k == "valueRenderOption"]

    def test_a_text_column_the_header_lacks_is_left_out_like_any_other(self):
        session = Session([["A", "x"]], header=["team", "note"])
        frame = etl.read_sheet_tab("SID", GID, ["team", "discord_user_id"], text=["discord_user_id"],
                                   token=TOKEN, session=session)
        assert list(frame.columns) == ["team"]

    def test_a_tab_whose_only_wanted_column_is_text_reads(self):
        session = Session([["A", ID_17, "x"]])
        frame = etl.read_sheet_tab("SID", GID, ["discord_user_id"], text=["discord_user_id"],
                                   token=TOKEN, session=session)
        assert list(frame["discord_user_id"]) == [ID_17]


class TestANumberCellIsRefused:
    @pytest.mark.parametrize("cell", [123456789012345000, 123456789012345678, 1.23456789012345e17, 12345, True])
    def test_a_cell_stored_as_a_number_raises_with_its_row_and_no_value(self, cell):
        with pytest.raises(etl.SheetsNumberCells) as info:
            read([["A", ID_17, "x"], ["B", cell, "x"], ["C", ID_18, "x"]])
        assert info.value.column == "discord_user_id" and info.value.rows == [3]
        assert str(info.value) == "Google Sheets: 1 cell(s) of column discord_user_id are stored as numbers (rows 3)"
        assert str(cell) not in str(info.value)

    def test_a_lone_number_among_text_ids_is_caught(self):
        with pytest.raises(etl.SheetsNumberCells) as info:
            read([["A", ID_17, "x"], ["B", ID_18, "x"], ["C", 123456789012345000, "x"], ["D", ID_19, "x"]])
        assert info.value.rows == [4]

    def test_every_number_cell_is_listed(self):
        with pytest.raises(etl.SheetsNumberCells) as info:
            read([["A", 1, "x"], ["B", ID_17, "x"], ["C", 2.5, "x"]])
        assert info.value.rows == [2, 4]

    def test_a_whole_column_of_numbers_is_refused_though_the_displayed_digits_look_right(self):
        rows = [["A", int(ID_17), "x"], ["B", int(ID_18), "x"]]
        assert Session(rows).get("https://x/values:batchGet", [("ranges", f"'{TITLE}'!B:B")])\
            .json()["valueRanges"][0]["values"][0][1] == ID_17
        with pytest.raises(etl.SheetsNumberCells):
            read(rows)

    def test_the_error_is_a_runtime_error_so_a_caller_that_catches_one_still_stops(self):
        assert issubclass(etl.SheetsNumberCells, RuntimeError)


class TestWithoutTextTheReadIsTheOneItAlwaysWas:
    ROWS = [["A", ID_17, "x"], ["B", ID_18, "x"]]

    def test_the_request_has_no_render_option_and_makes_the_same_three_calls(self):
        session = Session(self.ROWS)
        etl.read_sheet_tab("SID", GID, ["team", "discord_user_id"], token=TOKEN, session=session)
        assert len(session.calls) == 3
        assert not [1 for c in batch_calls(session) for k, _ in c["params"] if k == "valueRenderOption"]
        assert batch_calls(session)[0]["params"][-1] == ("majorDimension", "COLUMNS")

    def test_digit_text_is_still_parsed_as_a_number_for_a_caller_that_asks_for_no_text(self):
        frame = etl.read_sheet_tab("SID", GID, ["team", "discord_user_id"], token=TOKEN, session=Session(self.ROWS))
        assert frame["discord_user_id"].dtype.kind == "i"

    def test_a_number_cell_is_not_refused_when_no_text_column_is_named(self):
        rows = [["A", 123456789012345000, "x"]]
        frame = etl.read_sheet_tab("SID", GID, ["team", "discord_user_id"], token=TOKEN, session=Session(rows))
        assert len(frame) == 1

    def test_the_result_equals_the_csv_read_of_the_same_content(self):
        frame = etl.read_sheet_tab("SID", GID, ["team", "note"], token=TOKEN, session=Session(self.ROWS))
        pd.testing.assert_frame_equal(frame, pd.DataFrame({"team": ["A", "B"], "note": ["x", "x"]}))
