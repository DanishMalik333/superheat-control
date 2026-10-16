"""Fixtures for the closed-loop HIL tests.

Real rig (Raspberry Pi runner, Board 1 on USB):
    pytest tests/hil --mute-gpio 17
Board 1's VCP is found automatically; pass --port /dev/ttyACM0 (or COM4) to
pick one. Without --mute-gpio the link-loss test is skipped.

No hardware (any PC), against the simulator in sim.py:
    pytest tests/hil --sim
"""
import os

import pytest

from board import Board1, write_csv

ST_LINK_VID = 0x0483
OUT_DIR = os.path.join(os.path.dirname(__file__), "out")


def pytest_addoption(parser):
    g = parser.getgroup("hil")
    g.addoption("--port", help="Board 1 ST-LINK VCP port (default: auto-detect)")
    g.addoption("--baud", type=int, default=115200)
    g.addoption("--mute-gpio", type=int,
                help="BCM number of the Pi GPIO wired to Board 2's D4 (link mute)")
    g.addoption("--sim", action="store_true", help="run against the software rig in sim.py")
    g.addoption("--sim-kp", type=float, help="simulator only: override Kp (to see tests fail)")
    g.addoption("--sim-ki", type=float, help="simulator only: override Ki")


def _find_stlink_port():
    from serial.tools import list_ports

    ports = [p.device for p in list_ports.comports() if p.vid == ST_LINK_VID]
    if len(ports) != 1:
        raise pytest.UsageError(f"expected one ST-LINK VCP, found {ports or 'none'}; pass --port")
    return ports[0]


@pytest.fixture(scope="session")
def rig(request):
    """The transport under Board1: a pyserial port or a SimRig."""
    cfg = request.config
    if cfg.getoption("--sim"):
        from sim import SimRig

        kw = {}
        if cfg.getoption("--sim-kp") is not None:
            kw["kp"] = cfg.getoption("--sim-kp")
        if cfg.getoption("--sim-ki") is not None:
            kw["ki"] = cfg.getoption("--sim-ki")
        return SimRig(**kw)

    import serial

    port = cfg.getoption("--port") or _find_stlink_port()
    return serial.Serial(port, cfg.getoption("--baud"), timeout=0.2)


@pytest.fixture(scope="session")
def board1(rig):
    b = Board1(rig, period=getattr(rig, "period", 1.0))
    if not b.ping():
        b.close()
        pytest.exit("Board 1 doesn't answer 'ping' - is the HIL firmware flashed?", returncode=3)
    yield b
    b.close()


@pytest.fixture
def board(board1, request):
    """Board 1 for one test. Every row the test saw is saved to
    tests/hil/out/<test>.csv for tools/plot_from_log.py."""
    start = board1.mark()
    yield board1
    os.makedirs(OUT_DIR, exist_ok=True)
    write_csv(os.path.join(OUT_DIR, request.node.name + ".csv"), board1.rows_since(start))


class _GpioLinkCut:
    def __init__(self, pin):
        from gpiozero import DigitalOutputDevice

        self._dev = DigitalOutputDevice(pin, initial_value=False)

    def cut(self):
        self._dev.on()

    def restore(self):
        self._dev.off()

    def close(self):
        self._dev.off()
        self._dev.close()


class _SimLinkCut:
    def __init__(self, rig):
        self._rig = rig

    def cut(self):
        self._rig.muted = True

    def restore(self):
        self._rig.muted = False

    def close(self):
        self._rig.muted = False


@pytest.fixture
def link(request, rig):
    """cut() stops Board 2 replying, restore() brings it back."""
    cfg = request.config
    if cfg.getoption("--sim"):
        cutter = _SimLinkCut(rig)
    elif cfg.getoption("--mute-gpio") is not None:
        cutter = _GpioLinkCut(cfg.getoption("--mute-gpio"))
    else:
        pytest.skip("needs --mute-gpio (Pi GPIO wired to Board 2 D4) or --sim")
    yield cutter
    cutter.close()
