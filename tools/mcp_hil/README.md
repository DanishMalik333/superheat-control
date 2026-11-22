# hil-bench: a safe-first MCP server for the HIL test bench

An [MCP](https://modelcontextprotocol.io) server that lets an AI assistant
(Claude Code, or any MCP client) use the existing HIL test bench: run the
pytest suite, read the results, explain a failure from the logged data, plot a
run, change the setpoint and check CI.

It is a thin layer over code that already exists. It doesn't model the
controller or redefine the tests:

| Server feature | Reuses |
|---|---|
| Running tests | `tests/hil` through pytest (`--sim`, or `--port`/`--mute-gpio` on the rig) |
| Parsing CSV rows | `board.Row.parse`, `board.VALVE_MIN/MAX` |
| Pass limits in `hil_explain_failure` | Constants imported from `test_step.py`, `test_windup.py`, `test_link_loss.py` |
| Setpoint, reset, link fault | `board.Board1` on `sim.SimRig` or a pyserial port; `conftest._SimLinkCut` / `_GpioLinkCut` |
| Plots | `tools/plot_from_log.py` |
| Flash | `tools/hil/flash.sh` with the Board 1 elf, as in `.github/workflows/hil.yml` |

Transport: stdio. SDK: the official `mcp` Python package, `FastMCP` API
(pinned to `mcp==1.30.0`, because mcp 2.x renamed `FastMCP` to `MCPServer`).

## Tools

| Tool | What it does | Touches hardware? |
|---|---|---|
| `hil_status` | Backend (sim/rig), Board 1 serial port found?, gpiozero available?, mute GPIO, dangerous flag, last run time | No (lists ports only) |
| `hil_run_tests(test?, sim_kp?, sim_ki?)` | Runs pytest on `tests/hil` with a timeout. Returns pass/fail per test with overshoot %, settling ticks, undershoot %, valve min/max, saturation ticks, link transitions | Rig only if started with `HIL_BACKEND=rig` |
| `hil_get_last_results` | Reads `tests/hil/out/junit.xml` and every test's CSV | No |
| `hil_explain_failure(test)` | Facts from the CSV, the test's own limits re-checked, then hypotheses labelled `HYPOTHESIS:` | No |
| `hil_plot(test)` | Runs `tools/plot_from_log.py`, returns the PNG path | No |
| `hil_set_setpoint(value)` | Sends `sp <value>` (0..40 °C) and confirms it from the CSV stream. On the sim backend it drives a throwaway simulated rig | Rig only on the rig backend |
| `hil_ci_status` | `gh run list --workflow hil.yml`; returns `available: false` if `gh` is missing or fails | No |
| `hil_flash(confirm)` | **Dangerous.** Flashes `Superheat_Control/build/Debug/Superheat_Control.elf` via `tools/hil/flash.sh`. Rig only. Takes no path | Yes |
| `hil_reset(confirm)` | **Dangerous.** Sends `reset`, checks the CSV header comes back | Yes on rig |
| `hil_inject_link_fault(confirm, ticks)` | **Dangerous.** Mutes Board 2 for 1..30 ticks, reports `link_ok` transitions and the valve while down | Yes on rig |

`test` accepts `all`, `boot`, `step`, `windup`, `link_loss`, or a full test
name such as `test_step_response`. Anything else is refused.

## Install

Windows (sim backend, no hardware needed), from the repo root:

```powershell
py -3.13 -m venv tools\mcp_hil\.venv
tools\mcp_hil\.venv\Scripts\python.exe -m pip install -r tools\mcp_hil\requirements.txt
tools\mcp_hil\.venv\Scripts\python.exe -m pytest tools\mcp_hil      # the server's own tests
```

Linux / Raspberry Pi:

```bash
python3 -m venv --system-site-packages tools/mcp_hil/.venv   # sees apt's gpiozero on the Pi
tools/mcp_hil/.venv/bin/pip install -r tools/mcp_hil/requirements.txt
```

`.venv/` is ignored by `tools/mcp_hil/.gitignore`.

## Register it in Claude Code

Simulator (the default, safe on any PC). Windows, from the repo root:

```powershell
claude mcp add hil-bench -- "$PWD\tools\mcp_hil\.venv\Scripts\python.exe" "$PWD\tools\mcp_hil\server.py"
```

Linux / macOS, from the repo root:

```bash
claude mcp add hil-bench -- "$PWD/tools/mcp_hil/.venv/bin/python" "$PWD/tools/mcp_hil/server.py"
```

Real rig, on the Pi (dangerous tools still off):

```bash
claude mcp add hil-bench -e HIL_BACKEND=rig -e HIL_MUTE_GPIO=17 -- \
    ~/superheat-control/tools/mcp_hil/.venv/bin/python ~/superheat-control/tools/mcp_hil/server.py
```

Then check with `claude mcp list` or `/mcp` inside Claude Code. The default
scope is `local` (your user config for this project), so nothing is written to
the repo. `-s project` would create a `.mcp.json` in the repo instead.

## Running the tests

### On the simulator (any PC, no hardware)

The same suite the server runs, straight from pytest:

```bash
# from the repo root
python -m pytest tests/hil --sim                 # shipped gains: all pass
python -m pytest tests/hil --sim --sim-kp 0.3    # broken gains: tests fail
```

Or ask the assistant: "Run the step test and tell me the overshoot."

### On the hardware (Raspberry Pi with both boards)

Wiring and one-time setup are in `docs/HIL_TEST_BENCH.md` (Board 1 on the
Pi's USB, Board 2 flashed once, Pi GPIO17 to Board 2 D4, common GND).

1. Stop the CI runner so it can't take the serial port while you work:
   `sudo ./svc.sh stop` in `~/actions-runner`.
2. Run the suite directly to check the rig:
   ```bash
   ~/hil-venv/bin/python -m pytest tests/hil --mute-gpio 17
   ```
3. Register the server with `HIL_BACKEND=rig` (see "Register it in Claude
   Code" above). Optionally pin the port with `-e HIL_PORT=/dev/ttyACM0`.
4. Ask the assistant to run the tests, for example "Run the whole suite and
   summarise the results".
5. Flash, reset and link-fault injection stay off. To enable them, start the
   server with `-e HIL_ALLOW_DANGEROUS=1`; every call then still needs
   `confirm=true`.
6. When finished: `sudo ./svc.sh start` to bring the CI runner back.

### Server configuration (environment)

| Variable | Default | Meaning |
|---|---|---|
| `HIL_BACKEND` | `sim` | `rig` uses the real boards. Any other value means `sim` (and `hil_status` warns) |
| `HIL_ALLOW_DANGEROUS` | unset | Exactly `1` enables flash/reset/link-fault (they still need `confirm=true`) |
| `HIL_PORT` | auto-detect | Board 1 VCP, e.g. `/dev/ttyACM0` or `COM4`. Must look like a serial port name |
| `HIL_MUTE_GPIO` | unset | BCM pin wired to Board 2 D4 (2..27). Without it the rig link-loss test is skipped |
| `HIL_TIMEOUT_S` | 180 sim / 1200 rig | pytest timeout, 10..3600 |

## Example prompts

- "What's the HIL bench status?"
- "Run the step test and tell me the overshoot and settling time."
- "Run the whole suite with sim_kp 0.3 and explain why it fails."
- "Explain the windup test result. Facts first, then your hypotheses."
- "Plot the link-loss run."
- "Is the last HIL CI run on main green?"
- "Set the setpoint to 12 °C." (rig backend: Board 1 keeps it until reset)

## Safety model

1. **Simulator by default.** The backend is fixed when the server starts
   (`HIL_BACKEND`). The assistant can't switch to the rig.
2. **No caller-supplied paths or commands.** Test names go through an
   allowlist. Every subprocess gets a fixed argument list, `shell=True` is never
   used, and child processes get `stdin=DEVNULL`, so they can't read the MCP
   stream. Plot output goes next to the CSV in `tests/hil/out`. `hil_flash` has
   no path argument: it only ever flashes the repo's Board 1 elf.
3. **Validated values.** Setpoint 0..40 °C (the firmware's own range), sim
   gains 0 < k ≤ 2, fault length 1..30 ticks, and `HIL_PORT`/`HIL_MUTE_GPIO`
   checked against a pattern.
4. **Dangerous tools need two switches.** The operator starts the server with
   `HIL_ALLOW_DANGEROUS=1`, and each call passes `confirm=true`. Without the
   flag they refuse with a message saying how to enable them. The tool
   description tells the assistant to ask the user before confirming.
5. **One bench operation at a time.** A lock makes a second operation fail
   with "busy" instead of two processes fighting over the serial port.
6. **Timeouts everywhere**: pytest (180 s sim / 1200 s rig), plot 120 s,
   flash 180 s, `gh` 30 s.
7. **Honest output.** `hil_explain_failure` separates measured facts, checks
   against the test's own limits, and labelled hypotheses. It also says what
   the CSV can't show (fault latency, header timing).

What it does **not** protect against: someone who can change the server's
environment or edit the repo (e.g. `tests/hil` or `flash.sh`) controls what
runs. The CI runner and this server can both open the rig's serial port; stop
the runner service before using rig mode by hand (see "Day-to-day use" in
`docs/HIL_TEST_BENCH.md`).

## Tests

```powershell
tools\mcp_hil\.venv\Scripts\python.exe -m pytest tools\mcp_hil
```

Each test works on a temporary copy of `tests/hil`, so the repo's
`tests/hil/out` is never overwritten. They cover:

- allowlist validation (path traversal, shell metacharacters, flags), sim gain
  limits, rig arguments coming only from the server environment
- setpoint range, including NaN/inf/bool/strings, and a real `sp` on the sim
- dangerous tools: refused without the flag (with or without confirm), refused
  without a literal `confirm=true`, flash with no path argument and refused on
  the sim, reset and link fault working on the sim once enabled
- junit and CSV parsing, segment metrics, oscillation detection, busy lock,
  timeout handling, `gh` missing or failing
- end to end on the simulator: shipped gains pass (overshoot about 2.3 %,
  settling 4 ticks, no hypotheses); `sim_kp=0.3` fails 3 tests and
  `hil_explain_failure` reports oscillation, a limit cycle between both valve
  clamps, and "gains too high" as a hypothesis
- `tests/test_mcp_stdio.py`: a real MCP stdio session using the SDK client
  (initialize, list tools, `hil_status`, `hil_run_tests` on the sim, a refused
  test name and a refused `hil_flash`)

