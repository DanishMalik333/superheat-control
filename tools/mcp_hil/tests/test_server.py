"""Unit and integration tests for tools/mcp_hil/server.py (simulator only, no hardware)."""
import inspect
import math
import subprocess
from pathlib import Path

import anyio
import pytest

import server
from server import hil_board

Row = hil_board.Row


def _no_subprocess(monkeypatch):
    def boom(*a, **k):
        raise AssertionError(f"subprocess must not run here: {a}")
    monkeypatch.setattr(server.subprocess, "run", boom)


# --- allowlist ----------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    (None, (None, None)),
    ("", (None, None)),
    ("all", (None, None)),
    ("step", ("step", None)),
    (" Windup ", ("windup", None)),
    ("link_loss", ("link_loss", None)),
    ("boot", ("boot", None)),
    ("test_step_response", ("step", "test_step_response")),
    ("test_link_up_after_boot", ("boot", "test_link_up_after_boot")),
])
def test_allowlist_accepts_known_names(name, expected):
    assert server.resolve_selection(name) == expected


@pytest.mark.parametrize("name", [
    "../../etc/passwd", "step; rm -rf /", "step && calc", "test_step.py", "-k step",
    "tests/hil/test_step.py", "step::test_step_response", "steps", "--sim-kp=9", 3, ["step"],
])
def test_allowlist_rejects_everything_else(name):
    with pytest.raises(ValueError):
        server.resolve_selection(name)


def test_run_tests_rejects_unknown_name_without_running_anything(bench, monkeypatch):
    _no_subprocess(monkeypatch)
    r = server.run_tests("step; del /q *")
    assert r["ok"] is False and "unknown test" in r["error"]


def test_explain_and_plot_need_one_named_test(bench):
    for fn in (server.explain_failure, server.plot):
        assert fn("all")["ok"] is False
        assert fn("../x")["ok"] is False


def test_resolve_cases_expands_suite():
    assert server.resolve_cases("boot") == ["test_reset_reports_header_and_rows", "test_link_up_after_boot"]
    assert server.resolve_cases("step") == ["test_step_response"]


@pytest.mark.parametrize("kp", [0, -0.1, 2.5, float("nan"), float("inf"), True, "0.3"])
def test_sim_gain_validation(bench, monkeypatch, kp):
    _no_subprocess(monkeypatch)
    assert server.run_tests("step", sim_kp=kp)["ok"] is False


# --- pytest command line --------------------------------------------------------

def test_sim_args_are_a_fixed_list(bench):
    args = server.build_pytest_args("step", None, 0.3, None)
    assert all(isinstance(a, str) for a in args)
    assert args[1:3] == ["-m", "pytest"]
    assert Path(args[3]) == bench / "test_step.py"
    assert "--sim" in args and args[args.index("--sim-kp") + 1] == "0.3"
    assert "--port" not in args and "--mute-gpio" not in args


def test_rig_args_come_from_server_env_only(bench, monkeypatch):
    monkeypatch.setenv("HIL_BACKEND", "rig")
    monkeypatch.setenv("HIL_PORT", "/dev/ttyACM0")
    monkeypatch.setenv("HIL_MUTE_GPIO", "17")
    args = server.build_pytest_args(None, None)
    assert "--sim" not in args
    assert args[args.index("--port") + 1] == "/dev/ttyACM0"
    assert args[args.index("--mute-gpio") + 1] == "17"
    with pytest.raises(ValueError):
        server.build_pytest_args("step", None, sim_kp=0.3)


@pytest.mark.parametrize("port", ["COM4 && calc", "/dev/ttyACM0; reboot", "../../x", "/etc/passwd"])
def test_rig_rejects_bad_port_env(bench, monkeypatch, port):
    monkeypatch.setenv("HIL_BACKEND", "rig")
    monkeypatch.setenv("HIL_PORT", port)
    with pytest.raises(ValueError):
        server.build_pytest_args("step", None)


def test_unknown_backend_value_falls_back_to_sim(monkeypatch):
    monkeypatch.setenv("HIL_BACKEND", "real-hardware")
    assert server.backend() == "sim"
    s = server.status()
    assert s["backend"] == "sim" and "warning" in s


def test_bad_mute_gpio_env_is_ignored(monkeypatch):
    monkeypatch.setenv("HIL_MUTE_GPIO", "17; reboot")
    gpio, problem = server.configured_mute_gpio()
    assert gpio is None and problem


# --- setpoint ----------------------------------------------------------------

@pytest.mark.parametrize("v,expected", [(0, 0.0), (40, 40.0), (13.333, 13.33), (10.0, 10.0)])
def test_setpoint_in_range(v, expected):
    assert server.validate_setpoint(v) == expected


@pytest.mark.parametrize("v", [-0.01, 40.01, 1e9, float("nan"), float("inf"), True, "13", None])
def test_setpoint_out_of_range(v):
    with pytest.raises(ValueError):
        server.validate_setpoint(v)


def test_set_setpoint_rejects_before_touching_the_bench(monkeypatch):
    monkeypatch.setattr(server, "_open_board", lambda: (_ for _ in ()).throw(AssertionError("opened")))
    r = server.set_setpoint(41)
    assert r["ok"] is False and "0..40" in r["error"]


def test_set_setpoint_on_sim_is_confirmed_by_a_row():
    r = server.set_setpoint(13.0)
    assert r["ok"] is True, r
    assert r["backend"] == "sim"
    assert abs(r["confirmed_by_row"]["setpoint"] - 13.0) < 0.005


# --- dangerous tools ---------------------------------------------------------

DANGEROUS = [server.flash, server.reset, server.inject_link_fault]


@pytest.mark.parametrize("fn", DANGEROUS)
@pytest.mark.parametrize("confirm", [False, True])
def test_dangerous_tools_disabled_by_default(monkeypatch, fn, confirm):
    _no_subprocess(monkeypatch)
    monkeypatch.setattr(server, "_open_board", lambda: (_ for _ in ()).throw(AssertionError("opened")))
    r = fn(confirm=confirm)
    assert r["ok"] is False and r["refused"] is True
    assert "HIL_ALLOW_DANGEROUS=1" in r["error"]


@pytest.mark.parametrize("fn", DANGEROUS)
@pytest.mark.parametrize("confirm", [False, None, "true", 1])
def test_dangerous_tools_need_literal_confirm_true(monkeypatch, fn, confirm):
    monkeypatch.setenv("HIL_ALLOW_DANGEROUS", "1")
    _no_subprocess(monkeypatch)
    r = fn(confirm=confirm)
    assert r["ok"] is False and r["refused"] is True and "confirm=true" in r["error"]


@pytest.mark.parametrize("flag", ["0", "true", "yes", " "])
def test_only_exact_flag_enables_dangerous(monkeypatch, flag):
    monkeypatch.setenv("HIL_ALLOW_DANGEROUS", flag)
    assert server.dangerous_enabled() is False


def test_flash_takes_no_path_and_uses_repo_elf():
    assert list(inspect.signature(server.flash).parameters) == ["confirm"]
    assert server.flash_command() == ["bash", "tools/hil/flash.sh",
                                      "Superheat_Control/build/Debug/Superheat_Control.elf"]


def test_flash_refused_on_sim_even_when_enabled(monkeypatch):
    monkeypatch.setenv("HIL_ALLOW_DANGEROUS", "1")
    _no_subprocess(monkeypatch)
    r = server.flash(confirm=True)
    assert r["ok"] is False and "real rig" in r["error"]


def test_flash_on_rig_needs_built_elf(monkeypatch, tmp_path):
    monkeypatch.setenv("HIL_ALLOW_DANGEROUS", "1")
    monkeypatch.setenv("HIL_BACKEND", "rig")
    monkeypatch.setattr(server, "REPO", tmp_path)
    _no_subprocess(monkeypatch)
    r = server.flash(confirm=True)
    assert r["ok"] is False and "not found" in r["error"]


def test_mcp_flash_schema_has_only_confirm():
    tools = anyio.run(server.mcp.list_tools)
    flash = next(t for t in tools if t.name == "hil_flash")
    assert set(flash.inputSchema["properties"]) == {"confirm"}


def test_reset_on_sim_when_enabled(monkeypatch):
    monkeypatch.setenv("HIL_ALLOW_DANGEROUS", "1")
    r = server.reset(confirm=True)
    assert r["ok"] is True and r["header_seen"] is True
    assert r["first_row_after_reset"]["tick"] <= 2


def test_inject_link_fault_on_sim_when_enabled(monkeypatch):
    monkeypatch.setenv("HIL_ALLOW_DANGEROUS", "1")
    r = server.inject_link_fault(confirm=True, ticks=8)
    assert r["ok"] is True, r
    states = [t["link_ok"] for t in r["link"]["transitions"]]
    assert states == [0, 1]
    assert r["link"]["valve_values_while_down"] == [0.3]


@pytest.mark.parametrize("ticks", [0, 31, -1, "5", True, 2.5])
def test_inject_link_fault_ticks_validated(monkeypatch, ticks):
    monkeypatch.setenv("HIL_ALLOW_DANGEROUS", "1")
    r = server.inject_link_fault(confirm=True, ticks=ticks)
    assert r["ok"] is False and "ticks" in r["error"]


# --- robustness ----------------------------------------------------------------

def test_busy_lock_refuses_second_operation(bench):
    assert server._lock.acquire(blocking=False)
    try:
        r = server.run_tests("step")
        assert r["ok"] is False and "another HIL operation" in r["error"]
        assert server.set_setpoint(10)["ok"] is False
    finally:
        server._lock.release()


def test_pytest_timeout_is_reported(bench, monkeypatch):
    def slow(*a, **k):
        raise subprocess.TimeoutExpired(a[0], k.get("timeout"))
    monkeypatch.setattr(server.subprocess, "run", slow)
    r = server.run_tests("step")
    assert r["ok"] is False and "timed out" in r["error"]
    assert not server._lock.locked()


def test_ci_status_without_gh_is_not_available(monkeypatch):
    monkeypatch.setattr(server.shutil, "which", lambda _: None)
    assert server.ci_status() == {"ok": True, "available": False, "reason": "gh CLI not installed"}


def test_ci_status_never_raises(monkeypatch):
    def broken(*a, **k):
        raise OSError("gh exploded")
    monkeypatch.setattr(server.shutil, "which", lambda _: "gh")
    monkeypatch.setattr(server.subprocess, "run", broken)
    r = server.ci_status()
    assert r["ok"] is True and r["available"] is False


def test_status_on_sim(bench):
    s = server.status()
    assert s["backend"] == "sim"
    assert s["dangerous_tools_enabled"] is False
    for k in ("serial_port_found", "gpio_library_available", "last_run"):
        assert k in s


def test_get_last_results_without_results(bench):
    assert server.get_last_results()["ok"] is False


# --- parsing -----------------------------------------------------------------

JUNIT = """<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest" tests="4">
<testcase classname="test_boot" name="test_link_up_after_boot" time="0.15" />
<testcase classname="test_step" name="test_step_response" time="2.4">
  <failure message="AssertionError: overshoot 24.0% (peak 13.72 degC)&#10;assert 0.24 &lt; 0.1">tb</failure>
</testcase>
<testcase classname="test_link_loss" name="test_link_loss_holds_safe_valve" time="0.0">
  <skipped message="needs --mute-gpio" />
</testcase>
<testcase classname="test_windup" name="test_recovers_from_saturation" time="0.1"><error message="boom" /></testcase>
</testsuite></testsuites>"""


def test_parse_junit(tmp_path):
    p = tmp_path / "junit.xml"
    p.write_text(JUNIT)
    j = server.parse_junit(p)
    assert j["counts"] == {"passed": 1, "failed": 1, "error": 1, "skipped": 1}
    step = j["cases"]["test_step_response"]
    assert step["outcome"] == "failed" and step["message"] == "AssertionError: overshoot 24.0% (peak 13.72 degC)"
    assert j["cases"]["test_link_loss_holds_safe_valve"]["outcome"] == "skipped"


def test_read_rows_skips_header_status_and_garbage(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("tick,bme280_degC,plant_degC,valve,setpoint_degC,link_ok\n"
                 "1,23.0,9.9,0.5,10.0,1\n"
                 "# FAULT link lost\n"
                 "1,2,3\n"
                 "2,23.0,9.9,0.3,10.0,2\n"
                 "3,nan,9.8,0.3,10.0,0\n")
    rows = server.read_rows(p)
    assert [r.tick for r in rows] == [1, 3]
    assert math.isnan(rows[1].ambient) and rows[1].link_ok is False


def _rows(spec):
    return [Row(t, 23.0, y, v, sp, ok) for t, (y, v, sp, ok) in enumerate(spec)]


def test_analyze_rows_link_and_valve_facts():
    rows = _rows([(10, 0.5, 10, True), (10, 0.5, 10, True), (10, 0.3, 10, False), (10, 0.3, 10, False),
                  (10, 0.3, 10, True), (10, float("nan"), 10, True), (10, 0.95, 10, True)])
    a = server.analyze_rows(rows)
    assert a["link"]["transitions"] == [{"tick": 2, "link_ok": 0}, {"tick": 4, "link_ok": 1}]
    assert a["link"]["down_rows"] == 2 and a["link"]["valve_values_while_down"] == [0.3]
    assert a["valve"]["nan_count"] == 1 and a["valve"]["outside_clamp_count"] == 1


def test_analyze_rows_step_metrics_and_oscillation():
    calm = [(10, 0.5, 10, True)] * 3 + [(10 + 3 * (1 - 0.5 ** k), 0.5, 13, True) for k in range(30)]
    a = server.analyze_rows(_rows(calm))
    step = a["segments"][1]
    assert step["from_setpoint"] == 10 and step["overshoot_pct"] == 0.0
    assert step["settling_ticks"] is not None and step["settling_ticks"] < 6
    assert a["oscillation_detected"] is False

    wobbly = [(10 + 1.5 * math.sin(k), 0.5, 10, True) for k in range(40)]
    a = server.analyze_rows(_rows(wobbly))
    assert a["oscillation_detected"] is True and a["segments"][0]["settling_ticks"] is None


def test_analyze_rows_counts_resets():
    rows = _rows([(10, 0.5, 10, True)] * 3)
    rows[2].tick = 0
    assert server.analyze_rows(rows)["board_resets_seen"] == 1


# --- end to end on the simulator -----------------------------------------------

def test_run_tests_shipped_gains_pass(shipped_run):
    _, r = shipped_run
    assert r["ok"] is True and r["backend"] == "sim"
    assert r["exit_code"] == 0, r
    assert r["counts"] == {"passed": 5, "failed": 0, "error": 0, "skipped": 0}
    step = next(t for t in r["tests"] if t["test"] == "test_step_response")
    assert step["outcome"] == "passed"
    assert 0 <= step["metrics"]["overshoot_pct"] < 10
    assert step["metrics"]["settling_ticks"] <= 30
    windup = next(t for t in r["tests"] if t["test"] == "test_recovers_from_saturation")
    assert windup["metrics"]["valve_at_max_ticks_while_saturating"] >= 10
    assert windup["metrics"]["undershoot_pct"] < 10
    link = next(t for t in r["tests"] if t["test"] == "test_link_loss_holds_safe_valve")
    assert [t["link_ok"] for t in link["metrics"]["link_transitions"]] == [0, 1]
    assert link["metrics"]["valve_values_while_down"] == [0.3]


def test_run_tests_records_last_run_for_status(bench):
    r = server.run_tests("step")
    assert r["exit_code"] == 0 and [t["test"] for t in r["tests"]] == ["test_step_response"]
    assert server.status()["last_run"] is not None


def test_get_last_results_reads_out_dir(shipped_run, results_of):
    results_of(shipped_run)
    r = server.get_last_results()
    assert r["ok"] is True
    assert r["junit"]["counts"]["passed"] == 5
    assert {c["test"] for c in r["csv"]} == set(server.TEST_CASES)


def test_explain_shipped_gains_finds_nothing_wrong(shipped_run, results_of):
    results_of(shipped_run)
    for name in ("step", "windup", "link_loss", "boot"):
        for rep in server.explain_failure(name)["reports"]:
            assert rep["junit"]["outcome"] == "passed"
            assert rep["hypotheses"] == [], rep
            assert all(c["ok"] for c in rep["checks"]), rep["checks"]
            assert rep["summary"].startswith("Nothing to explain")
            assert rep["facts"]["oscillation_detected"] is False
    step = server.explain_failure("step")["reports"][0]
    seg = next(s for s in step["facts"]["segments"] if s["setpoint"] == 13.0)
    assert 1.0 < seg["overshoot_pct"] < 5.0  # docs/HIL_TEST_BENCH.md: about 2.3 %


def test_run_tests_broken_gains_fail(broken_run):
    _, r = broken_run
    assert r["exit_code"] == 1
    assert r["sim_gains_override"] == {"kp": 0.3, "ki": None}
    assert r["counts"]["failed"] == 3
    outcome = {t["test"]: t["outcome"] for t in r["tests"]}
    assert outcome["test_step_response"] == "failed"
    assert outcome["test_recovers_from_saturation"] == "failed"
    assert outcome["test_link_loss_holds_safe_valve"] == "failed"
    step = next(t for t in r["tests"] if t["test"] == "test_step_response")
    assert step["metrics"]["oscillation_detected"] is True


def test_explain_broken_gains_reports_oscillation(broken_run, results_of):
    results_of(broken_run)
    for name in ("step", "windup", "link_loss"):
        rep = server.explain_failure(name)["reports"][0]
        assert rep["junit"]["outcome"] == "failed"
        assert rep["facts"]["oscillation_detected"] is True
        assert any(not c["ok"] for c in rep["checks"])
        assert rep["hypotheses"], rep
        assert all(h.startswith("HYPOTHESIS:") for h in rep["hypotheses"])
        assert "too high" in rep["hypotheses"][0]
        assert "oscillates" in rep["summary"]
        assert rep["facts"]["valve"]["at_max_ticks"] > 0 and rep["facts"]["valve"]["at_min_ticks"] > 0


def test_plot_writes_png(shipped_run, results_of):
    hil = results_of(shipped_run)
    r = server.plot("step")
    assert r["ok"] is True, r
    png = Path(r["plots"][0]["png"])
    assert png == hil / "out" / "test_step_response.png"
    assert png.stat().st_size > 10_000
