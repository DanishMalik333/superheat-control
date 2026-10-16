"""Software stand-in for the two-board rig, used by `pytest --sim`.

Speaks the same VCP protocol as Board 1 (CSV rows, '#' lines, sp/ping/reset
commands) and runs the same PI law, plant and link-fault logic as the
firmware, faster than real time. It exists to develop and check the tests
themselves without hardware, not to replace the rig: a test that passes here
still has to pass on the boards.

The timing matches the firmware: superheat at tick k responds to the valve
output computed at tick k-2 (one tick through the ValveOutputQueue, one inside
the plant's u[n-1]). This reproduces a logged hardware run to 4 decimals.
"""
import queue
import threading
import time

# Board 1 (Superheat_Control/Core/Src/main.c)
PID_KP, PID_KI, PID_TS = 0.1, 0.015, 1.0
PID_OUT_MIN, PID_OUT_MAX = 0.1, 0.9
SETPOINT_DEGC = 10.0
LINK_FAULT_MISSES = 2
VALVE_SAFE = 0.3

# Board 2 (HVACPlant/Core/Inc/plant.h)
PLANT_NUM, PLANT_DEN = 3.273862869, 0.836306857
PLANT_AMBIENT_REF_DEGC = 22.0
PLANT_NUM_AMBIENT = 0.5 * (1.0 - PLANT_DEN)


class SimRig:
    def __init__(self, period=0.02, kp=PID_KP, ki=PID_KI, ambient_degC=23.0):
        self.period = period
        self.kp, self.ki = kp, ki
        self.ambient = ambient_degC
        self.muted = False  # stands in for the Pi GPIO on Board 2's D4

        # Board 2 state survives a Board 1 reset, as on the rig.
        self._y = 0.0
        self._u_prev = 0.0
        self._d_prev = 0.0

        self._out = queue.Queue()
        self._cmds = queue.Queue()
        self._stop = threading.Event()
        self._boot()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # --- transport interface (what Board1 expects from pyserial) ---------

    def readline(self):
        try:
            return self._out.get(timeout=0.1)
        except queue.Empty:
            return b""

    def write(self, data):
        for line in data.decode().splitlines():
            if line.strip():
                self._cmds.put(line.strip())

    def close(self):
        self._stop.set()
        self._thread.join(timeout=2)

    # --- rig model -------------------------------------------------------

    def _print(self, line):
        self._out.put((line + "\r\n").encode())

    def _boot(self):
        self._tick = 0
        self._integrator = 0.0
        self._setpoint = SETPOINT_DEGC
        self._y_rx = 0.0
        self._u_link = PID_OUT_MIN
        self._misses = 0
        self._link_ok = True
        self._was_ok = True
        self._print("# BME280 over SIM, chip_id=0x60")
        self._print(",".join(["tick", "bme280_degC", "plant_degC", "valve", "setpoint_degC", "link_ok"]))

    def _command(self, line):
        if line.startswith("sp "):
            try:
                sp = float(line[3:])
            except ValueError:
                sp = -1.0
            if 0.0 <= sp <= 40.0:
                self._setpoint = sp
                self._print(f"# ok sp {sp:.2f}")
            else:
                self._print("# err sp must be 0.0..40.0")
        elif line == "ping":
            self._print("# pong")
        elif line == "reset":
            self._print("# resetting")
            self._boot()
        else:
            self._print("# err unknown command")

    def _pid(self, sp, y):
        e = sp - y
        self._integrator += self.ki * e * PID_TS
        u = self.kp * e + self._integrator
        if u > PID_OUT_MAX:
            self._integrator -= u - PID_OUT_MAX
            u = PID_OUT_MAX
        elif u < PID_OUT_MIN:
            self._integrator += PID_OUT_MIN - u
            u = PID_OUT_MIN
        return u

    def _step(self):
        # LinkTask <-> Board 2: the plant always gets the frame; mute only drops the reply.
        d = self.ambient - PLANT_AMBIENT_REF_DEGC
        y = PLANT_DEN * self._y + PLANT_NUM * self._u_prev + PLANT_NUM_AMBIENT * self._d_prev
        self._y, self._u_prev, self._d_prev = y, self._u_link, d
        if not self.muted:
            self._y_rx = y
            self._misses = 0
            self._link_ok = True
        else:
            self._print("# HIL link: malformed/missing frame, holding last simulated_temp")
            self._misses += 1
            if self._misses >= LINK_FAULT_MISSES and self._link_ok:
                self._link_ok = False
                self._print(f"# FAULT link lost, valve held at {VALVE_SAFE:.2f}")

        # ControlTask
        ok = self._link_ok
        if ok:
            if not self._was_ok:
                self._integrator = VALVE_SAFE
            u = self._pid(self._setpoint, self._y_rx)
        else:
            u = VALVE_SAFE
        self._was_ok = ok
        self._u_link = u
        self._print(f"{self._tick},{self.ambient:.2f},{self._y_rx:.4f},{u:.3f},"
                    f"{self._setpoint:.2f},{int(ok)}")
        self._tick += 1

    def _run(self):
        next_t = time.monotonic()
        while not self._stop.is_set():
            while not self._cmds.empty():
                self._command(self._cmds.get())
            self._step()
            next_t += self.period
            time.sleep(max(0.0, next_t - time.monotonic()))
