"""Host-side driver for Board 1's ST-LINK VCP: sends commands, parses the CSV stream.

Board 1 prints one CSV row per control tick (1 s):
    tick,bme280_degC,plant_degC,valve,setpoint_degC,link_ok
Lines starting with '#' are status messages ("# ok sp 13.00", "# FAULT ...").

Tests count in rows (control ticks) rather than seconds wherever they can, so
the same tests run against the real rig (1 row/s) and the simulator (much
faster). Wall-clock timeouts are derived from the row period.
"""
import csv
import math
import threading
import time
from dataclasses import dataclass

CSV_FIELDS = ["tick", "bme280_degC", "plant_degC", "valve", "setpoint_degC", "link_ok"]


@dataclass
class Row:
    tick: int
    ambient: float  # nan when Board 1 has no BME280 reading
    superheat: float
    valve: float  # 0..1
    setpoint: float
    link_ok: bool

    @classmethod
    def parse(cls, line):
        """Returns a Row, or None for anything that isn't a well-formed data row."""
        parts = line.split(",")
        if len(parts) != len(CSV_FIELDS) or parts[5].strip() not in ("0", "1"):
            return None
        try:
            return cls(int(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]),
                       float(parts[4]), parts[5].strip() == "1")
        except ValueError:
            return None


class Board1:
    def __init__(self, transport, period=1.0):
        """transport: anything with readline() -> bytes, write(bytes) and close(),
        e.g. a pyserial Serial opened with a timeout. period: seconds per row."""
        self._t = transport
        self.period = period
        self._cv = threading.Condition()
        self._rows = []
        self._lines = []
        self._stop = False
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def close(self):
        self._stop = True
        self._reader.join(timeout=2)
        self._t.close()

    def _read_loop(self):
        while not self._stop:
            raw = self._t.readline()
            if not raw:
                continue
            line = raw.decode(errors="replace").strip()
            if not line:
                continue
            row = None if line.startswith("#") else Row.parse(line)
            with self._cv:
                self._lines.append(line)
                if row is not None:
                    self._rows.append(row)
                self._cv.notify_all()

    # --- raw access -----------------------------------------------------

    def send(self, cmd):
        self._t.write((cmd + "\r\n").encode())

    def mark(self):
        """Position in the row stream; pass it to rows_since() / wait_*()."""
        with self._cv:
            return len(self._rows)

    def line_mark(self):
        with self._cv:
            return len(self._lines)

    def rows_since(self, mark):
        with self._cv:
            return list(self._rows[mark:])

    def _timeout(self, rows):
        # Generous: the firmware's tick isn't locked to the host clock, and the
        # first row after a command can be up to one period away.
        return (rows + 3) * self.period * 1.5 + 2.0

    # --- waiting --------------------------------------------------------

    def wait_rows(self, n, start=None):
        """Blocks until n rows have arrived after `start` (default: now)."""
        start = self.mark() if start is None else start
        deadline = time.monotonic() + self._timeout(n)
        with self._cv:
            while len(self._rows) - start < n:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError(f"only {len(self._rows) - start} of {n} rows arrived")
                self._cv.wait(left)
            return list(self._rows[start:start + n])

    def wait_for(self, pred, max_rows, start=None):
        """Returns the first row after `start` matching pred, or None if none of
        the next max_rows rows does."""
        start = self.mark() if start is None else start
        deadline = time.monotonic() + self._timeout(max_rows)
        seen = start
        with self._cv:
            while True:
                while seen < len(self._rows) and seen - start < max_rows:
                    if pred(self._rows[seen]):
                        return self._rows[seen]
                    seen += 1
                if seen - start >= max_rows:
                    return None
                left = deadline - time.monotonic()
                if left <= 0:
                    return None
                self._cv.wait(left)

    def wait_line(self, pred, timeout_s, start=None):
        """Returns the first raw line (including '#' lines) matching pred."""
        start = self.line_mark() if start is None else start
        deadline = time.monotonic() + timeout_s
        seen = start
        with self._cv:
            while True:
                while seen < len(self._lines):
                    if pred(self._lines[seen]):
                        return self._lines[seen]
                    seen += 1
                left = deadline - time.monotonic()
                if left <= 0:
                    return None
                self._cv.wait(left)

    # --- commands -------------------------------------------------------

    def ping(self, timeout_s=3.0):
        start = self.line_mark()
        self.send("ping")
        return self.wait_line(lambda l: l == "# pong", timeout_s, start) is not None

    def set_setpoint(self, sp):
        """Sends "sp", then waits for a row that shows the new setpoint.
        Returns the mark of that row, i.e. where the step response starts."""
        sp = round(sp, 2)  # what Board 1 will echo
        start = self.mark()
        self.send(f"sp {sp:.2f}")
        row = self.wait_for(lambda r: abs(r.setpoint - sp) < 0.005, 5, start)
        if row is None:
            raise AssertionError(f"Board 1 didn't take setpoint {sp}")
        with self._cv:
            return self._rows.index(row, start)

    def reset(self):
        self.send("reset")

    def settle(self, sp, band=0.3, hold=5, max_rows=120):
        """Puts the loop at setpoint sp and waits until superheat has stayed
        within +-band for `hold` rows in a row. Raises if it doesn't."""
        start = self.set_setpoint(sp)
        in_band = 0
        for i in range(max_rows):
            r = self.wait_rows(1, start + i)[0]
            in_band = in_band + 1 if (r.link_ok and abs(r.superheat - sp) <= band) else 0
            if in_band >= hold:
                return
        raise AssertionError(f"loop didn't settle at {sp} within {max_rows} rows")


VALVE_MIN, VALVE_MAX = 0.1, 0.9  # PID_OUT_MIN / PID_OUT_MAX in Board 1's main.c


def assert_valve_in_limits(rows):
    """The valve command must never be NaN or leave its clamp."""
    bad = [r for r in rows if math.isnan(r.valve) or not VALVE_MIN - 1e-3 <= r.valve <= VALVE_MAX + 1e-3]
    assert not bad, f"valve outside [{VALVE_MIN}, {VALVE_MAX}] at ticks {[r.tick for r in bad][:10]}"


def write_csv(path, rows):
    """Writes rows in the same format as tools/plot_live.py, so
    tools/plot_from_log.py can plot them."""
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_FIELDS)
        for r in rows:
            w.writerow([r.tick, "nan" if math.isnan(r.ambient) else r.ambient,
                        r.superheat, r.valve, r.setpoint, int(r.link_ok)])
