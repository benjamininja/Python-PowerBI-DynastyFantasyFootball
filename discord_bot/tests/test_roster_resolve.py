from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import roster  # noqa: E402
from delivery import CommandError  # noqa: E402


def _teams():
    return pd.DataFrame({
        "team_key": ["A01", "A02", "B01"],
        "team_name": ["Big Dogs", "Big Cats", "Small Fry"],
    })


def test_several_matches_lists_the_names_only():
    with pytest.raises(CommandError) as exc:
        roster._resolve_team(_teams(), "big")
    msg = str(exc.value)
    assert "Big Dogs, Big Cats" in msg
    assert "()" not in msg and "``" not in msg and "None" not in msg and "nan" not in msg


def test_a_part_of_one_name_finds_that_team():
    assert roster._resolve_team(_teams(), "FRY")["team_key"] == "B01"


def test_no_match_is_a_command_error():
    with pytest.raises(CommandError, match="No team matches"):
        roster._resolve_team(_teams(), "zzzz")


@pytest.mark.parametrize("query", [None, "", "   "])
def test_an_empty_query_is_a_command_error(query):
    with pytest.raises(CommandError):
        roster._resolve_team(_teams(), query)
