"""
world_log.py — Session log of world/node changes, player actions, and LLM edits.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import scrolledtext
from datetime import datetime
from typing import Callable

# Shared palette (matches control_window)
BG   = "#1a1a18"
BG2  = "#222220"
FG   = "#c8c8bc"
FG_DIM = "#6a6a60"
ACC  = "#a0a090"


def diff_node_dicts(before: list[dict], after: list[dict]) -> list[str]:
    """Human-readable diff lines for LLM/sanity node edits."""
    lines: list[str] = []
    after_by_id = {n["id"]: n for n in after}
    for b in before:
        nid = b.get("id", "?")
        a = after_by_id.get(nid)
        if a is None:
            lines.append(f"  [{nid}] removed from batch")
            continue
        if (b.get("text") or b.get("description")) != (a.get("text") or a.get("description")):
            old_t = (b.get("text") or b.get("description") or "")[:300]
            new_t = (a.get("text") or a.get("description") or "")[:300]
            lines.append(f"  [{nid}] text changed:")
            lines.append(f"    − {old_t}")
            lines.append(f"    + {new_t}")
        if b.get("items") != a.get("items"):
            lines.append(f"  [{nid}] items: {b.get('items')} → {a.get('items')}")
        old_exits = {e.get("to"): e.get("label") for e in b.get("exits", [])}
        new_exits = {e.get("to"): e.get("label") for e in a.get("exits", [])}
        for dest, lbl in new_exits.items():
            if old_exits.get(dest) != lbl:
                lines.append(f"  [{nid}] exit → {dest}: {old_exits.get(dest)!r} → {lbl!r}")
    for a in after:
        if a.get("id") not in {b.get("id") for b in before}:
            lines.append(f"  [{a.get('id')}] NEW node: {a.get('title', '')}")
    return lines


class WorldLog:
    """Append-only session log with optional UI window."""

    def __init__(self):
        self._lines: list[str] = []
        self._listeners: list[Callable[[str], None]] = []
        self._window: LogWindow | None = None

    def subscribe(self, cb: Callable[[str], None]):
        self._listeners.append(cb)

    def _stamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _emit(self, line: str):
        """Append one line to the buffer and notify UI listeners (once)."""
        self._lines.append(line)
        for cb in self._listeners:
            try:
                cb(line)
            except Exception:
                pass

    def add(self, category: str, message: str):
        self._emit(f"[{self._stamp()}] {category}: {message}")

    def add_block(self, category: str, header: str, body_lines: list[str]):
        self.add(category, header)
        for bl in body_lines:
            self._emit(f"           {bl}")

    def text(self) -> str:
        return "\n".join(self._lines)

    def clear(self):
        self._lines.clear()
        if self._window and self._window.win.winfo_exists():
            self._window.clear()

    def open_window(self, parent):
        if self._window is None or not self._window.win.winfo_exists():
            self._window = LogWindow(parent, self)
        else:
            self._window.win.lift()


class LogWindow:
    def __init__(self, parent, world_log: WorldLog):
        self.world_log = world_log
        self.win = tk.Toplevel(parent)
        self.win.title("World Log")
        self.win.geometry("720x480")
        self.win.configure(bg=BG)
        self.win.minsize(400, 200)

        bar = tk.Frame(self.win, bg=BG2)
        bar.pack(fill="x", padx=8, pady=6)
        tk.Label(bar, text="world log", bg=BG2, fg=ACC,
                 font=("Courier", 11, "bold")).pack(side="left")
        tk.Button(bar, text="Clear", command=self._clear,
                  bg=BG2, fg=FG, font=("Courier", 9), relief="flat",
                  ).pack(side="right", padx=4)
        tk.Button(bar, text="Copy all", command=self._copy,
                  bg=BG2, fg=FG, font=("Courier", 9), relief="flat",
                  ).pack(side="right")

        self.text = scrolledtext.ScrolledText(
            self.win, bg=BG2, fg=FG, font=("Courier", 9),
            wrap="word", state="disabled", relief="flat",
        )
        self.text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        for line in world_log._lines:
            self.append(line, scroll=False)
        self.text.see("end")

        world_log.subscribe(self._on_external)

    def _on_external(self, line: str):
        if self.win.winfo_exists():
            self.append(line)

    def append(self, line: str, scroll: bool = True):
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n")
        self.text.configure(state="disabled")
        if scroll:
            self.text.see("end")

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def _clear(self):
        self.world_log.clear()

    def _copy(self):
        self.win.clipboard_clear()
        self.win.clipboard_append(self.world_log.text())
