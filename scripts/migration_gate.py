"""Hold a destructive migration for the owner's dispatch (#534, ADR-0018 decision 12).

    migration_gate.py --applied FILE [--migrations DIR] [--remove]

`migrate.yml` runs this on a push to main, before `supabase db push`. FILE
holds the versions the project has applied, one per line (from
`supabase_migrations.schema_migrations`). The first pending migration with a
destructive statement is held, with every pending migration after it, so the
ones before it apply and the rest wait for the owner to run the workflow by
`workflow_dispatch`. With `--remove` the held files are deleted from DIR,
which on the runner is a throwaway checkout. Prints `held=<file>`, or `held=`
when nothing is held, for `$GITHUB_OUTPUT`. Standard library only: the push
job installs nothing.

The gate guards every migration, not only the generator's (planner ruling on
PR #536). Comments are stripped and the file is split into statements on `;`,
both outside quotes. A statement is destructive when it holds, anywhere and
in any case: DROP (any form), TRUNCATE, DELETE FROM, MERGE, UPDATE ... SET,
RENAME, ALTER [COLUMN] ... [SET DATA] TYPE, ALTER TYPE, DETACH PARTITION or
SET SCHEMA. A file with a single-quoted string holding a backslash is held
too. GRANT and REVOKE are not held. The one exemption is the generator's check widening (#443): an
`ALTER TABLE t DROP CONSTRAINT t_chk_<8 hex>` statement directly followed by
an `ALTER TABLE t ADD CONSTRAINT t_chk_<8 hex> CHECK (...)` statement on the
same table. A key, foreign key or unique constraint dropped is held. A false
hold costs a dispatch; a false pass loses data.
"""
import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MIGRATIONS = REPO / "supabase" / "migrations"

_NAME = r'(?:"(?:[^"]|"")*"|[^\s;(),]+)'
DESTRUCTIVE = [
    re.compile(r"\bDROP\b", re.IGNORECASE),
    re.compile(r"\bTRUNCATE\b", re.IGNORECASE),
    re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
    re.compile(r"\bRENAME\b", re.IGNORECASE),
    re.compile(rf"\bALTER\s+(?:COLUMN\s+)?{_NAME}\s+(?:SET\s+DATA\s+)?TYPE\b", re.IGNORECASE),
    re.compile(r"\bALTER\s+TYPE\b", re.IGNORECASE),
    re.compile(r"\bMERGE\b", re.IGNORECASE),
    re.compile(rf"\bUPDATE(?:\s+|(?=\"))(?:ONLY(?:\s+|(?=\")))?{_NAME}\s*\*?\s*"
               rf"(?:(?:AS(?:\s+|(?=\")))?{_NAME}\s*)?\bSET\b", re.IGNORECASE),
    re.compile(r"\bDETACH\s+PARTITION\b", re.IGNORECASE),
    re.compile(r"\bSET\s+SCHEMA\b", re.IGNORECASE),
]
_WIDEN_DROP = re.compile(rf"ALTER\s+TABLE\s+({_NAME})\s+DROP\s+CONSTRAINT\s+({_NAME})", re.IGNORECASE)
_WIDEN_ADD = re.compile(rf"ALTER\s+TABLE\s+({_NAME})\s+ADD\s+CONSTRAINT\s+({_NAME})\s+CHECK\s*\(.*\)",
                        re.IGNORECASE | re.DOTALL)


def _is_check_name(table, name):
    """True when `name` is a generator check name for `table`: `<table>_chk_<8 hex>`."""
    bare = table.lower().rsplit(".", 1)[-1]
    return re.fullmatch(rf"{re.escape(bare)}_chk_[0-9a-f]{{8}}", name.lower()) is not None


def _widening_pair(drop_stmt, add_stmt):
    """The #443 pair (planner ruling on PR #536): a generator check dropped and a
    generator check added on the same table. Any other constraint is held."""
    drop, add = _WIDEN_DROP.fullmatch(drop_stmt), _WIDEN_ADD.fullmatch(add_stmt)
    if not drop or not add or drop.group(1).lower() != add.group(1).lower():
        return False
    table = drop.group(1)
    return (_is_check_name(table, drop.group(2)) and _is_check_name(table, add.group(2))
            and not _hits(add_stmt))
_DOLLAR = re.compile(r"\$[A-Za-z0-9_]*\$")


AMBIGUOUS = "a quoted string holding a backslash"


def statements(sql):
    """The statements of `sql`, comments stripped and whitespace collapsed.
    Quotes, quoted names and dollar-quoted bodies are kept whole."""
    return _scan(sql)[0]


def _scan(sql):
    """(statements, ambiguous). An E'...' string honours backslash escapes, as
    Postgres does. Any single-quoted string holding a backslash makes the
    file ambiguous, since how Postgres reads it depends on its settings and
    prefix (#536 re-check B2): the gate then holds the file."""
    out, buf, i, n, ambiguous = [], [], 0, len(sql), False
    while i < n:
        ch = sql[i]
        if sql.startswith("--", i):
            end = sql.find("\n", i)
            i = n if end < 0 else end
            buf.append(" ")
        elif sql.startswith("/*", i):
            depth, i = 1, i + 2
            while i < n and depth:
                if sql.startswith("/*", i):
                    depth, i = depth + 1, i + 2
                elif sql.startswith("*/", i):
                    depth, i = depth - 1, i + 2
                else:
                    i += 1
            buf.append(" ")
        elif ch in "'\"":
            escapes = ch == "'" and i > 0 and sql[i - 1] in "eE" and (
                i < 2 or not (sql[i - 2].isalnum() or sql[i - 2] in "_$"))
            end = i + 1
            while end < n:
                if ch == "'" and sql[end] == "\\":
                    ambiguous = True
                    if escapes:
                        end += 2
                        continue
                if sql[end] == ch:
                    if end + 1 < n and sql[end + 1] == ch:
                        end += 2
                        continue
                    break
                end += 1
            buf.append(sql[i:end + 1])
            i = end + 1
        elif ch == "$" and _DOLLAR.match(sql, i):
            tag = _DOLLAR.match(sql, i).group(0)
            end = sql.find(tag, i + len(tag))
            end = n if end < 0 else end + len(tag)
            buf.append(sql[i:end])
            i = end
        elif ch == ";":
            out.append("".join(buf))
            buf, i = [], i + 1
        else:
            buf.append(ch)
            i += 1
    out.append("".join(buf))
    return [s for s in (" ".join(part.split()) for part in out) if s], ambiguous


def _hits(stmt):
    return any(p.search(stmt) for p in DESTRUCTIVE)


def destructive(sql):
    """The destructive statements of `sql`, past the #443 widening pair, and
    AMBIGUOUS first when a quoted string holds a backslash."""
    stmts, ambiguous = _scan(sql)
    exempt = set()
    for i in range(len(stmts) - 1):
        if _widening_pair(stmts[i], stmts[i + 1]):
            exempt.add(i)
    found = [s for i, s in enumerate(stmts) if i not in exempt and _hits(s)]
    return ([AMBIGUOUS] if ambiguous else []) + found


def is_destructive(sql):
    return bool(destructive(sql))


def version(path):
    return Path(path).name.split("_", 1)[0]


def held(paths, applied):
    """The pending files from the first destructive pending one on, in order."""
    pending = [p for p in sorted(paths, key=lambda p: Path(p).name) if version(p) not in applied]
    for i, path in enumerate(pending):
        if is_destructive(Path(path).read_text(encoding="utf-8")):
            return pending[i:]
    return []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--applied", required=True)
    parser.add_argument("--migrations", default=str(MIGRATIONS))
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args(argv)
    applied = {line.strip() for line in Path(args.applied).read_text(encoding="utf-8").splitlines()
               if line.strip()}
    hold = held(Path(args.migrations).glob("*.sql"), applied)
    for path in hold:
        print(f"migration_gate: held for the owner's dispatch: {Path(path).name}", file=sys.stderr)
        if args.remove:
            Path(path).unlink()
    print(f"held={Path(hold[0]).name if hold else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
