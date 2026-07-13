"""Unit tests for 04v_minor_contracts.py's pure diff/parse functions.

Per ADR-0008: build_worklist, eligibility_to_frame, rosters_to_frame, and
_header_index are I/O-free (the Playwright pulls are separate functions), so
they get fixture-driven unit tests. The two HIGH findings from the pre-merge
cap-ledger audit are pinned here: per-copy contract divergence across
conferences, and graduated-while-FA vanish detection.
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))

import pandas as pd

mv = importlib.import_module("04v_minor_contracts")


def _placement(rows):
    cols = ["team_key", "scorer_id", "player_name", "contract"]
    return pd.DataFrame(rows, columns=cols)


def _elig(rows):
    cols = ["scorer_id", "player_name", "fa_status", "contract"]
    return pd.DataFrame(rows, columns=cols)


class TestBuildWorklist:
    def test_eligible_rostered_copy_flips_to_minor(self):
        wl = mv.build_worklist(
            _elig([("x1", "Guy A", "taken", "1st")]),
            _placement([("A01", "x1", "Guy A", "1st")]),
        )
        assert len(wl) == 1
        a = wl.iloc[0]
        assert (a.team_key, a.from_contract, a.to_contract) == ("A01", "1st", "Minor")

    def test_diverging_conference_contracts_act_per_copy(self):
        # Duplicate-player league: 1st on A01, Minor on B13 — only the A01
        # copy needs a flip; the compliant B13 copy must NOT get an action.
        wl = mv.build_worklist(
            _elig([("x1", "Guy A", "taken", "1st")]),
            _placement([("A01", "x1", "Guy A", "1st"),
                        ("B13", "x1", "Guy A", "Minor")]),
        )
        assert list(wl.team_key) == ["A01"]

    def test_graduation_per_rostered_copy(self):
        wl = mv.build_worklist(
            _elig([]),
            _placement([("A01", "x1", "Guy A", "Minor"),
                        ("B13", "x1", "Guy A", "1st")]),
        )
        assert len(wl) == 1
        a = wl.iloc[0]
        assert (a.team_key, a.to_contract) == ("A01", "1st")
        assert "graduate" in a.reason

    def test_fa_copy_flips_to_minor_pool_level(self):
        wl = mv.build_worklist(
            _elig([("x2", "Guy B", "available", "FA")]),
            _placement([]),
        )
        a = wl.iloc[0]
        assert pd.isna(a.team_key) or a.team_key is None
        assert (a.fa_status, a.to_contract) == ("available", "Minor")

    def test_compliant_players_emit_nothing(self):
        wl = mv.build_worklist(
            _elig([("x1", "Guy A", "taken", "Minor"),
                   ("x2", "Guy B", "available", "Minor")]),
            _placement([("A01", "x1", "Guy A", "Minor")]),
        )
        assert wl.empty

    def test_vanished_while_fa_graduates_to_fa(self):
        # Eligible last snapshot, absent from BOTH pulls this week -> the
        # invisible-graduation case; only prev snapshot can catch it.
        prev = _elig([("x3", "Guy C", "available", "Minor")])
        wl = mv.build_worklist(_elig([]), _placement([]), prev)
        a = wl.iloc[0]
        assert (a.scorer_id, a.to_contract) == ("x3", "FA")
        assert bool(a.needs_verification)

    def test_vanished_but_now_rostered_is_not_vanished(self):
        # Left eligibility because they graduated AND got rostered — the
        # placement loop owns that case; vanish detection must skip it.
        prev = _elig([("x3", "Guy C", "available", "Minor")])
        wl = mv.build_worklist(
            _elig([]),
            _placement([("A01", "x3", "Guy C", "Minor")]),
            prev,
        )
        assert list(wl.reason) == ["crossed 20 GP — graduate off Minor"]

    def test_unknown_contract_flags_needs_verification(self):
        wl = mv.build_worklist(
            _elig([("x1", "Guy A", "taken", None)]),
            _placement([("A01", "x1", "Guy A", None)]),
        )
        assert bool(wl.iloc[0].needs_verification)


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
                         "t2": [self._row("x1", "Guy A", "9", "Minor")]})
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
        raw = self._raw({"t1": [self._row("x1", "Guy A", "9", "Minor"),
                                {"scorer": {}, "statusId": "3", "cells": []}]})
        df = mv.rosters_to_frame(raw, self._teams(["t1"]), 2026, "PRE")
        assert len(df) == 1
        assert df.iloc[0].roster_section == "Minors"
        assert df.iloc[0].contract == "Minor"
