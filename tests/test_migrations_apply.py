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


DEADLINE_WRITES = ("INSERT INTO ops.choice_deadline (season_id, choice_kind, deadline_at) "
                   "VALUES ('S', 'resign', now() - interval '1 hour')",
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


@pytest.mark.parametrize("state", ["passed", "none"])
def test_every_owner_write_is_refused_once_the_deadline_has_passed_and_with_no_deadline_row(conn, state):
    _world(conn)
    if state == "passed":
        _deadline(conn, "fa_keep", PAST)
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


@pytest.mark.parametrize("state,others,owner", [("open", 0, 1), ("passed", 1, 1), ("none", 0, 1)])
def test_a_row_is_private_while_open_public_once_passed_and_private_again_with_no_deadline_row(
        conn, state, others, owner):
    _world(conn)
    if state != "none":
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
                                  "SELECT shared.choice_window('S', 'fa_keep')"])
def test_the_two_definer_functions_cannot_be_called_by_anon_or_an_etl_role(conn, role, call):
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


def test_anon_reads_and_writes_nothing_anywhere(conn):
    _world(conn)
    _deadline(conn, "fa_keep", PAST)
    conn.execute(OWN_INSERT, ("T", "x", "fa_keep", "loader", None))
    for sql in ("SELECT * FROM app.contract_choices", "SELECT * FROM app.team_choice_sharing",
                "SELECT * FROM football.dim_season", "SELECT * FROM ops.choice_deadline",
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
    for table in ("app.contract_choices", "app.team_choice_sharing"):
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            assert not conn.execute("SELECT has_table_privilege('etl_reader', %s, %s)",
                                    (table, privilege)).fetchone()[0], (table, privilege)
    assert not conn.execute("SELECT has_table_privilege('etl_writer', 'app.team_choice_sharing', "
                            "'SELECT,INSERT,UPDATE,DELETE')").fetchone()[0]
    assert conn.execute("SELECT has_table_privilege('etl_writer', 'app.contract_choices', 'SELECT')").fetchone()[0]
    assert not conn.execute("SELECT has_table_privilege('etl_writer', 'app.contract_choices', "
                            "'INSERT,UPDATE,DELETE')").fetchone()[0]
    for role in ("etl_writer", "etl_reader"):
        assert not conn.execute("SELECT has_table_privilege(%s, 'shared.owner_crosswalk', "
                                "'SELECT,INSERT,UPDATE,DELETE')", (role,)).fetchone()[0]


DEFINERS = ("caller_team_keys", "choice_window")
SHARED_FUNCTIONS_TODAY = 1


def test_the_functions_in_shared_are_the_pii_hash_and_the_two_definers_and_no_others(conn):
    names = [r[0] for r in conn.execute("SELECT proname FROM pg_proc WHERE pronamespace = 'shared'::regnamespace "
                                        "ORDER BY proname").fetchall()]
    assert names == ["caller_team_keys", "choice_window", "pii_token_hashes"]
    assert len(names) == SHARED_FUNCTIONS_TODAY + len(DEFINERS)


def test_no_function_in_shared_but_the_two_definers_is_executable_by_authenticated_anon_or_public(conn):
    rows = conn.execute("SELECT p.proname, p.oid FROM pg_proc p WHERE p.pronamespace = 'shared'::regnamespace").fetchall()
    others = [(name, oid) for name, oid in rows if name not in DEFINERS]
    assert others
    for name, oid in others:
        for role in ("authenticated", "anon", "public"):
            assert not conn.execute("SELECT has_function_privilege(%s, %s, 'EXECUTE')", (role, oid)).fetchone()[0], \
                (name, role)


def test_the_two_definers_are_executable_by_authenticated_alone_and_pin_the_search_path(conn):
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
    assert {digest(i) for i in DISCORD.values()} <= got
    assert {digest("test"), digest("person"), digest("testuser")} <= got
    assert not set(DISCORD.values()) & got


def test_the_owner_policies_are_the_eight_named_and_all_for_authenticated(conn):
    rows = conn.execute("SELECT tablename, policyname, cmd, roles::text[] FROM pg_policies WHERE schemaname = 'app' "
                        "AND roles::text[] <@ ARRAY['authenticated'] ORDER BY 1, 2").fetchall()
    assert [(t, p, c) for t, p, c, _ in rows] == [
        ("contract_choices", "owner_insert_own_team_while_open", "INSERT"),
        ("contract_choices", "owner_select_own_team", "SELECT"),
        ("contract_choices", "owner_update_own_team_while_open", "UPDATE"),
        ("contract_choices", "signed_in_select_after_deadline", "SELECT"),
        ("contract_choices", "signed_in_select_shared_team", "SELECT"),
        ("team_choice_sharing", "owner_insert_own_team_while_open", "INSERT"),
        ("team_choice_sharing", "owner_update_own_team_while_open", "UPDATE"),
        ("team_choice_sharing", "signed_in_select_all", "SELECT")]
    assert all(r[3] == ["authenticated"] for r in rows)


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
