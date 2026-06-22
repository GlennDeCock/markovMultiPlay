"""
player_window.py — Individual player window, styled as an E-Ink screen.
800×600, off-white paper, black ink, dotted borders.
"""

import tkinter as tk
from tkinter import font as tkfont
from engine import STATUS_ACTIVE, STATUS_ENCOUNTER, STATUS_GAME_OVER
from image_gen import generate_scene_image, generate_choice_image

# ---------------------------------------------------------------------------
# E-Ink palette
# ---------------------------------------------------------------------------
PAPER     = "#dcdcd0"
PAPER_HOV = "#c8c8bc"
INK       = "#0f0f0c"
INK_DIM   = "#8a8a80"
INK_RULE  = "#aaaaA0"
WIN_BG    = "#0a0a08"

# ---------------------------------------------------------------------------
# Layout  (all px, 480×800 portrait e-ink)
# ---------------------------------------------------------------------------
BEZEL  = 0
SCR_W  = 480
SCR_H  = 800
PW     = SCR_W
PH     = SCR_H

IMG_W   = 280                         # 280×280 grid rendered at ZOOM=1 → 280px (1px dots)
IMG_H   = 280
IMG_PAD = 8
IMG_TOP = 18                          # dropped 10px from top
IMG_X   = (PW - IMG_W) // 2          # 100
SEP1_Y  = IMG_TOP + IMG_H + IMG_PAD  # 306

TEXT_Y  = SEP1_Y + 9                 # ~20% more gap
TRACE_H = 28
MAX_CHOICES   = 2
CHOICE_D      = 200                   # grid_size=100 at zoom=2 → 200px diameter
CHOICE_GRID   = 100
CHOICE_ZOOM   = 2
CHOICE_R      = CHOICE_D // 2
CHOICE_LX     = PW // 4
CHOICE_RX     = 3 * PW // 4
CHOICE_Y_CTR  = PH - CHOICE_R - 20
SEP2_Y        = CHOICE_Y_CTR - CHOICE_R - TRACE_H - 8
TEXT_H        = SEP2_Y - TEXT_Y
TRACE_Y       = SEP2_Y + 4
_TEXT_PADY    = 10                    # small fixed padding; zone height handles centering


class PlayerWindow:

    def __init__(self, parent_root, player_id: str, engine, on_event_cb):
        self.player_id = player_id
        self.engine    = engine
        self.on_event  = on_event_cb
        self._photo    = None

        self.win = tk.Toplevel(parent_root)
        self.win.title(player_id)
        self.win.geometry(f"{SCR_W}x{SCR_H}")
        self.win.resizable(False, False)
        self.win.configure(bg=WIN_BG)
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

        # Bind A/B keys to choice 0/1 for Digispark hardware support
        self.win.bind("<Key-a>", lambda e: self._on_choice(0))
        self.win.bind("<Key-A>", lambda e: self._on_choice(0))
        self.win.bind("<Key-b>", lambda e: self._on_choice(1))
        self.win.bind("<Key-B>", lambda e: self._on_choice(1))

        self._build_ui()
        self._refresh_from_state()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Paper frame
        paper = tk.Frame(self.win, bg=PAPER, width=PW, height=PH)
        paper.place(x=BEZEL, y=BEZEL)
        paper.pack_propagate(False)
        self._paper = paper

        # ── Outer border: none ──────────────────────────────────────────

        # ── Scene image ───────────────────────────────────────────────
        self._img_label = tk.Label(paper, bg=PAPER, bd=0,
                                   highlightthickness=0)
        self._img_label.place(x=IMG_X, y=IMG_TOP, width=IMG_W, height=IMG_H)

        # ── Scene text ────────────────────────────────────────────────
        mono = tkfont.Font(family="Courier", size=11)
        self.text_box = tk.Text(
            paper, wrap="word",
            bg=PAPER, fg=INK, font=mono,
            relief="flat", bd=0, state="disabled",
            cursor="arrow", spacing1=4, spacing3=4,
            highlightthickness=0, padx=24, pady=_TEXT_PADY,
        )
        self.text_box.tag_configure("center", justify="center")
        self.text_box.place(x=0, y=TEXT_Y, width=PW, height=TEXT_H)

        # ── Choice stars (noise-map dithered eight-spiked star) ────────
        bfont = tkfont.Font(family="Courier", size=8)
        self._choice_buttons: list = []
        self._choice_photos:  list = []
        self._choice_labels:  list = ["", ""]
        self._last_scene_node: str | None = None
        for i, cx_pos in enumerate([CHOICE_LX, CHOICE_RX]):
            x0 = cx_pos - CHOICE_R
            y0 = CHOICE_Y_CTR - CHOICE_R
            cv = tk.Canvas(paper, width=CHOICE_D, height=CHOICE_D,
                           bg=PAPER, highlightthickness=0, bd=0,
                           cursor="hand2")
            cv.place(x=x0, y=y0)
            photo = generate_choice_image("", grid_size=CHOICE_GRID, zoom=CHOICE_ZOOM, ink=INK, paper=PAPER)
            self._choice_photos.append(photo)
            img_id = cv.create_image(0, 0, image=photo, anchor="nw")
            txt_id = cv.create_text(
                CHOICE_R, CHOICE_R, text="",
                fill=INK, font=bfont,
                width=CHOICE_D - 56, justify="center", anchor="center",
            )
            idx = i
            cv.bind("<Button-1>", lambda e, i=idx: self._on_choice(i))
            self._choice_buttons.append((cv, img_id, txt_id))

        # ── Trace line (distinct dimmed line below sep2) ───────────────
        self._lbl_trace = tk.Label(
            paper, text="", bg=PAPER, fg=INK_DIM,
            font=("Courier", 8), anchor="center",
            wraplength=PW - 32, justify="center",
        )
        self._lbl_trace.place(x=16, y=TRACE_Y, width=PW - 32, height=TRACE_H)

        # ── Co-presence overlay widget removed (replaced by encounter system) ──

        # ── Restart button (hidden by default) ────────────────────────
        self._btn_restart = tk.Button(
            paper, text="[ restart ]",
            bg=PAPER, fg=INK, activebackground=PAPER_HOV,
            font=("Courier", 11), relief="flat", bd=0,
            pady=14, cursor="hand2",
            command=self._on_restart,
        )

        # ── Node id (top-right of text zone, very dim) ─────────────────────────────
        self._lbl_node = tk.Label(
            paper, text="", bg=PAPER, fg=INK_DIM,
            font=("Courier", 7), anchor="e",
        )
        self._lbl_node.place(x=PW - 100, y=SEP1_Y + 2, width=92)

        # ── Separator lines: none ────────────────────────────────────────

    # ------------------------------------------------------------------
    # State → UI
    # ------------------------------------------------------------------

    def _refresh_from_state(self):
        state = self.engine.players.get(self.player_id)
        if state is None:
            return

        node  = self.engine.active_graph.nodes.get(state.current_node)
        links = state.current_links

        node_text = self.engine.get_display_text_for_player(self.player_id)
        if not node_text and node:
            node_text = node.text

        if state.status == STATUS_ENCOUNTER:
            self._apply_screen(
                node_id=state.current_node,
                body_text=state.encounter_text or "",
                trace="",
                display=[],
                game_over=False,
                scene_photo=None,
                choice_photos=None,
            )
            return

        trace = self.engine.get_player_trace_text(self.player_id)

        display: list[tuple[str, str]] = []
        if state.status != STATUS_GAME_OVER:
            for ch in (links or [])[:MAX_CHOICES]:
                pfx = "↺  " if getattr(ch, "is_cross", False) else "→  "
                display.append((pfx, ch.label))

        scene_photo = None
        if self._last_scene_node != state.current_node:
            scene_photo = generate_scene_image(node_text, ink=INK, paper=PAPER)

        choice_photos: list[tuple[int, object]] = []
        for i, (pfx, label) in enumerate(display[:MAX_CHOICES]):
            if label != self._choice_labels[i]:
                choice_photos.append((
                    i,
                    generate_choice_image(
                        label, grid_size=CHOICE_GRID, zoom=CHOICE_ZOOM,
                        ink=INK, paper=PAPER,
                    ),
                ))

        self._apply_screen(
            node_id=state.current_node,
            body_text=node_text,
            trace=trace,
            display=display,
            game_over=state.status == STATUS_GAME_OVER,
            scene_photo=scene_photo,
            choice_photos=choice_photos,
        )
        if scene_photo is not None:
            self._last_scene_node = state.current_node

    def _apply_screen(self, *, node_id, body_text, trace, display,
                      game_over, scene_photo, choice_photos):
        """Apply a fully prepared screen in one shot (Pi-style atomic update)."""
        self._lbl_node.configure(text=node_id)
        self._set_text(body_text)
        self._lbl_trace.configure(text=trace)

        if game_over:
            for cv, *_ in self._choice_buttons:
                cv.place_forget()
            self._btn_restart.place(x=0, y=SEP2_Y + 2,
                                    width=PW, height=PH - SEP2_Y - 10)
        else:
            self._btn_restart.place_forget()
            cx_positions = [CHOICE_LX, CHOICE_RX]
            for i, (cv, img_id, txt_id) in enumerate(self._choice_buttons):
                if i < len(display):
                    pfx, label = display[i]
                    cv.place(x=cx_positions[i] - CHOICE_R, y=CHOICE_Y_CTR - CHOICE_R)
                    cv.itemconfigure(txt_id, text=pfx + label)
                else:
                    cv.place_forget()

        if scene_photo is not None:
            self._photo = scene_photo
            self._img_label.configure(image=scene_photo)

        if choice_photos:
            for i, photo in choice_photos:
                self._choice_photos[i] = photo
                self._choice_labels[i] = display[i][1]
                cv, img_id, _ = self._choice_buttons[i]
                cv.itemconfigure(img_id, image=photo)

        self.win.update_idletasks()

    def _set_text(self, text: str):
        self.text_box.configure(state="normal")
        self.text_box.delete("1.0", "end")
        self.text_box.insert("end", text, "center")
        self.text_box.configure(state="disabled")

    # ------------------------------------------------------------------
    # Interactions
    # ------------------------------------------------------------------

    def _on_choice(self, index: int):
        state = self.engine.players.get(self.player_id)
        if state is None:
            return
        if state.status == STATUS_ENCOUNTER:
            return  # locked during encounter
        self.engine.make_choice(self.player_id, index)
        self.on_event(refresh_only=True)

    def _on_restart(self):
        self.engine.reset_player(self.player_id)
        self._refresh_from_state()
        self.on_event(refresh_only=True)

    def _on_close(self):
        self.engine.remove_player(self.player_id)
        self.win.destroy()
        self.on_event(refresh_only=False)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def notify_graph_changed(self):
        if self.win.winfo_exists():
            self._refresh_from_state()

    def destroy(self):
        self.engine.remove_player(self.player_id)
        self.win.destroy()


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------
