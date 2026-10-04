"""02d's main(), end to end on the committed Fantrax fixtures (#117).

main() runs against a throwaway data dir: the draft-results and
transaction-history fixtures as the raw captures, hand-built dims, and a
small Roster State, preseason capture and eligibility list. The module's
`DATA` and every `*_PATH` / `*_GLOB` constant are pointed at that dir, so
nothing under data/ is written. Only dim_contract and dim_season come from
data/ (copied in).
"""
import importlib
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import pandas as pd
import pytest

rt = importlib.import_module("02d_fact_roster_transactions")

FIXTURES = REPO / "tests" / "fixtures" / "fantrax"
OUTPUTS = ("FACT_PATH", "ASSET_PATH", "PICK_PATH", "TRADE_LOG_PATH")
SEASON = "2026-2027"
MINIMUM = 2_000_000.0                       # dim_contract's FA min_salary
READ = pd.Timestamp("2026-09-18")           # the day period 1's roster was read
ROSTERED_ONLY = "0zz99"                     # on a roster, never drafted or moved


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


SLOTS = _load("draft_results.json")["responses"][0]["data"]["draftPicksOrdered"]
MADE = [s for s in SLOTS if s.get("scorerId")]
TXNS = [r for page in _load("txn_history.json")
        for r in page["responses"][0]["data"]["table"]["rows"]]
TEAM_IDS = sorted({s["teamId"] for s in SLOTS}
                  | {c["teamId"] for r in TXNS for c in r["cells"] if c.get("teamId")})
TEAM_KEY = {team_id: f"A{i:02d}" for i, team_id in enumerate(TEAM_IDS, 1)}

# What the fixtures hold, counted off the raw rows rather than through 02d's parsers.
PLAYER_TRADES = [r for r in TXNS if r.get("transactionCode") is None
                 and (r.get("scorer") or {}).get("scorerId")]
CLAIMS = [r for r in TXNS if r.get("transactionCode") == "CLAIM"]
DROPS = [r for r in TXNS if r.get("transactionCode") == "DROP"]

# The drafted copies the tests follow (none is traded or dropped in the fixture),
# and the claim Roster State shows.
ON_STATE, ON_PRESEASON, ELIGIBLE, UNPRICED = MADE[1], MADE[2], MADE[3], MADE[-1]
CLAIMED = CLAIMS[0]


def _team(row):
    return TEAM_KEY[row["teamId"]]


def _claim_team(row):
    return TEAM_KEY[next(c["teamId"] for c in row["cells"] if c["key"] == "team")]


def _pool_salary(pick):
    return 3_000_000.0 + 100_000 * MADE.index(pick)


def write_inputs(data: Path):
    raw = data / "raw"
    raw.mkdir()
    shutil.copy(FIXTURES / "draft_results.json", raw / "fantrax_draftresults_2026.json")
    shutil.copy(FIXTURES / "txn_history.json", raw / "fantrax_txn_history_2026.json")
    for dim in ("dim_contract", "dim_season"):
        shutil.copy(REPO / "data" / f"{dim}.parquet", data / f"{dim}.parquet")

    pd.DataFrame({"fantrax_team_id": TEAM_IDS, "team_key": [TEAM_KEY[t] for t in TEAM_IDS],
                  "conference": "A"}).to_parquet(data / "dim_fantasy_teams.parquet", index=False)
    pd.DataFrame({"scorer_id": [MADE[0]["scorerId"], ON_STATE["scorerId"]],
                  "gsis_id": ["00-0000001", None],
                  "player_key": [None, "pk-0001"]}
                 ).to_parquet(data / "dim_fantrax_crosswalk.parquet", index=False)
    pd.DataFrame([{"season": 2026, "week": "DRAFT", "capture_date": "2026-06-09",
                   "scorer_id": p["scorerId"], "salary": _pool_salary(p)}
                  for p in MADE if p is not UNPRICED]
                 ).to_parquet(data / "fact_fantrax_adp.parquet", index=False)

    pd.DataFrame(
        [(SEASON, 1, _team(ON_STATE), ON_STATE["scorerId"], "Minors", 9_100_000.0, "Minor", READ),
         (SEASON, 1, _claim_team(CLAIMED), CLAIMED["scorer"]["scorerId"], "Bench",
          2_600_000.0, "FA", READ),
         (SEASON, 1, TEAM_KEY[TEAM_IDS[0]], ROSTERED_ONLY, "Bench", MINIMUM, "FA", READ)],
        columns=["season_id", "period", "team_key", "scorer_id", "roster_slot", "salary",
                 "contract_id", "capture_date"]
    ).to_parquet(data / "fact_roster_state.parquet", index=False)
    pd.DataFrame(
        [(SEASON, _team(ON_PRESEASON), ON_PRESEASON["scorerId"], 7_500_000.0,
          pd.Timestamp("2026-07-18"))],
        columns=["season_id", "team_key", "scorer_id", "salary", "capture_date"]
    ).to_parquet(data / "fact_preseason_salary.parquet", index=False)
    pd.DataFrame({"scorer_id": [ELIGIBLE["scorerId"]], "season": [2026], "week": ["PRE"],
                  "capture_date": ["2026-07-18"]}
                 ).to_parquet(data / "fact_minor_eligibility.parquet", index=False)


@pytest.fixture
def data(tmp_path, monkeypatch):
    """The temp data dir, with 02d pointed at it."""
    write_inputs(tmp_path)
    monkeypatch.setattr(rt, "DATA", tmp_path)
    for name, value in list(vars(rt).items()):
        if name.endswith("_PATH"):
            monkeypatch.setattr(rt, name, tmp_path / Path(value).name)
        elif name.endswith("_GLOB"):
            monkeypatch.setattr(rt, name, str(tmp_path / "raw" / Path(value).name))
    return tmp_path


def outputs():
    return {name: pd.read_parquet(getattr(rt, name)) for name in OUTPUTS}


class TestMain:
    def test_ledger_holds_the_draft_rows_and_every_transaction_leg(self, data):
        rt.main()
        ledger = pd.read_parquet(rt.FACT_PATH)
        assert ledger["event_type"].value_counts().to_dict() == {
            rt.EVENT_TYPE: len(MADE),
            rt.TRADE_AWAY: len(PLAYER_TRADES), rt.TRADE_IN: len(PLAYER_TRADES),
            rt.CLAIM_EVENT: len(CLAIMS), rt.DROP_EVENT: len(DROPS)}
        assert len(MADE) == 28 and len(ledger) == 36
        assert list(ledger.columns) == rt.LEDGER_COLS

    def test_a_leg_with_no_scoring_period_stops_the_run(self, data, monkeypatch):
        # Fantrax stamps every move with the period it takes effect in. Without
        # one the move cannot be placed in a stint, so the ledger is not rebuilt.
        parse = rt.parse_txn_rows

        def unstamped(*args):
            trade_log, legs, stats = parse(*args)
            legs[0]["period"] = None
            return trade_log, legs, stats

        monkeypatch.setattr(rt, "parse_txn_rows", unstamped)
        with pytest.raises(RuntimeError, match="Scoring Period"):
            rt.main()
        assert not rt.FACT_PATH.exists()

    def test_ledger_key_is_whole_and_unique(self, data):
        rt.main()
        ledger = pd.read_parquet(rt.FACT_PATH)
        assert ledger["season_id"].notna().all() and set(ledger["season_id"]) == {SEASON}
        assert ledger[rt.LEDGER_KEY + ["event_date"]].notna().all().all()
        assert not ledger.duplicated(rt.LEDGER_KEY).any()
        assert set(ledger["team_key"]) <= set(TEAM_KEY.values())

    def test_rosters_reach_the_ledger(self, data):
        rt.main()
        ledger = pd.read_parquet(rt.FACT_PATH)
        draft = ledger[ledger["event_type"] == rt.EVENT_TYPE].set_index("scorer_id")
        terms = draft[["contract_id", "contract_value"]]
        # Roster State sets contract and salary; the preseason capture, salary only.
        assert tuple(terms.loc[ON_STATE["scorerId"]]) == ("Minor", 9_100_000)
        assert tuple(terms.loc[ON_PRESEASON["scorerId"]]) == ("1st", 7_500_000)
        # No roster shows these two: the eligibility list and the draft-time pool.
        assert tuple(terms.loc[ELIGIBLE["scorerId"]]) == ("Minor", _pool_salary(ELIGIBLE))
        assert tuple(terms.loc[UNPRICED["scorerId"]]) == ("1st", MINIMUM)

        claim = ledger[(ledger["event_type"] == rt.CLAIM_EVENT)
                       & (ledger["scorer_id"] == CLAIMED["scorer"]["scorerId"])].iloc[0]
        assert (claim["team_key"], claim["contract_id"], claim["contract_value"]) == (
            _claim_team(CLAIMED), "FA", 2_600_000)

    def test_asset_bridge_covers_every_copy(self, data):
        rt.main()
        out = outputs()
        assets, ledger = out["ASSET_PATH"], out["FACT_PATH"]
        assert assets["asset_id"].is_unique and assets["scorer_id"].is_unique
        assert set(ledger["scorer_id"]) | {ROSTERED_ONLY} <= set(assets["scorer_id"])
        by_scorer = assets.set_index("scorer_id")
        assert (ledger["asset_id"] == ledger["scorer_id"].map(by_scorer["asset_id"])).all()
        assert by_scorer.loc[MADE[0]["scorerId"], "asset_type"] == "player"
        assert by_scorer.loc[ON_STATE["scorerId"], "asset_type"] == "prospect"

    def test_pick_grid_and_trade_log(self, data):
        rt.main()
        out = outputs()
        assert len(out["PICK_PATH"]) == len(SLOTS) and out["PICK_PATH"]["pick_ref"].is_unique
        log = out["TRADE_LOG_PATH"]
        assert len(log) == sum(r.get("transactionCode") is None for r in TXNS)
        assert int((log["asset_kind"] == "player").sum()) == len(PLAYER_TRADES)

    def test_a_second_run_changes_nothing(self, data):
        rt.main()
        first = outputs()
        rt.main()
        second = outputs()
        for name in OUTPUTS:
            pd.testing.assert_frame_equal(first[name], second[name], obj=name)

    def test_a_rerun_over_an_existing_ledger_is_byte_identical(self, data):
        # scripts/run_pipeline.py commits data/ on a byte diff. Compared from
        # the second run on: the first one, into an empty dir, writes the
        # ledger's pick columns as int64 and every later one as double.
        rt.main()
        rt.main()
        settled = {name: getattr(rt, name).read_bytes() for name in OUTPUTS}
        rt.main()
        assert [name for name in OUTPUTS if getattr(rt, name).read_bytes() != settled[name]] == []
