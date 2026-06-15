"""
pi_client.py — runs on each Pi Zero with a 7.5" e-paper display + Digispark.
Connects to the main PC server, displays full-screen rendered scenes, and
sends A/B choices from the Digispark back to the server.

Usage:
  python pi_client.py <server_ip> [port]

Requires:
  - Pillow (PIL)
  - evdev
  - waveshare_epd (for your specific e-paper variant)
"""

from __future__ import annotations

import base64
import json
import logging
import socket
import sys
import time
from io import BytesIO

from PIL import Image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# E-Paper driver — pick your variant by uncommenting the right import
# ---------------------------------------------------------------------------
# from waveshare_epd import epd7in5 as epd_driver      # V1 (640x384)
from waveshare_epd import epd7in5_V2 as epd_driver   # V2 (800x480)
# from waveshare_epd import epd7in5_HD as epd_driver   # HD (880x528)

# Native e-paper resolution (landscape)
EPD_W = epd_driver.EPD_WIDTH   # 800
EPD_H = epd_driver.EPD_HEIGHT  # 480

# Server renders at portrait resolution; the Pi Zero tells the server these
# values in the hello message so the server picks the right layout.
RENDER_W = 480
RENDER_H = 800

# Should the received portrait image be rotated to match the physical
# orientation of the e-paper?  If the display is physically mounted in
# landscape and you want portrait, set ROTATE = 90 (counter-clockwise).
# If mounted in portrait already, set ROTATE = 0.
ROTATE = 90

# ---------------------------------------------------------------------------
# Digispark evdev discovery
# ---------------------------------------------------------------------------

KEY_A = 30   # KEY_A evdev code
KEY_B = 48   # KEY_B evdev code

DIGISTUMP_VID = 0x16C0
DIGIKEY_PID = 0x27DB


def find_digispark() -> str | None:
    """Find the input event device for the Digispark keyboard."""
    from evdev import InputDevice, list_devices
    for path in list_devices():
        try:
            dev = InputDevice(path)
            # Match by known Digistump USB VID/PID first; then by common names.
            if dev.info.vendor == DIGISTUMP_VID and dev.info.product == DIGIKEY_PID:
                log.info("Found Digispark by VID/PID at %s: %s", path, dev.name)
                return path

            name = dev.name.lower()
            if (
                "digispark" in name
                or "digispart" in name
                or "digikey" in name
                or "digistump" in name
                or "usb keyboard" in name
            ):
                log.info("Found Digispark at %s: %s", path, dev.name)
                return path
            dev.close()
        except Exception:
            continue
    # Fallback: return first keyboard-like device
    for path in list_devices():
        try:
            dev = InputDevice(path)
            if "keyboard" in dev.name.lower() and "virtual" not in dev.name.lower():
                log.info("Fallback: using keyboard at %s: %s", path, dev.name)
                return path
            dev.close()
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

def connect(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(15.0)
    sock.connect((host, port))
    sock.settimeout(None)
    log.info("Connected to %s:%d", host, port)
    return sock


def send_json(sock: socket.socket, msg: dict):
    sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))


def recv_line(sock: socket.socket) -> str:
    buf = b""
    sock.settimeout(10.0)
    try:
        while True:
            c = sock.recv(1)
            if not c:
                raise ConnectionError("Server disconnected")
            if c == b"\n":
                break
            buf += c
    finally:
        sock.settimeout(None)
    return buf.decode("utf-8")


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def display_scene(epd, png_bytes: bytes):
    """Decode PNG bytes, rotate if needed, and display on e-paper."""
    img = Image.open(BytesIO(png_bytes))
    log.info("Image from server: %s %s", img.size, img.mode)

    if ROTATE:
        img = img.rotate(ROTATE, expand=True)
        log.info("After rotate: %s %s", img.size, img.mode)

    if img.mode != "1":
        img = img.convert("1")
        log.info("Converted to mode: %s", img.mode)

    if img.size != (EPD_W, EPD_H):
        log.warning("Resizing from %s to %dx%d", img.size, EPD_W, EPD_H)
        img = img.resize((EPD_W, EPD_H), Image.NEAREST)

    log.info("Displaying %s on e-paper...", img.size)
    epd.init()
    epd.display(epd.getbuffer(img))
    epd.sleep()
    log.info("Display done")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def _wait_for_key_evdev(dev) -> int:
    """Read A/B from Digispark via evdev. Returns 0 or 1, or -1 if device lost."""
    from evdev import ecodes
    while True:
        try:
            event = dev.read_one()
            if event and event.type == ecodes.EV_KEY and event.value == 1:
                if event.code == KEY_A:
                    return 0
                elif event.code == KEY_B:
                    return 1
            time.sleep(0.05)
        except OSError:
            log.warning("Digispark device lost")
            return -1


def _wait_for_key_stdin() -> int:
    """Read a/b from terminal/SSH input. Returns 0 or 1."""
    import select
    sys.stdout.write("\r[A] option 1  [B] option 2  > ")
    sys.stdout.flush()
    while True:
        r, _, _ = select.select([sys.stdin], [], [], 0.2)
        if r:
            ch = sys.stdin.read(1).lower()
            if ch == "a":
                return 0
            elif ch == "b":
                return 1
            # skip other chars (newline, etc.) and try again


def run(host: str, port: int, use_stdin: bool = False):
    # Find Digispark input (optional)
    dp_path = find_digispark() if not use_stdin else None
    dev = None
    if dp_path:
        from evdev import InputDevice
        dev = InputDevice(dp_path)
        log.info("Digispark found at %s", dp_path)
    else:
        log.warning("No Digispark — will read A/B from terminal (SSH) input")

    # Initialize e-paper
    log.info("Initializing e-paper display...")
    epd = epd_driver.EPD()
    epd.init()
    epd.Clear()
    log.info("E-paper ready")

    if dev is None and not use_stdin:
        log.warning("No input device — run with --stdin to use terminal input")

    while True:
        try:
            sock = connect(host, port)
            send_json(sock, {
                "type": "hello",
                "width": RENDER_W,
                "height": RENDER_H,
            })

            while True:
                line = recv_line(sock)
                msg = json.loads(line)
                log.debug("Server msg: player=%s status=%s",
                          msg.get("player_id"), msg.get("status"))

                # Update e-paper
                png_b64 = msg.get("image_b64", "")
                if png_b64:
                    png_bytes = base64.b64decode(png_b64)
                    display_scene(epd, png_bytes)

                choice_count = msg.get("choice_count", 2)
                is_encounter = msg.get("encounter", False)

                if is_encounter:
                    # Locked in encounter — server will push again when resolved
                    log.info("Encounter in progress, waiting for server resolution")
                    continue
                elif choice_count <= 1:
                    # Auto-select the only option (or restart on game over)
                    time.sleep(3)
                    index = 0
                elif dev:
                    index = _wait_for_key_evdev(dev)
                    if index == -1:
                        # Device lost — try to re-detect
                        dev = None
                        dp_path = find_digispark()
                        if dp_path:
                            from evdev import InputDevice
                            dev = InputDevice(dp_path)
                            log.info("Digispark re-detected at %s", dp_path)
                            index = _wait_for_key_evdev(dev)
                            if index == -1:
                                dev = None
                        if dev is None:
                            log.warning("Digispark gone — falling back to terminal input")
                            index = _wait_for_key_stdin()
                else:
                    index = _wait_for_key_stdin()

                send_json(sock, {"type": "choice", "index": index})
                log.info("Choice: %s → %d", "A" if index == 0 else "B", index)

        except (ConnectionError, OSError) as exc:
            log.warning("Connection lost: %s. Retrying in 3s...", exc)
            time.sleep(3)
            continue
        except KeyboardInterrupt:
            break
        except Exception as exc:
            log.error("Unexpected error: %s", exc)
            time.sleep(3)
            continue

    # Cleanup
    log.info("Shutting down...")
    epd.sleep()
    if dev:
        dev.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pi Zero e-paper client")
    parser.add_argument("host", help="Server IP address")
    parser.add_argument("port", nargs="?", type=int, default=9999)
    parser.add_argument("--stdin", action="store_true",
                        help="Read A/B from terminal (use when no Digispark)")
    args = parser.parse_args()
    run(args.host, args.port, use_stdin=args.stdin)
