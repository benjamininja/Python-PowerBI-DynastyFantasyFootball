"""The storage seam's contract (#77, docs/research/storage-seam-inventory.md §7).

`etl.read_table` / `etl.write_table` address a table by name; the registry
(docs/data_model.yml) is the schema a write is checked against. The contract
cases run on a temp data dir with a small fixture registry. The golden cases
run every published table through the seam against the real registry.

Parquet is the only backend today. The Postgres backend joins this suite
behind `TEST_DATABASE_URL` when it lands.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import numpy as np
import pandas as pd
import pytest
import yaml

import etl_helpers as etl

REGISTRY = {"tables": [
    {"name": "fact_snap", "type": "fact", "grain": "(day, source, player)",
     "columns": [{"name": "day", "dtype": "datetime64[us]"}, {"name": "source", "dtype": "str"},
                 {"name": "player", "dtype": "str"}, {"name": "value", "dtype": "float64"}]},
    {"name": "dim_one", "type": "dim", "grain": "key",
     "columns": [{"name": "key", "dtype": "int64"}, {"name": "label", "dtype": "str"}]},
    {"name": "fact_types", "type": "fact", "grain": "id",
     "columns": [{"name": "id", "dtype": "int64"}, {"name": "nullable_int", "dtype": "Int64"},
                 {"name": "small_int", "dtype": "int32"}, {"name": "gappy", "dtype": "float64"},
                 {"name": "day_us", "dtype": "datetime64[us]"}, {"name": "day_ms", "dtype": "datetime64[ms]"},
                 {"name": "at_utc", "dtype": "datetime64[us, UTC]"},
                 {"name": "empty", "dtype": "object", "sql_type": "text"},
                 {"name": "flag", "dtype": "bool"}, {"name": "text", "dtype": "str"},
                 {"name": "camelCase", "dtype": "str"}]},
    {"name": "fact_unseen", "type": "fact", "grain": "id",
     "columns": [{"name": "id", "dtype": "int64"},
                 {"name": "games", "dtype": "object", "sql_type": "integer"}]},
]}


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A temp data dir and the fixture registry."""
    registry = tmp_path / "registry.yml"
    registry.write_text(yaml.safe_dump(REGISTRY), encoding="utf-8")
    monkeypatch.setattr(etl, "REGISTRY_PATH", registry)
    monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path))
    return tmp_path


def snap(rows):
    df = pd.DataFrame(rows, columns=["day", "source", "player", "value"])
    return df.assign(day=pd.to_datetime(df["day"]).astype("datetime64[us]"))


D1, D2 = "2026-10-01", "2026-10-08"
BASE = snap([(D1, "KTC", "a", 1.0), (D1, "KTC", "b", 2.0), (D1, "DS", "a", 3.0), (D2, "KTC", "a", 4.0)])


def typed():
    return pd.DataFrame({
        "id": np.array([1, 2, 3], dtype="int64"),
        "nullable_int": pd.array([1, None, 3], dtype="Int64"),
        "small_int": np.array([7, 8, 9], dtype="int32"),
        "gappy": [1.5, np.nan, 3.0],
        "day_us": pd.to_datetime(["2026-01-01", None, "2026-01-03"]).astype("datetime64[us]"),
        "day_ms": pd.to_datetime(["2026-03-01", "2026-03-02", "2026-03-03"]).astype("datetime64[ms]"),
        "at_utc": pd.to_datetime(["2026-01-01 20:15", "2026-01-08 20:15", None], utc=True).astype("datetime64[us, UTC]"),
        "empty": [None, None, None],
        "flag": [True, False, True],
        "text": ["x", None, "z"],
        "camelCase": ["a", "b", "c"],
    })


class TestReplace:
    def test_round_trips_and_returns_the_row_count(self, store):
        assert etl.write_table("fact_snap", BASE) == 4
        pd.testing.assert_frame_equal(etl.read_table("fact_snap"), BASE)

    def test_replaces_the_whole_table(self, store):
        etl.write_table("fact_snap", BASE)
        assert etl.write_table("fact_snap", BASE.iloc[:1]) == 1
        assert len(etl.read_table("fact_snap")) == 1

    def test_leaves_no_temp_file(self, store):
        etl.write_table("fact_snap", BASE)
        assert sorted(p.name for p in store.glob("fact_snap*")) == ["fact_snap.parquet"]

    def test_a_failed_write_leaves_the_table_as_it_was(self, store, monkeypatch):
        etl.write_table("fact_snap", BASE)

        def fail(self, path, **kwargs):
            Path(path).write_bytes(b"half a file")
            raise OSError("disk full")
        monkeypatch.setattr(pd.DataFrame, "to_parquet", fail)
        with pytest.raises(OSError):
            etl.write_table("fact_snap", BASE.iloc[:1])
        monkeypatch.undo()
        assert len(pd.read_parquet(store / "fact_snap.parquet")) == 4


class TestReplacePartition:
    def test_keys_replace_only_the_slices_in_the_batch(self, store):
        etl.write_table("fact_snap", BASE)
        # the (D1, KTC) slice now holds one other player: no orphan a or b
        total = etl.write_table("fact_snap", snap([(D1, "KTC", "c", 9.0)]),
                                mode="replace_partition", keys=("day", "source"))
        out = etl.read_table("fact_snap")
        assert total == len(out) == 3
        assert out[(out["day"] == D1) & (out["source"] == "KTC")]["player"].tolist() == ["c"]
        assert set(zip(out["source"], out["player"])) == {("DS", "a"), ("KTC", "a"), ("KTC", "c")}

    def test_keys_into_an_empty_store_is_a_plain_write(self, store):
        assert etl.write_table("fact_snap", BASE, mode="replace_partition", keys=("day",)) == 4

    def test_partition_with_an_empty_batch_clears_the_slice(self, store):
        etl.write_table("fact_snap", BASE)
        total = etl.write_table("fact_snap", BASE.iloc[0:0], mode="replace_partition",
                                partition={"source": ["KTC", "nobody"]})
        out = etl.read_table("fact_snap")
        assert total == 1 and out["source"].tolist() == ["DS"]
        assert str(out["day"].dtype) == "datetime64[us]"

    def test_partition_deletes_the_named_values_not_the_batch_s(self, store):
        etl.write_table("fact_snap", BASE)
        etl.write_table("fact_snap", snap([(D2, "DS", "z", 5.0)]), mode="replace_partition",
                        partition={"source": ["KTC"]})
        out = etl.read_table("fact_snap")
        assert sorted(zip(out["source"], out["player"])) == [("DS", "a"), ("DS", "z")]

    def test_partition_on_two_columns_is_their_conjunction(self, store):
        etl.write_table("fact_snap", BASE)
        etl.write_table("fact_snap", BASE.iloc[0:0], mode="replace_partition",
                        partition={"source": ["KTC"], "player": ["a"]})
        assert len(etl.read_table("fact_snap")) == 2

    @pytest.mark.parametrize("kwargs", [{}, {"keys": ("day",), "partition": {"source": ["KTC"]}}])
    def test_takes_exactly_one_of_keys_and_partition(self, store, kwargs):
        with pytest.raises(etl.StorageError, match="exactly one"):
            etl.write_table("fact_snap", BASE, mode="replace_partition", **kwargs)


class TestUpsert:
    def test_keeps_the_latest_row_per_key_and_the_rest(self, store):
        etl.write_table("fact_snap", BASE)
        total = etl.write_table("fact_snap", snap([(D1, "KTC", "a", 10.0), (D2, "DS", "n", 6.0)]),
                                mode="upsert")
        out = etl.read_table("fact_snap")
        assert total == len(out) == 5
        value = out.set_index(["day", "source", "player"])["value"]
        assert value[(pd.Timestamp(D1), "KTC", "a")] == 10.0
        assert value[(pd.Timestamp(D1), "KTC", "b")] == 2.0

    def test_on_explicit_keys(self, store):
        etl.write_table("dim_one", pd.DataFrame({"key": [1, 2], "label": ["a", "b"]}))
        etl.write_table("dim_one", pd.DataFrame({"key": [3], "label": ["b"]}), mode="upsert", keys=("label",))
        assert sorted(etl.read_table("dim_one")["key"]) == [1, 3]

    def test_partition_is_refused(self, store):
        with pytest.raises(etl.StorageError, match="replace_partition"):
            etl.write_table("fact_snap", BASE, mode="upsert", partition={"source": ["KTC"]})


class TestGuards:
    def test_an_undeclared_table_is_refused(self, store):
        for call in (lambda: etl.write_table("fact_nope", BASE), lambda: etl.read_table("fact_nope"),
                     lambda: etl.table_exists("fact_nope")):
            with pytest.raises(etl.StorageError, match="not declared"):
                call()

    def test_a_declared_table_with_no_data(self, store):
        assert etl.table_exists("fact_snap") is False
        with pytest.raises(etl.TableNotFound):
            etl.read_table("fact_snap")
        etl.write_table("fact_snap", BASE)
        assert etl.table_exists("fact_snap") is True

    def test_a_repeated_key_raises_and_writes_nothing(self, store):
        with pytest.raises(etl.StorageError, match="1 repeated key"):
            etl.write_table("fact_snap", pd.concat([BASE, BASE.iloc[:1]]))
        assert not (store / "fact_snap.parquet").exists()

    def test_a_null_key_raises(self, store):
        with pytest.raises(etl.StorageError, match="1 row.s. with a null key"):
            etl.write_table("fact_snap", BASE.assign(player=["a", None, "a", "a"]))

    @pytest.mark.parametrize("batch", [BASE.drop(columns="value"), BASE.assign(extra=1)])
    def test_a_column_mismatch_raises(self, store, batch):
        with pytest.raises(etl.StorageError, match="columns do not match"):
            etl.write_table("fact_snap", batch)

    def test_column_order_is_the_caller_s(self, store):
        etl.write_table("fact_snap", BASE[["value", "player", "source", "day"]])
        assert list(etl.read_table("fact_snap").columns) == ["value", "player", "source", "day"]

    def test_a_tz_aware_column_is_refused_where_the_registry_declares_none(self, store):
        aware = BASE.assign(day=BASE["day"].dt.tz_localize("UTC"))
        with pytest.raises(etl.StorageError, match="time zone"):
            etl.write_table("fact_snap", aware)

    def test_a_naive_column_is_refused_where_the_registry_declares_a_zone(self, store):
        naive = typed().assign(at_utc=lambda d: d["at_utc"].dt.tz_localize(None))
        with pytest.raises(etl.StorageError, match="time zone"):
            etl.write_table("fact_types", naive)

    def test_a_value_that_cannot_be_cast_raises(self, store):
        with pytest.raises(etl.StorageError, match="cannot cast"):
            etl.write_table("dim_one", pd.DataFrame({"key": ["x", "y"], "label": ["a", "b"]}))

    def test_an_object_column_of_numbers_and_na_casts_to_float(self, store):
        rows = pd.DataFrame({"day": BASE["day"], "source": BASE["source"], "player": BASE["player"],
                             "value": pd.Series([1.0, pd.NA, 3.0, 4.0], dtype="object")})
        etl.write_table("fact_snap", rows)
        got = etl.read_table("fact_snap")["value"]
        assert str(got.dtype) == "float64" and got.isna().tolist() == [False, True, False, False]

    def test_values_in_a_column_declared_empty_text_must_be_text(self, store):
        with pytest.raises(etl.StorageError, match="text declared"):
            etl.write_table("fact_types", typed().assign(empty=[1.0, 2.0, 3.0]))

    def test_first_numbers_land_in_a_column_declared_empty_numeric(self, store):
        # `object` + a numeric sql_type: no value seen yet. The old writers
        # let the first ones in; so does the seam, uncast.
        etl.write_table("fact_unseen", pd.DataFrame({"id": [1, 2], "games": [None, None]}))
        etl.write_table("fact_unseen", pd.DataFrame({"id": [3], "games": [3.0]}),
                        mode="replace_partition", keys=("id",))
        assert etl.read_table("fact_unseen")["games"].tolist()[2] == 3.0

    def test_an_unknown_mode_raises(self, store):
        with pytest.raises(etl.StorageError, match="unknown write mode"):
            etl.write_table("fact_snap", BASE, mode="append")


class TestDtypes:
    """Each hazard class of the inventory's section 5 comes back as declared."""

    def test_every_dtype_round_trips(self, store):
        etl.write_table("fact_types", typed())
        back = etl.read_table("fact_types")
        pd.testing.assert_frame_equal(back, typed())
        assert {c: str(t) for c, t in back.dtypes.items() if c not in ("text", "camelCase", "empty")} == {
            "id": "int64", "nullable_int": "Int64", "small_int": "int32", "gappy": "float64",
            "day_us": "datetime64[us]", "day_ms": "datetime64[ms]", "at_utc": "datetime64[us, UTC]",
            "flag": "bool"}
        assert back["nullable_int"].isna().tolist() == [False, True, False]
        assert back["gappy"].isna().tolist() == [False, True, False]

    def test_the_batch_is_cast_to_the_registry_on_write(self, store):
        loose = typed().assign(small_int=[7, 8, 9], nullable_int=[1.0, np.nan, 3.0],
                               day_us=pd.to_datetime(["2026-01-01", None, "2026-01-03"]))
        etl.write_table("fact_types", loose)
        stored = pd.read_parquet(store / "fact_types.parquet")
        assert str(stored["small_int"].dtype) == "int32" and str(stored["nullable_int"].dtype) == "Int64"
        assert str(stored["day_us"].dtype) == "datetime64[us]"

    def test_the_caller_s_frame_is_not_changed(self, store):
        loose = typed().assign(small_int=[7, 8, 9])
        etl.write_table("fact_types", loose)
        assert str(loose["small_int"].dtype) == "int64"

    def test_a_read_casts_a_file_that_drifted(self, store):
        typed().assign(small_int=[7, 8, 9]).to_parquet(store / "fact_types.parquet", index=False)
        assert str(etl.read_table("fact_types")["small_int"].dtype) == "int32"

    def test_a_column_projection(self, store):
        etl.write_table("fact_types", typed())
        back = etl.read_table("fact_types", columns=["small_int", "id"])
        assert list(back.columns) == ["small_int", "id"] and str(back["small_int"].dtype) == "int32"


# ---- The legacy helpers run on the seam -------------------------------------------
def legacy_load_replace_partition(df, path, part_cols):
    """`load_replace_partition` as it was before #77, kept here as the reference."""
    path = Path(path)
    part_cols = list(part_cols)
    if path.exists():
        old = pd.read_parquet(path)
        keys = set(map(tuple, df[part_cols].drop_duplicates().to_numpy()))
        mask = old[part_cols].apply(tuple, axis=1).isin(keys)
        df = pd.concat([old[~mask], df], ignore_index=True)
    df.to_parquet(path, index=False)
    return len(df)


def legacy_upsert_dynasty_crosswalk(new_rows, path):
    path = Path(path)
    sources = set(new_rows["source"].unique())
    if path.exists():
        prior = pd.read_parquet(path)
        xw = pd.concat([prior[~prior["source"].isin(sources)], new_rows], ignore_index=True)
    else:
        xw = new_rows
    xw.to_parquet(path, index=False)
    return xw


# (table, partition columns) as the notebooks call load_replace_partition
PARTITIONED = [("fact_dynasty_ranking_metrics", ("snapshot_date", "source_name")),
               ("fact_roster_state", ("season_id", "period")),
               ("fact_roster_transactions", ("season_id", "event_type")),
               ("fact_draft_pick", ("draft_season",)),
               ("fact_draft_pick_future", ("draft_season",)),
               ("dim_scoring_period", ("season_id",)),
               ("dim_division", ("season_id",)),
               ("dim_pick_value_curve", ("snapshot_date", "source_name")),
               ("dim_position_ceiling", ("snapshot_date",))]


class TestLegacyHelpers:
    @pytest.mark.parametrize("table,part_cols", PARTITIONED)
    def test_load_replace_partition_writes_the_bytes_it_always_wrote(self, tmp_path, table, part_cols):
        published = pd.read_parquet(REPO / "data" / f"{table}.parquet")
        first = published[part_cols[0]].iloc[0]
        batch = published[published[part_cols[0]] == first]       # rewrite one real slice
        old_dir, new_dir = tmp_path / "old", tmp_path / "new"
        for d, load in ((old_dir, legacy_load_replace_partition), (new_dir, etl.load_replace_partition)):
            d.mkdir()
            published.to_parquet(d / f"{table}.parquet", index=False)
            assert load(batch, d / f"{table}.parquet", part_cols) == len(published)
        assert (new_dir / f"{table}.parquet").read_bytes() == (old_dir / f"{table}.parquet").read_bytes()

    def test_upsert_dynasty_crosswalk_writes_the_bytes_it_always_wrote(self, tmp_path):
        published = pd.read_parquet(REPO / "data" / "dim_dynasty_crosswalk.parquet")
        batch = published[published["source"] == published["source"].iloc[0]]
        out = {}
        for d, upsert in ((tmp_path / "old", legacy_upsert_dynasty_crosswalk),
                          (tmp_path / "new", etl.upsert_dynasty_crosswalk)):
            d.mkdir()
            published.to_parquet(d / "dim_dynasty_crosswalk.parquet", index=False)
            out[d.name] = upsert(batch, d / "dim_dynasty_crosswalk.parquet")
        pd.testing.assert_frame_equal(out["new"], out["old"])
        assert ((tmp_path / "new" / "dim_dynasty_crosswalk.parquet").read_bytes()
                == (tmp_path / "old" / "dim_dynasty_crosswalk.parquet").read_bytes())

    def test_a_declared_table_is_guarded_through_the_shim(self, tmp_path):
        published = pd.read_parquet(REPO / "data" / "fact_roster_state.parquet")
        with pytest.raises(etl.StorageError, match="repeated key"):
            etl.load_replace_partition(pd.concat([published.iloc[:5]] * 2),
                                       tmp_path / "fact_roster_state.parquet", ("season_id", "period"))

    def test_a_file_the_registry_does_not_know_is_written_unguarded(self, tmp_path):
        df = pd.DataFrame({"k": [1, 1], "v": [1, 2]})
        assert etl.load_replace_partition(df, tmp_path / "scratch.parquet", ("k",)) == 2


# ---- Golden round-trip: every published table ---------------------------------------
TABLES = sorted(p.stem for p in (REPO / "data").glob("*.parquet"))
# A published table the seam's guards refuse today, and the ticket that fixes
# it. The case below asserts the refusal, so the entry has to go when the fix
# lands. Nothing is written to such a table through the seam until then.
REFUSED = {}     # empty since #109 keyed fact_trade_log on (transaction_id, asset_id)


class TestGolden:
    def test_every_published_table_is_declared(self):
        assert set(TABLES) == set(etl._registry())

    @pytest.mark.parametrize("table", TABLES)
    def test_write_then_read_gives_the_table_back(self, table, tmp_path, monkeypatch):
        published = pd.read_parquet(REPO / "data" / f"{table}.parquet")
        monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path))
        if table in REFUSED:
            with pytest.raises(etl.StorageError, match="breaks the grain"):
                etl.write_table(table, published)
            return
        assert etl.write_table(table, published) == len(published)
        pd.testing.assert_frame_equal(etl.read_table(table), published)
        # the seam cast nothing: the file is the one a plain write gives
        published.to_parquet(tmp_path / "plain.parquet", index=False)
        assert (tmp_path / f"{table}.parquet").read_bytes() == (tmp_path / "plain.parquet").read_bytes()
