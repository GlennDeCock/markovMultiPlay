"""
control_window.py — Central control panel.
Left: Markov chain settings + node overview list.
Right: Full shared graph (all players, all nodes).
"""

import tkinter as tk
from tkinter import ttk, font as tkfont, messagebox
from pathlib import Path

from engine import StoryEngine, STATUS_ACTIVE, STATUS_ENCOUNTER, STATUS_GAME_OVER
from player_window import PlayerWindow
from graph_canvas import GraphCanvas
from world_text_parser import convert_file as _parse_world_txt

# Palette — E-Ink paper aesthetic (matches player_window)
BG    = "#0a0a08"   # outer bezel / root window
BG2   = "#dcdcd0"   # paper — main left-panel background
BG3   = "#d0d0c4"   # paper2 — right panel / sub-panel background
FG    = "#0f0f0c"   # ink
FG_DIM= "#8a8a80"   # dim ink
ACC   = "#0f0f0c"   # ink (section headers — no longer blue)
ACC2  = "#b84a1a"   # rust — destructive actions
ACC3  = "#1a6a30"   # dark green — positive / success
BTN   = "#dcdcd0"   # paper (button bg)
BTN_A = "#c8c8bc"   # paper hover
SEP   = "#aaaaA0"   # ink rule

STATUS_COLORS = {
    STATUS_ACTIVE:    "#1a6a30",   # dark green on paper
    STATUS_ENCOUNTER: "#b84a1a",   # rust on paper
    STATUS_GAME_OVER: "#aa1a2a",   # dark red on paper
    "offline":        "#8a8a80",   # dim ink
}


def _btn(parent, text, cmd, bg=BTN, fg=FG, **kw):
    return tk.Button(
        parent, text=text, command=cmd,
        bg=bg, fg=fg, activebackground=BTN_A, activeforeground=FG,
        relief="solid", bd=1, padx=8, pady=4,
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
        self.engine.on_graph_change    = self._on_graph_change
        self.engine.on_encounter_start = self._on_encounter_start

        self.player_windows: dict[str, PlayerWindow] = {}
        self._selected_node_id: str | None = None
        self._encounter_timers: dict[str, str] = {}  # node_id → after-id

        self._build_ui()
        self._refresh_player_list()

        # Load world graph after UI is built (on_graph_change needs graph_cv)
        world_candidates = [
            base / "data" / "world" / "example_world.json",
            base / "nodes.json",
        ]
        self._world_json = world_candidates[0]
        self._world_txt  = base / "data" / "world" / "example_world.txt"
        for p in world_candidates:
            if p.exists():
                self.engine.load_world(p)
                break

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
        _btn(btn_row, "Spawn",     self._spawn_players, fg=ACC3).pack(side="left", padx=(0, 4))
        _btn(btn_row, "Close All", self._close_all,     fg=ACC2).pack(side="left", padx=4)
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
        self.var_driftrate = tk.IntVar(value=1)

        _sl_row(mc, 0, "order:",        self.var_order,     1, 5,   lambda v: None)
        _sl_row(mc, 1, "text words:",   self.var_textlen,   10, 100, self._on_textlen)
        _sl_row(mc, 2, "choice words:", self.var_choicelen,  2, 12,  self._on_choicelen)
        _sl_row(mc, 3, "drift rate:",   self.var_driftrate,  1, 10,  self._on_driftrate)

        # Temperature slider with custom resolution
        tk.Label(mc, text="temperature:", bg=BG2, fg=FG,
                 font=("Courier", 9)).grid(row=4, column=0, sticky="w", pady=2, padx=(0, 6))
        tk.Scale(mc, from_=0.3, to=2.5, resolution=0.1, orient="horizontal",
                 variable=self.var_temp, bg=BG2, fg=FG, troughcolor=SEP,
                 highlightthickness=0, showvalue=True, length=130,
                 font=("Courier", 8), activebackground=ACC,
                 command=self._on_temp,
                 ).grid(row=4, column=1, sticky="ew", pady=2)
        tk.Label(mc, text="← precise    chaotic →", bg=BG2, fg=FG_DIM,
                 font=("Courier", 7)).grid(row=5, column=1, sticky="w")

        retrain_row = tk.Frame(left, bg=BG2)
        retrain_row.grid(row=9, column=0, sticky="ew", pady=4)
        _btn(retrain_row, "Retrain", self._retrain).pack(side="left")
        _btn(retrain_row, "Reset Graph", self._reset_graph,
             fg="#cc7700").pack(side="left", padx=6)
        _btn(retrain_row, "Rebuild World", self._rebuild_world,
             fg="#0055aa").pack(side="left", padx=6)
        _btn(retrain_row, "Load / Generate from Text…", self._load_from_text_file,
             fg=ACC3).pack(side="left", padx=6)
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

        # Node inspector
        tk.Label(left, text="node inspector", bg=BG2, fg=ACC,
                 font=("Courier", 10, "bold")).grid(row=14, column=0, sticky="w")

        insp = tk.Frame(left, bg=BG2)
        insp.grid(row=15, column=0, sticky="nsew", pady=4)
        insp.columnconfigure(0, weight=1)
        left.rowconfigure(15, weight=1)

        self._insp_text = tk.Text(
            insp, bg=BG3, fg=FG, font=("Courier", 7),
            relief="flat", bd=0, state="disabled",
            highlightthickness=0, wrap="word", padx=6, pady=6,
        )
        self._insp_text.pack(fill="both", expand=True)

        insp_btns = tk.Frame(left, bg=BG2)
        insp_btns.grid(row=16, column=0, sticky="ew", pady=2)
        _btn(insp_btns, "Reset Drift", self._reset_selected_drift,
             fg="#cc7700").pack(side="left")

        tk.Frame(left, bg=SEP, height=1).grid(row=17, column=0, sticky="ew", pady=8)

        # Player list
        tk.Label(left, text="players", bg=BG2, fg=ACC,
                 font=("Courier", 10, "bold")).grid(row=18, column=0, sticky="w")

        list_frame = tk.Frame(left, bg=BG2)
        list_frame.grid(row=19, column=0, sticky="nsew", pady=4)
        list_frame.columnconfigure(0, weight=1)
        left.rowconfigure(19, weight=1)

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
            state = self.engine.spawn_player()
            pid = state.player_id
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
        if not wins:
            return

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        margin   = 8
        title_h  = 36                       # rough window-title allowance

        w, h = SCR_W, SCR_H
        # How many full-size windows fit per row / column on this screen
        cols = max(1, (screen_w - margin) // (w + margin))
        rows = max(1, (screen_h - margin) // (h + title_h))
        per_screen = cols * rows

        for i, pw in enumerate(wins):
            slot = i % per_screen           # wrap once the grid is full
            cascade = (i // per_screen) * 28  # offset overflowing windows
            col = slot % cols
            row = slot // cols
            x = margin + col * (w + margin) + cascade
            y = margin + row * (h + title_h) + cascade
            # Clamp so the window always stays fully on screen
            x = min(x, max(0, screen_w - w - margin))
            y = min(y, max(0, screen_h - h - title_h))
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

    def _load_from_text_file(self):
        """Open a .txt file picker, then parse + train + load the world in one step."""
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Load World from Text",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialdir=str(Path(__file__).parent / "data" / "worlds"),
        )
        if not path:
            return
        try:
            json_path, n = self.engine.load_from_text(Path(path))
            self._world_txt  = Path(path)
            self._world_json = json_path
            for pw in self.player_windows.values():
                self.engine.spawn_player(pw.player_id)
                pw._refresh_from_state()
            self._refresh_player_list()
            self.graph_cv.refresh(animate=True)
            latent = len(self.engine._latent_nodes)
            mode = "generated" if latent > 0 else "parsed"
            extra = f"  +{latent} latent" if latent > 0 else ""
            self.lbl_train.configure(text=f"{mode} {n} nodes{extra}  trained from source")
            self.root.after(3000, lambda: self.lbl_train.configure(text=""))
        except Exception as exc:
            messagebox.showerror("Load from Text", str(exc))

    def _rebuild_world(self):
        """Re-parse the source .txt, retrain Markov, and reload the world."""
        if not self._world_txt.exists():
            messagebox.showerror(
                "Rebuild World",
                f"Source text not found:\n{self._world_txt}",
            )
            return
        try:
            json_path, n = self.engine.load_from_text(self._world_txt)
            self._world_json = json_path
            for pw in self.player_windows.values():
                self.engine.spawn_player(pw.player_id)
                pw._refresh_from_state()
            self._refresh_player_list()
            self.graph_cv.refresh(animate=True)
            self.lbl_train.configure(text=f"world rebuilt  {n} nodes")
            self.root.after(3000, lambda: self.lbl_train.configure(text=""))
        except Exception as exc:
            messagebox.showerror("Rebuild World", str(exc))

    def _on_textlen(self, val):
        self.engine.set_text_len(int(float(val)))

    def _on_choicelen(self, val):
        self.engine.set_choice_len(int(float(val)))

    def _on_temp(self, val):
        self.engine.set_temperature(float(val))

    def _on_driftrate(self, val):
        self.engine.set_drift_rate(int(float(val)))

    def _on_encounter_start(self, node_id: str):
        """Engine callback: a 15-second timed encounter has started at node_id."""
        # Refresh every player window now so all participants (the arriving
        # witness AND the fled occupants) see the encounter immediately,
        # not only the player who triggered it.
        self.graph_cv.refresh(animate=True)
        self._notify_all_graph_changed()
        self._refresh_player_list()
        if node_id in self._encounter_timers:
            return  # already scheduled
        after_id = self.root.after(
            15_000, lambda nid=node_id: self._resolve_encounter(nid)
        )
        self._encounter_timers[node_id] = after_id

    def _resolve_encounter(self, node_id: str):
        """Timer fired: relocate fled player(s) and restore choices."""
        self._encounter_timers.pop(node_id, None)
        self.engine.resolve_encounter(node_id)
        self._notify_all_graph_changed()

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
        self._refresh_inspector()

    def _select_node(self, node_id: str):
        self._selected_node_id = node_id
        self._refresh_inspector()

    def _refresh_inspector(self):
        node_id = self._selected_node_id
        if not node_id or not self.engine.world:
            return
        node = self.engine.world.nodes.get(node_id)
        if not node:
            return
        lines = [
            f"node:    {node.id}",
            f"title:   {node.title}",
            f"drift:   {node.drift:.0f} visits",
            "",
            "── original ──",
            node.base_text,
            "",
            "── current ──",
            node.current_text,
        ]
        if node.traces:
            lines += ["", "── traces ──"]
            for t in node.traces[-3:]:
                lines.append(f"  {t}")
        content = "\n".join(lines)
        self._insp_text.configure(state="normal")
        self._insp_text.delete("1.0", "end")
        self._insp_text.insert("end", content)
        self._insp_text.configure(state="disabled")

    def _reset_selected_drift(self):
        if self._selected_node_id:
            self.engine.reset_node_drift(self._selected_node_id)
            self._refresh_inspector()

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
            row = tk.Frame(self.player_list_inner, bg=BG2, cursor="hand2")
            row.pack(fill="x", pady=1)
            nid = state.current_node

            tk.Label(row, text="●", bg=BG2, fg=color,
                     font=("Courier", 9)).pack(side="left")
            tk.Label(row, text=f"{state.player_id:<6}", bg=BG2, fg=FG,
                     font=("Courier", 9)).pack(side="left", padx=4)
            tk.Label(row, text=state.current_node, bg=BG2, fg=FG_DIM,
                     font=("Courier", 8)).pack(side="left")
            tk.Label(row, text=f"  ({len(state.history)} steps)", bg=BG2, fg=FG_DIM,
                     font=("Courier", 7)).pack(side="left")
            row.bind("<Button-1>", lambda e, n=nid: self._select_node(n))
            for child in row.winfo_children():
                child.bind("<Button-1>", lambda e, n=nid: self._select_node(n))
