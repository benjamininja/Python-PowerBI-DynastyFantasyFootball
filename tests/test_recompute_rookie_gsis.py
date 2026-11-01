"""scripts/recompute_rookie_gsis.py on in-memory frames only (#301)."""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import pandas as pd
import pytest

import etl_helpers as etl

_spec = importlib.util.spec_from_file_location("recompute_rookie_gsis", REPO / "scripts" / "recompute_rookie_gsis.py")
rg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rg)


def _tables(fact_gsis):
    return {
        "dim_rookie_prospect": pd.DataFrame({
            "player_key": ["k_ann", "k_bob", "k_cy", "k_di"],
            "pfr_id": ["PfrAnn", "PfrBob", None, "PfrNone"],
        }),
        "dim_nfl_players": pd.DataFrame({
            "pfr_id": [None, "PfrAnn", "PfrBob", None],
            "gsis_id": ["00-0000000", "00-0000001", "00-0000002", "00-0000003"],
            "status": ["ACT", "ACT", "ACT", "ACT"],
        }),
        "fact_rookie_rankings": pd.DataFrame({
            "player_key": ["k_bob", "k_ann", "k_cy", "k_di", "k_ann"],
            "gsis_id": fact_gsis,
            "source_name": ["s1", "s1", "s1", "s1", "s2"],
            "global_rank": pd.array([2, 1, 3, 4, 5], dtype="Int64"),
        }),
    }


@pytest.fixture
def seam(monkeypatch):
    written = {}

    def install(tables):
        monkeypatch.setattr(etl, "read_table", lambda name, columns=None: tables[name].copy())
        monkeypatch.setattr(etl, "write_table", lambda name, df, **kw: written.update({name: df}))
        return written
    return install


WRONG = ["00-0000001", "00-0000000", "00-0000002", None, "00-0000009"]


class TestRecompute:
    def test_each_row_takes_the_id_of_its_own_pfr_row_or_null(self):
        t = _tables(WRONG)
        out = rg.recompute(t["fact_rookie_rankings"], t["dim_rookie_prospect"], t["dim_nfl_players"])
        assert out["gsis_id"].tolist()[:2] == ["00-0000002", "00-0000001"]
        assert out["gsis_id"].isna().tolist() == [False, False, True, True, False]
        assert out["gsis_id"].iloc[4] == "00-0000001"

    def test_only_gsis_id_changes(self):
        t = _tables(WRONG)
        before = t["fact_rookie_rankings"]
        out = rg.recompute(before, t["dim_rookie_prospect"], t["dim_nfl_players"])
        assert list(out.columns) == list(before.columns) and len(out) == len(before)
        others = [c for c in before.columns if c != "gsis_id"]
        assert out[others].equals(before[others])
        assert out["global_rank"].dtype == before["global_rank"].dtype

    def test_a_second_pass_changes_nothing(self):
        t = _tables(WRONG)
        once = rg.recompute(t["fact_rookie_rankings"], t["dim_rookie_prospect"], t["dim_nfl_players"])
        twice = rg.recompute(once, t["dim_rookie_prospect"], t["dim_nfl_players"])
        assert rg.changed_rows(once, twice) == 0

    def test_an_all_null_numeric_column_still_recomputes(self):
        t = _tables([float("nan")] * 5)
        out = rg.recompute(t["fact_rookie_rankings"], t["dim_rookie_prospect"], t["dim_nfl_players"])
        assert out["gsis_id"].iloc[0] == "00-0000002"


class TestDroppedTwin:
    def test_counts_rows_on_a_dropped_id_whose_pfr_id_has_a_live_row(self):
        nfl = pd.DataFrame({
            "pfr_id": ["PfrAnn", "PfrAnn", "PfrBob", None],
            "gsis_id": ["g_live", "g_drop", "g_bob_drop", "g_none_drop"],
            "status": ["ACT", etl.DROPPED_STATUS, etl.DROPPED_STATUS, etl.DROPPED_STATUS],
        })
        fixed = pd.DataFrame({"gsis_id": ["g_drop", "g_drop", "g_live", "g_bob_drop", "g_none_drop", None]})
        assert rg.on_dropped_with_live_twin(fixed, nfl) == 2

    def test_counts_rows_and_ids_on_dropped_ids(self):
        nfl = pd.DataFrame({
            "pfr_id": ["PfrAnn", "PfrBob"],
            "gsis_id": ["g_live", "g_drop"],
            "status": ["ACT", etl.DROPPED_STATUS],
        })
        fixed = pd.DataFrame({"gsis_id": ["g_drop", "g_drop", "g_live", None]})
        assert rg.on_dropped_ids(fixed, nfl) == (2, 1)

    def test_recompute_prefers_the_live_row_of_a_shared_pfr_id(self):
        t = _tables(WRONG)
        t["dim_nfl_players"] = pd.concat([t["dim_nfl_players"], pd.DataFrame({
            "pfr_id": ["PfrAnn"], "gsis_id": ["00-0000099"], "status": [etl.DROPPED_STATUS]})],
            ignore_index=True)
        out = rg.recompute(t["fact_rookie_rankings"], t["dim_rookie_prospect"], t["dim_nfl_players"])
        assert out["gsis_id"].iloc[1] == "00-0000001"


class TestMain:
    def test_writes_the_fixed_table_and_prints_counts_only(self, seam, capsys):
        written = seam(_tables(WRONG))
        assert rg.main() == 0
        assert list(written) == ["fact_rookie_rankings"]
        assert written["fact_rookie_rankings"]["gsis_id"].tolist()[:2] == ["00-0000002", "00-0000001"]
        printed = capsys.readouterr().out
        assert "gsis_id changed 4" in printed
        assert "00-0000" not in printed

    def test_writes_nothing_when_already_right(self, seam, capsys):
        t = _tables(WRONG)
        t["fact_rookie_rankings"] = rg.recompute(
            t["fact_rookie_rankings"], t["dim_rookie_prospect"], t["dim_nfl_players"])
        written = seam(t)
        assert rg.main() == 0
        assert written == {}
        assert "not written" in capsys.readouterr().out
