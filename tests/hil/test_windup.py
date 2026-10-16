"""Anti-windup: hold the valve in saturation, then check the recovery.

A 30 degC setpoint is out of reach (full valve gives about 18 degC), so the
valve sits at its 0.9 clamp. Without anti-windup the integrator would keep
growing the whole time and superheat would undershoot badly after the
setpoint comes back down. With the shipped clamping it barely undershoots.
"""
from board import VALVE_MAX, assert_valve_in_limits

SP_NORMAL = 10.0
SP_UNREACHABLE = 30.0
SATURATE_TICKS = 40
RECOVER_TICKS = 80
MAX_UNDERSHOOT = 0.10  # fraction of the drop back to SP_NORMAL
SETTLE_TICKS = 40
SETTLE_BAND = 0.5


def test_recovers_from_saturation(board):
    board.settle(SP_NORMAL)

    start = board.set_setpoint(SP_UNREACHABLE)
    saturated = board.wait_rows(SATURATE_TICKS, start)
    assert_valve_in_limits(saturated)
    assert sum(abs(r.valve - VALVE_MAX) < 1e-3 for r in saturated[-10:]) == 10, \
        "valve never saturated, so this test proves nothing"

    start = board.set_setpoint(SP_NORMAL)
    rows = board.wait_rows(RECOVER_TICKS, start)
    assert_valve_in_limits(rows)

    top = rows[0].superheat
    undershoot = (SP_NORMAL - min(r.superheat for r in rows)) / (top - SP_NORMAL)
    assert undershoot < MAX_UNDERSHOOT, f"undershoot {undershoot:.1%} after saturation (windup?)"

    worst = max(abs(r.superheat - SP_NORMAL) for r in rows[SETTLE_TICKS:])
    assert worst <= SETTLE_BAND, f"not back within +-{SETTLE_BAND} degC after {SETTLE_TICKS} ticks"
