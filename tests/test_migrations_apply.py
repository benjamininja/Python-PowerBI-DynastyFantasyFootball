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

from test_etl_storage import refuse_unless_throwaway

refuse_unless_throwaway(URL)

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
        "FROM information_schema.columns WHERE table_schema IN ('football','shared','ops','app')").fetchall()
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


CHOICE_INSERT = ("INSERT INTO app.contract_choices (season_id, team_key, scorer_id, choice_kind, choice, origin) "
                 "VALUES ('S', 'T', 'x', %s, %s, %s)")
PAST, FUTURE = "now() - interval '1 hour'", "now() + interval '1 day'"


def _fails(conn, role, sql, error):
    conn.execute("SAVEPOINT guard")
    conn.execute(f"SET LOCAL ROLE {role}")
    with pytest.raises(error):
        conn.execute(sql)
    conn.execute("ROLLBACK TO SAVEPOINT guard")


def _count_as(conn, role, sql="SELECT count(*) FROM app.contract_choices"):
    conn.execute(f"SET LOCAL ROLE {role}")
    (n,) = conn.execute(sql).fetchone()
    conn.execute("RESET ROLE")
    return n


def _deadline(conn, kind, when):
    conn.execute(f"INSERT INTO ops.choice_deadline (season_id, choice_kind, deadline_at) VALUES ('S', %s, {when})",
                 (kind,))


def test_the_choices_table_has_its_key_its_checks_and_its_foreign_keys(conn):
    (pk,) = conn.execute(
        "SELECT array_agg(a.attname::text ORDER BY a.attnum) FROM pg_index i JOIN pg_attribute a "
        "ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
        "WHERE i.indrelid = 'app.contract_choices'::regclass AND i.indisprimary").fetchone()
    assert pk == ["season_id", "team_key", "scorer_id", "choice_kind"]
    fks = dict(conn.execute(
        "SELECT conname, confrelid::regclass::text FROM pg_constraint "
        "WHERE conrelid = 'app.contract_choices'::regclass AND contype = 'f'").fetchall())
    assert fks == {"contract_choices_season_id_fkey": "football.dim_season",
                   "contract_choices_team_key_fkey": "football.dim_fantasy_teams"}
    (checks,) = conn.execute("SELECT count(*) FROM pg_constraint WHERE conrelid = 'app.contract_choices'::regclass "
                             "AND contype = 'c'").fetchone()
    assert checks == 3


@pytest.mark.parametrize("kind,choice", [("resign", "resign"), ("resign", "decline"),
                                         ("fa_keep", "keep"), ("fa_keep", "let_go")])
def test_a_choice_that_belongs_to_its_kind_is_accepted(conn, kind, choice):
    conn.execute(CHOICE_INSERT, (kind, choice, "loader"))


@pytest.mark.parametrize("kind,choice,origin", [
    ("resign", "keep", "loader"), ("resign", "let_go", "loader"), ("fa_keep", "resign", "loader"),
    ("fa_keep", "decline", "loader"), ("other", "keep", "loader"), ("fa_keep", "keep", "elsewhere")])
def test_a_choice_outside_its_kind_or_an_origin_outside_the_two_is_refused(conn, kind, choice, origin):
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(CHOICE_INSERT, (kind, choice, origin))
    conn.rollback()


def test_the_only_grant_on_the_choices_table_is_the_writers_select(conn):
    grants = conn.execute(
        "SELECT a.privilege_type, coalesce(r.rolname, 'PUBLIC') FROM pg_class c "
        "CROSS JOIN LATERAL aclexplode(c.relacl) a LEFT JOIN pg_roles r ON r.oid = a.grantee "
        "WHERE c.oid = 'app.contract_choices'::regclass AND a.grantee <> c.relowner").fetchall()
    assert grants == [("SELECT", "etl_writer")]


def test_the_writer_has_usage_on_app_and_the_reader_has_none(conn):
    assert conn.execute("SELECT has_schema_privilege('etl_writer', 'app', 'USAGE')").fetchone()[0]
    assert not conn.execute("SELECT has_schema_privilege('etl_reader', 'app', 'USAGE')").fetchone()[0]
    assert not conn.execute("SELECT has_schema_privilege('public', 'app', 'USAGE')").fetchone()[0]


def test_the_choices_table_has_one_policy_and_it_is_the_writers_select(conn):
    rows = conn.execute("SELECT policyname, cmd, roles::text[] FROM pg_policies "
                        "WHERE schemaname = 'app' AND tablename = 'contract_choices'").fetchall()
    assert rows == [("etl_writer_select_after_deadline", "SELECT", ["etl_writer"])]


def test_the_reader_is_refused_on_app(conn):
    _fails(conn, "etl_reader", "SELECT * FROM app.contract_choices", psycopg.errors.InsufficientPrivilege)


def test_the_writer_reads_no_row_while_the_deadline_is_missing_or_ahead(conn):
    conn.execute(CHOICE_INSERT, ("fa_keep", "keep", "loader"))
    assert _count_as(conn, "etl_writer") == 0
    _deadline(conn, "fa_keep", FUTURE)
    assert _count_as(conn, "etl_writer") == 0


def test_the_writer_reads_the_row_once_its_deadline_has_passed(conn):
    conn.execute(CHOICE_INSERT, ("fa_keep", "keep", "loader"))
    _deadline(conn, "fa_keep", PAST)
    assert _count_as(conn, "etl_writer") == 1


def test_a_passed_deadline_of_another_kind_releases_nothing(conn):
    conn.execute(CHOICE_INSERT, ("fa_keep", "keep", "loader"))
    _deadline(conn, "resign", PAST)
    assert _count_as(conn, "etl_writer") == 0


def test_the_writer_is_refused_an_insert_an_update_and_a_delete_on_the_choices_table(conn):
    conn.execute(CHOICE_INSERT, ("fa_keep", "keep", "loader"))
    _deadline(conn, "fa_keep", PAST)
    for sql in ("INSERT INTO app.contract_choices (season_id, team_key, scorer_id, choice_kind, choice, origin) "
                "VALUES ('S', 'T', 'y', 'fa_keep', 'keep', 'loader')",
                "UPDATE app.contract_choices SET choice = 'let_go'",
                "DELETE FROM app.contract_choices"):
        _fails(conn, "etl_writer", sql, psycopg.errors.InsufficientPrivilege)


def test_changed_at_is_set_on_insert_and_moves_on_an_update_that_tries_to_set_it(conn):
    conn.execute(CHOICE_INSERT, ("fa_keep", "keep", "loader"))
    first, ok = conn.execute("SELECT changed_at, changed_at BETWEEN now() AND clock_timestamp() "
                             "FROM app.contract_choices").fetchone()
    assert ok
    conn.execute("SELECT pg_sleep(0.05)")
    conn.execute("UPDATE app.contract_choices SET choice = 'let_go', changed_at = '2000-01-01'")
    (second,) = conn.execute("SELECT changed_at FROM app.contract_choices").fetchone()
    assert second > first


def test_a_passed_deadline_cannot_be_changed_or_deleted_by_any_role(conn):
    _deadline(conn, "fa_keep", PAST)
    for role in ("etl_writer", "NONE"):
        for sql in ("UPDATE ops.choice_deadline SET deadline_at = now() + interval '1 year'",
                    "DELETE FROM ops.choice_deadline"):
            _fails(conn, role, sql, psycopg.errors.RaiseException)


def test_a_deadline_still_ahead_can_be_moved_and_deleted(conn):
    _deadline(conn, "fa_keep", FUTURE)
    conn.execute("SET LOCAL ROLE etl_writer")
    conn.execute("UPDATE ops.choice_deadline SET deadline_at = now() + interval '2 days'")
    conn.execute("UPDATE ops.choice_deadline SET deadline_at = now() - interval '1 hour'")
    conn.execute("RESET ROLE")
    _fails(conn, "etl_writer", "DELETE FROM ops.choice_deadline", psycopg.errors.RaiseException)


def test_a_deadline_row_can_be_inserted_after_its_instant_has_passed(conn):
    _deadline(conn, "fa_keep", PAST)
    assert _count_as(conn, "etl_reader", "SELECT count(*) FROM ops.choice_deadline") == 1


def test_the_two_trigger_functions_are_in_ops_and_closed_to_everyone(conn):
    rows = conn.execute(
        "SELECT p.proname, p.prosecdef, p.proconfig, "
        "(SELECT count(*) FROM aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a "
        " WHERE a.grantee = 0), "
        "(SELECT count(*) FROM aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a "
        " WHERE a.grantee <> p.proowner) "
        "FROM pg_proc p WHERE p.pronamespace = 'ops'::regnamespace ORDER BY p.proname").fetchall()
    assert [r[0] for r in rows] == ["refuse_passed_deadline_change", "set_changed_at"]
    for _, definer, config, to_public, to_others in rows:
        assert not definer and "search_path=" in "".join(config or []) and to_public == 0 and to_others == 0
    assert conn.execute("SELECT count(*) FROM pg_proc WHERE pronamespace = 'app'::regnamespace").fetchone()[0] == 0
