"""
Print ownerless-property notices upside-down on the COM9 thermal printer.

Data flow (edit these, not this file, to change what gets printed):
    notice_template.txt - the blueprint. Free text, blank-line-separated
                           paragraphs, re-wrapped automatically. Placeholders
                           {address}, {judge_name}, {decision} are filled in
                           from the CSV; a paragraph containing only the
                           literal "{STAMP}" is replaced by stamp_small.bmp.
    notices.csv         - one row per notice: columns address, judge_name,
                           decision. Add more columns/placeholders together
                           in both files if you need extra fields later.

Why the reversed print order:
    This printer's upside-down mode (ESC { ) only rotates each printed
    character/pixel row 180 degrees in place - it doesn't change the feed
    direction. So whatever is sent first still ends up physically nearest
    the start of the strip, which becomes the BOTTOM of the page once you
    flip the finished strip over to read it normally. To make the notice
    read correctly top-to-bottom after flipping, we render it normally
    then send it to the printer back-to-front.

Requirements: pip install python-escpos pillow
"""

import csv
import re
import textwrap
import time
from pathlib import Path

from PIL import Image
from escpos.printer import Serial as escSerial

# ============================== CONFIG ==============================

PORT = "COM9"
BAUDRATE = 9600

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_FILE = BASE_DIR / "notice_template.txt"
CSV_FILE = BASE_DIR / "notices.csv"
STAMP_IMAGE = BASE_DIR / "stamp_small.bmp"
STAMP_MARKER = "{STAMP}"

LINE_WIDTH = 32  # characters per printed row
FEED_LINES_AFTER = 6  # blank lines fed after each notice (cut point)

# The printer's input buffer is tiny and silently drops data if it's
# overrun, so every send below is flushed and paced individually (same
# fix as WRITE_DELAY in sync_printers.py).
WRITE_DELAY = 0.05
IMAGE_DELAY = 1.0  # the stamp is a much bigger payload than a text line

# Raw ESC/POS command to toggle upside-down character printing (ESC { n).
UPSIDE_DOWN_ON = b"\x1b\x7b\x01"
UPSIDE_DOWN_OFF = b"\x1b\x7b\x00"

# ====================================================================


def render_blocks(template_text, data, width=LINE_WIDTH):
    """Turn the template + one CSV row into an ordered list of print blocks.

    Each block is ("text", line) or ("image", path). Paragraphs are
    separated by blank lines in the template and re-wrapped to `width`; a
    paragraph that is only STAMP_MARKER becomes an image block instead.
    """
    blocks = []
    paragraphs = re.split(r"\n\s*\n", template_text.strip())

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if paragraph == STAMP_MARKER:
            blocks.append(("image", STAMP_IMAGE))
            continue

        filled = paragraph.format(**data)
        joined = " ".join(filled.split())
        for line in textwrap.wrap(joined, width=width):
            blocks.append(("text", line))
        blocks.append(("text", ""))

    while blocks and blocks[-1] == ("text", ""):
        blocks.pop()

    return blocks


def connect():
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
    printer.hw("INIT")
    return printer


def _send(printer, delay=WRITE_DELAY):
    """Flush whatever was just written and pause before the next send."""
    printer.device.flush()
    time.sleep(delay)


def print_blocks(printer, blocks):
    """Send blocks to the printer back-to-front, one at a time, in upside-down mode."""
    printer._raw(UPSIDE_DOWN_ON)
    _send(printer)

    for kind, value in reversed(blocks):
        if kind == "text":
            printer.text(value + "\n")
            _send(printer)
        else:
            # Raster images aren't affected by ESC {, so rotate them by hand.
            image = Image.open(value).convert("1").rotate(180)
            printer.image(
                image,
                impl="bitImageRaster",
                high_density_horizontal=True,
                high_density_vertical=True,
            )
            _send(printer, delay=IMAGE_DELAY)

    printer._raw(UPSIDE_DOWN_OFF)
    _send(printer)
    printer.text("\n" * FEED_LINES_AFTER)
    _send(printer)


def load_rows(csv_file):
    with open(csv_file, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    template_text = TEMPLATE_FILE.read_text(encoding="utf-8")
    rows = load_rows(CSV_FILE)

    printer = connect()
    try:
        for row in rows:
            blocks = render_blocks(template_text, row)
            print_blocks(printer, blocks)
    finally:
        printer.close()


if __name__ == "__main__":
    main()
