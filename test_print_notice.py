"""
Offline regression tests for print_notice.py - no real serial hardware needed.

Run with: .venv/bin/python3 test_print_notice.py
Every check either passes silently or raises/prints a clear failure; a
final summary line reports pass/fail counts.
"""

import string
import sys
import time
import traceback
from pathlib import Path
from unittest import mock

import escpos.printer as escmod


class FakeSerial:
    """Stand-in for escpos.printer.Serial that records everything sent."""

    instances = []

    def __init__(self, devfile, **kwargs):
        self.devfile = devfile
        self.kwargs = kwargs
        self.device = self
        self.raw_log = []  # list of bytes objects passed to _raw
        self.images = []  # list of PIL images passed to .image()
        self.flush_count = 0
        self.closed = False
        self.opened_at = time.time()
        self.closed_at = None
        FakeSerial.instances.append(self)

    def hw(self, *a, **kw):
        pass

    def flush(self):
        self.flush_count += 1

    def _raw(self, data):
        self.raw_log.append(data)

    def image(self, img, **kw):
        self.images.append((img, kw))

    def close(self):
        self.closed = True
        self.closed_at = time.time()


escmod.Serial = FakeSerial

import print_notice as pn  # noqa: E402  (must patch escpos before importing)

pn.escSerial = FakeSerial

results = []


def check(name, fn):
    try:
        fn()
        results.append((name, True, None))
        print(f"PASS  {name}")
    except Exception as exc:  # noqa: BLE001
        results.append((name, False, exc))
        print(f"FAIL  {name}: {exc}")
        traceback.print_exc(limit=3)


TEMPLATE_FILES = [t for _, t in pn.PRINTERS]


# ---------------------------------------------------------------------------
# 1. Static files exist and are readable
# ---------------------------------------------------------------------------
def test_files_exist():
    for path in (*TEMPLATE_FILES, pn.CSV_FILE, pn.STAMP_IMAGE):
        assert path.exists(), f"missing file: {path}"


# ---------------------------------------------------------------------------
# 2. CSV loads, has rows, and every template placeholder has a matching column
# ---------------------------------------------------------------------------
def test_csv_matches_template_placeholders():
    rows = pn.load_rows(pn.CSV_FILE)
    assert rows, "notices.csv has no data rows"
    fieldnames = set(rows[0].keys())

    formatter = string.Formatter()
    for template_file in TEMPLATE_FILES:
        text = template_file.read_text(encoding="utf-8")
        placeholders = {
            field
            for _, field, _, _ in formatter.parse(text)
            if field and field != "STAMP"
        }
        missing = placeholders - fieldnames
        assert not missing, f"{template_file.name} needs columns not in CSV: {missing}"


# ---------------------------------------------------------------------------
# 3. render_blocks succeeds for every (template, row) combo, no KeyError etc.
# ---------------------------------------------------------------------------
def test_render_blocks_all_rows():
    rows = pn.load_rows(pn.CSV_FILE)
    for template_file in TEMPLATE_FILES:
        text = template_file.read_text(encoding="utf-8")
        for row in rows:
            pn.render_blocks(text, row)  # raises on failure


# ---------------------------------------------------------------------------
# 4. Every rendered text line fits its physical width ("big" = half width)
# ---------------------------------------------------------------------------
def test_line_widths():
    rows = pn.load_rows(pn.CSV_FILE)
    overflows = []
    for template_file in TEMPLATE_FILES:
        text = template_file.read_text(encoding="utf-8")
        for row in rows:
            for kind, value, size_tag, _ in pn.render_blocks(text, row):
                if kind != "text":
                    continue
                limit = pn.LINE_WIDTH // 2 if size_tag == "big" else pn.LINE_WIDTH
                if len(value) > limit:
                    overflows.append((template_file.name, size_tag, value))
    assert not overflows, f"lines exceeding printer width: {overflows}"


# ---------------------------------------------------------------------------
# 5. The {STAMP} paragraph in pt2 is isolated (exact match) so it becomes an
#    image block instead of failing .format() with a KeyError.
# ---------------------------------------------------------------------------
def test_stamp_marker_isolated():
    rows = pn.load_rows(pn.CSV_FILE)
    pt2_text = None
    for port, template_file in pn.PRINTERS:
        if template_file.name == "notice_template_pt2.txt":
            pt2_text = template_file.read_text(encoding="utf-8")
    assert pt2_text is not None, "notice_template_pt2.txt not wired to a printer"
    blocks = pn.render_blocks(pt2_text, rows[0])
    kinds = [k for k, _, _, _ in blocks]
    assert "image" in kinds, "STAMP paragraph did not become an image block"


# ---------------------------------------------------------------------------
# 6. cp437 round-trip: flag any characters that get mangled into '?' when
#    encoded for the printer (this is what _text_line() actually sends).
# ---------------------------------------------------------------------------
def test_cp437_losslessness():
    rows = pn.load_rows(pn.CSV_FILE)
    lossy = []
    for template_file in TEMPLATE_FILES:
        text = template_file.read_text(encoding="utf-8")
        for row in rows:
            for kind, value, _, _ in pn.render_blocks(text, row):
                if kind != "text" or not value:
                    continue
                roundtrip = value.encode("cp437", errors="replace").decode("cp437")
                if roundtrip != value:
                    lossy.append(value)
    if lossy:
        sample = "\n    ".join(dict.fromkeys(lossy[:8]))
        raise AssertionError(
            f"{len(lossy)} lines contain characters cp437 can't represent "
            f"(they will print as '?'), e.g.:\n    {sample}"
        )


# ---------------------------------------------------------------------------
# 7. print_notice_row() opens/closes printers strictly in order 1 -> 2 -> 3,
#    each fully closed before the next opens, and only sends its own template.
# ---------------------------------------------------------------------------
def test_sequential_printer_handoff():
    FakeSerial.instances.clear()
    rows = pn.load_rows(pn.CSV_FILE)
    pn.print_notice_row(rows[0])

    assert len(FakeSerial.instances) == 3, "expected exactly 3 printer connections"
    ports = [inst.devfile for inst in FakeSerial.instances]
    assert ports == [pn.PORT_1, pn.PORT_2, pn.PORT_3], f"wrong port order: {ports}"

    for inst in FakeSerial.instances:
        assert inst.closed, f"printer on {inst.devfile} was never closed"

    # Strict non-overlap: printer N must close at/before printer N+1 opens.
    for prev, nxt in zip(FakeSerial.instances, FakeSerial.instances[1:]):
        assert prev.closed_at <= nxt.opened_at, (
            f"{prev.devfile} closed after {nxt.devfile} opened - overlap detected"
        )

    # Each printer only ever receives upside-down toggles + its own content;
    # sanity-check it actually wrote something.
    for inst in FakeSerial.instances:
        assert pn.UPSIDE_DOWN_ON in inst.raw_log
        assert pn.UPSIDE_DOWN_OFF in inst.raw_log
        assert len(inst.raw_log) > 2


# ---------------------------------------------------------------------------
# 8. print_blocks sends text blocks in reverse order (back-to-front feeding)
# ---------------------------------------------------------------------------
def test_print_blocks_reversed_order():
    FakeSerial.instances.clear()
    rows = pn.load_rows(pn.CSV_FILE)
    text = TEMPLATE_FILES[0].read_text(encoding="utf-8")
    blocks = pn.render_blocks(text, rows[0])
    text_blocks = [b for b in blocks if b[0] == "text" and b[1]]
    assert text_blocks, "template produced no text lines"

    printer = pn.connect(pn.PORT_1)
    pn.print_blocks(printer, blocks)
    printer.close()

    sent_lines = [
        raw[:-1].decode("cp437")
        for raw in printer.raw_log
        if raw.endswith(b"\n") and raw not in (pn.UPSIDE_DOWN_ON, pn.UPSIDE_DOWN_OFF)
    ]
    # Compare post-cp437 (lossy for non-Latin chars) on both sides, since this
    # test is only about ordering, not encoding fidelity (see the dedicated
    # cp437 losslessness test for that).
    expected_first = text_blocks[-1][1].encode("cp437", errors="replace").decode("cp437")
    assert sent_lines[0] == expected_first, (
        f"expected last template line to print first, got {sent_lines[0]!r}"
    )


# ---------------------------------------------------------------------------
# 9. Clock-aligned scheduling: _next_tick lands on an exact interval boundary
#    in the future, and _sleep_until never sleeps for a past/now timestamp.
# ---------------------------------------------------------------------------
def test_scheduling_alignment():
    interval = 360
    fixed_now = 1_000_000_037  # arbitrary, not aligned to 360
    with mock.patch("time.time", return_value=fixed_now):
        tick = pn._next_tick(interval=interval)
        assert tick % interval == 0, f"tick {tick} not aligned to {interval}s"
        assert tick > fixed_now, "tick must be strictly in the future"
        assert tick - fixed_now <= interval, "tick further away than one interval"

    with mock.patch("time.time", return_value=fixed_now):
        with mock.patch("time.sleep") as sleep_mock:
            pn._sleep_until(fixed_now - 5)  # a timestamp already in the past
            sleep_mock.assert_not_called()


# ---------------------------------------------------------------------------
# 10. main() loop cycles through all CSV rows in order and wraps around,
#     using a fake clock so it doesn't actually wait 6 minutes per tick.
# ---------------------------------------------------------------------------
def test_main_loop_cycles_rows():
    rows = pn.load_rows(pn.CSV_FILE)
    seen_rows = []
    call_count = {"n": 0}
    STOP_AFTER = len(rows) + 3  # run past a full cycle to confirm wraparound

    def fake_print_notice_row(row):
        seen_rows.append(row)
        call_count["n"] += 1
        if call_count["n"] >= STOP_AFTER:
            raise KeyboardInterrupt

    with mock.patch.object(pn, "print_notice_row", side_effect=fake_print_notice_row), \
         mock.patch.object(pn, "_sleep_until", return_value=None):
        try:
            pn.main()
        except KeyboardInterrupt:
            pass

    assert len(seen_rows) == STOP_AFTER
    # rows 0..9 then wrap to 0,1,2
    expected_addresses = [rows[i % len(rows)]["address"] for i in range(STOP_AFTER)]
    actual_addresses = [r["address"] for r in seen_rows]
    assert actual_addresses == expected_addresses, "row order/wraparound is wrong"


# ---------------------------------------------------------------------------
# 11. A hardware failure on one printer is logged and skipped, but the other
#     printers still get their turn (no whole-run abort).
# ---------------------------------------------------------------------------
def test_connect_failure_is_isolated():
    FakeSerial.instances.clear()
    rows = pn.load_rows(pn.CSV_FILE)
    real_connect = pn.connect

    def flaky_connect(port):
        if port == pn.PORT_2:
            raise OSError(f"simulated: could not open {port}")
        return real_connect(port)

    with mock.patch.object(pn, "connect", side_effect=flaky_connect):
        pn.print_notice_row(rows[0])  # must not raise

    ports = [inst.devfile for inst in FakeSerial.instances]
    assert ports == [pn.PORT_1, pn.PORT_3], (
        f"expected printer 2 to be skipped, got connections: {ports}"
    )
    for inst in FakeSerial.instances:
        assert inst.closed, f"printer on {inst.devfile} was never closed"


# ---------------------------------------------------------------------------
# 12. A failure mid-print (print_blocks raises) still closes that printer and
#     doesn't stop the remaining printers from getting their turn.
# ---------------------------------------------------------------------------
def test_print_failure_is_isolated():
    FakeSerial.instances.clear()
    rows = pn.load_rows(pn.CSV_FILE)
    real_print_blocks = pn.print_blocks

    def flaky_print_blocks(printer, blocks):
        if printer.devfile == pn.PORT_1:
            raise RuntimeError("simulated print failure")
        return real_print_blocks(printer, blocks)

    with mock.patch.object(pn, "print_blocks", side_effect=flaky_print_blocks):
        pn.print_notice_row(rows[0])  # must not raise

    ports = [inst.devfile for inst in FakeSerial.instances]
    assert ports == [pn.PORT_1, pn.PORT_2, pn.PORT_3], f"expected all 3 to be attempted: {ports}"
    for inst in FakeSerial.instances:
        assert inst.closed, f"printer on {inst.devfile} was never closed despite the failure"


# ---------------------------------------------------------------------------
# 13. main()'s loop keeps going even if a whole row fails unexpectedly.
# ---------------------------------------------------------------------------
def test_main_loop_survives_row_failure():
    rows = pn.load_rows(pn.CSV_FILE)
    call_count = {"n": 0}

    def flaky_print_notice_row(row):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated failure on the 2nd tick")
        if call_count["n"] >= 4:
            raise KeyboardInterrupt

    with mock.patch.object(pn, "print_notice_row", side_effect=flaky_print_notice_row), \
         mock.patch.object(pn, "_sleep_until", return_value=None):
        try:
            pn.main()
        except KeyboardInterrupt:
            pass

    assert call_count["n"] == 4, "main() should have kept ticking past the failed row"


TESTS = [
    ("files exist", test_files_exist),
    ("csv columns cover all template placeholders", test_csv_matches_template_placeholders),
    ("render_blocks succeeds for every template x row", test_render_blocks_all_rows),
    ("rendered lines fit printer width", test_line_widths),
    ("STAMP marker becomes an image block", test_stamp_marker_isolated),
    ("cp437 encoding is lossless for all rendered text", test_cp437_losslessness),
    ("printers open/close strictly in order 1->2->3", test_sequential_printer_handoff),
    ("print_blocks sends lines back-to-front", test_print_blocks_reversed_order),
    ("tick scheduling aligns to wall clock", test_scheduling_alignment),
    ("main() loop cycles + wraps CSV rows", test_main_loop_cycles_rows),
    ("connect() failure on one printer is isolated", test_connect_failure_is_isolated),
    ("print failure on one printer is isolated", test_print_failure_is_isolated),
    ("main() loop survives a failed row", test_main_loop_survives_row_failure),
]


if __name__ == "__main__":
    for name, fn in TESTS:
        check(name, fn)

    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    print(f"\n{passed}/{len(results)} passed" + (f", {failed} FAILED" if failed else ""))
    sys.exit(1 if failed else 0)
