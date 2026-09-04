"""
Step 1: print a few lines upside-down on a single printer, using python-escpos.

Requirements: pip install python-escpos pillow
"""

import time

from escpos.printer import Serial as escSerial

# ============================== CONFIG ==============================

PORT = "COM9"
BAUDRATE = 9600

TEXT_FILE = "test_lines.txt"

WRITE_DELAY = 0.05  # small pause after each send; the printer's buffer is tiny

# Raw ESC/POS command to toggle upside-down character printing (ESC { n).
UPSIDE_DOWN_ON = b"\x1b\x7b\x01"
UPSIDE_DOWN_OFF = b"\x1b\x7b\x00"

# ====================================================================


def send(printer, data):
    printer._raw(data)
    printer.device.flush()
    time.sleep(WRITE_DELAY)


def load_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        return [line.rstrip("\n") for line in f]


def main():
    printer = escSerial(
        devfile=PORT,
        baudrate=BAUDRATE,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=2,
        xonxoff=False,
        dsrdtr=False,
    )

    lines = load_lines(TEXT_FILE)

    try:
        printer.hw("INIT")
        send(printer, UPSIDE_DOWN_ON)

        for line in lines:
            send(printer, line.encode("cp437") + b"\n")

        send(printer, UPSIDE_DOWN_OFF)
        send(printer, b"\n\n\n")
    finally:
        printer.close()


if __name__ == "__main__":
    main()
