#!/usr/bin/env python3
"""Render a static step-response plot from a CSV log produced by plot_live.py.

Usage:
    python plot_from_log.py logs/run_20260926_140000.csv [--out step_response.png]
"""
import argparse
import csv
import sys

import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log_path")
    parser.add_argument("--out", help="Save the figure to this path instead of just showing it")
    args = parser.parse_args()

    ticks, plant_temp, valve, setpoint = [], [], [], []
    with open(args.log_path, newline="") as f:
        for row in csv.DictReader(f):
            ticks.append(int(row["tick"]))
            plant_temp.append(float(row["plant_degC"]))
            valve.append(float(row["valve"]) * 100.0)
            setpoint.append(float(row["setpoint_degC"]))

    fig, (ax_temp, ax_valve) = plt.subplots(2, 1, sharex=True, figsize=(9, 6))

    ax_temp.plot(ticks, plant_temp, label="Superheat (simulated plant), °C")
    ax_temp.plot(ticks, setpoint, "--", label="Superheat setpoint, °C")
    ax_temp.set_ylabel("Superheat (°C)")
    ax_temp.set_title("Superheat Control HIL Step Response")
    ax_temp.legend(loc="upper right")
    ax_temp.grid(True)

    ax_valve.plot(ticks, valve, color="tab:orange", label="Valve opening, %")
    ax_valve.set_ylabel("Valve opening (%)")
    ax_valve.set_xlabel("Tick")
    ax_valve.legend(loc="upper right")
    ax_valve.grid(True)

    plt.tight_layout()

    if args.out:
        fig.savefig(args.out, dpi=150)
        print(f"Saved plot to {args.out}")
    else:
        plt.show()


if __name__ == "__main__":
    sys.exit(main())
