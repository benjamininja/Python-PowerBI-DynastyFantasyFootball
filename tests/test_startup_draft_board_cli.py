import importlib.util
from pathlib import Path

_BOARD = Path(__file__).resolve().parent.parent / "notebooks" / "05a_startup_draft_board.py"


def _load_board():
    spec = importlib.util.spec_from_file_location("startup_draft_board_05a", _BOARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_help_names_the_options():
    parser = _load_board().build_parser()
    text = parser.format_help()
    assert "--help" in text
    assert "05a_startup_draft_board.py" in text


def test_parser_accepts_no_arguments():
    parser = _load_board().build_parser()
    assert vars(parser.parse_args([])) == {}


def test_dropped_sources_are_gone_from_the_board():
    board = _load_board()
    dropped = {"value", "avg", "best", "worst", "stddev",
               "startup_adp", "startup_avg_auction_pct", "std_liquidity"}
    assert dropped.isdisjoint(board.METRIC_MAP)
