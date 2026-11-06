"""The Refresh schedule page and its stages (#380): the page is generated from
build_steps, every scheduled step is in exactly one stage, and a new step with
no stage fails here."""
import re
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import build_schedule_page as bsp  # noqa: E402

rp = bsp.load_run_pipeline()
STAGES = yaml.safe_load(bsp.STAGES.read_text(encoding="utf-8"))
STEP_NAMES = [s["name"] for s in rp.build_steps(None)]
BUILT = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def staged_names():
    return [m["name"] for st in STAGES["stages"] for m in st["steps"]]


def test_every_scheduled_step_is_in_exactly_one_stage():
    counts = Counter(staged_names())
    assert [n for n in STEP_NAMES if counts[n] != 1] == []


def test_every_step_named_in_stages_exists_in_build_steps():
    assert [n for n in staged_names() if n not in STEP_NAMES] == []


def test_manual_steps_are_not_scheduled_steps():
    prefixes = tuple(m["name"] + "_" for m in STAGES["manual"])
    assert [n for n in STEP_NAMES if n.startswith(prefixes)] == []


def test_every_stage_has_a_description_without_code_names_in_its_first_sentence():
    for st in [*STAGES["stages"], STAGES["publish"]]:
        text = " ".join(st["description"].split())
        assert text, st["name"]
        first = re.split(r"(?<=[.!?])\s", text)[0]
        assert not re.search(r"\b\d\d[a-z]?_|\b(dim|fact)_", first), st["name"]


def test_stage_tables_are_declared_in_the_data_model():
    declared = {t["name"] for t in yaml.safe_load(
        (REPO / "docs" / "data_model.yml").read_text(encoding="utf-8"))["tables"]}
    missing = [t for st in STAGES["stages"] for t in st["tables"] if t not in declared]
    assert missing == []


def rendered(periods=None, today=date(2026, 11, 6)):
    return bsp.render(rp.build_steps(None), STAGES, periods, today, 3, BUILT, bsp.sources_by_file())


def test_page_rows_match_build_steps():
    rows = {}
    for line in rendered().splitlines():
        m = re.match(r"\| `([^`]+)` \|.*\| (\S[^|]*) \| (daily|close_day) \| (yes|no) \|", line)
        if m:
            rows[m.group(1)] = (m.group(2).strip(), m.group(3), m.group(4))
    steps = {s["name"]: s for s in rp.build_steps(None)}
    assert set(rows) == set(steps)
    for name, s in steps.items():
        assert rows[name] == (bsp.phase_text(s), s["cadence"], "yes" if bsp.needs_login(s) else "no"), name


def test_login_steps_are_the_fantrax_sign_in_steps():
    login = {s["name"] for s in rp.build_steps(None) if bsp.needs_login(s)}
    assert login == {"04a_scrape", "04a_backfill_gp", "04v_minor_contracts", "04t_txn_history", "04s_scoring"}


def test_close_day_steps_show_close_day_and_the_rest_daily():
    for s in rp.build_steps(None):
        assert s["cadence"] == ("close_day" if s["name"] in rp.CLOSE_DAY_STEPS else "daily")


def test_next_three_close_days_from_the_periods():
    periods = pd.DataFrame({"end_date": pd.to_datetime(["2026-11-01", "2026-11-08", "2026-11-15", "2026-11-22"])})
    assert bsp.next_close_days(periods, date(2026, 11, 6), 3) == [
        date(2026, 11, 9), date(2026, 11, 16), date(2026, 11, 23)]


def test_close_days_continue_on_the_weekday_past_the_calendar():
    periods = pd.DataFrame({"end_date": pd.to_datetime(["2026-11-01", "2026-11-08"])})
    days = bsp.next_close_days(periods, date(2026, 11, 6), 3)
    assert days[0] == date(2026, 11, 9)
    assert [d.weekday() for d in days[1:]] == [3, 3] and days[1] > days[0]
    assert (days[2] - days[1]).days == 7


def test_close_days_without_a_calendar_are_the_weekday():
    days = bsp.next_close_days(None, date(2026, 11, 6), 3)
    assert days == [date(2026, 11, 12), date(2026, 11, 19), date(2026, 11, 26)]


def test_page_text_has_no_raw_or_review_paths_and_the_last_built_line():
    text = rendered()
    assert "data/raw" not in text and "data/review" not in text
    assert "Last built: 2026-11-06 12:00 UTC" in text
    assert "## Run by hand" in text and "### Publish" in text


def test_generated_from_the_published_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(bsp, "PAGE", tmp_path / "refresh-schedule.md")
    assert bsp.main() == 0
    text = (tmp_path / "refresh-schedule.md").read_text(encoding="utf-8")
    assert len([ln for ln in text.splitlines() if ln.startswith("- ")]) == 3
    for name in STEP_NAMES:
        assert f"| `{name}` |" in text


@pytest.mark.parametrize("path", [bsp.REPO / "docs" / "site" / "stages.yml"])
def test_stages_file_has_no_owner_text(path):
    text = path.read_text(encoding="utf-8")
    assert "@" not in text
