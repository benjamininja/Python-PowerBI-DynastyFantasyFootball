"""The Postgres backend of the storage seam (ADR-0014, ADR-0018, #135).

etl_helpers.read_table / write_table / table_exists hand a table here when
ETL_STORAGE=postgres. etl_helpers has already checked the batch against
docs/data_model.yml; this module maps it to SQL. The login is the URL in
SUPABASE_DB_URL. Each table is `<schema>.<name>`, the schema and primary key
taken from supabase/registry_state.json.
"""
import contextlib
import json
import os
import re
from pathlib import Path
from typing import NamedTuple

import pandas as pd

STATE_PATH = Path(__file__).resolve().parent.parent / "supabase" / "registry_state.json"
URL_ENV = "SUPABASE_DB_URL"
BATCH_TABLE = "_seam_batch"
_TEXT_DTYPES = ("str", "string", "object")


class WriteRefused(ValueError):
    """The database refused the batch: a value out of range, a null or a
    repeated key, a check, or a foreign key at commit."""


def _psycopg():
    import psycopg
    from psycopg import sql
    return psycopg, sql


@contextlib.contextmanager
def _db_errors():
    """Any error psycopg raises comes out as WriteRefused, first line only."""
    psycopg, _ = _psycopg()
    try:
        yield
    except psycopg.Error as exc:
        lines = str(exc).strip().splitlines()
        raise WriteRefused(lines[0] if lines else type(exc).__name__) from exc


def _connect():
    url = os.environ.get(URL_ENV)
    if not url:
        raise RuntimeError(f"ETL_STORAGE=postgres needs {URL_ENV} set")
    psycopg, _ = _psycopg()
    return psycopg.connect(url, prepare_threshold=None)


def _state() -> dict:
    with Path(STATE_PATH).open(encoding="utf-8") as fh:
        tables = json.load(fh)["tables"]
    return {spec["name"]: spec for spec in tables.values()}


def _spec(entry: dict) -> dict:
    spec = _state().get(entry["name"])
    if spec is None:
        raise WriteRefused(f"{entry['name']}: not in {Path(STATE_PATH).name}")
    return spec


def _table(spec: dict):
    _, sql = _psycopg()
    return sql.Identifier(spec["schema"], spec["name"])


def _names(columns):
    _, sql = _psycopg()
    return sql.SQL(", ").join(sql.Identifier(c) for c in columns)


def _declared(entry: dict) -> dict:
    return {c["name"]: str(c["dtype"]) for c in entry.get("columns") or []}


def _check_columns(entry: dict, spec: dict) -> list[str]:
    columns = [c["name"] for c in spec["columns"]]
    if set(columns) != set(_declared(entry)):
        raise WriteRefused(f"{entry['name']}: the registry and {Path(STATE_PATH).name} "
                           f"declare different columns")
    return columns


def has_rows(entry: dict) -> bool:
    _, sql = _psycopg()
    spec = _spec(entry)
    query = sql.SQL("SELECT EXISTS (SELECT 1 FROM {})").format(_table(spec))
    with _db_errors(), _connect() as conn:
        return bool(conn.execute(query).fetchone()[0])


def _series(values: list, sql_type: str, declared: str) -> pd.Series:
    if declared.startswith("datetime64"):
        stamps = pd.to_datetime(pd.Series(values, dtype=object), utc="," in declared)
        return stamps.astype(declared)
    if declared in _TEXT_DTYPES:
        if sql_type == "date":
            values = [None if v is None else v.isoformat() for v in values]
        return pd.Series(values)
    return pd.Series(values, dtype=object)


def read(entry: dict, columns=None):
    """The table as a frame in registry column order (or `columns`), rows
    ordered by primary key; None when it holds no rows. Values are mapped to
    the registry dtype where the SQL type differs: date to an ISO string,
    integer to float, timestamp to the declared unit, timestamptz to UTC."""
    with _db_errors(), _connect() as conn:
        return read_on(conn, entry, columns)


def read_on(conn, entry: dict, columns=None):
    """`read` on an open connection, so a load can read back what it wrote
    before it commits. The rows come in the binary format, which sends a
    double as its 8 bytes whatever extra_float_digits the session holds; the
    text format prints 15 digits at 0 (a Supabase session) and loses bits."""
    _, sql = _psycopg()
    spec = _spec(entry)
    declared = _declared(entry)
    names = _check_columns(entry, spec)
    wanted = names if columns is None else list(columns)
    unknown = [c for c in wanted if c not in declared]
    if unknown:
        raise WriteRefused(f"{entry['name']}: no such column {unknown}")
    query = sql.SQL("SELECT {} FROM {} ORDER BY {}").format(
        _names(wanted), _table(spec), _names(spec["pk"]))
    rows = conn.execute(query, binary=True).fetchall()
    if not rows:
        return None
    sql_types = {c["name"]: c["sql_type"] for c in spec["columns"]}
    by_column = list(zip(*rows))
    return pd.DataFrame({name: _series(list(by_column[i]), sql_types[name], declared[name])
                         for i, name in enumerate(wanted)})


def _python(value, sql_type: str, where: str):
    """One non-null cell as the Python value psycopg dumps for `sql_type`."""
    if sql_type == "integer":
        whole = int(value)
        if whole != value:
            raise WriteRefused(f"{where}: a value is not a whole number")
        return whole
    if sql_type == "double precision":
        return float(value)
    if sql_type == "boolean":
        return bool(value)
    if sql_type in ("timestamp", "timestamptz"):
        return value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
    if sql_type == "date" and hasattr(value, "to_pydatetime"):
        return value.date()
    return value


def _cells(series: pd.Series, sql_type: str, where: str) -> list:
    missing = series.isna().to_numpy()
    values = series.astype(object).tolist()
    return [None if gone else _python(v, sql_type, where) for v, gone in zip(values, missing)]


def _rows(df: pd.DataFrame, spec: dict, columns: list[str]):
    sql_types = {c["name"]: c["sql_type"] for c in spec["columns"]}
    cells = [_cells(df[c], sql_types[c], f"{spec['name']}.{c}") for c in columns]
    return zip(*cells)


def _copy(cur, target, columns: list[str], rows) -> None:
    _, sql = _psycopg()
    with cur.copy(sql.SQL("COPY {} ({}) FROM STDIN").format(target, _names(columns))) as copy:
        for row in rows:
            copy.write_row(row)


def _partition_delete(cur, spec: dict, partition) -> None:
    _, sql = _psycopg()
    sql_types = {c["name"]: c["sql_type"] for c in spec["columns"]}
    parts, params = [], []
    for col, values in partition.items():
        if col not in sql_types:
            raise WriteRefused(f"{spec['name']}: no such column {col!r}")
        parts.append(sql.SQL("{} = ANY(%s::{}[])").format(sql.Identifier(col), sql.SQL(sql_types[col])))
        params.append([_python(v, sql_types[col], f"{spec['name']}.{col}") for v in values])
    cur.execute(sql.SQL("DELETE FROM {} WHERE {}").format(
        _table(spec), sql.SQL(" AND ").join(parts)), params)


def stage(cur, spec: dict, columns: list[str], df: pd.DataFrame):
    """COPY `df` into a temp table shaped like the target and return its name.
    COPY FROM is refused on a table with row-level security, so rows reach the
    target by INSERT ... SELECT from here (insert_staged)."""
    _, sql = _psycopg()
    batch = sql.Identifier(BATCH_TABLE)
    cur.execute(sql.SQL("CREATE TEMP TABLE {} AS SELECT * FROM {} WITH NO DATA")
                .format(batch, _table(spec)))
    _copy(cur, batch, columns, _rows(df, spec, columns))
    return batch


def insert_staged(cur, spec: dict, columns: list[str], batch) -> None:
    """INSERT the staged rows into the target and drop the temp table."""
    _, sql = _psycopg()
    cur.execute(sql.SQL("INSERT INTO {} ({cols}) SELECT {cols} FROM {}").format(
        _table(spec), batch, cols=_names(columns)))
    cur.execute(sql.SQL("DROP TABLE {}").format(batch))


def _keys_delete(cur, spec: dict, columns: list[str], df: pd.DataFrame, keys) -> None:
    _, sql = _psycopg()
    batch = stage(cur, spec, columns, df)
    same = sql.SQL(" AND ").join(
        sql.SQL("t.{0} = b.{0}").format(sql.Identifier(k)) for k in keys)
    cur.execute(sql.SQL("DELETE FROM {} t USING {} b WHERE {}").format(_table(spec), batch, same))
    insert_staged(cur, spec, columns, batch)


def write(entry: dict, df: pd.DataFrame, mode: str, keys, partition) -> int:
    """Apply `mode` in one transaction and return the table's row count after.
    `df` is checked and cast already; `keys` is set for upsert."""
    _, sql = _psycopg()
    spec = _spec(entry)
    columns = _check_columns(entry, spec)
    if keys is not None:
        keys = list(keys)
        missing = [k for k in keys if k not in columns]
        if missing:
            raise WriteRefused(f"{entry['name']}: keys not in the table: {missing}")
    if mode == "upsert":
        df = df.drop_duplicates(subset=keys, keep="last")
    with _db_errors(), _connect() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                if mode == "replace":
                    batch = stage(cur, spec, columns, df)
                    cur.execute(sql.SQL("DELETE FROM {}").format(_table(spec)))
                    insert_staged(cur, spec, columns, batch)
                elif mode == "replace_partition" and partition is not None:
                    batch = stage(cur, spec, columns, df)
                    _partition_delete(cur, spec, partition)
                    insert_staged(cur, spec, columns, batch)
                elif len(df):
                    _keys_delete(cur, spec, columns, df, keys)
                count = cur.execute(sql.SQL("SELECT count(*) FROM {}").format(_table(spec))).fetchone()[0]
    return int(count)


# ---- The backfill: load the published tables, read them back, compare (#135, B3) ----
# Everything below prints and returns counts and names, never a cell. The
# workflow log that runs scripts/backfill_postgres.py is public.
SCHEMA = "football"
LOGIN = "etl_writer"
TEST_URL_ENV = "TEST_DATABASE_URL"
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")


class Loaded(NamedTuple):
    problems: list
    counts: dict
    refused: bool = False


def scrub(text: str) -> str:
    """The first line of `text` with every quoted string removed, and anything
    after a quote mark that never closes: a database or Python error quotes the
    value it choked on."""
    lines = str(text).strip().splitlines()
    line = _QUOTED.sub("<quoted>", lines[0] if lines else "")
    stray = re.search(r"['\"]", line)
    if stray:
        line = line[:stray.start()] + "<quoted>"
    return line[:200]


def describe(exc: BaseException) -> str:
    """An error in words that carry no cell value. A psycopg error is its class,
    SQLSTATE and the table, column and constraint it names (its message and
    DETAIL hold the row); any other is its class and scrubbed first line."""
    psycopg, _ = _psycopg()
    if isinstance(exc, psycopg.Error):
        diag = exc.diag
        parts = [type(exc).__name__]
        if getattr(exc, "sqlstate", None):
            parts.append(f"SQLSTATE {exc.sqlstate}")
        for label, value in (("table", diag.table_name), ("column", diag.column_name),
                             ("constraint", diag.constraint_name)):
            if value:
                parts.append(f"{label} {value}")
        return " ".join(parts)
    return f"{type(exc).__name__}: {scrub(exc)}"


def breaks(conn, spec: dict, batch: pd.DataFrame, columns: list[str]) -> list[str]:
    """Why the database refused `batch`: rows per constraint it breaks, counted
    on an unconstrained copy of the table. Counts only, never a cell."""
    _, sql = _psycopg()
    probe = sql.Identifier("_probe")
    lines = []
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE TEMP TABLE {} AS SELECT * FROM {} WITH NO DATA")
                    .format(probe, _table(spec)))
        _copy(cur, probe, columns, _rows(batch, spec, columns))
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


def orphans(conn) -> list[str]:
    """Rows per foreign key whose parent is missing, for every foreign key in
    the schema, counted with the rows loaded and the keys still deferred."""
    keys = conn.execute(
        "SELECT c.conname, c.conrelid::regclass::text, c.confrelid::regclass::text, "
        "(SELECT array_agg(a.attname ORDER BY k.ord) FROM unnest(c.conkey) WITH ORDINALITY k(n, ord) "
        " JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.n), "
        "(SELECT array_agg(a.attname ORDER BY k.ord) FROM unnest(c.confkey) WITH ORDINALITY k(n, ord) "
        " JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.n) "
        "FROM pg_constraint c WHERE c.contype = 'f' AND c.connamespace = %s::regnamespace "
        "ORDER BY c.conname", (SCHEMA,)).fetchall()
    lines = []
    for name, child, parent, ccols, pcols in keys:
        present = " AND ".join(f'c."{x}" IS NOT NULL' for x in ccols)
        match = " AND ".join(f'p."{y}" = c."{x}"' for x, y in zip(ccols, pcols))
        n = conn.execute(f"SELECT count(*) FROM {child} c WHERE {present} "
                         f"AND NOT EXISTS (SELECT 1 FROM {parent} p WHERE {match})").fetchone()[0]
        if n:
            lines.append(f"FOREIGN KEY {name}: {n} row(s) with no parent")
    return lines


def text_flavour_free(df: pd.DataFrame, entry: dict) -> pd.DataFrame:
    """`df` with each declared text column as object and its gaps as None. The
    seam treats str, string and object as one text type (etl._coerce) and a
    database keeps only text, so a published column that is `string` where the
    registry says `str` (fact_roster_transactions.claim_method,
    fact_trade_log.pick_ref) cannot come back as `string`: the read already
    gives the registry's dtype, and the snapshot is the odd one. Values and
    nulls are still compared exactly."""
    out = df.copy()
    for col in entry["columns"]:
        if str(col["dtype"]) in _TEXT_DTYPES:
            name = col["name"]
            out[name] = out[name].astype(object).where(out[name].notna(), None)
    return out


def prepared(df: pd.DataFrame, entry: dict) -> pd.DataFrame:
    """`df` in the order a Postgres read gives (sorted by the table's key, a
    fresh index) with text flavours folded: the shape two frames are compared in."""
    import etl_helpers as etl
    out = text_flavour_free(df, entry)
    return out.sort_values(etl.table_grain(entry)).reset_index(drop=True)


def _unequal(a: pd.Series, b: pd.Series) -> pd.Series:
    same = (a == b).fillna(False).astype(bool)
    return ~(same | (a.isna() & b.isna()))


def differences(got, published: pd.DataFrame, entry: dict) -> list[str]:
    """How `got` (a read-back, None for no rows) differs from `published`, as
    counts per table or column; [] when they are equal. An empty table is
    compared too: no rows read back against none published is equal."""
    name = entry["name"]
    rows = 0 if got is None else len(got)
    if rows != len(published):
        return [f"{name}: {rows} row(s) read back, {len(published)} published"]
    if not rows:
        return []
    columns = list(published.columns)
    if set(got.columns) != set(columns):
        return [f"{name}: the columns read back differ from the published ones"]
    left, right = prepared(got[columns], entry), prepared(published, entry)
    lines = []
    for col in columns:
        if str(left[col].dtype) != str(right[col].dtype):
            lines.append(f"{name}.{col}: {left[col].dtype} read back, {right[col].dtype} published")
            continue
        n = int(_unequal(left[col], right[col]).sum())
        if n:
            lines.append(f"{name}.{col}: {n} cell(s) differ")
    return lines


def load_published(url: str, frames: dict, *, replace: bool = False, verify: bool = False,
                   empty_only: bool = False) -> Loaded:
    """Load every table of `frames` in one transaction, as the login in `url`.
    The foreign keys are deferred, so the load order does not matter. With
    `verify`, every table is read back inside the transaction and compared
    with its frame before the commit. Returns the problems (counts and names;
    then nothing is committed) and the rows each table holds, counted in the
    database before the commit. `replace` empties each table first and is off
    unless a caller asks for it, since it deletes; without it a table that
    holds rows is a primary-key error. `empty_only` locks the tables and
    refuses, in the same transaction, if any holds a row."""
    import etl_helpers as etl
    psycopg, sql = _psycopg()
    problems, counts, refused = [], {}, False
    with psycopg.connect(url, prepare_threshold=None) as conn:
        with conn.transaction() as tx:
            if empty_only:
                conn.execute("SET LOCAL lock_timeout = '10s'")
                for name in sorted(frames):
                    conn.execute(sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE")
                                 .format(sql.Identifier(SCHEMA, name)))
                conn.execute("SET LOCAL lock_timeout = 0")
                problems.extend(f"{SCHEMA}.{name} already holds rows; this run loads an empty schema "
                                f"(--replace empties each table first)"
                                for name in nonempty(conn, sorted(frames)))
                refused = bool(problems)
                if refused:
                    raise psycopg.Rollback(tx)
            for name, frame in frames.items():
                entry = etl._table_entry(name)
                batch = etl._check_batch(frame, entry)
                spec = _spec(entry)
                columns = _check_columns(entry, spec)
                try:
                    with conn.transaction(), conn.cursor() as cur:
                        staged = stage(cur, spec, columns, batch)
                        if replace:
                            cur.execute(sql.SQL("DELETE FROM {}").format(_table(spec)))
                        insert_staged(cur, spec, columns, staged)
                except psycopg.Error as exc:
                    problems.append(f"{name}: refused: {describe(exc)}")
                    try:
                        problems.extend(breaks(conn, spec, batch, columns))
                    except psycopg.Error as again:
                        problems.append(f"{name}: no count: {describe(again)}")
            if not problems:
                problems.extend(orphans(conn))
            if not problems:
                conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
                counts = {name: conn.execute(sql.SQL("SELECT count(*) FROM {}")
                                             .format(sql.Identifier(SCHEMA, name))).fetchone()[0]
                          for name in frames}
            if verify and not problems:
                for name, frame in frames.items():
                    entry = etl._table_entry(name)
                    got = read_on(conn, entry)
                    if got is not None:
                        got = etl._coerce(got, entry)
                    problems.extend(differences(got, frame, entry))
            if problems:
                raise psycopg.Rollback(tx)
    return Loaded(problems, counts, refused)


def reload_snapshot(url: str, names, data_dir) -> Loaded:
    """Reload the `names` tables from the snapshot in `data_dir`, replacing
    what they hold, in one transaction (`load_published`): a refusal leaves
    every table as it was. A table with no file in `data_dir` is emptied."""
    import etl_helpers as etl
    frames = {}
    for name in names:
        try:
            frames[name] = etl.read_stored(name, data_dir)
        except etl.TableNotFound:
            frames[name] = etl.empty_frame(etl._table_entry(name))
    return load_published(url, frames, replace=True)


def like_snapshot(df: pd.DataFrame, snapshot: pd.DataFrame) -> pd.DataFrame:
    """`df` in the snapshot's column order, and with its text flavour where the
    snapshot's differs (a published `string` column the registry calls `str`)."""
    missing = [c for c in snapshot.columns if c not in df.columns]
    extra = [c for c in df.columns if c not in snapshot.columns]
    if missing or extra:
        raise ValueError(f"columns differ from the snapshot: missing {missing}, extra {extra}")
    return _snapshot_flavour(df[list(snapshot.columns)].copy(), snapshot)


def _snapshot_flavour(out: pd.DataFrame, snapshot: pd.DataFrame) -> pd.DataFrame:
    for col in out.columns:
        if col not in snapshot.columns:
            continue
        was, want = str(out[col].dtype), str(snapshot[col].dtype)
        if was != want and was in _TEXT_DTYPES and want in _TEXT_DTYPES:
            out[col] = out[col].astype(snapshot[col].dtype)
    return out


def frame_drift(df: pd.DataFrame, entry: dict) -> None:
    """Raise ValueError, naming columns only, unless `df` holds exactly the
    columns the registry declares for the table. The frame comes from the
    database through `read_on`, which has already refused unless the registry
    and registry_state.json agree; this is the explicit check that what is
    about to be written is the registry's shape, so a snapshot behind the
    registry is the one thing an export may follow (`follow_registry`)."""
    declared = [c["name"] for c in entry["columns"]]
    missing = [c for c in declared if c not in df.columns]
    extra = [c for c in df.columns if c not in declared]
    if missing or extra or len(df.columns) != len(declared):
        raise ValueError(f"{entry['name']}: columns differ from the registry: "
                         f"missing {missing}, extra {extra}")


def follow_registry(df: pd.DataFrame, snapshot: pd.DataFrame):
    """`df` (already the registry's columns) for a snapshot that is behind the
    registry: the snapshot's columns that remain, in its order, then the added
    ones, in `df` order, with the snapshot's text flavour where it differs.
    Returns the frame, the added column names and the dropped ones. A rename
    is one dropped name and one added name: the registry marks none."""
    added = [c for c in df.columns if c not in snapshot.columns]
    dropped = [c for c in snapshot.columns if c not in df.columns]
    kept = [c for c in snapshot.columns if c in df.columns]
    return _snapshot_flavour(df[kept + added].copy(), snapshot), added, dropped


def export_published(names, data_dir, changes=None) -> dict:
    """Write `<data_dir>/<name>.parquet` for each of `names` from the database
    and return the rows written per table. Rows are sorted by the table's
    primary key (Q1 of #135); columns and dtypes follow the snapshot already
    in `data_dir`, if any. Every table is read before any file is written.
    A frame that is not the registry's columns raises (`frame_drift`). A
    snapshot whose columns differ from the registry's is behind an intended
    change (#355): it is written in the registry's shape, and if `changes` is
    a dict, `changes[name] = {"added": [...], "dropped": [...]}` is set once
    every file is written, column names only."""
    import etl_helpers as etl
    data_dir = Path(data_dir)
    frames, found = {}, {}
    with _db_errors(), _connect() as conn:
        for name in names:
            entry = etl._table_entry(name)
            got = read_on(conn, entry)
            df = etl.empty_frame(entry) if got is None else etl._coerce(got, entry)
            df = df.sort_values(etl.table_grain(entry), kind="stable").reset_index(drop=True)
            frame_drift(df, entry)
            try:
                snapshot = etl.read_stored(name, data_dir)
            except etl.TableNotFound:
                snapshot = None
            if snapshot is not None:
                if set(snapshot.columns) == set(df.columns):
                    df = like_snapshot(df, snapshot)
                else:
                    df, added, dropped = follow_registry(df, snapshot)
                    found[name] = {"added": added, "dropped": dropped}
            frames[name] = (entry, df)
    written = {name: len(etl._write_parquet(data_dir / f"{name}.parquet", df, "replace", None, None, entry))
               for name, (entry, df) in frames.items()}
    if changes is not None:
        changes.update(found)
    return written


def clear_published(url: str, names) -> None:
    """Empty the `names` tables of the football schema. Runs only against the
    database in TEST_DATABASE_URL, whatever else a caller holds."""
    allowed = os.environ.get(TEST_URL_ENV)
    if not allowed or url != allowed:
        raise RuntimeError(f"clear_published runs only against {TEST_URL_ENV}")
    psycopg, sql = _psycopg()
    with psycopg.connect(url, prepare_threshold=None) as conn:
        for name in names:
            conn.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(SCHEMA, name)))


def login_facts(conn) -> dict:
    """Who the connection is, and which football tables have row-level security."""
    user, bypass, superuser = conn.execute(
        "SELECT current_user, r.rolbypassrls, r.rolsuper FROM pg_roles r "
        "WHERE r.rolname = current_user").fetchone()
    rls = dict(conn.execute(
        "SELECT c.relname, c.relrowsecurity FROM pg_class c "
        "WHERE c.relnamespace = %s::regnamespace AND c.relkind IN ('r', 'p')", (SCHEMA,)).fetchall())
    return {"user": user, "bypass_rls": bool(bypass), "superuser": bool(superuser), "rls": rls}


def login_problems(facts: dict, tables) -> list[str]:
    """What is wrong with the login for a load of `tables`: it must be etl_writer
    (ADR-0018 decision 9), without BYPASSRLS or superuser, and row-level security
    must be on for every football table. FORCE ROW LEVEL SECURITY and table
    ownership are not checked: ADR-0018 decision 9 gives etl_writer an explicit
    USING (true) policy per table, so RLS filters nothing for this login whether
    it owns a table or not, and BYPASSRLS, which is checked, is the only way
    past a policy that would matter."""
    problems = []
    if facts["user"] != LOGIN:
        problems.append(f"connected as {facts['user']}, expected {LOGIN}")
    if facts["bypass_rls"]:
        problems.append("the login has BYPASSRLS")
    if facts["superuser"]:
        problems.append("the login is a superuser")
    for name in sorted(set(facts["rls"]) | set(tables)):
        if name not in facts["rls"]:
            problems.append(f"{SCHEMA}.{name}: no such table")
        elif not facts["rls"][name]:
            problems.append(f"{SCHEMA}.{name}: row-level security is off")
    return problems


def nonempty(conn, tables) -> list[str]:
    """The football tables among `tables` that hold at least one row."""
    _, sql = _psycopg()
    return [name for name in tables
            if conn.execute(sql.SQL("SELECT EXISTS (SELECT 1 FROM {})")
                            .format(sql.Identifier(SCHEMA, name))).fetchone()[0]]
