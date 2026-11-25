"""Fail when a new migration sorts at or before the newest migration on the base ref.

Reads git and the migrations folder only; it never reaches a database.

    python scripts/check_migration_order.py [--base origin/main] [--repo .]
"""

import argparse
import subprocess
import sys
from pathlib import Path

MIGRATIONS = "supabase/migrations"
REPO_ROOT = Path(__file__).resolve().parent.parent


def base_files(repo: Path, base: str) -> set[str]:
    out = subprocess.run(
        ["git", "ls-tree", "--name-only", f"{base}:{MIGRATIONS}/"],
        cwd=repo, capture_output=True, text=True,
    )
    if out.returncode != 0:
        if "not a valid object name" in out.stderr or "Not a valid object name" in out.stderr:
            check_ref = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}"],
                cwd=repo, capture_output=True, text=True,
            )
            if check_ref.returncode == 0:
                return set()
        raise SystemExit(f"cannot read {MIGRATIONS} on {base}: {out.stderr.strip()}")
    return {n for n in out.stdout.splitlines() if n.endswith(".sql")}


def tree_files(repo: Path) -> set[str]:
    folder = repo / MIGRATIONS
    if not folder.is_dir():
        return set()
    return {p.name for p in folder.glob("*.sql")}


def out_of_order(base: set[str], tree: set[str]) -> list[str]:
    if not base:
        return []
    newest = max(base)
    return sorted(f for f in tree - base if f <= newest)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--repo", type=Path, default=REPO_ROOT)
    args = ap.parse_args(argv)

    base = base_files(args.repo, args.base)
    bad = out_of_order(base, tree_files(args.repo))
    if not bad:
        print(f"migration order OK against {args.base}")
        return 0
    newest = max(base)
    for name in bad:
        print(f"{MIGRATIONS}/{name} sorts at or before {newest}, the newest on {args.base}")
    print("Regenerate the migration so its stamp is after the newest on the base; never rename by hand.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
