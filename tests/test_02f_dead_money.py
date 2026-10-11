"""02f: Dead Money from the ledger's drops (ADR-0016 decision 5, #96).

The builder is pure (ledger, dim_contract and dim_season frames in, rows
out), so every case runs on small frames. The contract and season dims are
the real ones' shape: the schedule is read from them, never hard-coded.
"""
import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import pandas as pd
import pytest

import etl_checks as ec

dm = importlib.import_module("02f_fact_dead_money")

CONTRACTS = pd.DataFrame(
    [("Minor", "minor", None, 0.0, False),
     ("1st", "initial", 1, 0.5, True),
     ("2nd", "initial", 2, 0.4, True),
     ("3rd", "initial", 3, 0.0, False),
     ("4th", "extension", 1, 0.5, True),
     ("5th", "extension", 2, 0.4, True),
     ("6th", "extension", 3, 0.0, False),
     ("Tag", "franchise", 1, 0.5, True),
     ("X", "expiring", 1, 0.5, False),
     ("FA", "fa", 1, 0.0, False),
     ("Pick", "draft_pick", 1, 0.0, False)],
    columns=["contract_id", "contract_type", "contract_year", "cap_hit_pct", "guaranteed"],
).astype({"contract_year": "Int64"})

SEASONS = pd.DataFrame({"season_id": ["2026-2027", "2027-2028", "2028-2029"],
                        "season_start_year": [2026, 2027, 2028]})


def ledger(*rows):
    """Ledger rows: (transaction_id, event_type, team_key, scorer_id,
    contract_id, contract_value, contract_source[, season_id[, period]])."""
    out = []
    for i, r in enumerate(rows):
        r = tuple(r) + ("2026-2027", 2)[len(r) - 7:]
        out.append({"transaction_id": r[0], "event_type": r[1], "team_key": r[2],
                    "scorer_id": r[3], "contract_id": r[4], "contract_value": r[5],
                    "contract_source": r[6], "season_id": r[7], "period": r[8],
                    "event_date": pd.Timestamp("2026-09-16 08:00") + pd.Timedelta(minutes=i),
                    "gsis_id": f"00-{i:07d}"})
    return pd.DataFrame(out).astype({"period": "Int64", "contract_value": "float64"})


def build(*rows, seasons=SEASONS):
    return dm.build_dead_money(ledger(*rows), CONTRACTS, seasons)


def drop(contract, value=10_000_000.0, tx="t1", team="A01", scorer="s1",
         source="roster_state", **kw):
    return (tx, "drop", team, scorer, contract, value, source) + tuple(kw.values())


class TestSchedule:
    def test_it_is_read_from_dim_contract(self):
        s = dm.schedule(CONTRACTS)
        assert s["1st"] == [(0, "1st", 0.5), (1, "2nd", 0.4)]
        assert s["2nd"] == [(0, "2nd", 0.4)]
        assert s["4th"] == [(0, "4th", 0.5), (1, "5th", 0.4)]
        assert s["5th"] == [(0, "5th", 0.4)]
        assert s["Tag"] == [(0, "Tag", 0.5)]
        for none in ("3rd", "6th", "X", "FA", "Minor", "Pick"):
            assert s[none] == [], none

    def test_a_changed_rate_changes_the_charge(self):
        contracts = CONTRACTS.copy()
        contracts.loc[contracts["contract_id"] == "2nd", "cap_hit_pct"] = 0.25
        df = dm.build_dead_money(ledger(drop("1st")), contracts, SEASONS)
        assert df["dead_money"].tolist() == [5_000_000.0, 2_500_000.0]


class TestBuild:
    def test_a_first_year_drop_charges_two_seasons(self):
        df = build(drop("1st", 9_783_000.0))
        assert df["season_id"].tolist() == ["2026-2027", "2027-2028"]
        assert df["charge_contract_id"].tolist() == ["1st", "2nd"]
        assert df["cap_hit_pct"].tolist() == [0.5, 0.4]
        assert df["dead_money"].tolist() == [4_891_500.0, 3_913_200.0]
        assert set(df["contract_id"]) == {"1st"} and set(df["contract_value"]) == {9_783_000.0}
        assert list(df.columns) == dm.COLUMNS
        assert {c: str(t) for c, t in df.dtypes.items()} == dm.DTYPES

    def test_a_second_year_drop_charges_its_own_season_only(self):
        df = build(drop("2nd"))
        assert df[["season_id", "charge_contract_id", "dead_money"]].values.tolist() == [
            ["2026-2027", "2nd", 4_000_000.0]]

    def test_a_tag_charges_one_season(self):
        df = build(drop("Tag"))
        assert df[["season_id", "dead_money"]].values.tolist() == [["2026-2027", 5_000_000.0]]

    @pytest.mark.parametrize("contract", ["3rd", "6th", "X", "FA", "Minor"])
    def test_a_contract_with_no_guaranteed_year_left_charges_nothing(self, contract):
        assert build(drop(contract)).empty

    def test_an_empty_table_keeps_its_schema(self):
        df = build(drop("FA"))
        assert list(df.columns) == dm.COLUMNS
        assert {c: str(t) for c, t in df.dtypes.items()} == dm.DTYPES

    def test_only_drops_are_charged(self):
        df = build(("t0", "claim", "A01", "s1", "1st", 10_000_000.0, "roster_state"),
                   ("t9", "trade_away", "A01", "s2", "1st", 10_000_000.0, "roster_state"))
        assert df.empty

    def test_a_drop_absent_from_the_log_charges_nothing(self):
        both = build(drop("1st", tx="t1", scorer="s1"), drop("1st", tx="t2", scorer="s2"))
        one = build(drop("1st", tx="t1", scorer="s1"))
        assert len(both) == 4 and len(one) == 2
        # Removing a move changes no other row.
        pd.testing.assert_frame_equal(
            both[both["transaction_id"] == "t1"].reset_index(drop=True), one)

    def test_a_reclaim_by_the_same_team_does_not_cancel(self):
        df = build(drop("1st", tx="t1"),
                   ("t2", "claim", "A01", "s1", "FA", 2_000_000.0, "roster_state"))
        assert df["dead_money"].tolist() == [5_000_000.0, 4_000_000.0]

    def test_a_second_drop_of_the_same_player_is_its_own_charge(self):
        df = build(drop("1st", tx="t1"),
                   ("t2", "claim", "A01", "s1", "1st", 4_000_000.0, "roster_state"),
                   drop("1st", 4_000_000.0, tx="t3"))
        assert sorted(df["dead_money"]) == [1_600_000.0, 2_000_000.0, 4_000_000.0, 5_000_000.0]

    def test_a_drop_that_ends_no_stint_is_skipped_whatever_its_terms(self):
        # The one real case carries another team's `1st` and salary.
        assert build(drop("1st", 19_205_000.0, source="no_stint")).empty

    def test_a_drop_with_no_salary_is_skipped(self):
        assert build(drop("1st", None)).empty

    def test_a_drop_of_another_season_has_no_period_and_is_still_charged(self):
        df = build(drop("1st", season_id="2027-2028", period=None))
        assert df["season_id"].tolist() == ["2027-2028", "2028-2029"]
        assert df["drop_period"].isna().all()

    def test_a_charge_past_dim_season_raises(self):
        with pytest.raises(ValueError, match="no season 1 after 2028-2029"):
            build(drop("1st", season_id="2028-2029", period=None))

    def test_a_drop_in_an_unknown_season_raises(self):
        with pytest.raises(ValueError, match="2031-2032 is not in dim_season"):
            build(drop("1st", season_id="2031-2032", period=None))

    def test_an_unknown_contract_raises(self):
        with pytest.raises(ValueError, match="not in dim_contract"):
            build(drop("7th"))

    def test_cents_are_exact(self):
        # .4 x 4,494,000 is 1,797,600.0000000002 in floating point.
        df = build(drop("1st", 4_494_000.0))
        assert df["dead_money"].tolist() == [2_247_000.0, 1_797_600.0]

    def test_the_rows_do_not_depend_on_ledger_order(self):
        rows = [drop("1st", tx=f"t{i}", team=f"A0{i % 3}", scorer=f"s{i}") for i in range(6)]
        a = build(*rows)
        b = build(*reversed(rows))
        assert a.drop(columns=["drop_date", "gsis_id"]).sort_values(dm.KEY).reset_index(drop=True).equals(
            b.drop(columns=["drop_date", "gsis_id"]).sort_values(dm.KEY).reset_index(drop=True))

    def test_the_output_passes_its_own_gate(self):
        led = ledger(drop("1st", tx="t1"), drop("FA", tx="t2", scorer="s2"),
                     drop("1st", tx="t3", scorer="s3", source="no_stint"))
        df = dm.build_dead_money(led, CONTRACTS, SEASONS)
        assert ec.dead_money_errors(df, led, CONTRACTS) == []


class TestMain:
    def test_it_writes_the_whole_table_and_reruns_identically(self, tmp_path, monkeypatch, capsys):
        ledger(drop("1st", tx="t1"), drop("FA", tx="t2", scorer="s2")).to_parquet(
            tmp_path / "fact_roster_transactions.parquet", index=False)
        CONTRACTS.to_parquet(tmp_path / "dim_contract.parquet", index=False)
        SEASONS.to_parquet(tmp_path / "dim_season.parquet", index=False)
        out = tmp_path / "fact_dead_money.parquet"
        # A stale row from an earlier ledger must not survive the rewrite.
        pd.DataFrame({"transaction_id": ["gone"]}).to_parquet(out, index=False)
        for name in ("LEDGER_PATH", "CONTRACT_PATH", "SEASON_PATH", "OUT_PATH"):
            monkeypatch.setattr(dm, name, tmp_path / getattr(dm, name).name)

        assert dm.main() == 0
        first = out.read_bytes()
        df = pd.read_parquet(out)
        assert df["transaction_id"].tolist() == ["t1", "t1"]
        assert "2 rows from 1 of 2 drops" in capsys.readouterr().out
        assert dm.main() == 0 and out.read_bytes() == first
