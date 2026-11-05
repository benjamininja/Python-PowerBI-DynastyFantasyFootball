"""The storage seam's contract (#77, docs/research/storage-seam-inventory.md §7).

`etl.read_table` / `etl.write_table` address a table by name; the registry
(docs/data_model.yml) is the schema a write is checked against. The contract
cases run on a temp data dir with a small fixture registry. The golden cases
run every published table through the seam against the real registry; the
Postgres golden cases load all of them in one transaction into the migrations'
schema and read each back (#135, B2).

The contract cases run on both backends: the `store` fixture is `parquet` (a
temp data dir) or `pg` (a scratch schema, `seam_contract`, in the database
at TEST_DATABASE_URL, reached as the ETL_STORAGE=postgres login). A case that
holds only for files, or only for the database, takes `parquet_store` or
sits in TestPostgres. With TEST_DATABASE_URL unset the `pg` cases skip;
REQUIRE_TEST_DATABASE=1 makes that a failure (the storage-pg CI job).
"""
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import numpy as np
import pandas as pd
import pytest
import yaml

import etl_helpers as etl

SCRATCH = "seam_contract"
REGISTRY = {"tables": [
    {"name": "fact_snap", "type": "fact", "grain": "(day, source, player)",
     "columns": [{"name": "day", "dtype": "datetime64[us]", "sql_type": "timestamp"},
                 {"name": "source", "dtype": "str", "sql_type": "text"},
                 {"name": "player", "dtype": "str", "sql_type": "text"},
                 {"name": "value", "dtype": "float64", "sql_type": "double precision"}]},
    {"name": "dim_one", "type": "dim", "grain": "key",
     "columns": [{"name": "key", "dtype": "int64", "sql_type": "integer"},
                 {"name": "label", "dtype": "str", "sql_type": "text"}]},
    {"name": "fact_types", "type": "fact", "grain": "id",
     "columns": [{"name": "id", "dtype": "int64", "sql_type": "integer"},
                 {"name": "nullable_int", "dtype": "Int64", "sql_type": "integer"},
                 {"name": "small_int", "dtype": "int32", "sql_type": "integer"},
                 {"name": "gappy", "dtype": "float64", "sql_type": "double precision"},
                 {"name": "day_us", "dtype": "datetime64[us]", "sql_type": "timestamp"},
                 {"name": "day_ms", "dtype": "datetime64[ms]", "sql_type": "timestamp"},
                 {"name": "at_utc", "dtype": "datetime64[us, UTC]", "sql_type": "timestamptz"},
                 {"name": "empty", "dtype": "object", "sql_type": "text"},
                 {"name": "flag", "dtype": "bool", "sql_type": "boolean"},
                 {"name": "text", "dtype": "str", "sql_type": "text"},
                 {"name": "camelCase", "dtype": "str", "sql_type": "text"}]},
    {"name": "fact_unseen", "type": "fact", "grain": "id",
     "columns": [{"name": "id", "dtype": "int64", "sql_type": "integer"},
                 {"name": "games", "dtype": "object", "sql_type": "integer"}]},
]}
PKS = {t["name"]: etl.table_grain(t) for t in REGISTRY["tables"]}


def pg_state():
    """The fixture registry as supabase/registry_state.json holds a table."""
    return {"tables": {f"{SCRATCH}.{t['name']}": {
        "schema": SCRATCH, "name": t["name"], "pk": PKS[t["name"]],
        "columns": [{"name": c["name"], "sql_type": c["sql_type"], "not_null": c["name"] in PKS[t["name"]]}
                    for c in t["columns"]]} for t in REGISTRY["tables"]}}


def pg_ddl(spec):
    """CREATE TABLE with every identifier quoted, which the generator does not
    do (the registry allows no mixed-case name; the fixture has one)."""
    cols = [f'"{c["name"]}" {c["sql_type"]}{" NOT NULL" if c["not_null"] else ""}' for c in spec["columns"]]
    cols.append("PRIMARY KEY (" + ", ".join(f'"{k}"' for k in spec["pk"]) + ")")
    return f'CREATE TABLE "{spec["schema"]}"."{spec["name"]}" (' + ", ".join(cols) + ")"


def database_url():
    required = bool(os.environ.get("REQUIRE_TEST_DATABASE"))
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        if required:
            pytest.fail("REQUIRE_TEST_DATABASE is set but TEST_DATABASE_URL is not", pytrace=False)
        pytest.skip("TEST_DATABASE_URL is not set")
    try:
        import psycopg
    except ImportError:
        if required:
            pytest.fail("REQUIRE_TEST_DATABASE is set but psycopg is not installed", pytrace=False)
        pytest.skip("psycopg is not installed")
    return url


def pg_scratch(tmp_path, monkeypatch):
    """Point the seam at the fixture registry in the scratch schema of the
    test database, empty tables, and drop them after the case. The schema
    exists already (the CI job creates it owned by etl_writer) or is created
    here by a login that may."""
    import psycopg
    import etl_storage_pg
    url = database_url()
    registry = tmp_path / "registry.yml"
    registry.write_text(yaml.safe_dump(REGISTRY), encoding="utf-8")
    state = tmp_path / "registry_state.json"
    state.write_text(json.dumps(pg_state()), encoding="utf-8")
    monkeypatch.setattr(etl, "REGISTRY_PATH", registry)
    monkeypatch.setattr(etl_storage_pg, "STATE_PATH", state)
    monkeypatch.setenv("ETL_STORAGE", "postgres")
    monkeypatch.setenv(etl_storage_pg.URL_ENV, url)
    specs = list(pg_state()["tables"].values())
    with psycopg.connect(url, autocommit=True) as admin:
        if not admin.execute("SELECT 1 FROM pg_namespace WHERE nspname = %s", (SCRATCH,)).fetchone():
            admin.execute(f"CREATE SCHEMA {SCRATCH}")
        for spec in specs:
            admin.execute(f'DROP TABLE IF EXISTS "{SCRATCH}"."{spec["name"]}"')
            admin.execute(pg_ddl(spec))
        try:
            yield tmp_path
        finally:
            for spec in specs:
                admin.execute(f'DROP TABLE IF EXISTS "{SCRATCH}"."{spec["name"]}"')


@pytest.fixture
def parquet_store(tmp_path, monkeypatch):
    """A temp data dir and the fixture registry."""
    registry = tmp_path / "registry.yml"
    registry.write_text(yaml.safe_dump(REGISTRY), encoding="utf-8")
    monkeypatch.setattr(etl, "REGISTRY_PATH", registry)
    monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path))
    return tmp_path


@pytest.fixture(params=["parquet", "pg"])
def store(request, tmp_path, monkeypatch):
    """The fixture registry on a backend: a temp data dir, or the scratch
    schema of the test database, emptied after each case."""
    if request.param == "parquet":
        yield request.getfixturevalue("parquet_store")
    else:
        yield from pg_scratch(tmp_path, monkeypatch)


def ordered(table, df):
    """`df` sorted by the table's key. A database keeps no row order."""
    return df.sort_values(PKS[table]).reset_index(drop=True)


def same(table, got, want):
    """The frames are equal. Under Postgres the rows are compared by key."""
    if os.environ.get("ETL_STORAGE") == "postgres":
        got, want = ordered(table, got), ordered(table, want)
    pd.testing.assert_frame_equal(got, want)


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
        same("fact_snap", etl.read_table("fact_snap"), BASE)

    def test_replaces_the_whole_table(self, store):
        etl.write_table("fact_snap", BASE)
        assert etl.write_table("fact_snap", BASE.iloc[:1]) == 1
        assert len(etl.read_table("fact_snap")) == 1

    def test_leaves_no_temp_file(self, parquet_store):
        etl.write_table("fact_snap", BASE)
        assert sorted(p.name for p in parquet_store.glob("fact_snap*")) == ["fact_snap.parquet"]

    def test_a_failed_write_leaves_the_table_as_it_was(self, parquet_store, monkeypatch):
        etl.write_table("fact_snap", BASE)

        def fail(self, path, **kwargs):
            Path(path).write_bytes(b"half a file")
            raise OSError("disk full")
        monkeypatch.setattr(pd.DataFrame, "to_parquet", fail)
        with pytest.raises(OSError):
            etl.write_table("fact_snap", BASE.iloc[:1])
        monkeypatch.undo()
        assert len(pd.read_parquet(parquet_store / "fact_snap.parquet")) == 4


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

    def test_partition_on_a_timestamp_column(self, store):
        etl.write_table("fact_snap", BASE)
        etl.write_table("fact_snap", BASE.iloc[0:0], mode="replace_partition",
                        partition={"day": [pd.Timestamp(D1)]})
        assert etl.read_table("fact_snap")["player"].tolist() == ["a"]

    @pytest.mark.parametrize("kwargs", [{}, {"keys": ("day",), "partition": {"source": ["KTC"]}}])
    def test_takes_exactly_one_of_keys_and_partition(self, store, kwargs):
        with pytest.raises(etl.StorageError, match="exactly one"):
            etl.write_table("fact_snap", BASE, mode="replace_partition", **kwargs)

    def test_an_empty_partition_is_refused_and_deletes_nothing(self, store):
        etl.write_table("fact_snap", BASE)
        with pytest.raises(etl.StorageError, match="names no column"):
            etl.write_table("fact_snap", BASE.iloc[0:0], mode="replace_partition", partition={})
        assert len(etl.read_table("fact_snap")) == 4


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

    def test_a_batch_repeating_an_explicit_key_keeps_its_last_row(self, store):
        etl.write_table("dim_one", pd.DataFrame({"key": [1, 2], "label": ["a", "b"]}))
        etl.write_table("dim_one", pd.DataFrame({"key": [5, 6], "label": ["z", "z"]}), mode="upsert",
                        keys=("label",))
        assert sorted(etl.read_table("dim_one")["key"]) == [1, 2, 6]

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
        assert etl.table_exists("fact_snap") is False

    def test_a_null_key_raises(self, store):
        with pytest.raises(etl.StorageError, match="1 row.s. with a null key"):
            etl.write_table("fact_snap", BASE.assign(player=["a", None, "a", "a"]))

    @pytest.mark.parametrize("batch", [BASE.drop(columns="value"), BASE.assign(extra=1)])
    def test_a_column_mismatch_raises(self, store, batch):
        with pytest.raises(etl.StorageError, match="columns do not match"):
            etl.write_table("fact_snap", batch)

    def test_column_order_is_the_caller_s(self, parquet_store):
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
        got = ordered("fact_snap", etl.read_table("fact_snap"))["value"]
        want = ordered("fact_snap", rows)["value"].isna().tolist()
        assert str(got.dtype) == "float64" and got.isna().tolist() == want

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

    def test_an_unknown_backend_is_refused(self, parquet_store, monkeypatch):
        monkeypatch.setenv("ETL_STORAGE", "sqlite")
        with pytest.raises(etl.StorageError, match="expected parquet or postgres"):
            etl.read_table("fact_snap")


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

    def test_the_batch_is_cast_to_the_registry_on_write(self, parquet_store):
        loose = typed().assign(small_int=[7, 8, 9], nullable_int=[1.0, np.nan, 3.0],
                               day_us=pd.to_datetime(["2026-01-01", None, "2026-01-03"]))
        etl.write_table("fact_types", loose)
        stored = pd.read_parquet(parquet_store / "fact_types.parquet")
        assert str(stored["small_int"].dtype) == "int32" and str(stored["nullable_int"].dtype) == "Int64"
        assert str(stored["day_us"].dtype) == "datetime64[us]"

    def test_the_batch_is_cast_to_the_registry_before_it_is_stored(self, store):
        loose = typed().assign(small_int=[7, 8, 9], nullable_int=[1.0, np.nan, 3.0],
                               day_us=pd.to_datetime(["2026-01-01", None, "2026-01-03"]))
        etl.write_table("fact_types", loose)
        pd.testing.assert_frame_equal(etl.read_table("fact_types"), typed())

    def test_the_caller_s_frame_is_not_changed(self, store):
        loose = typed().assign(small_int=[7, 8, 9])
        etl.write_table("fact_types", loose)
        assert str(loose["small_int"].dtype) == "int64"

    def test_a_read_casts_a_file_that_drifted(self, parquet_store):
        typed().assign(small_int=[7, 8, 9]).to_parquet(parquet_store / "fact_types.parquet", index=False)
        assert str(etl.read_table("fact_types")["small_int"].dtype) == "int32"

    def test_a_column_projection(self, store):
        etl.write_table("fact_types", typed())
        back = etl.read_table("fact_types", columns=["small_int", "id"])
        assert list(back.columns) == ["small_int", "id"] and str(back["small_int"].dtype) == "int32"

    def test_read_stored_gives_the_file_uncast(self, parquet_store):
        """The Gates compare the store with the registry, so their read must not cast."""
        typed().assign(small_int=[7, 8, 9]).to_parquet(parquet_store / "fact_types.parquet", index=False)
        assert str(etl.read_stored("fact_types")["small_int"].dtype) == "int64"

    def test_read_stored_reads_another_copy_of_the_store(self, parquet_store, tmp_path):
        other = tmp_path / "other"
        other.mkdir()
        pd.DataFrame({"k": [1]}).to_parquet(other / "anything.parquet", index=False)
        assert len(etl.read_stored("anything", other)) == 1       # no registry lookup

    def test_read_stored_of_a_table_with_no_data(self, parquet_store):
        with pytest.raises(etl.TableNotFound):
            etl.read_stored("fact_types")


class TestPostgres:
    """What holds for the database and not for a file: the twins of the cases
    above that are parquet-only."""

    @pytest.fixture
    def store(self, tmp_path, monkeypatch):
        yield from pg_scratch(tmp_path, monkeypatch)

    def test_a_failed_write_leaves_the_table_as_it_was(self, store):
        etl.write_table("dim_one", pd.DataFrame({"key": [1, 2], "label": ["a", "b"]}))
        with pytest.raises(etl.StorageError, match="out of range"):
            etl.write_table("dim_one", pd.DataFrame({"key": [3, 2 ** 40], "label": ["c", "d"]}))
        assert sorted(etl.read_table("dim_one")["key"]) == [1, 2]

    def test_a_failed_partition_write_leaves_the_slice_as_it_was(self, store):
        etl.write_table("dim_one", pd.DataFrame({"key": [1, 2], "label": ["a", "b"]}))
        with pytest.raises(etl.StorageError, match="out of range"):
            etl.write_table("dim_one", pd.DataFrame({"key": [1, 2 ** 40], "label": ["c", "d"]}),
                            mode="replace_partition", keys=("key",))
        assert etl.read_table("dim_one")["label"].tolist() == ["a", "b"]

    def test_a_value_the_database_refuses_is_a_storage_error(self, store):
        with pytest.raises(etl.StorageError):
            etl.write_table("fact_unseen", pd.DataFrame({"id": [1], "games": [2.5]}))

    def test_any_database_error_is_a_storage_error(self, store):
        import psycopg
        with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as admin:
            admin.execute(f'DROP TABLE "{SCRATCH}"."dim_one"')
        one = pd.DataFrame({"key": [1], "label": ["a"]})
        for call in (lambda: etl.read_table("dim_one"), lambda: etl.table_exists("dim_one"),
                     lambda: etl.write_table("dim_one", one)):
            with pytest.raises(etl.StorageError, match="does not exist"):
                call()

    def test_columns_come_back_in_registry_order_whatever_the_caller_s(self, store):
        etl.write_table("fact_snap", BASE[["value", "player", "source", "day"]])
        assert list(etl.read_table("fact_snap").columns) == ["day", "source", "player", "value"]

    def test_rows_come_back_in_primary_key_order(self, store):
        etl.write_table("fact_snap", BASE.iloc[::-1])
        out = etl.read_table("fact_snap")
        keys = list(zip(out["day"], out["source"], out["player"]))
        assert keys == sorted(keys)

    def test_a_table_left_with_no_rows_holds_no_data(self, store):
        etl.write_table("fact_snap", BASE)
        etl.write_table("fact_snap", BASE.iloc[0:0])
        assert etl.table_exists("fact_snap") is False
        with pytest.raises(etl.TableNotFound):
            etl.read_table("fact_snap")

    def test_a_write_returns_the_count_of_the_whole_table(self, store):
        etl.write_table("fact_snap", BASE)
        assert etl.write_table("fact_snap", snap([(D2, "DS", "n", 6.0)]), mode="upsert") == 5


# ---- replace_partition writes what the helpers it replaced wrote -------------------
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


# (table, partition columns) as the notebooks call replace_partition
PARTITIONED = [("fact_dynasty_ranking_metrics", ("snapshot_date", "source_name")),
               ("fact_roster_state", ("season_id", "period")),
               ("fact_roster_transactions", ("season_id", "event_type")),
               ("fact_draft_pick", ("draft_season",)),
               ("fact_draft_pick_future", ("draft_season",)),
               ("dim_scoring_period", ("season_id",)),
               ("dim_division", ("season_id",)),
               ("dim_pick_value_curve", ("snapshot_date", "source_name")),
               ("dim_position_ceiling", ("snapshot_date",))]


class TestReplacePartitionAgainstTheOldHelpers:
    """`load_replace_partition` and `upsert_dynasty_crosswalk` are gone (#77
    phase 6). The reference copies above stay, so the seam is still held to
    the bytes those helpers wrote. Parquet only: the bytes are a file's."""

    @pytest.mark.parametrize("table,part_cols", PARTITIONED)
    def test_keys_write_the_bytes_load_replace_partition_wrote(self, tmp_path, monkeypatch, table, part_cols):
        published = pd.read_parquet(REPO / "data" / f"{table}.parquet")
        first = published[part_cols[0]].iloc[0]
        batch = published[published[part_cols[0]] == first]       # rewrite one real slice
        old_dir, new_dir = tmp_path / "old", tmp_path / "new"
        for d in (old_dir, new_dir):
            d.mkdir()
            published.to_parquet(d / f"{table}.parquet", index=False)
        assert legacy_load_replace_partition(batch, old_dir / f"{table}.parquet", part_cols) == len(published)
        monkeypatch.setattr(etl.CFG, "data_dir", str(new_dir))
        assert etl.write_table(table, batch, mode="replace_partition", keys=part_cols) == len(published)
        assert (new_dir / f"{table}.parquet").read_bytes() == (old_dir / f"{table}.parquet").read_bytes()

    def test_keys_on_source_write_the_bytes_upsert_dynasty_crosswalk_wrote(self, tmp_path, monkeypatch):
        table = "dim_dynasty_crosswalk"
        published = pd.read_parquet(REPO / "data" / f"{table}.parquet")
        batch = published[published["source"] == published["source"].iloc[0]]
        old_dir, new_dir = tmp_path / "old", tmp_path / "new"
        for d in (old_dir, new_dir):
            d.mkdir()
            published.to_parquet(d / f"{table}.parquet", index=False)
        old = legacy_upsert_dynasty_crosswalk(batch, old_dir / f"{table}.parquet")
        monkeypatch.setattr(etl.CFG, "data_dir", str(new_dir))
        etl.write_table(table, batch, mode="replace_partition", keys=("source",))
        pd.testing.assert_frame_equal(etl.read_table(table), old)
        assert (new_dir / f"{table}.parquet").read_bytes() == (old_dir / f"{table}.parquet").read_bytes()

    def test_a_repeated_key_is_refused(self, tmp_path, monkeypatch):
        published = pd.read_parquet(REPO / "data" / "fact_roster_state.parquet")
        monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path))
        with pytest.raises(etl.StorageError, match="repeated key"):
            etl.write_table("fact_roster_state", pd.concat([published.iloc[:5]] * 2),
                            mode="replace_partition", keys=("season_id", "period"))


# ---- Golden round-trip: every published table ---------------------------------------
TABLES = sorted(p.stem for p in (REPO / "data").glob("*.parquet"))
# A published table the seam's guards refuse today, and the ticket that fixes
# it. The case below asserts the refusal, so the entry has to go when the fix
# lands. Nothing is written to such a table through the seam until then.
REFUSED = {}     # empty since #109 keyed fact_trade_log on (transaction_id, asset_id)


def pg_breaks(conn, spec, batch, columns):
    """Why the database refused `batch`: rows per constraint it breaks, counted
    on an unconstrained copy of the table. Counts only, never a cell."""
    import etl_storage_pg as pg
    _, sql = pg._psycopg()
    probe = sql.Identifier("_probe")
    lines = []
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE TEMP TABLE {} AS SELECT * FROM {} WITH NO DATA")
                    .format(probe, pg._table(spec)))
        pg._copy(cur, probe, columns, pg._rows(batch, spec, columns))
        for col in spec["columns"]:
            if col["not_null"] and col["name"] not in spec["pk"]:
                n = cur.execute(sql.SQL("SELECT count(*) FROM {} WHERE {} IS NULL")
                                .format(probe, sql.Identifier(col["name"]))).fetchone()[0]
                if n:
                    lines.append(f"NOT NULL {spec['name']}.{col['name']}: {n} row(s)")
        checks = cur.execute(
            "SELECT conname, pg_get_expr(conbin, conrelid) FROM pg_constraint "
            "WHERE conrelid = %s::regclass AND contype = 'c'",
            (f"{spec['schema']}.{spec['name']}",)).fetchall()
        for name, expr in checks:
            n = cur.execute(sql.SQL("SELECT count(*) FROM {} WHERE ({}) IS FALSE")
                            .format(probe, sql.SQL(expr))).fetchone()[0]
            if n:
                lines.append(f"CHECK {name}: {n} row(s)")
        cur.execute(sql.SQL("DROP TABLE {}").format(probe))
    return lines


def pg_orphans(conn):
    """Rows per foreign key whose parent is missing, for every foreign key in
    the schema, counted with the rows loaded and the keys still deferred."""
    keys = conn.execute(
        "SELECT c.conname, c.conrelid::regclass::text, c.confrelid::regclass::text, "
        "(SELECT array_agg(a.attname ORDER BY k.ord) FROM unnest(c.conkey) WITH ORDINALITY k(n, ord) "
        " JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.n), "
        "(SELECT array_agg(a.attname ORDER BY k.ord) FROM unnest(c.confkey) WITH ORDINALITY k(n, ord) "
        " JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.n) "
        "FROM pg_constraint c WHERE c.contype = 'f' AND c.connamespace = 'football'::regnamespace "
        "ORDER BY c.conname").fetchall()
    lines = []
    for name, child, parent, ccols, pcols in keys:
        present = " AND ".join(f'c."{x}" IS NOT NULL' for x in ccols)
        match = " AND ".join(f'p."{y}" = c."{x}"' for x, y in zip(ccols, pcols))
        n = conn.execute(f"SELECT count(*) FROM {child} c WHERE {present} "
                         f"AND NOT EXISTS (SELECT 1 FROM {parent} p WHERE {match})").fetchone()[0]
        if n:
            lines.append(f"FOREIGN KEY {name}: {n} row(s) with no parent")
    return lines


def pg_load_published(url, frames):
    """Load every table of `frames` in one transaction, as the login in `url`,
    and commit. Returns the lines of what the database refused (nothing is then
    committed), or [] when every row went in with the deferred keys checked."""
    import psycopg
    import etl_storage_pg as pg
    _, sql = pg._psycopg()
    report = []
    with psycopg.connect(url) as conn:
        with conn.transaction() as tx:
            for name, frame in frames.items():
                entry = etl._table_entry(name)
                batch = etl._check_batch(frame, entry)
                spec = pg._spec(entry)
                columns = pg._check_columns(entry, spec)
                try:
                    with conn.transaction(), conn.cursor() as cur:
                        staged = pg.stage(cur, spec, columns, batch)
                        cur.execute(sql.SQL("DELETE FROM {}").format(pg._table(spec)))
                        pg.insert_staged(cur, spec, columns, staged)
                except psycopg.Error as exc:
                    first = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
                    report.append(f"{name}: refused: {first}")
                    try:
                        report.extend(pg_breaks(conn, spec, batch, columns))
                    except psycopg.Error as again:
                        report.append(f"{name}: no count: {(str(again).strip().splitlines() or [''])[0]}")
            if not report:
                report.extend(pg_orphans(conn))
            if not report:
                conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
            else:
                raise psycopg.Rollback(tx)
    return report


def pg_clear_published(url, names):
    import psycopg
    with psycopg.connect(url) as conn:
        for name in names:
            conn.execute(f'DELETE FROM football."{name}"')


@pytest.fixture(scope="module")
def golden_pg():
    """The test database holding every published table, loaded in one
    transaction as the login in TEST_DATABASE_URL (etl_writer in CI) against
    the migrations' schema. Emptied again afterwards."""
    url = database_url()
    frames = {t: pd.read_parquet(REPO / "data" / f"{t}.parquet") for t in TABLES}
    pg_clear_published(url, TABLES)
    try:
        report = pg_load_published(url, frames)
        if report:
            pytest.fail("the database refuses published rows:\n  " + "\n  ".join(report), pytrace=False)
        yield url, frames
    finally:
        pg_clear_published(url, TABLES)


def text_flavour_free(df, entry):
    """`df` with each declared text column as object and its gaps as None. The
    seam treats str, string and object as one text type (etl._coerce) and a
    database keeps only text, so a published column that is `string` where the
    registry says `str` (fact_roster_transactions.claim_method,
    fact_trade_log.pick_ref) cannot come back as `string`. Values and nulls
    are still compared exactly."""
    out = df.copy()
    for col in entry["columns"]:
        if str(col["dtype"]) in etl._TEXT_DTYPES:
            name = col["name"]
            out[name] = out[name].astype(object).where(out[name].notna(), None)
    return out


class TestGolden:
    def test_text_flavours_compare_equal_and_values_still_differ(self):
        entry = {"columns": [{"name": "k", "dtype": "int64"}, {"name": "t", "dtype": "str"}]}
        a = pd.DataFrame({"k": [1, 2], "t": pd.array(["x", None], dtype="string")})
        b = pd.DataFrame({"k": [1, 2], "t": pd.Series(["x", None], dtype="str")})
        pd.testing.assert_frame_equal(text_flavour_free(a, entry), text_flavour_free(b, entry))
        c = b.assign(t=["x", "y"])
        with pytest.raises(AssertionError):
            pd.testing.assert_frame_equal(text_flavour_free(a, entry), text_flavour_free(c, entry))

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

    @pytest.mark.parametrize("table", TABLES)
    def test_postgres_gives_the_published_table_back(self, table, golden_pg, monkeypatch):
        import etl_storage_pg
        url, frames = golden_pg
        published = frames[table]
        monkeypatch.setenv("ETL_STORAGE", "postgres")
        monkeypatch.setenv(etl_storage_pg.URL_ENV, url)
        if published.empty:
            assert etl.table_exists(table) is False
            return
        entry = etl._table_entry(table)
        key = etl.table_grain(entry)
        got = etl.read_table(table)[list(published.columns)]
        pd.testing.assert_frame_equal(
            text_flavour_free(got.sort_values(key).reset_index(drop=True), entry),
            text_flavour_free(published.sort_values(key).reset_index(drop=True), entry))
