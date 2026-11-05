import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from etl_storage_pg import URL_ENV

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
TRIGGERS = ("daily", "poll", "weekly", "manual")
CONNECT_TIMEOUT_S = 10
STATEMENT_TIMEOUT_MS = 10000
LINE_LIMIT = 200
PAUSED_HINT = "The Supabase project may be paused; resume it from the dashboard."

INSERT = ("INSERT INTO ops.etl_run_log (run_id, trigger, started_at, status, git_sha) "
          "VALUES (%s, %s, %s, 'running', %s)")
UPDATE = ("UPDATE ops.etl_run_log SET finished_at = %s, status = %s, "
          "snapshot_commit_sha = %s, rows_written = %s::jsonb, error = %s WHERE run_id = %s")


def database_url() -> str | None:
    url = os.environ.get(URL_ENV)
    if url:
        return url
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    for line in lines:
        if line.strip().startswith(f"{URL_ENV}="):
            return line.split("=", 1)[1].strip().strip("\"'") or None
    return None


def enabled() -> bool:
    return database_url() is not None


def _connect():
    import psycopg
    return psycopg.connect(database_url(), connect_timeout=CONNECT_TIMEOUT_S,
                           prepare_threshold=None)


def _write(sql: str, params: tuple) -> None:
    with _connect() as conn:
        conn.execute(f"SET LOCAL statement_timeout = {int(STATEMENT_TIMEOUT_MS)}")
        conn.execute(sql, params)


def _secrets() -> list[str]:
    url = database_url() or ""
    found = [url]
    try:
        parts = urlsplit(url)
        for piece in (parts.password, parts.username):
            if piece:
                found += [piece, unquote(piece)]
    except ValueError:
        pass
    return sorted({s for s in found if s}, key=len, reverse=True)


def first_line(exc: BaseException) -> str:
    text = str(exc).strip()
    line = text.splitlines()[0].strip() if text else ""
    for secret in _secrets():
        line = line.replace(secret, "***")
    return (line or type(exc).__name__)[:LINE_LIMIT]


def head_sha(repo: Path) -> str | None:
    try:
        done = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or None if done.returncode == 0 else None


def data_committed(commit_line: str) -> bool:
    return commit_line.startswith("committed")


def data_pushed(commit_line: str) -> bool:
    return commit_line.startswith("committed + pushed")


def final_status(code: int, commit_line: str) -> str:
    if code:
        return "failed"
    return "published" if data_pushed(commit_line) else "committed"


def failure_summary(results: list[dict], plan: dict | None, commit_line: str) -> str:
    parts = [f"step {r['name']} {r['status']}" for r in results
             if r["status"] not in ("ok", "dry-run")]
    for chain, reasons in (plan or {}).get("failed", {}).items():
        parts.append(f"Chain {chain} held")
        parts += [r.split(":", 1)[0] for r in reasons if not r.startswith("step ")]
    if commit_line.startswith("ABORTED"):
        parts.append(":".join(commit_line.split(":")[:2]))
    return ("; ".join(parts) or "run exited non-zero")[:LINE_LIMIT * 2]


def row_counts(tables: list[str]) -> dict[str, int]:
    import etl_helpers as etl
    counts = {}
    for table in tables:
        try:
            counts[table] = int(len(etl.read_table(table)))
        except Exception:
            counts[table] = -1
    return counts


class RunLog:
    def __init__(self, trigger: str):
        self.trigger = trigger
        self.run_id: str | None = None
        self.warning: str | None = None

    def _failed(self, exc: BaseException) -> None:
        self.warning = f"⚠️ run log not written: {first_line(exc)}. {PAUSED_HINT}"
        print(f"[warn] {self.warning}")

    def start(self, git_sha: str | None) -> None:
        if not enabled():
            print(f"[info] {URL_ENV} not set - run log skipped")
            return
        run_id = str(uuid.uuid4())
        try:
            _write(INSERT, (run_id, self.trigger, datetime.now(timezone.utc), git_sha))
        except Exception as exc:
            self._failed(exc)
            return
        self.run_id = run_id
        print(f"[info] run log: {run_id} running")

    def finish(self, status: str, snapshot_commit_sha: str | None = None,
               rows_written: dict | None = None, error: str | None = None) -> None:
        if self.run_id is None:
            return
        rows = None if rows_written is None else json.dumps(rows_written)
        try:
            _write(UPDATE, (datetime.now(timezone.utc), status, snapshot_commit_sha,
                            rows, error, self.run_id))
        except Exception as exc:
            self._failed(exc)
            return
        print(f"[info] run log: {self.run_id} {status}")
