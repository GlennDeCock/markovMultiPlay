"""
Interactive image_gen preview — type commands, see results immediately.

Run from project root:
    python image_gen_playground.py

Commands (prefix optional: scene / choice / seal / all):
    scene You stand in an empty lobby.
    choice take the stairs
    seal node courtyard_north
    seal item rusty_key
    all The elevator doors are open.
    samples          — cycle built-in seal samples
    grid             — seal contact sheet
    clear            — drop render caches
    save [path.png]  — save current main image
    help
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from pathlib import Path
import time

import image_gen
from image_gen import (
    generate_scene_image,
    generate_choice_image,
    generate_seal_image,
    generate_seal_pil_image,
    generate_scene_pil_image,
    _scene_cache,
    _choice_cache,
    _seal_cache,
)

INK = "#0f0f0c"
PAPER = "#dcdcd0"
BG = "#0a0a08"
BG2 = "#dcdcd0"
FG = "#0f0f0c"
FG_DIM = "#8a8a80"

SEAL_SAMPLES = [
    ("node", "courtyard_north"),
    ("node", "elevator_shaft"),
    ("node", "roof_garden"),
    ("node", "empty_lobby"),
    ("choice", "take the stairs"),
    ("choice", "wait by the door"),
    ("item", "rusty_key"),
    ("item", "faded_map"),
    ("item", "broken_compass"),
]

SCENE_SAMPLES = [
    "You stand at the corner of two empty streets.",
    "The building casts a long shadow across the pavement.",
    "A bicycle leans against the wall near the door.",
    "The elevator doors are open. A sign says OUT OF ORDER.",
    "The courtyard smells of rain and old stone.",
    "Fire escapes zig-zag down the building face.",
]


class ImageGenPlayground:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("image_gen playground")
        self.root.configure(bg=BG)
        self.root.geometry("920x780")

        self._photos: list[tk.PhotoImage] = []
        self._current_pil = None
        self._current_label = ""
        self._sample_idx = 0
        self._scene_idx = 0

        top = tk.Frame(root, bg=BG2, padx=10, pady=8)
        top.pack(fill="x")

        tk.Label(
            top, text="image_gen playground", bg=BG2, fg=FG,
            font=("Courier", 11, "bold"),
        ).pack(anchor="w")
        self._status = tk.Label(
            top, text="Ready — type a command below.", bg=BG2, fg=FG_DIM,
            font=("Courier", 9), wraplength=880, justify="left",
        )
        self._status.pack(anchor="w", pady=(4, 0))

        body = tk.Frame(root, bg=BG, padx=10, pady=6)
        body.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(body, bg=PAPER, highlightthickness=1,
                                 highlightbackground="#aaaaa0")
        self._canvas.pack(fill="both", expand=True)

        entry_row = tk.Frame(root, bg=BG, padx=10, pady=8)
        entry_row.pack(fill="x")

        tk.Label(entry_row, text=">", bg=BG, fg=FG_DIM,
                 font=("Courier", 10)).pack(side="left")
        self._entry = tk.Entry(
            entry_row, bg=BG2, fg=FG, insertbackground=FG,
            font=("Courier", 10), relief="solid", bd=1,
        )
        self._entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self._entry.bind("<Return>", self._on_submit)
        self._entry.focus_set()

        hint = (
            "scene <text> | choice <text> | seal [node|choice|item] <label> | "
            "all <text> | samples | scenes | grid | clear | save"
        )
        tk.Label(root, text=hint, bg=BG, fg=FG_DIM,
                 font=("Courier", 8), wraplength=900, justify="left").pack(
            anchor="w", padx=10, pady=(0, 8))

        self._log_history: list[str] = []
        self._run_command("grid")

    def _set_status(self, text: str):
        self._status.configure(text=text)

    def _clear_canvas(self):
        self._canvas.delete("all")
        self._photos.clear()

    def _show_photo(self, photo: tk.PhotoImage, caption: str = ""):
        self._clear_canvas()
        self._photos.append(photo)
        cw = max(self._canvas.winfo_width(), 400)
        ch = max(self._canvas.winfo_height(), 400)
        x = cw // 2
        y = ch // 2
        self._canvas.create_image(x, y, image=photo, anchor="center")
        if caption:
            self._canvas.create_text(
                8, 8, text=caption, anchor="nw", fill=FG,
                font=("Courier", 9),
            )

    def _show_row(self, items: list[tuple[str, tk.PhotoImage]], caption: str = ""):
        self._clear_canvas()
        if not items:
            return
        gap = 12
        total_w = sum(p.width() for _, p in items) + gap * (len(items) - 1)
        max_h = max(p.height() for _, p in items)
        cw = max(self._canvas.winfo_width(), total_w + 40)
        ch = max(self._canvas.winfo_height(), max_h + 60)
        x = (cw - total_w) // 2
        y = (ch - max_h) // 2 + 10
        for label, photo in items:
            self._photos.append(photo)
            self._canvas.create_image(x + photo.width() // 2, y + photo.height() // 2,
                                        image=photo, anchor="center")
            self._canvas.create_text(
                x + photo.width() // 2, y + photo.height() + 14,
                text=label, fill=FG, font=("Courier", 8),
            )
            x += photo.width() + gap
        if caption:
            self._canvas.create_text(8, 8, text=caption, anchor="nw", fill=FG,
                                     font=("Courier", 9))

    def _on_submit(self, _event=None):
        line = self._entry.get().strip()
        if not line:
            return
        self._entry.delete(0, "end")
        self._run_command(line)

    def _run_command(self, line: str):
        t0 = time.perf_counter()
        self._log_history.append(line)
        try:
            msg = self._dispatch(line)
        except Exception as exc:
            msg = f"Error: {type(exc).__name__}: {exc}"
        elapsed_ms = (time.perf_counter() - t0) * 1000
        self._set_status(f"{msg}  ({elapsed_ms:.0f} ms)")

    def _dispatch(self, line: str) -> str:
        lower = line.lower()
        if lower in ("help", "?"):
            return (
                "scene <text> | choice <text> | seal [variant] <label> | "
                "all <text> | samples | scenes | grid | clear | save [file]"
            )
        if lower == "clear":
            _scene_cache.clear()
            _choice_cache.clear()
            _seal_cache.clear()
            return "Caches cleared."
        if lower == "samples":
            variant, label = SEAL_SAMPLES[self._sample_idx % len(SEAL_SAMPLES)]
            self._sample_idx += 1
            return self._render_seal(variant, label)
        if lower == "scenes":
            text = SCENE_SAMPLES[self._scene_idx % len(SCENE_SAMPLES)]
            self._scene_idx += 1
            return self._render_scene(text)
        if lower == "grid":
            return self._render_seal_grid()
        if lower.startswith("save"):
            return self._save_current(line)

        if lower.startswith("scene "):
            return self._render_scene(line[6:].strip())
        if lower.startswith("choice "):
            return self._render_choice(line[7:].strip())
        if lower.startswith("seal "):
            return self._parse_seal(line[5:].strip())
        if lower.startswith("all "):
            return self._render_all(line[4:].strip())

        if line and " " not in line:
            return self._render_seal("node", line)
        return self._render_scene(line)

    def _parse_seal(self, rest: str) -> str:
        parts = rest.split(None, 1)
        if len(parts) == 1:
            return self._render_seal("node", parts[0])
        variant, label = parts[0].lower(), parts[1]
        if variant not in ("node", "choice", "item"):
            return self._render_seal("node", rest)
        return self._render_seal(variant, label)

    def _render_scene(self, text: str) -> str:
        photo = generate_scene_image(text, ink=INK, paper=PAPER)
        self._current_pil = generate_scene_pil_image(text, zoom=1)
        self._current_label = f"scene: {text[:60]}"
        self.root.after_idle(lambda: self._show_photo(photo, self._current_label))
        return f"Scene — {text!r}"

    def _render_choice(self, text: str) -> str:
        photo = generate_choice_image(text, ink=INK, paper=PAPER)
        self._current_pil = None
        self._current_label = f"choice: {text}"
        self.root.after_idle(lambda: self._show_photo(photo, self._current_label))
        return f"Choice — {text!r}"

    def _render_seal(self, variant: str, label: str) -> str:
        photo = generate_seal_image(label, variant=variant, zoom=2, ink=INK, paper=PAPER)
        self._current_pil = generate_seal_pil_image(label, variant=variant, zoom=1)
        self._current_label = f"seal/{variant}: {label}"
        self.root.after_idle(lambda: self._show_photo(photo, self._current_label))
        return f"Seal [{variant}] — {label!r}"

    def _render_all(self, text: str) -> str:
        scene = generate_scene_image(text, ink=INK, paper=PAPER)
        choice = generate_choice_image(text, ink=INK, paper=PAPER)
        seal = generate_seal_image(text, variant="node", zoom=2, ink=INK, paper=PAPER)
        self._current_pil = generate_scene_pil_image(text, zoom=1)
        self._current_label = f"all: {text[:50]}"
        items = [("scene", scene), ("choice", choice), ("seal", seal)]
        self.root.after_idle(
            lambda: self._show_row(items, caption=self._current_label))
        return f"All three — {text!r}"

    def _render_seal_grid(self) -> str:
        cols = 3
        tile = generate_seal_pil_image("grid", variant="node", zoom=2)
        w, h = tile.size
        from PIL import Image
        rows = (len(SEAL_SAMPLES) + cols - 1) // cols
        sheet = Image.new("L", (w * cols, h * rows), 255)
        for i, (variant, label) in enumerate(SEAL_SAMPLES):
            tile = generate_seal_pil_image(label, variant=variant, zoom=2)
            r, c = divmod(i, cols)
            sheet.paste(tile, (c * w, r * h))
        self._current_pil = sheet
        self._current_label = "seal grid"
        photo = tk.PhotoImage(width=sheet.width, height=sheet.height)
        rows_data = []
        for y in range(sheet.height):
            row_colors = ["#0f0f0c" if sheet.getpixel((x, y)) < 128 else "#dcdcd0"
                          for x in range(sheet.width)]
            rows_data.append("{" + " ".join(row_colors) + "}")
        photo.put(" ".join(rows_data))
        self.root.after_idle(lambda: self._show_photo(photo, self._current_label))
        return f"Seal grid ({len(SEAL_SAMPLES)} samples)"

    def _save_current(self, line: str) -> str:
        if self._current_pil is None:
            return "Nothing to save — render a scene or seal first."
        parts = line.split(None, 1)
        if len(parts) > 1:
            path = Path(parts[1])
        else:
            safe = self._current_label.replace("/", "_").replace(":", "")[:40]
            safe = safe.replace(" ", "_") or "output"
            path = Path("seals_preview") / f"playground_{safe}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._current_pil.save(path)
        return f"Saved {path}"


def main():
    root = tk.Tk()
    ImageGenPlayground(root)
    root.mainloop()


if __name__ == "__main__":
    main()
