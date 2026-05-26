"""
control_window.py — Central control panel.
Left: Markov chain settings + node overview list.
Right: Full shared graph (all players, all nodes).
"""

import tkinter as tk
from tkinter import ttk, font as tkfont, messagebox
from pathlib import Path

from engine import StoryEngine, STATUS_ACTIVE, STATUS_COLLISION, STATUS_GAME_OVER
from player_window import PlayerWindow
from graph_canvas import GraphCanvas

# Palette
BG    = "#0d0d1a"
BG2   = "#111122"
BG3   = "#151528"
FG    = "#c8c8e8"
FG_DIM= "#445566"
ACC   = "#4a9eff"
ACC2  = "#ff6b35"
ACC3  = "#44cc88"
BTN   = "#1a1a3a"
BTN_A = "#2a2aaa"
SEP   = "#1a1a3a"

STATUS_COLORS = {
    STATUS_ACTIVE:    "#44cc88",
    STATUS_COLLISION: "#ff6b35",
    STATUS_GAME_OVER: "#ff3366",
    "offline":        "#222244",
}


def _btn(parent, text, cmd, bg=BTN, fg=FG, **kw):
    return tk.Button(
        parent, text=text, command=cmd,
        bg=bg, fg=fg, activebackground=BTN_A, activeforeground=FG,
        relief="flat", bd=0, padx=10, pady=6,
        font=("Courier", 9), cursor="hand2", **kw,
    )


class ControlWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("MultiMarkovPlay — Control")
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)
        self.root.configure(bg=BG)

        base = Path(__file__).parent
        self.engine = StoryEngine(training_dir=base / "training_texts")
        self.engine.on_graph_change = self._on_graph_change

        world_file = base / "data" / "world" / "example_world.json"
        if world_file.exists():
            self.engine.load_world(world_file)

        self.player_windows: dict[str, PlayerWindow] = {}
        self.next_num = 1

        self._build_ui()
        self._refresh_player_list()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.root.columnconfigure(0, weight=0, minsize=280)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        self._build_left_panel()
        self._build_right_panel()

    # --- Left panel ---

    def _build_left_panel(self):
        left = tk.Frame(self.root, bg=BG2, padx=14, pady=12)
        left.grid(row=0, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)

        # Title
        tk.Label(left, text="MultiMarkovPlay", bg=BG2, fg=ACC,
                 font=("Courier", 13, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(left, text="control panel", bg=BG2, fg=FG_DIM,
                 font=("Courier", 8)).grid(row=1, column=0, sticky="w", pady=(0, 10))

        tk.Frame(left, bg=SEP, height=1).grid(row=2, column=0, sticky="ew", pady=6)

        # Spawn controls
        tk.Label(left, text="spawn players", bg=BG2, fg=ACC,
                 font=("Courier", 10, "bold")).grid(row=3, column=0, sticky="w")

        spawn_f = tk.Frame(left, bg=BG2)
        spawn_f.grid(row=4, column=0, sticky="ew", pady=4)
        spawn_f.columnconfigure(1, weight=1)

        tk.Label(spawn_f, text="count:", bg=BG2, fg=FG,
                 font=("Courier", 9)).grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.var_count = tk.IntVar(value=3)
        tk.Scale(spawn_f, from_=1, to=20, orient="horizontal",
                 variable=self.var_count, bg=BG2, fg=FG, troughcolor=SEP,
                 highlightthickness=0, showvalue=True, length=120,
                 font=("Courier", 8), activebackground=ACC,
                 ).grid(row=0, column=1, sticky="w")

        btn_row = tk.Frame(left, bg=BG2)
        btn_row.grid(row=5, column=0, sticky="ew", pady=4)
        _btn(btn_row, "Spawn",     self._spawn_players, bg="#0d2a0d", fg=ACC3).pack(side="left", padx=(0, 4))
        _btn(btn_row, "Close All", self._close_all,     bg="#2a0d0d", fg=ACC2).pack(side="left", padx=4)
        _btn(btn_row, "Reset All", self._reset_all).pack(side="left", padx=4)

        tk.Frame(left, bg=SEP, height=1).grid(row=6, column=0, sticky="ew", pady=8)

        # Markov chain settings
        tk.Label(left, text="markov chain", bg=BG2, fg=ACC,
                 font=("Courier", 10, "bold")).grid(row=7, column=0, sticky="w")

        mc = tk.Frame(left, bg=BG2)
        mc.grid(row=8, column=0, sticky="ew", pady=4)
        mc.columnconfigure(1, weight=1)

        def _sl_row(parent, row, label, var, lo, hi, cb):
            tk.Label(parent, text=label, bg=BG2, fg=FG,
                     font=("Courier", 9)).grid(row=row, column=0, sticky="w", pady=2, padx=(0, 6))
            tk.Scale(parent, from_=lo, to=hi, orient="horizontal",
                     variable=var, bg=BG2, fg=FG, troughcolor=SEP,
                     highlightthickness=0, showvalue=True, length=130,
                     font=("Courier", 8), activebackground=ACC,
                     command=cb,
                     ).grid(row=row, column=1, sticky="ew", pady=2)

        self.var_order     = tk.IntVar(value=self.engine.markov.order)
        self.var_textlen   = tk.IntVar(value=self.engine.text_len)
        self.var_choicelen = tk.IntVar(value=self.engine.choice_len)
        self.var_temp      = tk.DoubleVar(value=self.engine.markov.temperature)

        _sl_row(mc, 0, "order:",        self.var_order,     1, 5,   lambda v: None)
        _sl_row(mc, 1, "scene words:",  self.var_textlen,   10, 100, self._on_textlen)
        _sl_row(mc, 2, "choice words:", self.var_choicelen,  2, 12,  self._on_choicelen)

        # Temperature slider with custom resolution
        tk.Label(mc, text="temperature:", bg=BG2, fg=FG,
                 font=("Courier", 9)).grid(row=3, column=0, sticky="w", pady=2, padx=(0, 6))
        tk.Scale(mc, from_=0.3, to=2.5, resolution=0.1, orient="horizontal",
                 variable=self.var_temp, bg=BG2, fg=FG, troughcolor=SEP,
                 highlightthickness=0, showvalue=True, length=130,
                 font=("Courier", 8), activebackground=ACC,
                 command=self._on_temp,
                 ).grid(row=3, column=1, sticky="ew", pady=2)
        tk.Label(mc, text="← precise    chaotic →", bg=BG2, fg=FG_DIM,
                 font=("Courier", 7)).grid(row=4, column=1, sticky="w")

        retrain_row = tk.Frame(left, bg=BG2)
        retrain_row.grid(row=9, column=0, sticky="ew", pady=4)
        _btn(retrain_row, "Retrain", self._retrain).pack(side="left")
        _btn(retrain_row, "Reset Graph", self._reset_graph,
             bg="#2a1a0d", fg="#ffaa44").pack(side="left", padx=6)
        self.lbl_train = tk.Label(retrain_row, text="", bg=BG2, fg=ACC3,
                                   font=("Courier", 8))
        self.lbl_train.pack(side="left", padx=6)

        tk.Frame(left, bg=SEP, height=1).grid(row=10, column=0, sticky="ew", pady=8)

        # Legend
        tk.Label(left, text="legend", bg=BG2, fg=ACC,
                 font=("Courier", 10, "bold")).grid(row=11, column=0, sticky="w")

        legend_items = [
            ("●", "#4a9eff", "your position"),
            ("●", "#ff6b35", "other player"),
            ("●", "#44cc88", "expanded node"),
            ("●", "#1a1a3a", "unexplored"),
            ("—", "#2a4a6a", "normal link"),
            ("—", "#6a2a4a", "cross-link"),
        ]
        leg = tk.Frame(left, bg=BG2)
        leg.grid(row=12, column=0, sticky="ew", pady=4)
        for i, (sym, color, desc) in enumerate(legend_items):
            tk.Label(leg, text=sym, bg=BG2, fg=color,
                     font=("Courier", 10)).grid(row=i, column=0, sticky="w")
            tk.Label(leg, text=desc, bg=BG2, fg=FG_DIM,
                     font=("Courier", 8)).grid(row=i, column=1, sticky="w", padx=6)

        tk.Frame(left, bg=SEP, height=1).grid(row=13, column=0, sticky="ew", pady=8)

        # Player list
        tk.Label(left, text="players", bg=BG2, fg=ACC,
                 font=("Courier", 10, "bold")).grid(row=14, column=0, sticky="w")

        list_frame = tk.Frame(left, bg=BG2)
        list_frame.grid(row=15, column=0, sticky="nsew", pady=4)
        list_frame.columnconfigure(0, weight=1)
        left.rowconfigure(15, weight=1)

        self.player_list_inner = tk.Frame(list_frame, bg=BG2)
        self.player_list_inner.pack(fill="both", expand=True)

    # --- Right panel (full graph) ---

    def _build_right_panel(self):
        right = tk.Frame(self.root, bg=BG3)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        header = tk.Frame(right, bg=BG3, pady=6, padx=12)
        header.grid(row=0, column=0, sticky="ew")
        tk.Label(header, text="shared story graph", bg=BG3, fg=FG_DIM,
                 font=("Courier", 9)).pack(side="left")

        self.graph_cv = GraphCanvas(
            right, self.engine,
            width=700, height=650,
            highlight_player=None,
            show_labels=True,
            bg="#080810",
        )
        self.graph_cv.grid(row=1, column=0, sticky="nsew")

        # Make graph canvas resize with window
        right.bind("<Configure>", self._on_right_resize)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_right_resize(self, event):
        # Rough resize — just refresh layout
        pass

    def _spawn_players(self):
        count = self.var_count.get()
        existing = len(self.player_windows)
        to_spawn = min(count, 20 - existing)
        if to_spawn <= 0:
            messagebox.showinfo("Limit", "Already at 20 players.")
            return
        for _ in range(to_spawn):
            pid = f"P{self.next_num:02d}"
            self.next_num += 1
            self.engine.spawn_player(pid)
            pw = PlayerWindow(
                self.root, pid, self.engine,
                on_event_cb=self._on_player_event,
            )
            self.player_windows[pid] = pw
        self._tile_windows()
        self._refresh_player_list()
        self._notify_all_graph_changed()

    def _tile_windows(self):
        from player_window import SCR_W, SCR_H
        wins = list(self.player_windows.values())
        cols = 3
        w, h = SCR_W, SCR_H
        ctrl_x = self.root.winfo_x()
        ctrl_w = self.root.winfo_width()
        ox = ctrl_x + ctrl_w + 10
        oy = 20
        for i, pw in enumerate(wins):
            x = ox + (i % cols) * (w + 6)
            y = oy + (i // cols) * (h + 30)
            pw.win.geometry(f"{w}x{h}+{x}+{y}")

    def _close_all(self):
        for pw in list(self.player_windows.values()):
            pw.destroy()
        self.player_windows.clear()
        self._refresh_player_list()

    def _reset_all(self):
        for pw in list(self.player_windows.values()):
            self.engine.reset_player(pw.player_id)
            pw._refresh_from_state()
        self._refresh_player_list()

    def _reset_graph(self):
        if not messagebox.askyesno("Reset Graph",
                                    "Clear the entire story graph and restart all players?"):
            return
        self.engine.reset_graph()
        for pw in list(self.player_windows.values()):
            self.engine.spawn_player(pw.player_id)
            pw._refresh_from_state()
        self._refresh_player_list()
        self.graph_cv.refresh(animate=True)

    def _retrain(self):
        order = self.var_order.get()
        n = self.engine.retrain(order)
        self.lbl_train.configure(text=f"trained {n} file(s)")
        self.root.after(3000, lambda: self.lbl_train.configure(text=""))

    def _on_textlen(self, val):
        self.engine.set_text_len(int(float(val)))

    def _on_choicelen(self, val):
        self.engine.set_choice_len(int(float(val)))

    def _on_temp(self, val):
        self.engine.set_temperature(float(val))

    def _on_player_event(self, refresh_only: bool = True):
        if not refresh_only:
            self.player_windows = {
                pid: pw for pid, pw in self.player_windows.items()
                if pw.win.winfo_exists()
            }
        self._refresh_player_list()
        self.graph_cv.refresh(animate=False)

    def _on_graph_change(self, skip_players=None):
        """Engine callback: graph structure changed."""
        self.graph_cv.refresh(animate=True)
        self._notify_all_graph_changed(skip_players=skip_players)

    def _notify_all_graph_changed(self, skip_players=None):
        skip = skip_players or set()
        for pid, pw in self.player_windows.items():
            if pid in skip:
                continue
            if pw.win.winfo_exists():
                pw.notify_graph_changed()

    # ------------------------------------------------------------------
    # Player list
    # ------------------------------------------------------------------

    def _refresh_player_list(self):
        for w in self.player_list_inner.winfo_children():
            w.destroy()

        states = self.engine.get_all_states()
        if not states:
            tk.Label(self.player_list_inner, text="no active players",
                     bg=BG2, fg=FG_DIM, font=("Courier", 8)).pack(anchor="w")
            return

        for state in states:
            color = STATUS_COLORS.get(state.status, STATUS_COLORS["offline"])
            row = tk.Frame(self.player_list_inner, bg=BG2)
            row.pack(fill="x", pady=1)

            tk.Label(row, text="●", bg=BG2, fg=color,
                     font=("Courier", 9)).pack(side="left")
            tk.Label(row, text=f"{state.player_id:<6}", bg=BG2, fg=FG,
                     font=("Courier", 9)).pack(side="left", padx=4)
            tk.Label(row, text=state.current_node, bg=BG2, fg=FG_DIM,
                     font=("Courier", 8)).pack(side="left")
            tk.Label(row, text=f"  ({len(state.history)} steps)", bg=BG2, fg=FG_DIM,
                     font=("Courier", 7)).pack(side="left")
