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
        [(SEASON, _team(ON_PRESEASON), ON_PRESEASON["scorerId"], 7_500_000.0, "1st",
          pd.Timestamp("2026-07-18"))],
        columns=["season_id", "team_key", "scorer_id", "salary", "contract_id", "capture_date"]
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


def keys(ledger):
    return set(map(tuple, ledger[rt.LEDGER_KEY].to_numpy()))


def before_the_key(ledger):
    """A ledger as it was written before #96: no key columns, and `dead_money`."""
    return (ledger.drop(columns=["transaction_id", "period", "contract_source"])
            .assign(dead_money=0.0))


class TestUnkeyedMoves:
    LEDGER = pd.DataFrame({"event_type": [rt.EVENT_TYPE, rt.CLAIM_EVENT, rt.DROP_EVENT],
                           "transaction_id": [None, "tx1", None]})

    def test_counts_the_moves_with_no_transaction_id(self):
        # the draft row is rebuilt on every run, so it is not counted
        assert rt.unkeyed_moves(self.LEDGER) == 1

    def test_every_move_counts_on_a_ledger_with_no_such_column(self):
        assert rt.unkeyed_moves(self.LEDGER.drop(columns="transaction_id")) == 2

    def test_a_keyed_ledger_has_none(self):
        assert rt.unkeyed_moves(self.LEDGER.assign(transaction_id="tx")) == 0


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
        # A draft row is keyed by its slot's pick_ref, a move by Fantrax's txSetId.
        grid = pd.read_parquet(rt.PICK_PATH)
        is_draft = ledger["event_type"] == rt.EVENT_TYPE
        assert set(ledger.loc[is_draft, "transaction_id"]) == set(
            grid.loc[grid["is_made"], "pick_ref"])
        assert set(ledger.loc[~is_draft, "transaction_id"]) <= {r["txSetId"] for r in TXNS}
        assert ledger["period"].notna().all() and str(ledger["period"].dtype) == "Int64"
        assert set(ledger["contract_source"]) <= {
            rt.FROM_STATE, rt.FROM_PRESEASON, rt.FROM_DEFAULT, rt.NO_STINT}

    def test_the_key_survives_a_rebuild_from_shuffled_inputs(self, data, monkeypatch):
        rt.main()
        first = pd.read_parquet(rt.FACT_PATH)
        parse_txn, parse_draft = rt.parse_txn_rows, rt.parse_draft_results

        def legs_reversed(*args):
            trade_log, legs, stats = parse_txn(*args)
            return trade_log, legs[::-1], stats

        monkeypatch.setattr(rt, "parse_txn_rows", legs_reversed)
        monkeypatch.setattr(rt, "parse_draft_results",
                            lambda payloads: parse_draft(payloads).sample(frac=1, random_state=7))
        rt.main()
        assert keys(pd.read_parquet(rt.FACT_PATH)) == keys(first)

    def test_a_move_removed_from_the_log_changes_no_other_key(self, data, monkeypatch):
        rt.main()
        first = pd.read_parquet(rt.FACT_PATH)
        parse, removed = rt.parse_txn_rows, []

        def without_the_earliest(*args):
            trade_log, legs, stats = parse(*args)
            removed.append(rt.sort_legs(legs)[0])
            return trade_log, [l for l in legs if l is not removed[-1]], stats

        monkeypatch.setattr(rt, "parse_txn_rows", without_the_earliest)
        rt.main()
        second = pd.read_parquet(rt.FACT_PATH)
        gone = first[(first["transaction_id"] == removed[-1]["transaction_id"])
                     & (first["scorer_id"] == removed[-1]["scorer_id"])]
        assert len(gone) == 1
        assert keys(second) == keys(first) - keys(gone)
        # event_seq is sort order only: the same removal renumbers every later move.
        seq = {name: frame[frame["event_type"] != rt.EVENT_TYPE]
               .set_index(rt.LEDGER_KEY)["event_seq"] for name, frame in
               (("first", first), ("second", second))}
        assert (seq["second"] == seq["first"].loc[seq["second"].index] - 1).all()

    def test_a_ledger_from_before_the_key_is_rebuilt_whole(self, data):
        rt.main()
        first = pd.read_parquet(rt.FACT_PATH)
        before_the_key(first).to_parquet(rt.FACT_PATH, index=False)
        rt.main()
        ledger = pd.read_parquet(rt.FACT_PATH)
        assert list(ledger.columns) == rt.LEDGER_COLS
        assert ledger[rt.LEDGER_KEY].notna().all().all()
        assert keys(ledger) == keys(first)

    def test_a_dropped_column_goes_when_no_move_is_rebuilt(self, data, monkeypatch):
        # No transaction history on this machine: only the draft rows are
        # rebuilt, and the older file's `dead_money` still must not ride along.
        rt.main()
        first = pd.read_parquet(rt.FACT_PATH)
        draft = first[first["event_type"] == rt.EVENT_TYPE]
        before_the_key(draft).to_parquet(rt.FACT_PATH, index=False)
        monkeypatch.setattr(rt, "load_txn_rows", lambda: [])
        rt.main()
        ledger = pd.read_parquet(rt.FACT_PATH)
        assert list(ledger.columns) == rt.LEDGER_COLS
        assert keys(ledger) == keys(draft)

    def test_moves_from_before_the_key_stop_a_run_that_cannot_rebuild_them(self, data,
                                                                         monkeypatch):
        rt.main()
        before_the_key(pd.read_parquet(rt.FACT_PATH)).to_parquet(rt.FACT_PATH, index=False)
        written = rt.FACT_PATH.read_bytes()
        monkeypatch.setattr(rt, "load_txn_rows", lambda: [])
        with pytest.raises(RuntimeError, match="transaction_id"):
            rt.main()
        assert rt.FACT_PATH.read_bytes() == written

    def test_rosters_reach_the_ledger(self, data):
        rt.main()
        ledger = pd.read_parquet(rt.FACT_PATH)
        draft = ledger[ledger["event_type"] == rt.EVENT_TYPE].set_index("scorer_id")
        terms = draft[["contract_id", "contract_value"]]
        read = draft["contract_source"]
        # Roster State sets contract and salary. The preseason capture sets the
        # salary, and the contract of a copy no Roster State shows.
        assert tuple(terms.loc[ON_STATE["scorerId"]]) == ("Minor", 9_100_000)
        assert read.loc[ON_STATE["scorerId"]] == rt.FROM_STATE
        assert tuple(terms.loc[ON_PRESEASON["scorerId"]]) == ("1st", 7_500_000)
        assert read.loc[ON_PRESEASON["scorerId"]] == rt.FROM_PRESEASON
        # No roster shows these two: the eligibility list and the draft-time pool.
        assert tuple(terms.loc[ELIGIBLE["scorerId"]]) == ("Minor", _pool_salary(ELIGIBLE))
        assert tuple(terms.loc[UNPRICED["scorerId"]]) == ("1st", MINIMUM)
        assert read.loc[ELIGIBLE["scorerId"]] == read.loc[UNPRICED["scorerId"]] == rt.FROM_DEFAULT

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
