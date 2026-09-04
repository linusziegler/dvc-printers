"""
Step 1: print a few lines upside-down on a single printer, using python-escpos.

Requirements: pip install python-escpos pillow
"""

import time

from escpos.printer import Serial as escSerial

# ============================== CONFIG ==============================

PORT = "COM9"
BAUDRATE = 9600

LINE_COUNT = 5
LINE_TEXT = "testtesttest"

WRITE_DELAY = 0.05  # small pause after each send; the printer's buffer is tiny

# Raw ESC/POS command to toggle upside-down character printing (ESC { n).
UPSIDE_DOWN_ON = b"\x1b\x7b\x01"
UPSIDE_DOWN_OFF = b"\x1b\x7b\x00"

# ====================================================================


def send(printer, data):
    printer._raw(data)
    printer.device.flush()
    time.sleep(WRITE_DELAY)


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

    try:
        printer.hw("INIT")
        send(printer, UPSIDE_DOWN_ON)

        for _ in range(LINE_COUNT):
            send(printer, LINE_TEXT.encode("cp437") + b"\n")

        send(printer, UPSIDE_DOWN_OFF)
        send(printer, b"\n\n\n")
    finally:
        printer.close()


if __name__ == "__main__":
    main()
