import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import generate_migrations as gm

SUPABASE = REPO / "supabase"


def _newest_migration():
    return sorted((SUPABASE / "migrations").glob("*.sql"))[-1]


def test_the_state_file_is_the_registry():
    registry = yaml.safe_load((REPO / "docs" / "data_model.yml").read_text(encoding="utf-8"))
    state = json.loads((SUPABASE / gm.STATE_FILE).read_text(encoding="utf-8"))
    assert gm.desired_model(registry) == state, (
        "docs/data_model.yml changed without a migration: run scripts/generate_migrations.py")


def test_the_newest_migration_carries_the_state_hash():
    state = gm.load_state(SUPABASE / gm.STATE_FILE)
    first = _newest_migration().read_text(encoding="utf-8").splitlines()[0]
    assert first == f"-- registry_state sha256: {gm.state_sha(state)}"


def test_every_migration_name_is_fourteen_digits_then_a_name():
    for path in (SUPABASE / "migrations").glob("*.sql"):
        stamp, _, rest = path.stem.partition("_")
        assert len(stamp) == 14 and stamp.isdigit() and rest, path.name
