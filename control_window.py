"""
control_window.py — Central control panel.
Left: Markov chain settings + node overview list.
Right: Full shared graph (all players, all nodes).
"""

import tkinter as tk
from tkinter import ttk, font as tkfont, messagebox
from pathlib import Path
import time

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


def _btn(parent, text, cmd, bg=BTN, fg=FG, tooltip=None, **kw):
    btn = tk.Button(
        parent, text=text, command=cmd,
        bg=bg, fg=fg, activebackground=BTN_A, activeforeground=FG,
        relief="solid", bd=1, padx=8, pady=4,
        font=("Courier", 9), cursor="hand2", **kw,
    )
    if tooltip:
        ToolTip(btn, tooltip)
    return btn


class ToolTip:
    """Hover tooltip for any Tk widget."""

    def __init__(self, widget, text: str, delay_ms: int = 450):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._tip: tk.Toplevel | None = None
        self._after: str | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._hide()
        self._after = self.widget.after(self.delay_ms, self._show)

    def _show(self):
        self._after = None
        if not self.widget.winfo_exists():
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tw, text=self.text, justify="left",
            bg="#ffffe8", fg=FG, relief="solid", bd=1,
            font=("Courier", 8), padx=8, pady=5,
            wraplength=320,
        ).pack()

    def _hide(self, _event=None):
        if self._after:
            self.widget.after_cancel(self._after)
            self._after = None
        if self._tip:
            self._tip.destroy()
            self._tip = None


def _tip(widget, text: str):
    ToolTip(widget, text)
    return widget


def _short_path(path: Path, max_len: int = 42) -> str:
    s = str(path)
    if len(s) <= max_len:
        return s
    return "…" + s[-(max_len - 1):]


class WorldLoadDialog(tk.Toplevel):
    """Startup / manual dialog: load cached JSON, rebuild from text, or browse."""

    def __init__(self, parent, txt_path: Path, json_path: Path, title: str = "Load World"):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=BG2)
        self.resizable(False, False)
        self.result: str | None = None

        self.transient(parent)
        self.grab_set()

        pad = tk.Frame(self, bg=BG2, padx=20, pady=16)
        pad.pack(fill="both", expand=True)

        tk.Label(
            pad, text="How should the story world be loaded?",
            bg=BG2, fg=ACC, font=("Courier", 11, "bold"), anchor="w",
        ).pack(fill="x", pady=(0, 4))
        tk.Label(
            pad,
            text="Rebuild regenerates nodes from your .txt (Markov + graph).\n"
                 "Cached JSON loads the last generated world instantly.",
            bg=BG2, fg=FG_DIM, font=("Courier", 8), justify="left", anchor="w",
        ).pack(fill="x", pady=(0, 12))

        self._var = tk.StringVar(value="")
        options = []

        if json_path.exists():
            options.append((
                "cached",
                f"Use cached JSON\n{_short_path(json_path)}",
            ))
        if txt_path.exists():
            options.append((
                "rebuild",
                f"Rebuild from current text\n{_short_path(txt_path)}",
            ))
        options.append(("browse", "Choose a different .txt file…"))

        if json_path.exists():
            self._var.set("cached")
        elif txt_path.exists():
            self._var.set("rebuild")
        else:
            self._var.set("browse")

        for value, label in options:
            tips = {
                "cached": "Load the saved JSON as-is — fast, no regeneration. "
                          "Use after a previous rebuild or when the .txt has not changed.",
                "rebuild": "Re-read the current .txt, retrain Markov, regenerate all nodes "
                           "and overwrite the _generated.json sidecar.",
                "browse": "Pick any .txt file (structured locations or free prose corpus). "
                          "Generates or parses a world and sets it as active.",
            }
            rb = tk.Radiobutton(
                pad, text=label, variable=self._var, value=value,
                bg=BG2, fg=FG, activebackground=BG2, activeforeground=FG,
                selectcolor=BG3, font=("Courier", 9), anchor="w",
                justify="left", padx=8, pady=4,
            )
            rb.pack(fill="x", pady=2)
            _tip(rb, tips.get(value, ""))

        btn_row = tk.Frame(pad, bg=BG2)
        btn_row.pack(fill="x", pady=(14, 0))
        _btn(btn_row, "Load", self._on_load, fg=ACC3,
             tooltip="Apply the selected load option.").pack(side="right", padx=(6, 0))
        _btn(btn_row, "Cancel", self._on_cancel,
             tooltip="Skip — on startup, cached JSON is loaded if available.").pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.bind("<Return>", lambda e: self._on_load())
        self.bind("<Escape>", lambda e: self._on_cancel())

        self.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{x}+{y}")

    def _on_load(self):
        self.result = self._var.get()
        self.grab_release()
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.grab_release()
        self.destroy()


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
        self.engine.on_world_progress  = self._on_world_progress
        self.engine.on_schedule_main   = lambda fn: self.root.after(0, fn)

        from llm_client import LLMClient
        _llm = LLMClient.from_env()
        self.engine.llm_mode = _llm.mode
        self.engine.llm_model = _llm.model
        self.engine.llm_ollama_url = _llm.ollama_url

        self.player_windows: dict[str, PlayerWindow] = {}
        self._selected_node_id: str | None = None
        self._encounter_timers: dict[str, str] = {}  # node_id → after-id

        self._base = base
        self._init_default_world_paths()

        self._build_ui()
        self._refresh_player_list()
        self.root.update_idletasks()
        self._startup_load_world()
        self.root.after(60_000, self._gallery_idle_tick)
        self.root.after(900_000, self._autosave_tick)

    def _init_default_world_paths(self):
        """Set default txt/json paths (empty_city preferred)."""
        empty_city_json = self._base / "data" / "worlds" / "empty_city_generated.json"
        empty_city_txt  = self._base / "data" / "worlds" / "empty_city.txt"
        fallback_json   = self._base / "nodes.json"

        if empty_city_txt.exists():
            self._world_txt = empty_city_txt
        else:
            self._world_txt = self._base / "data" / "world" / "example_world.txt"

        if empty_city_json.exists():
            self._world_json = empty_city_json
        elif fallback_json.exists():
            self._world_json = fallback_json
        else:
            self._world_json = empty_city_json

    def _startup_load_world(self):
        """Ask how to load the world on first launch."""
        dlg = WorldLoadDialog(
            self.root, self._world_txt, self._world_json,
            title="MultiMarkovPlay — Load World",
        )
        self.root.wait_window(dlg)

        if dlg.result == "cached":
            self._load_cached_world()
        elif dlg.result == "rebuild":
            self._rebuild_world(show_errors=True)
        elif dlg.result == "browse":
            self._load_from_text_file()
        elif self._world_json.exists():
            self._load_cached_world()
        else:
            messagebox.showwarning(
                "No World",
                "No world loaded. Use the World section to load a JSON or text file.",
            )

    def _update_world_status(self, extra: str = ""):
        if not hasattr(self, "lbl_world_status"):
            return
        n = len(self.engine.world.nodes) if self.engine.world else 0
        latent = len(self.engine._latent_nodes)
        until = max(
            0,
            self.engine._effective_spawn_every() - self.engine._node_changes_since_spawn,
        )
        txt = self._world_txt.name if self._world_txt.exists() else "(no source .txt)"
        js = self._world_json.name if self._world_json.exists() else "(no JSON yet)"
        latent_s = f"  +{latent} latent" if latent else ""
        spawn_s = f"  spawn in {until}" if self.engine.world else ""
        if self.engine.world and self.engine.gallery_pace:
            eff = self.engine._effective_spawn_every()
            idle_m = self.engine.gallery_idle_seconds_remaining() // 60
            spawn_s = f"  gallery spawn/{eff} in {until}  idle {idle_m}m"
        status = f"{n} nodes{latent_s}{spawn_s}  ·  text: {txt}  ·  json: {js}"
        if extra:
            status = f"{extra}  —  {status}"
        self.lbl_world_status.configure(text=status)

    def _on_world_progress(self, msg: str):
        self._update_world_status(msg)
        self.root.update_idletasks()

    def _on_llm_mode(self, *_):
        mode = self.var_llm_mode.get()
        self.engine.llm_mode = mode
        self.engine.llm_model = self.var_llm_model.get() or None

    def _test_llm(self):
        from llm_client import LLMClient
        self._on_llm_mode()
        client = LLMClient(
            mode=self.engine.llm_mode,
            model=self.engine.llm_model,
            ollama_url=self.engine.llm_ollama_url,
        )
        ok, msg = client.test_connection()
        if ok:
            messagebox.showinfo("LLM Test", msg)
        else:
            messagebox.showerror("LLM Test", msg)

    def _spawn_now(self):
        n = self.engine.spawn_now()
        if n:
            self._reset_graph_layout()
            self._notify_all_graph_changed()
        self._update_world_status(
            f"Spawned {n} location(s)" if n else "Spawn failed (no corpus?)"
        )

    def _open_world_log(self):
        self.engine.world_log.open_window(self.root)

    def _show_llm_changes_if_any(self):
        """After rebuild, offer to open log if LLM/sanity made edits."""
        if not getattr(self.engine, "_last_review_had_changes", False):
            return
        self.engine._last_review_had_changes = False
        if messagebox.askyesno(
            "World quality review",
            "Sanity rules and/or the AI made changes during rebuild.\n\n"
            "Open World Log to review what changed?",
        ):
            self._open_world_log()

    def _on_spawn_every_changes(self, val):
        self.engine.spawn_every_node_changes = int(float(val))
        self._update_world_status()

    def _on_gallery_pace(self):
        self.engine.gallery_pace = self.var_gallery_pace.get()
        self._update_world_status()

    def _gallery_idle_tick(self):
        if self.engine.world and self.engine.gallery_pace:
            n = self.engine.tick_gallery_idle()
            if n:
                self._reset_graph_layout()
                self._notify_all_graph_changed()
            self._update_world_status()
        self.root.after(60_000, self._gallery_idle_tick)

    def _autosave_tick(self):
        if self.engine.world:
            from world_archive import save_session
            path = save_session(self.engine, snapshot=True)
            if path:
                self._update_world_status(f"Auto-saved {path.name}")
        self.root.after(900_000, self._autosave_tick)

    def _export_day(self):
        from world_archive import export_day
        if not self.engine.world:
            messagebox.showwarning("Export day", "No world loaded.")
            return
        json_path, log_path = export_day(
            self.engine,
            self.engine.world_log.text(),
            base_dir=self._base / "data" / "sessions",
        )
        messagebox.showinfo(
            "Export day",
            f"Saved:\n{json_path}\n{log_path}",
        )
        self._update_world_status(f"Exported {json_path.name}")

    def _reset_graph_layout(self):
        self.graph_cv._pos.clear()
        self.graph_cv.refresh(animate=True)

    def _load_cached_world(self):
        """Load the sidecar / cached JSON without re-parsing text."""
        path = self._world_json
        if not path.exists():
            messagebox.showerror(
                "Load Cached JSON",
                f"File not found:\n{path}",
            )
            return
        try:
            self.engine.load_world(path)
            self._reset_graph_layout()
            self._update_world_status("cached loaded")
        except Exception as exc:
            messagebox.showerror("Load Cached JSON", str(exc))

    def _apply_world_from_text(self, txt_path: Path) -> int:
        """Parse/generate from .txt, retrain Markov, reload world."""
        json_path, n = self.engine.load_from_text(txt_path)
        self._world_txt = txt_path
        self._world_json = json_path
        for pw in self.player_windows.values():
            self.engine.spawn_player(pw.player_id)
            pw._refresh_from_state()
        self._refresh_player_list()
        self._reset_graph_layout()
        latent = len(self.engine._latent_nodes)
        mode = "generated" if latent > 0 else "parsed"
        extra = f"  +{latent} latent" if latent > 0 else ""
        self._update_world_status(f"{mode} {n} nodes{extra}")
        if self.engine._last_review_had_changes:
            self._show_llm_changes_if_any()
        return n

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

        # World — source files and load actions
        lbl_world_hdr = tk.Label(left, text="world", bg=BG2, fg=ACC,
                 font=("Courier", 10, "bold"))
        lbl_world_hdr.grid(row=3, column=0, sticky="w")
        _tip(lbl_world_hdr,
             "Story map loaded from .txt (source) and/or _generated.json (cached graph).")

        self.lbl_world_status = tk.Label(
            left, text="not loaded", bg=BG2, fg=FG_DIM,
            font=("Courier", 7), wraplength=250, justify="left", anchor="w",
        )
        self.lbl_world_status.grid(row=4, column=0, sticky="ew", pady=(2, 6))
        _tip(self.lbl_world_status,
             "Active world: node count, source text file, and cached JSON sidecar.")

        world_btns = tk.Frame(left, bg=BG2)
        world_btns.grid(row=5, column=0, sticky="ew", pady=(0, 4))
        _btn(world_btns, "Cached JSON", self._load_cached_world,
             tooltip="Load existing JSON only — instant, no Markov regen. "
                     "Use when the .txt has not changed since last rebuild."
             ).pack(side="left", padx=(0, 4))
        _btn(world_btns, "Rebuild Text", self._rebuild_world, fg="#0055aa",
             tooltip="Re-parse the current .txt, retrain Markov, regenerate nodes, "
                     "and overwrite the _generated.json file."
             ).pack(side="left", padx=4)
        _btn(world_btns, "Other .txt…", self._load_from_text_file, fg=ACC3,
             tooltip="Browse for a different world .txt (structured locations or prose corpus)."
             ).pack(side="left", padx=4)
        _btn(world_btns, "Reload…", self._show_world_load_dialog,
             tooltip="Open the startup load dialog again (cached / rebuild / browse)."
             ).pack(side="left", padx=4)

        # LLM quality + play-driven spawning
        lbl_llm_hdr = tk.Label(left, text="quality (LLM)", bg=BG2, fg=ACC,
                 font=("Courier", 10, "bold"))
        lbl_llm_hdr.grid(row=6, column=0, sticky="w", pady=(4, 0))
        _tip(lbl_llm_hdr,
             "Optional OpenAI/Ollama review runs in the background during play — "
             "Markov text shows immediately; AI fixes nodes you've already left.")

        llm_f = tk.Frame(left, bg=BG2)
        llm_f.grid(row=7, column=0, sticky="ew", pady=2)

        self.var_llm_mode = tk.StringVar(value=self.engine.llm_mode)
        for label, val in [("Off", "off"), ("OpenAI", "openai"), ("Ollama", "ollama")]:
            tk.Radiobutton(
                llm_f, text=label, variable=self.var_llm_mode, value=val,
                bg=BG2, fg=FG, selectcolor=SEP, activebackground=BG2,
                font=("Courier", 8), command=self._on_llm_mode,
            ).pack(side="left", padx=(0, 6))

        self.var_llm_model = tk.StringVar(value=self.engine.llm_model or "")
        tk.Entry(llm_f, textvariable=self.var_llm_model, width=14,
                 bg=BG, fg=FG, font=("Courier", 8),
                 ).pack(side="left", padx=4)
        _btn(llm_f, "Test", self._test_llm,
             tooltip="Ping the configured LLM (or confirm Off mode)."
             ).pack(side="left", padx=2)

        disc_f = tk.Frame(left, bg=BG2)
        disc_f.grid(row=8, column=0, sticky="ew", pady=2)
        tk.Label(disc_f, text="spawn every", bg=BG2, fg=FG,
                 font=("Courier", 8)).pack(side="left")
        self.var_spawn_every = tk.IntVar(value=self.engine.spawn_every_node_changes)
        tk.Scale(disc_f, from_=3, to=20, orient="horizontal",
                 variable=self.var_spawn_every, bg=BG2, fg=FG, troughcolor=SEP,
                 highlightthickness=0, length=80, font=("Courier", 7),
                 command=self._on_spawn_every_changes,
                 ).pack(side="left", padx=2)
        tk.Label(disc_f, text="node changes", bg=BG2, fg=FG,
                 font=("Courier", 8)).pack(side="left", padx=(2, 6))
        _btn(disc_f, "Spawn now", self._spawn_now,
             tooltip="Add a Markov location immediately (LLM polishes text in background)."
             ).pack(side="left", padx=2)
        _btn(disc_f, "World Log", self._open_world_log,
             tooltip="Open window: player travel, items, node text changes, LLM edits."
             ).pack(side="left", padx=2)
        _btn(disc_f, "Export day", self._export_day,
             tooltip="Save final world JSON + world log to data/sessions/."
             ).pack(side="left", padx=2)

        gallery_f = tk.Frame(left, bg=BG2)
        gallery_f.grid(row=9, column=0, sticky="ew", pady=2)
        self.var_gallery_pace = tk.BooleanVar(value=self.engine.gallery_pace)
        cb_gallery = tk.Checkbutton(
            gallery_f, text="gallery pace", variable=self.var_gallery_pace,
            bg=BG2, fg=FG, selectcolor=SEP, activebackground=BG2,
            font=("Courier", 8), command=self._on_gallery_pace,
        )
        cb_gallery.pack(side="left")
        _tip(cb_gallery,
             "Unattended multi-player: scales spawn rate with player count and "
             "adds a location every ~12 min if the world goes quiet.")

        tk.Frame(left, bg=SEP, height=1).grid(row=10, column=0, sticky="ew", pady=8)

        # Spawn controls
        lbl_spawn_hdr = tk.Label(left, text="spawn players", bg=BG2, fg=ACC,
                 font=("Courier", 10, "bold"))
        lbl_spawn_hdr.grid(row=11, column=0, sticky="w")
        _tip(lbl_spawn_hdr,
             "Open E-Ink player windows on this PC (local mode) or assign IDs for server clients.")

        spawn_f = tk.Frame(left, bg=BG2)
        spawn_f.grid(row=12, column=0, sticky="ew", pady=4)
        spawn_f.columnconfigure(1, weight=1)

        lbl_count = tk.Label(spawn_f, text="count:", bg=BG2, fg=FG,
                 font=("Courier", 9))
        lbl_count.grid(row=0, column=0, sticky="w", padx=(0, 6))
        _tip(lbl_count, "How many new player windows to open (maximum 20 total).")
        self.var_count = tk.IntVar(value=3)
        scale_count = tk.Scale(spawn_f, from_=1, to=20, orient="horizontal",
                 variable=self.var_count, bg=BG2, fg=FG, troughcolor=SEP,
                 highlightthickness=0, showvalue=True, length=120,
                 font=("Courier", 8), activebackground=ACC,
                 )
        scale_count.grid(row=0, column=1, sticky="w")
        _tip(scale_count, "Number of players to spawn in one click.")

        btn_row = tk.Frame(left, bg=BG2)
        btn_row.grid(row=13, column=0, sticky="ew", pady=4)
        _btn(btn_row, "Spawn", self._spawn_players, fg=ACC3,
             tooltip="Create player windows at spread-out starting nodes."
             ).pack(side="left", padx=(0, 4))
        _btn(btn_row, "Close All", self._close_all, fg=ACC2,
             tooltip="Close every player window (removes players from the session)."
             ).pack(side="left", padx=4)
        _btn(btn_row, "Reset All", self._reset_all,
             tooltip="Keep windows open but move each player to a fresh spawn point."
             ).pack(side="left", padx=4)

        tk.Frame(left, bg=SEP, height=1).grid(row=14, column=0, sticky="ew", pady=8)

        # Markov chain settings
        lbl_mc_hdr = tk.Label(left, text="markov chain", bg=BG2, fg=ACC,
                 font=("Courier", 10, "bold"))
        lbl_mc_hdr.grid(row=15, column=0, sticky="w")
        _tip(lbl_mc_hdr,
             "Controls generated text and choice labels. Retrain reloads training_texts/ "
             "unless you rebuilt from a world .txt (that corpus takes priority).")

        mc = tk.Frame(left, bg=BG2)
        mc.grid(row=15, column=0, sticky="ew", pady=4)
        mc.columnconfigure(1, weight=1)

        _MC_TIPS = {
            "order:": "Markov memory depth (n-gram order). Higher = more coherent, less surprising.",
            "text words:": "Target length of generated narrative passages (word count).",
            "choice words:": "Max words shown on each choice button.",
            "drift rate:": "How many visits before a node sentence is rewritten (1 = every visit).",
            "temperature:": "Randomness of generation. Low = repetitive; high = chaotic.",
        }

        def _sl_row(parent, row, label, var, lo, hi, cb):
            lbl = tk.Label(parent, text=label, bg=BG2, fg=FG,
                     font=("Courier", 9))
            lbl.grid(row=row, column=0, sticky="w", pady=2, padx=(0, 6))
            _tip(lbl, _MC_TIPS.get(label, ""))
            scl = tk.Scale(parent, from_=lo, to=hi, orient="horizontal",
                     variable=var, bg=BG2, fg=FG, troughcolor=SEP,
                     highlightthickness=0, showvalue=True, length=130,
                     font=("Courier", 8), activebackground=ACC,
                     command=cb,
                     )
            scl.grid(row=row, column=1, sticky="ew", pady=2)
            _tip(scl, _MC_TIPS.get(label, ""))
            return scl

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
        lbl_temp = tk.Label(mc, text="temperature:", bg=BG2, fg=FG,
                 font=("Courier", 9))
        lbl_temp.grid(row=4, column=0, sticky="w", pady=2, padx=(0, 6))
        _tip(lbl_temp, _MC_TIPS["temperature:"])
        scale_temp = tk.Scale(mc, from_=0.3, to=2.5, resolution=0.1, orient="horizontal",
                 variable=self.var_temp, bg=BG2, fg=FG, troughcolor=SEP,
                 highlightthickness=0, showvalue=True, length=130,
                 font=("Courier", 8), activebackground=ACC,
                 command=self._on_temp,
                 )
        scale_temp.grid(row=4, column=1, sticky="ew", pady=2)
        _tip(scale_temp, _MC_TIPS["temperature:"])
        lbl_temp_hint = tk.Label(mc, text="← precise    chaotic →", bg=BG2, fg=FG_DIM,
                 font=("Courier", 7))
        lbl_temp_hint.grid(row=5, column=1, sticky="w")

        retrain_row = tk.Frame(left, bg=BG2)
        retrain_row.grid(row=16, column=0, sticky="ew", pady=4)
        _btn(retrain_row, "Retrain Markov", self._retrain,
             tooltip="Reload all files in training_texts/ with current slider settings."
             ).pack(side="left")
        _btn(retrain_row, "Reset Graph", self._reset_graph, fg="#cc7700",
             tooltip="Dynamic mode only: wipe the runtime graph and respawn all players. "
                     "Does not reload the authored world JSON."
             ).pack(side="left", padx=6)
        self.lbl_train = tk.Label(retrain_row, text="", bg=BG2, fg=ACC3,
                                   font=("Courier", 8))
        self.lbl_train.pack(side="left", padx=6)
        _tip(self.lbl_train, "Brief status after retrain or world load.")

        tk.Frame(left, bg=SEP, height=1).grid(row=17, column=0, sticky="ew", pady=8)

        # Legend
        lbl_leg_hdr = tk.Label(left, text="legend", bg=BG2, fg=ACC,
                 font=("Courier", 10, "bold"))
        lbl_leg_hdr.grid(row=18, column=0, sticky="w")
        _tip(lbl_leg_hdr, "Graph dot and link colours (also shown in each player window).")

        legend_items = [
            ("●", "#4a9eff", "your position",
             "Highlighted player’s current node (blue pulse)."),
            ("●", "#ff6b35", "other player",
             "Another player is at this node (no collision yet)."),
            ("●", "#44cc88", "expanded node",
             "Node has been visited and exits were generated."),
            ("●", "#1a1a3a", "unexplored",
             "Node exists but no player has expanded it yet."),
            ("—", "#2a4a6a", "normal link",
             "Exit to a newly created or direct neighbour."),
            ("—", "#6a2a4a", "cross-link",
             "Exit crossing back to an existing distant node."),
        ]
        leg = tk.Frame(left, bg=BG2)
        leg.grid(row=19, column=0, sticky="ew", pady=4)
        for i, (sym, color, desc, tip) in enumerate(legend_items):
            sym_l = tk.Label(leg, text=sym, bg=BG2, fg=color,
                     font=("Courier", 10))
            sym_l.grid(row=i, column=0, sticky="w")
            desc_l = tk.Label(leg, text=desc, bg=BG2, fg=FG_DIM,
                     font=("Courier", 8))
            desc_l.grid(row=i, column=1, sticky="w", padx=6)
            _tip(sym_l, tip)
            _tip(desc_l, tip)

        tk.Frame(left, bg=SEP, height=1).grid(row=20, column=0, sticky="ew", pady=8)

        # Node inspector
        lbl_insp_hdr = tk.Label(left, text="node inspector", bg=BG2, fg=ACC,
                 font=("Courier", 10, "bold"))
        lbl_insp_hdr.grid(row=21, column=0, sticky="w")
        _tip(lbl_insp_hdr,
             "Click a player in the list below to inspect their current node text and drift.")

        insp = tk.Frame(left, bg=BG2)
        insp.grid(row=22, column=0, sticky="nsew", pady=4)
        insp.columnconfigure(0, weight=1)
        left.rowconfigure(22, weight=1)

        self._insp_text = tk.Text(
            insp, bg=BG3, fg=FG, font=("Courier", 7),
            relief="flat", bd=0, state="disabled",
            highlightthickness=0, wrap="word", padx=6, pady=6,
        )
        self._insp_text.pack(fill="both", expand=True)
        _tip(self._insp_text,
             "Original vs current node text, drift count, and recent player traces.")

        insp_btns = tk.Frame(left, bg=BG2)
        insp_btns.grid(row=23, column=0, sticky="ew", pady=2)
        _btn(insp_btns, "Reset Drift", self._reset_selected_drift, fg="#cc7700",
             tooltip="Restore the selected node’s text to its original authored/generated version."
             ).pack(side="left")

        tk.Frame(left, bg=SEP, height=1).grid(row=24, column=0, sticky="ew", pady=8)

        # Player list
        lbl_players_hdr = tk.Label(left, text="players", bg=BG2, fg=ACC,
                 font=("Courier", 10, "bold"))
        lbl_players_hdr.grid(row=25, column=0, sticky="w")
        _tip(lbl_players_hdr,
             "Active players — click a row to inspect that node in the graph and inspector.")

        list_frame = tk.Frame(left, bg=BG2)
        list_frame.grid(row=26, column=0, sticky="nsew", pady=4)
        list_frame.columnconfigure(0, weight=1)
        left.rowconfigure(26, weight=1)

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
        lbl_graph_hdr = tk.Label(header, text="shared story graph", bg=BG3, fg=FG_DIM,
                 font=("Courier", 9))
        lbl_graph_hdr.pack(side="left")
        _tip(lbl_graph_hdr,
             "Scroll wheel = zoom · Right-drag = pan · Double-click = reset view · "
             "Hover a node for its id.")

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

    def _show_world_load_dialog(self):
        """Re-open the load-world choice dialog (same as startup)."""
        dlg = WorldLoadDialog(
            self.root, self._world_txt, self._world_json,
            title="Reload World",
        )
        self.root.wait_window(dlg)
        if dlg.result == "cached":
            self._load_cached_world()
        elif dlg.result == "rebuild":
            self._rebuild_world(show_errors=True)
        elif dlg.result == "browse":
            self._load_from_text_file()

    def _load_from_text_file(self):
        """Open a .txt file picker, then parse + train + load the world in one step."""
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Load World from Text",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialdir=str(self._base / "data" / "worlds"),
        )
        if not path:
            return
        try:
            self._apply_world_from_text(Path(path))
        except Exception as exc:
            messagebox.showerror("Load from Text", str(exc))

    def _rebuild_world(self, show_errors: bool = True):
        """Re-parse the current source .txt, retrain Markov, and reload the world."""
        if not self._world_txt.exists():
            if show_errors:
                messagebox.showerror(
                    "Rebuild World",
                    f"Source text not found:\n{self._world_txt}\n\n"
                    "Use Other .txt… to pick a file first.",
                )
            return
        try:
            self._apply_world_from_text(self._world_txt)
        except Exception as exc:
            if show_errors:
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

    def _on_graph_change(self, skip_players=None, moved_player=None, canvas_only=False):
        """Engine callback: graph structure changed."""
        self.graph_cv.refresh(animate=moved_player is None and not canvas_only)
        if canvas_only:
            self._refresh_inspector()
            return
        if moved_player:
            pw = self.player_windows.get(moved_player)
            if pw and pw.win.winfo_exists():
                pw.notify_graph_changed()
        else:
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
        if node.exits:
            lines += ["", "── all exits ──"]
            for ex in node.exits:
                dest = self.engine.world.nodes.get(ex.to_node)
                dest_title = dest.title if dest else ex.to_node
                lines.append(f"  → {dest_title} ({ex.to_node}): {ex.label}")
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
