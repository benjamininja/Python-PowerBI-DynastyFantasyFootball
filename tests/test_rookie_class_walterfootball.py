"""#474: WalterFootball's next rookie class in 03b, the phase by run date, and each
run's own rank_date in ingest_ranking_source.

The scraper cases load the shipped 03b cell by its id and run it on the trimmed
page fixtures in tests/fixtures/walterfootball_2027 (no network). The ingest cases
swap the three table calls for in-memory frames, as test_etl_helpers.py does.
"""
import dataclasses
import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import pandas as pd
import pytest

import etl_helpers as etl

NOTEBOOK = REPO / "notebooks" / "03b_walterfootball_rankings.ipynb"
SCRAPER_CELL = "f044baa5"
FIXTURES = REPO / "tests" / "fixtures" / "walterfootball_2027"


def cell_source(cell_id):
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return "".join(next(c for c in nb["cells"] if c.get("id") == cell_id)["source"])


def load_scraper(cfg=None):
    ns = {"pd": pd, "re": re, "time": time, "CFG": cfg or etl.CFG,
          "ETL_USER_AGENT": etl.ETL_USER_AGENT, "_make_session": etl._make_session,
          "_parse_rank_date": etl._parse_rank_date}
    exec(compile(cell_source(SCRAPER_CELL), SCRAPER_CELL, "exec"), ns)
    return ns["WalterFootballScraper"]


def fixture_html(source_key):
    return (FIXTURES / f"{source_key.removeprefix('WalterFootball_')}.html").read_text(encoding="utf-8")


class TestPhaseByRunDate:
    CFG = etl.CFG
    combine_end = date.fromisoformat(CFG.rookie_class_combine_end)
    draft_end = date.fromisoformat(CFG.rookie_class_draft_end)

    def test_the_dates_sit_in_the_class_year_in_order(self):
        assert self.combine_end < self.draft_end
        assert self.combine_end.year == self.draft_end.year == self.CFG.rookie_class_year

    @pytest.mark.parametrize("run_date, phase", [
        (date(2026, 11, 8), "pre_combine"),
        (combine_end - timedelta(days=1), "pre_combine"),
        (combine_end, "pre_combine"),
        (combine_end + timedelta(days=1), "post_combine"),
        (draft_end, "post_combine"),
        (draft_end + timedelta(days=1), "post_draft"),
        (date(2027, 9, 1), "post_draft"),
    ])
    def test_the_run_date_sets_the_phase(self, run_date, phase):
        assert self.CFG.rookie_phase(run_date) == phase
        assert self.CFG.rookie_phase(run_date.isoformat()) == phase

    def test_every_phase_is_one_ingest_accepts(self):
        phases = {self.CFG.rookie_phase(d) for d in (date(2026, 11, 8), self.combine_end + timedelta(days=1),
                                                      self.draft_end + timedelta(days=1))}
        assert phases == {"pre_combine", "post_combine", "post_draft"}

    def test_the_dates_are_config_fields(self):
        cfg = dataclasses.replace(self.CFG, rookie_class_combine_end="2028-03-05",
                                  rookie_class_draft_end="2028-04-29")
        assert cfg.rookie_phase("2028-03-05") == "pre_combine"
        assert cfg.rookie_phase("2028-03-06") == "post_combine"
        assert cfg.rookie_phase("2028-04-30") == "post_draft"

    def test_draft_year_stays_2026(self):
        assert etl.CFG.draft_year == 2026
        assert etl.CFG.rookie_class_year == 2027


class TestClassYearComesFromConfig:
    def test_notebook_code_holds_no_class_year_or_phase_literal(self):
        nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        code = "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
        assert not re.search(r"20(2|3)\d", code)
        assert not re.search(r"""["'](pre_combine|post_combine|post_draft)["']""", code)

    def test_the_urls_follow_the_class_year(self):
        cfg = dataclasses.replace(etl.CFG, rookie_class_year=2028)
        sources = load_scraper(cfg).SOURCES
        assert len(sources) == 13
        assert all(s["url"].endswith("2028.php") for s in sources.values())
        assert all("2028 NFL Draft" in s["site_reference"] for s in sources.values())

    def test_the_2027_pages(self):
        sources = load_scraper().SOURCES
        assert len(sources) == 13
        assert all(s["url"].startswith("https://walterfootball.com/") and s["url"].endswith("2027.php")
                   for s in sources.values())
        assert sources["WalterFootball_OLB34"]["url"] == "https://walterfootball.com/OLB3-4Rankings2027.php"


EXPECTED = {
    "WalterFootball_QB":    ("2026-11-03", [("Darian Mensah", "QB", "Miami", "1"), ("Brendan Sorsby", "QB", "Texas Tech", "1-3")]),
    "WalterFootball_RB":    ("2026-10-28", [("Isaac Brown", "RB", "Louisville", "2-3")]),
    "WalterFootball_WR":    ("2026-11-03", [("Charlie Becker", "WR", "Indiana", "1-2"), ("Nick Marsh", "WR", "Indiana", "2")]),
    "WalterFootball_TE":    ("2026-11-03", [("Rocky Beers", "TE", "Oklahoma", "2-3"), ("Benjamin Brahmer", "TE", "Penn State", "3"),
                                                ("Trey’Dez Green", "TE", "LSU", "3-4")]),
    "WalterFootball_DE":    ("2026-11-03", [("Kenyatta Jackson", "DE", "Ohio State", "1-2")]),
    "WalterFootball_DT":    ("2026-11-03", [("Will Echoles", "DT", "Ole Miss", "1-2"), ("Ahmad Moten Sr.", "DT", "Miami", "2-3")]),
    "WalterFootball_OLB34": ("2026-11-03", [("Kenyatta Jackson", "OLB", "Ohio State", "1-2")]),
    "WalterFootball_DE34":  ("2026-11-03", [("Will Echoles", "DE", "Ole Miss", "1-2"), ("Ahmad Moten Sr.", "DE", "Miami", "2-3")]),
    "WalterFootball_NT":    ("2026-11-03", [("Will Echoles", "NT", "Ole Miss", "1-2"), ("Ahmad Moten Sr.", "NT", "Miami", "2-3")]),
    "WalterFootball_OLB":   ("2026-11-03", [("Suntarine Perkins", "OLB", "Ole Miss", "1-2")]),
    "WalterFootball_ILB":   ("2026-11-03", [("Sammy Brown", "ILB", "Clemson", "2"), ("Tony Rojas", "ILB", "Penn State", "2-3")]),
    "WalterFootball_CB":    ("2026-11-03", [("D.J. McKinney", "CB", "Notre Dame", "2"), ("Elliot Washington II", "CB", "Clemson", "2-3")]),
    "WalterFootball_S":     ("2026-09-05", [("Bray Hubbard", "S", "Alabama", "2"), ("Adon Shuler", "S", "Notre Dame", "2-3")]),
}


class TestParse:
    def test_the_fixture_covers_every_page(self):
        assert set(EXPECTED) == set(load_scraper().SOURCES)

    @pytest.mark.parametrize("source_key", sorted(EXPECTED))
    def test_a_page_gives_its_own_class_ranked_in_page_order(self, source_key):
        cls = load_scraper()
        df, rank_date = cls.__new__(cls).parse(fixture_html(source_key), source_key)
        want_date, want_rows = EXPECTED[source_key]
        assert rank_date == want_date
        got = list(zip(df["player_name"], df["position_raw"], df["school_raw"], df["proj_round"]))
        assert got == want_rows
        assert list(df["positional_rank"]) == list(range(1, len(want_rows) + 1))
        assert df["global_rank"].isna().all()

    def test_later_class_marks_are_left_out_and_do_not_shift_the_ranks(self):
        cls = load_scraper()
        df, _ = cls.__new__(cls).parse(fixture_html("WalterFootball_QB"), "WalterFootball_QB")
        assert "Drew Mestemaker" not in set(df["player_name"])
        assert "Arch Manning" not in set(df["player_name"])
        assert df.loc[df["player_name"] == "Brendan Sorsby", "positional_rank"].iloc[0] == 2

    def test_a_comment_below_the_article_is_not_read(self):
        cls = load_scraper()
        df, _ = cls.__new__(cls).parse(fixture_html("WalterFootball_QB"), "WalterFootball_QB")
        assert "Zed Commenter" not in set(df["player_name"])

    def test_an_entry_that_cannot_be_read_fails_the_page_instead_of_shifting_ranks(self):
        cls = load_scraper()
        html = fixture_html("WalterFootball_WR").replace("Nick Marsh, WR,", "Nick Marsh WR")
        with pytest.raises(ValueError, match="read 3 entries but the page numbers 4"):
            cls.__new__(cls).parse(html, "WalterFootball_WR")

    def test_a_page_with_no_player_of_the_class_raises(self):
        cls = load_scraper()
        html = fixture_html("WalterFootball_RB").replace("Isaac Brown,", "Isaac Brown*,")
        with pytest.raises(ValueError, match="No player entries"):
            cls.__new__(cls).parse(html, "WalterFootball_RB")


COLUMNS = ["player_key", "gsis_id", "source_name", "source_site", "phase", "draft_year",
           "global_rank", "positional_rank", "grade", "capture_date", "rank_date"]


def fact_row(key, phase, year, rank, rank_date, capture="2026-04-20", source="WalterFootball_DL"):
    return (key, None, source, "WalterFootball", phase, year, None, rank, None, capture, rank_date)


@pytest.fixture
def tables(monkeypatch):
    state = {
        "dim_rookie_prospect": pd.DataFrame({
            "player_name_clean": ["ann one", "bob two"],
            "player_key": ["k_ann", "k_bob"],
            "pfr_id": [None, None],
        }),
        "dim_nfl_players": pd.DataFrame({"pfr_id": [None], "gsis_id": [None], "status": ["ACT"]}),
        "fact_rookie_rankings": pd.DataFrame(columns=COLUMNS),
    }
    monkeypatch.setattr(etl, "read_table", lambda name, columns=None: state[name].copy())
    monkeypatch.setattr(etl, "table_exists", lambda name: False)
    monkeypatch.setattr(etl, "write_table", lambda name, df, **kw: state.update({name: df.copy()}))
    return state


def seed(tables, *rows):
    df = pd.DataFrame(list(rows), columns=COLUMNS)
    df["draft_year"] = df["draft_year"].astype("Int64")
    df["positional_rank"] = df["positional_rank"].astype("Int64")
    df["global_rank"] = df["global_rank"].astype("Int64")
    tables["fact_rookie_rankings"] = df


def run(tables, rank_date, phase="pre_combine", year=2027, rank=1, capture="2026-11-10"):
    rankings = pd.DataFrame({"player_name": ["Ann One"], "global_rank": [None], "positional_rank": [rank]})
    etl.ingest_ranking_source(rankings, "WalterFootball_DL", "WalterFootball", phase, draft_year=year,
                              capture_date=capture, rank_date=rank_date)
    return tables["fact_rookie_rankings"]


def pick(fact, phase, year):
    return fact[(fact["phase"] == phase) & (fact["draft_year"] == year)].reset_index(drop=True)


class TestEachRunKeepsItsOwnRankDate:
    def test_a_later_run_replaces_the_date_with_its_ranks(self, tables):
        seed(tables, fact_row("k_ann", "pre_combine", 2027, 5, "2026-11-03"))
        out = run(tables, "2026-11-10", rank=3)
        row = pick(out, "pre_combine", 2027)
        assert len(row) == 1
        assert row.loc[0, "positional_rank"] == 3
        assert row.loc[0, "rank_date"] == "2026-11-10"

    def test_a_date_older_than_the_stored_one_is_not_kept_over_the_new_run(self, tables):
        seed(tables, fact_row("k_ann", "pre_combine", 2027, 5, "2026-11-10"))
        out = run(tables, "2026-11-03", rank=4)
        assert pick(out, "pre_combine", 2027).loc[0, "rank_date"] == "2026-11-03"

    def test_a_first_run_stores_its_date(self, tables):
        out = run(tables, "2026-11-03")
        assert pick(out, "pre_combine", 2027).loc[0, "rank_date"] == "2026-11-03"

    @pytest.mark.parametrize("caller, first, second", [
        ("03b", "2026-11-03", "2026-11-10"),
        ("03d", "2026-04-30", "2026-05-07"),
        ("03x", "2026-05-16", "2026-05-23"),
    ])
    def test_every_caller_shape_gets_the_update(self, tables, caller, first, second):
        seed(tables, fact_row("k_ann", "post_draft", 2026, 5, first))
        out = run(tables, second, phase="post_draft", year=2026, rank=2)
        row = pick(out, "post_draft", 2026)
        assert (len(row), row.loc[0, "rank_date"], row.loc[0, "positional_rank"]) == (1, second, 2)

    @pytest.mark.parametrize("raw, want", [("Nov. 10, 2026.", "2026-11-10"), ("Sept. 5, 2026", "2026-09-05")])
    def test_a_page_style_date_is_stored_as_iso(self, tables, raw, want):
        out = run(tables, raw)
        assert pick(out, "pre_combine", 2027).loc[0, "rank_date"] == want


class TestTheKeptRows:
    def test_a_2027_run_leaves_the_2026_walterfootball_rows_unchanged(self, tables):
        old = [fact_row("k_ann", "post_draft", 2026, 5, "2026-04-19"),
               fact_row("k_bob", "post_draft", 2026, 7, "2026-04-19")]
        seed(tables, *old)
        before = tables["fact_rookie_rankings"].copy()
        out = run(tables, "2026-11-10", phase="pre_combine", year=2027, rank=1)
        kept = pick(out, "post_draft", 2026).sort_values("player_key").reset_index(drop=True)
        pd.testing.assert_frame_equal(kept, before.sort_values("player_key").reset_index(drop=True),
                                      check_dtype=False)
        assert len(pick(out, "pre_combine", 2027)) == 1

    def test_the_same_phase_in_another_year_is_its_own_row(self, tables):
        seed(tables, fact_row("k_ann", "post_draft", 2026, 5, "2026-04-19"))
        out = run(tables, "2026-11-10", phase="post_draft", year=2027, rank=1)
        assert pick(out, "post_draft", 2026).loc[0, "rank_date"] == "2026-04-19"
        assert pick(out, "post_draft", 2026).loc[0, "positional_rank"] == 5
        assert pick(out, "post_draft", 2027).loc[0, "rank_date"] == "2026-11-10"

    def test_a_later_phase_leaves_the_earlier_phase_rows(self, tables):
        seed(tables, fact_row("k_ann", "pre_combine", 2027, 5, "2026-11-03"))
        out = run(tables, "2027-03-20", phase="post_combine", year=2027, rank=2)
        assert pick(out, "pre_combine", 2027).loc[0, "rank_date"] == "2026-11-03"
        assert pick(out, "post_combine", 2027).loc[0, "rank_date"] == "2027-03-20"
