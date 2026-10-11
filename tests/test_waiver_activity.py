"""trade-bud's two claim-activity profile signals (#68; design from #63).

infer_waiver_activity counts a team's claim and drop rows on the roster
ledger whose claim_method is `waiver`; infer_free_agent_activity the ones
whose method is `free_agent`. Each tiers the team by its rank inside the
league on its own count. The rules run on a small ledger and league patched
into data_access; the last test checks the wiring on the real parquet.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mouserat_trade-bud" / "backend"))

import pandas as pd
import pytest

import data_access as da
import profiles

# (the signal's function, its ledger method, its field prefix, the other method)
SIGNALS = [
    pytest.param(profiles.infer_waiver_activity, "waiver", "waiver", "free_agent", id="waiver"),
    pytest.param(profiles.infer_free_agent_activity, "free_agent", "free_agent", "waiver",
                 id="free_agent"),
]


def ledger(counts, method, other_method):
    """{team_key: (claims, drops, other rows)} -> a ledger frame. The claims
    and drops carry `method`. Every team also gets `other` rows of each kind
    that must not count: a draft pick, a trade, a drop with no method and a
    claim of the other method."""
    rows = []
    for team, (claims, drops, other) in counts.items():
        rows += [("claim", team, method)] * claims + [("drop", team, method)] * drops
        rows += [("startup_draft", team, pd.NA), ("trade", team, pd.NA),
                 ("drop", team, pd.NA), ("claim", team, other_method)] * other
    frame = pd.DataFrame(rows, columns=["event_type", "team_key", "claim_method"])
    frame["claim_method"] = frame["claim_method"].astype("string")
    return frame


@pytest.fixture
def patched(monkeypatch):
    """The league is the teams named in `counts`."""
    def use(counts, method, other_method):
        frames = {"fact_roster_transactions": ledger(counts, method, other_method),
                  "dim_fantasy_teams": pd.DataFrame({"team_key": list(counts)})}
        real = da.read_parquet
        monkeypatch.setattr(
            da, "read_parquet", lambda name: frames[name] if name in frames else real(name))
    return use


def league(moves):
    """[moves per team] -> {team_key: (claims, drops, other rows)}."""
    return {f"T{i:02d}": (n, 0, 3) for i, n in enumerate(moves)}


@pytest.mark.parametrize("infer, method, field, other", SIGNALS)
class TestClaimActivity:
    def tiers(self, patched, counts, infer, method, field, other):
        patched(counts, method, other)
        return [infer(t)[f"{field}_activity"] for t in counts]

    def test_the_top_third_is_active_and_zero_is_inactive(self, patched, infer, method, field,
                                                         other):
        got = self.tiers(patched, league([9, 8, 7, 6, 5, 4, 0, 0, 0]), infer, method, field, other)
        assert got == ["active"] * 3 + ["occasional"] * 3 + ["inactive"] * 3

    def test_every_team_tied_at_the_cut_is_active(self, patched, infer, method, field, other):
        got = self.tiers(patched, league([5, 5, 5, 5, 1, 1]), infer, method, field, other)
        assert got == ["active"] * 4 + ["occasional"] * 2

    def test_no_moves_is_inactive_even_inside_the_top_third(self, patched, infer, method, field,
                                                           other):
        got = self.tiers(patched, league([3, 0, 0, 0, 0, 0]), infer, method, field, other)
        assert got == ["active"] + ["inactive"] * 5
        assert self.tiers(patched, league([0, 0, 0]), infer, method, field, other) == [
            "inactive"] * 3

    def test_the_tiers_do_not_drift_as_the_counts_grow(self, patched, infer, method, field, other):
        early = self.tiers(patched, league([4, 3, 2, 1, 1, 0]), infer, method, field, other)
        late = self.tiers(patched, league([40, 30, 20, 10, 10, 0]), infer, method, field, other)
        assert late == early == ["active"] * 2 + ["occasional"] * 3 + ["inactive"]

    @pytest.mark.parametrize("claims, drops, confidence", [
        (0, 0, "low"), (1, 0, "medium"), (0, 1, "medium"), (9, 5, "medium"),
    ])
    def test_count_and_confidence(self, patched, infer, method, field, other, claims, drops,
                                  confidence):
        patched({"A01": (claims, drops, 7), "A02": (2, 2, 0), "A03": (1, 0, 0)}, method, other)
        got = infer("A01")
        assert set(got) == {f"{field}_activity", f"{field}_activity_confidence", f"{field}_count"}
        assert got[f"{field}_count"] == claims + drops
        assert got[f"{field}_activity_confidence"] == confidence

    def test_a_claim_and_the_drop_made_with_it_are_two_moves(self, patched, infer, method, field,
                                                            other):
        patched({"A01": (2, 2, 0)}, method, other)
        assert infer("A01")[f"{field}_count"] == 4

    def test_other_rows_and_other_teams_do_not_count(self, patched, infer, method, field, other):
        # A01 holds only draft picks, trades, lone drops and the other method's claims.
        patched({"A01": (0, 0, 30), "A02": (6, 6, 0)}, method, other)
        assert infer("A01")[f"{field}_count"] == 0
        assert infer("A01")[f"{field}_activity"] == "inactive"
        assert infer("A02")[f"{field}_count"] == 12

    def test_a_team_not_in_the_league_is_inactive(self, patched, infer, method, field, other):
        patched({"A01": (3, 3, 0)}, method, other)
        assert infer("Z99")[f"{field}_activity"] == "inactive"


class TestTheTwoSignals:
    def test_each_is_ranked_on_its_own_count(self, monkeypatch):
        # T0 leads on waiver claims and makes no free-agent add; T2 the reverse.
        rows = ([("claim", "T0", "waiver")] * 6 + [("claim", "T1", "waiver")] * 2
                + [("claim", "T1", "free_agent")] * 2 + [("claim", "T2", "free_agent")] * 6
                + [("drop", "T2", pd.NA)] * 9)
        frames = {"fact_roster_transactions": pd.DataFrame(
                      rows, columns=["event_type", "team_key", "claim_method"]),
                  "dim_fantasy_teams": pd.DataFrame({"team_key": ["T0", "T1", "T2"]})}
        monkeypatch.setattr(da, "read_parquet", lambda name: frames[name])
        waiver = [profiles.infer_waiver_activity(t) for t in ("T0", "T1", "T2")]
        free = [profiles.infer_free_agent_activity(t) for t in ("T0", "T1", "T2")]
        assert [w["waiver_count"] for w in waiver] == [6, 2, 0]
        assert [f["free_agent_count"] for f in free] == [0, 2, 6]
        assert [w["waiver_activity"] for w in waiver] == ["active", "occasional", "inactive"]
        assert [f["free_agent_activity"] for f in free] == ["inactive", "occasional", "active"]

    def test_the_share_is_its_own_constant(self):
        assert profiles._CLAIM_ACTIVITY_TOP_SHARE == pytest.approx(1 / 3)

    def test_the_methods_are_the_ledgers(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))
        import importlib
        rt = importlib.import_module("02d_fact_roster_transactions")
        assert (profiles._CLAIM_WAIVER, profiles._CLAIM_FREE_AGENT) == (
            rt.CLAIM_WAIVER, rt.CLAIM_FREE_AGENT)


class TestProfileWiring:
    @pytest.mark.parametrize("field", ["waiver_activity", "free_agent_activity"])
    def test_low_confidence_lists_the_field_only_when_low(self, field):
        base = {"stance_confidence": "high", "risk_confidence": "high",
                "trade_activity_confidence": "medium", "waiver_activity_confidence": "medium",
                "free_agent_activity_confidence": "medium"}
        assert field in profiles.low_confidence_fields({**base, f"{field}_confidence": "low"})
        assert field not in profiles.low_confidence_fields(base)

    @pytest.mark.parametrize("method, field", [("waiver", "waiver"), ("free_agent", "free_agent")])
    def test_build_profile_carries_the_signal_on_real_data(self, method, field):
        real = da.read_parquet("fact_roster_transactions")
        teams = da.read_parquet("dim_fantasy_teams")["team_key"]
        moves = real[real["event_type"].isin(["claim", "drop"]) & (real["claim_method"] == method)]
        want = moves.groupby("team_key").size().reindex(teams, fill_value=0)
        assert want.sum() > 0
        for team in (want.idxmax(), want.idxmin()):
            for mode in ("my", "counterparty"):
                p = profiles.build_profile(team, mode)
                assert p[f"{field}_count"] == int(want[team])
                assert p[f"{field}_activity"] in ("active", "occasional", "inactive")
            assert (f"{field}_activity" in p["low_confidence_fields"]) == (want[team] == 0)
        got = pd.Series({t: profiles.build_profile(t, "my")[f"{field}_activity"] for t in teams})
        assert set(got[want == 0]) <= {"inactive"} and "inactive" not in set(got[want > 0])
        # About a third of the league, more only when teams tie at the cut.
        cut = want.sort_values(ascending=False).iloc[len(teams) // 3 - 1]
        assert (got == "active").sum() == int(((want >= cut) & (want > 0)).sum())

    def test_every_method_row_is_in_exactly_one_count_on_real_data(self):
        real = da.read_parquet("fact_roster_transactions")
        teams = da.read_parquet("dim_fantasy_teams")["team_key"]
        counted = sum(profiles.build_profile(t, "my")[f"{f}_count"]
                      for t in teams for f in ("waiver", "free_agent"))
        assert counted == int(real["claim_method"].notna().sum())
