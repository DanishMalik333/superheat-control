"""Safe-first MCP server for the Superheat Control HIL test bench.

Exposes the existing bench (tests/hil: board.py, sim.py, conftest.py and the
test_*.py limits; tools/plot_from_log.py; tools/hil/flash.sh) to an MCP
client such as Claude Code over stdio. Nothing here re-implements the
controller, the plant or the tests: it runs them and reads what they write.

Safety model (see README.md):
  * Backend is the simulator unless the server was started with HIL_BACKEND=rig.
  * Callers never pass paths or shell commands. Test names are checked against
    an allowlist; every subprocess gets a fixed argument list (no shell=True).
  * hil_flash / hil_reset / hil_inject_link_fault refuse unless the server was
    started with HIL_ALLOW_DANGEROUS=1, and even then need confirm=true.
  * One bench operation at a time (a lock), so two tools never fight over the
    serial port.

Server-side configuration (environment, set by whoever registers the server):
  HIL_BACKEND          "sim" (default) or "rig"
  HIL_ALLOW_DANGEROUS  "1" enables the dangerous tools (still need confirm=true)
  HIL_PORT             Board 1 VCP, e.g. /dev/ttyACM0 or COM4 (default: auto-detect)
  HIL_MUTE_GPIO        BCM pin wired to Board 2 D4 (rig link-loss test, fault injection)
  HIL_TIMEOUT_S        pytest timeout in seconds (default 180 sim, 1200 rig)
"""
from __future__ import annotations

import functools
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HIL_DIR = REPO / "tests" / "hil"
OUT_DIR = HIL_DIR / "out"
PLOT_SCRIPT = REPO / "tools" / "plot_from_log.py"
# Relative to REPO, exactly as .github/workflows/hil.yml runs them.
FLASH_SCRIPT_REL = "tools/hil/flash.sh"
BOARD1_ELF_REL = "Superheat_Control/build/Debug/Superheat_Control.elf"

# Reuse the bench's own code and limits rather than copying them.
sys.path.insert(0, str(HIL_DIR))
import board as hil_board  # noqa: E402  Row, CSV_FIELDS, VALVE_MIN/MAX, Board1
import sim as hil_sim  # noqa: E402  SimRig and the shipped gains PID_KP / PID_KI
import test_link_loss  # noqa: E402  VALVE_SAFE
import test_step  # noqa: E402  SP_FROM, SP_TO, MAX_OVERSHOOT, SETTLE_TICKS, ...
import test_windup  # noqa: E402  SP_NORMAL, SP_UNREACHABLE, MAX_UNDERSHOOT, ...

ST_LINK_VID = 0x0483  # same as tests/hil/conftest.py
SETPOINT_MIN, SETPOINT_MAX = 0.0, 40.0  # Board 1 CommandTask accepts 0..40 degC
SIM_GAIN_MAX = 2.0

# --- allowlists ---------------------------------------------------------------

SUITES = {
    "boot": "test_boot.py",
    "link_loss": "test_link_loss.py",
    "step": "test_step.py",
    "windup": "test_windup.py",
}
# pytest node name (also the CSV name in tests/hil/out) -> suite
TEST_CASES = {
    "test_reset_reports_header_and_rows": "boot",
    "test_link_up_after_boot": "boot",
    "test_link_loss_holds_safe_valve": "link_loss",
    "test_step_response": "step",
    "test_recovers_from_saturation": "windup",
}

_PORT_RE = re.compile(r"^(COM\d{1,3}|/dev/tty(ACM|USB)\d{1,3}|/dev/serial/by-id/[A-Za-z0-9_.:\-]+)$")

SETTLE_BAND = 0.3  # degC, the band board.settle() and test_step use
CROSS_HYSTERESIS = 0.1  # degC, error must leave +-this to count as a sign change
SAT_EPS = 1e-3

_lock = threading.Lock()
LAST_RUN: dict | None = None


class BenchBusy(RuntimeError):
    pass


class _exclusive:
    """One bench operation at a time; refuse instead of queueing."""

    def __enter__(self):
        if not _lock.acquire(blocking=False):
            raise BenchBusy("another HIL operation is running; try again when it finishes")

    def __exit__(self, *exc):
        _lock.release()


def _run(args: list[str], cwd: Path, timeout: float, env=None) -> subprocess.CompletedProcess:
    """Fixed argument list, no shell. stdin is DEVNULL: the server's own stdin is
    the MCP stdio stream and a child must never inherit it."""
    return subprocess.run(args, cwd=str(cwd), stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout, env=env)


def _err(msg: str, **extra) -> dict:
    return {"ok": False, "error": msg, **extra}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


# --- server-side configuration -----------------------------------------------


def backend() -> str:
    return "rig" if os.environ.get("HIL_BACKEND", "").strip().lower() == "rig" else "sim"


def dangerous_enabled() -> bool:
    return os.environ.get("HIL_ALLOW_DANGEROUS", "").strip() == "1"


def configured_port() -> tuple[str | None, str | None]:
    """(port, problem). HIL_PORT if valid, else auto-detect one ST-LINK VCP."""
    env = os.environ.get("HIL_PORT", "").strip()
    if env:
        if _PORT_RE.match(env):
            return env, None
        return None, f"HIL_PORT={env!r} is not a recognised serial port name"
    try:
        from serial.tools import list_ports
    except ImportError:
        return None, "pyserial not installed"
    ports = [p.device for p in list_ports.comports() if p.vid == ST_LINK_VID]
    if len(ports) == 1:
        return ports[0], None
    return None, f"expected one ST-LINK VCP, found {ports or 'none'}"


def configured_mute_gpio() -> tuple[int | None, str | None]:
    env = os.environ.get("HIL_MUTE_GPIO", "").strip()
    if not env:
        return None, "HIL_MUTE_GPIO not set"
    if env.isdigit() and 2 <= int(env) <= 27:
        return int(env), None
    return None, f"HIL_MUTE_GPIO={env!r} is not a BCM pin 2..27"


def gpio_library_available() -> bool:
    try:
        import gpiozero  # noqa: F401
    except Exception:
        return False
    return True


def timeout_s() -> int:
    env = os.environ.get("HIL_TIMEOUT_S", "").strip()
    if env.isdigit() and 10 <= int(env) <= 3600:
        return int(env)
    return 1200 if backend() == "rig" else 180


# --- validation --------------------------------------------------------------


def resolve_selection(name) -> tuple[str | None, str | None]:
    """Run-tests filter -> (suite, case). None/'all' -> whole suite.
    Raises ValueError for anything not on the allowlist."""
    if name is None:
        return None, None
    if not isinstance(name, str):
        raise ValueError("test must be a string")
    key = name.strip().lower()
    if key in ("", "all"):
        return None, None
    if key in SUITES:
        return key, None
    if key in TEST_CASES:
        return TEST_CASES[key], key
    raise ValueError(f"unknown test {name!r}; allowed: all, {', '.join(SUITES)}, {', '.join(TEST_CASES)}")


def resolve_cases(name) -> list[str]:
    """Test name for explain/plot -> list of pytest case names (CSV names)."""
    suite, case = resolve_selection(name)
    if suite is None:
        raise ValueError("name one test: " + ", ".join(list(SUITES) + list(TEST_CASES)))
    if case:
        return [case]
    return [c for c, s in TEST_CASES.items() if s == suite]


def validate_setpoint(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("setpoint must be a number")
    v = float(value)
    if not math.isfinite(v) or not SETPOINT_MIN <= v <= SETPOINT_MAX:
        raise ValueError(f"setpoint must be within {SETPOINT_MIN:g}..{SETPOINT_MAX:g} degC, got {value!r}")
    return round(v, 2)


def _validate_gain(name, value) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    v = float(value)
    if not math.isfinite(v) or not 0.0 < v <= SIM_GAIN_MAX:
        raise ValueError(f"{name} must be within (0, {SIM_GAIN_MAX:g}], got {value!r}")
    return v


# --- reading results ---------------------------------------------------------


def read_rows(path: Path) -> list:
    """Parses a tests/hil/out CSV with board.Row.parse (header and junk skipped)."""
    rows = []
    with open(path, newline="") as f:
        for line in f:
            r = hil_board.Row.parse(line.strip())
            if r is not None:
                rows.append(r)
    return rows


def parse_junit(path: Path) -> dict:
    root = ET.parse(path).getroot()
    cases = {}
    for tc in root.iter("testcase"):
        outcome, message = "passed", ""
        for tag, label in (("failure", "failed"), ("error", "error"), ("skipped", "skipped")):
            el = tc.find(tag)
            if el is not None:
                outcome = label
                lines = (el.get("message") or el.text or "").strip().splitlines()
                message = lines[0][:300] if lines else ""
                break
        cases[tc.get("name")] = {
            "outcome": outcome,
            "time_s": round(float(tc.get("time") or 0.0), 3),
            "message": message,
        }
    counts = {k: sum(1 for c in cases.values() if c["outcome"] == k)
              for k in ("passed", "failed", "error", "skipped")}
    return {"cases": cases, "counts": counts}


def _segments(rows) -> list[list]:
    segs = []
    for r in rows:
        if segs and abs(r.setpoint - segs[-1][-1].setpoint) < 0.005:
            segs[-1].append(r)
        else:
            segs.append([r])
    return segs


def _crossings(errors) -> int:
    state, n = 0, 0
    for e in errors:
        s = 1 if e > CROSS_HYSTERESIS else -1 if e < -CROSS_HYSTERESIS else 0
        if s and state and s != state:
            n += 1
        if s:
            state = s
    return n


def _segment_metrics(seg, prev_sp) -> dict:
    sp = seg[0].setpoint
    ok = [r for r in seg if r.link_ok]  # superheat is stale while the link is down
    ys = [r.superheat for r in ok]
    m = {"setpoint": sp, "from_setpoint": prev_sp, "start_tick": seg[0].tick, "rows": len(seg),
         "valve_at_max_ticks": sum(abs(r.valve - hil_board.VALVE_MAX) < SAT_EPS for r in seg),
         "valve_at_min_ticks": sum(abs(r.valve - hil_board.VALVE_MIN) < SAT_EPS for r in seg)}
    if not ys:
        return m
    m["superheat_min"], m["superheat_max"] = round(min(ys), 4), round(max(ys), 4)
    if prev_sp is not None and sp > prev_sp:  # same formula as test_step
        m["overshoot_pct"] = round(max(0.0, max(ys) - sp) / (sp - prev_sp) * 100, 2)
    elif prev_sp is not None and sp < prev_sp and ys[0] > sp:  # same formula as test_windup
        m["undershoot_pct"] = round(max(0.0, sp - min(ys)) / (ys[0] - sp) * 100, 2)
    out = [i for i, y in enumerate(ys) if abs(y - sp) > SETTLE_BAND]
    m["settling_ticks"] = 0 if not out else (None if out[-1] == len(ys) - 1 else out[-1] + 1)
    errs = [sp - y for y in ys]
    m["error_sign_changes"] = _crossings(errs)
    late = ys[-20:]
    m["late_peak_to_peak"] = round(max(late) - min(late), 4)
    m["oscillating"] = m["error_sign_changes"] >= 4 and m["late_peak_to_peak"] > 2 * SETTLE_BAND
    return m


def analyze_rows(rows) -> dict:
    """Facts from one test's CSV rows; no interpretation."""
    if not rows:
        return {"rows": 0}
    valves = [r.valve for r in rows]
    finite = [v for v in valves if not math.isnan(v)]
    transitions, prev = [], rows[0].link_ok
    for r in rows[1:]:
        if r.link_ok != prev:
            transitions.append({"tick": r.tick, "link_ok": int(r.link_ok)})
            prev = r.link_ok
    down = [r for r in rows if not r.link_ok]
    segs, out_segs, prev_sp = _segments(rows), [], None
    for s in segs:
        out_segs.append(_segment_metrics(s, prev_sp))
        prev_sp = s[0].setpoint
    return {
        "rows": len(rows),
        "first_tick": rows[0].tick,
        "last_tick": rows[-1].tick,
        "board_resets_seen": sum(1 for a, b in zip(rows, rows[1:]) if b.tick < a.tick),
        "valve": {
            "min": round(min(finite), 3) if finite else None,
            "max": round(max(finite), 3) if finite else None,
            "nan_count": len(valves) - len(finite),
            "outside_clamp_count": sum(1 for v in finite if not hil_board.VALVE_MIN - SAT_EPS <= v
                                       <= hil_board.VALVE_MAX + SAT_EPS),
            "at_max_ticks": sum(abs(v - hil_board.VALVE_MAX) < SAT_EPS for v in finite),
            "at_min_ticks": sum(abs(v - hil_board.VALVE_MIN) < SAT_EPS for v in finite),
        },
        "link": {
            "starts_ok": rows[0].link_ok,
            "ends_ok": rows[-1].link_ok,
            "transitions": transitions,
            "down_rows": len(down),
            "valve_values_while_down": sorted({round(r.valve, 3) for r in down})[:5],
        },
        "oscillation_detected": any(s.get("oscillating") for s in out_segs),
        "segments": out_segs,
    }


def _find_segment(analysis, sp, from_sp=None):
    for i, s in enumerate(analysis.get("segments", [])):
        if abs(s["setpoint"] - sp) < 0.005 and (from_sp is None or (
                s["from_setpoint"] is not None and abs(s["from_setpoint"] - from_sp) < 0.005)):
            return i, s
    return None, None


def key_metrics(case: str, analysis: dict) -> dict:
    """The few numbers worth showing per test in a run summary."""
    if not analysis.get("rows"):
        return {"rows": 0}
    km = {"rows": analysis["rows"], "valve_min": analysis["valve"]["min"],
          "valve_max": analysis["valve"]["max"], "oscillation_detected": analysis["oscillation_detected"]}
    suite = TEST_CASES[case]
    if suite == "step":
        _, s = _find_segment(analysis, test_step.SP_TO, test_step.SP_FROM)
        if s:
            km.update(overshoot_pct=s.get("overshoot_pct"), settling_ticks=s.get("settling_ticks"))
        else:
            km["note"] = f"no {test_step.SP_FROM:g}->{test_step.SP_TO:g} step in the log"
    elif suite == "windup":
        i, s = _find_segment(analysis, test_windup.SP_UNREACHABLE)
        if s:
            km["valve_at_max_ticks_while_saturating"] = s["valve_at_max_ticks"]
            segs = analysis["segments"]
            if i + 1 < len(segs):
                km.update(undershoot_pct=segs[i + 1].get("undershoot_pct"),
                          recovery_settling_ticks=segs[i + 1].get("settling_ticks"))
        else:
            km["note"] = f"never stepped to {test_windup.SP_UNREACHABLE:g} degC"
    elif suite == "link_loss":
        km.update(link_transitions=analysis["link"]["transitions"],
                  valve_values_while_down=analysis["link"]["valve_values_while_down"])
    else:
        km.update(board_resets_seen=analysis["board_resets_seen"], link_ends_ok=analysis["link"]["ends_ok"])
    return km


def _csv_path(case: str) -> Path:
    return OUT_DIR / f"{case}.csv"


def _junit_path() -> Path:
    return OUT_DIR / "junit.xml"


# --- tools: implementation (plain functions, unit-tested directly) -----------


def status() -> dict:
    port, port_problem = configured_port()
    gpio, gpio_problem = configured_mute_gpio()
    last = LAST_RUN
    junit = _junit_path()
    raw_backend = os.environ.get("HIL_BACKEND", "")
    s = {
        "ok": True,
        "backend": backend(),
        "serial_port": port,
        "serial_port_found": port is not None,
        "gpio_library_available": gpio_library_available(),
        "mute_gpio": gpio,
        "dangerous_tools_enabled": dangerous_enabled(),
        "last_run": last["finished"] if last else None,
        "last_run_by_this_server": last is not None,
        "junit_xml_mtime": _iso(junit.stat().st_mtime) if junit.exists() else None,
        "repo": str(REPO),
        "python": sys.executable,
    }
    if port_problem:
        s["serial_port_note"] = port_problem
    if gpio_problem:
        s["mute_gpio_note"] = gpio_problem
    if raw_backend and raw_backend.strip().lower() not in ("sim", "rig"):
        s["warning"] = f"HIL_BACKEND={raw_backend!r} not recognised; using sim"
    return s


def build_pytest_args(suite, case, sim_kp=None, sim_ki=None) -> list[str]:
    target = HIL_DIR if suite is None else HIL_DIR / SUITES[suite]
    tgt = str(target) + (f"::{case}" if case else "")
    args = [sys.executable, "-m", "pytest", tgt, f"--junitxml={_junit_path()}"]
    if backend() == "sim":
        args.append("--sim")
        if sim_kp is not None:
            args += ["--sim-kp", repr(sim_kp)]
        if sim_ki is not None:
            args += ["--sim-ki", repr(sim_ki)]
    else:
        if sim_kp is not None or sim_ki is not None:
            raise ValueError("sim_kp/sim_ki only apply to the simulator backend")
        if os.environ.get("HIL_PORT", "").strip():
            port, problem = configured_port()
            if problem:
                raise ValueError(problem)
            args += ["--port", port]
        gpio, _ = configured_mute_gpio()
        if gpio is not None:
            args += ["--mute-gpio", str(gpio)]
    return args


_EXIT_MEANING = {0: "all tests passed", 1: "some tests failed", 2: "interrupted",
                 3: "aborted (pytest.exit: e.g. Board 1 doesn't answer 'ping')",
                 4: "usage error (e.g. no ST-LINK port found)", 5: "no tests collected"}


def run_tests(test=None, sim_kp=None, sim_ki=None) -> dict:
    global LAST_RUN
    try:
        suite, case = resolve_selection(test)
        kp, ki = _validate_gain("sim_kp", sim_kp), _validate_gain("sim_ki", sim_ki)
        args = build_pytest_args(suite, case, kp, ki)
    except ValueError as e:
        return _err(str(e))
    try:
        with _exclusive():
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            started = time.time()
            env = dict(os.environ, MPLBACKEND="Agg", PYTHONIOENCODING="utf-8")
            try:
                proc = _run(args, HIL_DIR, timeout_s(), env)
            except subprocess.TimeoutExpired:
                return _err(f"pytest timed out after {timeout_s()} s and was killed", backend=backend())
            duration = time.time() - started
    except BenchBusy as e:
        return _err(str(e))

    result = {"ok": True, "backend": backend(), "selection": test or "all",
              "exit_code": proc.returncode, "exit_meaning": _EXIT_MEANING.get(proc.returncode, "unknown"),
              "duration_s": round(duration, 1)}
    if kp is not None or ki is not None:
        result["sim_gains_override"] = {"kp": kp, "ki": ki}
    junit = _junit_path()
    tests = []
    if junit.exists() and junit.stat().st_mtime >= started - 1:
        parsed = parse_junit(junit)
        result["counts"] = parsed["counts"]
        for name, info in parsed["cases"].items():
            entry = {"test": name, **info}
            csv = _csv_path(name) if name in TEST_CASES else None
            if csv and csv.exists() and csv.stat().st_mtime >= started - 1:
                entry["metrics"] = key_metrics(name, analyze_rows(read_rows(csv)))
            tests.append(entry)
    else:
        result["note"] = "pytest wrote no junit.xml for this run"
    result["tests"] = tests
    if proc.returncode not in (0, 1) or not tests:
        result["output_tail"] = (proc.stdout + proc.stderr).strip().splitlines()[-15:]
    LAST_RUN = {"finished": _now_iso(), "backend": result["backend"], "selection": result["selection"],
                "exit_code": proc.returncode, "counts": result.get("counts")}
    return result


def get_last_results() -> dict:
    if not OUT_DIR.exists():
        return _err("no results yet: tests/hil/out does not exist (run hil_run_tests first)")
    junit = _junit_path()
    res = {"ok": True, "out_dir": str(OUT_DIR), "last_run_by_this_server": LAST_RUN}
    if junit.exists():
        parsed = parse_junit(junit)
        res["junit"] = {"mtime": _iso(junit.stat().st_mtime), **parsed}
    else:
        res["junit"] = None
    csvs = []
    for case in TEST_CASES:
        p = _csv_path(case)
        if not p.exists():
            continue
        entry = {"test": case, "mtime": _iso(p.stat().st_mtime),
                 "metrics": key_metrics(case, analyze_rows(read_rows(p)))}
        if junit.exists() and p.stat().st_mtime < junit.stat().st_mtime - 60:
            entry["note"] = "older than junit.xml: probably from an earlier run"
        csvs.append(entry)
    res["csv"] = csvs
    return res


def _check(name, measured, limit, ok) -> dict:
    return {"check": name, "measured": measured, "limit": limit, "ok": bool(ok)}


def _explain_case(case: str, junit_cases: dict) -> dict:
    p = _csv_path(case)
    report = {"test": case, "junit": junit_cases.get(case)}
    if not p.exists():
        report["facts"] = {"rows": 0}
        report["checks"] = []
        report["hypotheses"] = ["HYPOTHESIS: the test never ran or crashed before its fixture saved the CSV; "
                                "run hil_run_tests for it first."]
        report["summary"] = f"No CSV for {case} in tests/hil/out."
        return report
    rows = read_rows(p)
    a = analyze_rows(rows)
    report["csv_mtime"] = _iso(p.stat().st_mtime)
    report["facts"] = a
    checks, hyp = [], []
    suite = TEST_CASES[case]
    msg = (report["junit"] or {}).get("message", "")

    if not rows:
        hyp.append("HYPOTHESIS: no data rows were captured: wrong serial port, Board 1 not flashed with the HIL "
                   "firmware, or Board 1 crashed (look for '!!! STACK OVERFLOW' on the VCP).")
    v = a.get("valve", {})
    if rows:
        checks.append(_check("valve never NaN and inside clamp",
                             {"nan": v["nan_count"], "outside": v["outside_clamp_count"]},
                             [hil_board.VALVE_MIN, hil_board.VALVE_MAX],
                             v["nan_count"] == 0 and v["outside_clamp_count"] == 0))
        if v["nan_count"] or v["outside_clamp_count"]:
            hyp.append("HYPOTHESIS: the PI output clamp is broken or the controller is fed a NaN measurement.")

    if "didn't settle" in msg:
        checks.append(_check("loop settled before the test procedure", False, "board.settle(): +-0.3 degC "
                             "for 5 rows within 120 rows", False))

    if suite == "step" and rows:
        i, s = _find_segment(a, test_step.SP_TO, test_step.SP_FROM)
        if s is None:
            checks.append(_check(f"step {test_step.SP_FROM:g}->{test_step.SP_TO:g} reached", False, True, False))
        else:
            seg = _segments(rows)[i][:test_step.OBSERVE_TICKS]
            peak = max(r.superheat for r in seg)
            ov = (peak - test_step.SP_TO) / test_step.STEP
            late = seg[test_step.SETTLE_TICKS:]
            worst = max((abs(r.superheat - test_step.SP_TO) for r in late), default=None)
            checks.append(_check("overshoot (fraction of step)", round(ov, 4), test_step.MAX_OVERSHOOT,
                                 ov < test_step.MAX_OVERSHOOT))
            checks.append(_check(f"worst |error| after {test_step.SETTLE_TICKS} ticks (degC)",
                                 None if worst is None else round(worst, 4), test_step.SETTLE_BAND,
                                 worst is not None and worst <= test_step.SETTLE_BAND))
            checks.append(_check("link up during the step", all(r.link_ok for r in seg), True,
                                 all(r.link_ok for r in seg)))
            if ov >= test_step.MAX_OVERSHOOT and not a["oscillation_detected"]:
                hyp.append("HYPOTHESIS: overshoot without sustained oscillation points to Ki (or Kp) somewhat "
                           "too high; on the real rig a large ambient (BME280) swing during the step could "
                           "also add to it.")
            if (worst is None or worst > test_step.SETTLE_BAND) and not a["oscillation_detected"] \
                    and ov < test_step.MAX_OVERSHOOT:
                hyp.append("HYPOTHESIS: slow, non-oscillating response: gains too low, or the plant on Board 2 "
                           "differs from the model the limits were computed for.")

    if suite == "windup" and rows:
        i, s = _find_segment(a, test_windup.SP_UNREACHABLE)
        segs = _segments(rows)
        if s is None:
            checks.append(_check(f"setpoint {test_windup.SP_UNREACHABLE:g} reached", False, True, False))
        else:
            sat = segs[i][:test_windup.SATURATE_TICKS][-10:]
            sat_n = sum(abs(r.valve - hil_board.VALVE_MAX) < SAT_EPS for r in sat)
            checks.append(_check("valve saturated at max for the last 10 saturation ticks", sat_n, 10, sat_n == 10))
            if sat_n < 10:
                hyp.append("HYPOTHESIS: the valve never saturated, so the setpoint was reachable: plant gain on "
                           "Board 2 higher than modelled. The test cannot judge anti-windup in that case.")
            if i + 1 < len(segs):
                rec = segs[i + 1][:test_windup.RECOVER_TICKS]
                top = rec[0].superheat
                under = (test_windup.SP_NORMAL - min(r.superheat for r in rec)) / (top - test_windup.SP_NORMAL) \
                    if top > test_windup.SP_NORMAL else None
                worst = max((abs(r.superheat - test_windup.SP_NORMAL) for r in rec[test_windup.SETTLE_TICKS:]),
                            default=None)
                checks.append(_check("undershoot after saturation (fraction)",
                                     None if under is None else round(under, 4), test_windup.MAX_UNDERSHOOT,
                                     under is not None and under < test_windup.MAX_UNDERSHOOT))
                checks.append(_check(f"worst |error| after {test_windup.SETTLE_TICKS} recovery ticks (degC)",
                                     None if worst is None else round(worst, 4), test_windup.SETTLE_BAND,
                                     worst is not None and worst <= test_windup.SETTLE_BAND))
                if sat_n == 10 and under is not None and under >= test_windup.MAX_UNDERSHOOT \
                        and not a["oscillation_detected"]:
                    hyp.append("HYPOTHESIS: large undershoot right after a saturated period is the classic sign "
                               "of integrator windup: the anti-windup clamp in the PI update may not be working.")
            else:
                checks.append(_check("recovery phase present", False, True, False))

    if suite == "link_loss" and rows:
        down = [r for r in rows if not r.link_ok]
        drops = [t for t in a["link"]["transitions"] if t["link_ok"] == 0]
        checks.append(_check("link_ok dropped while Board 2 was muted", len(drops), ">= 1", len(drops) >= 1))
        if down:
            held = all(abs(r.valve - test_link_loss.VALVE_SAFE) < SAT_EPS for r in down)
            checks.append(_check("valve held at VALVE_SAFE while link down", a["link"]["valve_values_while_down"],
                                 test_link_loss.VALVE_SAFE, held))
            if not held:
                hyp.append("HYPOTHESIS: Board 1's fault handling isn't holding the valve at VALVE_SAFE "
                           "(ControlTask kept running the PI on stale data).")
        checks.append(_check("link up again at the end", a["link"]["ends_ok"], True, a["link"]["ends_ok"]))
        checks.append(_check("final superheat within 0.3 of 10 degC", round(rows[-1].superheat, 4), "10 +- 0.3",
                             abs(rows[-1].superheat - 10.0) < 0.3))
        if not drops and "didn't settle" not in msg:
            hyp.append("HYPOTHESIS: muting Board 2 had no effect: GPIO/GND not wired to Board 2 D4, Board 2 "
                       "running old firmware without the mute pin, or HIL_MUTE_GPIO not set.")
        report["not_measurable_from_csv"] = ["fault latency (the cut time is not logged in the CSV)"]

    if suite == "boot" and rows:
        last = rows[-4:]
        checks.append(_check("link_ok in the last 4 rows", [int(r.link_ok) for r in last], "all 1",
                             all(r.link_ok for r in last)))
        if case == "test_reset_reports_header_and_rows":
            report["not_measurable_from_csv"] = ["CSV header timing (header lines are not saved in the CSV)"]

    if rows and a["link"]["down_rows"] and suite != "link_loss":
        hyp.append("HYPOTHESIS: link_ok went to 0 in a test that never cuts the link: Board 2 unpowered, "
                   "USART1 wiring loose, or Board 2 crashed.")
    if a.get("oscillation_detected"):
        osc = [s for s in a["segments"] if s.get("oscillating")]
        both = v.get("at_max_ticks", 0) > 0 and v.get("at_min_ticks", 0) > 0
        hyp.insert(0, "HYPOTHESIS: sustained oscillation around the setpoint means the loop is underdamped or "
                      "unstable: the PI gains (Kp and/or Ki) are most likely too high for this plant "
                      f"(shipped Kp={hil_sim.PID_KP:g}, Ki={hil_sim.PID_KI:g}; the simulator with "
                      "--sim-kp 0.3 shows this pattern)."
                      + (" The valve swings between both clamps, i.e. a limit cycle." if both else "")
                      + f" Seen in {len(osc)} setpoint segment(s).")

    failed = [c for c in checks if not c["ok"]]
    outcome = (report["junit"] or {}).get("outcome")
    if not failed and not hyp:
        report["summary"] = ("Nothing to explain: " + (f"junit says {outcome}; " if outcome else "")
                             + "every limit re-checked from the CSV holds.")
    else:
        parts = [f"junit outcome: {outcome}." if outcome else "No junit entry for this test."]
        if failed:
            parts.append("Failed checks: " + "; ".join(f"{c['check']} = {c['measured']} (limit {c['limit']})"
                                                       for c in failed) + ".")
        if a.get("oscillation_detected"):
            parts.append("Superheat oscillates and never settles.")
        report["summary"] = " ".join(parts)
    report["checks"] = checks
    report["hypotheses"] = hyp
    return report


def explain_failure(test) -> dict:
    try:
        cases = resolve_cases(test)
    except ValueError as e:
        return _err(str(e))
    junit = _junit_path()
    jc = parse_junit(junit)["cases"] if junit.exists() else {}
    return {"ok": True, "note": "facts and checks are computed from the CSV; hypotheses are inferences, not proof",
            "reports": [_explain_case(c, jc) for c in cases]}


def plot(test) -> dict:
    try:
        cases = resolve_cases(test)
    except ValueError as e:
        return _err(str(e))
    out = []
    for case in cases:
        csv = _csv_path(case)
        if not csv.exists():
            out.append({"test": case, "ok": False, "error": "no CSV; run the test first"})
            continue
        png = csv.with_suffix(".png")
        try:
            proc = _run([sys.executable, str(PLOT_SCRIPT), str(csv), "--out", str(png)], REPO, 120,
                        dict(os.environ, MPLBACKEND="Agg"))
        except subprocess.TimeoutExpired:
            out.append({"test": case, "ok": False, "error": "plot script timed out"})
            continue
        if proc.returncode == 0 and png.exists():
            out.append({"test": case, "ok": True, "png": str(png)})
        else:
            out.append({"test": case, "ok": False, "error": (proc.stderr or proc.stdout).strip()[-400:]})
    return {"ok": all(o["ok"] for o in out), "plots": out}


def _open_board():
    """Board1 on a fresh transport for the current backend. Returns (board, rig_or_serial)."""
    if backend() == "sim":
        rig = hil_sim.SimRig()
        b = hil_board.Board1(rig, period=rig.period)
    else:
        port, problem = configured_port()
        if problem:
            raise RuntimeError(problem)
        import serial

        rig = serial.Serial(port, 115200, timeout=0.2)
        b = hil_board.Board1(rig, period=1.0)
    if b.wait_for(lambda r: True, max_rows=5) is None:
        b.close()
        raise RuntimeError("no data rows from Board 1")
    return b, rig


def _row_dict(r) -> dict:
    return {"tick": r.tick, "superheat": r.superheat, "valve": r.valve, "setpoint": r.setpoint,
            "link_ok": int(r.link_ok)}


def set_setpoint(value) -> dict:
    try:
        sp = validate_setpoint(value)
    except ValueError as e:
        return _err(str(e))
    try:
        with _exclusive():
            b, _ = _open_board()
            try:
                idx = b.set_setpoint(sp)
                row = b.wait_rows(1, idx)[0]
            finally:
                b.close()
    except (BenchBusy, RuntimeError, AssertionError, TimeoutError, OSError) as e:
        return _err(str(e), backend=backend())
    res = {"ok": True, "backend": backend(), "setpoint": sp, "confirmed_by_row": _row_dict(row)}
    if backend() == "sim":
        res["note"] = "simulator: applied to a throwaway SimRig instance, which is discarded afterwards"
    else:
        res["note"] = "real rig: Board 1 keeps this setpoint until changed or reset"
    return res


# --- dangerous tools ---------------------------------------------------------


def _gate(tool: str, confirm) -> dict | None:
    if not dangerous_enabled():
        return _err(f"{tool} is disabled. Dangerous tools are off unless the server operator restarts the MCP "
                    "server with HIL_ALLOW_DANGEROUS=1. The assistant cannot enable this itself.",
                    refused=True)
    if confirm is not True:
        return _err(f"{tool} changes the state of the bench and needs confirm=true. Ask the user first.",
                    refused=True)
    return None


def flash_command() -> list[str]:
    """Fixed command: the repo's own Board 1 elf through the repo's flash script."""
    return ["bash", FLASH_SCRIPT_REL, BOARD1_ELF_REL]


def flash(confirm=False) -> dict:
    refusal = _gate("hil_flash", confirm)
    if refusal:
        return refusal
    if backend() != "rig":
        return _err("hil_flash only applies to the real rig (server started with HIL_BACKEND=rig)", refused=True)
    if not (REPO / BOARD1_ELF_REL).is_file():
        return _err(f"{BOARD1_ELF_REL} not found; build Board 1 first (cmake --preset Debug && "
                    "cmake --build --preset Debug in Superheat_Control)")
    missing = [t for t in ("bash", "openocd") if shutil.which(t) is None]
    if missing:
        return _err(f"not on PATH: {', '.join(missing)}")
    try:
        with _exclusive():
            proc = _run(flash_command(), REPO, 180)
    except BenchBusy as e:
        return _err(str(e))
    except subprocess.TimeoutExpired:
        return _err("openocd timed out after 180 s")
    text = (proc.stdout + proc.stderr)
    return {"ok": proc.returncode == 0, "exit_code": proc.returncode, "elf": BOARD1_ELF_REL,
            "verified": "Verified OK" in text, "output_tail": text.strip().splitlines()[-8:]}


def reset(confirm=False) -> dict:
    refusal = _gate("hil_reset", confirm)
    if refusal:
        return refusal
    try:
        with _exclusive():
            b, _ = _open_board()
            try:
                start = b.line_mark()
                b.reset()
                header = b.wait_line(lambda l: l == ",".join(hil_board.CSV_FIELDS), 3.0 + 3 * b.period, start)
                first = b.wait_for(lambda r: r.tick <= 2, max_rows=5) if header else None
            finally:
                b.close()
    except (BenchBusy, RuntimeError, TimeoutError, OSError) as e:
        return _err(str(e), backend=backend())
    return {"ok": header is not None and first is not None, "backend": backend(),
            "header_seen": header is not None, "first_row_after_reset": _row_dict(first) if first else None}


def _load_hil_conftest():
    """tests/hil/conftest.py under a private name, so it can't collide with any
    other module called 'conftest' (pytest registers those under that name)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("hil_conftest", HIL_DIR / "conftest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def inject_link_fault(confirm=False, ticks=10) -> dict:
    refusal = _gate("hil_inject_link_fault", confirm)
    if refusal:
        return refusal
    if isinstance(ticks, bool) or not isinstance(ticks, int) or not 1 <= ticks <= 30:
        return _err("ticks must be an integer 1..30")
    hil_conftest = _load_hil_conftest()  # reuse the bench's own link cutters
    gpio = None
    try:
        with _exclusive():
            if backend() == "rig":
                gpio, problem = configured_mute_gpio()
                if problem:
                    return _err(problem)
                if not gpio_library_available():
                    return _err("gpiozero not available on this machine")
            b, rig = _open_board()
            try:
                cutter = hil_conftest._SimLinkCut(rig) if backend() == "sim" else hil_conftest._GpioLinkCut(gpio)
                start = b.mark()
                cutter.cut()
                try:
                    b.wait_rows(ticks, start)
                finally:
                    cutter.restore()
                    cutter.close()
                b.wait_rows(ticks + 4, start)
                rows = b.rows_since(start)
            finally:
                b.close()
    except (BenchBusy, RuntimeError, TimeoutError, OSError) as e:
        return _err(str(e), backend=backend())
    a = analyze_rows(rows)
    return {"ok": True, "backend": backend(), "muted_ticks": ticks, "link": a["link"], "rows": len(rows)}


def ci_status() -> dict:
    gh = shutil.which("gh")
    if gh is None:
        return {"ok": True, "available": False, "reason": "gh CLI not installed"}
    try:
        proc = _run([gh, "run", "list", "--workflow", "hil.yml", "--limit", "5", "--json",
                     "status,conclusion,displayTitle,headSha,createdAt,url"], REPO, 30)
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"ok": True, "available": False, "reason": f"gh failed: {e}"}
    if proc.returncode != 0:
        return {"ok": True, "available": False, "reason": (proc.stderr or proc.stdout).strip()[:300]}
    import json

    try:
        runs = json.loads(proc.stdout or "[]")
    except ValueError:
        return {"ok": True, "available": False, "reason": "unexpected gh output"}
    for r in runs:
        r["headSha"] = (r.get("headSha") or "")[:8]
    return {"ok": True, "available": True, "runs": runs}


# --- MCP wiring --------------------------------------------------------------

from mcp.server.fastmcp import FastMCP  # noqa: E402
import anyio.to_thread  # noqa: E402

mcp = FastMCP(
    "hil-bench",
    instructions=(
        "Tools for the Superheat Control HIL test bench (Board 1 PI controller, Board 2 plant, pytest suite). "
        "Default backend is the simulator. Report facts from tool output; label guesses as hypotheses. "
        "Dangerous tools (flash/reset/link fault) are refused unless the operator enabled them, and need "
        "confirm=true: ask the user before setting it."
    ),
)


async def _off_loop(fn, *args, **kwargs):
    # Tools block on subprocesses and serial I/O; keep the stdio event loop responsive.
    return await anyio.to_thread.run_sync(functools.partial(fn, *args, **kwargs))


@mcp.tool()
async def hil_status() -> dict:
    """Backend in use (sim or rig), Board 1 serial port, GPIO availability, dangerous-tool flag, last run."""
    return await _off_loop(status)


@mcp.tool()
async def hil_run_tests(test: str | None = None, sim_kp: float | None = None, sim_ki: float | None = None) -> dict:
    """Run the pytest HIL suite (simulator unless the server runs with HIL_BACKEND=rig).

    test: optional filter: all, boot, step, windup, link_loss, or a full test name.
    sim_kp / sim_ki: simulator only, override the PI gains (e.g. sim_kp=0.3 to see the tests fail).
    Returns pass/fail per test with overshoot, settling ticks, undershoot and valve limits.
    """
    return await _off_loop(run_tests, test, sim_kp, sim_ki)


@mcp.tool()
async def hil_get_last_results() -> dict:
    """Read tests/hil/out (junit.xml and each test's CSV) and summarise the last results."""
    return await _off_loop(get_last_results)


@mcp.tool()
async def hil_explain_failure(test: str) -> dict:
    """Facts from a test's CSV (overshoot, settling, oscillation, valve saturation, link_ok transitions),
    the test's limits re-checked, then clearly labelled hypotheses about what went wrong.
    test: boot, step, windup, link_loss, or a full test name."""
    return await _off_loop(explain_failure, test)


@mcp.tool()
async def hil_plot(test: str) -> dict:
    """Plot a test's CSV with tools/plot_from_log.py; returns the PNG path.
    test: boot, step, windup, link_loss, or a full test name."""
    return await _off_loop(plot, test)


@mcp.tool()
async def hil_set_setpoint(value: float) -> dict:
    """Send 'sp <value>' (0..40 degC) to Board 1 and confirm from the CSV stream.
    On the simulator backend this drives a throwaway simulated rig."""
    return await _off_loop(set_setpoint, value)


@mcp.tool()
async def hil_ci_status() -> dict:
    """Recent runs of the HIL GitHub Actions workflow via `gh run list`; not-available if gh is missing."""
    return await _off_loop(ci_status)


@mcp.tool()
async def hil_flash(confirm: bool = False) -> dict:
    """DANGEROUS, real rig only: flash the repo's Board 1 elf with tools/hil/flash.sh.
    Disabled unless the server runs with HIL_ALLOW_DANGEROUS=1; needs confirm=true. Takes no path."""
    return await _off_loop(flash, confirm)


@mcp.tool()
async def hil_reset(confirm: bool = False) -> dict:
    """DANGEROUS: software-reset Board 1 ('reset' command) and check it boots.
    Disabled unless the server runs with HIL_ALLOW_DANGEROUS=1; needs confirm=true."""
    return await _off_loop(reset, confirm)


@mcp.tool()
async def hil_inject_link_fault(confirm: bool = False, ticks: int = 10) -> dict:
    """DANGEROUS: mute Board 2's replies for `ticks` (1..30) control ticks, then restore; reports link_ok
    transitions and the valve while down. Disabled unless HIL_ALLOW_DANGEROUS=1; needs confirm=true."""
    return await _off_loop(inject_link_fault, confirm, ticks)


if __name__ == "__main__":
    mcp.run()  # stdio
