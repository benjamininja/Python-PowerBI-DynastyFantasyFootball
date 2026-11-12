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
in any case, DROP (any form), TRUNCATE, DELETE FROM, RENAME, or an ALTER of a
column's type. The one exemption is the generator's check widening (#443): an
`ALTER TABLE t DROP CONSTRAINT a` statement directly followed by an
`ALTER TABLE t ADD CONSTRAINT b CHECK (...)` statement on the same table. A
false hold costs a dispatch; a false pass loses data.
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
]
_WIDEN_DROP = re.compile(rf"ALTER\s+TABLE\s+({_NAME})\s+DROP\s+CONSTRAINT\s+{_NAME}", re.IGNORECASE)
_WIDEN_ADD = re.compile(rf"ALTER\s+TABLE\s+({_NAME})\s+ADD\s+CONSTRAINT\s+{_NAME}\s+CHECK\s*\(.*\)",
                        re.IGNORECASE | re.DOTALL)
_DOLLAR = re.compile(r"\$[A-Za-z_]*\$")


def statements(sql):
    """The statements of `sql`, comments stripped and whitespace collapsed.
    Quotes, quoted names and dollar-quoted bodies are kept whole."""
    out, buf, i, n = [], [], 0, len(sql)
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
            end = i + 1
            while end < n:
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
    return [s for s in (" ".join(part.split()) for part in out) if s]


def _hits(stmt):
    return any(p.search(stmt) for p in DESTRUCTIVE)


def destructive(sql):
    """The destructive statements of `sql`, past the #443 widening pair."""
    stmts = statements(sql)
    exempt = set()
    for i in range(len(stmts) - 1):
        drop, add = _WIDEN_DROP.fullmatch(stmts[i]), _WIDEN_ADD.fullmatch(stmts[i + 1])
        if drop and add and drop.group(1).lower() == add.group(1).lower() and not _hits(stmts[i + 1]):
            exempt.add(i)
    return [s for i, s in enumerate(stmts) if i not in exempt and _hits(s)]


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
