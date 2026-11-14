"""The Minor drift check (#524, ADR-0008 decision 9): Fantrax's minors-eligibility
verdict (04v) against nflverse's (02j), on Fantrax's newest capture day."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "notebooks"))
import etl_checks

DAY = "2026-11-12"
CROSSWALK = pd.DataFrame({"scorer_id": ["s1", "s2", "s3", "s4", "s5", "s6"],
                          "gsis_id": ["g1", "g2", "g3", "g4", None, "g6"]})


def fantrax(*scorers, day=DAY):
    return pd.DataFrame({"scorer_id": list(scorers), "capture_date": day, "fa_status": "taken"},
                        columns=["scorer_id", "capture_date", "fa_status"])


def nflverse(*rows, day=DAY):
    """rows: (gsis_id, career_games)."""
    return pd.DataFrame([{"gsis_id": g, "capture_date": day, "career_games": n, "eligible": n <= 19}
                         for g, n in rows])


def roster(*scorers):
    return pd.DataFrame({"season_id": "2026-2027", "period": 9, "scorer_id": list(scorers)})


def run(fx, nv, on_roster=()):
    return dict(etl_checks.minor_drift_findings(fx, nv, roster(*on_roster), CROSSWALK))


class TestAgreement:
    def test_no_finding_when_both_list_the_same_players(self):
        got = run(fantrax("s1", "s2"), nflverse(("g1", 3), ("g2", 19), ("g3", 40)), on_roster=("s3",))
        assert got == {}

    def test_a_rostered_player_neither_calls_eligible_is_not_a_finding(self):
        assert run(fantrax("s1"), nflverse(("g1", 0), ("g3", 25)), on_roster=("s3",)) == {}

    def test_a_free_agent_nflverse_calls_eligible_and_fantrax_does_not_list_is_not_compared(self):
        assert run(fantrax("s1"), nflverse(("g1", 0), ("g4", 2))) == {}


class TestDisagreement:
    def test_fantrax_lists_a_player_nflverse_counts_past_the_limit(self):
        got = run(fantrax("s1", "s3"), nflverse(("g1", 3), ("g3", 20)))
        assert list(got) == ["s3"] and "nflverse counts 20 games" in got["s3"]

    def test_a_rostered_scorer_the_crosswalk_has_no_gsis_id_for_is_a_finding(self):
        got = run(fantrax("s5"), nflverse(("g1", 3)), on_roster=("s5",))
        assert "(on a roster)" in got["s5"] and "the crosswalk has no gsis_id" in got["s5"]

    def test_a_free_agent_the_crosswalk_has_no_gsis_id_for_is_not_compared(self):
        assert run(fantrax("s5"), nflverse(("g1", 3))) == {}

    def test_fantrax_lists_a_player_missing_from_nflverse_s_pool(self):
        got = run(fantrax("s6"), nflverse(("g1", 3)))
        assert "not in nflverse's pool" in got["s6"]

    def test_a_rostered_player_nflverse_calls_eligible_and_fantrax_does_not_list(self):
        got = run(fantrax("s1"), nflverse(("g1", 3), ("g2", 7)), on_roster=("s2",))
        assert list(got) == ["s2"]
        assert "on a fantasy roster and nflverse counts 7 games" in got["s2"]

    def test_the_boundary_is_nineteen_eligible_and_twenty_not(self):
        got = run(fantrax("s1", "s2"), nflverse(("g1", 19), ("g2", 20)))
        assert list(got) == ["s2"]

    def test_a_finding_names_the_scorer_id_and_no_player(self):
        got = run(fantrax("s3"), nflverse(("g3", 22)))
        assert got["s3"].startswith("Fantrax lists s3 (a free agent) ")

    def test_a_finding_says_whether_the_player_is_on_a_roster(self):
        got = run(fantrax("s3"), nflverse(("g3", 22)), on_roster=("s3",))
        assert got["s3"].startswith("Fantrax lists s3 (on a roster) ")


class TestWhatIsRead:
    def test_only_fantrax_s_newest_capture_day_is_read(self):
        old = fantrax("s3", day="2026-11-05")
        both = pd.concat([old, fantrax("s1")])
        nv = pd.concat([nflverse(("g1", 3), ("g3", 40), day="2026-11-05"), nflverse(("g1", 3))])
        assert run(both, nv) == {}

    def test_no_nflverse_capture_within_a_day_is_not_compared(self):
        with pytest.raises(etl_checks.NotComparable, match=r"within 1 day\(s\) of 2026-11-12"):
            run(fantrax("s1"), nflverse(("g1", 3), day="2026-11-10"))

    def test_the_nearest_capture_within_a_day_is_compared(self):
        nv = pd.concat([nflverse(("g1", 3), ("g3", 40), day="2026-11-13"),
                        nflverse(("g1", 3), ("g3", 5), day="2026-11-11")])
        got = run(fantrax("s1", "s3"), nv)
        assert got == {}          # the 11-13 capture is as near as 11-11; the earlier one wins the tie

    def test_no_fantrax_capture_is_not_compared(self):
        with pytest.raises(etl_checks.NotComparable):
            run(fantrax(), nflverse(("g1", 3)))

    def test_only_the_newest_roster_period_counts(self):
        old = pd.DataFrame({"season_id": "2026-2027", "period": 8, "scorer_id": ["s2"]})
        state = pd.concat([old, roster("s1")])
        got = dict(etl_checks.minor_drift_findings(fantrax("s1"), nflverse(("g1", 3), ("g2", 7)),
                                                   state, CROSSWALK))
        assert got == {}


class TestRegistered:
    def test_it_is_a_review_check_with_one_period_of_grace_on_fantrax_s_table(self):
        dc = next(d for d in etl_checks.DOMAIN_CHECKS if d.name == "minor_drift")
        assert (dc.tier, dc.table, dc.grace_periods) == ("review", "fact_minor_eligibility", 1)

    def test_a_store_without_nflverse_s_table_is_not_compared(self, tmp_path):
        dc = next(d for d in etl_checks.DOMAIN_CHECKS if d.name == "minor_drift")

        def load(name):
            if name == "fact_nfl_minor_eligibility":
                raise etl_checks.TableNotFound(name)
            return fantrax("s1")
        with pytest.raises(etl_checks.NotComparable):
            dc.fn(load)
