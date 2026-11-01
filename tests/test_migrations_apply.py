import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import generate_migrations as gm

URL = os.environ.get("TEST_DATABASE_URL")
if not URL:
    if os.environ.get("REQUIRE_TEST_DATABASE"):
        pytest.fail("REQUIRE_TEST_DATABASE is set but TEST_DATABASE_URL is not", pytrace=False)
    pytest.skip("TEST_DATABASE_URL is not set", allow_module_level=True)

psycopg = pytest.importorskip("psycopg")

STATE = json.loads((REPO / "supabase" / gm.STATE_FILE).read_text(encoding="utf-8"))
TABLES = STATE["tables"]
PG_TYPE = {"text": "text", "integer": "integer", "double precision": "double precision",
           "boolean": "boolean", "date": "date", "timestamp": "timestamp without time zone",
           "timestamptz": "timestamp with time zone", "jsonb": "jsonb", "uuid": "uuid"}


@pytest.fixture()
def conn():
    with psycopg.connect(URL, autocommit=False) as c:
        yield c
        c.rollback()


def _refused(conn, role, sql):
    with conn.cursor() as cur:
        cur.execute(f"SET LOCAL ROLE {role}")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(sql)
    conn.rollback()


def test_columns_and_types_match_the_registry(conn):
    rows = conn.execute(
        "SELECT table_schema, table_name, column_name, data_type, is_nullable "
        "FROM information_schema.columns WHERE table_schema IN ('football','shared','ops')").fetchall()
    found = {(s, t, c): (d, n) for s, t, c, d, n in rows}
    for spec in TABLES.values():
        for col in spec["columns"]:
            data_type, nullable = found[(spec["schema"], spec["name"], col["name"])]
            assert data_type == PG_TYPE[col["sql_type"]], (spec["name"], col["name"])
            if col["not_null"]:
                assert nullable == "NO", (spec["name"], col["name"])
    assert len(found) == sum(len(s["columns"]) for s in TABLES.values())


def test_every_table_has_rls_its_pk_and_deferrable_fks(conn):
    for spec in TABLES.values():
        qualified = f"{spec['schema']}.{spec['name']}"
        (rls,) = conn.execute("SELECT relrowsecurity FROM pg_class WHERE oid = %s::regclass", (qualified,)).fetchone()
        assert rls, qualified
        pk = conn.execute(
            "SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid "
            "AND a.attnum = ANY(i.indkey) WHERE i.indrelid = %s::regclass AND i.indisprimary", (qualified,)).fetchall()
        assert {r[0] for r in pk} == set(spec["pk"]), qualified
        fks = conn.execute(
            "SELECT conname, condeferrable, condeferred FROM pg_constraint "
            "WHERE conrelid = %s::regclass AND contype = 'f'", (qualified,)).fetchall()
        assert {r[0] for r in fks} == {f["name"] for f in spec["fks"]}, qualified
        assert all(r[1] and r[2] for r in fks), qualified


def test_a_dim_row_can_be_deleted_and_reinserted_in_one_transaction(conn):
    with conn.cursor() as cur:
        cur.execute("SET LOCAL ROLE etl_writer")
        cur.execute("INSERT INTO football.dim_season (season_id) VALUES ('S1')")
        cur.execute("INSERT INTO football.dim_division (season_id, conference, division_name) VALUES ('S1','A','D')")
        conn.commit()
        cur.execute("SET LOCAL ROLE etl_writer")
        cur.execute("DELETE FROM football.dim_season WHERE season_id = 'S1'")
        cur.execute("INSERT INTO football.dim_season (season_id) VALUES ('S1')")
        conn.commit()
        cur.execute("SET LOCAL ROLE etl_writer")
        cur.execute("SELECT count(*) FROM football.dim_division WHERE season_id = 'S1'")
        assert cur.fetchone()[0] == 1
        cur.execute("DELETE FROM football.dim_division WHERE season_id = 'S1'")
        cur.execute("DELETE FROM football.dim_season WHERE season_id = 'S1'")
        conn.commit()


def test_a_child_without_a_parent_is_refused_at_commit(conn):
    with conn.cursor() as cur:
        cur.execute("SET LOCAL ROLE etl_writer")
        cur.execute("INSERT INTO football.dim_division (season_id, conference, division_name) VALUES ('NOPE','A','D')")
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.commit()
    conn.rollback()


def test_etl_writer_writes_football_and_ops_but_not_shared_owner(conn):
    with conn.cursor() as cur:
        cur.execute("SET LOCAL ROLE etl_writer")
        cur.execute("INSERT INTO ops.review_check (check_name, table_name, row_key, created_at) "
                    "VALUES ('c', 't', '{}', now())")
        cur.execute("SELECT count(*) FROM football.dim_season")
    conn.rollback()
    _refused(conn, "etl_writer", "SELECT * FROM shared.owner")


def test_etl_writer_can_call_the_pii_function(conn):
    with conn.cursor() as cur:
        cur.execute("SET LOCAL ROLE etl_writer")
        cur.execute("SELECT * FROM shared.pii_token_hashes()")
        cur.fetchall()
    conn.rollback()


def test_etl_reader_reads_but_never_writes_or_sees_shared(conn):
    with conn.cursor() as cur:
        cur.execute("SET LOCAL ROLE etl_reader")
        cur.execute("SELECT count(*) FROM football.dim_season")
        cur.execute("SELECT count(*) FROM ops.review_check")
    conn.rollback()
    _refused(conn, "etl_reader", "INSERT INTO football.dim_season (season_id) VALUES ('X')")
    _refused(conn, "etl_reader", "SELECT * FROM shared.owner")
    _refused(conn, "etl_reader", "SELECT * FROM shared.pii_token_hashes()")


def test_a_second_open_review_row_is_refused_until_the_first_is_resolved(conn):
    insert = ("INSERT INTO ops.review_check (check_name, table_name, row_key, created_at) "
              "VALUES ('c', 't', '{\"k\": 1}', %s)")
    conn.execute(insert, ("2026-01-01",))
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(insert, ("2026-01-02",))
    conn.rollback()
    conn.execute(insert, ("2026-01-01",))
    conn.execute("UPDATE ops.review_check SET resolved_at = now() WHERE check_name = 'c'")
    conn.execute(insert, ("2026-01-02",))
    conn.rollback()
