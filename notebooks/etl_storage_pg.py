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
from pathlib import Path

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
    with _db_errors(), _connect() as conn:
        rows = conn.execute(query).fetchall()
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
            raise WriteRefused(f"{where}: {value!r} is not a whole number")
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
