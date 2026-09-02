import serial
import time
from PIL import Image

PORT = "COM11"
BAUDRATE = 9600

PRINTER_WIDTH = 384


def print_bmp(filename):

    image = Image.open(filename).convert("L")

    # ---------------------------------------------------------
    # Resize to printer width
    # ---------------------------------------------------------

    if image.width > PRINTER_WIDTH:

        ratio = PRINTER_WIDTH / image.width
        new_height = int(image.height * ratio)

        image = image.resize(
            (PRINTER_WIDTH, new_height),
            Image.Resampling.LANCZOS
        )

    # Pad to 384 pixels
    if image.width < PRINTER_WIDTH:

        padded = Image.new(
            "L",
            (PRINTER_WIDTH, image.height),
            255
        )

        padded.paste(image, (0, 0))
        image = padded

    # Convert to 1-bit
    image = image.convert("1")

    width, height = image.size
    width_bytes = width // 8

    print(f"Image: {width} x {height}")
    print(f"Raster bytes: {width_bytes * height:,}")

    # Estimate transmission time
    estimated_seconds = (
        (width_bytes * height) * 10 / BAUDRATE
    )

    print(
        f"Estimated serial transmission time: "
        f"{estimated_seconds:.1f} seconds"
    )

    # ---------------------------------------------------------
    # Build raster
    # ---------------------------------------------------------

    raster = bytearray()

    for y in range(height):

        for x in range(0, width, 8):

            byte = 0

            for bit in range(8):

                if image.getpixel(
                    (x + bit, y)
                ) == 0:

                    byte |= 1 << (7 - bit)

            raster.append(byte)

    # ---------------------------------------------------------
    # GS v 0 header
    # ---------------------------------------------------------

    command = bytearray([
        0x1D,       # GS
        0x76,       # v
        0x30,       # 0
        0x00,       # normal

        width_bytes & 0xFF,
        (width_bytes >> 8) & 0xFF,

        height & 0xFF,
        (height >> 8) & 0xFF,
    ])

    command.extend(raster)

    print(f"Total command size: {len(command):,} bytes")

    # ---------------------------------------------------------
    # Serial connection
    # ---------------------------------------------------------

    printer = serial.Serial(
        port=PORT,
        baudrate=BAUDRATE,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,

        # Read timeout
        timeout=2,

        # IMPORTANT:
        # None = don't abort the image transmission.
        write_timeout=None,

        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    )

    try:

        # Initialize
        printer.write(b"\x1B\x40")

        time.sleep(0.5)

        # -----------------------------------------------------
        # SEND ENTIRE IMAGE
        # -----------------------------------------------------

        print("Sending image...")

        start = time.perf_counter()

        printer.write(command)

        elapsed = time.perf_counter() - start

        print(
            f"Image transmission completed in "
            f"{elapsed:.1f} seconds"
        )

        printer.flush()

        # Give printer time to finish physically printing
        time.sleep(2)

        # Feed paper
        printer.write(b"\x0A\x0A\x0A")
        printer.flush()

        time.sleep(1)

        print("Done.")

    finally:
        printer.close()


if __name__ == "__main__":
    print_bmp("stamp_small.bmp")
