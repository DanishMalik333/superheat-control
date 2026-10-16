"""Setpoint step response on the closed loop.

With the shipped gains (Kp=0.1, Ki=0.015) a 10 -> 13 degC step peaks about
2 % over and is inside +-0.5 degC after about 4 ticks, so the limits below
leave plenty of room for BME280 ambient drift but still catch broken gains:
Kp=0.3 overshoots ~24 % and never settles; Ki=0.1 overshoots ~34 %.
"""
from board import assert_valve_in_limits

SP_FROM, SP_TO = 10.0, 13.0
STEP = SP_TO - SP_FROM
MAX_OVERSHOOT = 0.10  # fraction of the step
SETTLE_TICKS = 30
SETTLE_BAND = 0.3  # degC
OBSERVE_TICKS = 60


def test_step_response(board):
    board.settle(SP_FROM)
    start = board.set_setpoint(SP_TO)
    rows = board.wait_rows(OBSERVE_TICKS, start)

    assert all(r.link_ok for r in rows), "link dropped during the step"
    assert_valve_in_limits(rows)

    peak = max(r.superheat for r in rows)
    overshoot = (peak - SP_TO) / STEP
    assert overshoot < MAX_OVERSHOOT, f"overshoot {overshoot:.1%} (peak {peak:.2f} degC)"

    late = rows[SETTLE_TICKS:]
    worst = max(abs(r.superheat - SP_TO) for r in late)
    assert worst <= SETTLE_BAND, (
        f"not within +-{SETTLE_BAND} degC of {SP_TO} after {SETTLE_TICKS} ticks (worst {worst:.2f})")
