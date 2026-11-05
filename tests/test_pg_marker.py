import re
from pathlib import Path

TESTS = Path(__file__).resolve().parent
EXEMPT = {"test_migrations_apply.py", Path(__file__).name}
MARK = re.compile(r"^pytestmark\s*=.*\bpytest\.mark\.pg\b", re.M)


def test_every_file_reading_test_database_url_carries_the_pg_marker():
    unmarked = [
        p.name
        for p in sorted(TESTS.glob("test_*.py"))
        if p.name not in EXEMPT
        and "TEST_DATABASE_URL" in p.read_text(encoding="utf-8")
        and not MARK.search(p.read_text(encoding="utf-8"))
    ]
    assert not unmarked, (
        f"{unmarked} read TEST_DATABASE_URL without a module-level "
        "pytestmark = pytest.mark.pg; the storage-pg job runs -m pg and would skip them"
    )
