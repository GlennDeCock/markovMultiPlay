"""Load and scale UI element PNGs for the player window."""

from pathlib import Path

from PIL import Image, ImageTk

UI_DIR = Path(__file__).resolve().parent / "UI_Elements"

_cache: dict[tuple, object] = {}


def load_ui_photo(name: str, width: int, height: int):
    key = (name, width, height)
    if key in _cache:
        return _cache[key]
    path = UI_DIR / name
    img = Image.open(path).convert("RGBA")
    img = img.resize((width, height), Image.Resampling.LANCZOS)
    photo = ImageTk.PhotoImage(img)
    _cache[key] = photo
    return photo
