"""The commissioners' contract lists (#545): the rules, the status windows, an
empty list and the change key."""
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "notebooks"))
import etl_contract_moves as cm

DAY = date(2026, 11, 14)
RESIGN = date(2026, 11, 19)
FINAL = date(2027, 1, 4)

TEAMS = pd.DataFrame({"team_key": ["t1", "t2"], "conference": ["A", "B"], "division": ["Da", "Db"]})
PLAYERS = pd.DataFrame({"gsis_id": [f"g{i}" for i in range(1, 9)],
                        "display_name": [f"Player {i}" for i in range(1, 9)],
                        "position": "WR", "team_abbr": "KC"})


def copy(scorer, contract, team="t1", method="startup_draft", slot="Bench", when="2026-09-01",
         salary=2_000_000.0, season="2026-2027"):
    return {"team_key": team, "scorer_id": scorer, "gsis_id": "g" + scorer[1:],
            "contract_id": contract, "contract_value": salary, "roster_slot": slot,
            "acquired_method": method, "acquired_date": pd.Timestamp(when), "season": season}


def fantrax(*scorers, day="2026-11-12"):
    return pd.DataFrame({"scorer_id": list(scorers), "capture_date": day, "player_name": "x",
                         "position_raw": "WR", "nfl_team": "KC"})


def nflverse(*rows, day="2026-11-12"):
    return pd.DataFrame([{"gsis_id": g, "capture_date": day, "career_games": n, "eligible": n <= 20}
                         for g, n in rows])


LEDGER_COLUMNS = ["event_type", "team_key", "scorer_id", "event_seq", "season_id", "contract_id",
                  "event_date"]


def move(kind, scorer, team="t1", seq=100, contract="x", season="2026-2027"):
    return {"event_type": kind, "team_key": team, "scorer_id": scorer, "event_seq": seq,
            "season_id": season, "contract_id": contract, "event_date": pd.Timestamp("2026-10-01")}


def drops(*moves):
    """A ledger of the given moves (see `move`); no argument is an empty ledger."""
    return pd.DataFrame(list(moves), columns=LEDGER_COLUMNS)


def opened_by(rows, extra=()):
    """The ledger of a roster: each copy's opening move (its `acquired_method`, at
    seq 100 on its team) and the extra moves a test adds."""
    own = [move(r["acquired_method"], r["scorer_id"], r["team_key"]) for r in rows
           if r["acquired_method"]]
    return drops(*own, *extra)


def build(rows, fx=(), nv=(), ledger=(), day=DAY, resign=RESIGN, final=FINAL):
    return cm.build_lists(pd.DataFrame(rows), TEAMS, PLAYERS, fantrax(*fx), nflverse(*nv),
                          opened_by(rows, ledger), day, resign, final)


def only(out, name):
    return out[out["list_name"] == name]


class TestMinorToFirst:
    def test_a_minor_off_fantrax_s_list_is_due_now_for_first(self):
        out = only(build([copy("s1", "Minor")], fx=["s2"], nv=[("g1", 25)]), cm.LIST_MINOR)
        assert out[["contract_now", "move_to", "status", "nfl_games"]].iloc[0].tolist() == [
            "Minor", "1st", cm.DUE_NOW, 25]

    def test_a_minor_still_listed_at_19_or_20_games_is_due_within_7_days(self):
        out = only(build([copy("s1", "Minor"), copy("s2", "Minor")], fx=["s1", "s2"],
                         nv=[("g1", 19), ("g2", 20)]), cm.LIST_MINOR)
        assert set(out["status"]) == {cm.DUE_SOON} and len(out) == 2

    def test_a_minor_listed_at_18_games_is_not_on_the_list(self):
        assert only(build([copy("s1", "Minor")], fx=["s1"], nv=[("g1", 18)]), cm.LIST_MINOR).empty

    def test_a_minor_with_no_gsis_id_is_still_filed_when_fantrax_drops_it(self):
        row = copy("s1", "Minor")
        row["gsis_id"] = None
        out = only(build([row], fx=["s2"]), cm.LIST_MINOR)
        assert len(out) == 1 and pd.isna(out["nfl_games"].iloc[0])

    def test_the_two_conferences_each_get_their_own_rows(self):
        out = only(build([copy("s1", "Minor", team="t1"), copy("s1", "Minor", team="t2")],
                         fx=["s2"], nv=[("g1", 30)]), cm.LIST_MINOR)
        assert sorted(out["conference"]) == ["A", "B"]


class TestGameBoundaries:
    @pytest.mark.parametrize("games,expected", [(18, []), (19, [cm.DUE_SOON]), (20, [cm.DUE_SOON]),
                                                (21, [])])
    def test_the_heads_up_window_is_19_and_20_games_on_the_list(self, games, expected):
        out = only(build([copy("s1", "Minor")], fx=["s1"], nv=[("g1", games)]), cm.LIST_MINOR)
        assert out["status"].tolist() == expected

    def test_a_listed_minor_with_no_game_count_gets_no_heads_up(self):
        assert only(build([copy("s1", "Minor")], fx=["s1"]), cm.LIST_MINOR).empty

    def test_two_teams_holding_one_player_on_different_contracts_are_judged_alone(self):
        out = only(build([copy("s1", "Minor", team="t1"), copy("s1", "1st", team="t2")], fx=["s2"],
                         nv=[("g1", 30)]), cm.LIST_MINOR)
        assert out[["team_key", "move_to"]].values.tolist() == [["t1", "1st"]]

    def test_an_old_gsis_id_is_counted_under_its_newest_id(self):
        links = pd.DataFrame({"old_gsis_id": ["g1"], "new_gsis_id": ["g9"]})
        out = cm.build_lists(pd.DataFrame([copy("s1", "Minor")]), TEAMS, PLAYERS, fantrax("s1"),
                             nflverse(("g9", 19)), opened_by([copy("s1", "Minor")]), DAY, RESIGN,
                             FINAL, links)
        assert only(out, cm.LIST_MINOR)["status"].tolist() == [cm.DUE_SOON]
        assert only(out, cm.LIST_MINOR)["gsis_id"].tolist() == ["g1"]

    def test_the_newest_fantrax_capture_names_a_player_with_no_dimension_row(self):
        row = copy("s5", "FA")
        row["gsis_id"] = None
        old = fantrax("s5", day="2026-11-05").assign(player_name="Old Name")
        new = fantrax("s5", day="2026-11-12").assign(player_name="New Name")
        out = cm.build_lists(pd.DataFrame([row]), TEAMS, PLAYERS, pd.concat([new, old]), nflverse(),
                             drops(), DAY, RESIGN, FINAL)
        assert out["player_name"].tolist() == ["New Name"]


class TestToMinor:
    def test_an_eligible_draft_pick_on_first_belongs_on_minor(self):
        out = only(build([copy("s1", "1st")], fx=["s1"], nv=[("g1", 5)]), cm.LIST_MINOR)
        assert out[["contract_now", "move_to", "status"]].iloc[0].tolist() == ["1st", "Minor", cm.DUE_NOW]

    def test_an_eligible_draft_pick_on_fa_belongs_on_minor(self):
        out = only(build([copy("s1", "FA")], fx=["s1"]), cm.LIST_MINOR)
        assert out["move_to"].tolist() == ["Minor"]

    def test_a_pure_free_agent_claim_on_fa_is_never_filed(self):
        assert only(build([copy("s1", "FA", method="claim")], fx=["s1"]), cm.LIST_MINOR).empty

    def test_a_dropped_minor_claimed_while_eligible_belongs_on_minor(self):
        led = [move("drop", "s1", seq=50, contract="Minor")]
        out = only(build([copy("s1", "FA", method="claim")], fx=["s1"], ledger=led), cm.LIST_MINOR)
        assert out["move_to"].tolist() == ["Minor"]

    def test_a_claim_of_a_player_dropped_on_first_is_not_filed(self):
        led = [move("drop", "s1", seq=50, contract="1st")]
        assert only(build([copy("s1", "1st", method="claim")], fx=["s1"], ledger=led),
                    cm.LIST_MINOR).empty

    def test_a_drop_after_the_claim_does_not_count(self):
        led = [move("drop", "s1", seq=150, contract="Minor")]
        assert only(build([copy("s1", "FA", method="claim")], fx=["s1"], ledger=led),
                    cm.LIST_MINOR).empty

    def test_a_drop_in_another_season_does_not_count(self):
        led = [move("drop", "s1", seq=50, contract="Minor", season="2025-2026")]
        assert only(build([copy("s1", "FA", method="claim")], fx=["s1"], ledger=led),
                    cm.LIST_MINOR).empty

    def test_the_latest_of_two_drops_decides(self):
        led = [move("drop", "s1", seq=40, contract="Minor"), move("drop", "s1", seq=60, contract="1st")]
        assert only(build([copy("s1", "FA", method="claim")], fx=["s1"], ledger=led),
                    cm.LIST_MINOR).empty

    def test_the_drop_a_copy_s_own_conference_made_is_the_one_that_counts(self):
        """C2 / F1: a Minor dropped in the other Conference says nothing about
        this Conference's pure free-agent claim."""
        led = [move("drop", "s1", team="t2", seq=50, contract="Minor")]
        assert only(build([copy("s1", "FA", team="t1", method="claim")], fx=["s1"], ledger=led),
                    cm.LIST_MINOR).empty

    def test_a_later_drop_in_the_other_conference_does_not_hide_a_true_match(self):
        """F1, the reverse: the other Conference's later drop must not decide."""
        led = [move("drop", "s1", team="t1", seq=40, contract="Minor"),
               move("drop", "s1", team="t2", seq=60, contract="1st")]
        out = only(build([copy("s1", "FA", team="t1", method="claim")], fx=["s1"], ledger=led),
                   cm.LIST_MINOR)
        assert out["team_key"].tolist() == ["t1"]

    def test_two_drops_at_one_stamp_are_ordered_by_event_seq(self):
        stamp = pd.Timestamp("2026-10-01")
        led = [move("drop", "s1", seq=40, contract="Minor") | {"event_date": stamp},
               move("drop", "s1", seq=41, contract="1st") | {"event_date": stamp}]
        assert only(build([copy("s1", "FA", method="claim")], fx=["s1"], ledger=led),
                    cm.LIST_MINOR).empty
        led = [move("drop", "s1", seq=40, contract="1st") | {"event_date": stamp},
               move("drop", "s1", seq=41, contract="Minor") | {"event_date": stamp}]
        assert len(only(build([copy("s1", "FA", method="claim")], fx=["s1"], ledger=led),
                        cm.LIST_MINOR)) == 1

    def test_a_traded_startup_draftee_on_first_is_still_filed_under_its_new_team(self):
        """F2 / C3: a trade passes the copy on with its contract."""
        led = [move("startup_draft", "s1", team="t1", seq=10)]
        out = only(build([copy("s1", "1st", team="t1", method="trade")], fx=["s1"], ledger=led),
                   cm.LIST_MINOR)
        assert out[["team_key", "move_to"]].iloc[0].tolist() == ["t1", "Minor"]

    def test_a_traded_dropped_minor_claim_is_followed_back_to_its_drop(self):
        led = [move("drop", "s1", seq=5, contract="Minor"), move("claim", "s1", seq=10)]
        out = only(build([copy("s1", "FA", method="trade")], fx=["s1"], ledger=led), cm.LIST_MINOR)
        assert out["move_to"].tolist() == ["Minor"]

    def test_a_traded_pure_free_agent_claim_stays_unfiled(self):
        led = [move("claim", "s1", seq=10)]
        assert only(build([copy("s1", "FA", method="trade")], fx=["s1"], ledger=led),
                    cm.LIST_MINOR).empty

    def test_a_trade_with_no_earlier_move_is_not_filed(self):
        assert only(build([copy("s1", "1st", method="trade")], fx=["s1"]), cm.LIST_MINOR).empty

    def test_a_copy_with_no_open_stint_is_not_filed(self):
        assert only(build([copy("s1", "1st", method=None)], fx=["s1"]), cm.LIST_MINOR).empty

    def test_an_ineligible_draft_pick_on_first_is_correct(self):
        assert only(build([copy("s1", "1st")], fx=["s2"], nv=[("g1", 40)]), cm.LIST_MINOR).empty

    def test_an_eligible_player_already_on_minor_is_correct(self):
        assert only(build([copy("s1", "Minor")], fx=["s1"], nv=[("g1", 3)]), cm.LIST_MINOR).empty


class TestExpiringAndDecision:
    ROWS = [copy("s1", "X"), copy("s2", "6th"), copy("s3", "Tag"), copy("s4", "2nd"),
            copy("s5", "FA"), copy("s6", "1st")]

    def test_expiring_holds_x_6th_and_tag_only(self):
        out = only(build(self.ROWS, day=date(2026, 12, 30)), cm.LIST_EXPIRING)
        assert sorted(out["contract_now"]) == ["6th", "Tag", "X"]
        assert dict(zip(out["contract_now"], out["move_to"])) == {
            "X": "Tag or expire", "6th": "Tag or expire", "Tag": "Expire"}

    def test_decision_holds_2nd_and_fa_only(self):
        out = only(build(self.ROWS), cm.LIST_DECISION)
        assert sorted(out["contract_now"]) == ["2nd", "FA"]

    def test_a_kept_fa_becomes_x_and_an_unkept_one_returns_at_season_s_end(self):
        out = only(build([copy("s5", "FA")]), cm.LIST_DECISION)
        assert out["move_to"].tolist() == ["Keep (X next season), or let go at season's end"]
        assert out["reason"].tolist() == [
            "FA pickup: keep it by the re-sign deadline, or it returns to the pool at season's end"]

    def test_a_second_year_row_reads_re_sign_or_keep(self):
        out = only(build([copy("s4", "2nd")]), cm.LIST_DECISION)
        assert out["move_to"].tolist() == ["Re-sign, or keep to year 3"]

    def test_a_first_year_player_is_on_no_list(self):
        out = build([copy("s6", "1st")], fx=["s9"], nv=[("g6", 90)], day=date(2026, 12, 30))
        assert out.empty

    def test_every_rostered_copy_gets_a_row_one_per_conference(self):
        out = only(build([copy("s5", "FA", team="t1"), copy("s5", "FA", team="t2")]), cm.LIST_DECISION)
        assert sorted(out["conference"]) == ["A", "B"]


class TestStatusWindows:
    @pytest.mark.parametrize("day,expected", [
        (date(2026, 11, 12), cm.DUE_SOON),     # 7 days before
        (date(2026, 11, 18), cm.DUE_SOON),
        (date(2026, 11, 19), cm.DUE_SOON),     # the deadline day
        (date(2026, 11, 20), cm.DUE_NOW),      # after it
        (date(2026, 11, 11), None),            # 8 days before: not yet
    ])
    def test_status_against_the_resign_deadline(self, day, expected):
        assert cm.status_for(day, RESIGN) == expected

    def test_a_decision_row_is_absent_before_the_window(self):
        assert build([copy("s5", "FA")], day=date(2026, 11, 1)).empty

    def test_a_decision_row_turns_due_now_after_the_deadline(self):
        out = build([copy("s5", "FA")], day=date(2026, 11, 20))
        assert out["status"].tolist() == [cm.DUE_NOW]

    def test_expiring_is_absent_until_a_week_before_the_final_period(self):
        assert only(build([copy("s1", "X")], day=date(2026, 11, 14)), cm.LIST_EXPIRING).empty
        out = only(build([copy("s1", "X")], day=date(2026, 12, 29)), cm.LIST_EXPIRING)
        assert out["status"].tolist() == [cm.DUE_SOON]

    def test_expiring_is_due_now_after_the_final_period(self):
        out = only(build([copy("s1", "Tag")], day=date(2027, 1, 5)), cm.LIST_EXPIRING)
        assert out["status"].tolist() == [cm.DUE_NOW]


class TestEmptyAndShape:
    def test_an_empty_roster_gives_an_empty_frame_with_every_column(self):
        out = cm.build_lists(pd.DataFrame(columns=list(copy("s1", "FA"))), TEAMS, PLAYERS,
                             fantrax(), nflverse(), drops(), DAY, RESIGN, FINAL)
        assert out.empty and list(out.columns) == cm.COLUMNS

    def test_the_columns_are_in_the_published_order_and_typed(self):
        out = build([copy("s5", "FA")])
        assert list(out.columns) == cm.COLUMNS
        assert str(out["nfl_games"].dtype) == "Int64" and str(out["salary"].dtype) == "float64"

    def test_the_grain_is_unique(self):
        out = build([copy("s1", "Minor"), copy("s5", "FA"), copy("s4", "2nd")], fx=["s2"],
                    nv=[("g1", 30)])
        assert not out.duplicated(cm.KEY).any()

    def test_a_player_with_no_dimension_row_falls_back_to_the_scorer_id(self):
        row = copy("s5", "FA")
        row["gsis_id"] = None
        out = cm.build_lists(pd.DataFrame([row]), TEAMS, PLAYERS, pd.DataFrame(), nflverse(),
                             drops(), DAY, RESIGN, FINAL)
        assert out["player_name"].tolist() == ["s5"]


class TestChangeKey:
    def test_the_key_is_list_conference_team_player_status(self):
        out = build([copy("s5", "FA")])
        assert cm.change_keys(out) == {("decision", "A", "t1", "s5", cm.DUE_SOON)}

    def test_a_first_run_is_all_new(self):
        out = build([copy("s5", "FA"), copy("s4", "2nd")])
        assert len(cm.new_keys(out, cm.empty())) == 2

    def test_a_fix_alone_adds_no_new_key(self):
        before = build([copy("s5", "FA"), copy("s4", "2nd")])
        after = build([copy("s5", "FA")])
        assert cm.new_keys(after, before) == set()

    def test_a_status_change_is_a_new_key(self):
        soon = build([copy("s5", "FA")], day=date(2026, 11, 18))
        now = build([copy("s5", "FA")], day=date(2026, 11, 20))
        assert cm.new_keys(now, soon) == {("decision", "A", "t1", "s5", cm.DUE_NOW)}

    def test_a_player_new_on_the_list_is_a_new_key(self):
        before = build([copy("s5", "FA")])
        after = build([copy("s5", "FA"), copy("s4", "2nd")])
        assert len(cm.new_keys(after, before)) == 1

    def test_an_empty_list_has_no_keys(self):
        assert cm.change_keys(cm.empty()) == set()
        assert cm.new_keys(cm.empty(), build([copy("s5", "FA")])) == set()


class TestReviewCheck:
    def run(self, rows, fx, nv=(), ledger=()):
        import etl_checks
        found = etl_checks.minor_contract_findings(
            pd.DataFrame(rows), TEAMS, PLAYERS, fantrax(*fx), nflverse(*nv), opened_by(rows, ledger))
        assert len(found) == len({k for k, _ in found}), "a finding key repeats"
        return dict(found)

    def test_it_files_both_directions_due_now(self):
        got = self.run([copy("s1", "Minor"), copy("s2", "1st")], fx=["s2"], nv=[("g1", 30)])
        assert set(got) == {"t1|s1|1st", "t1|s2|Minor"}
        assert "nflverse counts 30 games" in got["t1|s1|1st"]

    def test_the_19_and_20_game_heads_up_is_not_a_finding(self):
        assert self.run([copy("s1", "Minor")], fx=["s1"], nv=[("g1", 20)]) == {}

    def test_a_pure_free_agent_claim_on_fa_is_not_a_finding(self):
        assert self.run([copy("s1", "FA", method="claim")], fx=["s1"]) == {}

    def test_a_finding_names_the_scorer_and_team_never_a_player(self):
        got = self.run([copy("s1", "Minor")], fx=["s2"])
        assert "Player" not in "".join(got.values())

    def test_no_fantrax_capture_is_not_compared(self):
        import etl_checks
        with pytest.raises(etl_checks.NotComparable):
            self.run([copy("s1", "Minor")], fx=[])

    def test_it_is_a_review_check_on_the_current_roster(self):
        import etl_checks
        dc = next(d for d in etl_checks.DOMAIN_CHECKS if d.name == "minor_contract")
        assert (dc.tier, dc.table) == ("review", "fact_fantasy_teams")

    def test_a_store_without_nflverse_s_table_still_runs(self):
        import etl_checks
        dc = next(d for d in etl_checks.DOMAIN_CHECKS if d.name == "minor_contract")
        frames = {"fact_fantasy_teams": pd.DataFrame([copy("s1", "Minor")]), "dim_fantasy_teams": TEAMS,
                  "dim_nfl_players": PLAYERS, "fact_minor_eligibility": fantrax("s2"),
                  "fact_roster_transactions": drops()}

        def load(name):
            if name not in frames:
                raise etl_checks.TableNotFound(name)
            return frames[name]
        assert [k for k, _ in dc.fn(load)] == ["t1|s1|1st"]


class TestTheStep:
    """02k writes only from a healthy Roster State (ADR-0008 decision 6, amended)."""

    @pytest.fixture
    def step(self, monkeypatch):
        import importlib
        import etl_helpers
        mod = importlib.import_module("02k_fact_contract_move")
        writes = []
        monkeypatch.setattr(etl_helpers, "write_table", lambda *a, **k: writes.append(a) or 0)
        mod.writes = writes
        return mod, monkeypatch, etl_helpers

    def test_an_empty_roster_raises_and_writes_nothing(self, step):
        mod, mp, etl = step
        mp.setattr(etl, "read_table", lambda name: pd.DataFrame())
        with pytest.raises(RuntimeError, match="no rows"):
            mod.main()
        assert mod.writes == []

    def test_an_empty_eligibility_capture_raises_and_writes_nothing(self, step):
        """S1 / C1: an empty Fantrax capture would file every Minor as past 20 games."""
        mod, mp, etl = step
        frames = {"fact_fantasy_teams": pd.DataFrame([copy("s1", "Minor")]), "dim_fantasy_teams": TEAMS,
                  "dim_nfl_players": PLAYERS, "fact_minor_eligibility": fantrax(),
                  "fact_roster_transactions": drops()}
        mp.setattr(etl, "read_table", lambda name: frames[name])
        mp.setattr(etl, "table_exists", lambda name: False)
        mp.setattr(etl, "league_date", lambda: DAY)
        with pytest.raises(RuntimeError, match="fact_minor_eligibility holds no rows"):
            mod.main()
        assert mod.writes == []

    def test_a_missing_eligibility_table_raises_and_writes_nothing(self, step):
        mod, mp, etl = step

        def read(name):
            if name == "fact_minor_eligibility":
                raise etl.TableNotFound(name)
            return pd.DataFrame([copy("s1", "Minor")])
        mp.setattr(etl, "read_table", read)
        with pytest.raises(RuntimeError, match="fact_minor_eligibility is missing"):
            mod.main()
        assert mod.writes == []

    def test_a_missing_roster_raises_and_writes_nothing(self, step):
        mod, mp, etl = step

        def read(name):
            raise etl.TableNotFound(name)
        mp.setattr(etl, "read_table", read)
        with pytest.raises(RuntimeError, match="missing"):
            mod.main()
        assert mod.writes == []

    def test_a_healthy_roster_with_nothing_due_writes_an_empty_list(self, step):
        mod, mp, etl = step
        frames = {"fact_fantasy_teams": pd.DataFrame([copy("s6", "1st")]), "dim_fantasy_teams": TEAMS,
                  "dim_nfl_players": PLAYERS, "fact_minor_eligibility": fantrax("s9"),
                  "fact_roster_transactions": drops()}
        mp.setattr(etl, "read_table", lambda name: frames[name])
        mp.setattr(etl, "table_exists", lambda name: False)
        mp.setattr(etl, "league_date", lambda: DAY)
        assert mod.main() == 0
        assert len(mod.writes) == 1 and mod.writes[0][0] == "fact_contract_move"
        assert mod.writes[0][1].empty


class TestTheShrinkFlag:
    def test_exactly_one_table_is_exempt_from_the_shrink_gate(self):
        import etl_checks
        flagged = [n for n, e in etl_checks.load_registry().items() if e.get("shrinks_by_design")]
        assert flagged == ["fact_contract_move"]


class TestConfig:
    def test_the_dates_are_league_config_settings(self):
        import etl_helpers
        assert etl_helpers.CFG.resign_deadline == "2026-11-19"
        assert etl_helpers.CFG.trade_deadline == "2026-11-16"

    def test_the_final_period_matches_the_calendar(self):
        import etl_helpers
        path = Path(etl_helpers.DATA) / "dim_scoring_period.parquet"
        if not path.exists():
            pytest.skip("no scoring-period snapshot here")
        periods = pd.read_parquet(path)
        ends = {pd.Timestamp(g["end_at"].max()).tz_convert("America/New_York").date().isoformat()
                for _, g in periods.groupby("season_id")}
        assert etl_helpers.CFG.final_period_end in ends
