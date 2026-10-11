"""Unit tests for notebooks/etl_checks.py — the publish-gate check suite
(#115, ADR-0008 amendment decisions 4, 6, 8, 16).

The gate functions are pure, so most tests build tiny DataFrames. run_suite
runs against a tmp data dir with an injected registry and HEAD row count;
head_row_count runs against a throwaway git repo (conftest.git_repo).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))

import pandas as pd
import pytest

import etl_checks as ec
from conftest import closeable, git, league_teams as _teams


class TestRegistry:
    def test_single_grain(self):
        assert ec.table_key({"grain": "scorer_id"}) == ["scorer_id"]

    def test_composite_grain(self):
        assert ec.table_key({"grain": "(team_id, scorer_id, season, week)"}) == [
            "team_id", "scorer_id", "season", "week"]

    def test_pk_wins_over_grain(self):
        # ADR-0018's pk (#108) replaces grain without touching the checks.
        assert ec.table_key({"grain": "(a, b)", "pk": ["a", "c"]}) == ["a", "c"]
        assert ec.table_key({"grain": "(a, b)", "pk": "z"}) == ["z"]

    def test_chain_tables_skip_manual(self):
        reg = {"t1": {"chain": "rookie"}, "t2": {"chain": "rookie"}, "t3": {}}
        assert ec.chain_tables(reg) == {"rookie": ["t1", "t2"]}

    def test_real_registry_loads(self):
        reg = ec.load_registry()
        assert "fact_trade_log" in reg
        assert all(ec.table_key(e) for e in reg.values())


class TestGrain:
    def test_unique(self):
        df = pd.DataFrame({"a": [1, 2], "b": ["x", "x"]})
        assert ec.check_grain(df, ["a", "b"]) == (0, 0)

    def test_duplicate_on_complete_keys(self):
        df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
        assert ec.check_grain(df, ["a", "b"]) == (1, 0)

    def test_null_key_rows_excluded_and_counted(self):
        # Two rows sharing a null key are not "duplicates" — they're filed.
        df = pd.DataFrame({"a": [1, 1, 2], "b": [None, None, "y"]})
        assert ec.check_grain(df, ["a", "b"]) == (0, 2)


class TestRequiredKeys:
    def test_ok(self):
        assert ec.check_required_keys(pd.DataFrame({"k": [1, 2]}), ["k"]) == []

    def test_nulls(self):
        assert ec.check_required_keys(pd.DataFrame({"k": [1, None]}), ["k"]) == ["k: 1 null"]

    def test_missing_column(self):
        assert ec.check_required_keys(pd.DataFrame({"k": [1]}), ["j"]) == ["j: column missing"]


class TestSchema:
    entry = {"name": "t", "columns": [{"name": "a", "dtype": "str"},
                                      {"name": "b", "dtype": "int64"}]}

    def test_match_text_family(self):
        assert ec.schema_errors(self.entry, {"a": "object", "b": "int64"}) == []

    def test_dtype_drift(self):
        assert ec.schema_errors(self.entry, {"a": "str", "b": "float64"}) == [
            "[t].b: yaml dtype 'int64' != parquet dtype 'float64'"]

    def test_renamed_column(self):
        errs = ec.schema_errors(self.entry, {"a": "str", "b2": "int64"})
        assert "[t] parquet has undeclared columns: ['b2']" in errs
        assert "[t] yaml declares columns not in parquet: ['b']" in errs


class TestShrink:
    def test_within_limit(self):
        assert ec.check_shrink(80, 100) is None          # exactly 20% is allowed

    def test_over_limit(self):
        assert "shrank 100 -> 79" in ec.check_shrink(79, 100)

    def test_to_zero(self):
        assert "collapsed to 0" in ec.check_shrink(0, 100)

    def test_growth_never_blocks(self):
        assert ec.check_shrink(500, 100) is None

    def test_new_table(self):
        assert ec.check_shrink(0, None) is None

    def test_per_table_limit(self):
        assert ec.check_shrink(60, 100, limit=0.5) is None
        assert ec.check_shrink(40, 100, limit=0.5) is not None

    def test_accepted(self):
        assert ec.check_shrink(0, 100, accepted=True) is None


class TestHeadRowCount:
    def test_reads_head_and_missing(self, git_repo):
        pd.DataFrame({"a": range(7)}).to_parquet(git_repo / "data" / "t.parquet")
        git(git_repo, "add", "data/t.parquet")
        git(git_repo, "commit", "-q", "-m", "seed")
        # The working copy changes; HEAD is what counts.
        pd.DataFrame({"a": range(2)}).to_parquet(git_repo / "data" / "t.parquet")
        assert ec.head_row_count("t", repo=git_repo) == 7
        assert ec.head_row_count("absent", repo=git_repo) is None


class TestCoverage:
    def test_full(self):
        assert ec.coverage_errors(_teams()[["team_key"]], _teams()) == []

    def test_missing_team(self):
        errs = ec.coverage_errors(_teams().iloc[1:][["team_key"]], _teams())
        assert "27 teams, expected 28" in errs
        assert "conference A: 13 teams, expected 14" in errs

    def test_unknown_team(self):
        roster = pd.DataFrame({"team_key": [*_teams()["team_key"], "ZZ"]})
        assert any("not in dim_fantasy_teams" in e for e in ec.coverage_errors(roster, _teams()))


def _roster_state(periods=(("2026-2027", 1), ("2026-2027", 2)), contract="1st"):
    """One player per team in each (season_id, period)."""
    teams = _teams()["team_key"]
    return pd.concat([pd.DataFrame({"season_id": season, "period": period,
                                    "team_key": teams, "contract_id": contract})
                      for season, period in periods], ignore_index=True)


class TestRosterStateChecks:
    CONTRACTS = pd.DataFrame({"contract_id": ["Minor", "1st", "FA"]})

    def _run(self, check, state):
        tables = {"fact_roster_state": state, "dim_fantasy_teams": _teams(),
                  "dim_contract": self.CONTRACTS}
        dc = next(d for d in ec.DOMAIN_CHECKS
                  if (d.table, d.name) == ("fact_roster_state", check))
        assert dc.tier == "gate"
        return dc.fn(tables.__getitem__)

    def test_newest_period_of_the_newest_season(self):
        # Last season's period 12 is a higher number, not the newer period.
        state = _roster_state((("2025-2026", 12), ("2026-2027", 1), ("2026-2027", 2)))
        newest = ec.newest_period(state)
        assert set(zip(newest["season_id"], newest["period"])) == {("2026-2027", 2)}
        assert len(newest) == 28

    def test_coverage_passes_on_a_full_newest_period(self):
        assert self._run("coverage", _roster_state()) == []

    def test_coverage_reads_only_the_newest_period(self):
        state = _roster_state()
        older_gap = state[~((state["period"] == 1) & (state["team_key"] == "T00"))]
        assert self._run("coverage", older_gap) == []
        newest_gap = state[~((state["period"] == 2) & (state["team_key"] == "T00"))]
        assert "27 teams, expected 28" in self._run("coverage", newest_gap)

    def test_every_contract_is_a_dim_contract_row(self):
        assert self._run("contract", _roster_state()) == []
        assert ec.contract_errors(_roster_state(contract="7th"), self.CONTRACTS) == [
            "contract_id not in dim_contract: ['7th']"]

    def test_an_unknown_contract_in_an_older_period_still_blocks(self):
        state = _roster_state()
        state.loc[(state["period"] == 1) & (state["team_key"] == "T00"), "contract_id"] = "7th"
        assert self._run("contract", state) == ["contract_id not in dim_contract: ['7th']"]


def _scoring(rows):
    """Period Scoring rows from (team_key, scorer_id, is_starter, offense,
    defense, special teams), all in period 1."""
    df = pd.DataFrame(rows, columns=["team_key", "scorer_id", "is_starter", *ec.UNIT_COLUMNS])
    df["fpts"] = df[ec.UNIT_COLUMNS].sum(axis=1)
    return df.assign(season_id="2026-2027", period=1)


def _slots(rows):
    """Roster State rows from (team_key, scorer_id, roster_slot), period 1."""
    return pd.DataFrame(rows, columns=["team_key", "scorer_id", "roster_slot"]).assign(
        season_id="2026-2027", period=1)


def _matchup(rows):
    """Matchup rows from (team_key, opponent_team_key, is_home, fpts_for,
    fpts_against), all in period 1."""
    return pd.DataFrame(rows, columns=["team_key", "opponent_team_key", "is_home",
                                       "fpts_for", "fpts_against"]).assign(
        season_id="2026-2027", period=1)


class TestScoringChecks:
    """The #118 Gates on fact_period_scoring and fact_matchup."""

    SCORING = [("A01", "p1", True, 10.0, 0.0, 2.5), ("A01", "p2", False, 0.0, 4.0, 0.0)]
    SLOTS = [("A01", "p1", "Starter"), ("A01", "p2", "Bench"), ("A01", "p3", "Starter")]
    MATCHUP = [("A01", "B01", False, 12.5, 20.0), ("B01", "A01", True, 20.0, 12.5)]

    def test_the_three_gates_are_registered(self):
        gates = {(d.table, d.name) for d in ec.DOMAIN_CHECKS if d.tier == "gate"}
        assert {("fact_period_scoring", "unit_sum"), ("fact_period_scoring", "starter_slot"),
                ("fact_matchup", "mirror")} <= gates

    def test_units_that_sum_to_fpts_pass(self):
        assert ec.unit_sum_errors(_scoring(self.SCORING)) == []

    def test_float_noise_inside_the_tolerance_passes(self):
        scoring = _scoring(self.SCORING)
        scoring.loc[0, "fpts"] += 0.004
        assert ec.unit_sum_errors(scoring) == []

    def test_units_off_fpts_block(self):
        scoring = _scoring(self.SCORING)
        scoring.loc[0, "fpts"] += 0.5
        assert ec.unit_sum_errors(scoring) == ["1 rows whose Units do not sum to fpts"]

    def test_starters_that_match_the_roster_slot_pass(self):
        # p3 is a Starter with no entry: no row is not this Gate's failure.
        assert ec.starter_slot_errors(_scoring(self.SCORING), _slots(self.SLOTS)) == []

    def test_a_row_off_the_roster_blocks(self):
        scoring = _scoring(self.SCORING + [("A01", "gone", False, 1.0, 0.0, 0.0)])
        assert ec.starter_slot_errors(scoring, _slots(self.SLOTS)) == [
            "1 rows not on that period's fact_roster_state (periods [1])"]

    def test_the_roster_of_another_period_does_not_count(self):
        slots = _slots(self.SLOTS).assign(period=2)
        assert "2 rows not on that period's" in ec.starter_slot_errors(
            _scoring(self.SCORING), slots)[0]

    @pytest.mark.parametrize("slots", [
        [("A01", "p1", "Bench"), ("A01", "p2", "Bench")],        # a Starter the roster benches
        [("A01", "p1", "Starter"), ("A01", "p2", "Starter")],    # a non-starter the roster starts
    ])
    def test_is_starter_against_the_slot_blocks(self, slots):
        assert ec.starter_slot_errors(_scoring(self.SCORING), _slots(slots)) == [
            "1 rows whose is_starter disagrees with the Roster Slot (periods [1])"]

    def test_mirrored_matchups_pass(self):
        assert ec.mirror_errors(_matchup(self.MATCHUP)) == []

    def test_an_opponent_with_no_row_blocks(self):
        assert ec.mirror_errors(_matchup(self.MATCHUP[:1])) == [
            "1 rows whose opponent has no row that period (periods [1])"]

    @pytest.mark.parametrize("second, rows", [
        (("B01", "A01", True, 20.0, 99.0), 2),      # scores not swapped
        (("B01", "A01", False, 20.0, 12.5), 2),     # both on the away side
        (("B01", "C01", True, 20.0, 12.5), 1),      # the opponent names another team
    ])
    def test_a_row_that_does_not_mirror_blocks(self, second, rows):
        errs = ec.mirror_errors(_matchup([self.MATCHUP[0], second]))
        assert f"{rows} rows that do not mirror their opponent's row (periods [1])" in errs


class TestCloseChecks:
    """ADR-0008 amendment decision 7 and ADR-0016 amendment decision 10: what
    04p asks before a period's Update-Set goes from closing to closed."""

    def errs(self, tables, period=1, season_id="2026-2027"):
        return ec.close_errors(season_id, period, tables.__getitem__)

    def test_a_complete_period_may_close(self):
        assert self.errs(closeable()) == []

    def test_roster_state_short_a_team_blocks(self):
        t = closeable()
        t["fact_roster_state"] = t["fact_roster_state"].iloc[1:]
        assert "Roster State: 27 teams, expected 28" in self.errs(t)

    def test_a_missing_matchup_blocks(self):
        t = closeable()
        t["fact_matchup"] = t["fact_matchup"].iloc[2:]          # T00 v T01, both rows
        errs = self.errs(t)
        assert "Matchups: 26 teams, expected 28" in errs
        assert "Matchups: conference A: 12 teams, expected 14" in errs

    def test_a_team_listed_twice_blocks(self):
        t = closeable()
        t["fact_matchup"] = pd.concat([t["fact_matchup"], t["fact_matchup"].iloc[:1]],
                                      ignore_index=True)
        assert "Matchups: team(s) listed more than once: ['T00']" in self.errs(t)

    def test_a_pair_that_does_not_mirror_blocks(self):
        t = closeable()
        t["fact_matchup"].loc[0, "fpts_against"] += 5.0
        assert any("do not mirror" in e for e in self.errs(t))

    def test_one_edited_score_blocks(self):
        # The mirror leg sees both rows of the pair; the Starter leg names the team.
        t = closeable()
        t["fact_matchup"].loc[0, "fpts_for"] += 0.5
        errs = self.errs(t)
        assert "1 team(s) whose Matchup score is not their Starter sum: ['T00']" in errs
        assert any("do not mirror" in e for e in errs)

    def test_one_edited_starter_blocks(self):
        t = closeable()
        s = t["fact_period_scoring"]
        s.loc[s["is_starter"] & (s["team_key"] == "T05"), "fpts"] -= 0.02
        assert self.errs(t) == [
            "1 team(s) whose Matchup score is not their Starter sum: ['T05']"]

    def test_float_noise_inside_the_tolerance_passes(self):
        t = closeable()
        t["fact_period_scoring"].loc[0, "fpts"] += 0.004
        assert self.errs(t) == []

    def test_bench_points_do_not_count(self):
        t = closeable()
        s = t["fact_period_scoring"]
        s.loc[~s["is_starter"], "fpts"] = 99.0
        assert self.errs(t) == []

    def test_a_team_with_no_starter_rows_blocks(self):
        t = closeable()
        s = t["fact_period_scoring"]
        t["fact_period_scoring"] = s[~(s["is_starter"] & (s["team_key"] == "T09"))]
        assert self.errs(t) == [
            "1 team(s) whose Matchup score is not their Starter sum: ['T09']"]

    def test_only_the_period_asked_for_is_read(self):
        t = closeable(periods=(1, 2))
        m = t["fact_matchup"]
        m.loc[(m["period"] == 2) & (m["team_key"] == "T00"), "fpts_for"] += 3.0
        assert self.errs(t, period=1) == []
        assert self.errs(t, period=2) != []

    def test_a_period_with_no_rows_blocks(self):
        errs = self.errs(closeable(), period=2)
        assert "Roster State: 0 teams, expected 28" in errs
        assert "Matchups: 0 teams, expected 28" in errs

    def test_another_seasons_rows_do_not_count(self):
        assert self.errs(closeable(season_id="2025-2026")) != []


class TestScoringCoverage:
    """The coverage Gate on fact_period_scoring (ADR-0008 amendment decision 4)."""

    @staticmethod
    def periods(states):
        return pd.DataFrame({"season_id": "2026-2027", "period": range(1, len(states) + 1),
                             "update_set_state": states})

    def errs(self, tables, states):
        tables = {**tables, "dim_scoring_period": self.periods(states)}
        dc = next(d for d in ec.DOMAIN_CHECKS
                  if (d.table, d.name) == ("fact_period_scoring", "coverage"))
        assert dc.tier == "gate"
        return dc.fn(tables.__getitem__)

    def test_every_loaded_period_covers_28_teams(self):
        assert self.errs(closeable(periods=(1, 2, 3)), ["closed", "closed", "closing", "open"]) == []

    def test_a_loaded_period_short_a_team_blocks(self):
        t = closeable(periods=(1, 2))
        s = t["fact_period_scoring"]
        t["fact_period_scoring"] = s[~((s["period"] == 2) & (s["team_key"] == "T00"))]
        assert self.errs(t, ["closing", "closing"]) == [
            "2026-2027 period 2: 27 teams, expected 28",
            "2026-2027 period 2: conference A: 13 teams, expected 14"]

    def test_a_closed_period_with_no_rows_blocks(self):
        t = closeable(periods=(1, 3))
        assert self.errs(t, ["closed", "closed", "closed"]) == [
            "2026-2027: no rows for period(s) [2], closed through period 3"]

    def test_a_period_that_is_not_closed_may_be_absent(self):
        # Period 2 is closing and not loaded: the games may not be final yet.
        assert self.errs(closeable(periods=(1,)), ["closed", "closing", "open"]) == []

    def test_no_closed_period_asks_for_none(self):
        assert self.errs(closeable(periods=()), ["closing", "open"]) == []


class TestRunSuite:
    REG = {
        "t": {"name": "t", "chain": "rookie", "grain": "(k, j)", "required_keys": ["k"],
              "columns": [{"name": "k", "dtype": "int64"}, {"name": "j", "dtype": "str"}]},
    }

    def _run(self, tmp_path, df, head=None, accepted=()):
        df.to_parquet(tmp_path / "t.parquet")
        res = ec.run_suite(["t"], accepted, registry=self.REG, data_dir=tmp_path,
                           head_rows=lambda name: head)
        return {r.check: r for r in res}

    def test_clean(self, tmp_path):
        res = self._run(tmp_path, pd.DataFrame({"k": [1, 2], "j": ["a", "b"]}))
        assert all(r.ok for r in res.values())
        assert {r.chain for r in res.values()} == {"rookie"}
        assert set(res) == {"schema", "grain", "grain_null_key", "required_keys", "shrink"}

    def test_duplicate_blocks(self, tmp_path):
        res = self._run(tmp_path, pd.DataFrame({"k": [1, 1], "j": ["a", "a"]}))
        assert not res["grain"].ok and res["grain"].tier == "gate"

    def test_null_key_files_one_finding(self, tmp_path):
        res = self._run(tmp_path, pd.DataFrame({"k": [1, 1, 2], "j": [None, None, "b"]}))
        assert res["grain"].ok
        r = res["grain_null_key"]
        assert r.tier == "review" and r.findings == [("*", "2 of 3 rows have a null grain column")]

    def test_shrink_and_accept(self, tmp_path):
        df = pd.DataFrame({"k": [1], "j": ["a"]})
        assert not self._run(tmp_path, df, head=10)["shrink"].ok
        assert self._run(tmp_path, df, head=10, accepted=["t"])["shrink"].ok

    def test_missing_parquet_blocks(self, tmp_path):
        res = ec.run_suite(["t"], registry=self.REG, data_dir=tmp_path, head_rows=lambda n: None)
        assert [(r.check, r.ok) for r in res] == [("schema", False)]


def _moves(*rows):
    """Ledger rows: (transaction_id, event_type, team_key, scorer_id,
    contract_id, contract_value, contract_source, period)."""
    df = pd.DataFrame(rows, columns=["transaction_id", "event_type", "team_key", "scorer_id",
                                     "contract_id", "contract_value", "contract_source", "period"])
    df["season_id"] = "2026-2027"
    df["event_date"] = pd.Timestamp("2026-09-16 08:00")
    return df.astype({"period": "Int64"})


def _dead(*rows):
    df = pd.DataFrame(rows, columns=["transaction_id", "scorer_id", "team_key", "season_id",
                                     "contract_value", "charge_contract_id", "cap_hit_pct",
                                     "dead_money"])
    return df.assign(contract_id="1st")


_CONTRACTS = pd.DataFrame({"contract_id": ["1st", "2nd", "X", "FA"],
                           "contract_type": ["initial", "initial", "expiring", "fa"],
                           "contract_year": [1, 2, 1, 1],
                           "cap_hit_pct": [0.5, 0.4, 0.5, 0.0],
                           "guaranteed": [True, True, False, False]})


class TestDeadMoneyChecks:
    """The `schedule` Gate on fact_dead_money and the two drop Review checks
    on the ledger (#96)."""

    LEDGER = _moves(("t1", "drop", "A01", "s1", "1st", 10e6, "roster_state", 2),
                    ("t2", "drop", "A01", "s2", "FA", 2e6, "default", 2),
                    ("t3", "claim", "A01", "s3", "1st", 4e6, "roster_state", 2))
    DEAD = _dead(("t1", "s1", "A01", "2026-2027", 10e6, "1st", 0.5, 5e6),
                 ("t1", "s1", "A01", "2027-2028", 10e6, "2nd", 0.4, 4e6))

    def errs(self, dead=None, ledger=None):
        return ec.dead_money_errors(self.DEAD if dead is None else dead,
                                    self.LEDGER if ledger is None else ledger, _CONTRACTS)

    def test_clean(self):
        assert self.errs() == []

    def test_an_empty_table_is_clean_when_nothing_is_owed(self):
        assert self.errs(self.DEAD.iloc[:0], self.LEDGER.iloc[1:]) == []

    def test_wrong_amount(self):
        dead = self.DEAD.copy()
        dead.loc[0, "dead_money"] = 5e6 + 1
        assert self.errs(dead) == ["1 rows whose dead_money is not cap_hit_pct x contract_value"]

    def test_a_charge_on_a_contract_that_is_not_guaranteed(self):
        dead = self.DEAD.copy()
        dead.loc[1, ["charge_contract_id", "cap_hit_pct", "dead_money"]] = ["X", 0.5, 5e6]
        assert any("not a guaranteed dim_contract row" in e and "'X'" in e for e in self.errs(dead))

    def test_a_rate_that_is_not_the_one_in_dim_contract(self):
        dead = self.DEAD.copy()
        dead.loc[1, ["cap_hit_pct", "dead_money"]] = [0.3, 3e6]
        assert any("not a guaranteed dim_contract row" in e for e in self.errs(dead))

    def test_a_row_that_is_not_a_drop_on_the_ledger(self):
        dead = pd.concat([self.DEAD, _dead(("t3", "s3", "A01", "2026-2027", 4e6, "1st", 0.5, 2e6),
                                           ("t3", "s3", "A01", "2027-2028", 4e6, "2nd", 0.4, 1.6e6))],
                         ignore_index=True)
        assert "1 charged moves are not a drop on the ledger" in self.errs(dead)

    def test_a_drop_with_no_contract_source_is_still_a_drop(self):
        ledger = self.LEDGER.copy()
        ledger.loc[0, "contract_source"] = None
        assert self.errs(ledger=ledger) == []

    def test_a_missing_schedule_row(self):
        assert self.errs(self.DEAD.iloc[:1]) == [
            "1 drops whose row count is not the guaranteed years left on the contract"]

    def test_a_later_year_charged_to_the_drop_season_or_before(self):
        dead = self.DEAD.copy()
        dead.loc[1, "season_id"] = "2025-2026"
        assert self.errs(dead) == ["1 rows charged to the wrong season"]

    def test_the_first_year_charged_to_another_season(self):
        dead = self.DEAD.copy()
        dead.loc[0, "season_id"] = "2028-2029"
        assert self.errs(dead) == ["1 rows charged to the wrong season"]

    def test_terms_that_are_not_the_ledger_drop(self):
        dead = self.DEAD.copy()
        dead[["contract_value", "dead_money"]] = dead[["contract_value", "dead_money"]] * 2
        assert self.errs(dead) == ["2 rows whose contract_id or contract_value is not the ledger drop's"]

    def test_a_charged_drop_that_ends_no_stint(self):
        ledger = self.LEDGER.copy()
        ledger.loc[0, "contract_source"] = "no_stint"
        assert self.errs(ledger=ledger) == ["1 charged drops end no stint"]

    def test_a_guaranteed_drop_with_no_row(self):
        assert self.errs(self.DEAD.iloc[:0]) == [
            "1 drops of a guaranteed contract have no row (run 02f after 02d)"]

    def test_a_stintless_or_unpriced_drop_owes_no_row(self):
        ledger = _moves(("t1", "drop", "A01", "s1", "1st", 10e6, "no_stint", 2),
                        ("t2", "drop", "A01", "s2", "1st", None, "default", 2))
        assert self.errs(self.DEAD.iloc[:0], ledger) == []

    # ---- Review: stintless_drop -----------------------------------------------
    STATE = pd.DataFrame({"season_id": "2026-2027", "period": [1, 2, 1],
                          "team_key": ["A01", "A01", "A02"], "scorer_id": ["s1", "s1", "s1"]})

    def stintless(self, period=3, state=None):
        ledger = _moves(("t1", "drop", "A01", "s1", "1st", 10e6, "no_stint", period),
                        ("t2", "drop", "A01", "s2", "FA", 2e6, "default", 2))
        return ec.stintless_drop_findings(ledger, self.STATE if state is None else state)

    def test_every_stintless_drop_is_listed_once(self):
        found = self.stintless()
        assert [k for k, _ in found] == ["t1|s1|A01"]
        assert "ends no stint; no Dead Money charged" in found[0][1]

    def test_the_finding_says_roster_state_showed_the_copy(self):
        detail = self.stintless(period=3)[0][1]
        assert "Roster State shows the copy on A01 in period(s) [1, 2]" in detail
        assert "missing the move in" in detail

    def test_only_periods_before_the_drop_count(self):
        # A drop effective in period 1 left before any Roster State; the row
        # of another team for the same player is not a stint on this team.
        detail = self.stintless(period=1)[0][1]
        assert "no Roster State row shows the copy on A01 before the drop" in detail

    def test_a_stintless_drop_of_another_season_has_no_period(self):
        detail = self.stintless(period=None, state=self.STATE.iloc[:0])[0][1]
        assert "no period (another season)" in detail

    # ---- Review: default_contract_drop ----------------------------------------
    PERIODS = pd.DataFrame({"season_id": "2026-2027", "period": [1, 2, 3],
                            "update_set_state": ["closed", "closing", "open"]})

    def defaults(self, *periods):
        ledger = _moves(*[(f"t{i}", "drop", "A01", f"s{i}", "FA", 2e6, "default", p)
                          for i, p in enumerate(periods)],
                        ("r1", "drop", "A01", "r1", "1st", 2e6, "roster_state", 3),
                        ("c1", "claim", "A01", "c1", "FA", 2e6, "default", 3))
        return ec.default_contract_drop_findings(ledger, self.PERIODS)

    def test_listed_while_the_period_is_not_closed(self):
        found = self.defaults(1, 2, 3)
        assert [k for k, _ in found] == ["t1|s1|A01", "t2|s2|A01"]
        assert "period 2 is priced on the default contract FA" in found[0][1]

    def test_a_period_the_dim_does_not_hold_is_not_closed(self):
        assert [k for k, _ in self.defaults(9)] == ["t0|s0|A01"]

    def test_a_drop_with_no_period_is_not_listed(self):
        assert self.defaults(None) == []


class TestReviewDomainChecks:
    """A Review-tier DomainCheck files its findings; run_suite used to drop
    them (#96)."""

    REG = {
        "t": {"name": "t", "chain": "rookie", "grain": "(k)", "required_keys": ["k"],
              "columns": [{"name": "k", "dtype": "int64"}]},
    }

    def _run(self, tmp_path, monkeypatch, fn, tier="review"):
        pd.DataFrame({"k": [1, 2]}).to_parquet(tmp_path / "t.parquet")
        monkeypatch.setattr(ec, "DOMAIN_CHECKS", [ec.DomainCheck("odd", tier, "t", fn)])
        res = ec.run_suite(["t"], registry=self.REG, data_dir=tmp_path, head_rows=lambda n: None)
        return res, next(r for r in res if r.check == "odd")

    def test_findings_are_filed_and_do_not_block(self, tmp_path, monkeypatch):
        res, r = self._run(tmp_path, monkeypatch,
                           lambda load: [(str(k), f"k={k}") for k in load("t")["k"]])
        assert (r.tier, r.ok, r.detail) == ("review", False, "")
        assert r.findings == [("1", "k=1"), ("2", "k=2")]
        assert not [x for x in res if x.tier == "gate" and not x.ok]
        findings, ran = ec.review_findings(res)
        assert ("odd", "t") in ran
        assert [f["row_key"] for f in findings if f["check_name"] == "odd"] == ["1", "2"]

    def test_no_findings_is_ok_and_clears(self, tmp_path, monkeypatch):
        res, r = self._run(tmp_path, monkeypatch, lambda load: [])
        assert r.ok and r.findings == []
        assert ("odd", "t") in ec.review_findings(res)[1]

    def test_a_review_check_that_raises_files_nothing_and_clears_nothing(self, tmp_path, monkeypatch):
        def boom(load):
            raise KeyError("no such column")
        res, r = self._run(tmp_path, monkeypatch, boom)
        assert not r.ok and "check raised" in r.detail and not r.ran
        findings, ran = ec.review_findings(res)
        assert ("odd", "t") not in ran and not [f for f in findings if f["check_name"] == "odd"]

    def test_a_gate_check_still_returns_error_strings(self, tmp_path, monkeypatch):
        _, r = self._run(tmp_path, monkeypatch, lambda load: ["bad", "worse"], tier="gate")
        assert (r.tier, r.ok, r.detail, r.findings) == ("gate", False, "bad; worse", [])

    def test_a_gate_check_that_raises_blocks(self, tmp_path, monkeypatch):
        def boom(load):
            raise KeyError("x")
        _, r = self._run(tmp_path, monkeypatch, boom, tier="gate")
        assert r.tier == "gate" and not r.ok and "check raised" in r.detail

    def test_the_drop_checks_are_registered(self):
        got = {(c.name, c.tier, c.table) for c in ec.DOMAIN_CHECKS}
        assert {("schedule", "gate", "fact_dead_money"),
                ("stintless_drop", "review", "fact_roster_transactions"),
                ("default_contract_drop", "review", "fact_roster_transactions")} <= got


class TestFiling:
    def _f(self, row_key="*", detail="2 rows"):
        return {"check_name": "grain_null_key", "table_name": "t",
                "row_key": row_key, "detail": detail}

    RAN = {("grain_null_key", "t")}

    def _empty(self):
        return pd.DataFrame(columns=ec.FILING_COLUMNS)

    def test_new(self):
        out, stats = ec.file_findings(self._empty(), [self._f()], self.RAN, "r1", "t1")
        assert stats == {"opened": 1, "repeated": 0, "cleared": 0, "open": 1}
        row = out.iloc[0]
        assert (row.created_at, row.last_seen_at, row.run_id, row.pending) == ("t1", "t1", "r1", False)

    def test_repeat_updates_in_place(self):
        out, _ = ec.file_findings(self._empty(), [self._f()], self.RAN, "r1", "t1")
        out, stats = ec.file_findings(out, [self._f(detail="3 rows")], self.RAN, "r2", "t2")
        assert len(out) == 1 and stats["repeated"] == 1
        row = out.iloc[0]
        assert (row.created_at, row.last_seen_at, row.run_id, row.detail) == ("t1", "t2", "r2", "3 rows")

    def test_cleared_when_unseen(self):
        out, _ = ec.file_findings(self._empty(), [self._f()], self.RAN, "r1", "t1")
        out, stats = ec.file_findings(out, [], self.RAN, "r2", "t2")
        assert stats["cleared"] == 1 and stats["open"] == 0
        assert (out.iloc[0].resolved_at, out.iloc[0].resolution) == ("t2", "cleared")

    def test_not_cleared_when_check_did_not_run(self):
        out, _ = ec.file_findings(self._empty(), [self._f()], self.RAN, "r1", "t1")
        out, stats = ec.file_findings(out, [], {("grain_null_key", "other")}, "r2", "t2")
        assert stats["cleared"] == 0 and stats["open"] == 1

    def test_recurrence_opens_new_row(self):
        out, _ = ec.file_findings(self._empty(), [self._f()], self.RAN, "r1", "t1")
        out, _ = ec.file_findings(out, [], self.RAN, "r2", "t2")
        out, stats = ec.file_findings(out, [self._f()], self.RAN, "r3", "t3")
        assert len(out) == 2 and stats["opened"] == 1 and stats["open"] == 1

    def test_csv_round_trip(self, tmp_path):
        path = tmp_path / "review_check.csv"
        res = [ec.Result("grain_null_key", "t", "rookie", "review", False,
                         findings=[("*", "2 rows")]),
               ec.Result("grain", "t", "rookie", "gate", True)]
        assert ec.file_review(res, "r1", path=path, now="t1")["opened"] == 1
        assert ec.file_review(res, "r2", path=path, now="t2") == {
            "opened": 0, "repeated": 1, "cleared": 0, "open": 1}
        back = pd.read_csv(path, dtype=str, keep_default_na=False)
        assert list(back.columns) == ec.FILING_COLUMNS and len(back) == 1
        clean = [ec.Result("grain_null_key", "t", "rookie", "review", True)]
        assert ec.file_review(clean, "r3", path=path, now="t3")["cleared"] == 1
