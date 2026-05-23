"""
Flipper Zero serial interface for MeshtasticBot.

Communicates with a Flipper Zero connected via USB (CDC ACM serial port).
Used to replay saved SubGHz transmissions (e.g. awning remote control).

The Flipper Zero exposes a CLI over serial at 115200 baud.  We send a
`subghz tx_from_file <path>` command and wait for the prompt to return.
"""

import time

import serial
import structlog

log = structlog.get_logger()

# Seconds to wait for the Flipper CLI to respond
_DEFAULT_TIMEOUT = 8.0

# The Flipper CLI prompt
_PROMPT = b">: "


def send_subghz_file(device: str, filepath: str, timeout: float = _DEFAULT_TIMEOUT) -> str:
    """Replay a saved SubGHz .sub file via the Flipper Zero CLI.

    Args:
        device:   Serial device path, e.g. "/dev/ttyACM0".
        filepath: Path to the .sub file on the Flipper's SD card,
                  e.g. "/ext/subghz/awning_open.sub".
        timeout:  Seconds to wait for the CLI response.

    Returns:
        The Flipper's response text (stripped).

    Raises:
        serial.SerialException: If the device cannot be opened.
        TimeoutError: If the Flipper does not respond within *timeout* seconds.
    """
    log.info("flipper_tx_start", device=device, filepath=filepath)
    with serial.Serial(device, 115200, timeout=1.0) as ser:
        # Drain any buffered output / get to a clean prompt
        ser.write(b"\r\n")
        time.sleep(0.3)
        ser.read(ser.in_waiting or 1)

        cmd = f"subghz tx_from_file {filepath}\r\n".encode()
        ser.write(cmd)

        # Read until we see the prompt again (command finished)
        deadline = time.monotonic() + timeout
        buf = b""
        while time.monotonic() < deadline:
            chunk = ser.read(ser.in_waiting or 1)
            buf += chunk
            if _PROMPT in buf:
                break
            time.sleep(0.05)
        else:
            raise TimeoutError(f"Flipper did not respond within {timeout}s")

    # Strip the echoed command and trailing prompt
    response = buf.decode(errors="replace").strip()
    log.info("flipper_tx_done", device=device, filepath=filepath, response=response)
    return response
