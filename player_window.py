"""
player_window.py — Individual player window, styled as an E-Ink screen.
800×600, off-white paper, black ink, dotted borders.
"""

import tkinter as tk
from tkinter import font as tkfont
from engine import STATUS_ACTIVE, STATUS_COLLISION, STATUS_GAME_OVER
from image_gen import generate_scene_image

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
# Layout  (all px, paper = 784 × 584)
# image 300×300 + padding / text / buttons
# ---------------------------------------------------------------------------
BEZEL  = 8
SCR_W  = 600
SCR_H  = 800
PW     = SCR_W - BEZEL * 2   # 584
PH     = SCR_H - BEZEL * 2   # 784

IMG_W   = 300                         # 100×100 grid rendered at ZOOM=3
IMG_H   = 300
IMG_PAD = 12                          # whitespace above/below image
SEP1_Y  = IMG_H + IMG_PAD * 2        # 324 — bottom of image zone
IMG_TOP = IMG_PAD                     # 12  — top of image
IMG_X   = (PW - IMG_W) // 2          # 142 — horizontally centred

TEXT_Y  = SEP1_Y + 2                  # 326
BTN_CV_H = 80                         # canvas height for each button widget
BTN_PAD = 16
BTN_GAP = 10
BTN_W   = (PW - BTN_PAD * 2 - BTN_GAP) // 2   # 366
BTN_H   = BTN_CV_H + 24              # total button strip height
SEP2_Y  = PH - BTN_H - 2            # bottom of text zone
TEXT_H  = SEP2_Y - TEXT_Y            # remaining for text
BTN_Y   = SEP2_Y + 2 + (BTN_H - BTN_CV_H) // 2  # vertically centred in strip


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

        # ── Outer dotted border (canvas behind everything) ────────────
        border_cv = tk.Canvas(paper, width=PW, height=PH,
                              bg=PAPER, highlightthickness=0, bd=0)
        border_cv.place(x=0, y=0)
        _dotted_rect(border_cv, 4, 4, PW - 4, PH - 4)
        # stays at bottom z-order (created first)

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
            cursor="arrow", spacing1=5, spacing3=5,
            highlightthickness=0, padx=24, pady=10,
        )
        self.text_box.place(x=0, y=TEXT_Y, width=PW, height=TEXT_H)

        # ── Buttons ───────────────────────────────────────────────────
        bfont = tkfont.Font(family="Courier", size=10)

        def make_btn(x_pos, cmd):
            cv = tk.Canvas(paper, width=BTN_W, height=BTN_CV_H,
                           bg=PAPER, highlightthickness=0, bd=0,
                           cursor="hand2")
            cv.place(x=x_pos, y=BTN_Y)
            _dotted_rect(cv, 1, 1, BTN_W - 1, BTN_CV_H - 1)
            lbl = cv.create_text(
                BTN_W // 2, BTN_CV_H // 2, text="",
                fill=INK, font=bfont,
                width=BTN_W - 20, justify="left", anchor="center",
            )
            cv.bind("<Button-1>", lambda e: cmd())
            cv.bind("<Enter>",    lambda e, c=cv: c.configure(bg=PAPER_HOV))
            cv.bind("<Leave>",    lambda e, c=cv: c.configure(bg=PAPER))
            return cv, lbl

        self._bcv0, self._btxt0 = make_btn(BTN_PAD,
                                            lambda: self._on_choice(0))
        self._bcv1, self._btxt1 = make_btn(BTN_PAD + BTN_W + BTN_GAP,
                                            lambda: self._on_choice(1))

        # ── Restart button (hidden by default) ────────────────────────
        self._btn_restart = tk.Button(
            paper, text="[ restart ]",
            bg=PAPER, fg=INK, activebackground=PAPER_HOV,
            font=("Courier", 11), relief="flat", bd=0,
            pady=14, cursor="hand2",
            command=self._on_restart,
        )

        # ── Node id (bottom-right, very dim) ──────────────────────────
        self._lbl_node = tk.Label(
            paper, text="", bg=PAPER, fg=INK_DIM,
            font=("Courier", 7), anchor="e",
        )
        self._lbl_node.place(x=PW - 100, y=PH - 14, width=92)

        # ── Separator lines — created LAST so they sit on top ─────────
        # Each is a thin Canvas strip placed over the relevant y position.
        sep1 = tk.Canvas(paper, width=PW, height=3,
                         bg=PAPER, highlightthickness=0, bd=0)
        sep1.place(x=0, y=SEP1_Y)
        sep1.create_line(18, 1, PW - 18, 1,
                         fill=INK_RULE, dash=(2, 5), width=1)

        sep2 = tk.Canvas(paper, width=PW, height=3,
                         bg=PAPER, highlightthickness=0, bd=0)
        sep2.place(x=0, y=SEP2_Y)
        sep2.create_line(18, 1, PW - 18, 1,
                         fill=INK_RULE, dash=(2, 5), width=1)

    # ------------------------------------------------------------------
    # State → UI
    # ------------------------------------------------------------------

    def _refresh_from_state(self):
        state = self.engine.players.get(self.player_id)
        if state is None:
            return

        node  = self.engine.graph.nodes.get(state.current_node)
        links = state.current_links
        if state.status == STATUS_COLLISION and state.collision_overlay_text:
            text = state.collision_overlay_text
        else:
            text = node.text if node else ""

        self._lbl_node.configure(text=state.current_node)
        self._set_text(text)
        self._update_image(text)

        if state.status == STATUS_GAME_OVER:
            self._bcv0.place_forget()
            self._bcv1.place_forget()
            self._btn_restart.place(x=0, y=SEP2_Y + 2,
                                    width=PW, height=BTN_H)
        else:
            self._btn_restart.place_forget()
            self._bcv0.place(x=BTN_PAD, y=BTN_Y)
            self._bcv1.place(x=BTN_PAD + BTN_W + BTN_GAP, y=BTN_Y)

            if state.status == STATUS_COLLISION and state.collision_choice_labels:
                lbl0 = state.collision_choice_labels[0]
                lbl1 = (
                    state.collision_choice_labels[1]
                    if len(state.collision_choice_labels) > 1
                    else "—"
                )
            else:
                lbl0 = links[0].label if links else "—"
                lbl1 = links[1].label if len(links) > 1 else "—"
            pfx0 = "↺  " if (links and links[0].is_cross) else "→  "
            pfx1 = "↺  " if (len(links) > 1 and links[1].is_cross) else "→  "

            self._bcv0.itemconfigure(self._btxt0, text=pfx0 + lbl0)
            self._bcv1.itemconfigure(self._btxt1, text=pfx1 + lbl1)

    def _set_text(self, text: str):
        self.text_box.configure(state="normal")
        self.text_box.delete("1.0", "end")
        self.text_box.insert("end", text)
        self.text_box.configure(state="disabled")

    def _update_image(self, text: str):
        photo = generate_scene_image(text, ink=INK, paper=PAPER)
        self._photo = photo
        self._img_label.configure(image=photo)

    # ------------------------------------------------------------------
    # Interactions
    # ------------------------------------------------------------------

    def _on_choice(self, index: int):
        state = self.engine.players.get(self.player_id)
        if state is None:
            return
        if state.status == STATUS_COLLISION:
            self.engine.resolve_collision_choice(self.player_id, index)
        else:
            self.engine.make_choice(self.player_id, index)
        self._refresh_from_state()
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

def _dotted_rect(cv, x1, y1, x2, y2):
    d = dict(fill=INK_RULE, dash=(2, 5), width=1)
    cv.create_line(x1, y1, x2, y1, **d)
    cv.create_line(x2, y1, x2, y2, **d)
    cv.create_line(x2, y2, x1, y2, **d)
    cv.create_line(x1, y2, x1, y1, **d)
