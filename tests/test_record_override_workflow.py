"""The Record a crosswalk override workflow (#431, ADR-0015): started by hand
only, from main only, in the etl environment, one concurrency group with the
Daily Run, every action pinned to a SHA, and no input inside a run line."""
import re
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "record-override.yml"
SHA = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def _load() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _on(wf: dict) -> dict:
    return wf.get("on", wf.get(True))


def _job(wf: dict) -> dict:
    return wf["jobs"]["record"]


def test_it_starts_by_hand_and_nothing_else():
    on = _on(_load())
    assert set(on) == {"workflow_dispatch"}
    assert "pull_request_target" not in WORKFLOW.read_text(encoding="utf-8")


def test_the_inputs_are_two_ids_and_a_tick_with_no_free_text_field():
    inputs = _on(_load())["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"scorer_id", "gsis_id", "replace"}
    assert inputs["replace"]["type"] == "boolean" and inputs["replace"]["default"] is False
    assert inputs["scorer_id"]["required"] and inputs["gsis_id"]["required"]
    assert all(i["type"] in ("string", "boolean") for i in inputs.values())


def test_it_refuses_to_run_outside_main():
    assert _job(_load())["if"] == "github.ref == 'refs/heads/main'"


def test_environment_concurrency_and_permissions():
    wf = _load()
    job = _job(wf)
    assert job["environment"] == "etl"
    assert job["concurrency"] == {"group": "etl", "cancel-in-progress": False}
    assert wf["permissions"] == {"contents": "read"}


def test_every_action_is_pinned_to_a_sha():
    uses = [s["uses"] for s in _job(_load())["steps"] if "uses" in s]
    assert uses
    for u in uses:
        assert SHA.match(u), u


def test_checkout_keeps_no_credentials():
    checkout = next(s for s in _job(_load())["steps"] if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["persist-credentials"] is False


def test_no_input_or_expression_is_inside_a_run_line():
    for step in _job(_load())["steps"]:
        if "run" in step:
            assert "${{" not in step["run"], step["run"]


def test_the_script_step_gets_the_inputs_and_the_secret_through_env():
    step = next(s for s in _job(_load())["steps"] if s.get("run") == "python scripts/record_crosswalk_override.py")
    env = step["env"]
    assert env["ETL_STORAGE"] == "postgres"
    assert env["SUPABASE_DB_URL"] == "${{ secrets.SUPABASE_DB_URL }}"
    assert env["SCORER_ID"] == "${{ inputs.scorer_id }}"
    assert env["GSIS_ID"] == "${{ inputs.gsis_id }}"
    assert env["REPLACE"] == "${{ inputs.replace }}"
    assert set(env) == {"ETL_STORAGE", "SUPABASE_DB_URL", "SCORER_ID", "GSIS_ID", "REPLACE"}


def test_it_names_no_secret_but_the_database_url():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert set(re.findall(r"secrets\.(\w+)", text)) == {"SUPABASE_DB_URL"}


def test_it_does_not_rebuild_the_crosswalk_or_open_a_pull_request():
    text = WORKFLOW.read_text(encoding="utf-8")
    for word in ("run_pipeline", "04z", "gh pr", "create-github-app-token"):
        assert word not in text.split("\njobs:", 1)[1], word
