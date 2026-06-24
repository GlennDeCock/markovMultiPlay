"""
Export sample gothic seals as PNG for visual review.

Run from project root:
    python scripts/export_seals.py
    python scripts/export_seals.py --out seals_preview
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from image_gen import generate_seal_pil_image

SAMPLES = [
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Export gothic seal PNG samples")
    parser.add_argument("--out", default="seals_preview", help="output directory")
    parser.add_argument("--size", type=int, default=140, help="grid size before zoom")
    parser.add_argument("--zoom", type=int, default=2, help="nearest-neighbor upscale")
    args = parser.parse_args()

    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    for variant, label in SAMPLES:
        img = generate_seal_pil_image(label, size=args.size, variant=variant, zoom=args.zoom)
        safe = label.replace(" ", "_")[:40]
        path = out_dir / f"{variant}_{safe}.png"
        img.save(path)
        print(path.relative_to(ROOT))

    struct_dir = out_dir / "structures"
    struct_dir.mkdir(exist_ok=True)
    from image_gen import _SEAL_STRUCTURES, _hash_val
    found = {}
    probe = 0
    while len(found) < len(_SEAL_STRUCTURES) and probe < 5000:
        label = f"probe_{probe}"
        seed = hash(label) & 0xFFFF_FFFF
        idx = int(_hash_val(8, 8, seed) * len(_SEAL_STRUCTURES)) % len(_SEAL_STRUCTURES)
        if idx not in found:
            found[idx] = label
            img = generate_seal_pil_image(label, size=args.size, variant="node", zoom=args.zoom)
            name = _SEAL_STRUCTURES[idx].__name__.replace("_seal_struct_", "")
            img.save(struct_dir / f"{idx}_{name}.png")
            print((struct_dir / f"{idx}_{name}.png").relative_to(ROOT))
        probe += 1

    grid_path = out_dir / "_grid.png"
    cols = 3
    w, h = generate_seal_pil_image("grid", size=args.size, variant="node", zoom=args.zoom).size
    from PIL import Image
    sheet = Image.new("1", (w * cols, h * ((len(SAMPLES) + cols - 1) // cols)), 1)
    for i, (variant, label) in enumerate(SAMPLES):
        tile = generate_seal_pil_image(label, size=args.size, variant=variant, zoom=args.zoom)
        row, col = divmod(i, cols)
        sheet.paste(tile, (col * w, row * h))
    sheet.save(grid_path)
    print(grid_path.relative_to(ROOT))


if __name__ == "__main__":
    main()
