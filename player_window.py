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
BTN_CV_H = 80                         # kept for restart-button sizing compat
BTN_PAD = 16
BTN_GAP = 10
BTN_W   = (PW - BTN_PAD * 2 - BTN_GAP) // 2
BTN_H   = BTN_CV_H + 24

# Choice button zone (replaces fixed 2-button strip)
CHOICE_BTN_H   = 40                   # height of each choice button canvas
CHOICE_GAP     = 5                    # gap between buttons
CHOICE_PAD     = 16                   # horizontal padding
MAX_CHOICES    = 5                    # pre-built button slots
_CHOICE_ZONE   = MAX_CHOICES * CHOICE_BTN_H + (MAX_CHOICES - 1) * CHOICE_GAP  # 220
SEP2_Y         = PH - _CHOICE_ZONE - 8    # bottom of text zone  (~556)
TEXT_H         = SEP2_Y - TEXT_Y          # text area height     (~230)
CHOICE_Y_START = SEP2_Y + 6              # first button top y    (~562)
CHOICE_W       = PW - CHOICE_PAD * 2     # button width          (552)


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

        # ── Choice buttons (vertical stack, MAX_CHOICES pre-built slots) ──
        bfont = tkfont.Font(family="Courier", size=10)
        self._choice_buttons: list = []   # list of (canvas, text_item_id)
        for i in range(MAX_CHOICES):
            y_pos = CHOICE_Y_START + i * (CHOICE_BTN_H + CHOICE_GAP)
            cv = tk.Canvas(paper, width=CHOICE_W, height=CHOICE_BTN_H,
                           bg=PAPER, highlightthickness=0, bd=0,
                           cursor="hand2")
            cv.place(x=CHOICE_PAD, y=y_pos)
            _dotted_rect(cv, 1, 1, CHOICE_W - 1, CHOICE_BTN_H - 1)
            txt_id = cv.create_text(
                16, CHOICE_BTN_H // 2, text="",
                fill=INK, font=bfont,
                width=CHOICE_W - 24, justify="left", anchor="w",
            )
            idx = i
            cv.bind("<Button-1>", lambda e, i=idx: self._on_choice(i))
            cv.bind("<Enter>",    lambda e, c=cv: c.configure(bg=PAPER_HOV))
            cv.bind("<Leave>",    lambda e, c=cv: c.configure(bg=PAPER))
            self._choice_buttons.append((cv, txt_id))

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

        # Get the correct node regardless of engine mode
        node  = self.engine.active_graph.nodes.get(state.current_node)
        links = state.current_links
        if state.status == STATUS_COLLISION and state.collision_overlay_text:
            text = state.collision_overlay_text
        else:
            text = node.text if node else ""

        self._lbl_node.configure(text=state.current_node)
        self._set_text(text)
        self._update_image(text)

        if state.status == STATUS_GAME_OVER:
            for cv, _ in self._choice_buttons:
                cv.place_forget()
            self._btn_restart.place(x=0, y=SEP2_Y + 2,
                                    width=PW, height=_CHOICE_ZONE + 6)
        else:
            self._btn_restart.place_forget()

            # Build display list: (prefix, label) per choice
            choices = links or []
            if state.status == STATUS_COLLISION and state.collision_choice_labels:
                col_labels = state.collision_choice_labels
                display = []
                for i, lnk in enumerate(choices[:MAX_CHOICES]):
                    label = col_labels[i] if i < len(col_labels) else lnk.label
                    display.append(("->  ", label))
            else:
                display = []
                for ch in choices[:MAX_CHOICES]:
                    ctype = getattr(ch, "choice_type", "exit")
                    if ctype == "interact":
                        pfx = "o  "
                    elif getattr(ch, "is_cross", False):
                        pfx = "~  "
                    else:
                        pfx = "->  "
                    display.append((pfx, ch.label))

            for i, (cv, txt_id) in enumerate(self._choice_buttons):
                y_pos = CHOICE_Y_START + i * (CHOICE_BTN_H + CHOICE_GAP)
                if i < len(display):
                    pfx, label = display[i]
                    cv.place(x=CHOICE_PAD, y=y_pos)
                    cv.itemconfigure(txt_id, text=pfx + label)
                else:
                    cv.place_forget()

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
