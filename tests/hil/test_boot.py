"""Board 1 restarts cleanly and the loop comes up."""
from board import CSV_FIELDS


def test_reset_reports_header_and_rows(board):
    start = board.line_mark()
    board.reset()

    header = board.wait_line(lambda l: l == ",".join(CSV_FIELDS), 3.0 + 3 * board.period, start)
    assert header is not None, "no CSV header within 3 s of reset"

    first = board.wait_for(lambda r: r.tick <= 2, max_rows=3)
    assert first is not None, "no data rows after the header"


def test_link_up_after_boot(board):
    # Board 1 needs LINK_FAULT_MISSES (2) missed replies to flag a fault, so
    # look at rows well past that.
    rows = board.wait_rows(8)
    assert all(r.link_ok for r in rows[-4:]), "Board 2 isn't answering after boot"
