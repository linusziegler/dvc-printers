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
import msvcrt

from escpos.printer import Serial as escSerial

# ============================== CONFIG ==============================

# Serial ports for the three printers, in physical order along the strip.
PORT_1 = "COM11"
PORT_2 = "COM10"
PORT_3 = "COM9"

BAUDRATE = 9600  # must match each printer's DIP-switch/config baud rate

# Fixed physical distance between consecutive printers, in lines of text.
# Must be greater than SYNC_MARK_LINES.
N = 50

# How many marker lines printer 1 prints at the start of each N-line block.
SYNC_MARK_LINES = 5

# Characters used for the alignment marks.
SYNC_MARK_PRE = "<<<<<<<<<<<<<<<<>>>>>>>>>>>>>>>>"   # printed by printer 1
SYNC_MARK_P1 = "ooooooo"   # printed by printer 1
SYNC_MARK_OVERWRITE = "xxxxxxx"  # printed by printer 2 / printer 3 on top

# Width (in characters) of each marker line, so the marks are easy to see.
MARK_WIDTH = 32

# Which stage to run when this script is executed. Edit and re-run:
#   "sync" -> run the stage 1 alignment procedure
#   "show" -> run the stage 2 synced playback loop
MODE = "show"

# Stage 2 content: one entry per printed row, one array per printer.
# Leave "" for a printer on a given row to just feed a blank line there -
# the row still advances the paper by exactly one line either way.
# repeat line for N times
PRINTER1_LINES = ["Printer 1 Printer 1"] * N
PRINTER2_LINES = ["Printer 2 Printer 2"] * N
PRINTER3_LINES = ["Printer 3 Printer 3"] * N
# Pause after every single line sent to a printer. Without this the
# printer's tiny input buffer overruns almost instantly (there's no usable
# flow control) and the data is silently dropped instead of printed - see
# test.py's send(), which does the same flush+sleep after every write.
WRITE_DELAY = 0.01

# ======================================================================

assert N > SYNC_MARK_LINES, "N must be larger than SYNC_MARK_LINES"

_p1: escSerial | None = None
_p2: escSerial | None = None
_p3: escSerial | None = None


def _connect(port):
    # NB: python-escpos's Serial.open() only ever forwards timeout, xonxoff
    # and dsrdtr to pyserial - any other kwargs here (e.g. write_timeout,
    # rtscts) are silently swallowed and have no effect.
    printer = escSerial(
        devfile=port,
        baudrate=BAUDRATE,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=2,
        xonxoff=False,
        dsrdtr=False,
    )
    printer.hw("INIT")
    time.sleep(WRITE_DELAY)
    printer.set(align="left", font="a", bold=False, double_height=False, double_width=False)
    time.sleep(WRITE_DELAY)
    return printer


def _advance_one_line(printer: escSerial | None, text=""):
    """Print `text` (or nothing) followed by exactly one line feed."""
    assert printer is not None, "connect_all() must be called before printing"
    printer.text(str(text))
    printer.text("\n")
    printer.device.flush()  # type: ignore[union-attr]
    time.sleep(WRITE_DELAY)


def connect_all():
    global _p1, _p2, _p3
    _p1 = _connect(PORT_1)
    _p2 = _connect(PORT_2)
    _p3 = _connect(PORT_3)


def disconnect_all():
    for printer in (_p1, _p2, _p3):
        if printer is not None:
            printer.close()


def _run_step_on_enter(prompt):
    """Return True when Enter is pressed, or False when another key is pressed."""
    print(prompt)
    print("Press Enter to run this step, or any other key to skip it.")
    key = msvcrt.getwch()
    print()
    return key in ("\r", "\n")


def print_sync_sequence(printer):
    _advance_one_line(printer, SYNC_MARK_PRE)
    _advance_one_line(printer)
    for _ in range(SYNC_MARK_LINES):
        _advance_one_line(printer, SYNC_MARK_P1)

def run_sync():
    """Stage 1: print alignment marks and pause for manual paper feeding."""
    connect_all()
    try:
        if _run_step_on_enter("Sync Printer 1"):
            print_sync_sequence(_p1)
            for _ in range(N - (SYNC_MARK_LINES + 2)):
                _advance_one_line(_p1)

            print_sync_sequence(_p1)
            for _ in range(N - (SYNC_MARK_LINES + 2)):
                _advance_one_line(_p1)

        overwrite_line = SYNC_MARK_OVERWRITE
        if _run_step_on_enter(
            "Sync Printer 2"
        ):
            for _ in range(SYNC_MARK_LINES):
                _advance_one_line(_p2, overwrite_line)

        if _run_step_on_enter(
            "Sync Printer 3"
        ):
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
        line_count = N
        for i in range(line_count):
            msg1 = PRINTER1_LINES[i] if i < len(PRINTER1_LINES) else ""
            msg2 = PRINTER2_LINES[i] if i < len(PRINTER2_LINES) else ""
            msg3 = PRINTER3_LINES[i] if i < len(PRINTER3_LINES) else ""
            print_line(msg1, msg2, msg3)
    finally:
        disconnect_all()


if __name__ == "__main__":
    if MODE == "sync":
        run_sync()
    elif MODE == "show":
        run_show()
    else:
        raise ValueError(f"Unknown MODE: {MODE!r} (expected 'sync' or 'show')")
