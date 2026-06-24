"""
pi_client.py — runs on each Pi Zero with a 7.5" e-paper display + Digispark.
Connects to the main PC server, displays full-screen rendered scenes, and
sends A/B choices from the Digispark back to the server.

Usage:
  python pi_client.py <server_ip> [port]

Requires:
  - Pillow (PIL)
  - evdev
  - waveshare_epd (Waveshare 7.5" V2) OR betterepd7in5 (recommended, much faster)

Install faster driver (Pi Zero 2 W, Python 3.12+):
  pip install betterepd7in5 numpy
"""

from __future__ import annotations

import base64
import json
import logging
import socket
import sys
import time
from io import BytesIO
from typing import Literal

from PIL import Image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# E-Paper — Waveshare fallback (always importable if waveshare installed)
# ---------------------------------------------------------------------------
# from waveshare_epd import epd7in5 as epd_driver      # V1 (640x384)
from waveshare_epd import epd7in5_V2 as epd_driver   # V2 (800x480)
# from waveshare_epd import epd7in5_HD as epd_driver   # HD (880x528)

EPD_W = epd_driver.EPD_WIDTH   # 800
EPD_H = epd_driver.EPD_HEIGHT  # 480

RENDER_W = 480
RENDER_H = 800

# Portrait → landscape; use 270 when the panel is hung upside-down.
ROTATE = 270

DisplayDriver = Literal["auto", "betterepd", "waveshare"]
DisplayMode = Literal["grayscale", "bilevel", "fast"]

# ---------------------------------------------------------------------------
# Digispark evdev discovery
# ---------------------------------------------------------------------------

KEY_A = 30
KEY_B = 48
DIGISTUMP_VID = 0x16C0
DIGIKEY_PID = 0x27DB


def find_digispark() -> str | None:
    """Find the input event device for the Digispark keyboard."""
    from evdev import InputDevice, list_devices
    for path in list_devices():
        try:
            dev = InputDevice(path)
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


def recv_line(sock: socket.socket, timeout: float = 120.0) -> str:
    buf = bytearray()
    sock.settimeout(timeout)
    try:
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                raise ConnectionError("Server disconnected")
            nl = chunk.find(b"\n")
            if nl >= 0:
                buf.extend(chunk[:nl])
                break
            buf.extend(chunk)
    finally:
        sock.settimeout(None)
    return buf.decode("utf-8")


# ---------------------------------------------------------------------------
# Display backends
# ---------------------------------------------------------------------------

def _resolve_driver(name: DisplayDriver):
    if name == "betterepd" or name == "auto":
        try:
            import betterepd7in5
            epd = betterepd7in5.EPD(betterepd7in5.RaspberryPi())
            log.info("Using betterepd7in5 driver")
            return "betterepd", epd
        except ImportError:
            if name == "betterepd":
                raise SystemExit(
                    "betterepd7in5 not installed — pip install betterepd7in5 numpy"
                )
    epd = epd_driver.EPD()
    log.info("Using Waveshare epd7in5_V2 driver")
    return "waveshare", epd


def _prepare_frame(png_bytes: bytes) -> Image.Image:
    img = Image.open(BytesIO(png_bytes))
    if ROTATE:
        img = img.rotate(ROTATE, expand=True)
    if img.mode != "L":
        img = img.convert("L")
    if img.size != (EPD_W, EPD_H):
        log.warning("Resizing from %s to %dx%d", img.size, EPD_W, EPD_H)
        img = img.resize((EPD_W, EPD_H), Image.Resampling.LANCZOS)
    return img


def _init_display(driver_kind: str, epd) -> None:
    if driver_kind == "betterepd":
        epd.clear()
    else:
        epd.init()
        epd.Clear()


def _shutdown_display(driver_kind: str, epd) -> None:
    if driver_kind == "betterepd":
        epd.sleep()
    else:
        epd.sleep()


def display_scene(
    driver_kind: str,
    epd,
    png_bytes: bytes,
    mode: DisplayMode,
):
    """Decode PNG bytes, rotate if needed, and display on e-paper."""
    t0 = time.perf_counter()
    img = _prepare_frame(png_bytes)
    log.info("Frame ready: %s %s (prep %.1fs)", img.size, img.mode, time.perf_counter() - t0)

    lo, hi = img.getextrema()
    label = f"{driver_kind}/{mode}"
    log.info("Pixel range %d..%d — refresh starting (%s)", lo, hi, label)

    t1 = time.perf_counter()
    if driver_kind == "betterepd":
        if mode == "grayscale":
            ctx = epd.display_grayscale()
        elif mode == "fast":
            ctx = epd.display_bilevel_fast_refresh()
        else:
            ctx = epd.display_bilevel_full_refresh()
        with ctx as disp:
            disp(img)
    elif mode == "grayscale":
        epd.init_4Gray()
        epd.display_4Gray(epd.getbuffer_4Gray(img))
        epd.sleep()
    else:
        epd.init()
        epd.display(epd.getbuffer(img))
        epd.sleep()

    log.info("Display done (refresh %.1fs)", time.perf_counter() - t1)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def _wait_for_key_evdev(dev) -> int:
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


def run(
    host: str,
    port: int,
    use_stdin: bool = False,
    device_id: str | None = None,
    driver: DisplayDriver = "auto",
    mode: DisplayMode = "fast",
):
    dp_path = find_digispark() if not use_stdin else None
    dev = None
    if dp_path:
        from evdev import InputDevice
        dev = InputDevice(dp_path)
        log.info("Digispark found at %s", dp_path)
    else:
        log.warning("No Digispark — will read A/B from terminal (SSH) input")

    if device_id is None:
        import socket as _socket
        device_id = _socket.gethostname()

    log.info("Initializing e-paper display...")
    driver_kind, epd = _resolve_driver(driver)
    _init_display(driver_kind, epd)
    log.info("E-paper ready (driver=%s mode=%s)", driver_kind, mode)

    if dev is None and not use_stdin:
        log.warning("No input device — run with --stdin to use terminal input")

    while True:
        try:
            sock = connect(host, port)
            send_json(sock, {
                "type": "hello",
                "device_id": device_id,
                "width": RENDER_W,
                "height": RENDER_H,
            })

            while True:
                log.info("Waiting for server state...")
                t0 = time.perf_counter()
                line = recv_line(sock)
                log.info("Received %d wire bytes in %.1fs",
                         len(line), time.perf_counter() - t0)
                t1 = time.perf_counter()
                msg = json.loads(line)
                log.info("Parsed JSON in %.1fs", time.perf_counter() - t1)
                log.info("Server msg: player=%s status=%s image=%d bytes",
                         msg.get("player_id"), msg.get("status"),
                         len(msg.get("image_b64", "")))

                png_b64 = msg.get("image_b64", "")
                if png_b64:
                    t2 = time.perf_counter()
                    png_bytes = base64.b64decode(png_b64)
                    log.info("Decoded PNG %d bytes in %.1fs",
                             len(png_bytes), time.perf_counter() - t2)
                    display_scene(driver_kind, epd, png_bytes, mode)
                else:
                    log.warning("Server message had no image_b64")

                choice_count = msg.get("choice_count", 2)
                is_encounter = msg.get("encounter", False)

                if is_encounter:
                    log.info("Encounter in progress, waiting for server resolution")
                    continue
                elif choice_count <= 1:
                    time.sleep(3)
                    index = 0
                elif dev:
                    index = _wait_for_key_evdev(dev)
                    if index == -1:
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

    log.info("Shutting down...")
    _shutdown_display(driver_kind, epd)
    if dev:
        dev.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pi Zero e-paper client")
    parser.add_argument("host", help="Server IP address")
    parser.add_argument("port", nargs="?", type=int, default=9999)
    parser.add_argument("--device-id", default=None,
                        help="Wall station ID (default: hostname)")
    parser.add_argument("--stdin", action="store_true",
                        help="Read A/B from terminal (use when no Digispark)")
    parser.add_argument("--driver", choices=("auto", "betterepd", "waveshare"),
                        default="auto",
                        help="Display driver (default: auto → betterepd if installed)")
    mode_grp = parser.add_mutually_exclusive_group()
    mode_grp.add_argument("--grayscale", action="store_const", const="grayscale",
                          dest="mode", help="4-gray refresh (~3s with betterepd7in5)")
    mode_grp.add_argument("--bilevel", action="store_const", const="bilevel",
                          dest="mode", help="Full black/white refresh")
    mode_grp.add_argument("--fast", action="store_const", const="fast",
                          dest="mode",
                          help="Fast bilevel refresh (~2s, default with betterepd)")
    parser.set_defaults(mode="fast")
    args = parser.parse_args()
    run(args.host, args.port, use_stdin=args.stdin, device_id=args.device_id,
        driver=args.driver, mode=args.mode)
