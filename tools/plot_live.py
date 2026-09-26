#!/usr/bin/env python3
"""Live-plot and log the Board 1 (Controller) debug CSV stream over its ST-LINK VCP port.

Usage:
    python plot_live.py COM4 [--baud 115200] [--window 120]

Board 1 prints one CSV header line, then one data row per tick:
    tick,bme280_degC,plant_degC,valve,setpoint_degC
Lines starting with '#' are comments (e.g. dropped-frame notices) and are skipped.

Every row read is appended to a timestamped CSV file in ./logs/ regardless of
whether the live plot window is open, so a step-response plot can always be
produced afterward from the logged data.
"""
import argparse
import csv
import os
import sys
from collections import deque
from datetime import datetime

import serial
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

FIELDS = ["tick", "bme280_degC", "plant_degC", "valve", "setpoint_degC"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", help="Serial port, e.g. COM4")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--window", type=int, default=120,
                         help="Number of most recent ticks to show in the live plot")
    args = parser.parse_args()

    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, datetime.now().strftime("run_%Y%m%d_%H%M%S.csv"))

    ser = serial.Serial(args.port, args.baud, timeout=1)
    log_file = open(log_path, "w", newline="")
    writer = csv.writer(log_file)
    writer.writerow(FIELDS)
    print(f"Logging to {log_path}")
    print(f"Reading from {args.port} @ {args.baud} baud. Press Ctrl+C to stop.")

    ticks = deque(maxlen=args.window)
    plant_temp = deque(maxlen=args.window)
    valve = deque(maxlen=args.window)
    setpoint = deque(maxlen=args.window)

    fig, (ax_temp, ax_valve) = plt.subplots(2, 1, sharex=True, figsize=(9, 6))
    line_plant, = ax_temp.plot([], [], label="Superheat (simulated plant), °C")
    line_setpoint, = ax_temp.plot([], [], "--", label="Superheat setpoint, °C")
    ax_temp.set_ylabel("Superheat (°C)")
    ax_temp.set_title("Superheat Control — Live HIL Response")
    ax_temp.legend(loc="upper right")
    ax_temp.grid(True)

    line_valve, = ax_valve.plot([], [], color="tab:orange", label="Valve opening, %")
    ax_valve.set_ylabel("Valve opening (%)")
    ax_valve.set_xlabel("Tick")
    ax_valve.set_ylim(0.0, 100.0)
    ax_valve.legend(loc="upper right")
    ax_valve.grid(True)

    def read_available_lines():
        rows_added = 0
        while ser.in_waiting:
            raw = ser.readline()
            if not raw:
                break
            line = raw.decode(errors="replace").strip()
            if not line or line.startswith("#") or line.startswith("tick,"):
                continue
            parts = line.split(",")
            if len(parts) != len(FIELDS):
                continue
            try:
                tick = int(parts[0])
                bme, plant, val, sp = (float(x) for x in parts[1:])
            except ValueError:
                continue

            writer.writerow([tick, bme, plant, val, sp])
            log_file.flush()

            ticks.append(tick)
            plant_temp.append(plant)
            valve.append(val * 100.0)
            setpoint.append(sp)
            rows_added += 1
        return rows_added

    def update(_frame):
        read_available_lines()
        if not ticks:
            return line_plant, line_setpoint, line_valve

        line_plant.set_data(ticks, plant_temp)
        line_setpoint.set_data(ticks, setpoint)
        line_valve.set_data(ticks, valve)

        ax_temp.set_xlim(ticks[0], max(ticks[-1], ticks[0] + 1))
        ymin = min(min(plant_temp), min(setpoint))
        ymax = max(max(plant_temp), max(setpoint))
        pad = max(0.5, (ymax - ymin) * 0.1)
        ax_temp.set_ylim(ymin - pad, ymax + pad)

        return line_plant, line_setpoint, line_valve

    ani = FuncAnimation(fig, update, interval=300, cache_frame_data=False)

    try:
        plt.tight_layout()
        plt.show()
    except KeyboardInterrupt:
        pass
    finally:
        log_file.close()
        ser.close()
        print(f"\nStopped. Log saved to {log_path}")


if __name__ == "__main__":
    sys.exit(main())
