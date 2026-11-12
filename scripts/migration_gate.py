"""Hold a destructive migration for the owner's dispatch (#534, ADR-0018 decision 12).

    migration_gate.py --applied FILE [--migrations DIR] [--remove]

`migrate.yml` runs this on a push to main, before `supabase db push`. FILE
holds the versions the project has applied, one per line (from
`supabase_migrations.schema_migrations`). The first pending migration that
holds DROP COLUMN or DROP TABLE is held, with every pending migration after
it, so the ones before it apply and the rest wait for the owner to run the
workflow by `workflow_dispatch`. With `--remove` the held files are deleted
from DIR, which on the runner is a throwaway checkout. Prints `held=<file>`,
or `held=` when nothing is held, for `$GITHUB_OUTPUT`. Standard library only:
the push job installs nothing.
"""
import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MIGRATIONS = REPO / "supabase" / "migrations"
DESTRUCTIVE = re.compile(r"^\s*(ALTER\s+TABLE\s+\S+\s+DROP\s+COLUMN|DROP\s+TABLE)\b",
                         re.IGNORECASE | re.MULTILINE)


def version(path):
    return Path(path).name.split("_", 1)[0]


def is_destructive(sql):
    return DESTRUCTIVE.search(sql) is not None


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
