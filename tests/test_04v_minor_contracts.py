"""Unit tests for 04v_minor_contracts.py's pure parse functions.

Per ADR-0008: eligibility_to_frame, rosters_to_frame, and _header_index are
I/O-free (the Playwright pulls are separate functions), so they get
fixture-driven unit tests.

The former TestBuildWorklist class is gone: ADR-0011 retired 04v's
eligibility-vs-contract diff and its write-side apply path, and ADR-0019 kept
them retired (Fantrax sets the `Minor` contract itself; 04v only records what
it shows). What survives is the parse layer that produces
fact_roster_placement — which is load-bearing (02e stamps roster_status from
it, the cap exemption follows that, and 02d reads its contract column).
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))

import pandas as pd

mv = importlib.import_module("04v_minor_contracts")


class TestHeaderIndex:
    def test_grid_tableheader(self):
        d = {"tableHeader": {"cells": [{"shortName": "Sal"}, {"shortName": "Con"}]}}
        assert mv._header_index(d) == {"Sal": 0, "Con": 1}

    def test_roster_table_header(self):
        d = {"header": {"cells": [{"shortName": "Age"}, {"shortName": "Con"}]}}
        assert mv._header_index(d)["Con"] == 1

    def test_missing_header_empty(self):
        assert mv._header_index({}) == {}


class TestRostersToFrame:
    @staticmethod
    def _raw(team_rows):
        """Minimal getTeamRosterInfo shape: one table, header with Sal/Con."""
        def resp(rows):
            return {"responses": [{"data": {"tables": [{
                "statusTotals": [{"id": "1", "name": "Active"},
                                 {"id": "9", "name": "Minors"}],
                "header": {"cells": [{"shortName": "Sal"}, {"shortName": "Con"}]},
                "rows": rows,
            }]}}]}
        return {tid: resp(rows) for tid, rows in team_rows.items()}

    @staticmethod
    def _row(sid, name, status_id, contract="1st"):
        # The contract is whatever Fantrax shows; placement does not set it. A
        # player in the Minors slot can be on "1st", and a "Minor" player can
        # sit Active (ADR-0019).
        return {"scorer": {"scorerId": sid, "name": name, "posShortNames": "RB"},
                "statusId": status_id,
                "cells": [{"content": "2,000,000"}, {"content": contract}]}

    def _teams(self, ids):
        return pd.DataFrame({"fantrax_team_id": ids,
                             "team_key": [f"K{i}" for i, _ in enumerate(ids)],
                             "team_name": ids})

    def test_grain_is_team_scorer(self):
        # Same scorer on two teams (one per conference) -> two rows.
        raw = self._raw({"t1": [self._row("x1", "Guy A", "1")],
                         "t2": [self._row("x1", "Guy A", "9")]})
        df = mv.rosters_to_frame(raw, self._teams(["t1", "t2"]), 2026, "PRE")
        assert len(df) == 2
        assert set(df.roster_section) == {"Active", "Minors"}

    def test_dedup_within_team(self):
        # Dual-eligible player repeated across a team's stat tables -> one row.
        raw = self._raw({"t1": [self._row("x1", "Guy A", "1"),
                                self._row("x1", "Guy A", "1")]})
        df = mv.rosters_to_frame(raw, self._teams(["t1"]), 2026, "PRE")
        assert len(df) == 1

    def test_empty_slots_skipped_and_status_mapped(self):
        # Empty slots (null scorerId) occur under every statusId -- skipped by
        # the missing scorer, not by section.
        raw = self._raw({"t1": [self._row("x1", "Guy A", "9"),
                                {"scorer": {}, "statusId": "3", "cells": []},
                                {"scorer": {"scorerId": None}, "statusId": "2",
                                 "cells": []}]})
        df = mv.rosters_to_frame(raw, self._teams(["t1"]), 2026, "PRE")
        assert len(df) == 1
        assert df.iloc[0].roster_section == "Minors"

    def test_ir_row_kept_via_fallback(self):
        # In-season statusId "3" is IR with real players -- must not be dropped.
        # Fixture statusTotals lacks "3", so the fallback names it.
        raw = self._raw({"t1": [self._row("x1", "Guy A", "3")]})
        df = mv.rosters_to_frame(raw, self._teams(["t1"]), 2026, "01")
        assert len(df) == 1
        assert df.iloc[0].roster_section == "Inj Res"
        assert df.iloc[0].status_id == "3"

    def test_live_status_totals_name_overrides_fallback(self):
        # Name differs from the fallback's "Inj Res", so this proves the live
        # statusTotals map wins rather than passing via the fallback.
        raw = self._raw({"t1": [self._row("x1", "Guy A", "3")]})
        tbl = raw["t1"]["responses"][0]["data"]["tables"][0]
        tbl["statusTotals"].append({"id": "3", "name": "IR"})
        df = mv.rosters_to_frame(raw, self._teams(["t1"]), 2026, "01")
        assert df.iloc[0].roster_section == "IR"

    def test_minors_placement_keeps_ordinary_contract(self):
        # Placement in the Minors squad does not change the contract (ADR-0011,
        # kept by ADR-0019): the parser records what Fantrax shows.
        raw = self._raw({"t1": [self._row("x1", "Guy A", "9", "1st")]})
        df = mv.rosters_to_frame(raw, self._teams(["t1"]), 2026, "PRE")
        assert df.iloc[0].roster_section == "Minors"
        assert df.iloc[0].contract == "1st"

    def test_unknown_status_id_passes_through_raw(self):
        # A section id in neither statusTotals nor the fallback must surface, not bin.
        raw = self._raw({"t1": [self._row("x1", "Guy A", "11")]})
        df = mv.rosters_to_frame(raw, self._teams(["t1"]), 2026, "PRE")
        assert df.iloc[0].roster_section == "11"
