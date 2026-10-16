#!/usr/bin/env bash
# Flash an .elf through a Nucleo's onboard ST-LINK with OpenOCD, then run it.
#   tools/hil/flash.sh Superheat_Control/build/Debug/Superheat_Control.elf
# With more than one ST-LINK plugged in, pass the one to use (serial from
# `ls /dev/serial/by-id/`, the part after STLink_):
#   tools/hil/flash.sh firmware.elf 066DFF485550755187121234
set -euo pipefail

elf=${1:?usage: flash.sh <firmware.elf> [stlink-serial]}
[[ -f "$elf" ]] || { echo "no such file: $elf" >&2; exit 1; }

args=(-f interface/stlink.cfg)
if [[ -n "${2:-}" ]]; then
  args+=(-c "adapter serial $2")
fi
args+=(-f target/stm32f4x.cfg -c "program {$elf} verify reset exit")

openocd "${args[@]}"
