"""Compare published tables: the working tree against HEAD, or two folders.

    compare_tables.py HEAD          data/*.parquet against `git show HEAD:<file>`
    compare_tables.py <dir> <dir>   every *.parquet in the two folders

Per table one line: `identical` (same bytes), `equal` (same frame, other
bytes) or `DIFFERS` with counts only. No cell value and no column name is
printed. Exit code 0 when every table is identical or equal, 1 otherwise.
"""
import argparse
import io
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

REPO = Path(__file__).resolve().parent.parent
IDENTICAL, EQUAL, DIFFERS = "identical", "equal", "DIFFERS"


def _frame(raw: bytes) -> pd.DataFrame:
    return pq.read_table(io.BytesIO(raw)).to_pandas()


def _same(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a == b) | (a.isna() & b.isna())


def compare_bytes(left, right) -> tuple[str, str]:
    """(status, detail) for one table. `left` / `right` are parquet bytes, or
    None when the table is absent on that side."""
    if left is None or right is None:
        return DIFFERS, "missing on the " + ("left" if left is None else "right")
    if left == right:
        return IDENTICAL, ""
    a, b = _frame(left), _frame(right)
    only_a, only_b = set(a.columns) - set(b.columns), set(b.columns) - set(a.columns)
    common = [c for c in a.columns if c in b.columns]
    notes = []
    if only_a or only_b:
        notes.append(f"columns only left {len(only_a)}, only right {len(only_b)}")
    retyped = [c for c in common if str(a[c].dtype) != str(b[c].dtype)]
    if retyped:
        notes.append(f"columns with a different dtype {len(retyped)}")
    if len(a) != len(b):
        notes.append(f"rows left {len(a)}, right {len(b)}")
    elif common:
        a, b = a.reset_index(drop=True), b.reset_index(drop=True)
        cells = sum(int((~_same(a[c], b[c])).sum()) for c in common)
        if cells:
            notes.append(f"cells differing {cells}")
        if list(a[common].columns) != [c for c in b.columns if c in a.columns]:
            notes.append("column order differs")
    if notes:
        return DIFFERS, "; ".join(notes)
    return EQUAL, ""


def _git(*args) -> bytes:
    return subprocess.run(["git", *args], cwd=REPO, check=True,
                          capture_output=True).stdout


def head_sources(data_dir: Path):
    """(names, read_left, read_right): the working tree's tables against HEAD's."""
    in_head = {Path(p).name for p in _git("ls-tree", "--name-only", "HEAD", "data/")
               .decode().split() if p.endswith(".parquet")}
    names = sorted(in_head | {p.name for p in data_dir.glob("*.parquet")})

    def left(name):
        path = data_dir / name
        return path.read_bytes() if path.exists() else None

    def right(name):
        if name not in in_head:
            return None
        return _git("show", f"HEAD:data/{name}")

    return names, left, right


def dir_sources(left_dir: Path, right_dir: Path):
    names = sorted({p.name for d in (left_dir, right_dir) for p in d.glob("*.parquet")})

    def reader(folder):
        return lambda name: (folder / name).read_bytes() if (folder / name).exists() else None

    return names, reader(left_dir), reader(right_dir)


def run(args: list[str], data_dir: Path = REPO / "data", out=sys.stdout) -> int:
    if len(args) == 1 and args[0] == "HEAD":
        names, left, right = head_sources(data_dir)
    elif len(args) == 2:
        names, left, right = dir_sources(Path(args[0]), Path(args[1]))
    else:
        print("usage: compare_tables.py HEAD | compare_tables.py <dir> <dir>", file=sys.stderr)
        return 2
    counts = {IDENTICAL: 0, EQUAL: 0, DIFFERS: 0}
    for name in names:
        status, detail = compare_bytes(left(name), right(name))
        counts[status] += 1
        print(f"{status:9s} {name}" + (f"  ({detail})" if detail else ""), file=out)
    print(f"tables {len(names)}: identical {counts[IDENTICAL]}, equal {counts[EQUAL]}, "
          f"differing {counts[DIFFERS]}", file=out)
    return 1 if counts[DIFFERS] or not names else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("where", nargs="+", metavar="HEAD | DIR DIR")
    return run(parser.parse_args(argv).where)


if __name__ == "__main__":
    sys.exit(main())
