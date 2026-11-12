"""scripts/reproof.py and scripts/look_only_checks.py on fixtures only (#518)."""
import importlib.util
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rp = load("reproof")
lo = load("look_only_checks")


class TestSha:
    def test_accepts_40_lowercase_hex(self):
        assert rp.valid_sha("a" * 40)

    def test_refuses_the_rest(self):
        for bad in ("", "a" * 39, "a" * 41, "A" * 40, "g" * 40, "a" * 40 + "\n", "main"):
            assert not rp.valid_sha(bad)

    def test_main_refuses_a_bad_sha_before_doing_anything(self, capsys):
        assert rp.main(["reproof.py", "1", "nothex"]) == 2
        assert "40 lowercase hex" in capsys.readouterr().err


class TestSteps:
    def test_step_order(self):
        steps = rp.build_steps(rp.Ctx("1", "a" * 40, Path("t"), Path("e")))
        assert [n for n, _ in steps] == [
            "pytest", "pii", "data_model", "data_model --check",
            "sources --check", "check-only", "review findings"]

    def test_all_pass_is_green_and_exit_zero(self):
        lines, ran = [], []
        steps = [(n, (lambda n=n: (ran.append(n) or (True, "")))) for n in "abc"]
        assert rp.run_steps(steps, out=lines.append) == 0
        assert ran == ["a", "b", "c"]
        assert lines == ["PASS a", "PASS b", "PASS c", "RESULT: GREEN"]

    def test_a_failed_step_is_nonzero_and_later_steps_still_run(self):
        lines, ran = [], []

        def step(name, ok):
            return name, (lambda: (ran.append(name) or (ok, f"detail {name}")))

        code = rp.run_steps([step("a", True), step("b", False), step("c", True)],
                            out=lines.append)
        assert code == 1
        assert ran == ["a", "b", "c"]
        assert "FAIL b" in lines and lines[-1] == "RESULT: NOT GREEN"

    def test_a_raising_step_fails(self):
        def boom():
            raise ValueError("x")

        lines = []
        assert rp.run_steps([("boom", boom)], out=lines.append) == 1
        assert lines[0] == "FAIL boom"


class TestLookOnly:
    def test_runs_against_a_fixture_snapshot(self, tmp_path):
        registry = {"t": {"name": "t", "grain": "k", "chain": "c", "required_keys": ["k"],
                          "columns": [{"name": "k", "dtype": "float64"}]}}
        pd.DataFrame({"k": [1, 1, None]}).to_parquet(tmp_path / "t.parquet", index=False)
        lines = []
        total = lo.run(tmp_path, registry=registry, out=lambda *a: lines.append(" ".join(map(str, a))))
        assert total == 1
        assert any("grain_null_key" in ln and "findings=1" in ln for ln in lines)
        assert lines[-1] == "TOTAL findings 1"

    def test_main_needs_a_folder(self, capsys):
        assert lo.main(["x"]) == 2
        assert lo.main(["x", "no-such-folder"]) == 2
