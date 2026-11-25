import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))

import psycopg
from psycopg import sql

import backfill_postgres as backfill
import etl_storage_pg as pg

url = os.environ["TEST_DATABASE_URL"]
frames = backfill.published_frames()
names = sorted(frames)
print("tables", len(names), "rows", sum(len(f) for f in frames.values()), flush=True)

with psycopg.connect(url) as conn:
    unindexed = conn.execute(
        "SELECT c.conrelid::regclass::text, a.attname FROM pg_constraint c "
        "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1] "
        "WHERE c.contype = 'f' AND c.connamespace = 'football'::regnamespace "
        "AND NOT EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1]) "
        "ORDER BY 1, 2").fetchall()
    print("fk columns with no leading index:", len(unindexed))
    for row in unindexed:
        print("  ", row)
    fks = conn.execute(
        "SELECT conrelid::regclass::text, confrelid::regclass::text FROM pg_constraint "
        "WHERE contype = 'f' AND connamespace = 'football'::regnamespace").fetchall()
print("fks", len(fks), flush=True)

t = time.time()
loaded = pg.load_published(url, frames, replace=True)
print(f"load {time.time() - t:.1f}s problems={len(loaded.problems)}", flush=True)

t = time.time()
with psycopg.connect(url, prepare_threshold=None) as conn:
    for name in names:
        s = time.time()
        conn.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier("football", name)))
        d = time.time() - s
        if d > 0.3:
            print(f"  A delete {name} {d:.2f}s", flush=True)
    s = time.time()
    conn.commit()
    print(f"A commit {time.time() - s:.1f}s", flush=True)
print(f"A one transaction, alphabetical: {time.time() - t:.1f}s", flush=True)

t = time.time()
loaded = pg.load_published(url, frames, replace=True)
print(f"reload {time.time() - t:.1f}s", flush=True)

pairs = [(c.split(".")[-1], p.split(".")[-1]) for c, p in fks]
order, left = [], set(names)
while left:
    ready = sorted(n for n in left if not any(p == n and c in left and c != n for c, p in pairs))
    if not ready:
        ready = sorted(left)
    order += ready
    left -= set(ready)
t = time.time()
with psycopg.connect(url, prepare_threshold=None) as conn:
    for name in order:
        s = time.time()
        conn.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier("football", name)))
        d = time.time() - s
        if d > 0.3:
            print(f"  B delete {name} {d:.2f}s", flush=True)
    s = time.time()
    conn.commit()
    print(f"B commit {time.time() - s:.1f}s", flush=True)
print(f"B one transaction, children first: {time.time() - t:.1f}s", flush=True)
