"""
graph_canvas.py — Reusable force-directed graph visualization widget.

Used by both the player windows (local highlight) and the control window
(full overview). Pass highlight_player to mark one player's position.
"""

import tkinter as tk
import math
import random

# Visual constants
NODE_R        = 7
NODE_R_SELF   = 11
NODE_R_OTHER  = 9

# Colours
C_BG           = "#0d0d1a"
C_NODE_UNEXP   = "#1a1a3a"
C_NODE_EXP     = "#1e3a2a"
C_NODE_BORDER  = "#3a3a6a"
C_NODE_EXP_BDR = "#44cc88"
C_SELF         = "#4a9eff"
C_SELF_BDR     = "#88ccff"
C_OTHER        = "#ff6b35"
C_OTHER_BDR    = "#ffaa77"
C_COLLISION    = "#ff3366"
C_LINK         = "#2a4a6a"
C_LINK_CROSS   = "#6a2a4a"
C_LABEL        = "#334466"
C_LABEL_CROSS  = "#664433"
C_NODE_TEXT    = "#445566"
C_NODE_MUTATED     = "#3a2a0a"
C_NODE_MUTATED_BDR = "#cc8822"


def _lerp_hex(c1: str, c2: str, t: float) -> str:
    """Linearly interpolate between two hex colours."""
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = int(c1[1:3],16), int(c1[3:5],16), int(c1[5:7],16)
    r2, g2, b2 = int(c2[1:3],16), int(c2[3:5],16), int(c2[5:7],16)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"



class GraphCanvas:
    """
    Force-directed graph drawn on a tk.Canvas.

    Parameters
    ----------
    parent          : Tk parent widget
    engine          : StoryEngine instance (shared)
    width, height   : canvas size
    highlight_player: player_id whose current node gets the blue highlight
    show_labels     : show node id labels under dots
    bg              : background colour
    """

    def __init__(
        self,
        parent,
        engine,
        width: int = 400,
        height: int = 300,
        highlight_player: str = None,
        show_labels: bool = True,
        bg: str = C_BG,
    ):
        self.engine           = engine
        self.width            = width
        self.height           = height
        self.highlight_player = highlight_player
        self.show_labels      = show_labels

        self.canvas = tk.Canvas(
            parent, width=width, height=height,
            bg=bg, highlightthickness=0, bd=0,
        )

        # Layout state: node_id → [x, y]
        self._pos: dict[str, list] = {}
        self._animating = False

        # Zoom / pan state
        self._zoom     = 1.0
        self._view_cx  = width  / 2.0
        self._view_cy  = height / 2.0
        self._drag_start: tuple | None = None
        self._drag_vc:    tuple | None = None

        # Tooltip
        self._tip_id = None
        self.canvas.bind("<Motion>", self._on_mouse_move)
        self.canvas.bind("<Leave>",  self._on_mouse_leave)

        # Zoom (mouse wheel) and pan (right-click drag)
        self.canvas.bind("<MouseWheel>",      self._on_zoom)       # Windows
        self.canvas.bind("<Button-4>",        self._on_zoom_in)    # Linux scroll up
        self.canvas.bind("<Button-5>",        self._on_zoom_out)   # Linux scroll down
        self.canvas.bind("<ButtonPress-3>",   self._on_pan_start)
        self.canvas.bind("<B3-Motion>",       self._on_pan_drag)
        self.canvas.bind("<Double-Button-1>", self._reset_view)

        self._draw()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def pack(self, **kw):
        self.canvas.pack(**kw)

    def grid(self, **kw):
        self.canvas.grid(**kw)

    def set_highlight(self, player_id: str):
        self.highlight_player = player_id

    def refresh(self, animate: bool = True):
        """Call whenever the graph changes. Syncs layout and redraws."""
        self._sync_new_nodes()
        self._draw()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _sync_new_nodes(self):
        graph = self.engine.active_graph
        node_ids = list(graph.nodes.keys())
        missing = [nid for nid in node_ids if nid not in self._pos]
        if not missing:
            return

        if (self.engine._is_world_mode
                and len(node_ids) >= 3
                and len(self._pos) == 0):
            self._layout_world_intertwined(node_ids)
            return

        for node_id in missing:
            cx, cy = self._initial_pos(node_id)
            self._pos[node_id] = [cx, cy]

    def _layout_world_intertwined(self, node_ids: list[str]):
        """Force-directed layout — scattered start, springs on edges, links cross naturally."""
        from collections import deque

        graph = self.engine.active_graph
        if not node_ids:
            return

        adj: dict[str, list[str]] = {nid: [] for nid in node_ids}
        edge_pairs: list[tuple[str, str, bool]] = []
        seen_edges: set[tuple[str, str]] = set()
        for link in graph.links.values():
            a, b = link.from_node, link.to_node
            if a not in adj or b not in adj:
                continue
            key = (min(a, b), max(a, b))
            if key in seen_edges:
                continue
            seen_edges.add(key)
            if b not in adj[a]:
                adj[a].append(b)
            if a not in adj[b]:
                adj[b].append(a)
            is_cross = bool(getattr(link, "is_cross", False))
            edge_pairs.append((a, b, is_cross))

        # BFS tree edges — non-tree links get longer springs (chords across the map)
        root = max(node_ids, key=lambda nid: len(adj.get(nid, [])))
        tree_edges: set[tuple[str, str]] = set()
        seen = {root}
        q = deque([root])
        while q:
            n = q.popleft()
            for nb in adj.get(n, []):
                key = (min(n, nb), max(n, nb))
                if nb not in seen:
                    seen.add(nb)
                    tree_edges.add(key)
                    q.append(nb)

        n = len(node_ids)
        cx = self.width / 2
        cy = self.height / 2
        radius = max(100, 22 * math.sqrt(n))

        order = list(node_ids)
        random.shuffle(order)
        pos: dict[str, list[float]] = {}
        for i, nid in enumerate(order):
            angle = 2 * math.pi * i / n + random.uniform(-0.35, 0.35)
            r = radius * random.uniform(0.55, 1.2)
            pos[nid] = [cx + r * math.cos(angle), cy + r * math.sin(angle)]

        k_rep = 6500.0
        k_spring = 0.07
        rest_short = 52.0
        rest_long = 105.0

        for step in range(140):
            damp = 0.12 + 0.88 * (1.0 - step / 140.0)
            force = {nid: [0.0, 0.0] for nid in node_ids}

            for i, a in enumerate(node_ids):
                for b in node_ids[i + 1:]:
                    dx = pos[a][0] - pos[b][0]
                    dy = pos[a][1] - pos[b][1]
                    dist = max(1.0, math.hypot(dx, dy))
                    f = k_rep / (dist * dist)
                    fx, fy = f * dx / dist, f * dy / dist
                    force[a][0] += fx
                    force[a][1] += fy
                    force[b][0] -= fx
                    force[b][1] -= fy

            for a, b, is_cross in edge_pairs:
                dx = pos[b][0] - pos[a][0]
                dy = pos[b][1] - pos[a][1]
                dist = max(1.0, math.hypot(dx, dy))
                key = (min(a, b), max(a, b))
                if is_cross or key not in tree_edges:
                    rest = rest_long
                else:
                    rest = rest_short
                f = k_spring * (dist - rest)
                fx, fy = f * dx / dist, f * dy / dist
                force[a][0] += fx
                force[a][1] += fy
                force[b][0] -= fx
                force[b][1] -= fy

            for nid in node_ids:
                force[nid][0] += (cx - pos[nid][0]) * 0.003
                force[nid][1] += (cy - pos[nid][1]) * 0.003
                pos[nid][0] += force[nid][0] * damp * 0.35
                pos[nid][1] += force[nid][1] * damp * 0.35

        self._pos = {nid: [pos[nid][0], pos[nid][1]] for nid in node_ids}

    def _initial_pos(self, node_id: str) -> tuple:
        """Place new node near a linked neighbour, or at centre with jitter."""
        graph = self.engine.active_graph
        for link in graph.links.values():
            if link.to_node == node_id and link.from_node in self._pos:
                nx, ny = self._pos[link.from_node]
                a = random.uniform(0, 2 * math.pi)
                return (nx + 70 * math.cos(a), ny + 70 * math.sin(a))
            if link.from_node == node_id and link.to_node in self._pos:
                nx, ny = self._pos[link.to_node]
                a = random.uniform(0, 2 * math.pi)
                return (nx + 70 * math.cos(a), ny + 70 * math.sin(a))
        cx = self.width  / 2 + random.uniform(-80, 80)
        cy = self.height / 2 + random.uniform(-80, 80)
        return (cx, cy)

    # ------------------------------------------------------------------
    # Coordinate transforms (zoom / pan)
    # ------------------------------------------------------------------

    def _to_screen(self, wx: float, wy: float) -> tuple:
        """Convert world coordinates to canvas pixel coordinates."""
        sx = self.width  / 2 + (wx - self._view_cx) * self._zoom
        sy = self.height / 2 + (wy - self._view_cy) * self._zoom
        return sx, sy

    def _from_screen(self, sx: float, sy: float) -> tuple:
        """Convert canvas pixel coordinates to world coordinates."""
        wx = self._view_cx + (sx - self.width  / 2) / self._zoom
        wy = self._view_cy + (sy - self.height / 2) / self._zoom
        return wx, wy

    def _on_zoom(self, event):
        """Mouse-wheel zoom centred on the pointer (Windows)."""
        factor = 1.15 if event.delta > 0 else 1 / 1.15
        self._apply_zoom(factor, event.x, event.y)

    def _on_zoom_in(self, event):
        """Scroll-up zoom (Linux)."""
        self._apply_zoom(1.15, event.x, event.y)

    def _on_zoom_out(self, event):
        """Scroll-down zoom (Linux)."""
        self._apply_zoom(1 / 1.15, event.x, event.y)

    def _apply_zoom(self, factor: float, mx: int, my: int):
        new_zoom = max(0.15, min(10.0, self._zoom * factor))
        # Keep the world point under the mouse fixed in screen space
        wx, wy = self._from_screen(mx, my)
        self._zoom = new_zoom
        self._view_cx = wx - (mx - self.width  / 2) / new_zoom
        self._view_cy = wy - (my - self.height / 2) / new_zoom
        self._draw()

    def _on_pan_start(self, event):
        self._drag_start = (event.x, event.y)
        self._drag_vc    = (self._view_cx, self._view_cy)

    def _on_pan_drag(self, event):
        if self._drag_start is None:
            return
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        vcx, vcy = self._drag_vc
        self._view_cx = vcx - dx / self._zoom
        self._view_cy = vcy - dy / self._zoom
        self._draw()

    def _reset_view(self, event=None):
        """Double-click to reset zoom and pan to defaults."""
        self._zoom    = 1.0
        self._view_cx = self.width  / 2.0
        self._view_cy = self.height / 2.0
        self._draw()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw(self):
        if not self.canvas.winfo_exists():
            return
        self.canvas.delete("all")

        graph = self.engine.active_graph

        # Index players by node
        players_at: dict[str, list] = {}
        for pid, state in self.engine.players.items():
            players_at.setdefault(state.current_node, []).append(pid)

        # Current player's path (history) for path highlight
        path_set: set = set()
        if self.highlight_player and self.highlight_player in self.engine.players:
            hist = self.engine.players[self.highlight_player].history
            for i in range(len(hist) - 1):
                path_set.add((hist[i], hist[i + 1]))

        # --- Draw links ---
        for link in graph.links.values():
            if link.from_node not in self._pos or link.to_node not in self._pos:
                continue
            x1, y1 = self._to_screen(*self._pos[link.from_node])
            x2, y2 = self._to_screen(*self._pos[link.to_node])

            on_path = (link.from_node, link.to_node) in path_set
            color   = C_LINK_CROSS if link.is_cross else C_LINK
            width   = 2.0 if on_path else 1.2

            # Shorten line so it doesn't go under node circle
            dx, dy = x2 - x1, y2 - y1
            dist = max(math.hypot(dx, dy), 1)
            ux, uy = dx / dist, dy / dist
            r_end = NODE_R + 4
            ex, ey = x2 - ux * r_end, y2 - uy * r_end

            self.canvas.create_line(
                x1, y1, ex, ey,
                fill=color, width=width,
                arrow="last", arrowshape=(7, 9, 3),
                smooth=False,
            )

            # Short link label at midpoint
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            words  = link.label.split()
            short  = " ".join(words[:4]) + ("…" if len(words) > 4 else "")
            lc = C_LABEL_CROSS if link.is_cross else C_LABEL
            self.canvas.create_text(
                mx, my - 7, text=short,
                fill=lc, font=("Courier", 6), anchor="center",
            )

        # --- Draw nodes ---
        for node_id, pos in self._pos.items():
            x, y  = self._to_screen(*pos)
            node  = graph.nodes.get(node_id)
            if node is None:
                continue

            at_here = players_at.get(node_id, [])
            is_self  = self.highlight_player in at_here
            is_other = bool(set(at_here) - {self.highlight_player})
            multi    = len(at_here) >= 2
            collision_here = multi

            if is_self:
                r        = NODE_R_SELF
                fill     = C_COLLISION if collision_here else C_SELF
                outline  = C_SELF_BDR
                lw       = 2.5
            elif is_other:
                r        = NODE_R_OTHER
                fill     = C_OTHER
                outline  = C_OTHER_BDR
                lw       = 2.0
            elif node.is_mutated:
                drift = getattr(node, 'drift', 0)
                t     = min(1.0, drift / 20.0)
                r        = NODE_R
                fill     = _lerp_hex(C_NODE_EXP, C_NODE_MUTATED, t)
                outline  = _lerp_hex(C_NODE_EXP_BDR, C_NODE_MUTATED_BDR, t)
                lw       = 1.5 + t * 0.3
            elif node.expanded:
                r        = NODE_R
                fill     = C_NODE_EXP
                outline  = C_NODE_EXP_BDR
                lw       = 1.5
            else:
                r        = NODE_R - 2
                fill     = C_NODE_UNEXP
                outline  = C_NODE_BORDER
                lw       = 1.0

            # Pulse ring for current player
            if is_self:
                self.canvas.create_oval(
                    x - r - 5, y - r - 5, x + r + 5, y + r + 5,
                    outline=C_SELF, fill="", width=1.0,
                )

            self.canvas.create_oval(
                x - r, y - r, x + r, y + r,
                fill=fill, outline=outline, width=lw,
                tags=(f"node:{node_id}",),
            )

            # Node id label below dot
            if self.show_labels:
                label = node_id if len(node_id) <= 8 else node_id[:7] + "…"
                self.canvas.create_text(
                    x, y + r + 6, text=label,
                    fill=C_NODE_TEXT, font=("Courier", 6), anchor="n",
                    tags=(f"nodelabel:{node_id}",),
                )

            # Player count badge
            if len(at_here) > 1:
                self.canvas.create_text(
                    x + r, y - r, text=str(len(at_here)),
                    fill="#ffffff", font=("Courier", 7, "bold"), anchor="center",
                )

    # ------------------------------------------------------------------
    # Tooltip on hover
    # ------------------------------------------------------------------

    def _on_mouse_move(self, event):
        hovered = self._node_at(event.x, event.y)
        if hovered:
            self._show_tip(event.x, event.y, hovered)
        else:
            self._hide_tip()

    def _on_mouse_leave(self, event):
        self._hide_tip()

    def _node_at(self, mx: int, my: int) -> str | None:
        """Return node_id if mouse is within a node's hit radius (screen space)."""
        for node_id, (wx, wy) in self._pos.items():
            sx, sy = self._to_screen(wx, wy)
            if math.hypot(mx - sx, my - sy) <= NODE_R + 6:
                return node_id
        return None

    def _show_tip(self, x: int, y: int, node_id: str):
        self._hide_tip()
        node  = self.engine.active_graph.nodes.get(node_id)
        if not node:
            return
        at   = [pid for pid, s in self.engine.players.items() if s.current_node == node_id]
        text = node.text[:80] + ("…" if len(node.text) > 80 else "")
        mut_tag = f" [mutated ×{len(node.mutations)}]" if node.is_mutated else ""
        tip  = f"{node_id}  {'[expanded]' if node.expanded else '[unexpanded]'}{mut_tag}\n"
        if at:
            tip += f"here: {', '.join(at)}\n"
        tip += text
        self._tip_id = self.canvas.create_text(
            min(x + 12, self.width - 10), min(y + 12, self.height - 10),
            text=tip, anchor="nw",
            fill="#aaaacc", font=("Courier", 7),
            width=200,
        )
        # Background rect
        bbox = self.canvas.bbox(self._tip_id)
        if bbox:
            bg = self.canvas.create_rectangle(
                bbox[0] - 3, bbox[1] - 3, bbox[2] + 3, bbox[3] + 3,
                fill="#111122", outline="#334466",
            )
            self.canvas.tag_raise(self._tip_id, bg)
            self._tip_bg_id = bg

    def _hide_tip(self):
        if self._tip_id:
            self.canvas.delete(self._tip_id)
            self._tip_id = None
        if hasattr(self, "_tip_bg_id") and self._tip_bg_id:
            self.canvas.delete(self._tip_bg_id)
            self._tip_bg_id = None
