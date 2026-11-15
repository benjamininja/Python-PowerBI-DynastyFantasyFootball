"""A rejected source has no row in the published rookie rankings, and 03x
cannot write one (#589, ADR-0022).

The rejected sources are read from docs/sources.yml (status `rejected`), so a
source rejected later is covered without a change here. A source is matched by
its id, its name, the short name in the name's brackets and its `match` words,
each lower-cased with everything but letters and digits taken out, and compared
whole (never as a part of a word).
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import check_sources as cs
import etl_helpers as etl

NOTEBOOK_03X = REPO / "notebooks" / "03x_manual_rankings.ipynb"
SOURCES_CELL = "03043218"


def _norm(text) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def rejected_names(sources) -> dict:
    """{normalised name: source id} for every rejected source."""
    found = {}
    for s in sources:
        if s.get("status") != "rejected":
            continue
        name = str(s.get("name", ""))
        words = [s["id"], re.sub(r"\(.*?\)", "", name)]
        words += re.findall(r"\((.*?)\)", name)
        words += list(s.get("match") or [])
        for w in words:
            if _norm(w):
                found[_norm(w)] = s["id"]
    return found


def rejected_rows(frame: pd.DataFrame, sources) -> dict:
    """{source id: row count} of rows whose source_name or source_site is a rejected source."""
    names = rejected_names(sources)
    hits: dict = {}
    rows = frame[[c for c in ("source_name", "source_site") if c in frame.columns]]
    for _, row in rows.iterrows():
        ids = {names[_norm(v)] for v in row if _norm(v) in names}
        for sid in ids:
            hits[sid] = hits.get(sid, 0) + 1
    return hits


def _src(sid, status="rejected", name=None, match=()):
    return {"id": sid, "name": name or sid, "status": status, "match": list(match)}


class TestTheCheckItself:
    SOURCES = [
        _src("keeptradecut", name="KeepTradeCut (KTC)"),
        _src("dynastyleaguefootball", name="Dynasty League Football (DLF)"),
        _src("fantasycalc", status="live", name="FantasyCalc"),
    ]

    def test_a_rejected_source_row_is_found_by_name_or_site(self):
        frame = pd.DataFrame({
            "source_name": ["DynastyLeagueFootball", "FantasyCalc", "KTC", "RotoBaller"],
            "source_site": ["DynastyLeagueFootball", "FantasyCalc", "KeepTradeCut", "RotoBaller"],
        })
        assert rejected_rows(frame, self.SOURCES) == {"dynastyleaguefootball": 1, "keeptradecut": 1}

    def test_a_row_is_counted_once_even_when_name_and_site_both_match(self):
        frame = pd.DataFrame({"source_name": ["KeepTradeCut"], "source_site": ["KeepTradeCut"]})
        assert rejected_rows(frame, self.SOURCES) == {"keeptradecut": 1}

    def test_spacing_and_case_do_not_hide_a_row(self):
        frame = pd.DataFrame({"source_name": ["Dynasty League Football"], "source_site": ["dlf"]})
        assert rejected_rows(frame, self.SOURCES) == {"dynastyleaguefootball": 1}

    def test_live_sources_and_part_words_are_not_found(self):
        frame = pd.DataFrame({"source_name": ["FantasyCalc", "DynastyLeagueFootballExtra"],
                              "source_site": ["FantasyCalc", "x"]})
        assert rejected_rows(frame, self.SOURCES) == {}

    def test_an_empty_table_has_no_rejected_rows(self):
        assert rejected_rows(pd.DataFrame(columns=["source_name", "source_site"]), self.SOURCES) == {}

    def test_the_real_manifest_names_the_rejected_sources_it_should(self):
        names = rejected_names(cs.load_yaml()["sources"])
        for expected in ("keeptradecut", "ktc", "fantasypros", "pff", "dynastyleaguefootball", "dlf"):
            assert expected in names, expected
        assert "fantasycalc" not in names and "rotoballer" not in names


class TestThePublishedTable:
    def test_fact_rookie_rankings_holds_no_row_of_a_rejected_source(self):
        found = rejected_rows(etl.read_table("fact_rookie_rankings"), cs.load_yaml()["sources"])
        assert found == {}, (
            f"fact_rookie_rankings holds rows of rejected sources (source id: rows): {found}. "
            "The rows leave the store first, then the snapshot is re-exported (#589)."
        )


class Test03xCannotWriteARejectedSource:
    def _sources_cell(self) -> str:
        nb = json.loads(NOTEBOOK_03X.read_text(encoding="utf-8"))
        cells = [c for c in nb["cells"] if c.get("id") == SOURCES_CELL]
        assert len(cells) == 1, f"03x has no cell {SOURCES_CELL}"
        return "".join(cells[0]["source"])

    def test_the_sources_cell_names_no_rejected_source(self):
        names = rejected_names(cs.load_yaml()["sources"])
        text = self._sources_cell()
        strings = re.findall(r'"([^"]*)"', text)
        assert strings, "the SOURCES cell holds no strings; the test reads the wrong cell"
        assert [s for s in strings if _norm(s) in names] == []

    def test_the_sources_cell_still_holds_the_live_sources(self):
        text = self._sources_cell()
        for kept in ("RotoBaller", "mystery_iono", "FantasyCalc"):
            assert f'"{kept}"' in text, kept
