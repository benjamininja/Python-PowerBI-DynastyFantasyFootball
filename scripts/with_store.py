"""Run one command with the store's two settings in its environment (#615).

    .venv\\Scripts\\python.exe scripts\\with_store.py [--env-file F] -- COMMAND [ARGS...]

run.ps1 -Store calls this. ETL_STORAGE and SUPABASE_DB_URL come from the
environment, else from the repo's .env (the parser run_pipeline uses), and
go into the environment of COMMAND alone. This process's own environment is
not changed, and no value is printed. It stops, naming only the settings, when
ETL_STORAGE does not resolve to postgres or the URL is missing.

The seam in etl_helpers reads the environment and never a file, so a test, the
keep loader or any other import of it cannot pick the store up from .env: only
a person who types -Store reaches it.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import etl_run_log  # noqa: E402

STORAGE_ENV = "ETL_STORAGE"
URL_ENV = etl_run_log.URL_ENV


class StoreNotSet(Exception):
    pass


def store_env(env_file: Path | None = None, environ=None) -> dict:
    """`environ` (default: the process environment) plus the two store settings,
    each from `environ` first, else from the .env file. Raises StoreNotSet,
    naming the setting only, when the pair is not a Postgres one."""
    base = dict(os.environ if environ is None else environ)
    path = REPO / ".env" if env_file is None else env_file
    for key in (STORAGE_ENV, URL_ENV):
        if not base.get(key):
            value = etl_run_log.env_value(key, path)
            if value:
                base[key] = value
    if base.get(STORAGE_ENV) != "postgres":
        raise StoreNotSet(f"{STORAGE_ENV} is not postgres in the environment or in .env")
    if not base.get(URL_ENV):
        raise StoreNotSet(f"{URL_ENV} is not set in the environment or in .env")
    return base


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--env-file", type=Path, default=None, help="a dotenv file other than the repo's .env")
    ap.add_argument("command", nargs=argparse.REMAINDER, help="after --, the command to run")
    args = ap.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        print("with_store: no command given; nothing was run")
        return 2
    try:
        env = store_env(args.env_file)
    except StoreNotSet as exc:
        print(f"with_store: {exc}; nothing was run")
        return 2
    try:
        return subprocess.run(command, env=env).returncode
    except OSError as exc:
        print(f"with_store: could not start the command ({type(exc).__name__}); nothing was run")
        return 2


if __name__ == "__main__":
    sys.exit(main())
