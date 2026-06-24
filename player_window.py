"""
player_window.py — Individual player window, styled as an E-Ink screen.
480×800 portrait — Background.png carries frame/button art; canvas overlays
cityscape + text only (no widget backgrounds).
"""

import tkinter as tk
from tkinter import font as tkfont
from engine import STATUS_ENCOUNTER, STATUS_GAME_OVER
from image_gen import generate_node_image
from ui_assets import load_ui_photo

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
PAPER     = "#ffffff"
INK       = "#0f0f0c"
INK_DIM   = "#8a8a80"
WIN_BG    = "#ffffff"

# ---------------------------------------------------------------------------
# Layout  (480×800 portrait e-ink — 7.5" panel)
# ---------------------------------------------------------------------------
BEZEL  = 0
SCR_W  = 480
SCR_H  = 800
PW     = SCR_W
PH     = SCR_H

SCENE_TOP     = 92
SCENE_W       = 340
SCENE_H       = 212
SCENE_X       = (PW - SCENE_W) // 2
SCENE_GRID_W  = SCENE_W
SCENE_GRID_H  = SCENE_H
SCENE_ZOOM    = 1

NODE_FRAME_W  = int(PW * 0.68)
NODE_FRAME_H  = int(NODE_FRAME_W * 666 / 1182)
NODE_FRAME_X  = (PW - NODE_FRAME_W) // 2
NODE_FRAME_Y  = 338
NODE_FRAME_BORDER = 0.05

TEXT_WRAP_W   = int(NODE_FRAME_W * (1 - 2 * NODE_FRAME_BORDER))
TEXT_CY       = NODE_FRAME_Y + NODE_FRAME_H // 2
TEXT_BODY_SIZE = 8
NODE_ID_TEXT_SIZE = 6

BTN_SIZE      = 88
BTN_Y         = PH - 112
CHOICE_GAP    = 62
CHOICE_LX     = PW // 2 - CHOICE_GAP
CHOICE_RX     = PW // 2 + CHOICE_GAP
CHOICE_TEXT_Y = BTN_Y - BTN_SIZE // 2 - 14
CHOICE_W      = 168

TRACE_H       = 22
TRACE_Y       = PH - TRACE_H - 6
MAX_CHOICES   = 2


class PlayerWindow:

    def __init__(self, parent_root, player_id: str, engine, on_event_cb):
        self.player_id = player_id
        self.engine    = engine
        self.on_event  = on_event_cb
        self._scene_photo = None
        self._last_scene_node: str | None = None
        self._ui_photos: list = []

        self.win = tk.Toplevel(parent_root)
        self.win.title(player_id)
        self.win.geometry(f"{SCR_W}x{SCR_H}")
        self.win.resizable(False, False)
        self.win.configure(bg=WIN_BG)
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

        self.win.bind("<Key-a>", lambda e: self._on_choice(0))
        self.win.bind("<Key-A>", lambda e: self._on_choice(0))
        self.win.bind("<Key-b>", lambda e: self._on_choice(1))
        self.win.bind("<Key-B>", lambda e: self._on_choice(1))

        self._build_ui()
        self._refresh_from_state()

    def _keep_photo(self, photo) -> object:
        self._ui_photos.append(photo)
        return photo

    def _build_ui(self):
        paper = tk.Frame(self.win, bg=WIN_BG, width=PW, height=PH)
        paper.place(x=BEZEL, y=BEZEL)
        paper.pack_propagate(False)
        self._paper = paper

        self._canvas = tk.Canvas(
            paper, width=PW, height=PH,
            highlightthickness=0, bd=0, bg=WIN_BG,
        )
        self._canvas.place(x=0, y=0)

        bg = self._keep_photo(load_ui_photo("Background.png", PW, PH))
        self._canvas.create_image(0, 0, image=bg, anchor="nw")

        self._scene_id = self._canvas.create_image(
            SCENE_X, SCENE_TOP, anchor="nw",
        )

        self._body_font = tkfont.Font(family="Georgia", size=TEXT_BODY_SIZE)
        self._node_font = tkfont.Font(family="Courier", size=NODE_ID_TEXT_SIZE)
        self._choice_font = tkfont.Font(family="Georgia", size=9)
        self._trace_font = tkfont.Font(family="Courier", size=7)

        self._body_text_id = self._canvas.create_text(
            NODE_FRAME_X + NODE_FRAME_W // 2, TEXT_CY,
            text="", width=TEXT_WRAP_W,
            font=self._body_font, fill=INK,
            justify="center", anchor="center",
        )
        self._node_text_id = self._canvas.create_text(
            NODE_FRAME_X + NODE_FRAME_W - int(NODE_FRAME_W * NODE_FRAME_BORDER),
            NODE_FRAME_Y + int(NODE_FRAME_H * NODE_FRAME_BORDER),
            text="", font=self._node_font, fill=INK_DIM, anchor="ne",
        )

        self._choice_text_ids: list[int] = []
        self._choice_hit_ids: list[int] = []
        for i, cx_pos in enumerate([CHOICE_LX, CHOICE_RX]):
            tid = self._canvas.create_text(
                cx_pos, CHOICE_TEXT_Y,
                text="", font=self._choice_font, fill=INK,
                width=CHOICE_W, justify="center", anchor="s",
            )
            hid = self._canvas.create_rectangle(
                cx_pos - BTN_SIZE // 2, BTN_Y - BTN_SIZE // 2,
                cx_pos + BTN_SIZE // 2, BTN_Y + BTN_SIZE // 2,
                fill="", outline="", width=0,
            )
            idx = i
            self._canvas.tag_bind(tid, "<Button-1>", lambda e, i=idx: self._on_choice(i))
            self._canvas.tag_bind(hid, "<Button-1>", lambda e, i=idx: self._on_choice(i))
            self._canvas.tag_bind(hid, "<Enter>", lambda e: self._canvas.configure(cursor="hand2"))
            self._canvas.tag_bind(hid, "<Leave>", lambda e: self._canvas.configure(cursor=""))
            self._choice_text_ids.append(tid)
            self._choice_hit_ids.append(hid)

        self._trace_id = self._canvas.create_text(
            PW // 2, TRACE_Y + TRACE_H // 2,
            text="", font=self._trace_font, fill=INK_DIM,
            width=PW - 32, justify="center", anchor="center",
        )

        self._restart_id = self._canvas.create_text(
            PW // 2, BTN_Y,
            text="[ restart ]", font=("Courier", 11), fill=INK,
            anchor="center", state="hidden",
        )
        self._canvas.tag_bind(self._restart_id, "<Button-1>", lambda e: self._on_restart())
        self._canvas.tag_bind(self._restart_id, "<Enter>", lambda e: self._canvas.configure(cursor="hand2"))
        self._canvas.tag_bind(self._restart_id, "<Leave>", lambda e: self._canvas.configure(cursor=""))

    def _set_choice_visible(self, index: int, visible: bool):
        state = "normal" if visible else "hidden"
        self._canvas.itemconfigure(self._choice_text_ids[index], state=state)
        self._canvas.itemconfigure(self._choice_hit_ids[index], state=state)

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
            )
            return

        trace = self.engine.get_player_trace_text(self.player_id)

        display: list[tuple[str, str]] = []
        if state.status != STATUS_GAME_OVER:
            for ch in (links or [])[:MAX_CHOICES]:
                pfx = "↺  " if getattr(ch, "is_cross", False) else ""
                display.append((pfx, ch.label))

        scene_photo = None
        node_key = state.current_node or node_text or ""
        if node_key and self._last_scene_node != state.current_node:
            scene_photo = generate_node_image(
                node_key, grid_w=SCENE_GRID_W, grid_h=SCENE_GRID_H,
                zoom=SCENE_ZOOM, ink=INK, paper=PAPER,
            )

        self._apply_screen(
            node_id=state.current_node,
            body_text=node_text,
            trace=trace,
            display=display,
            game_over=state.status == STATUS_GAME_OVER,
            scene_photo=scene_photo,
        )
        if scene_photo is not None:
            self._last_scene_node = state.current_node

    def _apply_screen(self, *, node_id, body_text, trace, display,
                      game_over, scene_photo):
        self._canvas.itemconfigure(self._node_text_id, text=node_id or "")
        self._canvas.itemconfigure(self._body_text_id, text=body_text or "")
        self._canvas.itemconfigure(self._trace_id, text=trace or "")

        if game_over:
            for i in range(MAX_CHOICES):
                self._set_choice_visible(i, False)
            self._canvas.itemconfigure(self._restart_id, state="normal")
        else:
            self._canvas.itemconfigure(self._restart_id, state="hidden")
            for i in range(MAX_CHOICES):
                if i < len(display):
                    pfx, label = display[i]
                    self._canvas.itemconfigure(self._choice_text_ids[i], text=pfx + label)
                    self._set_choice_visible(i, True)
                else:
                    self._set_choice_visible(i, False)

        if scene_photo is not None:
            self._scene_photo = scene_photo
            self._canvas.itemconfigure(self._scene_id, image=scene_photo)

        self.win.update_idletasks()

    def _on_choice(self, index: int):
        state = self.engine.players.get(self.player_id)
        if state is None:
            return
        if state.status == STATUS_ENCOUNTER:
            return
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

    def notify_graph_changed(self):
        if self.win.winfo_exists():
            self._refresh_from_state()

    def destroy(self):
        self.engine.remove_player(self.player_id)
        self.win.destroy()
