import serial
import time
import sys
import msvcrt

# Change this to your COM port
PORT_1 = "COM10"
PORT_2 = "COM9"
PORT_3 = "COM11"

# Change if your printer uses a different baud rate
BAUDRATE = 9600


def send(printer, data):
    printer.write(data)
    printer.flush()
    time.sleep(0.1)


def print_inverse(printer, enabled=True):
    """
    Enable/disable upside-down (180°) printing.

    ESC { n
    n = 1 -> upside down
    n = 0 -> normal
    """
    send(printer, b"\x1b\x7b" + (b"\x01" if enabled else b"\x00"))


def print_round(printer, idx : int, blank : bool = False):
    """
    Print one complete round on a single printer.
    """

    # Initialize printer
    send(printer, b"\x1b\x40")


    # Main test
    for _ in range(10):
        if blank:
            send(printer, b"\n")
        else:
            match idx:
                case 1:
                    send(printer, b"PRINT\n")
                case 2:
                    send(printer, b"      PRINT\n")
                case 3:
                    send(printer, b"            PRINT\n")

    # 5 blank lines
    for _ in range(10):
        send(printer, b"\n")
    # Final newline
    send(printer, b"\n")

    # Disable upside-down mode
    print_inverse(printer, False)

    # Feed paper
    send(printer, b"\x1b\x64\x05")


def main():

    try:
        print(f"Opening {PORT_1} at {BAUDRATE} baud...")
        printer1 = serial.Serial(
            port=PORT_1,
            baudrate=BAUDRATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=2,
            write_timeout=2,
        )

        print(f"Opening {PORT_2} at {BAUDRATE} baud...")
        printer2 = serial.Serial(
            port=PORT_2,
            baudrate=BAUDRATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=2,
            write_timeout=2,
        )

        print(f"Opening {PORT_3} at {BAUDRATE} baud...")
        printer3 = serial.Serial(
            port=PORT_3,
            baudrate=BAUDRATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=2,
            write_timeout=2,
        )

    except Exception as e:
        print(f"Could not open printer: {e}")
        sys.exit(1)

    try:

        print()
        print("Ready.")
        print("1 = Printer 1")
        print("2 = Printer 2")
        print("3 = Printer 3")
        print("A = All printers")
        print("Q = Quit")
        print()

        while True:

            key = msvcrt.getwch().lower()

            if key == "1":
                print("Printing on Printer 1...")
                print_round(printer1, 1)
                print_round(printer2, 2, blank=True)
                print_round(printer3, 3, blank=True)

            elif key == "2":
                print("Printing on Printer 2...")
                print_round(printer1, 1)
                print_round(printer2, 2)
                print_round(printer3, 3, blank=True)

            elif key == "3":
                print("Printing on Printer 3...")
                print_round(printer1, 1)
                print_round(printer2, 2)
                print_round(printer3, 3)

            elif key == "a":
                print("Printing on all printers...")

                print_round(printer1, 1)
                print_round(printer2, 2)
                print_round(printer3, 3)

            elif key == "q":
                print("Exiting...")
                break

    except Exception as e:
        print(f"Error while printing: {e}")

    finally:
        printer1.close()
        printer2.close()
        printer3.close()

        print("Printer connections closed.")


if __name__ == "__main__":
    main()
