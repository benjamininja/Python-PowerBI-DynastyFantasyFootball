import csv
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


AUTH_STUB = REPO / "tests" / "sql" / "auth_stub.sql"


@pytest.fixture(scope="module", autouse=True)
def auth_stub():
    """The stand-in for Supabase's auth setup, made only where absent. CI runs the
    same file before the migrations apply (they name auth.uid() and auth.identities);
    this makes a local database that missed it usable, and never touches a real one."""
    with psycopg.connect(URL, autocommit=True) as c:
        c.execute(AUTH_STUB.read_text(encoding="utf-8"))


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
        "FROM information_schema.columns WHERE table_schema IN ('football','shared','ops','app') "
        "AND (table_schema, table_name) IN (SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_type = 'BASE TABLE')").fetchall()
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


LATER_FINAL = "now() + interval '30 days'"
FINAL_ROW = ("now() - interval '2 hours'", "now() - interval '1 hour'")


def _deadline(conn, kind, when, final=LATER_FINAL):
    conn.execute("INSERT INTO ops.choice_deadline (season_id, choice_kind, deadline_at, final_at) "
                 f"VALUES ('S', %s, {when}, {final})", (kind,))


def _final(conn, kind="fa_keep"):
    _deadline(conn, kind, *FINAL_ROW)


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


def test_the_only_etl_grant_on_the_choices_table_is_the_writers_select(conn):
    grants = conn.execute(
        "SELECT a.privilege_type, coalesce(r.rolname, 'PUBLIC') FROM pg_class c "
        "CROSS JOIN LATERAL aclexplode(c.relacl) a LEFT JOIN pg_roles r ON r.oid = a.grantee "
        "WHERE c.oid = 'app.contract_choices'::regclass AND a.grantee <> c.relowner "
        "AND coalesce(r.rolname, 'PUBLIC') <> 'authenticated'").fetchall()
    assert grants == [("SELECT", "etl_writer")]


def test_the_writer_has_usage_on_app_and_the_reader_has_none(conn):
    assert conn.execute("SELECT has_schema_privilege('etl_writer', 'app', 'USAGE')").fetchone()[0]
    assert not conn.execute("SELECT has_schema_privilege('etl_reader', 'app', 'USAGE')").fetchone()[0]
    assert not conn.execute("SELECT has_schema_privilege('public', 'app', 'USAGE')").fetchone()[0]


def test_the_choices_table_has_one_etl_policy_and_it_is_the_writers_select(conn):
    rows = conn.execute("SELECT policyname, cmd, roles::text[] FROM pg_policies "
                        "WHERE schemaname = 'app' AND tablename = 'contract_choices' "
                        "AND NOT roles::text[] <@ ARRAY['authenticated']").fetchall()
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


DEADLINE_WRITES = ("INSERT INTO ops.choice_deadline (season_id, choice_kind, deadline_at, final_at) "
                   "VALUES ('S', 'resign', now() - interval '1 hour', now() + interval '30 days')",
                   "UPDATE ops.choice_deadline SET deadline_at = now() - interval '1 hour'",
                   "DELETE FROM ops.choice_deadline")


def test_the_deadline_table_grants_both_etl_roles_select_and_nothing_else(conn):
    grants = conn.execute(
        "SELECT a.privilege_type, coalesce(r.rolname, 'PUBLIC') FROM pg_class c "
        "CROSS JOIN LATERAL aclexplode(c.relacl) a LEFT JOIN pg_roles r ON r.oid = a.grantee "
        "WHERE c.oid = 'ops.choice_deadline'::regclass AND a.grantee <> c.relowner "
        "ORDER BY 2").fetchall()
    assert grants == [("SELECT", "etl_reader"), ("SELECT", "etl_writer")]
    policies = conn.execute("SELECT policyname, cmd, roles::text[] FROM pg_policies "
                            "WHERE schemaname = 'ops' AND tablename = 'choice_deadline' "
                            "ORDER BY policyname").fetchall()
    assert policies == [("etl_reader_select", "SELECT", ["etl_reader"]),
                        ("etl_writer_select", "SELECT", ["etl_writer"])]


def test_both_etl_roles_read_the_deadline_table(conn):
    _deadline(conn, "fa_keep", FUTURE)
    for role in ("etl_writer", "etl_reader"):
        assert _count_as(conn, role, "SELECT count(*) FROM ops.choice_deadline") == 1


def test_the_writer_is_refused_every_write_on_a_deadline_row_ahead_and_passed(conn):
    _deadline(conn, "fa_keep", FUTURE)
    _deadline(conn, "resign", PAST)
    for sql in DEADLINE_WRITES:
        _fails(conn, "etl_writer", sql, psycopg.errors.InsufficientPrivilege)


def test_the_reader_is_refused_every_write_on_the_deadline_table(conn):
    _deadline(conn, "fa_keep", FUTURE)
    for sql in DEADLINE_WRITES:
        _fails(conn, "etl_reader", sql, psycopg.errors.InsufficientPrivilege)


def test_the_writer_cannot_open_a_choice_by_writing_a_deadline(conn):
    conn.execute(CHOICE_INSERT, ("fa_keep", "keep", "loader"))
    _deadline(conn, "fa_keep", FUTURE)
    _fails(conn, "etl_writer", DEADLINE_WRITES[1], psycopg.errors.InsufficientPrivilege)
    assert _count_as(conn, "etl_writer") == 0


def test_the_owner_can_move_and_delete_a_deadline_still_ahead(conn):
    _deadline(conn, "fa_keep", FUTURE)
    conn.execute("UPDATE ops.choice_deadline SET deadline_at = now() + interval '2 days'")
    conn.execute("UPDATE ops.choice_deadline SET deadline_at = now() - interval '1 hour'")
    _fails(conn, "NONE", "DELETE FROM ops.choice_deadline", psycopg.errors.RaiseException)
    _deadline(conn, "resign", FUTURE)
    conn.execute("DELETE FROM ops.choice_deadline WHERE choice_kind = 'resign'")


def test_a_passed_deadline_cannot_be_changed_or_deleted_even_by_the_owner(conn):
    _deadline(conn, "fa_keep", PAST)
    for sql in ("UPDATE ops.choice_deadline SET deadline_at = now() + interval '1 year'",
                "DELETE FROM ops.choice_deadline"):
        _fails(conn, "NONE", sql, psycopg.errors.RaiseException)


def test_a_deadline_row_can_be_inserted_after_its_instant_has_passed(conn):
    _deadline(conn, "fa_keep", PAST)
    assert _count_as(conn, "etl_reader", "SELECT count(*) FROM ops.choice_deadline") == 1


def test_the_loaders_file_leaves_an_owners_row_alone_and_updates_a_loader_row(conn):
    import load_contract_choices as loader
    conn.execute(CHOICE_INSERT, ("fa_keep", "keep", "app"))
    conn.execute("INSERT INTO app.contract_choices (season_id, team_key, scorer_id, choice_kind, choice, origin) "
                 "VALUES ('S', 'T', 'y', 'fa_keep', 'keep', 'loader')")
    rows = [{"team_key": "T", "scorer_id": s, "choice": "let_go", "locked_value": 5.0} for s in ("x", "y", "z")]
    body = loader.sql_file("S", rows).replace("BEGIN;\n", "").replace("COMMIT;\n", "")
    written, left_alone = conn.execute(body).fetchone()
    assert (written, left_alone) == (2, 1)
    got = dict(conn.execute("SELECT scorer_id, choice || '/' || origin || '/' || coalesce(locked_value::text, '-') "
                            "FROM app.contract_choices").fetchall())
    assert got == {"x": "keep/app/-", "y": "let_go/loader/5", "z": "let_go/loader/5"}


def test_the_trigger_functions_are_in_ops_closed_to_everyone_and_only_the_history_writer_is_a_definer(conn):
    rows = conn.execute(
        "SELECT p.proname, p.prosecdef, p.proconfig, "
        "(SELECT count(*) FROM aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a "
        " WHERE a.grantee = 0), "
        "(SELECT count(*) FROM aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a "
        " WHERE a.grantee <> p.proowner) "
        "FROM pg_proc p WHERE p.pronamespace = 'ops'::regnamespace ORDER BY p.proname").fetchall()
    assert [r[0] for r in rows] == ["record_choice_history", "refuse_passed_deadline_change", "set_changed_at"]
    for name, definer, config, to_public, to_others in rows:
        assert definer is (name == "record_choice_history"), name
        assert "search_path=" in "".join(config or []) and to_public == 0 and to_others == 0, name
    for role in ("authenticated", "anon", "etl_writer", "etl_reader"):
        assert not conn.execute("SELECT has_function_privilege(%s, 'ops.record_choice_history()', 'EXECUTE')",
                                (role,)).fetchone()[0], role
    assert conn.execute("SELECT count(*) FROM pg_proc WHERE pronamespace = 'app'::regnamespace").fetchone()[0] == 0


# --- the owner policies (ADR-0025 decisions 2, 3 and 6; #548 brief 3) -------------
# Made-up users, ids and teams. U1 and U2 co-own team T, U3 owns T2, U4 signed in
# with a Discord identity the crosswalk does not list, U5 has no Discord identity
# (a GitHub one whose id equals U1's Discord id), U6 owns both T and T2.
U1, U2, U3, U4, U5, U6 = (f"00000000-0000-0000-0000-00000000000{n}" for n in range(1, 7))
DISCORD = {U1: "11111111111111111", U2: "22222222222222222", U3: "33333333333333333",
           U4: "44444444444444444", U6: "66666666666666666"}
CROSSWALK = [("T", U1), ("T", U2), ("T2", U3), ("T", U6), ("T2", U6)]
OWN_INSERT = ("INSERT INTO app.contract_choices (season_id, team_key, scorer_id, choice_kind, choice, origin, "
              "changed_by) VALUES ('S', %s, %s, %s, 'keep', %s, %s)")
SHARE_INSERT = "INSERT INTO app.team_choice_sharing (season_id, team_key, shared, changed_by) VALUES ('S', %s, %s, %s)"


def _world(conn):
    for uid, discord_id in DISCORD.items():
        conn.execute("INSERT INTO auth.identities (user_id, provider, provider_id) VALUES (%s, 'discord', %s)",
                     (uid, discord_id))
    conn.execute("INSERT INTO auth.identities (user_id, provider, provider_id) VALUES (%s, 'github', %s)",
                 (U5, DISCORD[U1]))
    for team, uid in CROSSWALK:
        conn.execute("INSERT INTO shared.owner_crosswalk (team_key, discord_user_id) VALUES (%s, %s)",
                     (team, DISCORD[uid]))


def _as(conn, uid, role="authenticated"):
    conn.execute("SELECT set_config('request.jwt.claim.sub', %s, true)", (uid,))
    conn.execute(f"SET LOCAL ROLE {role}")


def _do(conn, uid, sql, params=()):
    """Run `sql` as the signed-in user `uid` and give back the row count."""
    _as(conn, uid)
    try:
        return conn.execute(sql, params).rowcount
    finally:
        conn.execute("RESET ROLE")


def _read(conn, uid, sql="SELECT count(*) FROM app.contract_choices", params=()):
    _as(conn, uid)
    try:
        return conn.execute(sql, params).fetchone()[0]
    finally:
        conn.execute("RESET ROLE")


def _denied(conn, uid, sql, params=(), role="authenticated"):
    conn.execute("SAVEPOINT guard")
    _as(conn, uid, role)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(sql, params)
    conn.execute("ROLLBACK TO SAVEPOINT guard")


def _choice(conn):
    return conn.execute("SELECT choice, origin, changed_by::text FROM app.contract_choices "
                        "WHERE scorer_id = 'x'").fetchone()


def test_an_owner_writes_their_own_team_before_the_deadline(conn):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    assert _do(conn, U1, OWN_INSERT, ("T", "x", "fa_keep", "app", U1)) == 1
    assert _choice(conn) == ("keep", "app", U1)
    update = "UPDATE app.contract_choices SET choice = 'let_go', origin = 'app', changed_by = %s WHERE scorer_id = 'x'"
    assert _do(conn, U1, update, (U1,)) == 1
    assert _choice(conn) == ("let_go", "app", U1)


def test_a_co_owner_writes_the_same_team_and_changed_by_is_the_one_who_wrote(conn):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    assert _do(conn, U1, OWN_INSERT, ("T", "x", "fa_keep", "app", U1)) == 1
    update = "UPDATE app.contract_choices SET choice = 'let_go', origin = 'app', changed_by = %s WHERE scorer_id = 'x'"
    assert _do(conn, U2, update, (U2,)) == 1
    assert _choice(conn) == ("let_go", "app", U2)


def test_an_owner_of_two_teams_writes_both(conn):
    _world(conn)
    _deadline(conn, "resign", FUTURE)
    for team in ("T", "T2"):
        assert _do(conn, U6, OWN_INSERT.replace("'keep'", "'resign'"), (team, "x", "resign", "app", U6)) == 1


def test_a_discord_identity_with_its_id_in_the_crosswalk_is_the_only_way_to_a_team(conn):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    assert _read(conn, U1, "SELECT count(*) FROM shared.caller_team_keys()") == 1
    assert _read(conn, U6, "SELECT count(*) FROM shared.caller_team_keys()") == 2
    assert _read(conn, U4, "SELECT count(*) FROM shared.caller_team_keys()") == 0
    assert _read(conn, U5, "SELECT count(*) FROM shared.caller_team_keys()") == 0


def test_another_teams_owner_a_user_with_no_crosswalk_row_and_a_signed_out_caller_are_refused(conn):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    for uid in (U3, U4, U5, "00000000-0000-0000-0000-0000000000ff"):
        _denied(conn, uid, OWN_INSERT, ("T", "x", "fa_keep", "app", uid))
    conn.execute("SELECT set_config('request.jwt.claim.sub', '', true)")
    _denied(conn, "", OWN_INSERT, ("T", "x", "fa_keep", "app", None))


def test_another_teams_owner_cannot_change_a_row_that_stays_hidden_from_them(conn):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    conn.execute(OWN_INSERT, ("T", "x", "fa_keep", "app", U1))
    update = "UPDATE app.contract_choices SET choice = 'let_go', origin = 'app', changed_by = %s WHERE scorer_id = 'x'"
    assert _do(conn, U3, update, (U3,)) == 0
    assert _do(conn, U4, update, (U4,)) == 0
    assert _choice(conn) == ("keep", "app", U1)


@pytest.mark.parametrize("origin,changed_by", [("loader", U1), ("app", U2), ("app", None), ("loader", None)])
def test_a_forged_origin_or_changed_by_is_refused_on_insert(conn, origin, changed_by):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    _denied(conn, U1, OWN_INSERT, ("T", "x", "fa_keep", origin, changed_by))


@pytest.mark.parametrize("set_clause", ["origin = 'loader', changed_by = '" + U1 + "'",
                                        "origin = 'app', changed_by = '" + U2 + "'",
                                        "origin = 'app', changed_by = NULL"])
def test_a_forged_origin_or_changed_by_is_refused_on_update(conn, set_clause):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    conn.execute(OWN_INSERT, ("T", "x", "fa_keep", "app", U1))
    _denied(conn, U1, f"UPDATE app.contract_choices SET choice = 'let_go', {set_clause} WHERE scorer_id = 'x'")


def test_an_update_that_moves_a_row_to_another_team_is_refused(conn):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    conn.execute(OWN_INSERT, ("T", "x", "fa_keep", "app", U1))
    _denied(conn, U1, "UPDATE app.contract_choices SET team_key = 'T2' WHERE scorer_id = 'x'")


def test_locked_value_and_changed_at_cannot_be_written_by_an_owner(conn):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    _denied(conn, U1, "INSERT INTO app.contract_choices (season_id, team_key, scorer_id, choice_kind, choice, "
                      "origin, changed_by, locked_value) VALUES ('S', 'T', 'x', 'fa_keep', 'keep', 'app', %s, 9)",
            (U1,))
    _denied(conn, U1, "INSERT INTO app.contract_choices (season_id, team_key, scorer_id, choice_kind, choice, "
                      "origin, changed_by, changed_at) VALUES ('S', 'T', 'x', 'fa_keep', 'keep', 'app', %s, "
                      "'2000-01-01')", (U1,))
    conn.execute(OWN_INSERT, ("T", "x", "fa_keep", "app", U1))
    _denied(conn, U1, "UPDATE app.contract_choices SET locked_value = 1 WHERE scorer_id = 'x'")
    _denied(conn, U1, "UPDATE app.contract_choices SET changed_at = '2000-01-01' WHERE scorer_id = 'x'")


def test_changed_at_moves_when_an_owner_updates_a_row(conn):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    conn.execute(OWN_INSERT, ("T", "x", "fa_keep", "app", U1))
    (first,) = conn.execute("SELECT changed_at FROM app.contract_choices").fetchone()
    conn.execute("SELECT pg_sleep(0.05)")
    update = "UPDATE app.contract_choices SET choice = 'let_go', origin = 'app', changed_by = %s WHERE scorer_id = 'x'"
    assert _do(conn, U1, update, (U1,)) == 1
    (second,) = conn.execute("SELECT changed_at FROM app.contract_choices").fetchone()
    assert second > first


def test_no_owner_deletes_a_row(conn):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    conn.execute(OWN_INSERT, ("T", "x", "fa_keep", "app", U1))
    _denied(conn, U1, "DELETE FROM app.contract_choices")
    _denied(conn, U1, "DELETE FROM app.team_choice_sharing")


@pytest.mark.parametrize("state", ["passed", "final", "none"])
def test_every_owner_write_is_refused_once_the_deadline_has_passed_and_with_no_deadline_row(conn, state):
    _world(conn)
    if state == "passed":
        _deadline(conn, "fa_keep", PAST)
    elif state == "final":
        _final(conn)
    conn.execute(OWN_INSERT, ("T", "x", "fa_keep", "app", U1))
    _denied(conn, U1, OWN_INSERT, ("T", "y", "fa_keep", "app", U1))
    update = "UPDATE app.contract_choices SET choice = 'let_go', origin = 'app', changed_by = %s WHERE scorer_id = 'x'"
    assert _do(conn, U1, update, (U1,)) == 0
    assert _choice(conn) == ("keep", "app", U1)


def test_an_open_deadline_of_the_other_kind_does_not_open_a_write(conn):
    _world(conn)
    _deadline(conn, "resign", FUTURE)
    _denied(conn, U1, OWN_INSERT, ("T", "x", "fa_keep", "app", U1))


def _choices_seen_by(conn, uid):
    return _read(conn, uid, "SELECT count(*) FROM app.contract_choices WHERE scorer_id = 'x'")


@pytest.mark.parametrize("state,others,owner", [("open", 0, 1), ("passed", 1, 1), ("final", 1, 1), ("none", 0, 1)])
def test_a_row_is_private_while_open_public_once_passed_or_final_and_private_with_no_deadline_row(
        conn, state, others, owner):
    _world(conn)
    if state == "final":
        _final(conn)
    elif state != "none":
        _deadline(conn, "fa_keep", FUTURE if state == "open" else PAST)
    conn.execute(OWN_INSERT, ("T", "x", "fa_keep", "loader", None))
    for uid in (U3, U4, U5):
        assert _choices_seen_by(conn, uid) == others, (state, uid)
    for uid in (U1, U2, U6):
        assert _choices_seen_by(conn, uid) == owner, (state, uid)


def test_a_passed_deadline_of_another_kind_releases_no_row(conn):
    _world(conn)
    _deadline(conn, "resign", PAST)
    _deadline(conn, "fa_keep", FUTURE)
    conn.execute(OWN_INSERT, ("T", "x", "fa_keep", "loader", None))
    assert _choices_seen_by(conn, U3) == 0


def test_another_team_reads_a_row_while_the_teams_toggle_is_on_and_not_before_or_after(conn):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    conn.execute(OWN_INSERT, ("T", "x", "fa_keep", "loader", None))
    assert _choices_seen_by(conn, U3) == 0
    conn.execute("INSERT INTO app.team_choice_sharing (season_id, team_key, shared) VALUES ('S', 'T', false)")
    assert _choices_seen_by(conn, U3) == 0
    conn.execute("UPDATE app.team_choice_sharing SET shared = true")
    assert _choices_seen_by(conn, U3) == 1 and _choices_seen_by(conn, U4) == 1
    conn.execute("UPDATE app.team_choice_sharing SET shared = false")
    assert _choices_seen_by(conn, U3) == 0


def test_a_toggle_for_another_season_or_team_shows_nothing(conn):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    conn.execute(OWN_INSERT, ("T", "x", "fa_keep", "loader", None))
    conn.execute("INSERT INTO app.team_choice_sharing (season_id, team_key, shared) VALUES ('S', 'T2', true)")
    conn.execute("INSERT INTO app.team_choice_sharing (season_id, team_key, shared) VALUES ('OTHER', 'T', true)")
    assert _choices_seen_by(conn, U3) == 0 and _choices_seen_by(conn, U4) == 0


def test_every_signed_in_user_reads_every_toggle(conn):
    _world(conn)
    conn.execute("INSERT INTO app.team_choice_sharing (season_id, team_key, shared) VALUES ('S', 'T', false)")
    conn.execute("INSERT INTO app.team_choice_sharing (season_id, team_key, shared) VALUES ('S', 'T2', true)")
    for uid in (U1, U3, U4, U5):
        assert _read(conn, uid, "SELECT count(*) FROM app.team_choice_sharing") == 2


def test_an_owner_writes_their_toggle_while_one_of_the_two_windows_is_open(conn):
    _world(conn)
    _deadline(conn, "resign", PAST)
    _deadline(conn, "fa_keep", FUTURE)
    assert _do(conn, U1, SHARE_INSERT, ("T", True, U1)) == 1
    update = "UPDATE app.team_choice_sharing SET shared = false, changed_by = %s WHERE team_key = 'T'"
    assert _do(conn, U2, update, (U2,)) == 1
    assert conn.execute("SELECT shared, changed_by::text FROM app.team_choice_sharing").fetchone() == (False, U2)


@pytest.mark.parametrize("deadlines", [(), (("resign", PAST),), (("resign", PAST), ("fa_keep", PAST))])
def test_a_toggle_write_is_refused_with_no_window_open(conn, deadlines):
    _world(conn)
    for kind, when in deadlines:
        _deadline(conn, kind, when)
    conn.execute("INSERT INTO app.team_choice_sharing (season_id, team_key, shared) VALUES ('S', 'T2', false)")
    _denied(conn, U6, SHARE_INSERT, ("T", True, U6))
    update = "UPDATE app.team_choice_sharing SET shared = true, changed_by = %s WHERE team_key = 'T2'"
    assert _do(conn, U6, update, (U6,)) == 0
    assert conn.execute("SELECT shared FROM app.team_choice_sharing").fetchone() == (False,)


def test_a_toggle_write_for_another_team_or_with_a_forged_changed_by_is_refused(conn):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    _denied(conn, U3, SHARE_INSERT, ("T", True, U3))
    _denied(conn, U4, SHARE_INSERT, ("T", True, U4))
    _denied(conn, U1, SHARE_INSERT, ("T", True, U2))
    _denied(conn, U1, SHARE_INSERT, ("T", True, None))
    conn.execute("INSERT INTO app.team_choice_sharing (season_id, team_key, shared) VALUES ('S', 'T', false)")
    update = "UPDATE app.team_choice_sharing SET shared = true, changed_by = %s WHERE team_key = 'T'"
    assert _do(conn, U3, update, (U3,)) == 0
    _denied(conn, U1, update, (U2,))


def test_changed_at_cannot_be_written_on_a_toggle_and_moves_on_update(conn):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    _denied(conn, U1, "INSERT INTO app.team_choice_sharing (season_id, team_key, shared, changed_by, changed_at) "
                      "VALUES ('S', 'T', true, %s, '2000-01-01')", (U1,))
    assert _do(conn, U1, SHARE_INSERT, ("T", True, U1)) == 1
    (first,) = conn.execute("SELECT changed_at FROM app.team_choice_sharing").fetchone()
    conn.execute("SELECT pg_sleep(0.05)")
    assert _do(conn, U1, "UPDATE app.team_choice_sharing SET shared = false, changed_by = %s", (U1,)) == 1
    (second,) = conn.execute("SELECT changed_at FROM app.team_choice_sharing").fetchone()
    assert second > first
    _denied(conn, U1, "UPDATE app.team_choice_sharing SET changed_at = '2000-01-01'")


def test_the_crosswalk_is_unreadable_and_unwritable_to_every_role_but_its_owner(conn):
    _world(conn)
    for role in ("authenticated", "anon", "etl_writer", "etl_reader"):
        _denied(conn, U1, "SELECT * FROM shared.owner_crosswalk", role=role)
        _denied(conn, U1, "INSERT INTO shared.owner_crosswalk (team_key, discord_user_id) "
                          "VALUES ('T9', '99999999999999999')", role=role)
    (rls,) = conn.execute("SELECT relrowsecurity FROM pg_class WHERE oid = 'shared.owner_crosswalk'::regclass").fetchone()
    assert rls
    assert not conn.execute("SELECT count(*) FROM pg_policies WHERE tablename = 'owner_crosswalk'").fetchone()[0]


@pytest.mark.parametrize("role", ["anon", "etl_writer", "etl_reader"])
@pytest.mark.parametrize("call", ["SELECT * FROM shared.caller_team_keys()",
                                  "SELECT shared.choice_window('S', 'fa_keep')",
                                  "SELECT shared.caller_is_commissioner_for('T')",
                                  "SELECT shared.caller_is_site_admin()",
                                  "SELECT * FROM shared.choice_windows()"])
def test_the_five_definer_functions_cannot_be_called_by_anon_or_an_etl_role(conn, role, call):
    _world(conn)
    _denied(conn, U1, call, role=role)


def test_signed_in_callers_get_only_their_own_teams_and_a_state_from_the_window_function(conn):
    _world(conn)
    window = "SELECT shared.choice_window('S', 'fa_keep')"
    assert _read(conn, U1, window) == "none"
    _deadline(conn, "fa_keep", FUTURE)
    assert _read(conn, U1, window) == "open"
    conn.execute("UPDATE ops.choice_deadline SET deadline_at = now() - interval '1 hour'")
    assert _read(conn, U4, window) == "passed"


def test_the_window_function_gives_each_of_its_four_states_from_one_row(conn):
    _world(conn)
    window = "SELECT shared.choice_window('S', 'fa_keep')"
    assert [_read(conn, U1, window)] == ["none"]
    for deadline, final, expected in (("now() + interval '1 day'", "now() + interval '2 days'", "open"),
                                      ("now() - interval '1 hour'", "now() + interval '2 days'", "passed"),
                                      ("now() - interval '2 hours'", "now() - interval '1 hour'", "final")):
        conn.execute("SAVEPOINT state_row")
        _deadline(conn, "fa_keep", deadline, final)
        assert _read(conn, U1, window) == expected
        conn.execute("ROLLBACK TO SAVEPOINT state_row")
    _deadline(conn, "resign", FUTURE)
    assert _read(conn, U1, window) == "none"


def test_a_final_instant_not_later_than_the_deadline_is_refused_and_the_column_is_required(conn):
    for deadline, final in (("now() + interval '1 day'", "now() + interval '1 day'"),
                            ("now() + interval '1 day'", "now() + interval '1 hour'")):
        conn.execute("SAVEPOINT bad_row")
        with pytest.raises(psycopg.errors.CheckViolation):
            _deadline(conn, "fa_keep", deadline, final)
        conn.execute("ROLLBACK TO SAVEPOINT bad_row")
    conn.execute("SAVEPOINT bad_row")
    with pytest.raises(psycopg.errors.NotNullViolation):
        conn.execute("INSERT INTO ops.choice_deadline (season_id, choice_kind, deadline_at) "
                     "VALUES ('S', 'fa_keep', now() + interval '1 day')")
    conn.execute("ROLLBACK TO SAVEPOINT bad_row")
    assert conn.execute("SELECT column_default FROM information_schema.columns WHERE table_schema = 'ops' "
                        "AND table_name = 'choice_deadline' AND column_name = 'final_at'").fetchone() == (None,)


def test_a_final_row_cannot_be_changed_or_deleted_even_by_the_owner(conn):
    _final(conn)
    for sql in ("UPDATE ops.choice_deadline SET final_at = now() + interval '1 year'",
                "DELETE FROM ops.choice_deadline"):
        _fails(conn, "NONE", sql, psycopg.errors.RaiseException)


def test_a_choice_row_stays_readable_to_every_signed_in_user_in_final(conn):
    _world(conn)
    _final(conn)
    conn.execute(OWN_INSERT, ("T", "x", "fa_keep", "loader", None))
    for uid in (U1, U2, U3, U4, U5, U6):
        assert _choices_seen_by(conn, uid) == 1, uid
    assert _count_as(conn, "etl_writer") == 1


def test_anon_reads_and_writes_nothing_anywhere(conn):
    _world(conn)
    _deadline(conn, "fa_keep", PAST)
    conn.execute(OWN_INSERT, ("T", "x", "fa_keep", "loader", None))
    for sql in ("SELECT * FROM app.contract_choices", "SELECT * FROM app.team_choice_sharing",
                "SELECT * FROM app.contract_choice_history", "SELECT * FROM football.dim_season", "SELECT * FROM ops.choice_deadline",
                "SELECT * FROM shared.owner_crosswalk", "SELECT * FROM shared.owner",
                OWN_INSERT % ("'T'", "'z'", "'fa_keep'", "'app'", "NULL"),
                "UPDATE app.contract_choices SET choice = 'let_go'", "DELETE FROM app.contract_choices"):
        _denied(conn, U1, sql, role="anon")
    held = conn.execute(
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname IN ('football', 'shared', 'ops', 'app') AND c.relkind IN ('r', 'p') "
        "AND has_table_privilege('anon', c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')").fetchone()[0]
    assert held == 0
    for schema in ("football", "shared", "ops", "app"):
        assert not conn.execute("SELECT has_schema_privilege('anon', %s, 'USAGE')", (schema,)).fetchone()[0]


def test_authenticated_holds_usage_on_app_and_shared_and_no_table_outside_app(conn):
    for schema, usage in (("app", True), ("shared", True), ("football", False), ("ops", False)):
        got = conn.execute("SELECT has_schema_privilege('authenticated', %s, 'USAGE')", (schema,)).fetchone()[0]
        assert got is usage, schema
    held = conn.execute(
        "SELECT n.nspname, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname IN ('football', 'shared', 'ops') AND c.relkind IN ('r', 'p') "
        "AND has_table_privilege('authenticated', c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')"
    ).fetchall()
    assert held == []
    for table in ("app.contract_choices", "app.team_choice_sharing"):
        for privilege in ("DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
            assert not conn.execute("SELECT has_table_privilege('authenticated', %s, %s)",
                                    (table, privilege)).fetchone()[0], (table, privilege)
    for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
        assert not conn.execute("SELECT has_table_privilege('authenticated', 'app.contract_choice_history', %s)",
                                (privilege,)).fetchone()[0], privilege
    assert conn.execute("SELECT has_table_privilege('authenticated', 'app.contract_choice_history', 'SELECT')"
                        ).fetchone()[0]
    for column in ("history_id", "choice", "origin", "changed_at", "action_id", "recorded_at"):
        for privilege in ("INSERT", "UPDATE"):
            assert not conn.execute("SELECT has_column_privilege('authenticated', 'app.contract_choice_history', "
                                    "%s, %s)", (column, privilege)).fetchone()[0], (column, privilege)


def test_authenticated_holds_the_columns_the_adr_names_and_never_locked_value_or_changed_at(conn):
    def can(table, column, privilege):
        return conn.execute("SELECT has_column_privilege('authenticated', %s, %s, %s)",
                            (table, column, privilege)).fetchone()[0]
    for column in ("season_id", "team_key", "scorer_id", "choice_kind", "choice", "origin", "changed_by"):
        assert can("app.contract_choices", column, "INSERT"), column
    for column in ("choice", "origin", "changed_by"):
        assert can("app.contract_choices", column, "UPDATE"), column
    for column in ("season_id", "team_key", "scorer_id", "choice_kind", "locked_value", "changed_at"):
        assert not can("app.contract_choices", column, "UPDATE"), column
    for column in ("locked_value", "changed_at"):
        assert not can("app.contract_choices", column, "INSERT"), column
    for column in ("season_id", "team_key", "shared", "changed_by"):
        assert can("app.team_choice_sharing", column, "INSERT"), column
    for column in ("shared", "changed_by"):
        assert can("app.team_choice_sharing", column, "UPDATE"), column
    for column in ("changed_at", "season_id", "team_key"):
        assert not can("app.team_choice_sharing", column, "UPDATE"), column
    assert not can("app.team_choice_sharing", "changed_at", "INSERT")


def test_the_etl_roles_keep_their_posture_on_app(conn):
    for table in ("app.contract_choices", "app.team_choice_sharing", "app.contract_choice_history"):
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            assert not conn.execute("SELECT has_table_privilege('etl_reader', %s, %s)",
                                    (table, privilege)).fetchone()[0], (table, privilege)
    for role in ("etl_writer", "etl_reader"):
        assert not conn.execute("SELECT has_table_privilege(%s, 'app.contract_choice_history', "
                                "'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')", (role,)).fetchone()[0], role
    assert not conn.execute("SELECT has_table_privilege('etl_writer', 'app.team_choice_sharing', "
                            "'SELECT,INSERT,UPDATE,DELETE')").fetchone()[0]
    assert conn.execute("SELECT has_table_privilege('etl_writer', 'app.contract_choices', 'SELECT')").fetchone()[0]
    assert not conn.execute("SELECT has_table_privilege('etl_writer', 'app.contract_choices', "
                            "'INSERT,UPDATE,DELETE')").fetchone()[0]
    for role in ("etl_writer", "etl_reader"):
        assert not conn.execute("SELECT has_table_privilege(%s, 'shared.owner_crosswalk', "
                                "'SELECT,INSERT,UPDATE,DELETE')", (role,)).fetchone()[0]


DEFINERS = ("caller_is_commissioner_for", "caller_is_site_admin", "caller_team_keys", "choice_window",
            "choice_windows")
LOAD_FUNCTIONS = ("load_app_roles", "load_owner_crosswalk")
SHARED_FUNCTIONS_TODAY = 1 + len(LOAD_FUNCTIONS)


def test_the_functions_in_shared_are_the_pii_hash_the_two_loaders_and_the_five_definers_and_no_others(conn):
    names = [r[0] for r in conn.execute("SELECT proname FROM pg_proc WHERE pronamespace = 'shared'::regnamespace "
                                        "ORDER BY proname").fetchall()]
    assert names == ["caller_is_commissioner_for", "caller_is_site_admin", "caller_team_keys", "choice_window",
                     "choice_windows", "load_app_roles", "load_owner_crosswalk", "pii_token_hashes"]
    assert len(names) == SHARED_FUNCTIONS_TODAY + len(DEFINERS) == 8


def test_no_function_in_shared_but_the_five_definers_is_executable_by_authenticated_anon_or_public(conn):
    rows = conn.execute("SELECT p.proname, p.oid FROM pg_proc p WHERE p.pronamespace = 'shared'::regnamespace").fetchall()
    others = [(name, oid) for name, oid in rows if name not in DEFINERS]
    assert others
    for name, oid in others:
        for role in ("authenticated", "anon", "public"):
            assert not conn.execute("SELECT has_function_privilege(%s, %s, 'EXECUTE')", (role, oid)).fetchone()[0], \
                (name, role)


def test_the_five_definers_are_executable_by_authenticated_alone_and_pin_the_search_path(conn):
    rows = conn.execute("SELECT p.proname, p.prosecdef, p.proconfig, p.oid FROM pg_proc p "
                        "WHERE p.pronamespace = 'shared'::regnamespace AND p.proname = ANY(%s)",
                        (list(DEFINERS),)).fetchall()
    assert sorted(r[0] for r in rows) == sorted(DEFINERS)
    for name, definer, config, oid in rows:
        assert definer and any(c.replace(" ", "") in ('search_path=""', "search_path=") for c in (config or [])), name
        assert conn.execute("SELECT has_function_privilege('authenticated', %s, 'EXECUTE')", (oid,)).fetchone()[0]
        for role in ("anon", "public", "etl_writer", "etl_reader"):
            assert not conn.execute("SELECT has_function_privilege(%s, %s, 'EXECUTE')", (role, oid)).fetchone()[0], \
                (name, role)


def test_the_pii_hash_function_stays_with_the_writer_alone(conn):
    (oid,) = conn.execute("SELECT 'shared.pii_token_hashes()'::regprocedure::oid").fetchone()
    for role, expected in (("etl_writer", True), ("etl_reader", False), ("authenticated", False),
                           ("anon", False), ("public", False)):
        got = conn.execute("SELECT has_function_privilege(%s, %s, 'EXECUTE')", (role, oid)).fetchone()[0]
        assert got is expected, role


def test_the_pii_hash_list_holds_the_sha256_of_each_crosswalk_id_and_never_the_id(conn):
    import hashlib
    _world(conn)
    conn.execute("INSERT INTO shared.owner (owner_id, team_key, human_name, fantrax_username) "
                 "VALUES ('o1', 'T', 'Test Person', 'testuser')")
    with conn.cursor() as cur:
        cur.execute("SET LOCAL ROLE etl_writer")
        cur.execute("SELECT * FROM shared.pii_token_hashes()")
        got = {r[0] for r in cur.fetchall()}
    conn.rollback()

    def digest(text):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    listed = {DISCORD[uid] for _, uid in CROSSWALK}
    assert listed and {digest(i) for i in listed} <= got
    assert digest(DISCORD[U4]) not in got
    assert {digest("test"), digest("person"), digest("testuser")} <= got
    assert not set(DISCORD.values()) & got


def test_the_owner_policies_are_the_eleven_named_and_all_for_authenticated(conn):
    rows = conn.execute("SELECT tablename, policyname, cmd, roles::text[] FROM pg_policies WHERE schemaname = 'app' "
                        "AND roles::text[] <@ ARRAY['authenticated'] ORDER BY 1, 2").fetchall()
    assert [(t, p, c) for t, p, c, _ in rows] == [
        ("contract_choice_history", "owner_select_own_team", "SELECT"),
        ("contract_choice_history", "signed_in_select_after_deadline", "SELECT"),
        ("contract_choice_history", "signed_in_select_shared_team", "SELECT"),
        ("contract_choices", "owner_insert_own_team_while_open", "INSERT"),
        ("contract_choices", "owner_select_own_team", "SELECT"),
        ("contract_choices", "owner_update_own_team_while_open", "UPDATE"),
        ("contract_choices", "signed_in_select_after_deadline", "SELECT"),
        ("contract_choices", "signed_in_select_shared_team", "SELECT"),
        ("team_choice_sharing", "owner_insert_own_team_while_open", "INSERT"),
        ("team_choice_sharing", "owner_update_own_team_while_open", "UPDATE"),
        ("team_choice_sharing", "signed_in_select_all", "SELECT")]
    assert all(r[3] == ["authenticated"] for r in rows)


# --- the page's read path: two views in app over shared functions (ADR-0026 decision 10 point 1; #670) ---
VIEWS = STATE["views"]
VIEW_WRITES = ("INSERT INTO app.choice_windows (season_id, choice_kind, state) VALUES ('S', 'resign', 'open')",
               "UPDATE app.choice_windows SET state = 'final'", "DELETE FROM app.choice_windows",
               "INSERT INTO app.my_teams (team_key) VALUES ('T9')", "UPDATE app.my_teams SET team_key = 'T9'",
               "DELETE FROM app.my_teams")


def _rows_as(conn, uid, sql):
    _as(conn, uid)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.execute("RESET ROLE")


def test_app_holds_the_two_views_every_one_with_security_invoker_on_and_no_function(conn):
    rows = conn.execute("SELECT c.relname, c.reloptions FROM pg_class c WHERE c.relnamespace = 'app'::regnamespace "
                        "AND c.relkind IN ('v', 'm') ORDER BY 1").fetchall()
    assert [r[0] for r in rows] == ["choice_windows", "my_teams"]
    assert sorted(f"app.{r[0]}" for r in rows) == sorted(VIEWS)
    for name, options in rows:
        assert "security_invoker=true" in (options or []), name
    assert conn.execute("SELECT count(*) FROM pg_proc WHERE pronamespace = 'app'::regnamespace").fetchone()[0] == 0


def test_each_view_returns_the_columns_the_registry_names_and_none_a_discord_id_fills(conn):
    for spec in VIEWS.values():
        cols = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = %s "
                            "AND table_name = %s ORDER BY ordinal_position", (spec["schema"], spec["name"])).fetchall()
        assert [c[0] for c in cols] == spec["columns"], spec["name"]
        assert not [c for c in spec["columns"] if "discord" in c], spec["name"]


def test_authenticated_reads_both_views_and_anon_and_the_etl_roles_are_refused(conn):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    assert _read(conn, U1, "SELECT count(*) FROM app.choice_windows") == 1
    assert _read(conn, U1, "SELECT count(*) FROM app.my_teams") == 1
    for role in ("anon", "etl_writer", "etl_reader"):
        for name in VIEWS:
            _denied(conn, U1, f"SELECT * FROM {name}", role=role)
    for name in VIEWS:
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
            for role in ("anon", "etl_writer", "etl_reader", "public", "authenticated"):
                held = conn.execute("SELECT has_table_privilege(%s, %s, %s)", (role, name, privilege)).fetchone()[0]
                assert held is (role == "authenticated" and privilege == "SELECT"), (name, role, privilege)


def test_the_windows_view_gives_each_state_from_its_row_and_no_row_for_none(conn):
    _world(conn)
    sql = "SELECT season_id, choice_kind, state, deadline_at, final_at FROM app.choice_windows ORDER BY choice_kind"
    assert _rows_as(conn, U4, sql) == []
    for deadline, final, expected in (("now() + interval '1 day'", "now() + interval '2 days'", "open"),
                                      ("now() - interval '1 hour'", "now() + interval '2 days'", "passed"),
                                      (*FINAL_ROW, "final")):
        conn.execute("SAVEPOINT state_row")
        _deadline(conn, "fa_keep", deadline, final)
        (row,) = conn.execute("SELECT season_id, choice_kind, deadline_at, final_at FROM ops.choice_deadline").fetchall()
        assert _rows_as(conn, U4, sql) == [(row[0], row[1], expected, row[2], row[3])]
        conn.execute("ROLLBACK TO SAVEPOINT state_row")


def test_the_windows_view_gives_one_row_per_window_each_with_choice_windows_answer(conn):
    _world(conn)
    _deadline(conn, "resign", FUTURE)
    _final(conn, "fa_keep")
    assert _rows_as(conn, U1, "SELECT choice_kind, state FROM app.choice_windows ORDER BY 1") == [
        ("fa_keep", "final"), ("resign", "open")]
    for kind in ("resign", "fa_keep"):
        (state,) = _rows_as(conn, U1, f"SELECT state FROM app.choice_windows WHERE choice_kind = '{kind}'")[0]
        assert state == _read(conn, U1, f"SELECT shared.choice_window('S', '{kind}')")


def test_the_my_teams_view_gives_an_owner_their_teams_a_co_owner_the_shared_team_and_a_stranger_no_row(conn):
    _world(conn)
    sql = "SELECT team_key FROM app.my_teams ORDER BY 1"
    seen = {uid: [r[0] for r in _rows_as(conn, uid, sql)] for uid in (U1, U2, U3, U4, U5, U6)}
    assert seen == {U1: ["T"], U2: ["T"], U3: ["T2"], U4: [], U5: [], U6: ["T", "T2"]}


def test_neither_view_can_be_written_by_anyone(conn):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    for sql in VIEW_WRITES:
        for role in ("authenticated", "anon", "etl_writer", "etl_reader"):
            conn.execute("SAVEPOINT view_write")
            _as(conn, U1, role)
            with pytest.raises((psycopg.errors.InsufficientPrivilege, psycopg.errors.ObjectNotInPrerequisiteState)):
                conn.execute(sql)
            conn.execute("ROLLBACK TO SAVEPOINT view_write")
    for name in VIEWS:
        assert conn.execute("SELECT pg_relation_is_updatable(%s::regclass, true)", (name,)).fetchone()[0] == 0, name


def test_the_new_tables_have_their_key_checks_and_foreign_keys(conn):
    fks = dict(conn.execute(
        "SELECT conname, confrelid::regclass::text FROM pg_constraint "
        "WHERE conrelid = 'app.team_choice_sharing'::regclass AND contype = 'f'").fetchall())
    assert fks == {"team_choice_sharing_season_id_fkey": "football.dim_season",
                   "team_choice_sharing_team_key_fkey": "football.dim_fantasy_teams"}
    fk = conn.execute("SELECT condeferrable, condeferred, confrelid::regclass::text FROM pg_constraint "
                      "WHERE conrelid = 'shared.owner_crosswalk'::regclass AND contype = 'f'").fetchall()
    assert fk == [(True, True, "football.dim_fantasy_teams")]


def test_the_crosswalk_file_replaces_every_row_so_a_removed_owner_loses_access(conn):
    sys.path.insert(0, str(REPO / "notebooks"))
    import load_owner_crosswalk as loader
    _world(conn)
    assert _read(conn, U1, "SELECT count(*) FROM shared.caller_team_keys()") == 1
    body = loader.sql_file([("T2", DISCORD[U3]), ("T2", DISCORD[U4])]).replace("BEGIN;\n", "").replace("COMMIT;\n", "")
    with conn.cursor() as cur:
        for statement in (s for s in body.split(";\n") if s.strip()):
            cur.execute(statement)
        assert cur.fetchone() == (2, 1)
    assert conn.execute("SELECT count(*) FROM shared.owner_crosswalk").fetchone()[0] == 2
    assert _read(conn, U1, "SELECT count(*) FROM shared.caller_team_keys()") == 0
    assert _read(conn, U6, "SELECT count(*) FROM shared.caller_team_keys()") == 0
    assert _read(conn, U3, "SELECT count(*) FROM shared.caller_team_keys()") == 1
    assert _read(conn, U4, "SELECT count(*) FROM shared.caller_team_keys()") == 1


@pytest.mark.parametrize("value,accepted", [("1" * 17, True), ("9" * 20, True), ("1" * 16, False),
                                            ("1" * 21, False), ("1" * 16 + "a", False), ("", False),
                                            ("1" * 8 + " " + "1" * 8, False)])
def test_the_crosswalk_takes_digits_only_seventeen_to_twenty_long(conn, value, accepted):
    sql = "INSERT INTO shared.owner_crosswalk (team_key, discord_user_id) VALUES ('T', %s)"
    if accepted:
        conn.execute(sql, (value,))
    else:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(sql, (value,))
        conn.rollback()


# --- origin commissioner, the history and the final window (ADR-0026 decisions 4 to 6; #661) ---------

def _history(conn, where="scorer_id = 'x'"):
    return conn.execute("SELECT choice, origin, coalesce(changed_by::text, '-') FROM app.contract_choice_history "
                        f"WHERE {where} ORDER BY recorded_at, changed_at").fetchall()


OWN_UPDATE = "UPDATE app.contract_choices SET choice = 'let_go', origin = 'app', changed_by = %s WHERE scorer_id = 'x'"
HISTORY_INSERT = ("INSERT INTO app.contract_choice_history (season_id, team_key, scorer_id, choice_kind, choice, "
                  "origin, changed_at) VALUES ('S', 'T', 'x', 'fa_keep', 'keep', 'app', now())")


def test_the_table_takes_origin_commissioner_and_an_owner_cannot_write_it_on_insert_or_update(conn):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    _denied(conn, U1, OWN_INSERT, ("T", "x", "fa_keep", "commissioner", U1))
    conn.execute(CHOICE_INSERT, ("fa_keep", "keep", "commissioner"))
    assert _choice(conn)[1] == "commissioner"
    _denied(conn, U1, "UPDATE app.contract_choices SET origin = 'commissioner', changed_by = %s WHERE scorer_id = 'x'",
            (U1,))
    assert _choice(conn)[1] == "commissioner"


def test_an_owner_overwrites_a_commissioners_entry_while_the_window_is_open_and_the_row_returns_to_app(conn):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    conn.execute("INSERT INTO app.contract_choices (season_id, team_key, scorer_id, choice_kind, choice, origin, "
                 "changed_by) VALUES ('S', 'T', 'x', 'fa_keep', 'keep', 'commissioner', %s)", (U3,))
    assert _do(conn, U1, OWN_UPDATE, (U1,)) == 1
    assert _choice(conn) == ("let_go", "app", U1)


def test_an_origin_outside_the_three_is_still_refused(conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(CHOICE_INSERT, ("fa_keep", "keep", "owner"))
    conn.rollback()


def test_the_history_table_has_its_key_and_its_foreign_keys(conn):
    (pk,) = conn.execute(
        "SELECT array_agg(a.attname::text) FROM pg_index i JOIN pg_attribute a "
        "ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
        "WHERE i.indrelid = 'app.contract_choice_history'::regclass AND i.indisprimary").fetchone()
    assert pk == ["history_id"]
    fks = dict(conn.execute("SELECT conname, confrelid::regclass::text FROM pg_constraint "
                            "WHERE conrelid = 'app.contract_choice_history'::regclass AND contype = 'f'").fetchall())
    assert fks == {"contract_choice_history_season_id_fkey": "football.dim_season",
                   "contract_choice_history_team_key_fkey": "football.dim_fantasy_teams"}


def test_an_insert_by_any_route_writes_one_history_row_with_the_database_set_columns(conn):
    conn.execute(CHOICE_INSERT, ("fa_keep", "keep", "loader"))
    assert _history(conn) == [("keep", "loader", "-")]
    action, ok, key = conn.execute("SELECT action_id, recorded_at BETWEEN now() AND clock_timestamp(), history_id "
                                   "FROM app.contract_choice_history").fetchone()
    assert action is None and ok and key is not None


def test_an_owner_insert_and_each_update_write_one_history_row_each_with_who_wrote_it(conn):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    assert _do(conn, U1, OWN_INSERT, ("T", "x", "fa_keep", "app", U1)) == 1
    assert _history(conn) == [("keep", "app", U1)]
    assert _do(conn, U1, OWN_UPDATE, (U1,)) == 1
    assert _do(conn, U2, OWN_UPDATE.replace("let_go", "keep"), (U2,)) == 1
    assert _history(conn) == [("keep", "app", U1), ("let_go", "app", U1), ("keep", "app", U2)]
    assert conn.execute("SELECT count(*) FROM app.contract_choice_history").fetchone()[0] == 3


def test_an_update_of_a_row_with_no_history_first_records_the_old_version_and_only_once(conn):
    conn.execute(CHOICE_INSERT, ("fa_keep", "keep", "loader"))
    (first_changed_at,) = conn.execute("SELECT changed_at FROM app.contract_choices").fetchone()
    conn.execute("DELETE FROM app.contract_choice_history")
    conn.execute("SELECT pg_sleep(0.05)")
    conn.execute("UPDATE app.contract_choices SET choice = 'let_go'")
    assert _history(conn) == [("keep", "loader", "-"), ("let_go", "loader", "-")]
    (old_changed_at,) = conn.execute("SELECT changed_at FROM app.contract_choice_history "
                                     "WHERE choice = 'keep'").fetchone()
    assert old_changed_at == first_changed_at
    conn.execute("UPDATE app.contract_choices SET choice = 'keep'")
    assert [r[0] for r in _history(conn)] == ["keep", "let_go", "keep"]


def test_a_history_is_kept_per_row_and_one_rows_update_leaves_the_others_alone(conn):
    for scorer in ("x", "y"):
        conn.execute("INSERT INTO app.contract_choices (season_id, team_key, scorer_id, choice_kind, choice, origin) "
                     "VALUES ('S', 'T', %s, 'fa_keep', 'keep', 'loader')", (scorer,))
    conn.execute("DELETE FROM app.contract_choice_history WHERE scorer_id = 'y'")
    conn.execute("UPDATE app.contract_choices SET choice = 'let_go' WHERE scorer_id = 'x'")
    assert len(_history(conn, "scorer_id = 'x'")) == 2 and _history(conn, "scorer_id = 'y'") == []


@pytest.mark.parametrize("role", ["authenticated", "anon", "etl_writer", "etl_reader"])
def test_no_role_inserts_updates_or_deletes_a_history_row(conn, role):
    _world(conn)
    conn.execute(CHOICE_INSERT, ("fa_keep", "keep", "loader"))
    for sql in (HISTORY_INSERT, "UPDATE app.contract_choice_history SET choice = 'let_go'",
                "DELETE FROM app.contract_choice_history", "TRUNCATE app.contract_choice_history"):
        _denied(conn, U1, sql, role=role)
    assert len(_history(conn)) == 1


def test_the_history_writer_cannot_be_called_by_any_role(conn):
    _world(conn)
    for role in ("authenticated", "anon", "etl_writer", "etl_reader"):
        _denied(conn, U1, "SELECT ops.record_choice_history()", role=role)


@pytest.mark.parametrize("state", ["open", "passed", "final", "none"])
def test_a_history_row_is_hidden_from_a_caller_exactly_when_its_choice_row_is(conn, state):
    _world(conn)
    if state == "final":
        _final(conn)
    elif state != "none":
        _deadline(conn, "fa_keep", FUTURE if state == "open" else PAST)
    conn.execute(OWN_INSERT, ("T", "x", "fa_keep", "loader", None))
    conn.execute("UPDATE app.contract_choices SET choice = 'let_go'")
    for uid in (U1, U2, U3, U4, U5, U6):
        seen = _choices_seen_by(conn, uid)
        kept = _read(conn, uid, "SELECT count(*) FROM app.contract_choice_history WHERE scorer_id = 'x'")
        assert kept == 2 * seen, (state, uid)
    assert (_choices_seen_by(conn, U3) == 1) is (state in ("passed", "final"))


def test_a_history_row_follows_the_teams_toggle_like_its_choice_row(conn):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    conn.execute(OWN_INSERT, ("T", "x", "fa_keep", "loader", None))
    count = "SELECT count(*) FROM app.contract_choice_history"
    assert _read(conn, U3, count) == 0
    conn.execute("INSERT INTO app.team_choice_sharing (season_id, team_key, shared) VALUES ('S', 'T', true)")
    assert _read(conn, U3, count) == 1 and _read(conn, U4, count) == 1
    conn.execute("UPDATE app.team_choice_sharing SET shared = false")
    assert _read(conn, U3, count) == 0 and _read(conn, U1, count) == 1


def test_a_refused_owner_write_leaves_no_history_row(conn):
    _world(conn)
    _deadline(conn, "fa_keep", FUTURE)
    _denied(conn, U1, OWN_INSERT, ("T", "x", "fa_keep", "loader", U1))
    _denied(conn, U3, OWN_INSERT, ("T", "x", "fa_keep", "app", U3))
    assert conn.execute("SELECT count(*) FROM app.contract_choice_history").fetchone()[0] == 0


def test_the_loaders_file_writes_a_history_row_for_each_row_it_writes(conn):
    import load_contract_choices as loader
    rows = [{"team_key": "T", "scorer_id": s, "choice": "let_go", "locked_value": 5.0} for s in ("x", "y", "z")]
    body = loader.sql_file("S", rows).replace("BEGIN;\n", "").replace("COMMIT;\n", "")
    written, _ = conn.execute(body).fetchone()
    assert written == 3
    assert conn.execute("SELECT count(*) FROM app.contract_choice_history").fetchone()[0] == 3


NEW_MIGRATION = "_choice_history_final_window.sql"
NEW_DROPS = "_choice_history_final_window_drops.sql"


def _final_at_default(c):
    return c.execute("SELECT column_default FROM information_schema.columns WHERE table_schema = 'ops' "
                     "AND table_name = 'choice_deadline' AND column_name = 'final_at'").fetchone()[0]


def test_the_migration_gives_the_one_passed_row_its_final_instant_with_the_guard_untouched():
    """A throwaway database made here (never the one under test): every migration before
    the new ones applies, one passed deadline row and one choice row are put in, then the
    new migration applies, and then the one that drops the fill's default."""
    from psycopg import conninfo
    files = sorted((REPO / "supabase" / "migrations").glob("*.sql"))
    (new,) = [f for f in files if f.name.endswith(NEW_MIGRATION)]
    (drops,) = [f for f in files if f.name.endswith(NEW_DROPS)]
    assert files.index(drops) == files.index(new) + 1
    before = files[:files.index(new)]
    name = "migration_before_final_window"
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {name}")
        admin.execute(f"CREATE DATABASE {name}")
    try:
        with psycopg.connect(conninfo.make_conninfo(URL, dbname=name), autocommit=True) as c:
            c.execute(AUTH_STUB.read_text(encoding="utf-8"))
            for path in before:
                c.execute(path.read_text(encoding="utf-8"))
            c.execute("SET session_replication_role = replica")
            c.execute("INSERT INTO ops.choice_deadline (season_id, choice_kind, deadline_at) "
                      "VALUES ('S', 'fa_keep', now() - interval '1 hour')")
            c.execute("INSERT INTO app.contract_choices (season_id, team_key, scorer_id, choice_kind, choice, origin) "
                      "VALUES ('S', 'T', 'x', 'fa_keep', 'keep', 'loader')")
            c.execute("SET session_replication_role = origin")
            assert not c.execute("SELECT to_regclass('app.contract_choice_history')").fetchone()[0]
            c.execute(new.read_text(encoding="utf-8"))
            assert c.execute("SELECT count(*), bool_and(final_at = timestamptz '2027-03-01 04:59:59+00' "
                             "AND deadline_at < final_at) FROM ops.choice_deadline").fetchone() == (1, True)
            assert c.execute("SELECT tgenabled FROM pg_trigger WHERE tgrelid = 'ops.choice_deadline'::regclass "
                             "AND tgname = 'choice_deadline_guard_row'").fetchone() == ("O",)
            assert "2027-03-01" in _final_at_default(c)
            c.execute(drops.read_text(encoding="utf-8"))
            assert _final_at_default(c) is None
            assert c.execute("SELECT count(*), bool_and(final_at = timestamptz '2027-03-01 04:59:59+00') "
                             "FROM ops.choice_deadline").fetchone() == (1, True)
            with pytest.raises(psycopg.errors.RaiseException):
                c.execute("UPDATE ops.choice_deadline SET final_at = final_at + interval '1 day'")
            with pytest.raises(psycopg.errors.RaiseException):
                c.execute("DELETE FROM ops.choice_deadline")
            assert c.execute("SELECT shared.choice_window('S', 'fa_keep')").fetchone() == ("passed",)
            with c.transaction(force_rollback=True):
                c.execute("UPDATE app.contract_choices SET choice = 'let_go'")
                assert c.execute("SELECT choice FROM app.contract_choice_history ORDER BY recorded_at, changed_at"
                                 ).fetchall() == [("keep",), ("let_go",)]
    finally:
        with psycopg.connect(URL, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {name}")


# --- the role table, its two checks and the role, phase and action table (ADR-0026 decisions 1, 2 and 7; #662) ---
# Made-up users, ids and teams. A stranger has a Discord identity the crosswalk does not list; the two owners own
# T and T2; the commissioner and the site admin hold a role and own no team.
PERSONAS = {"stranger": ("00000000-0000-0000-0000-0000000000a1", "71111111111111111"),
            "owner_of_team": ("00000000-0000-0000-0000-0000000000a2", "72222222222222222"),
            "owner_of_other_team": ("00000000-0000-0000-0000-0000000000a3", "73333333333333333"),
            "commissioner": ("00000000-0000-0000-0000-0000000000a4", "74444444444444444"),
            "site_admin": ("00000000-0000-0000-0000-0000000000a5", "75555555555555555")}
ROLES_OF = {"commissioner": ("commissioner", gm.LEAGUE_PLACEHOLDER), "site_admin": ("site_admin", gm.ALL_LEAGUES)}
OWNS = {"owner_of_team": "T", "owner_of_other_team": "T2"}
ROLE_INSERT = "INSERT INTO shared.app_role (discord_user_id, role, league_key) VALUES (%s, %s, %s)"
TABLE_FILE = REPO / "tests" / "role_phase_action.csv"
PHASES = ("none", "open", "passed", "final")


def _roles_world(conn):
    """Teams T and T2, each persona's Discord identity, the crosswalk rows and the two role rows."""
    for team in ("T", "T2"):
        conn.execute("INSERT INTO football.dim_fantasy_teams (team_key) VALUES (%s)", (team,))
    for name, (uid, discord_id) in PERSONAS.items():
        conn.execute("INSERT INTO auth.identities (user_id, provider, provider_id) VALUES (%s, 'discord', %s)",
                     (uid, discord_id))
        if name in OWNS:
            conn.execute("INSERT INTO shared.owner_crosswalk (team_key, discord_user_id) VALUES (%s, %s)",
                         (OWNS[name], discord_id))
        if name in ROLES_OF:
            conn.execute(ROLE_INSERT, (discord_id, *ROLES_OF[name]))


def test_the_role_table_is_unreadable_and_unwritable_to_every_role_but_its_owner(conn):
    _roles_world(conn)
    uid = PERSONAS["commissioner"][0]
    for role in ("authenticated", "anon", "etl_writer", "etl_reader"):
        _denied(conn, uid, "SELECT * FROM shared.app_role", role=role)
        _denied(conn, uid, ROLE_INSERT % ("'99999999999999999'", "'site_admin'", "'*'"), role=role)
        _denied(conn, uid, "UPDATE shared.app_role SET role = 'site_admin'", role=role)
        _denied(conn, uid, "DELETE FROM shared.app_role", role=role)
    assert conn.execute("SELECT relrowsecurity FROM pg_class WHERE oid = 'shared.app_role'::regclass").fetchone()[0]
    assert not conn.execute("SELECT count(*) FROM pg_policies WHERE tablename = 'app_role'").fetchone()[0]
    assert conn.execute("SELECT count(*) FROM shared.app_role").fetchone()[0] == 2


def test_the_role_table_has_its_key_and_no_foreign_key(conn):
    (pk,) = conn.execute(
        "SELECT array_agg(a.attname::text ORDER BY a.attnum) FROM pg_index i JOIN pg_attribute a "
        "ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
        "WHERE i.indrelid = 'shared.app_role'::regclass AND i.indisprimary").fetchone()
    assert pk == ["discord_user_id", "role", "league_key"]
    assert conn.execute("SELECT count(*) FROM pg_constraint WHERE conrelid = 'shared.app_role'::regclass "
                        "AND contype = 'f'").fetchone()[0] == 0


@pytest.mark.parametrize("value,accepted", [("1" * 17, True), ("9" * 20, True), ("1" * 16, False),
                                            ("1" * 21, False), ("1" * 16 + "a", False), ("", False),
                                            ("1" * 8 + " " + "1" * 8, False)])
def test_the_role_table_takes_digits_only_seventeen_to_twenty_long(conn, value, accepted):
    if accepted:
        conn.execute(ROLE_INSERT, (value, "commissioner", "main"))
    else:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(ROLE_INSERT, (value, "commissioner", "main"))
        conn.rollback()


@pytest.mark.parametrize("role,league,accepted", [
    ("commissioner", "main", True), ("commissioner", "other", True), ("site_admin", "*", True),
    ("commissioner", "*", False), ("site_admin", "main", False), ("owner", "main", False),
    ("", "main", False), ("Commissioner", "main", False)])
def test_a_commissioner_names_a_league_a_site_admin_holds_every_league_and_no_other_role_exists(
        conn, role, league, accepted):
    if accepted:
        conn.execute(ROLE_INSERT, ("1" * 17, role, league))
    else:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(ROLE_INSERT, ("1" * 17, role, league))
        conn.rollback()


def test_a_person_may_hold_both_roles_and_a_repeated_pair_is_refused(conn):
    conn.execute(ROLE_INSERT, ("1" * 17, "commissioner", "main"))
    conn.execute(ROLE_INSERT, ("1" * 17, "site_admin", "*"))
    conn.execute("SAVEPOINT twice")
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(ROLE_INSERT, ("1" * 17, "commissioner", "main"))
    conn.execute("ROLLBACK TO SAVEPOINT twice")


def test_the_two_checks_tell_the_truth_for_each_kind_of_caller(conn):
    _roles_world(conn)
    commissioner_of = "SELECT shared.caller_is_commissioner_for(%s)"
    admin = "SELECT shared.caller_is_site_admin()"
    answers = {name: (_read(conn, uid, commissioner_of, ("T",)), _read(conn, uid, commissioner_of, ("T2",)),
                      _read(conn, uid, admin)) for name, (uid, _) in PERSONAS.items()}
    assert answers == {"commissioner": (True, True, False), "site_admin": (False, False, True),
                       "owner_of_team": (False, False, False), "owner_of_other_team": (False, False, False),
                       "stranger": (False, False, False)}
    assert _read(conn, "", commissioner_of, ("T",)) is False and _read(conn, "", admin) is False
    assert _read(conn, PERSONAS["commissioner"][0], commissioner_of, ("NO_SUCH_TEAM",)) is False


def test_a_person_holding_both_roles_passes_both_checks(conn):
    _roles_world(conn)
    uid, discord_id = PERSONAS["stranger"]
    conn.execute(ROLE_INSERT, (discord_id, "commissioner", "main"))
    conn.execute(ROLE_INSERT, (discord_id, "site_admin", "*"))
    assert _read(conn, uid, "SELECT shared.caller_is_commissioner_for('T')") is True
    assert _read(conn, uid, "SELECT shared.caller_is_site_admin()") is True


def test_a_commissioner_of_another_league_is_no_commissioner_of_this_one(conn):
    _roles_world(conn)
    uid, discord_id = PERSONAS["stranger"]
    conn.execute(ROLE_INSERT, (discord_id, "commissioner", "another_league"))
    assert _read(conn, uid, "SELECT shared.caller_is_commissioner_for('T')") is False


def test_a_role_is_read_from_the_discord_identity_and_never_from_another_provider(conn):
    _roles_world(conn)
    other = "00000000-0000-0000-0000-0000000000b1"
    conn.execute("INSERT INTO auth.identities (user_id, provider, provider_id) VALUES (%s, 'github', %s)",
                 (other, PERSONAS["site_admin"][1]))
    assert _read(conn, other, "SELECT shared.caller_is_site_admin()") is False
    assert _read(conn, other, "SELECT shared.caller_is_commissioner_for('T')") is False


def test_the_role_file_replaces_every_row_so_a_removed_role_is_gone(conn):
    sys.path.insert(0, str(REPO / "notebooks"))
    import load_app_roles as loader
    _roles_world(conn)
    admin_uid = PERSONAS["site_admin"][0]
    assert _read(conn, admin_uid, "SELECT shared.caller_is_site_admin()") is True
    rows = [(PERSONAS["commissioner"][1], "commissioner", "main"), (PERSONAS["stranger"][1], "site_admin", "*")]
    body = loader.sql_file(rows).replace("BEGIN;\n", "").replace("COMMIT;\n", "")
    with conn.cursor() as cur:
        for statement in (s for s in body.split(";\n") if s.strip()):
            cur.execute(statement)
        assert cur.fetchone() == (2, 2)
    assert _read(conn, admin_uid, "SELECT shared.caller_is_site_admin()") is False
    assert _read(conn, PERSONAS["stranger"][0], "SELECT shared.caller_is_site_admin()") is True
    assert _read(conn, PERSONAS["commissioner"][0], "SELECT shared.caller_is_commissioner_for('T')") is True


def test_the_pii_hash_list_holds_the_sha256_of_each_role_table_id_and_never_the_id(conn):
    import hashlib
    _roles_world(conn)
    with conn.cursor() as cur:
        cur.execute("SET LOCAL ROLE etl_writer")
        cur.execute("SELECT * FROM shared.pii_token_hashes()")
        got = {r[0] for r in cur.fetchall()}
    conn.rollback()

    def digest(text):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    in_the_table = {PERSONAS["commissioner"][1], PERSONAS["site_admin"][1]}
    assert {digest(i) for i in in_the_table} <= got
    assert digest(PERSONAS["stranger"][1]) not in got
    assert not {i for _, i in PERSONAS.values()} & got


def _table_rows():
    with TABLE_FILE.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(line for line in fh if not line.startswith("#")))


def _seed_phase(conn, phase):
    for kind in ("resign", "fa_keep"):
        if phase == "open":
            _deadline(conn, kind, FUTURE)
        elif phase == "passed":
            _deadline(conn, kind, PAST)
        elif phase == "final":
            _deadline(conn, kind, *FINAL_ROW)


def _attempt(conn, who, sql, params=(), fetch=False):
    """True when the persona's statement went through: a write that changed a row, or a read that
    returned a row. Postgres raises insufficient_privilege for a row-level security refusal too."""
    uid = PERSONAS[who][0] if who in PERSONAS else ""
    conn.execute("SAVEPOINT cell_try")
    try:
        _as(conn, uid, "anon" if who == "signed_out" else "authenticated")
        cur = conn.execute(sql, params)
        return bool(cur.fetchall()) if fetch else cur.rowcount == 1
    except psycopg.errors.InsufficientPrivilege:
        return False
    finally:
        conn.execute("ROLLBACK TO SAVEPOINT cell_try")


def _who(who):
    return PERSONAS[who][0] if who in PERSONAS else None


ACTIONS = {
    "read_choices": lambda conn, who: _attempt(conn, who, "SELECT 1 FROM app.contract_choices WHERE team_key = 'T'",
                                               fetch=True),
    "write_choices": lambda conn, who: _attempt(conn, who, OWN_INSERT, ("T", "w", "fa_keep", "app", _who(who))),
    "read_toggle": lambda conn, who: _attempt(conn, who, "SELECT 1 FROM app.team_choice_sharing WHERE team_key = 'T'",
                                              fetch=True),
    "write_toggle": lambda conn, who: _attempt(conn, who, SHARE_INSERT, ("T", True, _who(who))),
    "read_windows": lambda conn, who: _attempt(conn, who, "SELECT 1 FROM app.choice_windows", fetch=True),
    "read_my_teams": lambda conn, who: _attempt(conn, who, "SELECT 1 FROM app.my_teams WHERE team_key = 'T'",
                                                fetch=True),
}


def _outcome(conn, who, action, phase):
    conn.execute("SAVEPOINT cell")
    try:
        _roles_world(conn)
        _seed_phase(conn, phase)
        conn.execute(OWN_INSERT, ("T", "x", "fa_keep", "loader", None))
        if action == "read_toggle":
            conn.execute("INSERT INTO app.team_choice_sharing (season_id, team_key, shared, changed_by) "
                         "VALUES ('S', 'T', false, NULL)")
        return "allowed" if ACTIONS[action](conn, who) else "refused"
    finally:
        conn.execute("ROLLBACK TO SAVEPOINT cell")
        conn.execute("RELEASE SAVEPOINT cell")


def test_the_table_names_every_persona_and_action_once_and_every_cell_is_allowed_or_refused():
    rows = _table_rows()
    assert list(rows[0]) == ["persona", "action", *PHASES]
    keys = [(r["persona"], r["action"]) for r in rows]
    assert len(keys) == len(set(keys))
    personas = {"stranger", "owner_of_team", "owner_of_other_team", "commissioner", "site_admin", "signed_out"}
    assert set(PERSONAS) | {"signed_out"} == personas
    assert set(keys) == {(p, a) for p in personas for a in ACTIONS}
    for row in rows:
        assert all(row[phase] in ("allowed", "refused") for phase in PHASES), row


def test_a_commissioner_and_a_site_admin_hold_exactly_a_strangers_powers_on_the_app_tables():
    by = {(r["persona"], r["action"]): [r[p] for p in PHASES] for r in _table_rows()}
    for action in ACTIONS:
        for persona in ("commissioner", "site_admin", "owner_of_other_team"):
            assert by[(persona, action)] == by[("stranger", action)], (persona, action)


@pytest.mark.parametrize("phase", PHASES)
@pytest.mark.parametrize("persona,action", [(r["persona"], r["action"]) for r in _table_rows()])
def test_every_cell_of_the_role_phase_and_action_table_is_proved_by_the_policies(conn, persona, action, phase):
    expected = {(r["persona"], r["action"]): r for r in _table_rows()}[(persona, action)][phase]
    assert _outcome(conn, persona, action, phase) == expected


# The two load functions of the scheduled run (ADR-0026 decision 2 as amended, #700).
L1, L2, L3, L4 = "41111111111111111", "42222222222222222", "43333333333333333", "44444444444444444"
LOAD_IDS = (L1, L2, L3, L4)
LOAD_CROSSWALK = "SELECT rows_before, rows_after FROM shared.load_owner_crosswalk(%s::text[], %s::text[])"
LOAD_ROLES = "SELECT rows_before, rows_after FROM shared.load_app_roles(%s::text[], %s::text[])"
LOAD_TABLES = {"shared.load_owner_crosswalk": ("shared.owner_crosswalk", "team_key, discord_user_id"),
               "shared.load_app_roles": ("shared.app_role", "discord_user_id, role, league_key")}


def _load_world(conn):
    for team in ("T", "T2"):
        conn.execute("INSERT INTO football.dim_fantasy_teams (team_key) VALUES (%s)", (team,))
    conn.execute("INSERT INTO shared.owner_crosswalk (team_key, discord_user_id) VALUES ('T', %s), ('T2', %s)",
                 (L1, L2))
    conn.execute("INSERT INTO shared.app_role (discord_user_id, role, league_key) VALUES (%s, 'commissioner', 'main')",
                 (L1,))


def _load(conn, call, first, second):
    """(counts, None) or (None, the error), called as etl_writer inside a savepoint."""
    conn.execute("SELECT 1")
    try:
        with conn.transaction():
            conn.execute("SET LOCAL ROLE etl_writer")
            return conn.execute(call, (first, second)).fetchone(), None
    except psycopg.errors.Error as exc:
        return None, exc
    finally:
        conn.execute("RESET ROLE")


def _rows(conn, table, columns):
    return sorted(conn.execute(f"SELECT {columns} FROM {table}").fetchall())


def _words(exc):
    d = exc.diag
    return " ".join(str(p) for p in (exc, d.message_primary, d.message_detail, d.message_hint, d.context))


@pytest.mark.parametrize("name", LOAD_FUNCTIONS)
def test_the_writer_alone_executes_each_load_function_and_it_is_a_definer_with_the_search_path_empty(conn, name):
    (oid, definer, config) = conn.execute("SELECT p.oid, p.prosecdef, p.proconfig FROM pg_proc p "
                                          "WHERE p.pronamespace = 'shared'::regnamespace AND p.proname = %s",
                                          (name,)).fetchone()
    assert definer and any(c.replace(" ", "") in ('search_path=""', "search_path=") for c in (config or []))
    for role, expected in (("etl_writer", True), ("etl_reader", False), ("authenticated", False),
                           ("anon", False), ("public", False)):
        assert conn.execute("SELECT has_function_privilege(%s, %s, 'EXECUTE')", (role, oid)).fetchone()[0] is expected, role


def test_the_writer_holds_no_grant_on_either_table_and_is_refused_every_statement_on_them(conn):
    for table in ("shared.owner_crosswalk", "shared.app_role"):
        assert not conn.execute("SELECT has_table_privilege('etl_writer', %s, 'SELECT,INSERT,UPDATE,DELETE')",
                                (table,)).fetchone()[0]
        assert not conn.execute("SELECT count(*) FROM information_schema.column_privileges WHERE grantee = 'etl_writer' "
                                "AND table_schema = 'shared' AND table_name = %s", (table.split(".")[1],)).fetchone()[0]
        assert not conn.execute("SELECT count(*) FROM pg_policies WHERE tablename = %s", (table.split(".")[1],)).fetchone()[0]
        _refused(conn, "etl_writer", f"SELECT * FROM {table}")
        _refused(conn, "etl_writer", f"DELETE FROM {table}")


def test_a_good_set_replaces_the_crosswalk_rows_and_returns_the_two_counts(conn):
    _load_world(conn)
    counts, error = _load(conn, LOAD_CROSSWALK, ["T", "T", "T2"], [L1, L3, L3])
    assert error is None and counts == (2, 3)
    assert _rows(conn, "shared.owner_crosswalk", "team_key, discord_user_id") == [("T", L1), ("T", L3), ("T2", L3)]


def test_a_good_set_replaces_the_role_rows_gives_each_its_league_and_returns_the_two_counts(conn):
    _load_world(conn)
    counts, error = _load(conn, LOAD_ROLES, [L2, L3, L3], ["commissioner", "site_admin", "commissioner"])
    assert error is None and counts == (1, 3)
    assert _rows(conn, "shared.app_role", "discord_user_id, role, league_key") == sorted([
        (L2, "commissioner", gm.LEAGUE_PLACEHOLDER), (L3, "site_admin", gm.ALL_LEAGUES),
        (L3, "commissioner", gm.LEAGUE_PLACEHOLDER)])


def test_a_set_that_drops_a_row_removes_it_so_a_removed_owner_or_role_is_gone(conn):
    _load_world(conn)
    assert _load(conn, LOAD_CROSSWALK, ["T"], [L1])[0] == (2, 1)
    assert _load(conn, LOAD_ROLES, [L2], ["site_admin"])[0] == (1, 1)
    assert _rows(conn, "shared.owner_crosswalk", "team_key, discord_user_id") == [("T", L1)]
    assert _rows(conn, "shared.app_role", "discord_user_id, role, league_key") == [(L2, "site_admin", "*")]


REFUSED_CROSSWALK = {
    "empty": ([], []), "null arrays": (None, None), "unequal": (["T", "T2"], [L3]),
    "short id": (["T"], ["4" * 16]), "long id": (["T"], ["4" * 21]), "letter in id": (["T"], ["4" * 16 + "x"]),
    "id with a space": (["T"], ["4" * 16 + " "]), "null id": (["T"], [None]), "null team": ([None], [L3]),
    "unknown team": (["NOPE"], [L3]), "repeated pair": (["T", "T"], [L3, L3]),
    "one bad row among good": (["T", "T2"], [L3, "4" * 16]),
}
REFUSED_ROLES = {
    "empty": ([], []), "null arrays": (None, None), "unequal": ([L3, L4], ["site_admin"]),
    "short id": (["4" * 16], ["site_admin"]), "long id": (["4" * 21], ["site_admin"]),
    "letter in id": (["4" * 16 + "x"], ["site_admin"]), "null id": ([None], ["site_admin"]),
    "unknown role word": ([L3], ["owner"]), "wrong case": ([L3], ["Commissioner"]), "null role": ([L3], [None]),
    "repeated pair": ([L3, L3], ["site_admin", "site_admin"]),
    "one bad row among good": ([L3, L4], ["site_admin", "root"]),
}


@pytest.mark.parametrize("case", REFUSED_CROSSWALK)
def test_the_crosswalk_function_refuses_a_bad_set_changes_nothing_and_names_no_value(conn, case):
    _load_world(conn)
    before = _rows(conn, "shared.owner_crosswalk", "team_key, discord_user_id")
    counts, error = _load(conn, LOAD_CROSSWALK, *REFUSED_CROSSWALK[case])
    assert counts is None and isinstance(error, psycopg.errors.RaiseException), case
    assert "nothing changed" in error.diag.message_primary
    assert not any(i in _words(error) for i in LOAD_IDS), _words(error)
    assert _rows(conn, "shared.owner_crosswalk", "team_key, discord_user_id") == before


@pytest.mark.parametrize("case", REFUSED_ROLES)
def test_the_role_function_refuses_a_bad_set_changes_nothing_and_names_no_value(conn, case):
    _load_world(conn)
    before = _rows(conn, "shared.app_role", "discord_user_id, role, league_key")
    counts, error = _load(conn, LOAD_ROLES, *REFUSED_ROLES[case])
    assert counts is None and isinstance(error, psycopg.errors.RaiseException), case
    assert "nothing changed" in error.diag.message_primary
    assert not any(i in _words(error) for i in LOAD_IDS), _words(error)
    assert _rows(conn, "shared.app_role", "discord_user_id, role, league_key") == before


@pytest.mark.parametrize("name,call,first,second", [
    ("shared.load_owner_crosswalk", LOAD_CROSSWALK, ["T", "T2", "T"], [L2, L3, L4]),
    ("shared.load_app_roles", LOAD_ROLES, [L2, L3, L4], ["site_admin", "commissioner", "commissioner"])])
def test_a_set_that_fails_part_way_leaves_the_table_unchanged_and_the_message_names_no_id(
        conn, name, call, first, second):
    table, columns = LOAD_TABLES[name]
    _load_world(conn)
    conn.execute("CREATE FUNCTION public.boom_on_the_third() RETURNS trigger LANGUAGE plpgsql AS $b$ "
                 "BEGIN IF NEW.discord_user_id = '" + L4 + "' THEN "
                 "RAISE EXCEPTION 'the row holding % broke', NEW.discord_user_id; END IF; RETURN NEW; END $b$")
    conn.execute(f"CREATE TRIGGER boom BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION public.boom_on_the_third()")
    before = _rows(conn, table, columns)
    counts, error = _load(conn, call, first, second)
    assert counts is None and isinstance(error, psycopg.errors.RaiseException)
    assert error.diag.message_primary.endswith("(SQLSTATE P0001); nothing changed")
    assert not any(i in _words(error) for i in LOAD_IDS), _words(error)
    assert _rows(conn, table, columns) == before


def test_the_returned_value_of_both_functions_is_two_integers_and_nothing_else(conn):
    _load_world(conn)
    for call, first, second in ((LOAD_CROSSWALK, ["T"], [L3]), (LOAD_ROLES, [L3], ["site_admin"])):
        counts, error = _load(conn, call, first, second)
        assert error is None and len(counts) == 2 and all(type(c) is int for c in counts)
        assert not any(i in str(counts) for i in LOAD_IDS)
    columns = conn.execute("SELECT p.proname, pg_get_function_result(p.oid) FROM pg_proc p "
                           "WHERE p.pronamespace = 'shared'::regnamespace AND p.proname = ANY(%s)",
                           (list(LOAD_FUNCTIONS),)).fetchall()
    assert {r[1] for r in columns} == {"TABLE(rows_before integer, rows_after integer)"}


def test_a_role_holder_loaded_through_the_function_reaches_the_pii_hash_list_and_the_two_checks(conn):
    import hashlib
    _load_world(conn)
    assert _load(conn, LOAD_ROLES, [L3], ["site_admin"])[0] == (1, 1)
    conn.execute("INSERT INTO auth.identities (user_id, provider, provider_id) VALUES (%s, 'discord', %s)",
                 ("00000000-0000-0000-0000-0000000000c3", L3))
    with conn.cursor() as cur:
        cur.execute("SET LOCAL ROLE etl_writer")
        cur.execute("SELECT * FROM shared.pii_token_hashes()")
        got = {r[0] for r in cur.fetchall()}
    conn.execute("RESET ROLE")
    assert hashlib.sha256(L3.encode("utf-8")).hexdigest() in got and L3 not in got
    assert _read(conn, "00000000-0000-0000-0000-0000000000c3", "SELECT shared.caller_is_site_admin()") is True
