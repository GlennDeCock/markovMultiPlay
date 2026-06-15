#!/usr/bin/env python3
"""world_editor.py — Visual graph editor for MultiMarkovPlay worlds."""

import tkinter as tk
from tkinter import filedialog, messagebox
import json, os, math, re
from pathlib import Path

NODE_R = 28

COLORS = {
    "bg": "#0a0a08",
    "canvas_bg": "#dcdcd0",
    "edge": "#8a8a80",
    "edge_hi": "#0f0f0c",
    "node": "#d0d0c4",
    "node_sel": "#0f0f0c",
    "node_conn": "#b84a1a",
    "node_text": "#0f0f0c",
    "node_id": "#8a8a80",
    "panel": "#dcdcd0",
    "panel_fg": "#0f0f0c",
    "panel_dim": "#8a8a80",
    "entry": "#d0d0c4",
    "btn": "#d0d0c4",
    "btn_fg": "#0f0f0c",
    "btn_danger": "#b84a1a",
    "btn_success": "#1a6a30",
    "bar": "#0a0a08",
    "bar_fg": "#dcdcd0",
    "sep": "#aaaaa0",
}


def _id_from_title(title: str, existing: set[str]) -> str:
    s = re.sub(r"[^a-z0-9\s]+", "", title.lower().strip())
    s = re.sub(r"\s+", "_", s).strip("_")
    if not s or s[0].isdigit():
        s = "node_" + s
    if not s:
        s = "untitled"
    base = s
    i = 2
    while s in existing:
        s = f"{base}_{i}"
        i += 1
    return s


class WorldEditor:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("MultiMarkovPlay — World Editor")
        self.root.geometry("1600x900")
        self.root.configure(bg=COLORS["panel"])

        self.nodes: dict[str, dict] = {}
        self.selected_id: str | None = None
        self.connect_source_id: str | None = None
        self.file_path: str | None = None

        self._drag_node = None
        self._drag_sx = 0
        self._drag_sy = 0
        self._drag_nx = 0
        self._drag_ny = 0

        self._build_ui()
        self._bind_events()
        self._autosave_timer()
        self._update_status("Double-click canvas to add a node. Click to select. C to connect.")
        self._redraw()

    # ------------------------------------------------------------------
    # UI build
    # ------------------------------------------------------------------

    def _build_ui(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        fm = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=fm)
        fm.add_command(label="New World", command=self._new_world, accelerator="Ctrl+N")
        fm.add_command(label="Open...",     command=self._open_file, accelerator="Ctrl+O")
        fm.add_command(label="Save",        command=self._save,      accelerator="Ctrl+S")
        fm.add_command(label="Save As...",  command=self._save_as)
        fm.add_separator()
        fm.add_command(label="Export Clean JSON...", command=self._export_clean)
        fm.add_separator()
        fm.add_command(label="Exit", command=self.root.quit)

        # toolbar
        tb = tk.Frame(self.root, bg=COLORS["bar"], height=36)
        tb.pack(side="top", fill="x")

        self._btn_connect = tk.Button(
            tb, text="\u270e Connect (C)", bg=COLORS["btn"], fg=COLORS["btn_fg"],
            relief="flat", padx=10, pady=2, font=("Courier", 9),
            command=self._toggle_connect_mode)
        self._btn_connect.pack(side="left", padx=4, pady=4)

        tk.Button(
            tb, text="\U0001f5d1 Delete (Del)", bg=COLORS["btn"], fg=COLORS["btn_fg"],
            relief="flat", padx=10, pady=2, font=("Courier", 9),
            command=self._delete_selected).pack(side="left", padx=4, pady=4)

        self._lbl_ncount = tk.Label(
            tb, text="Total nodes: 0", bg=COLORS["bar"], fg=COLORS["bar_fg"],
            font=("Courier", 9))
        self._lbl_ncount.pack(side="left", padx=20)

        self._status_label = tk.Label(
            tb, text="", bg=COLORS["bar"], fg=COLORS["bar_fg"],
            font=("Courier", 9))
        self._status_label.pack(side="right", padx=10)

        # paned: canvas | inspector
        paned = tk.PanedWindow(self.root, orient="horizontal", bg=COLORS["bg"], sashwidth=3)
        paned.pack(fill="both", expand=True)

        # canvas
        cf = tk.Frame(paned, bg=COLORS["canvas_bg"])
        paned.add(cf, stretch="always")

        self.canvas = tk.Canvas(cf, bg=COLORS["canvas_bg"], highlightthickness=0,
                                scrollregion=(0, 0, 4000, 4000))
        hb = tk.Scrollbar(cf, orient="horizontal", command=self.canvas.xview)
        vb = tk.Scrollbar(cf, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hb.set, yscrollcommand=vb.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        vb.grid(row=0, column=1, sticky="ns")
        hb.grid(row=1, column=0, sticky="ew")
        cf.grid_rowconfigure(0, weight=1)
        cf.grid_columnconfigure(0, weight=1)

        # inspector
        self._insp_frame = tk.Frame(paned, bg=COLORS["panel"], width=420)
        paned.add(self._insp_frame, stretch="never")
        paned.sash_place(0, 1150, 0)

        self._insp_cv = tk.Canvas(self._insp_frame, bg=COLORS["panel"], highlightthickness=0)
        iv = tk.Scrollbar(self._insp_frame, orient="vertical", command=self._insp_cv.yview)

        self._insp_inner = tk.Frame(self._insp_cv, bg=COLORS["panel"])
        self._insp_inner.bind("<Configure>",
            lambda e: self._insp_cv.configure(scrollregion=self._insp_cv.bbox("all")))
        self._insp_cv.create_window((0, 0), window=self._insp_inner,
                                     anchor="nw", width=410)
        self._insp_cv.configure(yscrollcommand=iv.set)

        self._insp_cv.pack(side="left", fill="both", expand=True)
        iv.pack(side="right", fill="y")

        self._build_inspector_empty()

    def _bind_events(self):
        self.root.bind("<Control-n>",     lambda e: self._new_world())
        self.root.bind("<Control-o>",     lambda e: self._open_file())
        self.root.bind("<Control-s>",     lambda e: self._save())
        self.root.bind("<Delete>",        lambda e: self._delete_selected())
        self.root.bind("<BackSpace>",     lambda e: self._delete_selected())
        self.root.bind("<KeyPress-c>",    lambda e: self._toggle_connect_mode())
        self.root.bind("<KeyPress-C>",    lambda e: self._toggle_connect_mode())
        self.root.bind("<Escape>",        lambda e: self._cancel_connect_mode())

        self.canvas.bind("<Button-1>",       self._on_canvas_click)
        self.canvas.bind("<B1-Motion>",      self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>",self._on_canvas_release)
        self.canvas.bind("<Double-Button-1>",self._on_canvas_dbl)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def _update_status(self, msg):
        self._status_label.config(text=msg)

    def _update_ncount(self):
        self._lbl_ncount.config(text=f"Total nodes: {len(self.nodes)}")

    # ------------------------------------------------------------------
    # Autosave
    # ------------------------------------------------------------------

    def _autosave_timer(self):
        if self.nodes and self.file_path:
            autopath = self.file_path + ".autosave"
            try:
                out = []
                for nid, nd in self.nodes.items():
                    out.append({
                        "id": nid,
                        "title": nd.get("title", nid),
                        "description": nd.get("description", ""),
                        "pos": [nd["x"], nd["y"]],
                        "exits": nd.get("exits", []),
                    })
                start_nodes = sorted(self.nodes)[:8]
                os.makedirs(os.path.dirname(autopath) or ".", exist_ok=True)
                with open(autopath, "w") as f:
                    json.dump({"start_nodes": start_nodes, "nodes": out},
                              f, indent=2, ensure_ascii=False)
            except Exception:
                pass
        self.root.after(60000, self._autosave_timer)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _redraw(self):
        self.canvas.delete("all")

        for nid, node in self.nodes.items():
            for ex in node.get("exits", []):
                if ex["to"] in self.nodes:
                    self._draw_edge(nid, ex["to"], ex.get("label", ""))

        for nid in self.nodes:
            self._draw_node(nid)

        if self.connect_source_id and self.connect_source_id in self.nodes:
            nd = self.nodes[self.connect_source_id]
            self.canvas.create_oval(
                nd["x"] - NODE_R - 6, nd["y"] - NODE_R - 6,
                nd["x"] + NODE_R + 6, nd["y"] + NODE_R + 6,
                outline=COLORS["node_conn"], width=2, dash=(4, 4), tags="temp")

    def _draw_node(self, nid):
        nd = self.nodes[nid]
        x, y = nd["x"], nd["y"]
        r = NODE_R

        if nid == self.selected_id:
            fill, out, w = COLORS["node_sel"], COLORS["panel_fg"], 2.5
        elif nid == self.connect_source_id:
            fill, out, w = COLORS["node_conn"], COLORS["panel_fg"], 2.5
        else:
            fill, out, w = COLORS["node"], COLORS["sep"], 1.5

        self.canvas.create_oval(x - r, y - r, x + r, y + r,
                                fill=fill, outline=out, width=w,
                                tags=("n", nid))

        self.canvas.create_text(x, y, text=nd.get("title", nid),
                                fill=COLORS["node_text"], font=("Courier", 7, "bold"),
                                width=r * 3, tags=("n", nid))

        self.canvas.create_text(x, y + r + 10, text=nid,
                                fill=COLORS["node_id"], font=("Courier", 6),
                                tags=("n", nid))

    def _draw_edge(self, fid, tid, label):
        a, b = self.nodes[fid], self.nodes[tid]
        dx = b["x"] - a["x"]
        dy = b["y"] - a["y"]
        d = math.sqrt(dx * dx + dy * dy)
        if d < 1:
            return

        nx, ny = dx / d, dy / d
        x1 = a["x"] + nx * NODE_R
        y1 = a["y"] + ny * NODE_R
        x2 = b["x"] - nx * NODE_R
        y2 = b["y"] - ny * NODE_R

        color = COLORS["edge_hi"] if fid == self.selected_id else COLORS["edge"]
        lw = 2.0 if fid == self.selected_id else 1.2

        self.canvas.create_line(x1, y1, x2, y2, fill=color, width=lw,
                                arrow="last", arrowshape=(8, 10, 5), tags="e")

        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        self.canvas.create_text(mx, my - 10, text=label,
                                fill=COLORS["panel_dim"], font=("Courier", 6), tags="e")

    # ------------------------------------------------------------------
    # Canvas events
    # ------------------------------------------------------------------

    def _hit_test(self, x, y):
        for nid, nd in self.nodes.items():
            dx = x - nd["x"]
            dy = y - nd["y"]
            if dx * dx + dy * dy <= NODE_R * NODE_R:
                return nid
        return None

    def _on_canvas_click(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        nid = self._hit_test(x, y)

        if self.connect_source_id:
            if nid and nid != self.connect_source_id:
                self._create_connection(self.connect_source_id, nid)
                self._cancel_connect_mode()
            elif not nid:
                self._cancel_connect_mode()
            return

        if nid:
            self._select_node(nid)
            self._drag_node = nid
            self._drag_sx, self._drag_sy = event.x, event.y
            self._drag_nx, self._drag_ny = self.nodes[nid]["x"], self.nodes[nid]["y"]
        else:
            self._select_node(None)

    def _on_canvas_drag(self, event):
        if not self._drag_node:
            return
        dx, dy = event.x - self._drag_sx, event.y - self._drag_sy
        if abs(dx) > 3 or abs(dy) > 3:
            nd = self.nodes[self._drag_node]
            nd["x"] = self._drag_nx + dx
            nd["y"] = self._drag_ny + dy
            self._redraw()

    def _on_canvas_release(self, event):
        self._drag_node = None

    def _on_canvas_dbl(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        if self._hit_test(x, y):
            return

        title = "placeholder"
        nid = _id_from_title(title, set(self.nodes))
        self.nodes[nid] = {
            "id": nid, "title": title, "description": "",
            "x": x, "y": y, "exits": [],
        }
        self._select_node(nid)
        self._redraw()
        self._update_ncount()
        self._update_status(f"Created node '{nid}'. Click it to edit its details.")

    # ------------------------------------------------------------------
    # Selection & inspector
    # ------------------------------------------------------------------

    def _select_node(self, nid):
        self.selected_id = nid
        self._redraw()
        self._build_inspector() if nid and nid in self.nodes else self._build_inspector_empty()

    def _build_inspector_empty(self):
        for w in self._insp_inner.winfo_children():
            w.destroy()
        tk.Label(self._insp_inner, text="World Editor",
                 bg=COLORS["panel"], fg=COLORS["panel_fg"],
                 font=("Courier", 14, "bold")).pack(pady=20)
        tk.Label(self._insp_inner, text="Double-click canvas to add a node.\nClick a node to select and edit.",
                 bg=COLORS["panel"], fg=COLORS["panel_dim"],
                 font=("Courier", 9)).pack(pady=10)
        tk.Label(self._insp_inner, text=f"Nodes: {len(self.nodes)}",
                 bg=COLORS["panel"], fg=COLORS["panel_dim"],
                 font=("Courier", 9)).pack(pady=5)
        self._insp_cv.after(10, lambda: self._insp_cv.configure(
            scrollregion=self._insp_cv.bbox("all")))

    def _build_inspector(self):
        for w in self._insp_inner.winfo_children():
            w.destroy()
        nid = self.selected_id
        if not nid or nid not in self.nodes:
            self._build_inspector_empty()
            return

        nd = self.nodes[nid]

        # title
        tk.Label(self._insp_inner, text="Title", bg=COLORS["panel"],
                 fg=COLORS["panel_fg"], font=("Courier", 9, "bold")
                 ).pack(anchor="w", padx=10, pady=(10, 0))
        self._ti_var = tk.StringVar(value=nd.get("title", ""))
        tk.Entry(self._insp_inner, textvariable=self._ti_var,
                 bg=COLORS["entry"], fg=COLORS["panel_fg"],
                 font=("Courier", 11), relief="flat", bd=4
                 ).pack(fill="x", padx=10, pady=2)
        self._ti_var.trace_add("write", self._on_title_change)

        # id
        tk.Label(self._insp_inner, text=f"ID: {nid}",
                 bg=COLORS["panel"], fg=COLORS["panel_dim"],
                 font=("Courier", 8)).pack(anchor="w", padx=10, pady=(2, 0))

        # description
        tk.Label(self._insp_inner, text="Description",
                 bg=COLORS["panel"], fg=COLORS["panel_fg"],
                 font=("Courier", 9, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
        df = tk.Frame(self._insp_inner, bg=COLORS["panel"])
        df.pack(fill="both", expand=True, padx=10, pady=2)
        self._td = tk.Text(df, bg=COLORS["entry"], fg=COLORS["panel_fg"],
                           font=("Courier", 10), relief="flat", bd=4,
                           wrap="word", height=14)
        self._td.insert("1.0", nd.get("description", ""))
        self._td.pack(fill="both", expand=True)
        self._td.bind("<KeyRelease>", self._on_desc_change)

        # exits
        self._rebuild_exits()

        # delete button
        tk.Button(self._insp_inner, text="\U0001f5d1 Delete Node",
                  bg=COLORS["btn_danger"], fg=COLORS["panel_fg"],
                  relief="flat", bd=2, font=("Courier", 10),
                  command=self._delete_selected).pack(pady=10)

        self._insp_cv.after(10, lambda: self._insp_cv.configure(
            scrollregion=self._insp_cv.bbox("all")))

    def _rebuild_exits(self):
        if hasattr(self, "_exs") and self._exs.winfo_exists():
            self._exs.destroy()

        nid = self.selected_id
        if not nid or nid not in self.nodes:
            return
        nd = self.nodes[nid]
        targets = sorted(t for t in self.nodes if t != nid)

        self._exs = tk.Frame(self._insp_inner, bg=COLORS["panel"])
        self._exs.pack(fill="x", pady=4)

        tk.Label(self._exs, text=f"Exits ({len(nd.get('exits', []))})",
                 bg=COLORS["panel"], fg=COLORS["panel_fg"],
                 font=("Courier", 9, "bold")).pack(anchor="w", padx=10)

        exf = tk.Frame(self._exs, bg=COLORS["panel"])
        exf.pack(fill="x", padx=10, pady=2)

        disp_map = {t: f"{self.nodes[t].get('title', t)} ({t})" for t in targets}
        inv_map  = {v: k for k, v in disp_map.items()}

        for i, ex in enumerate(nd.get("exits", [])):
            row = tk.Frame(exf, bg=COLORS["panel"])
            row.pack(fill="x", pady=2)

            tv = tk.StringVar(value=disp_map.get(ex["to"], ex["to"]))
            om = tk.OptionMenu(row, tv, *disp_map.values())
            om.configure(bg=COLORS["entry"], fg=COLORS["panel_fg"],
                         relief="flat", bd=2, font=("Courier", 8),
                         highlightthickness=0, activebackground=COLORS["btn"],
                         direction="above")
            om.pack(side="left", fill="x", expand=True)

            def tv_cb(idx, tv=tv):
                def fn(*_):
                    if self.selected_id and self.selected_id in self.nodes:
                        exs = self.nodes[self.selected_id]["exits"]
                        if idx < len(exs):
                            v = tv.get()
                            exs[idx]["to"] = inv_map.get(v, v)
                return fn
            tv.trace_add("write", tv_cb(i))

            lv = tk.StringVar(value=ex.get("label", ""))
            tk.Entry(row, textvariable=lv, bg=COLORS["entry"],
                     fg=COLORS["panel_fg"], font=("Courier", 9),
                     relief="flat", bd=2).pack(side="left", fill="x", expand=True, padx=(4, 0))

            def lv_cb(idx, lv=lv):
                def fn(*_):
                    if self.selected_id and self.selected_id in self.nodes:
                        exs = self.nodes[self.selected_id]["exits"]
                        if idx < len(exs):
                            exs[idx]["label"] = lv.get()
                return fn
            lv.trace_add("write", lv_cb(i))

            def rm(idx):
                if self.selected_id and self.selected_id in self.nodes:
                    exs = self.nodes[self.selected_id].get("exits", [])
                    if idx < len(exs):
                        exs.pop(idx)
                    self._rebuild_exits()
                    self._redraw()

            tk.Button(row, text="\u2715", bg=COLORS["btn_danger"], fg=COLORS["panel_fg"],
                      relief="flat", bd=2, font=("Courier", 9), width=2,
                      command=lambda i=i: rm(i)).pack(side="left", padx=(4, 0))

        if not targets:
            tk.Label(exf, text="No other nodes to connect to.",
                     bg=COLORS["panel"], fg=COLORS["panel_dim"],
                     font=("Courier", 9)).pack(pady=4)
        else:
            tk.Button(exf, text="+ Add Exit", bg=COLORS["btn_success"], fg=COLORS["panel_fg"],
                      relief="flat", bd=2, font=("Courier", 9),
                      command=self._add_exit).pack(fill="x", pady=4)

    # ------------------------------------------------------------------
    # Inspector change handlers
    # ------------------------------------------------------------------

    def _on_title_change(self, *_):
        nid = self.selected_id
        if nid and nid in self.nodes:
            self.nodes[nid]["title"] = self._ti_var.get()
            self._redraw()

    def _on_desc_change(self, event=None):
        nid = self.selected_id
        if nid and nid in self.nodes:
            self.nodes[nid]["description"] = self._td.get("1.0", "end-1c")

    # ------------------------------------------------------------------
    # Connect mode
    # ------------------------------------------------------------------

    def _toggle_connect_mode(self):
        if self.connect_source_id:
            self._cancel_connect_mode()
            return
        if not self.selected_id:
            self._update_status("Select a source node first, then press C to connect.")
            return
        self.connect_source_id = self.selected_id
        self._btn_connect.config(bg=COLORS["btn_danger"], fg=COLORS["panel_fg"])
        self._update_status(f"Connect mode: click a target node to connect from '{self.selected_id}'")
        self._redraw()

    def _cancel_connect_mode(self):
        self.connect_source_id = None
        self._btn_connect.config(bg=COLORS["btn"], fg=COLORS["btn_fg"])
        self._update_status("")
        self._redraw()

    def _create_connection(self, fid, tid):
        for ex in self.nodes[fid].get("exits", []):
            if ex["to"] == tid:
                self._update_status(f"Exit to '{tid}' already exists.")
                return
        label = f"Enter {self.nodes[tid].get('title', tid)}"
        self.nodes[fid].setdefault("exits", []).append({"to": tid, "label": label})
        self._redraw()
        self._update_status(f"Connected '{fid}' \u2192 '{tid}'")
        if self.selected_id == fid:
            self._rebuild_exits()

    def _add_exit(self):
        nid = self.selected_id
        if not nid or nid not in self.nodes:
            return
        targets = [t for t in self.nodes if t != nid and
                   not any(e["to"] == t for e in self.nodes[nid].get("exits", []))]
        if targets:
            t = targets[0]
            label = f"Enter {self.nodes[t].get('title', t)}"
            self.nodes[nid].setdefault("exits", []).append({"to": t, "label": label})
        else:
            self.nodes[nid].setdefault("exits", []).append({"to": "", "label": ""})
        self._rebuild_exits()
        self._redraw()

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    def _delete_selected(self):
        nid = self.selected_id
        if not nid or nid not in self.nodes:
            return
        if not messagebox.askyesno("Delete Node", f"Delete '{nid}'?"):
            return
        for nd in self.nodes.values():
            nd["exits"] = [e for e in nd.get("exits", []) if e["to"] != nid]
        del self.nodes[nid]
        self.selected_id = None
        self._cancel_connect_mode()
        self._redraw()
        self._build_inspector_empty()
        self._update_ncount()

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _new_world(self):
        if self.nodes and not messagebox.askyesno("New World", "Clear all nodes?"):
            return
        self.nodes = {}
        self.selected_id = None
        self.connect_source_id = None
        self.file_path = None
        self._cancel_connect_mode()
        self._redraw()
        self._build_inspector_empty()
        self._update_ncount()

    def _open_file(self, path=None):
        if not path:
            path = filedialog.askopenfilename(
                title="Open World File",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                initialdir=str(Path(__file__).parent / "data" / "world"))
        if not path:
            return
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load file:\n{e}")
            return

        self.nodes = {}
        for nd in data.get("nodes", []):
            nid = nd["id"]
            p = nd.get("pos", [0, 0])
            self.nodes[nid] = {
                "id": nid,
                "title": nd.get("title", nid),
                "description": nd.get("description", ""),
                "x": p[0] if isinstance(p, list) and len(p) >= 2 else 100,
                "y": p[1] if isinstance(p, list) and len(p) >= 2 else 100,
                "exits": nd.get("exits", []),
            }

        self._auto_layout_if_needed()
        self.file_path = path
        self.selected_id = None
        self._cancel_connect_mode()
        self._redraw()
        self._build_inspector_empty()
        self._update_ncount()
        self._update_status(f"Loaded {len(self.nodes)} nodes from {path}")

    def _auto_layout_if_needed(self):
        if len(self.nodes) < 2:
            return
        xs = [n["x"] for n in self.nodes.values()]
        ys = [n["y"] for n in self.nodes.values()]
        if any(abs(x) > 10 or abs(y) > 10 for x, y in zip(xs, ys)):
            return

        cols = min(10, math.ceil(math.sqrt(len(self.nodes))))
        sx, sy = 120, 100
        for i, nid in enumerate(sorted(self.nodes)):
            c, r = i % cols, i // cols
            self.nodes[nid]["x"] = 100 + c * sx
            self.nodes[nid]["y"] = 100 + r * sy

    def _save(self):
        if self.file_path:
            self._write_file(self.file_path)
        else:
            self._save_as()

    def _save_as(self):
        suggested = self.file_path or str(
            Path(__file__).parent / "data" / "world" / "my_world.json")
        path = filedialog.asksaveasfilename(
            title="Save World File",
            filetypes=[("JSON files", "*.json")],
            defaultextension=".json",
            initialfile=os.path.basename(suggested),
            initialdir=os.path.dirname(suggested))
        if path:
            self.file_path = path
            self._write_file(path)

    def _write_file(self, path):
        out = []
        for nid, nd in self.nodes.items():
            out.append({
                "id": nid,
                "title": nd.get("title", nid),
                "description": nd.get("description", ""),
                "pos": [nd["x"], nd["y"]],
                "exits": nd.get("exits", []),
            })
        start_nodes = sorted(self.nodes)[:8]
        data = {"start_nodes": start_nodes, "nodes": out}

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self._update_status(f"Saved {len(out)} nodes to {path}")

    def _export_clean(self):
        path = filedialog.asksaveasfilename(
            title="Export Clean JSON (no positions)",
            filetypes=[("JSON files", "*.json")],
            defaultextension=".json",
            initialfile="clean_world.json")
        if not path:
            return
        out = []
        for nid, nd in self.nodes.items():
            out.append({
                "id": nid,
                "title": nd.get("title", nid),
                "description": nd.get("description", ""),
                "exits": nd.get("exits", []),
            })
        start_nodes = sorted(self.nodes)[:8]
        with open(path, "w") as f:
            json.dump({"start_nodes": start_nodes, "nodes": out},
                      f, indent=2, ensure_ascii=False)
        self._update_status(f"Exported {len(out)} nodes (no positions) to {path}")


if __name__ == "__main__":
    WorldEditor().root.mainloop()
