"""Re-proof a PR: the project's Green list, run on the merged tree.

Usage: reproof.py PR [HEAD]

Fetches nothing: run `git fetch origin` first so origin/main and the PR's head
commit are local. HEAD is the PR's head sha (40 lowercase hex); if omitted it
is read with `gh pr view PR --json headRefOid`. The merged tree of origin/main
and HEAD is exported to a temp folder outside the repo and the steps run
there. Never pushes, merges, comments or writes in the repo it runs from.
Exit 0 only when every step passes.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parent.parent
SHA_RE = re.compile(r"[0-9a-f]{40}")

STEP_NAMES = ("pytest", "pii", "data_model", "data_model --check",
              "sources --check", "check-only", "review findings")


@dataclass
class Ctx:
    pr: str
    sha: str
    tmp: Path
    export: Path
    repo: Path = REPO


def valid_sha(sha: str) -> bool:
    return bool(SHA_RE.fullmatch(sha))


def sh(cmd: list[str], cwd: Path) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def tail(text: str, n: int) -> str:
    return "\n".join(text.strip().splitlines()[-n:])


def py_step(ctx: Ctx, args: list[str], keep: int = 2,
            log: Path | None = None) -> tuple[bool, str]:
    rc, out = sh([sys.executable, *args], ctx.export)
    if log is not None:
        log.write_text(out, encoding="utf-8")
    return rc == 0, tail(out, keep)


def step_pytest(ctx: Ctx) -> tuple[bool, str]:
    return py_step(ctx, ["-m", "pytest", "tests/", "-q", "-rf"], 2,
                   ctx.tmp / "pytest.log")


def step_pii(ctx: Ctx) -> tuple[bool, str]:
    rc, out = sh(["gh", "pr", "diff", ctx.pr, "--name-only"], ctx.repo)
    if rc != 0:
        return False, "gh pr diff failed: " + tail(out, 2)
    files = [f for f in out.split() if (ctx.export / f).is_file()]
    if not files:
        return True, "no changed files in the merged tree"
    return py_step(ctx, ["scripts/check_pii.py", *files])


def step_data_model(ctx: Ctx) -> tuple[bool, str]:
    return py_step(ctx, ["scripts/check_data_model.py"], 1)


def step_data_model_check(ctx: Ctx) -> tuple[bool, str]:
    return py_step(ctx, ["scripts/check_data_model.py", "--check"], 1)


def step_sources(ctx: Ctx) -> tuple[bool, str]:
    return py_step(ctx, ["scripts/check_sources.py", "--check"], 3)


def step_check_only(ctx: Ctx) -> tuple[bool, str]:
    return py_step(ctx, ["scripts/run_pipeline.py", "--check-only"], 2)


def step_review_findings(ctx: Ctx) -> tuple[bool, str]:
    path = ctx.export / "data" / "review" / "review_check.csv"
    if not path.is_file():
        return True, "no review_check.csv written"
    rows = [ln for ln in path.read_text(encoding="utf-8").splitlines()[1:] if ln.strip()]
    shown = ["  " + ",".join(r.split(",")[:3]) for r in rows]
    return True, "\n".join([f"{len(rows)} review finding(s), listed for the reader"] + shown)


STEP_FUNCS: dict[str, Callable[[Ctx], tuple[bool, str]]] = {
    "pytest": step_pytest,
    "pii": step_pii,
    "data_model": step_data_model,
    "data_model --check": step_data_model_check,
    "sources --check": step_sources,
    "check-only": step_check_only,
    "review findings": step_review_findings,
}


def build_steps(ctx: Ctx) -> list[tuple[str, Callable[[], tuple[bool, str]]]]:
    return [(name, (lambda f=STEP_FUNCS[name]: f(ctx))) for name in STEP_NAMES]


def run_steps(steps, out=print) -> int:
    """Run every step in order, print one PASS or FAIL line each, then the result."""
    failed = False
    for name, fn in steps:
        try:
            ok, detail = fn()
        except Exception as exc:
            ok, detail = False, f"raised {type(exc).__name__}: {exc}"
        out(f"{'PASS' if ok else 'FAIL'} {name}")
        if detail:
            out("\n".join("    " + ln for ln in detail.splitlines()))
        failed = failed or not ok
    out("RESULT: NOT GREEN" if failed else "RESULT: GREEN")
    return 1 if failed else 0


def export_merged_tree(sha: str, tmp: Path, repo: Path = REPO) -> Path:
    rc, out = sh(["git", "merge-tree", "--write-tree", "origin/main", sha], repo)
    if rc != 0:
        raise RuntimeError("merge conflict or unknown commit:\n" + tail(out, 5))
    tree = out.splitlines()[0].strip()
    export = tmp / "export"
    export.mkdir()
    tar_path = tmp / "tree.tar"
    rc, out = sh(["git", "archive", "--format=tar", f"--output={tar_path}", tree], repo)
    if rc != 0:
        raise RuntimeError("git archive failed: " + tail(out, 3))
    with tarfile.open(tar_path) as tf:
        if hasattr(tarfile, "data_filter"):
            tf.extractall(export, filter="data")
        else:
            tf.extractall(export)
    tar_path.unlink()
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "-c", "user.email=reproof", "-c", "user.name=reproof",
                 "commit", "-q", "-m", "export"]):
        rc, out = sh(cmd, export)
        if rc != 0:
            raise RuntimeError("throwaway repo failed: " + tail(out, 3))
    print(f"tree={tree} base={sh(['git', 'rev-parse', '--short', 'origin/main'], repo)[1].strip()}")
    return export


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3) or not argv[1].isdigit():
        print("usage: reproof.py PR [HEAD]", file=sys.stderr)
        return 2
    pr = argv[1]
    if len(argv) == 3:
        sha = argv[2]
    else:
        rc, out = sh(["gh", "pr", "view", pr, "--json", "headRefOid", "--jq", ".headRefOid"], REPO)
        sha = out.strip() if rc == 0 else ""
    if not valid_sha(sha):
        print("head sha must be 40 lowercase hex characters", file=sys.stderr)
        return 2
    tmp = Path(tempfile.mkdtemp(prefix="reproof-"))
    try:
        try:
            export = export_merged_tree(sha, tmp)
        except RuntimeError as exc:
            print(f"FAIL export\n    {exc}")
            print("RESULT: NOT GREEN")
            shutil.rmtree(tmp, ignore_errors=True)
            return 1
        try:
            return run_steps(build_steps(Ctx(pr, sha, tmp, export)))
        finally:
            shutil.rmtree(export, ignore_errors=True)
            print(f"pytest log kept in {tmp}")
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


if __name__ == "__main__":
    sys.exit(main(sys.argv))
