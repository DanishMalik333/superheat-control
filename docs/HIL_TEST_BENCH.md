# HIL Test Bench: How It Works

This explains the automated hardware-in-the-loop (HIL) test bench: what was
added, why each piece exists, and what happens from `git push` to a pass or
fail. For setup commands, see the "Automated HIL tests" section of the
[README](../README.md).

## 1. The problem

Before this change the rig was a **live demo**. You flashed both boards,
watched the LCD and the serial plot, and decided by eye whether the loop
behaved. Nothing stopped a bad commit, such as wrong PI gains, a broken
anti-windup or a link bug, from reaching `main`.

The goal was to turn the demo into a **test**. A script drives the real
hardware, measures the closed-loop response, and decides pass or fail with
no human watching. It runs on every push, so every commit is tested in
closed loop on real hardware.

## 2. The setup, and the one-cable constraint

There is only one USB cable, so only one board can be reached from the host.
It goes to **Board 1**, the controller and the board under test:

```
  GitHub push
       │
       ▼
  Raspberry Pi 4  (GitHub Actions self-hosted runner, label "hil")
       │ USB: ST-LINK (flash) + VCP (log + commands)      │ GPIO17 + GND
       ▼                                                   ▼
  ┌─────────┐          USART1 link (115200)          ┌─────────┐
  │ Board 1 │ ◄────────────────────────────────────► │ Board 2 │
  │ PI ctrl │                                        │ plant   │  D4 = link mute
  └─────────┘                                        └─────────┘
```

- **Board 1** is rebuilt and reflashed on every run, because it is the code
  being tested.
- **Board 2** is the plant model. It rarely changes, so it is flashed once by
  hand (move the cable over, flash, move it back) and then left alone. The
  tests treat it as fixed test equipment.
- **The Pi's GPIO17** replaces a second USB connection for the one thing the
  tests need from Board 2: making it go silent on demand.

## 3. What changed in the firmware

The tests can only check what the firmware lets them see and control. Four
things were missing.

### 3.1 A way to command Board 1: VCP commands

Before, USART2 (the ST-LINK virtual COM port) only sent data. It now also
receives, using the same interrupt-driven, line-at-a-time scheme as the
inter-board link:

```
byte arrives ─► USART2 IRQ ─► HAL_UART_RxCpltCallback ─► Cmd_RxByte()
                                                          │ on '\n' or '\r'
                                                          ▼
                                    vTaskNotifyGiveFromISR(CommandTask)
                                                          │
                                                          ▼
                                     CommandTask parses and acts on the line
```

| Command | Effect | Reply |
|---|---|---|
| `sp 13.0` | Set the superheat setpoint (0–40 °C) | `# ok sp 13.00` |
| `ping` | Check the firmware supports commands | `# pong` |
| `reset` | Software reset (`NVIC_SystemReset`) | `# resetting` |

The setpoint used to be the compile-time constant `SETPOINT_DEGC`. It is now
a `volatile float` that CommandTask writes and ControlTask and the LCD read.
As with the other shared floats, an aligned 32-bit access is atomic on the
Cortex-M4, so no lock is needed.

The USART2 interrupt isn't enabled in the `.ioc`. It is enabled in the
`USER CODE` sections of `stm32f4xx_hal_msp.c` and `stm32f4xx_it.c`, so
regenerating with CubeMX won't remove it.

### 3.2 Link fault detection: a safety behaviour to test

Before, if Board 2 stopped replying, Board 1 printed a warning and kept
running the PI on a stale measurement forever. The integrator went on acting
on old data.

Now:

1. **LinkTask** counts consecutive missed replies. After **2 in a row**
   (`LINK_FAULT_MISSES`) it clears `link_ok` and prints `# FAULT link lost`.
2. **ControlTask** sees `link_ok == 0`. It stops calling `PID_Update`, so the
   integrator is frozen, and holds the valve at `VALVE_SAFE` (0.3). The LCD
   shows `--.-` for superheat.
3. When a reply arrives again, `link_ok` returns to 1. ControlTask seeds the
   integrator with 0.3 (a bumpless restart), so the valve continues smoothly
   from where it was held instead of jumping.

Two misses rather than one, so a single corrupted frame doesn't trip a fault.

### 3.3 A visible fault state: the `link_ok` CSV column

Each CSV row now ends with `link_ok`:

```
tick,bme280_degC,plant_degC,valve,setpoint_degC,link_ok
57,24.82,9.9953,0.500,10.00,1
```

The tests read everything from this stream: superheat, valve, setpoint and
link state. `plot_live.py` handles both the new 6-column and the old
5-column format.

### 3.4 A way to break the link on purpose: the mute pin on Board 2

Board 2's PB5 (header pin D4) is an input with a pull-down. While it is
**high**, Board 2 still receives each frame and updates the plant, but sends
**no reply**. LD2 lights up meanwhile.

This is **fault injection**: it reproduces a cut reply wire without anyone
touching the rig. The plant keeps evolving during the fault, as a real
evaporator would. The pull-down means an unconnected pin is harmless, so the
board behaves normally without the Pi.

### 3.5 Thread-safety fixes found in review

A separate review pass found two real bugs, both now fixed:

- **A command could be lost for good at boot.** If a command line finished
  before the FreeRTOS scheduler started, the ISR set the "line ready" flag
  but couldn't notify CommandTask. CommandTask blocked forever, and the ISR
  dropped all later bytes because the flag was still set. Fix: CommandTask
  checks the flag *before* blocking:
  `while (!cmd_rx_line_ready) ulTaskNotifyTake(...)`.
- **Output from different tasks could interleave.** `printf` sends one
  character at a time, and newlib-nano's float formatting and parsing share
  global state (the stdout buffer and a Bigint freelist) with no locking.
  Two tasks printing at once could garble a CSV row or drop the `# pong` the
  tests wait for. Fix: tasks print through `log_printf`, which formats into a
  local buffer and sends the whole line in one transmit under a mutex with
  priority inheritance. Every task-side `snprintf`, `sscanf` and `strtod`
  also holds that mutex.

Smaller fixes:

- `HAL_UART_ErrorCallback` re-arms reception after a UART overrun, on both
  boards. Before, an overrun silently killed reception until reset.
- An overlong command line is discarded completely, so its tail can't run as
  a command.
- `sp 12abc` is rejected.

## 4. The tests

Everything lives in `tests/hil/`:

| File | Role |
|---|---|
| `board.py` | Talks to Board 1: a reader thread parses the serial stream into `Row`s; helpers send commands, wait for rows and settle the loop |
| `conftest.py` | pytest options (`--port`, `--mute-gpio`, `--sim`) and fixtures; saves each test's rows to `tests/hil/out/<test>.csv` |
| `sim.py` | Software model of the whole rig (section 5) |
| `test_*.py` | The tests |

### 4.1 What each test checks

| Test | Procedure | Pass criteria |
|---|---|---|
| `test_boot` | Send `reset` | CSV header within 3 s, then data rows; `link_ok` is 1 a few ticks after boot |
| `test_step` | Settle at 10 °C, step to 13 °C, watch 60 ticks | Overshoot < 10 % of the step; within ±0.3 °C after 30 ticks; valve always within its clamp [0.1, 0.9] and never NaN |
| `test_windup` | Settle at 10, set 30 °C (out of reach, so the valve sits at 0.9) for 40 ticks, then back to 10 | The valve really did saturate; undershoot < 10 % of the drop; within ±0.5 °C after 40 ticks |
| `test_link_loss` | Settle at 10, set GPIO17 high for 10+ ticks, then low | `link_ok` drops within 6 ticks; valve exactly 0.3 while it is down; link back within 4 ticks; loop returns to 10 °C |

Every test starts by **settling** the loop at a known setpoint (±0.3 °C for 5
rows in a row). That way each test is independent of the ones before it and
of where the plant happened to be.

### 4.2 Why the tests count ticks, not seconds

Board 1 prints one row per control tick (1 s). The tests express time as
*rows*: "settled within 30 ticks", "fault within 6 ticks". Wall-clock
timeouts are derived from the row period. This does two things:

- The same test code runs on the real rig (1 row/s) and on the simulator
  (50 rows/s) without changes.
- The test follows the controller's own clock, not the Pi's, so host load
  doesn't cause flaky failures.

### 4.3 Where the limits come from

The limits are calculated, not guessed. The PI law and plant are known
exactly, so the closed loop can be simulated:

| Gains | Step overshoot | Settles? | Windup undershoot | Result |
|---|---|---|---|---|
| Kp=0.1, Ki=0.015 (shipped) | 2.3 % | yes, ~4 ticks | 0 % | **pass** |
| Kp=0.3 | 24 % | no (oscillates) | 18 % | **fail** |
| Ki=0.1 | 34 % | no | 21 % | **fail** |
| Kp=0.05, Ki=0.005 (slower, stable) | 0 % | yes, ~17 ticks | 6 % | pass |
| Shipped gains, anti-windup removed | – | – | large | **fail** (windup test) |

The limits (10 % overshoot, 30-tick settling) leave room for real-world
noise, mostly the BME280 ambient drifting into the plant as a disturbance.
They still clearly catch broken tuning. A slower but stable tune passes,
which is intended: the tests check that the loop is *correct*, not that it
uses one exact tuning.

### 4.4 Tests that can't pass by accident

A test that passes when the feature is broken is worse than no test. Some
checks exist only to prevent that:

- `test_windup` asserts that the valve **actually saturated** for the last 10
  ticks before it judges the recovery. Otherwise it would prove nothing.
- `test_link_loss` checks both `link_ok == 0` **and** valve == 0.3. Either
  one alone could look right by coincidence.
- `test_boot` requires the CSV header, which is only printed at startup, so
  it can't pass without a real reset.
- The row parser rejects any row whose `link_ok` isn't exactly `0` or `1`.
  A garbled row is dropped rather than read as "link down".

## 5. The simulator (`--sim`)

`sim.py` is a Python model of both boards behind the same interface as the
serial port. It runs the same PI law, plant, fault logic and commands as the
firmware, 50 times faster than real time.

Its timing matches the hardware: superheat at tick *k* responds to the valve
command from tick *k−2*. One tick comes from the `ValveOutputQueue` hand-off
between tasks, and one from the plant's `u[n-1]` term. Fed the initial state
of a logged hardware run, it reproduces that log to 4 decimal places.

It is used for:

- **Developing the tests** without the rig. The whole suite runs in about
  6 seconds.
- **Checking that the tests catch bugs**: `--sim-kp 0.3` must fail.
- **Running in CI with no hardware**, if wanted later.

It does **not** replace the rig. It models the firmware as written, so it
can't catch timing, UART, RTOS or hardware bugs. Only the real boards can.

## 6. What happens on a push

```
git push origin main
   │
   ▼
GitHub queues the "HIL" workflow ──► Pi runner (label "hil") picks it up
   │                                 (one run at a time: concurrency group "hil-rig")
   ▼
1. checkout          clean copy of the repo
2. build Board 1     cmake --preset Debug && cmake --build --preset Debug
3. flash Board 1     tools/hil/flash.sh → OpenOCD: program, verify, reset
4. run tests         pytest tests/hil --mute-gpio 17 --junitxml=...
5. plot              tools/plot_from_log.py for each tests/hil/out/*.csv (always runs)
6. upload            "hil-results" artifact: CSVs, PNGs, junit.xml (always runs)
   │
   ▼
✔ green  or  ✘ red, with step-response plots attached either way
```

Steps 5 and 6 run even when tests fail. The plot of a failed run is usually
the fastest way to see *why* it failed.

## 7. How the Pi gets jobs from GitHub

**The Pi pulls jobs from GitHub. GitHub never connects into the Pi.** The
runner program on the Pi keeps an *outbound* HTTPS connection open to GitHub
and keeps asking "any job for me?". So the Pi needs no public IP, no open
ports and no router setup. It can sit behind a home NAT on Wi-Fi.

```
  Raspberry Pi (home network, behind NAT)                GitHub
  ┌──────────────────────────────┐                ┌────────────────────────┐
  │ actions-runner service       │  HTTPS :443    │ Actions job queue      │
  │  (Runner.Listener)           │ ─────────────► │                        │
  │                              │  "any job for  │ push to main ─► job    │
  │                              │   labels       │ queued: needs          │
  │                              │   self-hosted, │ [self-hosted, hil]     │
  │                              │   hil?"        │                        │
  │                              │ ◄───────────── │                        │
  │                              │  job + short-  │                        │
  │                              │  lived token   │                        │
  └──────────────────────────────┘                └────────────────────────┘
```

1. **Registration (once).** GitHub gives you a one-time **registration
   token**, which expires after about an hour. `config.sh` on the Pi trades
   it for the runner's own long-lived credentials, stored in the hidden
   files `.runner` and `.credentials` in the runner folder. From then on
   GitHub lists the Pi under *Settings → Actions → Runners*.
2. **Waiting for work.** The runner service (`Runner.Listener`, run by
   systemd) **long-polls** GitHub. It opens an HTTPS request, and GitHub holds
   it open for up to about 50 seconds. If a job arrives during that time,
   GitHub answers at once. If not, the request times out and the runner
   opens a new one. Jobs start within a second or two, with very little
   traffic while idle.
3. **A push queues a job.** On a push to `main`, GitHub reads
   `.github/workflows/hil.yml`. The job asks for
   `runs-on: [self-hosted, hil]`, so it waits in the queue for a runner that
   has **all** of those labels. GitHub's cloud machines will never take it.
4. **Assignment.** GitHub answers the Pi's open request with the job and a
   short-lived token valid only for that job. Because the workflow sets
   `permissions: contents: read`, that token can read the repo but not
   change it.
5. **Running.** `Runner.Worker` runs the steps locally on the Pi, as the user
   the service runs as. `actions/checkout` uses the job token to clone the
   repo over HTTPS. Then come cmake, OpenOCD and pytest. Logs stream back
   live, which is why you can watch the run in the Actions tab.
6. **Reporting back.** The runner uploads the artifact and the step results,
   GitHub marks the run green or red, and the runner goes back to step 2.

| Situation | What happens |
|---|---|
| Pi off or offline when you push | The job waits: "Waiting for a runner to pick up this job…". GitHub cancels it after 24 h. The Pi picks it up when it reconnects. |
| Two pushes in quick succession | A runner takes one job at a time. The `concurrency: hil-rig` group also queues them in order, so two runs never fight over the boards. |
| Network the Pi needs | Outbound HTTPS to `github.com`, `api.github.com`, `*.actions.githubusercontent.com` and the artifact storage hosts. Normal home internet is enough. |

GitHub shows the runner's state under *Settings → Actions → Runners*:
**Idle** (connected, waiting), **Active** (running a job) or **Offline**.

**Security.** Anyone who can get a workflow to run on this runner runs code
on your Pi, inside your home network, as the runner's user. So:

- The workflow runs only on push to `main` and on manual runs, never on pull
  requests, and its token is read-only.
- In *Settings → Actions → General → Fork pull request workflows*, require
  approval for all outside contributors. The repo is public, and a fork's
  pull request could otherwise add its *own* workflow that targets the Pi.
- Run the runner as its own user with no `sudo` and no access to your home
  folder, never as root or as your login user. On this rig it runs as
  `hil-runner` (groups `dialout`, `plugdev`, `gpio` only) with its own
  `~/hil-venv`. Raspberry Pi OS shares the sudo password cache across all of
  a user's processes (`timestamp_type=global`), so a job running as your own
  user minutes after you typed your sudo password could get root.

## 8. Setting up the Pi and running everything

Do this once, in order. Each phase ends with a check, so if something breaks
you know which step caused it.

### What you need

- Raspberry Pi 4 with a microSD card (16 GB or more) and its official power
  supply. The Pi also powers Board 1 over USB.
- Board 1 and Board 2 wired together as they are today (USART1 link, common
  GND, Board 2 powered through E5V).
- Your one USB cable (Pi to Nucleo ST-LINK).
- 2 female-to-female jumper wires (Pi GPIO header to Nucleo header).

### Phase 1: Install the OS

1. On your PC, open **Raspberry Pi Imager**. Choose *Raspberry Pi 4*,
   *Raspberry Pi OS (64-bit)* (Bookworm), and your SD card.
2. In the settings (gear or "Edit settings"), set a hostname (for example
   `hil-pi`) and a username and password, enter your Wi-Fi details, and
   **enable SSH**.
3. Write the card, put it in the Pi, power it on, wait about a minute, then
   from your PC:
   ```bash
   ssh <user>@hil-pi.local
   ```

✔ **Check:** you get a shell on the Pi.

### Phase 2: Toolchain and Python environment

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/DanishMalik333/superheat-control.git
cd superheat-control
bash tools/hil/setup_pi.sh
```

The script installs `gcc-arm-none-eabi`, CMake, Ninja, OpenOCD and gpiozero.
It adds you to the `dialout` (serial port), `plugdev` (ST-LINK USB) and
`gpio` groups, and creates the Python venv `~/hil-venv`. **Log out and SSH
back in** so the new groups apply.

✔ **Check:**
```bash
groups                                      # includes dialout plugdev gpio
arm-none-eabi-gcc --version | head -1
openocd --version 2>&1 | head -1
~/hil-venv/bin/python -m pytest tests/hil --sim   # 5 passed, about 6 s
```
The last line runs the whole suite against the simulator, so the Python side
works before any hardware is connected.

### Phase 3: Flash Board 2 once

Board 2 needs the firmware with the mute pin, and this is the only time it
needs the cable.

1. Plug the USB cable from the Pi into **Board 2**.
2. Build and flash:
   ```bash
   cd ~/superheat-control/HVACPlant
   cmake --preset Debug && cmake --build --preset Debug
   cd ..
   bash tools/hil/flash.sh HVACPlant/build/Debug/HVACPlant.elf
   ```
   OpenOCD should finish with `** Verified OK **` and `** Resetting Target **`.
3. Unplug and move the cable to **Board 1**.

> Keep Board 2 on its E5V supply. With JP5 in the E5V position the USB cable
> only powers the ST-LINK part, not the target. The Nucleo user manual
> (UM1724) says to apply E5V *before* plugging in USB.

✔ **Check:** OpenOCD printed `Verified OK`.

### Phase 4: Wire the mute line

| Raspberry Pi 4 header | Board 2 Nucleo header |
|---|---|
| GPIO17, physical pin 11 | D4 (PB5), Arduino connector CN9 |
| GND, physical pin 9 | any GND pin |

```
Pi 40-pin header: odd pins on the inner row (towards the middle of the board),
even pins on the outer edge; pin 1 is at the end away from the USB ports

   (1)  3V3      ●  ●  5V     (2)
   (3)  GPIO2    ●  ●  5V     (4)
   (5)  GPIO3    ●  ●  GND    (6)
   (7)  GPIO4    ●  ●  GPIO14 (8)
   (9)  GND      ●  ●  GPIO15 (10)    ◄── pin 9  → Board 2 GND
  (11)  GPIO17   ●  ●  GPIO18 (12)    ◄── pin 11 → Board 2 D4
```

Both sides are 3.3 V logic, so no resistor or level shifter is needed.
**Don't** connect any Pi 5V pin to the Nucleo.

✔ **Check:** test the mute by hand (Board 2's LD2 should light):
```bash
~/hil-venv/bin/python -c "from gpiozero import LED; import time; p=LED(17); p.on(); time.sleep(3); p.off()"
```
LD2 only updates when a frame arrives, so Board 1 has to be running. It
lights within about 1 s and goes off again after the 3 s.

### Phase 5: Flash Board 1 and run the tests by hand

```bash
cd ~/superheat-control/Superheat_Control
cmake --preset Debug -DBME280_BUS=SPI      # or I2C, matching your wiring
cmake --build --preset Debug
cd ..
bash tools/hil/flash.sh Superheat_Control/build/Debug/Superheat_Control.elf
```

✔ **Check:** the board talks and answers commands:
```bash
ls /dev/serial/by-id/                    # one ...STLink... entry
~/hil-venv/bin/python -m serial.tools.miniterm /dev/ttyACM0 115200
```
You should see a CSV row every second, ending in `,1`. Type `ping` and press
Enter to get `# pong`. Leave miniterm with `Ctrl+]`.

Then run the whole suite against the real rig (about 6 minutes):
```bash
~/hil-venv/bin/python -m pytest tests/hil --mute-gpio 17
```

✔ **Check:** `5 passed`. If a test fails, plot its run and look before
changing anything:
```bash
MPLBACKEND=Agg ~/hil-venv/bin/python tools/plot_from_log.py \
    tests/hil/out/test_step_response.csv --out step.png
```
(Copy the PNG to your PC with `scp <user>@hil-pi.local:~/superheat-control/step.png .`)

The pass limits so far have only been checked against the simulator. If a
correct build fails on real hardware, loosen that one limit in the test file
and note why.

### Phase 6: Register the Pi as a GitHub runner

1. On GitHub, open the repo, then *Settings → Actions → Runners → New
   self-hosted runner*. Choose **Linux** and **ARM64**.
2. GitHub shows a block of commands. Run them on the Pi **in a new folder
   outside the repo**, for example `~/actions-runner`: `mkdir`, `curl`
   (download) and `tar` (unpack). Then run the `./config.sh ...` line it
   shows, which already contains the URL and registration token. When it
   asks:
   - *runner group*: press Enter
   - *runner name*: press Enter (the hostname) or type `hil-pi`
   - *additional labels*: type **`hil`** (this is how the workflow finds it)
   - *work folder*: press Enter
3. Install it as a service, so it starts on boot and survives logout:
   ```bash
   cd ~/actions-runner
   sudo ./svc.sh install $USER
   sudo ./svc.sh start
   ```
4. Back on GitHub, *Settings → Actions → General → Fork pull request
   workflows*: select **Require approval for all outside collaborators**.

✔ **Check:** on GitHub the runner shows **Idle** with labels
`self-hosted, Linux, ARM64, hil`. On the Pi:
```bash
sudo ./svc.sh status
journalctl -u 'actions.runner.*' -f        # "Listening for Jobs"
```

> The service picks up group memberships when it starts. If you ran
> `setup_pi.sh` after installing the service, run
> `sudo ./svc.sh stop && sudo ./svc.sh start`. Otherwise the job can't open
> the serial port or the GPIO.

### Phase 7: First CI run, then prove it can fail

1. Commit and push the test bench from your PC:
   ```bash
   git add -A && git commit -m "Add automated HIL test bench" && git push
   ```
   Or, if it's already pushed, use *Actions → HIL → Run workflow*.
2. Watch it in the **Actions** tab. On the Pi, `journalctl` shows
   `Running job: closed-loop`. When it finishes, download the
   **hil-results** artifact (plots, CSVs, junit.xml) from the run page.
3. **Prove the test bench catches a real bug.** This is the "done when"
   from the roadmap:
   ```bash
   # in Superheat_Control/Core/Src/main.c: #define PID_KP 0.3   (was 0.1)
   git commit -am "Deliberately break PI gains" && git push
   ```
   The run must go **red**: the loop oscillates and never settles, so the
   step, windup and link-loss tests fail. The plots in the artifact show the
   oscillation. Then revert it:
   ```bash
   git revert HEAD --no-edit && git push        # run goes green again
   ```

✔ **Done:** a broken controller can't reach `main` unnoticed.

### Day-to-day use

| You want to… | Do this |
|---|---|
| Test a change | Push to `main` (or *Actions → HIL → Run workflow*) |
| Run tests without CI | `~/hil-venv/bin/python -m pytest tests/hil --mute-gpio 17` on the Pi |
| Run one test | add `-k step` (or `windup`, `link_loss`, `boot`) |
| Develop tests with no hardware | `pytest tests/hil --sim` on any PC; `--sim-kp 0.3` to see failures |
| Use the rig for something else | `sudo ./svc.sh stop` in `~/actions-runner` first, so a CI job doesn't grab the port mid-session; `start` afterwards |
| Change Board 2 firmware | Repeat Phase 3. CI never reflashes Board 2. |

### Troubleshooting

| Symptom | Likely cause |
|---|---|
| Job stuck on "Waiting for a runner" | Pi off, service stopped, or the runner is missing the `hil` label |
| `Permission denied: /dev/ttyACM0` | Not in `dialout`, or the service started before the group change: restart it |
| OpenOCD `LIBUSB_ERROR_ACCESS` | Not in `plugdev`: log out and back in, then restart the service |
| `expected one ST-LINK VCP, found none` | Cable on the wrong board, or a charge-only USB cable |
| `Board 1 doesn't answer 'ping'` | Board 1 is running old firmware: rerun Phase 5's flash |
| `test_link_loss`: no fault within 6 ticks | Board 2 has old firmware (Phase 3), or GPIO17 or GND isn't connected |
| `test_boot`: "Board 2 isn't answering", rows end in `,0` | Board 2 unpowered or USART1 wiring loose; Board 1 prints `# FAULT link lost` |
| No rows at all | Wrong port, or Board 1 crashed: look for `!!! STACK OVERFLOW` or `heap allocation failed` in miniterm |

## 9. Status and next steps

| Item | Status |
|---|---|
| Firmware changes build for both boards | ✔ verified |
| Test suite against simulator: shipped gains pass, broken gains fail | ✔ verified |
| Tests on the real rig | ⏳ not yet run |
| Pi setup + runner registration | ⏳ to do |
| "Done when": a push with broken gains turns CI red | ⏳ to do |

Things to expect on the first hardware run:

- **The limits may need tuning.** Real ambient drift and the phase between
  LinkTask and ControlTask aren't fully modelled. If a test fails on a
  correct build, look at its plot, then loosen that one limit in the test
  file, and note why.
- **Board 2 must have the new firmware.** On the old firmware the
  link-loss test fails with "no fault within 6 ticks", because the mute pin
  does nothing.
- **Match `BME280_BUS`** in `.github/workflows/hil.yml` to how the sensor is
  wired (SPI by default).

Later projects in the roadmap (the Zephyr rewrite of Board 1) can reuse this
bench unchanged. The tests only depend on the VCP protocol and the CSV
format, not on which RTOS Board 1 runs.
