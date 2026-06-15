"""
main.py — Entry point for the MultiMarkovPlay prototype.

Modes:
  python main.py              → local mode (Tkinter player windows)
  python main.py --server     → server mode (TCP for Pi Zero clients)
  python main.py --server --port 8888
"""

import argparse
import logging
import tkinter as tk

from control_window import ControlWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
)


def main():
    parser = argparse.ArgumentParser(
        description="MultiMarkovPlay — multiplayer Markov narrative"
    )
    parser.add_argument("--server", action="store_true",
                        help="Start TCP server for Pi Zero terminals")
    parser.add_argument("--port", type=int, default=9999,
                        help="TCP port (default: 9999)")
    args = parser.parse_args()

    root = tk.Tk()
    root.withdraw()

    if not args.server:
        from tkinter import messagebox
        result = messagebox.askyesnocancel(
            title="MultiMarkovPlay — Mode",
            message="Start in server mode (for Pi Zero terminals)?",
            detail="Yes  = TCP server mode (Pi Zeros connect to this PC)\n"
                   "No   = Local mode (Tkinter player windows on this PC)\n"
                   "Cancel = Exit",
        )
        if result is None:
            root.destroy()
            sys.exit(0)
        mode = "server" if result else "local"
    else:
        mode = "server"

    root.deiconify()
    root.lift()
    root.focus_force()
    ctrl = ControlWindow(root)

    if mode == "server":
        from server import GameServer
        server = GameServer(ctrl.engine, root, port=args.port)
        server.start()
        print(f"[Server mode] Listening on port {args.port}")
        print(f"[Server mode] Pi Zeros connect to this PC's IP on port {args.port}")
    else:
        print("[Local mode] Use the control panel to spawn player windows")

    root.mainloop()


if __name__ == "__main__":
    main()
