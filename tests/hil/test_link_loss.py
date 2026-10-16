"""Board 2 stops replying: Board 1 must flag a fault, hold the valve at its
safe position, and pick the loop back up when the link returns.

Fault latency: Board 1 waits 500 ms for each reply and declares the fault
after 2 misses in a row. Depending on where in the 1 s cycle the cut lands,
that shows up in the CSV 2-4 ticks later; 6 leaves a margin.
"""
from board import assert_valve_in_limits

VALVE_SAFE = 0.3  # VALVE_SAFE in Board 1's main.c
FAULT_WITHIN_TICKS = 6
CUT_TICKS = 10
RECOVER_WITHIN_TICKS = 4
RESETTLE_TICKS = 60


def test_link_loss_holds_safe_valve(board, link):
    board.settle(10.0)

    start = board.mark()
    link.cut()
    try:
        fault = board.wait_for(lambda r: not r.link_ok, FAULT_WITHIN_TICKS, start)
        assert fault is not None, f"no fault within {FAULT_WITHIN_TICKS} ticks of cutting the link"

        held = board.wait_rows(CUT_TICKS)
        assert all(not r.link_ok for r in held), "link_ok came back while the link was cut"
        assert all(abs(r.valve - VALVE_SAFE) < 1e-3 for r in held), \
            f"valve not held at {VALVE_SAFE}: {sorted({r.valve for r in held})}"
    finally:
        link.restore()

    start = board.mark()
    back = board.wait_for(lambda r: r.link_ok, RECOVER_WITHIN_TICKS, start)
    assert back is not None, f"link not back within {RECOVER_WITHIN_TICKS} ticks of restoring it"

    rows = board.wait_rows(RESETTLE_TICKS, start)
    assert_valve_in_limits(rows)
    assert abs(rows[-1].superheat - 10.0) < 0.3, "loop didn't return to the setpoint"
