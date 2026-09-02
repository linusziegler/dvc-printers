"""
Synchronized control of 3 ESC/POS printers (Goojprt QR203) over serial.

Physical setup: the paper strip exits printer 1 and is manually fed into
printer 2, then from printer 2 into printer 3. The print heads are a fixed
distance of N lines apart along that strip.

Stage 1 - SYNC:
    Printer 1 prints reference marks ("o") on the strip:
        - 3 marker lines for printer 2, then (N-3) blank lines
        - 3 marker lines for printer 3, then (N-3) blank lines
    You then feed the strip into printer 2 until its head sits on the
    FIRST marker block and let it print "x" over the "o" marks (confirming
    registration), then feed into printer 3 and do the same for the
    SECOND marker block.

Stage 2 - SHOW:
    Every printer advances by exactly one line per call to print_line(),
    whether it prints text or nothing, so the three printers stay in sync
    forever after the initial alignment. The main loop walks the three
    message arrays below and calls print_line() once per row.

"""

import time

from escpos.printer import Serial as escSerial

# ============================== CONFIG ==============================

# Serial ports for the three printers, in physical order along the strip.
PORT_1 = "COM11"
PORT_2 = "COM9"
PORT_3 = "COM10"

BAUDRATE = 9600  # must match each printer's DIP-switch/config baud rate

# Fixed physical distance between consecutive printers, in lines of text.
# Must be greater than SYNC_MARK_LINES.
N = 30

# How many marker lines printer 1 prints at the start of each N-line block.
SYNC_MARK_LINES = 5

# Characters used for the alignment marks.
SYNC_MARK_CHAR_P1 = "o"   # printed by printer 1
SYNC_MARK_CHAR_OVERWRITE = "x"  # printed by printer 2 / printer 3 on top

# Width (in characters) of each marker line, so the marks are easy to see.
MARK_WIDTH = 32

# Delay between each synced line during stage 2 (seconds). Tune to taste /
# to give slower printers time to feed & print before the next line.
LINE_DELAY = 0.05

# Which stage to run when this script is executed. Edit and re-run:
#   "sync" -> run the stage 1 alignment procedure
#   "show" -> run the stage 2 synced playback loop
MODE = "sync"

# Stage 2 content: one entry per printed row, one array per printer.
# Leave "" for a printer on a given row to just feed a blank line there -
# the row still advances the paper by exactly one line either way.
PRINTER1_LINES = [
    "Hello",
    "",
    "World",
]
PRINTER2_LINES = [
    "",
    "Foo",
    "",
]
PRINTER3_LINES = [
    "",
    "",
    "Bar",
]

# ======================================================================

assert N > SYNC_MARK_LINES, "N must be larger than SYNC_MARK_LINES"

_p1 = None
_p2 = None
_p3 = None


def _connect(port):
    printer = escSerial(
        devfile=port,
        baudrate=BAUDRATE,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=2,
        write_timeout=2,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    )
    printer.hw("INIT")
    printer.set(align="left", font="a", bold=False, double_height=False, double_width=False)
    return printer


def _advance_one_line(printer : escSerial, text=""):
    """Print `text` (or nothing) followed by exactly one line feed."""
    printer.text(text.encode())
    printer.text(b"\n")


def connect_all():
    global _p1, _p2, _p3
    _p1 = _connect(PORT_1)
    _p2 = _connect(PORT_2)
    _p3 = _connect(PORT_3)


def disconnect_all():
    for printer in (_p1, _p2, _p3):
        if printer is not None:
            printer.close()


def run_sync():
    """Stage 1: print alignment marks and pause for manual paper feeding."""
    connect_all()
    try:
        input("Printer 1 loaded with paper. Press Enter to print sync markers...")

        mark_line = SYNC_MARK_CHAR_P1 * MARK_WIDTH
        for _ in range(SYNC_MARK_LINES):
            _advance_one_line(_p1, mark_line)
        for _ in range(N - SYNC_MARK_LINES):
            _advance_one_line(_p1)
        for _ in range(SYNC_MARK_LINES):
            _advance_one_line(_p1, mark_line)
        for _ in range(N - SYNC_MARK_LINES):
            _advance_one_line(_p1)

        input(
            "Feed the strip into printer 2 until its head is on the FIRST "
            "'o' marker block, then press Enter to overwrite it with 'x'..."
        )
        overwrite_line = SYNC_MARK_CHAR_OVERWRITE * MARK_WIDTH
        for _ in range(SYNC_MARK_LINES):
            _advance_one_line(_p2, overwrite_line)

        input(
            "Feed the strip into printer 3 until its head is on the SECOND "
            "'o' marker block, then press Enter to overwrite it with 'x'..."
        )
        for _ in range(SYNC_MARK_LINES):
            _advance_one_line(_p3, overwrite_line)

        print("Sync complete. Set MODE = \"show\" to run the synced playback.")
    finally:
        disconnect_all()


def print_line(print1_msg="", print2_msg="", print3_msg=""):
    """Advance all three printers by exactly one line each, in sync."""
    _advance_one_line(_p1, print1_msg)
    _advance_one_line(_p2, print2_msg)
    _advance_one_line(_p3, print3_msg)


def run_show():
    """Stage 2: walk the three message arrays, one synced line at a time."""
    connect_all()
    try:
        line_count = max(len(PRINTER1_LINES), len(PRINTER2_LINES), len(PRINTER3_LINES))
        for i in range(line_count):
            msg1 = PRINTER1_LINES[i] if i < len(PRINTER1_LINES) else ""
            msg2 = PRINTER2_LINES[i] if i < len(PRINTER2_LINES) else ""
            msg3 = PRINTER3_LINES[i] if i < len(PRINTER3_LINES) else ""
            print_line(msg1, msg2, msg3)
            time.sleep(LINE_DELAY)
    finally:
        disconnect_all()


if __name__ == "__main__":
    if MODE == "sync":
        run_sync()
    elif MODE == "show":
        run_show()
    else:
        raise ValueError(f"Unknown MODE: {MODE!r} (expected 'sync' or 'show')")
