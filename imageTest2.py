"""
Simple BMP image printer test.

Printer:
    Goojprt QR203

Port:
    COM11

Image:
    stamp_small.bmp

Requirements:
    pip install python-escpos pillow
"""

import os
import time

from PIL import Image
from escpos.printer import Serial as escSerial


# ============================== CONFIG ==============================

PORT = "COM11"
BAUDRATE = 9600

IMAGE_FILE = "stamp_small.bmp"

# Set to True if you want the image centered.
CENTER_IMAGE = True

# Number of blank lines after printing.
FEED_LINES = 1

# ====================================================================


def main():

    printer = None

    try:
        # ------------------------------------------------------------
        # FIND IMAGE
        # ------------------------------------------------------------

        image_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            IMAGE_FILE
        )

        print()
        print("=" * 60)
        print("BMP IMAGE PRINT TEST")
        print("=" * 60)
        print()

        print(f"Printer: {PORT}")
        print(f"Baudrate: {BAUDRATE}")
        print(f"Image:    {image_path}")
        print()

        if not os.path.exists(image_path):
            raise FileNotFoundError(
                f"Image not found:\n{image_path}"
            )

        # ------------------------------------------------------------
        # OPEN IMAGE
        # ------------------------------------------------------------

        image = Image.open(image_path)

        print(
            f"Image size: "
            f"{image.width} x {image.height} pixels"
        )

        print(
            f"Image mode: {image.mode}"
        )

        # Convert to a format suitable for ESC/POS printing.
        image = image.convert("1")

        # ------------------------------------------------------------
        # CONNECT TO PRINTER
        # ------------------------------------------------------------

        print()
        print("Opening COM11...")

        printer = escSerial(
            devfile=PORT,
            baudrate=BAUDRATE,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=1,
            dsrdtr=False,
        )

        print("Printer connected.")

        # ------------------------------------------------------------
        # INITIALIZE
        # ------------------------------------------------------------

        printer.hw("INIT")

        time.sleep(0.5)

        # ------------------------------------------------------------
        # ALIGNMENT
        # ------------------------------------------------------------

        if CENTER_IMAGE:
            printer.set(align="center")
        else:
            printer.set(align="left")

        # ------------------------------------------------------------
        # PRINT IMAGE
        # ------------------------------------------------------------

        print()
        print("Sending image to printer...")

        printer.image(
            image,
            impl="bitImageRaster",
            high_density_horizontal=True,
            high_density_vertical=True,
        )

        # ------------------------------------------------------------
        # FEED PAPER
        # ------------------------------------------------------------

        print("Feeding paper...")

        printer.text(
            "\n" * FEED_LINES
        )

        print()
        print("Image sent successfully.")
        print()

    except Exception as e:

        print()
        print("=" * 60)
        print("PRINT FAILED")
        print("=" * 60)
        print()

        print(type(e).__name__)
        print(str(e))
        print()

    finally:

        if printer is not None:

            print("Closing printer...")

            try:
                printer.close()
            except Exception:
                pass

        print("Done.")
        print()


if __name__ == "__main__":
    main()