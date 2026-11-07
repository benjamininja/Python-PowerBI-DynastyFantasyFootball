"""The Daily Run workflow (#93, brief 1, ADR-0015): the schedule, the main-only
and ETL_DAILY_ENABLED gate, the etl environment, one concurrency group, and
every action pinned to a commit SHA."""
import re
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "etl-daily.yml"
SHA = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def _load() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _triggers(wf: dict) -> dict:
    return wf.get("on", wf.get(True))


def _job(wf: dict) -> dict:
    return wf["jobs"]["daily"]


def test_cron_and_manual_trigger():
    on = _triggers(_load())
    assert on["schedule"] == [{"cron": "17 11 * * *"}]
    assert "workflow_dispatch" in on


def test_no_pull_request_target_or_other_triggers():
    on = _triggers(_load())
    assert set(on) == {"schedule", "workflow_dispatch"}
    assert "pull_request_target" not in WORKFLOW.read_text(encoding="utf-8")


def test_environment_concurrency_timeout_permissions():
    wf = _load()
    job = _job(wf)
    assert job["environment"] == "etl"
    assert job["concurrency"] == {"group": "etl", "cancel-in-progress": False}
    assert job["timeout-minutes"] == 180
    assert wf["permissions"] == {"contents": "read"}


def test_main_only_and_schedule_gate():
    cond = _job(_load())["if"]
    assert "github.ref == 'refs/heads/main'" in cond
    assert "github.event_name == 'workflow_dispatch'" in cond
    assert "vars.ETL_DAILY_ENABLED == 'true'" in cond


def test_every_action_is_pinned_to_a_sha():
    uses = [s["uses"] for s in _job(_load())["steps"] if "uses" in s]
    assert uses
    for u in uses:
        assert SHA.match(u), u


def test_checkout_keeps_history_and_no_credentials():
    checkout = next(s for s in _job(_load())["steps"] if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["fetch-depth"] == 0
    assert checkout["with"]["persist-credentials"] is False


def test_run_step_env_and_command():
    run = next(s for s in _job(_load())["steps"] if s.get("run") == "bash scripts/run_daily.sh")
    env = run["env"]
    assert env["ETL_STORAGE"] == "${{ vars.ETL_STORAGE }}"
    for name in ("FANTRAX_EMAIL", "FANTRAX_PASSWORD", "FANTRAX_TOTP_SECRET",
                 "SUPABASE_DB_URL", "DISCORD_WEBHOOK_URL"):
        assert env[name] == "${{ secrets." + name + " }}"
    assert env["GH_TOKEN"] == "${{ steps.app-token.outputs.token }}"
