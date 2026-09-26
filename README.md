# Superheat Control — Hardware-in-the-Loop PID Controller

A two-board Hardware-in-the-Loop (HIL) refrigeration superheat controller built on
STM32 Nucleo-F401RE boards. In the absence of a physical expansion valve and
evaporator, a second Nucleo runs a discretized transfer-function model of the
plant, closing a real control loop over a live inter-board link.

![Step response](docs/images/step_response.png)

*Simulated superheat converging to a 10°C setpoint under discrete PID control
(Kp=0.1, Ki=0.015), with the corresponding valve opening (%) settling to
steady state. Captured live from Board 1's UART debug stream — see
[Plotting the control loop](#plotting-the-control-loop).*

## Architecture

| | Board 1 — Controller | Board 2 — Plant Simulator |
|---|---|---|
| Folder | `Superheat_Control/` | `HVACPlant/` |
| Role | Reads a real BME280 temperature sensor over SPI, runs the discrete PID loop | Runs a discretized transfer-function model of the refrigeration plant |
| Sensor | BME280 (SPI1, logged only — not yet part of the control loop) | None |
| Debug output | USART2 → ST-LINK VCP (CSV telemetry) | USART2 → ST-LINK VCP (per-tick log) |
| Inter-board link | USART1 (PA9/PA10), master side | USART1 (PA9/PA10), replies to each frame |

Board 1 sends `valve_output` to Board 2 every control cycle; Board 2 runs it
through the plant model and replies with the resulting simulated temperature,
which becomes the PID's measurement input. This makes the HIL loop a genuine
closed loop — the controller board never sees the "real" plant, only what the
second board computes and sends back over the wire.

```mermaid
flowchart LR
    subgraph Board1["Board 1 — Controller"]
        BME280["BME280\n(SPI1, logged only)"]
        PID["Discrete PID\npid.c"]
    end

    subgraph Board2["Board 2 — Plant Simulator"]
        Plant["Discrete plant model\nplant.c"]
    end

    BME280 -.->|"logged, not yet\nin control loop"| PID
    PID -->|"valve_output\n(USART1, 115200)"| Plant
    Plant -->|"simulated_temp\n(USART1, 115200)"| PID

    Board1 -->|"CSV telemetry"| VCP1["ST-LINK VCP\n(USART2)"]
    Board2 -->|"per-tick log"| VCP2["ST-LINK VCP\n(USART2)"]
```

### Control loop

- Discrete PID: `pid.c` / `pid.h` — parallel P+I form with output clamping
  (anti-windup), `Kp=0.1`, `Ki=0.015`, `Kd=0`, sample time `Ts=1.0s`.
- Discrete plant model: `plant.c` / `plant.h` — `y[n] = den*y[n-1] + num*u[n-1]`,
  implementing `3.2739 / (z - 0.8363)` at `Ts=1.0s` (re-discretized from a
  continuous model with `tau≈5.594s`, `K=20.0`, originally tuned at `Ts=0.01s`
  in Simulink).

### Inter-board link protocol

Plain ASCII CSV over USART1 at 115200 baud: `"<tick>,<value>\r\n"`. Deliberately
kept separate from USART2, which is reserved on both boards for ST-LINK VCP
debug logging.

## Interrupt-driven UART reception

The inter-board link originally used polling (`HAL_UART_Receive` in a
byte-by-byte loop). This worked most of the time but intermittently corrupted
frames — worse under load (e.g. right after adding per-tick debug printing).

**Root cause:** the STM32 UART peripheral buffers exactly one received byte.
Polling only protects that byte if the CPU happens to be inside the polling
call at the exact moment it arrives. Any time the CPU was elsewhere — running
`printf`, computing the plant update — a byte landing during that window was
silently overwritten (receive overrun) before anything read it out, corrupting
that line's framing.

**Fix:** both boards now arm `HAL_UART_Receive_IT` once at startup and
assemble each line inside `HAL_UART_RxCpltCallback`, which the UART hardware
interrupt guarantees will run the instant a byte arrives — regardless of what
the main loop is doing. The callback appends the byte to a line buffer,
flags a complete line on `\n`, and immediately re-arms the next single-byte
receive before returning. The main loop's `Link_ReceiveLine` just waits on
that flag with a timeout, instead of touching bytes directly. This removed the
CPU-availability race entirely rather than just improving its odds.

## FreeRTOS task split (Board 1)

Board 1 originally ran a single bare-metal superloop doing everything
sequentially: BME280 read, UART link exchange, PID update, debug print. It now
runs three FreeRTOS (CMSIS-RTOS v2) tasks instead, connected by two depth-1
message queues that always hold the latest value:

- **`SensorTask`** — reads the BME280 once per second, independent of the
  control loop's timing.
- **`LinkTask`** (`osPriorityAboveNormal`) — sends `valve_output` to Board 2,
  waits for its reply, and pushes the result into `SimTempQueue`.
- **`ControlTask`** — reads `SimTempQueue`, runs `PID_Update`, pushes the new
  `valve_output` into `ValveOutputQueue`, and prints the CSV debug line.

```mermaid
flowchart TB
    Sensor["SensorTask\n(osPriorityNormal)\nBME280 read, 1s"]
    Link["LinkTask\n(osPriorityAboveNormal)\nUART exchange w/ Board 2"]
    Control["ControlTask\n(osPriorityNormal)\nPID_Update + CSV log"]

    ValveQ[["ValveOutputQueue\n(depth 1)"]]
    TempQ[["SimTempQueue\n(depth 1)"]]

    Control -->|"valve_output"| ValveQ
    ValveQ -->|"valve_output"| Link
    Link -->|"simulated_temp"| TempQ
    TempQ -->|"simulated_temp"| Control

    Sensor -.->|"latest_bme280_degC\n(logged only)"| Control
```

Two issues surfaced while bringing this up, both worth knowing if you extend
this further:

- **Missing NVIC priority grouping.** `HAL_MspInit` never called
  `HAL_NVIC_SetPriorityGrouping(NVIC_PRIORITYGROUP_4)`. FreeRTOS's Cortex-M
  port assumes 4 preemption-priority bits; running on the CPU's reset default
  silently broke interrupt masking, producing zero serial output with no
  error of any kind.
- **Stack overflow in `LinkTask`.** `sscanf`/`snprintf` float formatting in
  newlib-nano is stack-heavy, more than bare-metal's single large shared stack
  ever made obvious. `configCHECK_FOR_STACK_OVERFLOW` and a
  `vApplicationStackOverflowHook` were added to surface this instead of
  silently corrupting memory; `LinkTask`/`ControlTask` are now sized to 512
  words, `SensorTask` to 256.

`Link_ReceiveLine`'s wait loop also switched from a bare spin to `osDelay(1)`
per iteration — `LinkTask` runs at the highest priority, so a non-yielding
spin there starved the other two tasks entirely after their first cycle.

## Repository layout

```
Superheat_Control_Project/
├── Superheat_Control/   Board 1 (Controller) — STM32CubeIDE/CMake project
├── HVACPlant/           Board 2 (Plant Simulator) — STM32CubeIDE/CMake project
├── tools/               Host-side Python scripts for live plotting & logging
│   └── logs/            Timestamped CSV logs from tools/plot_live.py (gitignored)
└── docs/images/         Figures used in this README
```

## Building and flashing

Both projects are STM32CubeIDE/CMake projects using the STM32Cube-bundled
`arm-none-eabi-gcc` toolchain and Ninja. Open each folder in an IDE with CMake
Tools + Cortex-Debug (or STM32CubeIDE directly), build, and flash over each
board's onboard ST-LINK.

Flash and reset **both boards together** after any rebuild — if one board is
reflashed while the other keeps running, their tick counters and link framing
can start from different states.

## Wiring

| Board 1 (Controller) pin | Board 2 (Plant Simulator) pin | Purpose |
|---|---|---|
| D8 (PA9, USART1_TX) | D2 (PA10, USART1_RX) | Board 1 → Board 2 |
| D2 (PA10, USART1_RX) | D8 (PA9, USART1_TX) | Board 2 → Board 1 |
| GND | GND | Common reference |

Board 2 is powered externally (E5V via CN7 pin 6, JP5 jumper moved to the E5V
position, JP1 removed) since it has no USB connection of its own in the HIL
setup.

## Plotting the control loop

`tools/plot_live.py` reads Board 1's USART2 debug stream (ST-LINK VCP) live,
plots plant temperature vs. setpoint and valve output in real time, and logs
every row to a timestamped CSV in `tools/logs/`.

```
pip install pyserial matplotlib
python tools/plot_live.py COM4      # replace COM4 with Board 1's ST-LINK VCP port
```

To regenerate a static plot (e.g. for a report) from a saved log:

```
python tools/plot_from_log.py tools/logs/run_20260926_151558.csv --out step_response.png
```

## Status

- [x] Ts reconciliation between Simulink tuning and firmware (`Ts=1.0s`)
- [x] PID and plant models modularized into reusable `pid.c`/`plant.c`
- [x] Two-board HIL wiring and UART inter-board link
- [x] Interrupt-driven UART reception (see above)
- [x] Live plotting / CSV logging of the control loop
- [x] FreeRTOS task split on Board 1 (sensor read / link / control loop)
- [ ] Superheat computation from real sensor data (BME280 is currently logged
      but not yet part of the control loop)
