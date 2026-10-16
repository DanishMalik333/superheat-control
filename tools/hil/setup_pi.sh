#!/usr/bin/env bash
# One-time setup of a Raspberry Pi 4 (Raspberry Pi OS Bookworm, 64-bit) as the
# HIL bench: ARM toolchain, OpenOCD, and a Python venv for the tests.
# Run it as the user the GitHub Actions runner will run as.
set -euo pipefail

repo=$(cd "$(dirname "$0")/../.." && pwd)

sudo apt-get update
sudo apt-get install -y git cmake ninja-build gcc-arm-none-eabi libnewlib-arm-none-eabi \
    openocd python3-venv python3-gpiozero python3-lgpio

# dialout: the ST-LINK VCP (/dev/ttyACM*); plugdev: ST-LINK USB access for
# OpenOCD (its udev rules use that group); gpio: the link-mute pin.
sudo usermod -aG dialout,plugdev,gpio "$USER"

# --system-site-packages so the venv sees apt's gpiozero/lgpio, which need
# the Pi's GPIO libraries rather than a pip wheel.
python3 -m venv --system-site-packages ~/hil-venv
~/hil-venv/bin/pip install -r "$repo/tests/hil/requirements.txt"

echo
echo "Done. Log out and back in (or reboot) so the new groups apply, then check:"
echo "  ~/hil-venv/bin/python -m pytest $repo/tests/hil --sim"
