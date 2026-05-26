"""
main.py — Entry point for the MultiMarkovPlay prototype.
Run: python main.py
"""

import tkinter as tk
from control_window import ControlWindow


def main():
    root = tk.Tk()
    root.lift()
    root.focus_force()
    ControlWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
