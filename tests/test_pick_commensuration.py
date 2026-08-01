"""Regression tests for ADR-0013 decisions 4-5 (#49): picks and players
must share one 0-100 currency, no exceptions.

Runs against real repo parquet, same as the dev server -- these are
read-only local files, nothing to mock.
"""
import functools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mouserat_trade-bud" / "backend"))

import pytest

import data_access as da
import pick_value as pv

# Same one-shot-process memoization export_static.py applies (its
# _memoize_readers docstring explains why it's not baked into data_access.py
# itself): resolve_pick_value re-derives the whole player universe per pick,
# and this test iterates the full pick inventory across all 3 stances.
da.read_parquet = functools.lru_cache(maxsize=None)(da.read_parquet)
da.player_values = functools.lru_cache(maxsize=None)(da.player_values)
da.draft_pick_inventory = functools.lru_cache(maxsize=None)(da.draft_pick_inventory)

_EPS = 1e-6


@pytest.mark.parametrize("stance", da.STANCES)
def test_no_pick_prices_above_its_anchoring_pool(stance):
    """A pick's value can never exceed the highest-valued player in the
    source pool(s) it was quantile-mapped against (ADR-0013 decision 4) --
    the fix for 2027 R1 Early pricing at 108.4, above Josh Allen."""
    inventory = da.draft_pick_inventory()
    for _, row in inventory.iterrows():
        value = pv.value_for_pick_row(row, inventory, stance)
        assert value <= 100.0 + _EPS, (
            f"pick {row['pick_ref']} priced {value} under {stance} stance"
        )


@pytest.mark.parametrize("stance", da.STANCES)
def test_no_player_value_exceeds_its_position_ceiling(stance):
    """No player value can exceed its position's ceiling, under any stance
    -- the fix for the future-stance age tilt pushing Jeremiyah Love to
    111.5 against a 99.6 RB ceiling (ADR-0013 decision 5)."""
    values = da.player_values(stance)
    over = values[values["value"] > values["ceiling"] + _EPS]
    assert over.empty, (
        f"{len(over)} players under {stance} stance exceed their position "
        f"ceiling:\n{over[['gsis_id', 'position_group', 'value', 'ceiling']]}"
    )
