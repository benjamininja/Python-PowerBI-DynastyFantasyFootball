import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_migration_order as cmo  # noqa: E402

BASE_FILES = ["20261101000000_a.sql", "20261105000000_b.sql"]


def git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo, check=True, capture_output=True,
    )


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    folder = repo / "supabase" / "migrations"
    folder.mkdir(parents=True)
    for name in BASE_FILES:
        (folder / name).write_text("select 1;\n")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "branch", "base_ref")
    return repo, folder


def run(repo, capsys):
    code = cmo.main(["--base", "base_ref", "--repo", str(repo)])
    return code, capsys.readouterr().out


def test_new_file_after_newest_passes(tmp_path, capsys):
    repo, folder = make_repo(tmp_path)
    (folder / "20261110000000_c.sql").write_text("select 1;\n")
    assert run(repo, capsys)[0] == 0


def test_new_file_before_newest_fails_and_is_named(tmp_path, capsys):
    repo, folder = make_repo(tmp_path)
    (folder / "20261101000000_early.sql").write_text("select 1;\n")
    code, out = run(repo, capsys)
    assert code == 1
    assert "20261101000000_early.sql" in out


def test_new_file_between_two_base_files_fails(tmp_path, capsys):
    repo, folder = make_repo(tmp_path)
    (folder / "20261103000000_mid.sql").write_text("select 1;\n")
    code, out = run(repo, capsys)
    assert code == 1
    assert "20261103000000_mid.sql" in out


def test_no_new_file_passes(tmp_path, capsys):
    repo, _ = make_repo(tmp_path)
    assert run(repo, capsys)[0] == 0


def test_base_file_removed_on_branch_is_not_new(tmp_path, capsys):
    repo, folder = make_repo(tmp_path)
    (folder / BASE_FILES[1]).unlink()
    assert run(repo, capsys)[0] == 0
