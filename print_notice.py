"""
Print ownerless-property notices upside-down across three thermal printers.

Each notice is split across three printers, one template part each:
    printer 1 (PORT_1) <- notice_template_pt1.txt (the NOTICE)
    printer 2 (PORT_2) <- notice_template_pt2.txt (the COURT DECISION)
    printer 3 (PORT_3) <- notice_template_pt3.txt (the REAL ESTATE LISTING)
Every INTERVAL_SECONDS (aligned to the wall clock, not to script start time),
the next row of notices.csv is printed on printer 1, then printer 2, then
printer 3 - each one only starts once the previous has finished printing.
Once the last CSV row has been printed, it loops back to the first row.
If a printer fails (unplugged, wrong port, etc.) the error is logged and
the remaining printers still get their turn instead of the run aborting.

Data flow (edit these, not this file, to change what gets printed):
    notice_template_pt{1,2,3}.txt - the blueprints. Free text, blank-line-
                           separated paragraphs, re-wrapped automatically.
                           Placeholders such as {address}, {judge_name},
                           {decision} are filled in from the CSV; a
                           paragraph containing only the literal "{STAMP}"
                           is replaced by stamp_small.bmp. A paragraph may
                           start with "[big]" or "[tall]" to print it at
                           double size, and/or "[bold]" to emphasize it
                           (e.g. "[big][bold]"); otherwise it prints normal
                           size, not bold.
    notices.csv         - one row per notice. Add more columns/placeholders
                           together in both files if you need extra fields.

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

# Serial ports for the three printers, one per template part.
PORT_1 = "COM9"
PORT_2 = "COM10"
PORT_3 = "COM11"
BAUDRATE = 9600

BASE_DIR = Path(__file__).resolve().parent
PRINTERS = (
    (PORT_1, BASE_DIR / "notice_template_pt1.txt"),
    (PORT_2, BASE_DIR / "notice_template_pt2.txt"),
    (PORT_3, BASE_DIR / "notice_template_pt3.txt"),
)
CSV_FILE = BASE_DIR / "notices.csv"
STAMP_IMAGE = BASE_DIR / "stamp_small.bmp"
STAMP_MARKER = "{STAMP}"

# How often a new notice is printed, aligned to the wall clock (e.g. every
# hour at :00, :06, :12, ...) rather than to whenever the script started.
INTERVAL_SECONDS = 6 * 60

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

# Raw ESC/POS text size command (GS ! n: high nibble = width x2, low = height x2).
SIZE_COMMANDS = {
    None: b"\x1d\x21\x00",
    "normal": b"\x1d\x21\x00",
    "tall": b"\x1d\x21\x01",
    "big": b"\x1d\x21\x11",
}

# Raw ESC/POS emphasized (bold) mode command (ESC E n).
BOLD_ON = b"\x1b\x45\x01"
BOLD_OFF = b"\x1b\x45\x00"

# A paragraph may start with one or more of these tags in brackets, e.g.
# "[big]", "[bold]", or "[big][bold]" combined. Size tags are mutually
# exclusive (the last one wins); "bold" stacks with any size.
PARAGRAPH_TAG_PATTERN = re.compile(r"^\[(big|tall|normal|bold)\]\s*", re.IGNORECASE)


def _parse_paragraph_tags(paragraph):
    """Strip leading [tag] markers, returning (size_tag, bold, rest_of_text)."""
    size_tag, bold = None, False
    while True:
        match = PARAGRAPH_TAG_PATTERN.match(paragraph)
        if not match:
            return size_tag, bold, paragraph
        tag = match.group(1).lower()
        if tag == "bold":
            bold = True
        else:
            size_tag = tag
        paragraph = paragraph[match.end():]

# ====================================================================


def render_blocks(template_text, data, width=LINE_WIDTH):
    """Turn the template + one CSV row into an ordered list of print blocks.

    Each block is ("text", line, size_tag, bold) or ("image", path, None, None).
    Paragraphs are separated by blank lines in the template and re-wrapped
    to `width`; a paragraph that is only STAMP_MARKER becomes an image
    block instead. Leading "[big]"/"[tall]"/"[bold]" markers (stackable,
    e.g. "[big][bold]") size and/or emphasize the whole paragraph.
    """
    blocks = []
    paragraphs = re.split(r"\n\s*\n", template_text.strip())

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if paragraph == STAMP_MARKER:
            blocks.append(("image", STAMP_IMAGE, None, None))
            continue

        size_tag, bold, paragraph = _parse_paragraph_tags(paragraph)

        filled = paragraph.format(**data)
        joined = " ".join(filled.split())
        # "big" doubles character width too, so it fits half as many per line.
        wrap_width = width // 2 if size_tag == "big" else width
        for line in textwrap.wrap(joined, width=wrap_width):
            blocks.append(("text", line, size_tag, bold))
        blocks.append(("text", "", size_tag, bold))

    while blocks and blocks[-1][:2] == ("text", ""):
        blocks.pop()

    return blocks


def connect(port):
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
    return printer


def _send(printer, delay=WRITE_DELAY):
    """Flush whatever was just written and pause before the next send."""
    printer.device.flush()
    time.sleep(delay)


def _text_line(printer, line):
    """Write one line as raw CP437 bytes.

    python-escpos's printer.text() "magic encodes" text, which can inject
    code-page switch commands this printer clone doesn't understand and
    prints as gibberish. CP437 is the ESC/POS default code page, so we
    encode and send the bytes ourselves instead.
    """
    printer._raw(line.encode("cp437", errors="replace") + b"\n")


def print_blocks(printer, blocks):
    """Send blocks to the printer back-to-front, one at a time, in upside-down mode."""
    printer._raw(UPSIDE_DOWN_ON)
    _send(printer)

    for kind, value, size_tag, bold in reversed(blocks):
        if kind == "text":
            printer._raw(SIZE_COMMANDS[size_tag])
            printer._raw(BOLD_ON if bold else BOLD_OFF)
            _text_line(printer, value)
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

    printer._raw(SIZE_COMMANDS[None])
    printer._raw(BOLD_OFF)
    printer._raw(UPSIDE_DOWN_OFF)
    _send(printer)
    printer._raw(b"\n" * FEED_LINES_AFTER)
    _send(printer)


def load_rows(csv_file):
    with open(csv_file, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _log(message):
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}", flush=True)


def _next_tick(interval=INTERVAL_SECONDS):
    """Return the next interval boundary aligned to the wall clock (epoch time)."""
    return (time.time() // interval + 1) * interval


def _sleep_until(timestamp):
    delay = timestamp - time.time()
    if delay > 0:
        time.sleep(delay)


def print_notice_row(row):
    """Print one CSV row across all three printers, one after another.

    Each printer only connects and prints once the previous one has
    finished (and disconnected), so there's never more than one printer
    active at a time. A failure on one printer (unplugged, wrong port,
    bad template, ...) is logged and skipped rather than aborting the
    whole row - the remaining printers still get their turn.
    """
    for port, template_file in PRINTERS:
        try:
            template_text = template_file.read_text(encoding="utf-8")
            blocks = render_blocks(template_text, row)
            printer = connect(port)
        except Exception as exc:
            _log(f"ERROR: {port} could not start printing ({exc!r}); skipping it")
            continue

        try:
            print_blocks(printer, blocks)
        except Exception as exc:
            _log(f"ERROR: {port} failed while printing ({exc!r})")
        finally:
            try:
                printer.close()
            except Exception as exc:
                _log(f"ERROR: {port} failed to close cleanly ({exc!r})")


def main():
    rows = load_rows(CSV_FILE)
    row_index = 0
    while True:
        _sleep_until(_next_tick())
        try:
            print_notice_row(rows[row_index % len(rows)])
        except Exception as exc:
            _log(f"ERROR: unexpected failure printing row {row_index % len(rows)} ({exc!r})")
        row_index += 1


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
