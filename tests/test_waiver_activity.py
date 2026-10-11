"""trade-bud's waiver-activity profile signal (#68; design from #63).

infer_waiver_activity counts a team's claim and drop rows on the roster
ledger. The tier and confidence rules run on a small ledger frame patched
into data_access; the last test checks the wiring on the real parquet.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mouserat_trade-bud" / "backend"))

import pandas as pd
import pytest

import data_access as da
import profiles


def ledger(counts):
    """{team_key: (claims, drops, other rows)} -> a ledger frame."""
    rows = []
    for team, (claims, drops, other) in counts.items():
        rows += [("claim", team)] * claims + [("drop", team)] * drops
        rows += [("startup_draft", team)] * other + [("trade", team)] * other
    return pd.DataFrame(rows, columns=["event_type", "team_key"])


@pytest.fixture
def patched(monkeypatch):
    def use(counts):
        frame = ledger(counts)
        real = da.read_parquet
        monkeypatch.setattr(
            da, "read_parquet",
            lambda name: frame if name == "fact_roster_transactions" else real(name))
    return use


class TestInferWaiverActivity:
    @pytest.mark.parametrize("claims, drops, tier, confidence", [
        (0, 0, "inactive", "low"),
        (1, 0, "occasional", "medium"),
        (0, 1, "occasional", "medium"),
        (2, 1, "occasional", "medium"),
        (3, 1, "active", "medium"),
        (9, 5, "active", "medium"),
    ])
    def test_tiers_and_confidence(self, patched, claims, drops, tier, confidence):
        patched({"A01": (claims, drops, 7)})
        assert profiles.infer_waiver_activity("A01") == {
            "waiver_activity": tier,
            "waiver_activity_confidence": confidence,
            "waiver_count": claims + drops,
        }

    def test_claims_and_drops_are_one_count(self, patched):
        patched({"A01": (2, 2, 0)})
        assert profiles.infer_waiver_activity("A01")["waiver_count"] == 4

    def test_other_event_types_and_other_teams_do_not_count(self, patched):
        patched({"A01": (0, 0, 30), "A02": (6, 6, 0)})
        assert profiles.infer_waiver_activity("A01")["waiver_count"] == 0
        assert profiles.infer_waiver_activity("A02")["waiver_count"] == 12

    def test_a_team_not_on_the_ledger_is_inactive(self, patched):
        patched({"A01": (3, 3, 0)})
        assert profiles.infer_waiver_activity("Z99")["waiver_activity"] == "inactive"

    def test_the_cut_points_are_its_own_constants(self):
        assert (profiles._WAIVER_ACTIVITY_ACTIVE, profiles._WAIVER_ACTIVITY_OCCASIONAL) == (4, 1)


class TestProfileWiring:
    def test_low_confidence_lists_the_field_only_when_low(self):
        base = {"stance_confidence": "high", "risk_confidence": "high",
                "trade_activity_confidence": "medium"}
        assert "waiver_activity" in profiles.low_confidence_fields(
            {**base, "waiver_activity_confidence": "low"})
        assert "waiver_activity" not in profiles.low_confidence_fields(
            {**base, "waiver_activity_confidence": "medium"})

    def test_build_profile_carries_the_signal_on_real_data(self):
        real = da.read_parquet("fact_roster_transactions")
        teams = da.read_parquet("dim_fantasy_teams")["team_key"]
        want = (real[real["event_type"].isin(["claim", "drop"])]
                .groupby("team_key").size().reindex(teams, fill_value=0))
        for team in (want.idxmax(), want.idxmin()):
            for mode in ("my", "counterparty"):
                p = profiles.build_profile(team, mode)
                assert p["waiver_count"] == int(want[team])
                assert p["waiver_activity"] in ("active", "occasional", "inactive")
            assert ("waiver_activity" in p["low_confidence_fields"]) == (want[team] == 0)
        # Every claim and drop on the ledger belongs to exactly one team's count.
        assert int(want.sum()) == int(real["event_type"].isin(["claim", "drop"]).sum())
