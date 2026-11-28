"""The team-name crosswalk (#770): etl_helpers' team-name match and
scripts/load_team_names.py (the seed and --apply), on made-up teams.

Every team name and id below is invented. The command runs against a
throwaway data dir; the capture file is built here in 04t's shape.
"""
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import pandas as pd
import pytest

import etl_helpers as etl

_spec = importlib.util.spec_from_file_location("load_team_names", REPO / "scripts" / "load_team_names.py")
ln = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ln)

TEAMS = pd.DataFrame([("A01", "f1", "Team Alpha"), ("A02", "f2", "Team Bravo"), ("A03", "f3", "Team Charlie")],
                     columns=["team_key", "fantrax_team_id", "team_name"])


def aliases(*rows):
    return pd.DataFrame(rows, columns=["name_clean", "fantrax_team_id"])


class TestCleanTeamName:
    def test_trim_case_and_inner_spaces(self):
        assert etl.clean_team_name("  Team   ALPHA Club ") == "team alpha club"

    def test_anything_but_text_is_the_empty_name(self):
        assert etl.clean_team_name(None) == "" and etl.clean_team_name(float("nan")) == ""


class TestTeamNames:
    def test_the_crosswalk_and_the_current_names_resolve(self):
        known = etl.team_names(TEAMS, aliases(("old alpha", "f1")))
        assert known.lookup["old alpha"] == ("f1", "crosswalk")
        assert known.lookup["team bravo"] == ("f2", "current")
        assert ("old alpha", "f1") in known.known and not known.ambiguous

    def test_a_name_given_to_two_teams_resolves_to_neither(self):
        known = etl.team_names(TEAMS, aliases(("team bravo", "f1")))
        assert "team bravo" in known.ambiguous and "team bravo" not in known.lookup
        assert {("team bravo", "f1"), ("team bravo", "f2")} <= set(known.known)


class TestMatchTeamName:
    KNOWN = [("alpha", "f1"), ("alpha two", "f1"), ("bravo", "f2"), ("charlie", "f3")]

    @pytest.fixture
    def scores(self, monkeypatch):
        table = {}
        monkeypatch.setattr(etl.fuzz, "token_sort_ratio", lambda a, b: table.get(b, 0))
        return table

    def test_ninety_or_more_is_taken(self, scores):
        scores.update({"alpha": 60, "alpha two": 92, "bravo": 75})
        assert etl.match_team_name("x", self.KNOWN) == etl.TeamMatch("f1", "guess_90", 92, "f1")

    def test_seventy_to_eighty_nine_goes_to_the_list_with_its_guess(self, scores):
        scores.update({"alpha": 89, "bravo": 69})
        assert etl.match_team_name("x", self.KNOWN) == etl.TeamMatch(None, "guess_70_89", 89, "f1")

    def test_under_seventy_goes_to_the_list_with_none(self, scores):
        scores.update({"alpha": 69, "bravo": 50})
        assert etl.match_team_name("x", self.KNOWN) == etl.TeamMatch(None, "no_guess", None, None)

    def test_two_teams_in_one_band_always_go_to_the_list(self, scores):
        scores.update({"alpha": 95, "bravo": 90})
        assert etl.match_team_name("x", self.KNOWN).reason == "two_teams"
        scores.update({"alpha": 80, "bravo": 70})
        assert etl.match_team_name("x", self.KNOWN) == etl.TeamMatch(None, "two_teams", 80, "f1")

    def test_a_runner_up_in_a_lower_band_does_not_stop_the_guess(self, scores):
        scores.update({"alpha": 91, "bravo": 89})
        assert etl.match_team_name("x", self.KNOWN).fantrax_team_id == "f1"

    def test_the_real_scorer_takes_a_one_letter_slip(self):
        known = etl.team_names(TEAMS).known
        assert etl.match_team_name("Team Alphaa", known).fantrax_team_id == "f1"
        assert etl.match_team_name("Zulu Club", known).reason == "no_guess"


def capture(path: Path, cells):
    """One 04t capture file of one page, a row per (key, teamId, content)."""
    rows = [{"txSetId": f"t{i}", "cells": [{"key": k, "teamId": t, "content": c}]}
            for i, (k, t, c) in enumerate(cells)]
    path.write_text(json.dumps([{"responses": [{"data": {"table": {"rows": rows}}}]}]), encoding="utf-8")


@pytest.fixture
def store(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "raw").mkdir(parents=True)
    TEAMS.assign(conference="A").to_parquet(data / "dim_fantasy_teams.parquet", index=False)
    monkeypatch.setattr(etl.CFG, "data_dir", str(data))
    monkeypatch.setattr(ln.rt, "TXN_GLOB", str(data / "raw" / "fantrax_txn_history_*.json"))
    monkeypatch.setattr(ln, "REVIEW_PATH", tmp_path / "review_team_names.csv")
    return data


def crosswalk(data):
    return pd.read_parquet(data / f"{etl.TEAM_ALIAS_TABLE}.parquet").set_index("name_clean")


class TestSeed:
    def test_the_current_names_seed_with_no_capture(self, store, capsys):
        counts = ln.main([])
        table = crosswalk(store)
        assert sorted(table.index) == ["team alpha", "team bravo", "team charlie"]
        assert set(table["decision"]) == {"seed"} and set(table["source"]) == {"dim_fantasy_teams"}
        assert counts["new"] == 3 and "no 04t capture" in capsys.readouterr().out

    def test_the_capture_adds_an_earlier_name_beside_its_id(self, store):
        capture(store / "raw" / "fantrax_txn_history_2026.json",
                [("team", "f1", "Old Alpha"), ("from", "f2", "Team Bravo"), ("to", "f9", "Gone Team"),
                 ("date", None, "Mon Jul 13, 2026, 4:24PM")])
        counts = ln.main([])
        table = crosswalk(store)
        assert table.loc["old alpha", "fantrax_team_id"] == "f1"
        assert table.loc["old alpha", "source"] == "txn_capture"
        assert table.loc["team bravo", "source"] == "dim_fantasy_teams"
        assert counts["unknown_id"] == 1 and "gone team" not in table.index

    def test_a_name_two_teams_carried_is_counted_not_written(self, store, capsys):
        capture(store / "raw" / "fantrax_txn_history_2026.json", [("team", "f2", "Team Alpha")])
        counts = ln.main([])
        assert counts["reused"] == 1 and "team alpha" not in crosswalk(store).index
        assert "carried by two teams" in capsys.readouterr().out

    def test_the_seed_is_idempotent_and_never_changes_a_stored_row(self, store):
        etl.write_table(etl.TEAM_ALIAS_TABLE, ln._frame([("team bravo", "f3", "owner", None, "review_file",
                                                         pd.Timestamp.now(tz="UTC"))]))
        first = ln.main([])
        before = crosswalk(store)
        second = ln.main([])
        pd.testing.assert_frame_equal(crosswalk(store), before)
        assert first["conflict"] == 1 and second["new"] == 0 and second["stored"] == 2
        assert before.loc["team bravo", "fantrax_team_id"] == "f3"

    def test_the_output_names_no_team(self, store, capsys):
        capture(store / "raw" / "fantrax_txn_history_2026.json", [("team", "f1", "Old Alpha")])
        ln.main([])
        out = capsys.readouterr().out
        for value in ("Alpha", "alpha", "Bravo", "f1", "f2", "A01"):
            assert value not in out


def review_file(path: Path, rows):
    pd.DataFrame(rows, columns=etl.TEAM_NAME_REVIEW_COLS).to_csv(path, index=False)


class TestApply:
    def test_a_filled_row_is_owner_and_an_untouched_guess_is_guess(self, store):
        review_file(ln.REVIEW_PATH, [
            ("Zulu Club", 3, "no_guess", None, None, None, "f2"),
            ("Team Alphaa", 1, "guess_90", "A01", "Team Alpha", 95, "f1"),
            ("Team Charly", 2, "guess_70_89", "A03", "Team Charlie", 80, ""),
        ])
        counts = ln.main(["--apply"])
        table = crosswalk(store)
        assert table.loc["zulu club", "decision"] == "owner" and table.loc["zulu club", "fantrax_team_id"] == "f2"
        assert table.loc["team alphaa", "decision"] == "guess" and table.loc["team alphaa", "score"] == 95
        assert "team charly" not in table.index
        assert counts["owner"] == 1 and counts["guess"] == 1 and counts["blank"] == 1

    def test_a_guess_the_owner_changed_is_his(self, store):
        review_file(ln.REVIEW_PATH, [("Team Alphaa", 1, "guess_90", "A01", "Team Alpha", 95, "f3")])
        ln.main(["--apply"])
        assert crosswalk(store).loc["team alphaa", "decision"] == "owner"

    def test_an_unknown_id_or_a_name_given_two_ids_is_refused(self, store):
        review_file(ln.REVIEW_PATH, [("Zulu Club", 1, "no_guess", None, None, None, "f9"),
                                     ("Yankee", 1, "no_guess", None, None, None, "f1"),
                                     ("YANKEE ", 1, "no_guess", None, None, None, "f2")])
        counts = ln.main(["--apply"])
        assert counts["unknown_id"] == 1 and counts["two_ids"] == 2
        assert not (store / f"{etl.TEAM_ALIAS_TABLE}.parquet").exists()

    def test_apply_replaces_a_stored_row_and_twice_changes_nothing(self, store):
        ln.main([])
        review_file(ln.REVIEW_PATH, [("Team Bravo", 1, "two_teams", None, None, None, "f3")])
        assert ln.main(["--apply"])["replaced"] == 1
        assert crosswalk(store).loc["team bravo", "fantrax_team_id"] == "f3"
        assert ln.main(["--apply"])["unchanged"] == 1

    def test_no_list_stops_with_a_message(self, store):
        with pytest.raises(SystemExit, match="no review_team_names.csv"):
            ln.main(["--apply"])
