from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import roster  # noqa: E402
from delivery import CommandError  # noqa: E402


def _teams(abbrs):
    return pd.DataFrame({
        "team_key": ["A01", "A02", "B01"],
        "team_name": ["Big Dogs", "Big Cats", "Small Fry"],
        "team_abbr": abbrs,
    })


@pytest.mark.parametrize("abbrs", [[None, None, None], [float("nan"), "", None]])
def test_several_matches_without_abbr_has_no_brackets(abbrs):
    with pytest.raises(CommandError) as exc:
        roster._resolve_team(_teams(abbrs), "big")
    msg = str(exc.value)
    assert "Big Dogs, Big Cats" in msg
    assert "()" not in msg and "``" not in msg and "None" not in msg and "nan" not in msg


def test_none_query_is_a_command_error():
    with pytest.raises(CommandError):
        roster._resolve_team(_teams([None, None, None]), None)


def test_several_matches_with_abbr_still_shows_it():
    with pytest.raises(CommandError) as exc:
        roster._resolve_team(_teams(["BIGD", None, "SF"]), "big")
    msg = str(exc.value)
    assert "Big Dogs (`BIGD`)" in msg
    assert "Big Cats," in msg or "Big Cats." in msg
