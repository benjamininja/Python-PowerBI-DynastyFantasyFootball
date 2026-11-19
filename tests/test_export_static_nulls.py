import json
import types
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent


def _load_exporter():
    src = (REPO / "mouserat_trade-bud" / "export_static.py").read_text(encoding="utf-8")
    block = src[src.index("def _nulls_for_nan"): src.index("def export(")]
    ns = {"json": json, "Path": Path, "pd": pd}
    exec(block, ns)
    return types.SimpleNamespace(_nulls_for_nan=ns["_nulls_for_nan"], _write_json=ns["_write_json"])


def _payload():
    return {
        "team_abbr": pd.NA,
        "when": pd.NaT,
        "nested": {"rows": [{"team_abbr": pd.NA, "n": 1.0}, pd.NaT, float("nan")]},
        "kept": "ok",
    }


def test_missing_scalars_become_none():
    out = _load_exporter()._nulls_for_nan(_payload())
    assert out["team_abbr"] is None
    assert out["when"] is None
    assert out["nested"]["rows"][0] == {"team_abbr": None, "n": 1.0}
    assert out["nested"]["rows"][1] is None
    assert out["nested"]["rows"][2] is None
    assert out["kept"] == "ok"


def test_written_json_parses_with_nulls_and_no_text_markers(tmp_path):
    exporter = _load_exporter()
    path = tmp_path / "t.json"
    exporter._write_json(path, _payload())
    text = path.read_text(encoding="utf-8")
    assert "<NA>" not in text and "NaT" not in text
    parsed = json.loads(text)
    assert parsed["team_abbr"] is None
    assert parsed["nested"]["rows"][0]["team_abbr"] is None
