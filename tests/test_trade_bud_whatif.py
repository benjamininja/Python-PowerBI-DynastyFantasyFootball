import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

INDEX = Path(__file__).resolve().parent.parent / "mouserat_trade-bud" / "frontend" / "index.html"
NODE = shutil.which("node")

if NODE is None and os.environ.get("CI"):
    pytest.fail("node is required in CI to execute the what-if", pytrace=False)

pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed locally")


def _source() -> str:
    text = INDEX.read_text(encoding="utf-8")
    start = text.index("function whatIfCapRooms(")
    return text[start:text.index("\n}\n", start) + 3]


def what_if(my_room, cp_room, give, receive):
    script = _source() + "\nconst a = JSON.parse(process.argv[1]);\n" \
        "console.log(JSON.stringify(whatIfCapRooms(a[0], a[1], a[2], a[3])));\n"
    out = subprocess.run(
        [NODE, "-e", script, json.dumps([my_room, cp_room, give, receive])],
        capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def player(cap_hit, contract_value):
    return {"asset_type": "player", "cap_hit": cap_hit, "contract_value": contract_value}


PICK = {"asset_type": "pick"}


def test_player_given_sheds_charge_for_me_and_charges_salary_to_them():
    r = what_if(100, 50, [player(10, 10)], [])
    assert r == {"my": 110, "cp": 40}


def test_player_received_charges_salary_to_me_and_sheds_for_them():
    r = what_if(100, 50, [], [player(8, 8)])
    assert r == {"my": 92, "cp": 58}


def test_exempt_player_given_sheds_nothing_but_receiver_is_charged_full_salary():
    r = what_if(100, 50, [player(0, 12)], [])
    assert r == {"my": 100, "cp": 38}


def test_exempt_player_received_sheds_nothing_for_them_but_charges_me_full_salary():
    r = what_if(100, 50, [], [player(0, 12)])
    assert r == {"my": 88, "cp": 50}


def test_partial_charge_player_sheds_charge_and_costs_full_salary():
    r = what_if(100, 50, [player(5, 12)], [player(5, 12)])
    assert r == {"my": 93, "cp": 43}


def test_null_cap_hit_counts_zero():
    r = what_if(100, 50, [player(None, 12)], [player(None, 7)])
    assert r == {"my": 93, "cp": 38}


def test_null_contract_value_counts_zero():
    r = what_if(100, 50, [player(5, None)], [player(6, None)])
    assert r == {"my": 105, "cp": 56}


def test_pick_counts_zero_both_ways():
    assert what_if(100, 50, [PICK], [PICK]) == {"my": 100, "cp": 50}


def test_mixed_swap():
    r = what_if(100, 50, [player(10, 10), PICK], [player(0, 12)])
    assert r == {"my": 98, "cp": 40}
