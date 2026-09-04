"""
Step 1: print a few lines upside-down on a single printer, using python-escpos.

Requirements: pip install python-escpos pillow
"""

import re
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

# Raw ESC/POS commands for per-line style: bold (ESC E n) and font (ESC M n).
BOLD_ON = b"\x1b\x45\x01"
BOLD_OFF = b"\x1b\x45\x00"
FONT_A = b"\x1b\x4d\x00"  # default font
FONT_B = b"\x1b\x4d\x01"  # smaller/condensed font
UNDERLINE_ON = b"\x1b\x2d\x01"
UNDERLINE_OFF = b"\x1b\x2d\x00"
INVERT_ON = b"\x1d\x42\x01"  # white-on-black
INVERT_OFF = b"\x1d\x42\x00"
SIZE_NORMAL = b"\x1d\x21\x00"  # GS ! n: high nibble = width x2, low nibble = height x2
SIZE_WIDE = b"\x1d\x21\x10"
SIZE_TALL = b"\x1d\x21\x01"
SIZE_BIG = b"\x1d\x21\x11"  # double width and height

# Lines in TEXT_FILE may start with a "[tag,tag]" marker to style just that
# line; supported tags: bold, fontb, underline, invert, wide, tall, big.
# Unmarked lines print normal weight, Font A, normal size.
LINE_TAG_PATTERN = re.compile(r"^\[([a-z0-9_,]+)\]\s*(.*)$", re.IGNORECASE)

# ====================================================================


def send(printer, data):
    printer._raw(data)
    printer.device.flush()
    time.sleep(WRITE_DELAY)


def load_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        return [line.rstrip("\n") for line in f]


def parse_line(raw_line):
    """Split a leading "[tag,tag]" marker off a line, if present."""
    match = LINE_TAG_PATTERN.match(raw_line)
    if not match:
        return raw_line, set()
    tags_str, text = match.groups()
    tags = {tag.strip().lower() for tag in tags_str.split(",")}
    return text, tags


def style_commands(tags):
    if "big" in tags:
        size = SIZE_BIG
    elif "wide" in tags:
        size = SIZE_WIDE
    elif "tall" in tags:
        size = SIZE_TALL
    else:
        size = SIZE_NORMAL

    return (
        (BOLD_ON if "bold" in tags else BOLD_OFF)
        + (FONT_B if "fontb" in tags else FONT_A)
        + (UNDERLINE_ON if "underline" in tags else UNDERLINE_OFF)
        + (INVERT_ON if "invert" in tags else INVERT_OFF)
        + size
    )


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
            text, tags = parse_line(line)
            send(printer, style_commands(tags))
            send(printer, text.encode("cp437") + b"\n")

        send(printer, style_commands(set()))
        send(printer, UPSIDE_DOWN_OFF)
        send(printer, b"\n\n\n")
    finally:
        printer.close()


if __name__ == "__main__":
    main()
