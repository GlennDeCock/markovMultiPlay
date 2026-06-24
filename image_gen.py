"""
image_gen.py — Scene image generator.
100×100 pixel grid, ZOOM=3 → 300×300 display.
Shapes rendered as silhouette-biased noise-warped density blobs,
dithered with a 4×4 Bayer matrix onto the layered-noise background.
"""

import tkinter as tk

# ---------------------------------------------------------------------------
# Grid constants
# ---------------------------------------------------------------------------
# Render at half resolution and upscale 2× — ~4× fewer noise samples (faster)
# and chunkier, more defined e-ink pixels with naturally larger paper holes.
COLS    = 280
ROWS    = 280
ZOOM    = 1
HORIZON = 168  # row index where ground meets sky (≈0.6 × ROWS)
_GS     = COLS / 140.0   # grid scale factor — keeps visual proportions when grid doubles

# ---------------------------------------------------------------------------
# Bayer 4×4 ordered dither matrix  (values 0..1)
# ---------------------------------------------------------------------------
_B4 = [
    [v / 16 for v in row] for row in
    [[0, 8, 2, 10],
     [12, 4, 14, 6],
     [3, 11, 1, 9],
     [15, 7, 13, 5]]
]

# ===========================================================================
# Hash / noise
# ===========================================================================

def _hash_val(xi: int, yi: int, seed: int) -> float:
    h = (xi * 1_619 + yi * 31_337 + seed * 6_971) & 0xFFFF_FFFF
    h = ((h >> 16) ^ h) * 0x45d9f3b & 0xFFFF_FFFF
    h = ((h >> 16) ^ h) & 0xFFFF
    return h / 0xFFFF


def _value_noise(x: float, y: float, seed: int) -> float:
    x0, y0 = int(x), int(y)
    tx, ty = x - x0, y - y0
    v00 = _hash_val(x0,     y0,     seed)
    v10 = _hash_val(x0 + 1, y0,     seed)
    v01 = _hash_val(x0,     y0 + 1, seed)
    v11 = _hash_val(x0 + 1, y0 + 1, seed)
    v0  = v00 + tx * (v10 - v00)
    v1  = v01 + tx * (v11 - v01)
    return v0 + ty * (v1 - v0)


def _layered_noise(seed: int) -> list[list[float]]:
    hmap = [[0.0] * COLS for _ in range(ROWS)]
    octaves = [(0.035, 0.55, 0), (0.085, 0.30, 13337), (0.19, 0.15, 99991)]
    for freq, amp, s_off in octaves:
        for r in range(ROWS):
            for c in range(COLS):
                hmap[r][c] += _value_noise(c * freq, r * freq, seed + s_off) * amp
    # top-light gradient
    for r in range(ROWS):
        sky = 0.18 * (1.0 - r / ROWS)
        for c in range(COLS):
            hmap[r][c] += sky
    flat = [hmap[r][c] for r in range(ROWS) for c in range(COLS)]
    lo, hi = min(flat), max(flat)
    span = hi - lo or 1.0
    for r in range(ROWS):
        for c in range(COLS):
            v = (hmap[r][c] - lo) / span
            hmap[r][c] = v * v * (3 - 2 * v)
    return hmap


# ===========================================================================
# Dithering + render
# ===========================================================================

def _apply_contrast(hmap, k: float) -> None:
    """Push values away from mid-grey so silhouettes read as more defined
    ink/paper edges.  Keeps 0 and 1 anchored; k>1 sharpens."""
    for r in range(ROWS):
        row = hmap[r]
        for c in range(COLS):
            v = 0.5 + (row[c] - 0.5) * k
            row[c] = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


# Values at or above this become pure paper before dither (clean sky / margins).
_PAPER_SNAP = 0.90
_INK_SNAP = 0.10


def _dither(hmap):
    grid = [[False] * COLS for _ in range(ROWS)]
    for r in range(ROWS):
        for c in range(COLS):
            grid[r][c] = hmap[r][c] < _B4[r % 4][c % 4]
    return grid


def _to_photoimage(grid, ink, paper, zoom: int = 1):
    rows = len(grid)
    cols = len(grid[0]) if rows else COLS
    rows_data = []
    for row in grid:
        row_colors = [ink if cell else paper for cell in row]
        rows_data.append("{" + " ".join(row_colors) + "}")
    img = tk.PhotoImage(width=cols, height=rows)
    img.put(" ".join(rows_data))
    return img if zoom == 1 else img.zoom(zoom)


def _parse_hex(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _lerp_hex(t: float, ink: str, paper: str) -> str:
    t = max(0.0, min(1.0, t))
    ir, ig, ib = _parse_hex(ink)
    pr, pg, pb = _parse_hex(paper)
    r = int(ir + (pr - ir) * t)
    g = int(ig + (pg - ig) * t)
    b = int(ib + (pb - ib) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _hmap_to_pil_image(hmap) -> "Image":
    from PIL import Image as PILImage
    grid = _dither_diffusion_hmap(hmap)
    rows, cols = _hmap_dims(hmap)
    img = PILImage.new("1", (cols, rows), 1)
    px = img.load()
    for r in range(rows):
        for c in range(cols):
            if grid[r][c]:
                px[c, r] = 0
    return img


def _landscape_photoimage(
    seed: int,
    grid_w: int,
    grid_h: int,
    zoom: int,
    ink: str,
    paper: str,
) -> "tk.PhotoImage":
    hmap = _new_hmap_rect(grid_h, grid_w, 1.0)
    _compose_faded_cityscape(hmap, seed)
    _apply_contrast_on(hmap, 1.08)
    grid = _dither_diffusion_hmap(hmap)
    return _to_photoimage(grid, ink, paper, zoom=zoom)


# ===========================================================================
# Blob drawing
# ===========================================================================

def _draw_blob(hmap, cx, cy, seed,
               w=12, h=12, strength=0.85,
               noise_warp=4.0, noise_seed_off=0):
    """
    Paint a density cloud into hmap centred at (cy, cx).
    w, h   — half-axes of the ellipse in grid cells
    strength — how dark the core gets (0=black, 1=paper)
    noise_warp — how much value noise warps the boundary (0 = smooth ellipse)
    """
    rows = len(hmap)
    cols = len(hmap[0]) if rows else COLS
    gs = cols / 140.0
    _nw = noise_warp * gs
    r1 = max(0,    cy - h - int(_nw) - 1)
    r2 = min(rows, cy + h + int(_nw) + 2)
    c1 = max(0,    cx - w - int(_nw) - 1)
    c2 = min(cols, cx + w + int(_nw) + 2)

    ns = seed ^ noise_seed_off
    for r in range(r1, r2):
        for c in range(c1, c2):
            # warp the sample point with low-freq noise
            warp_r = (_value_noise(c * 0.09, r * 0.09, ns)          - 0.5) * _nw
            warp_c = (_value_noise(c * 0.09, r * 0.09, ns ^ 0x9E37) - 0.5) * _nw
            sr = r + warp_r - cy
            sc = c + warp_c - cx
            # elliptical distance
            d = ((sc / w) ** 2 + (sr / h) ** 2) ** 0.5
            if d >= 1.0:
                continue
            # smooth falloff: 1 at centre → 0 at edge
            density = (1.0 - d) ** 1.6
            target  = 1.0 - density * strength
            if target < hmap[r][c]:
                hmap[r][c] = target


def _draw_wide_band(hmap, cy, seed, band_h=6, strength=0.55):
    """A full-width flat band (ground, water, street, etc.)."""
    _bh = int(band_h * _GS)
    for r in range(max(0, cy - _bh), min(ROWS, cy + _bh + 1)):
        rel = abs(r - cy) / (_bh or 1)
        density = (1.0 - rel) ** 1.4
        for c in range(COLS):
            noise = _value_noise(c * 0.125, r * 0.125, seed) * 0.15
            target = 1.0 - density * strength + noise
            if target < hmap[r][c]:
                hmap[r][c] = target


# ===========================================================================
# Per-type shape wrappers
# ===========================================================================
# Each function: (hmap, cx, cy, seed, scale=1.0)
# Sizes are in grid cells; scale comes from _role_position.

def _s_building(hmap, cx, cy, seed, scale=1.0):
    w = max(4, int(14 * scale))
    h = max(6, int(20 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.92, noise_warp=3.0)

def _s_tower(hmap, cx, cy, seed, scale=1.0):
    w = max(3, int(6 * scale))
    h = max(8, int(24 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.90, noise_warp=2.5)

def _s_wall(hmap, cx, cy, seed, scale=1.0):
    w = max(6, int(22 * scale))
    h = max(3, int(5 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.80, noise_warp=3.5)

def _s_arch(hmap, cx, cy, seed, scale=1.0):
    w = max(5, int(10 * scale))
    h = max(5, int(12 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.85, noise_warp=3.0)

def _s_corridor(hmap, cx, cy, seed, scale=1.0):
    # wide shallow band suggesting a corridor receding
    _draw_wide_band(hmap, cy, seed, band_h=int(8 * scale), strength=0.60)
    w = max(4, int(8 * scale))
    h = max(4, int(8 * scale))
    _draw_blob(hmap, cx, cy, seed ^ 0xAB, w=w, h=h, strength=0.70, noise_warp=4.0)

def _s_room(hmap, cx, cy, seed, scale=1.0):
    w = max(8, int(18 * scale))
    h = max(5, int(10 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.70, noise_warp=5.0)

def _s_courtyard(hmap, cx, cy, seed, scale=1.0):
    w = max(10, int(20 * scale))
    h = max(6, int(12 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.60, noise_warp=6.0)

def _s_sky(hmap, cx, cy, seed, scale=1.0):
    # light wide diffuse band high up
    _draw_wide_band(hmap, HORIZON // 3, seed, band_h=int(14 * scale), strength=0.25)

def _s_parking(hmap, cx, cy, seed, scale=1.0):
    _draw_wide_band(hmap, cy, seed, band_h=int(6 * scale), strength=0.45)

def _s_marquee(hmap, cx, cy, seed, scale=1.0):
    w = max(10, int(18 * scale))
    h = max(3, int(6 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.88, noise_warp=2.0)

def _s_fire_escape(hmap, cx, cy, seed, scale=1.0):
    w = max(3, int(5 * scale))
    h = max(8, int(16 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.82, noise_warp=3.0)

def _s_stairs(hmap, cx, cy, seed, scale=1.0):
    w = max(6, int(14 * scale))
    h = max(4, int(8 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.78, noise_warp=4.0)

def _s_statue(hmap, cx, cy, seed, scale=1.0):
    # tall narrow upright
    w = max(3, int(5 * scale))
    h = max(6, int(13 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.88, noise_warp=3.0)
    # plinth
    _draw_blob(hmap, cx, cy + int(10 * scale), seed ^ 0x11,
               w=max(4, int(7 * scale)), h=max(2, int(3 * scale)),
               strength=0.80, noise_warp=2.0)

def _s_tree(hmap, cx, cy, seed, scale=1.0):
    # crown — round, offset upward
    crown_h = max(5, int(10 * scale))
    crown_w = max(5, int(9 * scale))
    crown_cy = cy - int(8 * scale)
    _draw_blob(hmap, cx, crown_cy, seed, w=crown_w, h=crown_h,
               strength=0.86, noise_warp=5.5)
    # trunk — narrow tall below crown
    _draw_blob(hmap, cx, cy + int(2 * scale), seed ^ 0xFF,
               w=max(2, int(2 * scale)), h=max(4, int(7 * scale)),
               strength=0.90, noise_warp=2.0)

def _s_fence(hmap, cx, cy, seed, scale=1.0):
    w = max(10, int(20 * scale))
    h = max(2, int(4 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.82, noise_warp=3.0)

def _s_bench(hmap, cx, cy, seed, scale=1.0):
    w = max(7, int(12 * scale))
    h = max(2, int(4 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.80, noise_warp=2.5)

def _s_chair(hmap, cx, cy, seed, scale=1.0):
    w = max(4, int(7 * scale))
    h = max(4, int(8 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.80, noise_warp=3.0)

def _s_table(hmap, cx, cy, seed, scale=1.0):
    w = max(8, int(14 * scale))
    h = max(2, int(4 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.78, noise_warp=2.5)

def _s_bicycle(hmap, cx, cy, seed, scale=1.0):
    w = max(8, int(14 * scale))
    h = max(4, int(7 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.84, noise_warp=3.5)

def _s_fountain(hmap, cx, cy, seed, scale=1.0):
    # basin — wide flat
    _draw_blob(hmap, cx, cy, seed,
               w=max(8, int(12 * scale)), h=max(3, int(4 * scale)),
               strength=0.80, noise_warp=3.0)
    # spray — diffuse upward cloud
    _draw_blob(hmap, cx, cy - int(8 * scale), seed ^ 0x55,
               w=max(5, int(8 * scale)), h=max(6, int(10 * scale)),
               strength=0.45, noise_warp=7.0)

def _s_water(hmap, cx, cy, seed, scale=1.0):
    _draw_wide_band(hmap, cy, seed, band_h=int(5 * scale), strength=0.50)

def _s_street(hmap, cx, cy, seed, scale=1.0):
    _draw_wide_band(hmap, cy, seed, band_h=int(6 * scale), strength=0.40)

def _s_traffic(hmap, cx, cy, seed, scale=1.0):
    # boxy wide low shape
    w = max(8, int(13 * scale))
    h = max(4, int(6 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.86, noise_warp=2.5)

def _s_sign(hmap, cx, cy, seed, scale=1.0):
    w = max(6, int(9 * scale))
    h = max(4, int(6 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.88, noise_warp=2.0)
    # pole
    _draw_blob(hmap, cx, cy + int(5 * scale), seed ^ 0x33,
               w=max(1, int(1 * scale)), h=max(4, int(6 * scale)),
               strength=0.88, noise_warp=1.5)

def _s_shadow(hmap, cx, cy, seed, scale=1.0):
    w = max(8, int(16 * scale))
    h = max(2, int(3 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.40, noise_warp=5.0)

def _s_clock(hmap, cx, cy, seed, scale=1.0):
    w = max(4, int(6 * scale))
    h = max(4, int(6 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.88, noise_warp=2.0)
    # post
    _draw_blob(hmap, cx, cy + int(6 * scale), seed ^ 0x44,
               w=1, h=max(4, int(6 * scale)), strength=0.90, noise_warp=1.0)

def _s_lamp(hmap, cx, cy, seed, scale=1.0):
    # head
    _draw_blob(hmap, cx, cy - int(6 * scale), seed,
               w=max(3, int(4 * scale)), h=max(3, int(4 * scale)),
               strength=0.88, noise_warp=2.5)
    # post
    _draw_blob(hmap, cx, cy, seed ^ 0x22,
               w=1, h=max(5, int(8 * scale)), strength=0.90, noise_warp=1.5)

def _s_hook(hmap, cx, cy, seed, scale=1.0):
    w = max(3, int(4 * scale))
    h = max(3, int(5 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.85, noise_warp=2.5)

def _s_pipe(hmap, cx, cy, seed, scale=1.0):
    w = max(1, int(2 * scale))
    h = max(7, int(14 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.88, noise_warp=2.0)

def _s_door(hmap, cx, cy, seed, scale=1.0):
    w = max(4, int(6 * scale))
    h = max(7, int(11 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.88, noise_warp=2.5)

def _s_window(hmap, cx, cy, seed, scale=1.0):
    w = max(4, int(6 * scale))
    h = max(4, int(7 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.85, noise_warp=2.5)

def _s_vending(hmap, cx, cy, seed, scale=1.0):
    w = max(4, int(6 * scale))
    h = max(7, int(11 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.90, noise_warp=2.0)

def _s_phone_box(hmap, cx, cy, seed, scale=1.0):
    w = max(4, int(6 * scale))
    h = max(7, int(12 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.90, noise_warp=2.0)

def _s_elevator(hmap, cx, cy, seed, scale=1.0):
    w = max(5, int(8 * scale))
    h = max(8, int(14 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.90, noise_warp=2.0)

def _s_key(hmap, cx, cy, seed, scale=1.0):
    w = max(3, int(5 * scale))
    h = max(2, int(3 * scale))
    _draw_blob(hmap, cx, cy, seed, w=w, h=h, strength=0.88, noise_warp=2.0)


# ===========================================================================
# Fallback motifs (when no keyword matches)
# ===========================================================================

_FALLBACKS = [
    lambda hmap, seed: _draw_blob(hmap, COLS//2, ROWS//3, seed,
                                   w=28, h=40, strength=0.88, noise_warp=4.0),
    lambda hmap, seed: _draw_blob(hmap, COLS//2, HORIZON-12, seed,
                                   w=20, h=20, strength=0.80, noise_warp=5.0),
    lambda hmap, seed: _draw_wide_band(hmap, HORIZON, seed,
                                        band_h=8, strength=0.55),
    lambda hmap, seed: _draw_blob(hmap, COLS//3, HORIZON-8, seed,
                                   w=16, h=28, strength=0.85, noise_warp=4.5),
    lambda hmap, seed: _draw_blob(hmap, COLS*2//3, HORIZON-8, seed ^ 0xAB,
                                   w=12, h=36, strength=0.88, noise_warp=3.5),
    lambda hmap, seed: _draw_blob(hmap, COLS//2, HORIZON+12, seed,
                                   w=32, h=10, strength=0.60, noise_warp=6.0),
    lambda hmap, seed: _draw_blob(hmap, COLS//2, HORIZON-4, seed,
                                   w=40, h=16, strength=0.72, noise_warp=5.0),
    lambda hmap, seed: _draw_blob(hmap, COLS//2, ROWS*2//5, seed,
                                   w=24, h=44, strength=0.90, noise_warp=4.0),
]


def _stamp_fallback(hmap, seed):
    idx = seed % len(_FALLBACKS)
    _FALLBACKS[idx](hmap, seed)
    # add a ground band for context
    _draw_wide_band(hmap, HORIZON, seed ^ 0xFF, band_h=5, strength=0.45)


# ===========================================================================
# Shape dispatch table
# ===========================================================================

_DRAW: dict = {
    "building":   _s_building,
    "tower":      _s_tower,
    "wall":       _s_wall,
    "arch":       _s_arch,
    "corridor":   _s_corridor,
    "room":       _s_room,
    "courtyard":  _s_courtyard,
    "sky":        _s_sky,
    "parking":    _s_parking,
    "marquee":    _s_marquee,
    "fire_escape":_s_fire_escape,
    "stairs":     _s_stairs,
    "statue":     _s_statue,
    "figure":     _s_statue,
    "tree":       _s_tree,
    "fence":      _s_fence,
    "bench":      _s_bench,
    "chair":      _s_chair,
    "table":      _s_table,
    "bicycle":    _s_bicycle,
    "fountain":   _s_fountain,
    "water":      _s_water,
    "street":     _s_street,
    "traffic":    _s_traffic,
    "sign":       _s_sign,
    "shadow":     _s_shadow,
    "clock":      _s_clock,
    "lamp":       _s_lamp,
    "hook":       _s_hook,
    "pipe":       _s_pipe,
    "door":       _s_door,
    "window":     _s_window,
    "vending":    _s_vending,
    "phone_box":  _s_phone_box,
    "elevator":   _s_elevator,
    "key":        _s_key,
}

# ===========================================================================
# Keyword → shape tag
# ===========================================================================

_KW: dict[str, tuple[str, str]] = {
    "building": ("building", "bg"), "buildings": ("building", "bg"),
    "tower":    ("tower",    "bg"), "towers":    ("tower",    "bg"),
    "wall":     ("wall",     "bg"), "walls":     ("wall",     "bg"),
    "arch":     ("arch",     "bg"), "bridge":    ("arch",     "bg"),
    "corridor": ("corridor", "bg"), "hallway":   ("corridor", "bg"),
    "hall":     ("corridor", "bg"),
    "room":     ("room",     "bg"), "chamber":   ("room",     "bg"),
    "courtyard":("courtyard","bg"), "square":    ("courtyard","bg"),
    "sky":      ("sky",      "bg"), "cloud":     ("sky",      "bg"),
    "clouds":   ("sky",      "bg"),
    "parking":  ("parking",  "bg"), "garage":    ("parking",  "bg"),
    "cinema":   ("marquee",  "bg"), "marquee":   ("marquee",  "bg"),
    "fire":     ("fire_escape","bg"),

    "stairs":   ("stairs",   "mg"), "stair":     ("stairs",   "mg"),
    "steps":    ("stairs",   "mg"), "step":      ("stairs",   "mg"),
    "statue":   ("statue",   "mg"), "monument":  ("statue",   "mg"),
    "tree":     ("tree",     "mg"), "trees":     ("tree",     "mg"),
    "branch":   ("tree",     "mg"), "branches":  ("tree",     "mg"),
    "fence":    ("fence",    "mg"), "railing":   ("fence",    "mg"),
    "railings": ("fence",    "mg"),
    "bench":    ("bench",    "mg"), "benches":   ("bench",    "mg"),
    "chair":    ("chair",    "mg"), "chairs":    ("chair",    "mg"),
    "table":    ("table",    "mg"), "desk":      ("table",    "mg"),
    "bicycle":  ("bicycle",  "mg"), "bike":      ("bicycle",  "mg"),
    "bikes":    ("bicycle",  "mg"),
    "fountain": ("fountain", "mg"),
    "water":    ("water",    "mg"), "river":     ("water",    "mg"),
    "canal":    ("water",    "mg"), "puddle":    ("water",    "mg"),
    "street":   ("street",   "mg"), "road":      ("street",   "mg"),
    "avenue":   ("street",   "mg"), "pavement":  ("street",   "mg"),
    "pedestrian":("statue",  "mg"), "pedestrians":("statue",  "mg"),
    "person":   ("statue",   "mg"), "people":    ("statue",   "mg"),
    "crowd":    ("statue",   "mg"), "figure":    ("statue",   "mg"),
    "traffic":  ("traffic",  "mg"), "car":       ("traffic",  "mg"),
    "cars":     ("traffic",  "mg"),
    "elevator": ("elevator", "mg"), "lift":      ("elevator", "mg"),
    "map":      ("sign",     "mg"),
    "sign":     ("sign",     "mg"), "signs":     ("sign",     "mg"),
    "notice":   ("sign",     "mg"), "schedule":  ("sign",     "mg"),
    "board":    ("sign",     "mg"),
    "shadow":   ("shadow",   "mg"), "shadows":   ("shadow",   "mg"),

    "clock":    ("clock",    "fg"), "clocks":    ("clock",    "fg"),
    "watch":    ("clock",    "fg"),
    "key":      ("key",      "fg"), "keys":      ("key",      "fg"),
    "lamp":     ("lamp",     "fg"), "lamps":     ("lamp",     "fg"),
    "lantern":  ("lamp",     "fg"),
    "light":    ("lamp",     "fg"), "lights":    ("lamp",     "fg"),
    "hook":     ("hook",     "fg"),
    "pipe":     ("pipe",     "fg"), "pipes":     ("pipe",     "fg"),
    "wire":     ("pipe",     "fg"), "wires":     ("pipe",     "fg"),
    "door":     ("door",     "fg"), "doors":     ("door",     "fg"),
    "doorway":  ("door",     "fg"),
    "window":   ("window",   "fg"), "windows":   ("window",   "fg"),
    "vending":  ("vending",  "fg"),
    "phone":    ("phone_box","fg"),
}


# ===========================================================================
# Scene composition
# ===========================================================================

def _draw_shapes(hmap, text, seed):
    found: list[tuple[str, str]] = []
    seen_tags: set[str] = set()
    for word in text.split():
        word = word.strip(".,;:!?\"'()-")
        entry = _KW.get(word)
        if entry and entry[0] not in seen_tags:
            found.append(entry)
            seen_tags.add(entry[0])
        if len(found) == 5:
            break

    if not found:
        _stamp_fallback(hmap, seed)
        return

    if len(found) > 1:
        r = (seed >> 8) & 0xFF
        for i in range(len(found) - 1, 0, -1):
            j = (r + i * 37) % (i + 1)
            found[i], found[j] = found[j], found[i]
        order = {"bg": 0, "mg": 1, "fg": 2}
        found.sort(key=lambda x: order[x[1]])

    found = found[:3]

    tags_present = {t for t, _ in found}
    if tags_present & {"street", "courtyard", "parking", "traffic",
                       "bicycle", "fountain", "statue", "bench", "fence", "tree"}:
        _draw_wide_band(hmap, HORIZON, seed ^ 0xBB, band_h=5, strength=0.45)

    for i, (tag, role) in enumerate(found):
        shape_seed = (seed ^ (i * 0x9E3779B9 + hash(tag))) & 0xFFFF_FFFF
        cx, cy, scale = _role_position(role, i, len(found), seed, i)
        _DRAW[tag](hmap, cx, cy, shape_seed, scale)


def _role_position(role, idx, total, seed, slot):
    jx = int((_hash_val(slot, 0, seed ^ 0x1111) - 0.5) * 48)
    jy = int((_hash_val(0, slot, seed ^ 0x2222) - 0.5) * 20)

    if role == "bg":
        cx = COLS // 2 + jx // 2
        cy = ROWS * 2 // 5 + jy // 2
        scale = 2.6 + _hash_val(slot, slot, seed) * 0.6
    elif role == "mg":
        base_x = [COLS // 3, COLS * 2 // 3, COLS // 2]
        cx = base_x[slot % 3] + jx
        cy = HORIZON - 8 + jy // 2
        scale = 1.7 + _hash_val(slot, slot + 1, seed) * 0.5
    else:
        base_x = [COLS // 4, COLS * 3 // 4, COLS // 2]
        cx = base_x[slot % 3] + jx
        cy = HORIZON + 10 + abs(jy) // 2
        scale = 1.3 + _hash_val(slot, slot + 2, seed) * 0.4

    cx = max(24, min(COLS - 24, cx))
    cy = max(12,  min(ROWS - 16, cy))
    return cx, cy, scale


# ===========================================================================
# Organic edge mask
# ===========================================================================

# Fraction of the half-diagonal at which the scene is still fully shown.
# Beyond this it fades to paper.  Values < 1.0 = inner radius, > 1.0 = outer.
EDGE_INNER    = 0.40   # scene fully opaque inside this normalised radius
EDGE_OUTER    = 0.90   # scene fully dissolved to paper outside this radius
EDGE_WARP     = 0.38   # how much low-freq noise warps the boundary (0 = perfect ellipse)
# Spikes point to the 4 canvas corners → perspective/room-edge illusion.
# SPIKE_REACH extends them to or past the canvas boundary.
SPIKE_REACH   = 0.70   # how far beyond EDGE_OUTER spikes extend (in normalised units)
SPIKE_WIDTH   = 0.09   # angular half-width of each spike (radians) — wider = softer room edge
HORIZON_WIDTH = 0.30   # angular half-width of horizon-mode spikes (wide → reads as a horizon)
BLOB_COUNT    = 2      # number of loose scatter blobs outside the main shape
BLOB_RADIUS   = 0.18   # normalised radius of each scatter blob (bigger = larger paper holes)
BLOB_ZONE_MIN = 0.5   # scatter blobs start at this distance from centre
BLOB_ZONE_MAX = 0.8   # and extend to this distance


def _apply_organic_mask(hmap: list[list[float]], seed: int) -> None:
    """Push edge cells toward paper using a noise-warped elliptical falloff.

    Also carves long thin spikes reaching outward from the boundary and
    plants small loose ink blobs scattered around the outside.
    """
    import math

    cx = COLS / 2.0
    cy = ROWS / 2.0

    mask_seed = seed ^ 0xD1CE_FA11

    # Spike layout has two seeded modes:
    #   • "room"    — 4 spikes toward the canvas corners → perspective room/space
    #   • "horizon" — 2 wide spikes left & right → a horizontal opening / horizon
    # ~1 in 3 scenes use the horizon layout.
    mode_roll = _hash_val(7, 7, mask_seed ^ 0x5EED)
    spikes = []   # list of (angle, half_width)
    if mode_roll < 0.34:
        for i, base_angle in enumerate([0.0, math.pi]):
            jitter = (_hash_val(i, 9, mask_seed ^ 0xABCD) - 0.5) * 0.12
            spikes.append((base_angle + jitter, HORIZON_WIDTH))
    else:
        for i, base_angle in enumerate([math.pi * 0.25, math.pi * 0.75,
                                         math.pi * 1.25, math.pi * 1.75]):
            jitter = (_hash_val(i, 0, mask_seed ^ 0xABCD) - 0.5) * 0.18
            spikes.append((base_angle + jitter, SPIKE_WIDTH))

    # --- Build scatter blob centres (in normalised dx/dy space) ---
    scatter_blobs = []
    for i in range(BLOB_COUNT):
        angle  = _hash_val(i, 1, mask_seed ^ 0x1234) * 2 * math.pi
        radius = (BLOB_ZONE_MIN
                  + _hash_val(i, 2, mask_seed ^ 0x5678)
                  * (BLOB_ZONE_MAX - BLOB_ZONE_MIN))
        bx = math.cos(angle) * radius
        by = math.sin(angle) * radius
        # blob strength: darker blobs look more like detached ink flecks
        strength = 0.3 + _hash_val(i, 3, mask_seed ^ 0x9ABC) * 0.4
        scatter_blobs.append((bx, by, BLOB_RADIUS, strength))

    for r in range(ROWS):
        for c in range(COLS):
            dx = (c - cx) / cx          # –1 .. +1
            dy = (r - cy) / cy          # –1 .. +1

            # Noise warp: shift the sample point, making the boundary irregular
            wx = _value_noise(c * 0.06, r * 0.06, mask_seed)          - 0.5
            wy = _value_noise(c * 0.06, r * 0.06, mask_seed ^ 0x9E37) - 0.5
            dxw = dx + wx * EDGE_WARP
            dyw = dy + wy * EDGE_WARP

            dist = (dxw ** 2 + dyw ** 2) ** 0.5   # 0 at centre, ~1.4 at corner

            # --- Check if cell is inside any scatter blob ---
            in_blob = False
            for bx, by, br, bstrength in scatter_blobs:
                bd = ((dx - bx) ** 2 + (dy - by) ** 2) ** 0.5
                if bd < br:
                    t = bd / br
                    m = t * t * (3.0 - 2.0 * t)   # smoothstep 0=centre 1=edge
                    hmap[r][c] = hmap[r][c] * (1.0 - (1.0 - m) * bstrength)
                    in_blob = True
                    break
            if in_blob:
                continue

            if dist <= EDGE_INNER:
                continue                           # fully inside — unchanged

            # --- Check if cell falls inside a spike ---
            angle = math.atan2(dy, dx)
            in_spike = False
            for sa, sw in spikes:
                da = abs(math.atan2(math.sin(angle - sa),
                                    math.cos(angle - sa)))   # angular diff, 0..π
                if da < sw:
                    spike_outer = EDGE_OUTER + SPIKE_REACH * (1.0 - da / sw)
                    if dist < spike_outer:
                        t = max(0.0, (dist - EDGE_INNER) / (spike_outer - EDGE_INNER))
                        m = t * t * (3.0 - 2.0 * t)
                        hmap[r][c] = hmap[r][c] + m * (1.0 - hmap[r][c]) * 0.7
                        in_spike = True
                        break
            if in_spike:
                continue

            if dist >= EDGE_OUTER:
                hmap[r][c] = 1.0                  # fully dissolved to paper
                continue

            # Smoothstep between inner and outer radius
            t = (dist - EDGE_INNER) / (EDGE_OUTER - EDGE_INNER)
            m = t * t * (3.0 - 2.0 * t)           # 0 inside → 1 outside

            # Blend current value toward paper (1.0)
            hmap[r][c] = hmap[r][c] + m * (1.0 - hmap[r][c])


# ===========================================================================
# Gothic seal — line/arc rasterizers + composition
# ===========================================================================

def _new_hmap(n: int, fill: float = 1.0) -> list[list[float]]:
    return [[fill] * n for _ in range(n)]


def _new_hmap_rect(rows: int, cols: int, fill: float = 1.0) -> list[list[float]]:
    return [[fill] * cols for _ in range(rows)]


def _hmap_dims(hmap) -> tuple[int, int]:
    rows = len(hmap)
    return rows, len(hmap[0]) if rows else 0


def _darken(hmap, r: int, c: int, target: float, n: int = 0) -> None:
    rows, cols = _hmap_dims(hmap)
    if 0 <= r < rows and 0 <= c < cols and target < hmap[r][c]:
        hmap[r][c] = target


def _stamp_point(hmap, r: int, c: int, n: int, strength: float,
                 seed: int, jitter: float = 0.0) -> None:
    if jitter > 0:
        j = (_value_noise(c * 0.5, r * 0.5, seed) - 0.5) * jitter
        strength = strength + j
    _darken(hmap, r, c, 1.0 - max(0.0, min(1.0, strength)), n)


def _stamp_line(hmap, x0: float, y0: float, x1: float, y1: float, n: int,
                seed: int, strength: float = 0.35, half_width: float = 0.6,
                noise_jitter: float = 0.12) -> None:
    steps = int(max(abs(x1 - x0), abs(y1 - y0), 1) * 2) + 1
    for i in range(steps + 1):
        t = i / steps
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t
        hw = half_width + (_value_noise(x * 0.2, y * 0.2, seed ^ 0x11) - 0.5) * noise_jitter
        ir, ic = int(round(y)), int(round(x))
        rad = int(max(1, round(hw)))
        for dr in range(-rad, rad + 1):
            for dc in range(-rad, rad + 1):
                if dr * dr + dc * dc > rad * rad:
                    continue
                nj = (_value_noise((ic + dc) * 0.3, (ir + dr) * 0.3, seed) - 0.5) * noise_jitter
                _stamp_point(hmap, ir + dr, ic + dc, n, strength + nj, seed)


def _stamp_dashed_line(hmap, x0: float, y0: float, x1: float, y1: float, n: int,
                       seed: int, strength: float = 0.22, dash: int = 5,
                       gap: int = 4, **kw) -> None:
    import math
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 1:
        return
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    pos = 0.0
    on = True
    while pos < length:
        seg = dash if on else gap
        end = min(pos + seg, length)
        if on:
            _stamp_line(hmap,
                        x0 + ux * pos, y0 + uy * pos,
                        x0 + ux * end, y0 + uy * end,
                        n, seed ^ int(pos), strength=strength, **kw)
        pos = end
        on = not on


def _stamp_circle_band(hmap, cx: float, cy: float, radius: float, n: int,
                       seed: int, strength: float = 0.2, band_half: float = 0.7,
                       warp: float = 0.15) -> None:
    for r in range(n):
        for c in range(n):
            wx = (_value_noise(c * 0.08, r * 0.08, seed) - 0.5) * warp
            wy = (_value_noise(c * 0.08, r * 0.08, seed ^ 0x9E37) - 0.5) * warp
            dx = (c - cx) / max(radius, 1) + wx
            dy = (r - cy) / max(radius, 1) + wy
            dist = (dx * dx + dy * dy) ** 0.5
            bd = abs(dist - 1.0) * radius
            if bd >= band_half:
                continue
            t = 1.0 - bd / band_half
            v = strength * t * t
            _darken(hmap, r, c, 1.0 - v, n)


def _stamp_gothic_arch_interior(hmap, cx: float, apex_y: float, base_y: float,
                                half_w: float, n: int, seed: int,
                                strength: float = 0.32, warp: float = 0.08) -> None:
    span = base_y - apex_y
    if span < 2:
        return
    for r in range(n):
        for c in range(n):
            if r < apex_y or r > base_y:
                continue
            rel = (r - apex_y) / span
            wx = (_value_noise(c * 0.1, r * 0.1, seed) - 0.5) * warp * half_w
            edge = half_w * rel + wx
            inset = edge - abs(c - cx)
            if inset < 0.5:
                continue
            wall = min(1.0, inset / max(edge * 0.45, 2.0))
            v = strength * wall * (0.55 + 0.45 * rel)
            grain = (_value_noise(c * 0.25, r * 0.25, seed ^ 0x61A1) - 0.5) * 0.12
            _darken(hmap, r, c, 1.0 - max(0.0, v + grain), n)


def _stamp_gothic_arch_band(hmap, cx: float, apex_y: float, base_y: float,
                            half_w: float, n: int, seed: int,
                            strength: float = 0.5, band_half: float = 1.1,
                            warp: float = 0.08) -> None:
    span = base_y - apex_y
    if span < 2:
        return
    for r in range(n):
        for c in range(n):
            if r < apex_y or r > base_y:
                continue
            rel = (r - apex_y) / span
            wx = (_value_noise(c * 0.1, r * 0.1, seed) - 0.5) * warp * half_w
            edge = half_w * rel + wx
            dist = abs(c - cx) - edge
            if abs(dist) > band_half:
                continue
            t = 1.0 - abs(dist) / band_half
            v = strength * t * t
            _darken(hmap, r, c, 1.0 - v, n)


def _stamp_rect_band(hmap, x0: float, y0: float, x1: float, y1: float, n: int,
                     seed: int, strength: float = 0.5, band_half: float = 1.2) -> None:
    for r in range(n):
        for c in range(n):
            if c < x0 - band_half or c > x1 + band_half or r < y0 - band_half or r > y1 + band_half:
                continue
            if x0 <= c <= x1 and y0 <= r <= y1:
                dist = min(c - x0, x1 - c, r - y0, y1 - r)
            else:
                dx = max(x0 - c, 0, c - x1)
                dy = max(y0 - r, 0, r - y1)
                dist = (dx * dx + dy * dy) ** 0.5
            if dist > band_half:
                continue
            t = 1.0 - dist / band_half
            v = strength * t * t
            _darken(hmap, r, c, 1.0 - v, n)


def _stamp_rect_interior(hmap, x0: float, y0: float, x1: float, y1: float, n: int,
                         seed: int, strength: float = 0.22, margin: float = 2.5) -> None:
    for r in range(n):
        for c in range(n):
            if c <= x0 + margin or c >= x1 - margin or r <= y0 + margin or r >= y1 - margin:
                continue
            dist = min(c - x0, x1 - c, r - y0, y1 - r)
            wall = min(1.0, dist / max(margin * 2, 1))
            grain = (_value_noise(c * 0.22, r * 0.22, seed) - 0.5) * 0.1
            v = strength * (0.5 + 0.5 * wall) + grain
            _darken(hmap, r, c, 1.0 - max(0.0, v), n)


def _stamp_semicircle_arch_band(hmap, cx: float, spring_y: float, radius: float,
                                n: int, seed: int, strength: float = 0.55,
                                band_half: float = 1.2, warp: float = 0.06) -> None:
    for r in range(n):
        for c in range(n):
            if r > spring_y:
                continue
            wx = (_value_noise(c * 0.1, r * 0.1, seed) - 0.5) * warp * radius
            dx = (c - cx + wx) / max(radius, 1)
            dy = (r - spring_y) / max(radius, 1)
            if dy > 0.05:
                continue
            dist = (dx * dx + dy * dy) ** 0.5
            bd = abs(dist - 1.0) * radius
            if bd > band_half:
                continue
            t = 1.0 - bd / band_half
            v = strength * t * t
            _darken(hmap, r, c, 1.0 - v, n)


def _stamp_semicircle_interior(hmap, cx: float, spring_y: float, radius: float,
                               base_y: float, n: int, seed: int,
                               strength: float = 0.26) -> None:
    for r in range(n):
        for c in range(n):
            if r > base_y or r > spring_y:
                continue
            dx = (c - cx) / max(radius, 1)
            dy = (r - spring_y) / max(radius, 1)
            if dy > 0.05:
                continue
            if dx * dx + dy * dy > 0.92:
                continue
            inset = 0.92 - (dx * dx + dy * dy) ** 0.5
            grain = (_value_noise(c * 0.2, r * 0.2, seed) - 0.5) * 0.1
            v = strength * inset + grain
            _darken(hmap, r, c, 1.0 - max(0.0, v), n)


def _stamp_jamb_walls(hmap, cx: float, spring_y: float, base_y: float,
                      half_w: float, n: int, seed: int,
                      strength: float = 0.5, band_half: float = 1.0) -> None:
    for side in (-1, 1):
        x = cx + side * half_w
        _stamp_line(hmap, x, spring_y, x, base_y, n, seed ^ side,
                    strength=strength, half_width=band_half)


def _stamp_architectural_column(hmap, x: float, y_top: float, y_base: float,
                                n: int, seed: int, scale: float,
                                strength: float = 0.56) -> None:
    capital_h = max(3.5, 5.0 * scale)
    spring = y_top + capital_h
    shaft_hw = max(0.45, 0.55 * scale)
    cap_w = shaft_hw * 2.6
    _stamp_line(hmap, x - cap_w * 1.15, y_top, x + cap_w * 1.15, y_top, n,
                seed ^ 0xC01, strength=strength * 0.92, half_width=0.42, noise_jitter=0.05)
    _stamp_line(hmap, x - cap_w * 0.75, y_top + capital_h * 0.35,
                x + cap_w * 0.75, y_top + capital_h * 0.35, n,
                seed ^ 0xC02, strength=strength * 0.78, half_width=0.35, noise_jitter=0.04)
    _stamp_line(hmap, x - cap_w, spring, x + cap_w, spring, n,
                seed ^ 0xC03, strength=strength * 0.88, half_width=0.4, noise_jitter=0.05)
    for dx in (-shaft_hw, shaft_hw):
        _stamp_line(hmap, x + dx, spring, x + dx, y_base, n, seed ^ int(dx * 10),
                    strength=strength, half_width=0.38, noise_jitter=0.05)
    _stamp_line(hmap, x - cap_w * 0.55, y_base, x + cap_w * 0.55, y_base, n,
                seed ^ 0xC04, strength=strength * 0.72, half_width=0.38, noise_jitter=0.04)


def _stamp_ornate_lantern(hmap, cx: float, cy: float, n: int, seed: int,
                          scale: float) -> None:
    s = scale
    y = cy
    _stamp_line(hmap, cx, y - 20 * s, cx, y - 13 * s, n, seed,
                strength=0.58, half_width=0.42, noise_jitter=0.05)
    _stamp_diamond(hmap, cx, y - 16.5 * s, 2.4 * s, n, seed ^ 0xA01, strength=0.52)
    _stamp_dashed_line(hmap, cx, y - 13 * s, cx, y - 9.5 * s, n, seed ^ 0xA02,
                       strength=0.32, dash=2, gap=2, half_width=0.35)
    _stamp_line(hmap, cx - 5.5 * s, y - 9.5 * s, cx + 5.5 * s, y - 9.5 * s, n,
                seed ^ 0xA03, strength=0.55, half_width=0.45, noise_jitter=0.05)
    _stamp_rect_band(hmap, cx - 4.5 * s, y - 9 * s, cx + 4.5 * s, y - 2.5 * s, n,
                     seed ^ 0xA04, strength=0.62, band_half=0.95)
    for i in range(3):
        ly = y - 7.5 * s + i * 2.2 * s
        _stamp_line(hmap, cx - 3.8 * s, ly, cx + 3.8 * s, ly, n, seed ^ (0xA10 + i),
                    strength=0.42, half_width=0.35, noise_jitter=0.04)
    _stamp_rect_band(hmap, cx - 5.5 * s, y - 2 * s, cx + 5.5 * s, y + 5.5 * s, n,
                     seed ^ 0xA05, strength=0.54, band_half=1.0)
    _stamp_line(hmap, cx - 6.5 * s, y + 5.5 * s, cx + 6.5 * s, y + 5.5 * s, n,
                seed ^ 0xA06, strength=0.5, half_width=0.48, noise_jitter=0.05)
    _stamp_line(hmap, cx - 2.2 * s, y + 5.5 * s, cx, y + 9.5 * s, n,
                seed ^ 0xA07, strength=0.46, half_width=0.4, noise_jitter=0.04)
    _stamp_line(hmap, cx + 2.2 * s, y + 5.5 * s, cx, y + 9.5 * s, n,
                seed ^ 0xA08, strength=0.46, half_width=0.4, noise_jitter=0.04)


def _draw_blueprint_construction(hmap, n: int, cx: float, cy: float, seed: int,
                                 scale: float, apex_y: float, base_y: float) -> None:
    import math
    circ_cy = apex_y + (base_y - apex_y) * 0.38
    for i, frac in enumerate((0.46, 0.38, 0.30, 0.22, 0.15)):
        _stamp_circle_band(hmap, cx, circ_cy, n * frac, n,
                           seed ^ (0xC1AC1E + i), strength=0.19 - i * 0.025,
                           band_half=0.7, warp=0.07)
    span = base_y - apex_y
    for layer in range(3):
        shrink = layer * n * 0.055
        hw = n * 0.40 - shrink
        la = apex_y + shrink * 0.3
        steps = max(8, int(hw))
        for i in range(steps):
            t = i / steps
            rel = t
            x = cx - hw * rel
            y = la + span * rel * 0.92
            if i % 4 == 0:
                _stamp_point(hmap, int(y), int(x), n, 0.2, seed ^ (layer * 0x40 + i))
            x2 = cx + hw * rel
            if i % 4 == 2:
                _stamp_point(hmap, int(y), int(x2), n, 0.2, seed ^ (layer * 0x40 + i + 1))
    _stamp_dashed_line(hmap, 5, cy, n - 6, cy, n, seed ^ 0xA0A12,
                       strength=0.15, dash=5, gap=4, half_width=0.4)
    _stamp_dashed_line(hmap, cx, 6, cx, n - 7, n, seed ^ 0xA0A13,
                       strength=0.14, dash=4, gap=5, half_width=0.38)
    for gy in (apex_y + span * 0.15, base_y - span * 0.08):
        _stamp_dashed_line(hmap, n * 0.10, gy, n * 0.90, gy, n,
                           seed ^ int(gy), strength=0.13, dash=3, gap=4,
                           half_width=0.35)
    for i in range(8):
        angle = i * math.pi / 4 + (_hash_val(i, 0, seed) - 0.5) * 0.12
        r = n * (0.20 + _hash_val(i, 1, seed) * 0.22)
        px = cx + math.cos(angle) * r
        py = circ_cy + math.sin(angle) * r
        _stamp_point(hmap, int(py), int(px), n, 0.22 + _hash_val(i, 2, seed) * 0.08,
                     seed ^ (i * 0x11))
    arm = max(4.5, 5.5 * scale)
    for i, (px, py) in enumerate([(cx, 5), (cx, n - 6), (5, cy), (n - 6, cy)]):
        _stamp_crosshair(hmap, px, py, n, seed ^ (i * 0x10), arm=arm, strength=0.26)
    for i, (ox, oy) in enumerate([(-0.34, -0.28), (0.34, -0.28),
                                   (-0.34, 0.16), (0.34, 0.16)]):
        _stamp_diamond(hmap, cx + n * ox, cy + n * oy, 2.8 * scale, n,
                       seed ^ (i * 0x20), strength=0.22)


def _draw_blueprint_gothic_frame(hmap, n: int, cx: float, cy: float,
                                 seed: int, scale: float) -> None:
    layers = 3
    apex = cy - n * 0.28
    base = cy + n * 0.30
    span = base - apex
    col_specs: list[tuple[float, float, float]] = []
    for layer in range(layers):
        shrink = layer * n * 0.065
        hw = n * 0.40 - shrink
        la = apex + shrink * 0.3
        lb = base - shrink * 0.12
        outer_st = 0.64 - layer * 0.06
        inner_st = outer_st * 0.62
        if layer == 0:
            _stamp_gothic_arch_interior(hmap, cx, la, lb, hw, n,
                                        seed ^ (layer * 0x200),
                                        strength=0.12, warp=0.03)
        _stamp_gothic_arch_band(hmap, cx, la, lb, hw, n, seed ^ (layer * 0x100),
                                strength=outer_st, band_half=0.72 + layer * 0.05, warp=0.04)
        _stamp_gothic_arch_band(hmap, cx, la + span * 0.04, lb - span * 0.03,
                                hw * 0.88, n, seed ^ (layer * 0x150),
                                strength=inner_st, band_half=0.55, warp=0.03)
        if layer == 0:
            col_x = hw * 0.90
            col_specs = [(cx - col_x, la, lb), (cx + col_x, la, lb)]
    for x, y_top, y_base in col_specs:
        _stamp_architectural_column(hmap, x, y_top - n * 0.02, y_base, n,
                                    seed ^ int(x), scale)


def _apply_blueprint_anchor_marks(hmap, n: int, cx: float, cy: float,
                                  seed: int, scale: float) -> None:
    import math
    circ_cy = cy - n * 0.12
    count = 5 + int(_hash_val(9, 1, seed) * 4)
    for i in range(count):
        angle = i * 2 * math.pi / count + (_hash_val(i, 0, seed) - 0.5) * 0.25
        r = n * (0.14 + _hash_val(i, 1, seed) * 0.18)
        px = cx + math.cos(angle) * r
        py = circ_cy + math.sin(angle) * r
        if _hash_val(i, 2, seed) > 0.55:
            _stamp_ink_star(hmap, px, py, n, seed ^ (i * 0x20),
                            size=2.0 + _hash_val(i, 3, seed) * 2.5 * scale,
                            points=4, strength=0.28)
        else:
            _stamp_point(hmap, int(py), int(px), n, 0.26, seed ^ i)


def _draw_seal_construction(hmap, n: int, cx: float, cy: float, seed: int,
                            scale: float) -> None:
    for i, frac in enumerate((0.48, 0.40, 0.32, 0.24)):
        _stamp_circle_band(hmap, cx, cy - n * 0.02, n * frac, n,
                           seed ^ (0xC1AC1E + i), strength=0.20 - i * 0.03,
                           band_half=0.85)
    _stamp_dashed_line(hmap, 4, cy, n - 5, cy, n, seed ^ 0xA0A12,
                       strength=0.16, dash=5, gap=4, half_width=0.45)
    _stamp_dashed_line(hmap, cx, 6, cx, n - 7, n, seed ^ 0xA0A13,
                       strength=0.14, dash=4, gap=5, half_width=0.4)
    for gy in (cy - n * 0.12, cy + n * 0.14):
        _stamp_dashed_line(hmap, n * 0.12, gy, n * 0.88, gy, n,
                           seed ^ int(gy), strength=0.12, dash=3, gap=4,
                           half_width=0.35)
    arm = max(5.0, 6.0 * scale)
    marks = [(cx, 5), (cx, n - 6), (5, cy), (n - 6, cy)]
    for i, (px, py) in enumerate(marks):
        _stamp_crosshair(hmap, px, py, n, seed ^ (i * 0x10), arm=arm, strength=0.28)
    for i, (px, py) in enumerate([(cx - n * 0.34, cy - n * 0.30),
                                   (cx + n * 0.34, cy - n * 0.30),
                                   (cx - n * 0.34, cy + n * 0.18),
                                   (cx + n * 0.34, cy + n * 0.18)]):
        _stamp_diamond(hmap, px, py, 3.0 * scale, n, seed ^ (i * 0x20), strength=0.24)


def _seal_struct_nested_gothic(hmap, n: int, cx: float, cy: float, seed: int,
                               scale: float) -> None:
    layers = 3 + int(_hash_val(0, 8, seed) * 2)
    apex = cy - n * 0.30
    base = cy + n * 0.32
    for layer in range(layers):
        shrink = layer * 0.05 * n
        hw = n * 0.42 - shrink
        la = apex + shrink * 0.25
        lb = base - shrink * 0.15
        st = 0.58 - layer * 0.07
        bh = 1.35 + layer * 0.1
        _stamp_gothic_arch_interior(hmap, cx, la, lb, hw, n,
                                    seed ^ (layer * 0x200), strength=0.28 - layer * 0.04)
        _stamp_gothic_arch_band(hmap, cx, la, lb, hw, n, seed ^ (layer * 0x100),
                                strength=st, band_half=bh)
    col_w = max(2, int(3 * scale))
    col_h = max(6, int((base - apex) * 0.55))
    col_x = int(n * 0.42)
    for side, off in ((-1, 0xC01), (1, 0xC02)):
        _draw_blob(hmap, int(cx + side * col_x), int((apex + base) / 2),
                   seed ^ off, w=col_w, h=col_h, strength=0.72, noise_warp=2.2)


def _seal_struct_round_doorway(hmap, n: int, cx: float, cy: float, seed: int,
                               scale: float) -> None:
    base = cy + n * 0.30
    for layer in range(3):
        shrink = layer * n * 0.04
        hw = n * 0.30 - shrink
        spring = cy - n * 0.08 + layer * n * 0.03
        rad = hw
        st = 0.55 - layer * 0.08
        _stamp_semicircle_interior(hmap, cx, spring, rad, base - shrink * 0.5, n,
                                   seed ^ (layer * 0x40), strength=0.24 - layer * 0.03)
        _stamp_semicircle_arch_band(hmap, cx, spring, rad, n, seed ^ (layer * 0x30),
                                    strength=st, band_half=1.1)
        _stamp_jamb_walls(hmap, cx, spring, base - shrink * 0.5, hw, n,
                          seed ^ (layer * 0x50), strength=st * 0.9)
    _stamp_dashed_line(hmap, cx - n * 0.34, base, cx + n * 0.34, base, n,
                       seed ^ 0x51, strength=0.35, dash=3, gap=3, half_width=0.5)
    steps = int(3 + _hash_val(1, 1, seed) * 2)
    for i in range(steps):
        sy = base + i * 2.5 * scale
        sw = n * 0.22 + i * 3 * scale
        _stamp_line(hmap, cx - sw, sy, cx + sw, sy, n, seed ^ i,
                    strength=0.3, half_width=0.45)


def _seal_struct_facade(hmap, n: int, cx: float, cy: float, seed: int,
                        scale: float) -> None:
    x0 = cx - n * 0.36
    x1 = cx + n * 0.36
    y0 = cy - n * 0.28
    y1 = cy + n * 0.32
    _stamp_rect_interior(hmap, x0, y0, x1, y1, n, seed ^ 0xFA, strength=0.2, margin=3)
    _stamp_rect_band(hmap, x0, y0, x1, y1, n, seed ^ 0xFB, strength=0.58, band_half=1.3)
    rows = 3 + int(_hash_val(2, 2, seed) * 2)
    cols = 2 + int(_hash_val(3, 2, seed) * 2)
    for row in range(rows):
        for col in range(cols):
            wx0 = x0 + (x1 - x0) * (col + 0.18) / cols
            wx1 = x0 + (x1 - x0) * (col + 0.82) / cols
            wy0 = y0 + (y1 - y0) * (row + 0.15) / (rows + 0.5)
            wy1 = y0 + (y1 - y0) * (row + 0.55) / (rows + 0.5)
            _stamp_rect_band(hmap, wx0, wy0, wx1, wy1, n,
                             seed ^ (row * 16 + col), strength=0.42, band_half=0.8)
    peak = _hash_val(4, 4, seed) > 0.5
    if peak:
        _stamp_gothic_arch_band(hmap, cx, y0 - n * 0.02, y0 + n * 0.14, n * 0.22, n,
                                seed ^ 0xFC, strength=0.45, band_half=1.0)
    else:
        _stamp_line(hmap, x0, y0, x1, y0, n, seed ^ 0xFC, strength=0.4, half_width=0.55)


def _seal_struct_tower(hmap, n: int, cx: float, cy: float, seed: int,
                       scale: float) -> None:
    bw = n * 0.14 + _hash_val(5, 5, seed) * n * 0.06
    x0, x1 = cx - bw, cx + bw
    y0 = cy - n * 0.34
    y1 = cy + n * 0.32
    _stamp_rect_interior(hmap, x0, y0, x1, y1, n, seed ^ 0x70, strength=0.25, margin=2)
    _stamp_rect_band(hmap, x0, y0, x1, y1, n, seed ^ 0x71, strength=0.6, band_half=1.2)
    for i in range(4):
        wy = y0 + (y1 - y0) * (i + 1) / 5
        _stamp_dashed_line(hmap, x0 + 2, wy, x1 - 2, wy, n, seed ^ i,
                           strength=0.28, dash=2, gap=3, half_width=0.35)
    top_style = int(_hash_val(6, 6, seed) * 3)
    if top_style == 0:
        _stamp_gothic_arch_band(hmap, cx, y0 - n * 0.06, y0 + n * 0.10, bw * 1.1, n,
                                seed ^ 0x72, strength=0.5, band_half=1.0)
    elif top_style == 1:
        _stamp_semicircle_arch_band(hmap, cx, y0, bw * 1.05, n, seed ^ 0x72,
                                    strength=0.5, band_half=1.0)
    else:
        _draw_blob(hmap, int(cx), int(y0 - 4 * scale), seed ^ 0x72,
                   w=max(3, int(bw * 0.6)), h=max(4, int(6 * scale)),
                   strength=0.75, noise_warp=2.5)
    _stamp_rect_band(hmap, x0 - 4 * scale, y1, x1 + 4 * scale, y1 + 5 * scale, n,
                     seed ^ 0x73, strength=0.45, band_half=1.0)


def _seal_struct_portico(hmap, n: int, cx: float, cy: float, seed: int,
                         scale: float) -> None:
    base = cy + n * 0.28
    spring = cy - n * 0.06
    hw = n * 0.34
    col_x = n * 0.30
    col_w = max(2, int(3 * scale))
    col_h = int(base - spring + n * 0.04)
    for side, off in ((-1, 0xA001), (1, 0xA002)):
        _draw_blob(hmap, int(cx + side * col_x), int((spring + base) / 2),
                   seed ^ off, w=col_w, h=col_h, strength=0.8, noise_warp=2.0)
        _draw_blob(hmap, int(cx + side * col_x), int(spring - 3 * scale), seed ^ (off + 1),
                   w=max(3, int(5 * scale)), h=max(2, int(3 * scale)), strength=0.7, noise_warp=2.0)
    round_top = _hash_val(7, 7, seed) > 0.45
    if round_top:
        _stamp_semicircle_interior(hmap, cx, spring, hw, base, n, seed ^ 0xA010, strength=0.22)
        _stamp_semicircle_arch_band(hmap, cx, spring, hw, n, seed ^ 0xA011, strength=0.55)
        _stamp_jamb_walls(hmap, cx, spring, base, hw, n, seed ^ 0xA012, strength=0.48)
    else:
        _stamp_gothic_arch_interior(hmap, cx, spring - hw * 0.5, base, hw, n,
                                    seed ^ 0xA010, strength=0.24)
        _stamp_gothic_arch_band(hmap, cx, spring - hw * 0.5, base, hw, n,
                                seed ^ 0xA011, strength=0.55, band_half=1.2)
    _stamp_line(hmap, cx - col_x - 6 * scale, spring - 2 * scale,
                cx + col_x + 6 * scale, spring - 2 * scale, n, seed ^ 0xA020,
                strength=0.42, half_width=0.55)


def _seal_struct_ruined_arch(hmap, n: int, cx: float, cy: float, seed: int,
                             scale: float) -> None:
    base = cy + n * 0.30
    hw = n * 0.38
    apex = cy - n * 0.26
    _stamp_gothic_arch_interior(hmap, cx, apex, base, hw, n, seed ^ 0xB001, strength=0.2)
    _stamp_gothic_arch_band(hmap, cx, apex, base, hw, n, seed ^ 0xB002,
                            strength=0.52, band_half=1.3)
    for c in range(n):
        for r in range(n):
            if r < apex or r > base:
                continue
            rel = (r - apex) / (base - apex)
            edge = hw * rel * 1.15
            if abs(c - cx) - edge > 2.5 or abs(c - cx) - edge < 0.5:
                continue
            if _value_noise(c * 0.15, r * 0.15, seed ^ 0xB003) < 0.38:
                continue
            _darken(hmap, r, c, 0.55, n)
    _draw_blob(hmap, int(cx - hw * 0.55), int(base - 8 * scale), seed ^ 0xB004,
               w=max(4, int(8 * scale)), h=max(3, int(5 * scale)), strength=0.65, noise_warp=4.0)
    _draw_blob(hmap, int(cx + hw * 0.4), int(apex + 10 * scale), seed ^ 0xB005,
               w=max(3, int(6 * scale)), h=max(5, int(9 * scale)), strength=0.5, noise_warp=5.0)


def _stamp_ink_star(hmap, cx: float, cy: float, n: int, seed: int,
                    size: float = 5.0, points: int = 6, strength: float = 0.5) -> None:
    import math
    for p in range(points):
        jitter = (_hash_val(p, 2, seed) - 0.5) * 0.35
        angle = p * 2 * math.pi / points + jitter
        x1 = cx + math.cos(angle) * size * (0.8 + _hash_val(p, 3, seed) * 0.4)
        y1 = cy + math.sin(angle) * size * (0.8 + _hash_val(p, 4, seed) * 0.4)
        _stamp_line(hmap, cx, cy, x1, y1, n, seed ^ p,
                    strength=strength, half_width=0.55, noise_jitter=0.18)


def _stamp_tendril(hmap, x0: float, y0: float, x1: float, y1: float, n: int,
                   seed: int, strength: float = 0.48) -> None:
    mx = (x0 + x1) / 2 + (_hash_val(0, 0, seed) - 0.5) * n * 0.18
    my = (y0 + y1) / 2 + (_hash_val(1, 0, seed) - 0.5) * n * 0.18
    steps = 14
    px, py = x0, y0
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        x = u * u * x0 + 2 * u * t * mx + t * t * x1
        y = u * u * y0 + 2 * u * t * my + t * t * y1
        _stamp_line(hmap, px, py, x, y, n, seed ^ i,
                    strength=strength, half_width=0.5, noise_jitter=0.2)
        px, py = x, y
    import math
    angle = math.atan2(y1 - my, x1 - mx)
    for k in range(3):
        a = angle + (k - 1) * 0.45
        spike = 3 + _hash_val(k, 1, seed) * 4
        _stamp_line(hmap, x1, y1,
                    x1 + math.cos(a) * spike, y1 + math.sin(a) * spike,
                    n, seed ^ (k + 10), strength=strength * 0.9,
                    half_width=0.4, noise_jitter=0.15)


def _stamp_hatching(hmap, x0: float, y0: float, x1: float, y1: float, n: int,
                    seed: int, spacing: float = 3.5, strength: float = 0.22,
                    vertical: bool = True) -> None:
    if vertical:
        x = x0 + 1
        while x < x1 - 1:
            _stamp_line(hmap, x, y0, x, y1, n, seed ^ int(x),
                        strength=strength, half_width=0.35, noise_jitter=0.1)
            x += spacing
    else:
        y = y0 + 1
        while y < y1 - 1:
            _stamp_line(hmap, x0, y, x1, y, n, seed ^ int(y),
                        strength=strength, half_width=0.35, noise_jitter=0.1)
            y += spacing


def _punch_negative_dots(hmap, n: int, seed: int, count: int = 16) -> None:
    placed = 0
    tries = 0
    while placed < count and tries < count * 12:
        tries += 1
        r = int(_hash_val(placed, tries, seed) * (n - 1))
        c = int(_hash_val(tries, placed, seed ^ 1) * (n - 1))
        if hmap[r][c] > 0.52:
            continue
        rad = 1 + int(_hash_val(placed, 2, seed) * 1.5)
        for dr in range(-rad, rad + 1):
            for dc in range(-rad, rad + 1):
                if dr * dr + dc * dc > rad * rad:
                    continue
                rr, cc = r + dr, c + dc
                if 0 <= rr < n and 0 <= cc < n:
                    hmap[rr][cc] = min(1.0, hmap[rr][cc] + 0.55)
        placed += 1


def _stamp_dense_blob(hmap, cx: float, cy: float, n: int, seed: int,
                      w: float, h: float, strength: float = 0.82) -> None:
    _draw_blob(hmap, int(cx), int(cy), seed, w=int(w), h=int(h),
               strength=strength, noise_warp=5.5)
    _punch_negative_dots(hmap, n, seed ^ 0xD07E, count=4 + int(_hash_val(3, 3, seed) * 6))


def _apply_organic_ornaments(hmap, n: int, seed: int, scale: float) -> None:
    star_count = 5 + int(_hash_val(9, 1, seed) * 7)
    for i in range(star_count):
        sx = 8 + _hash_val(i, 0, seed ^ 0x57A2) * (n - 16)
        sy = 8 + _hash_val(i, 1, seed ^ 0x57A2) * (n - 16)
        if _hash_val(i, 2, seed) < 0.35:
            continue
        pts = 4 + int(_hash_val(i, 3, seed) * 5)
        sz = 2.5 + _hash_val(i, 4, seed) * 5 * scale
        _stamp_ink_star(hmap, sx, sy, n, seed ^ (i * 0x20), size=sz, points=pts,
                        strength=0.32 + _hash_val(i, 5, seed) * 0.2)
    tendrils = 2 + int(_hash_val(8, 2, seed) * 3)
    for i in range(tendrils):
        side = 1 if _hash_val(i, 6, seed) > 0.5 else -1
        x0 = n * 0.5 + side * n * (0.08 + _hash_val(i, 7, seed) * 0.15)
        y0 = n * 0.55 + _hash_val(i, 8, seed) * n * 0.2
        x1 = x0 + side * n * (0.12 + _hash_val(i, 9, seed) * 0.1)
        y1 = y0 - n * (0.08 + _hash_val(i, 10, seed) * 0.15)
        _stamp_tendril(hmap, x0, y0, x1, y1, n, seed ^ (i * 0x100))
    _punch_negative_dots(hmap, n, seed ^ 0xA0E0, count=8 + int(_hash_val(4, 4, seed) * 10))


def _seal_struct_hallway(hmap, n: int, cx: float, cy: float, seed: int,
                         scale: float) -> None:
    vp_y = cy - n * 0.28
    floor_y = cy + n * 0.30
    wall_x = n * 0.38
    for i in range(-4, 5):
        ox = i * n * 0.11
        tx = cx + ox * 0.15
        _stamp_line(hmap, cx + ox, floor_y, tx, vp_y, n, seed ^ (i + 20),
                    strength=0.38, half_width=0.45, noise_jitter=0.14)
    _stamp_line(hmap, cx - wall_x, floor_y, cx - wall_x * 0.2, vp_y, n, seed ^ 0xA001,
                strength=0.5, half_width=0.65, noise_jitter=0.12)
    _stamp_line(hmap, cx + wall_x, floor_y, cx + wall_x * 0.2, vp_y, n, seed ^ 0xA002,
                strength=0.5, half_width=0.65, noise_jitter=0.12)
    _stamp_hatching(hmap, cx - wall_x + 3, vp_y + 8, cx - wall_x * 0.25, floor_y - 4,
                    n, seed ^ 0xA003, spacing=3, strength=0.2, vertical=True)
    _stamp_hatching(hmap, cx + wall_x * 0.25, vp_y + 8, cx + wall_x - 3, floor_y - 4,
                    n, seed ^ 0xA004, spacing=3, strength=0.2, vertical=True)
    for layer in range(3):
        shrink = layer * n * 0.04
        _stamp_gothic_arch_band(hmap, cx, vp_y + shrink, floor_y - n * 0.05,
                                n * 0.36 - shrink, n, seed ^ (layer * 0x10),
                                strength=0.5 - layer * 0.08, band_half=1.1)
    _stamp_dashed_line(hmap, cx - n * 0.08, floor_y, cx + n * 0.08, floor_y, n,
                       seed ^ 0xA005, strength=0.35, dash=2, gap=2, half_width=0.5)


def _seal_struct_organic_door(hmap, n: int, cx: float, cy: float, seed: int,
                              scale: float) -> None:
    base = cy + n * 0.28
    top = cy - n * 0.12
    hw = n * 0.22
    _stamp_gothic_arch_interior(hmap, cx, top - hw * 0.4, base, hw * 1.1, n,
                                seed ^ 0xD01, strength=0.3)
    _stamp_gothic_arch_band(hmap, cx, top - hw * 0.4, base, hw * 1.1, n,
                            seed ^ 0xD02, strength=0.58, band_half=1.4)
    dx0, dx1 = cx - hw * 0.75, cx + hw * 0.75
    _stamp_hatching(hmap, dx0 + 2, top + 4, dx1 - 2, base - 3, n, seed ^ 0xD03,
                    spacing=2.8, strength=0.28, vertical=True)
    for side in (-1, 1):
        _stamp_tendril(hmap, cx + side * hw * 1.3, base,
                       cx + side * hw * 1.6, top - n * 0.08, n, seed ^ side)
        _stamp_tendril(hmap, cx + side * hw * 0.9, top,
                       cx + side * hw * 1.2, top - n * 0.18, n, seed ^ (side + 4))
    _stamp_dense_blob(hmap, cx, (top + base) / 2, n, seed ^ 0xD04,
                      w=max(3, hw * 0.35), h=max(5, (base - top) * 0.25), strength=0.75)


def _seal_struct_thorn_arch(hmap, n: int, cx: float, cy: float, seed: int,
                            scale: float) -> None:
    apex = cy - n * 0.26
    base = cy + n * 0.28
    hw = n * 0.36
    _stamp_gothic_arch_interior(hmap, cx, apex, base, hw, n, seed ^ 0xB101, strength=0.32)
    _stamp_gothic_arch_band(hmap, cx, apex, base, hw, n, seed ^ 0xB102,
                            strength=0.6, band_half=1.5)
    import math
    for side in (-1, 1):
        for k in range(4):
            t = k / 3
            y = apex + (base - apex) * t
            edge = hw * t
            x = cx + side * edge
            spike = 4 + _hash_val(k, side, seed) * 6 * scale
            ang = side * (math.pi / 2 + 0.2 - t * 0.3)
            _stamp_line(hmap, x, y, x + math.cos(ang) * spike, y + math.sin(ang) * spike * 0.5,
                        n, seed ^ (k + side * 8), strength=0.45, half_width=0.45,
                        noise_jitter=0.16)
    _stamp_dense_blob(hmap, cx, cy + n * 0.02, n, seed ^ 0xB103,
                      w=max(5, hw * 0.45), h=max(6, n * 0.12), strength=0.78)


def _seal_struct_gnarled_building(hmap, n: int, cx: float, cy: float, seed: int,
                                  scale: float) -> None:
    import math
    _stamp_dense_blob(hmap, cx, cy, n, seed ^ 0xC101,
                      w=n * 0.32, h=n * 0.28, strength=0.85)
    _stamp_dense_blob(hmap, cx, cy - n * 0.18, n, seed ^ 0xC102,
                      w=n * 0.22, h=n * 0.12, strength=0.8)
    for i in range(3):
        ox = (i - 1) * n * 0.14
        _stamp_gothic_arch_band(hmap, cx + ox, cy - n * 0.22, cy + n * 0.08,
                                n * 0.08, n, seed ^ (i * 0x11), strength=0.42, band_half=0.9)
    _stamp_hatching(hmap, cx - n * 0.28, cy - n * 0.08, cx + n * 0.28, cy + n * 0.22,
                    n, seed ^ 0xC103, spacing=3, strength=0.24, vertical=False)
    for i in range(4):
        angle = -math.pi / 2 + (i - 1.5) * 0.5
        x0 = cx + math.cos(angle) * n * 0.2
        y0 = cy - n * 0.22 + math.sin(angle) * n * 0.08
        _stamp_tendril(hmap, cx, cy - n * 0.2, x0, y0 - n * 0.1, n, seed ^ (i * 0x30))


_SEAL_STRUCTURES = (
    _seal_struct_nested_gothic,
    _seal_struct_round_doorway,
    _seal_struct_facade,
    _seal_struct_tower,
    _seal_struct_portico,
    _seal_struct_ruined_arch,
    _seal_struct_hallway,
    _seal_struct_organic_door,
    _seal_struct_thorn_arch,
    _seal_struct_gnarled_building,
)


def _stamp_crosshair(hmap, cx: float, cy: float, n: int, seed: int,
                     arm: float = 6.0, strength: float = 0.3) -> None:
    _stamp_line(hmap, cx - arm, cy, cx + arm, cy, n, seed, strength=strength, half_width=0.4)
    _stamp_line(hmap, cx, cy - arm, cx, cy + arm, n, seed ^ 1, strength=strength, half_width=0.4)


def _stamp_diamond(hmap, cx: float, cy: float, size: float, n: int,
                   seed: int, strength: float = 0.25) -> None:
    s = size
    _stamp_line(hmap, cx, cy - s, cx + s, cy, n, seed, strength=strength, half_width=0.45)
    _stamp_line(hmap, cx + s, cy, cx, cy + s, n, seed ^ 2, strength=strength, half_width=0.45)
    _stamp_line(hmap, cx, cy + s, cx - s, cy, n, seed ^ 3, strength=strength, half_width=0.45)
    _stamp_line(hmap, cx - s, cy, cx, cy - s, n, seed ^ 4, strength=strength, half_width=0.45)


def _seal_motif_columns(hmap, cx: float, cy: float, n: int, seed: int,
                        scale: float) -> None:
    w = max(3, int(5 * scale))
    h = max(8, int(18 * scale))
    gap = max(5, int(10 * scale))
    _draw_blob(hmap, int(cx - gap), int(cy), seed, w=w, h=h, strength=0.88, noise_warp=2.5)
    _draw_blob(hmap, int(cx + gap), int(cy), seed ^ 0x22, w=w, h=h, strength=0.88, noise_warp=2.5)
    _draw_blob(hmap, int(cx - gap), int(cy - 6 * scale), seed ^ 0x23,
               w=max(4, int(6 * scale)), h=max(2, int(3 * scale)), strength=0.75, noise_warp=2.0)
    _draw_blob(hmap, int(cx + gap), int(cy - 6 * scale), seed ^ 0x24,
               w=max(4, int(6 * scale)), h=max(2, int(3 * scale)), strength=0.75, noise_warp=2.0)


def _seal_motif_lantern(hmap, cx: float, cy: float, n: int, seed: int,
                        scale: float) -> None:
    _draw_blob(hmap, int(cx), int(cy - 6 * scale), seed,
               w=max(4, int(7 * scale)), h=max(6, int(10 * scale)),
               strength=0.85, noise_warp=3.0)
    _draw_blob(hmap, int(cx), int(cy + 1 * scale), seed ^ 0x33,
               w=max(3, int(4 * scale)), h=max(5, int(8 * scale)),
               strength=0.90, noise_warp=2.0)
    _draw_blob(hmap, int(cx), int(cy + 9 * scale), seed ^ 0x44,
               w=max(5, int(8 * scale)), h=max(3, int(4 * scale)),
               strength=0.85, noise_warp=2.0)
    _stamp_line(hmap, cx, cy - 12 * scale, cx, cy - 8 * scale, n, seed ^ 0x45,
                strength=0.5, half_width=0.6)


def _seal_motif_rings(hmap, cx: float, cy: float, n: int, seed: int,
                      scale: float) -> None:
    for i, frac in enumerate((0.28, 0.42, 0.56, 0.68)):
        r = frac * n * 0.24 * scale
        _stamp_circle_band(hmap, cx, cy, r, n, seed ^ (i * 0x100),
                           strength=0.52 - i * 0.06, band_half=1.1)


def _seal_motif_lozenge(hmap, cx: float, cy: float, n: int, seed: int,
                        scale: float) -> None:
    s = 11.0 * scale
    _stamp_diamond(hmap, cx, cy, s, n, seed, strength=0.65)
    _stamp_diamond(hmap, cx, cy, s * 0.55, n, seed ^ 0x55, strength=0.45)
    _stamp_diamond(hmap, cx, cy, s * 0.28, n, seed ^ 0x56, strength=0.35)


def _seal_motif_star(hmap, cx: float, cy: float, n: int, seed: int,
                     scale: float) -> None:
    import math
    ccx, ccy = cx, cy
    SPIKES = 8
    outer = 0.28 * n * scale
    inner = outer * 0.68
    band_half = max(1.0, 1.5 * scale)
    for r in range(n):
        for c in range(n):
            dx, dy = c - ccx, r - ccy
            dist = (dx * dx + dy * dy) ** 0.5
            angle = math.atan2(dy, dx)
            phase = (angle * SPIKES / (2 * math.pi)) % 1.0
            tri = abs(phase * 2.0 - 1.0)
            star_r = inner + (outer - inner) * tri
            if abs(dist - star_r) >= band_half:
                continue
            t = 1.0 - abs(dist - star_r) / band_half
            v = 0.68 * t * t
            _darken(hmap, r, c, 1.0 - v, n)


def _seal_motif_bars(hmap, cx: float, cy: float, n: int, seed: int,
                     scale: float) -> None:
    count = 7
    span = 14.0 * scale
    for i in range(count):
        off = (i - count // 2) * (span / count)
        _stamp_line(hmap, cx - 8 * scale, cy + off, cx + 8 * scale, cy + off,
                    n, seed ^ i, strength=0.52, half_width=0.65)


_SEAL_MOTIFS = (
    _seal_motif_columns,
    _seal_motif_lantern,
    _seal_motif_rings,
    _seal_motif_lozenge,
    _seal_motif_star,
    _seal_motif_bars,
)


def _apply_ghost_pass(hmap, n: int, seed: int, strength: float = 0.35) -> None:
    ox = int((_hash_val(1, 0, seed) - 0.5) * 3)
    oy = int((_hash_val(0, 1, seed) - 0.5) * 3)
    ghost = [row[:] for row in hmap]
    for r in range(n):
        for c in range(n):
            gr, gc = r + oy, c + ox
            if 0 <= gr < n and 0 <= gc < n:
                g = ghost[gr][gc]
                hmap[r][c] = hmap[r][c] * (1.0 - strength) + g * strength * 0.85


def _apply_scan_tears(hmap, n: int, seed: int, count: int = 3) -> None:
    for i in range(count):
        row = int(_hash_val(i, 3, seed ^ 0x5CA4) * n)
        tear_w = 1 + int(_hash_val(i, 4, seed) * 2)
        shift = int((_hash_val(i, 5, seed) - 0.5) * 4)
        for dr in range(-tear_w, tear_w + 1):
            rr = row + dr
            if 0 <= rr < n:
                for c in range(n):
                    sc = c + shift if (c + shift) % 3 != 0 else c
                    if 0 <= sc < n:
                        hmap[rr][c] = min(1.0, hmap[rr][c] + 0.25 + dr * 0.05)


def _apply_seal_grain(hmap, n: int, seed: int, strength: float = 0.14) -> None:
    for r in range(n):
        for c in range(n):
            if hmap[r][c] > 0.92:
                continue
            g = _value_noise(c * 0.35, r * 0.35, seed ^ 0x6BA1A0)
            if g > 0.55:
                hmap[r][c] = max(0.0, hmap[r][c] - strength * (g - 0.55))


def _compose_wavefunction_seal(hmap, seed: int, variant: str = "node") -> None:
    """Ink density from |ψ|² interference + wavy lobe ring, dithered to dots."""
    import math
    n = len(hmap)
    cx = cy = (n - 1) / 2.0
    scale = n / 140.0

    lobes = 7 + int(_hash_val(0, 1, seed) * 3)
    if variant == "choice":
        lobes = 5 + int(_hash_val(0, 1, seed) * 4)
    elif variant == "item":
        lobes = 6 + int(_hash_val(0, 1, seed) * 5)

    outer_r = 0.84 + (_hash_val(2, 2, seed) - 0.5) * 0.07
    band_w = 0.050 + _hash_val(3, 3, seed) * 0.028
    warp_amp = 0.09 + _hash_val(4, 4, seed) * 0.09
    ripple_k = 12 + _hash_val(5, 5, seed) * 14
    phase = _hash_val(6, 6, seed) * math.tau
    arm = max(3.5, 5.0 * scale) / (n * 0.5)

    for r in range(n):
        for c in range(n):
            dx = (c - cx) / (n * 0.5)
            dy = (r - cy) / (n * 0.5)
            dist = math.hypot(dx, dy)
            angle = math.atan2(dy, dx)

            tri = abs(((angle * lobes / math.tau) % 1.0) * 2.0 - 1.0)
            inner_r = outer_r - band_w * 2.4
            star_r = inner_r + (outer_r - inner_r) * tri

            wx = (_value_noise(c * 0.11, r * 0.11, seed) - 0.5) * warp_amp
            wy = (_value_noise(c * 0.11, r * 0.11, seed ^ 0x9E37) - 0.5) * warp_amp
            dist_w = math.hypot(dx + wx, dy + wy)

            ring = 0.0
            band_d = abs(dist_w - star_r)
            if band_d < band_w:
                t = 1.0 - band_d / band_w
                ring = t ** 1.35

            psi = math.sin(dist * ripple_k + angle * lobes + phase)
            psi += 0.55 * math.sin(dist * ripple_k * 0.68 - angle * (lobes - 1) + phase * 0.8)
            psi += 0.25 * math.sin((dx + dy) * ripple_k * 0.4 + phase * 1.6)
            ripple = max(0.0, (psi * 0.5 + 0.5) ** 2 - 0.58) * 0.20

            guide = 0.0
            for gfrac in (1.02, 0.72, 0.48):
                gd = abs(dist - outer_r * gfrac)
                if gd < 0.014:
                    guide = max(guide, (1.0 - gd / 0.014) * (0.14 if gfrac > 0.9 else 0.08))

            cross = 0.0
            if abs(dx) < arm * 0.32 and abs(dy) < arm:
                cross = 0.40
            elif abs(dy) < arm * 0.32 and abs(dx) < arm:
                cross = 0.40

            v = ring + ripple + guide + cross

            if variant == "choice":
                if dist < 0.14:
                    v += 0.30 * (1.0 - dist / 0.14) ** 1.5
            elif variant == "item":
                if 0.07 < dist < 0.15:
                    t = 1.0 - abs(dist - 0.11) / 0.04
                    if t > 0:
                        v += 0.38 * t
                if dist < 0.055:
                    v += 0.48 * (1.0 - dist / 0.055)

            grain = _value_noise(c * 0.62, r * 0.62, seed ^ 0xB01D)
            speck = _value_noise(c * 1.8, r * 1.8, seed ^ 0x5FE0)
            v *= 0.70 + 0.20 * grain + 0.10 * speck

            hmap[r][c] = 1.0 - min(0.94, v)

    dot_count = int(18 + _hash_val(7, 7, seed) * 28)
    for i in range(dot_count):
        edge = int(_hash_val(i, 0, seed ^ 0xED6E) * 4)
        t = _hash_val(i, 1, seed)
        jitter = _hash_val(i, 2, seed) * 5
        if edge == 0:
            pr, pc = int(2 + jitter), int(t * (n - 1))
        elif edge == 1:
            pr, pc = int(t * (n - 1)), int(n - 3 - jitter)
        elif edge == 2:
            pr, pc = int(n - 3 - jitter), int(t * (n - 1))
        else:
            pr, pc = int(t * (n - 1)), int(2 + jitter)
        _stamp_point(hmap, pr, pc, n, 0.18 + _hash_val(i, 3, seed) * 0.14, seed ^ i)


def _darken_dot(hmap, x: float, y: float, n: int, strength: float, fade: float = 1.0) -> None:
    rows, cols = _hmap_dims(hmap)
    r, c = int(round(y)), int(round(x))
    if not (0 <= r < rows and 0 <= c < cols):
        return
    weight = max(0.0, min(1.0, strength * fade))
    if weight < 0.10:
        return
    if _hash_val(c, r, 0xD07) > weight:
        return
    _darken(hmap, r, c, 0.0, n)


def _stamp_horizontal_glitch(hmap, x: float, y: float, n: int, seed: int,
                             strength: float, fade: float) -> None:
    if _hash_val(0, 0, seed) < 0.72:
        return
    direction = 1 if _hash_val(1, 0, seed) > 0.5 else -1
    length = 2 + int(_hash_val(2, 0, seed) * 4)
    for k in range(1, length):
        if _hash_val(k, 3, seed) < 0.55:
            continue
        gx = x + direction * k
        gy = y + (_hash_val(k, 4, seed) - 0.5) * 0.35
        decay = (1.0 - k / length) ** 1.5
        _darken_dot(hmap, gx, gy, n, strength * decay * 0.35, fade)


def _stamp_broken_dots_along(hmap, x0: float, y0: float, x1: float, y1: float,
                             n: int, seed: int, strength: float,
                             spacing: float = 1.2, gap_prob: float = 0.25,
                             fade: float = 1.0, glitch: float = 0.0) -> None:
    import math
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 0.4:
        return
    steps = max(2, int(length / spacing))
    for i in range(steps + 1):
        if _hash_val(i, 0, seed) < gap_prob:
            continue
        t = i / steps
        x = x0 + (x1 - x0) * t + (_hash_val(i, 1, seed) - 0.5) * 0.55
        y = y0 + (y1 - y0) * t + (_hash_val(i, 4, seed) - 0.5) * 0.35
        s = strength * (0.65 + 0.35 * _hash_val(i, 2, seed))
        _darken_dot(hmap, x, y, n, s, fade)
        if glitch > 0 and _hash_val(i, 3, seed) > 0.78:
            _stamp_horizontal_glitch(hmap, x, y, n, seed ^ (i * 0x17), strength * glitch, fade)


def _stamp_broken_arc_dots(hmap, cx: float, cy: float, radius: float, n: int, seed: int,
                           strength: float, fade: float, start_a: float, end_a: float,
                           gap_prob: float = 0.38) -> None:
    import math
    steps = max(6, int(radius * 3.5))
    for i in range(steps + 1):
        if _hash_val(i, 0, seed) < gap_prob:
            continue
        t = i / steps
        a = start_a + (end_a - start_a) * t
        x = cx + math.cos(a) * radius
        y = cy + math.sin(a) * radius
        s = strength * (0.7 + 0.3 * _hash_val(i, 1, seed))
        _darken_dot(hmap, x, y, n, s, fade)


def _stamp_rose_window_dots(hmap, cx: float, cy: float, radius: float, n: int,
                            seed: int, strength: float, fade: float) -> None:
    import math
    _stamp_broken_arc_dots(hmap, cx, cy, radius, n, seed ^ 0x01, strength, fade,
                           0, math.tau, 0.40)
    _stamp_broken_dots_along(hmap, cx - radius * 0.85, cy, cx + radius * 0.85, cy, n,
                             seed ^ 0x02, strength * 0.55, 0.9, 0.45, fade, 0.15)
    _stamp_broken_dots_along(hmap, cx, cy - radius * 0.85, cx, cy + radius * 0.85, n,
                             seed ^ 0x03, strength * 0.55, 0.9, 0.45, fade, 0.15)


def _stamp_dotted_cross_star(hmap, cx: float, cy: float, n: int, seed: int,
                             arm: float, strength: float, fade: float = 1.0) -> None:
    d = arm * 0.707
    _stamp_broken_dots_along(hmap, cx - d, cy - d, cx + d, cy + d, n, seed ^ 0x01,
                             strength, 0.82, 0.28, fade, 0.0)
    _stamp_broken_dots_along(hmap, cx - d, cy + d, cx + d, cy - d, n, seed ^ 0x02,
                             strength, 0.82, 0.28, fade, 0.0)
    _stamp_broken_dots_along(hmap, cx - arm, cy, cx + arm, cy, n, seed ^ 0x03,
                             strength, 0.82, 0.28, fade, 0.0)
    _stamp_broken_dots_along(hmap, cx, cy - arm, cx, cy + arm, n, seed ^ 0x04,
                             strength, 0.82, 0.28, fade, 0.0)


def _cityscape_inset(w: int, h: int) -> tuple[float, float]:
    return w * 0.11, h * 0.11


_CITY_VIEW_SCALE = 0.80
_CITY_VIEW_DENSITY = 1.28
_CITY_HEIGHT_SCALE = 0.84


def _stamp_facade_openings(hmap, cx: float, y_top: float, y_bot: float,
                           half_w: float, n: int, seed: int,
                           strength: float, fade: float) -> None:
    span = y_bot - y_top
    if span < 4:
        return
    door_h = span * 0.38
    door_w = half_w * 0.38
    door_y0 = y_bot - door_h
    _stamp_rect_outline_dots(hmap, cx - door_w, door_y0, cx + door_w, y_bot, n,
                             seed ^ 0xD01, strength * 0.72, fade, glitch=0.32)
    _stamp_broken_dots_along(hmap, cx, door_y0, cx, door_y0 + door_h * 0.45, n,
                             seed ^ 0xD02, strength * 0.4, 0.9, 0.38, fade, 0.2)
    rows = 2 if span > half_w * 1.2 else 1
    cols = 2
    for row in range(rows):
        for col in range(cols):
            wx = cx + (col - 0.5) * half_w * 0.82
            wy0 = y_top + span * (0.10 + row * 0.30)
            ww = half_w * 0.26
            wh = span * 0.18
            _stamp_rect_outline_dots(hmap, wx - ww, wy0, wx + ww, wy0 + wh, n,
                                     seed ^ (0xD10 + row * 4 + col), strength * 0.55,
                                     fade, glitch=0.35)


def _stamp_building_body(hmap, cx: float, y_top: float, y_bot: float,
                         half_w: float, n: int, seed: int,
                         strength: float, fade: float) -> None:
    x0, x1 = cx - half_w, cx + half_w
    _stamp_rect_outline_dots(hmap, x0, y_top, x1, y_bot, n, seed, strength * 0.85, fade,
                             glitch=0.42)
    _stamp_facade_openings(hmap, cx, y_top, y_bot, half_w, n, seed ^ 0xB0D,
                           strength, fade)


def _stamp_gothic_arch_crown(hmap, cx: float, floor_y: float, peak_y: float,
                             half_w: float, n: int, seed: int,
                             strength: float, fade: float) -> None:
    apex_y = peak_y
    left_x, right_x = cx - half_w, cx + half_w
    ow = half_w * 1.08
    o_apex = peak_y + (floor_y - peak_y) * 0.05
    o_st = strength * 0.36
    _stamp_broken_dots_along(hmap, cx - ow, floor_y, cx, o_apex, n, seed ^ 0x08,
                             o_st, 1.2, 0.34, fade, glitch=0.32)
    _stamp_broken_dots_along(hmap, cx + ow, floor_y, cx, o_apex, n, seed ^ 0x09,
                             o_st, 1.2, 0.36, fade, glitch=0.32)
    _stamp_broken_dots_along(hmap, left_x, floor_y, cx, apex_y, n, seed ^ 0x01,
                             strength, 1.0, 0.12, fade, glitch=0.48)
    _stamp_broken_dots_along(hmap, right_x, floor_y, cx, apex_y, n, seed ^ 0x02,
                             strength, 1.0, 0.14, fade, glitch=0.48)
    _stamp_broken_dots_along(hmap, left_x, floor_y, right_x, floor_y, n, seed ^ 0x03,
                             strength * 0.55, 1.2, 0.28, fade, glitch=0.35)
    iw = half_w * 0.50
    iapex = floor_y - (floor_y - peak_y) * 0.72
    inner_y = floor_y + (floor_y - peak_y) * 0.04
    inner_st = strength * 0.45
    _stamp_broken_dots_along(hmap, cx - iw, inner_y, cx, iapex, n, seed ^ 0x04,
                             inner_st, 1.3, 0.36, fade, glitch=0.30)
    _stamp_broken_dots_along(hmap, cx + iw, inner_y, cx, iapex, n, seed ^ 0x05,
                             inner_st, 1.3, 0.38, fade, glitch=0.30)
    rose_y = floor_y - (floor_y - peak_y) * 0.42
    _stamp_rose_window_dots(hmap, cx, rose_y, half_w * 0.22, n, seed ^ 0x0B,
                            strength * 0.38, fade)


def _stamp_gothic_arch_dots(hmap, cx: float, spring_y: float, base_y: float,
                            half_w: float, n: int, seed: int,
                            strength: float, fade: float) -> None:
    apex_y = spring_y - half_w * 0.88
    left_x, right_x = cx - half_w, cx + half_w
    ow = half_w * 1.10
    o_apex = spring_y - ow * 0.86
    o_st = strength * 0.38
    _stamp_broken_dots_along(hmap, cx - ow, base_y, cx, o_apex, n, seed ^ 0x08,
                             o_st, 1.25, 0.36, fade, glitch=0.35)
    _stamp_broken_dots_along(hmap, cx + ow, base_y, cx, o_apex, n, seed ^ 0x09,
                             o_st, 1.25, 0.38, fade, glitch=0.35)
    _stamp_broken_dots_along(hmap, left_x, base_y, cx, apex_y, n, seed ^ 0x01,
                             strength, 1.05, 0.14, fade, glitch=0.50)
    _stamp_broken_dots_along(hmap, right_x, base_y, cx, apex_y, n, seed ^ 0x02,
                             strength, 1.05, 0.16, fade, glitch=0.50)
    _stamp_broken_dots_along(hmap, left_x, spring_y, right_x, spring_y, n, seed ^ 0x03,
                             strength * 0.58, 1.25, 0.30, fade, glitch=0.38)
    _stamp_broken_dots_along(hmap, left_x, spring_y - 1.2, right_x, spring_y - 1.2, n,
                             seed ^ 0x0A, strength * 0.42, 1.4, 0.40, fade, glitch=0.3)
    iw = half_w * 0.52
    iapex = spring_y - iw * 0.75
    inner_y = spring_y + (base_y - spring_y) * 0.12
    inner_st = strength * 0.48
    _stamp_broken_dots_along(hmap, cx - iw, inner_y, cx, iapex, n, seed ^ 0x04,
                             inner_st, 1.35, 0.38, fade, glitch=0.32)
    _stamp_broken_dots_along(hmap, cx + iw, inner_y, cx, iapex, n, seed ^ 0x05,
                             inner_st, 1.35, 0.40, fade, glitch=0.32)
    for side, off in ((-1, 0x06), (1, 0x07)):
        tx = cx + side * iw * 0.55
        ty = inner_y + (iapex - inner_y) * 0.45
        _stamp_broken_dots_along(hmap, cx, iapex + (spring_y - iapex) * 0.08,
                                 tx, ty, n, seed ^ off, inner_st * 0.72, 1.4, 0.46, fade, 0.22)
    rose_y = spring_y - half_w * 0.38
    _stamp_rose_window_dots(hmap, cx, rose_y, half_w * 0.24, n, seed ^ 0x0B,
                            strength * 0.40, fade)


def _stamp_rect_outline_dots(hmap, x0: float, y0: float, x1: float, y1: float,
                             n: int, seed: int, strength: float, fade: float,
                             glitch: float = 0.35) -> None:
    _stamp_broken_dots_along(hmap, x0, y0, x1, y0, n, seed ^ 0x01, strength, 1.1, 0.32, fade, glitch)
    _stamp_broken_dots_along(hmap, x1, y0, x1, y1, n, seed ^ 0x02, strength, 1.1, 0.34, fade, glitch)
    _stamp_broken_dots_along(hmap, x1, y1, x0, y1, n, seed ^ 0x03, strength, 1.1, 0.32, fade, glitch)
    _stamp_broken_dots_along(hmap, x0, y1, x0, y0, n, seed ^ 0x04, strength, 1.1, 0.34, fade, glitch)


def _stamp_round_arch_dots(hmap, cx: float, spring_y: float, base_y: float,
                           half_w: float, n: int, seed: int,
                           strength: float, fade: float) -> None:
    import math
    rad = half_w
    _stamp_broken_arc_dots(hmap, cx, spring_y, rad, n, seed ^ 0x01, strength, fade,
                           math.pi, math.tau, 0.26)
    _stamp_broken_dots_along(hmap, cx - half_w, spring_y, cx - half_w, base_y, n,
                             seed ^ 0x02, strength * 0.9, 1.0, 0.14, fade, glitch=0.5)
    _stamp_broken_dots_along(hmap, cx + half_w, spring_y, cx + half_w, base_y, n,
                             seed ^ 0x03, strength * 0.9, 1.0, 0.16, fade, glitch=0.5)
    _stamp_broken_dots_along(hmap, cx - half_w, spring_y, cx + half_w, spring_y, n,
                             seed ^ 0x04, strength * 0.55, 1.2, 0.30, fade, glitch=0.38)
    _stamp_rose_window_dots(hmap, cx, spring_y - rad * 0.55, rad * 0.32, n, seed ^ 0x05,
                            strength * 0.38, fade)


def _stamp_dome_dots(hmap, cx: float, seat_y: float, radius: float, n: int,
                     seed: int, strength: float, fade: float) -> None:
    import math
    _stamp_broken_arc_dots(hmap, cx, seat_y, radius, n, seed ^ 0x01, strength * 0.85, fade,
                           math.pi, math.tau, 0.24)
    _stamp_broken_dots_along(hmap, cx - radius, seat_y, cx + radius, seat_y, n,
                             seed ^ 0x02, strength * 0.5, 1.15, 0.34, fade, glitch=0.35)


def _stamp_block_tower_dots(hmap, cx: float, top_y: float, base_y: float,
                            half_w: float, n: int, seed: int,
                            strength: float, fade: float) -> None:
    x0, x1 = cx - half_w, cx + half_w
    _stamp_rect_outline_dots(hmap, x0, top_y, x1, base_y, n, seed, strength, fade, glitch=0.45)
    wy0 = top_y + (base_y - top_y) * 0.38
    wy1 = wy0 + half_w * 0.55
    wx0, wx1 = cx - half_w * 0.38, cx + half_w * 0.38
    _stamp_rect_outline_dots(hmap, wx0, wy0, wx1, wy1, n, seed ^ 0x10,
                             strength * 0.45, fade, glitch=0.4)
    _stamp_broken_dots_along(hmap, cx, top_y - half_w * 0.15, cx, top_y, n,
                             seed ^ 0x11, strength * 0.35, 1.0, 0.38, fade, glitch=0.3)


def _draw_gothic_tower(hmap, b: dict, base_y: float, n: int) -> None:
    cx, bw, bh = b["cx"], b["w"], b["h"]
    half_w = bw * 0.5
    top_y = base_y - bh
    peak_y = top_y + bh * 0.06
    body_top = top_y + bh * 0.50
    fade = b["fade"]
    st = 0.55 + fade * 0.42
    bs = b["seed"]
    ornament = int(_hash_val(4, 4, bs) * 3)

    _stamp_building_body(hmap, cx, body_top, base_y, half_w, n, bs ^ 0x10, st, fade)
    _stamp_gothic_arch_crown(hmap, cx, body_top, peak_y, half_w * 0.92, n, bs ^ 0x20, st, fade)

    if bh > n * 0.22:
        mid_peak = top_y + bh * 0.22
        mid_body = top_y + bh * 0.58
        _stamp_gothic_arch_crown(hmap, cx, mid_body, mid_peak, half_w * 0.68, n,
                                 bs ^ 0x50, st * 0.58, fade * 0.9)

    for tier in range(2):
        ty = body_top + (base_y - body_top) * (tier + 1) / 3.5
        _stamp_broken_dots_along(hmap, cx - half_w * 0.92, ty, cx + half_w * 0.92, ty,
                                 n, bs ^ (0x60 + tier), st * 0.34, 1.15, 0.40, fade, glitch=0.35)

    if ornament == 0:
        _stamp_broken_dots_along(hmap, cx, body_top - bh * 0.08, cx, peak_y, n, bs ^ 0x21,
                                 st * 0.75, 1.0, 0.14, fade, glitch=0.40)
    elif ornament == 1:
        for side, off in ((-1, 0x23), (1, 0x24)):
            px = cx + side * half_w * 0.75
            _stamp_broken_dots_along(hmap, px, body_top - bh * 0.05, px, peak_y + bh * 0.04,
                                     n, bs ^ off, st * 0.62, 1.1, 0.22, fade, glitch=0.45)

    _stamp_broken_dots_along(hmap, cx - half_w * 1.05, base_y, cx + half_w * 1.05, base_y,
                             n, bs ^ 0x40, st * 0.48, 1.25, 0.32, fade, glitch=0.0)


def _draw_round_tower(hmap, b: dict, base_y: float, n: int) -> None:
    cx, bw, bh = b["cx"], b["w"], b["h"]
    half_w, top_y = bw * 0.5, base_y - bh
    peak_y = top_y + bh * 0.10
    body_top = top_y + bh * 0.52
    fade, st, bs = b["fade"], 0.55 + b["fade"] * 0.42, b["seed"]
    _stamp_building_body(hmap, cx, body_top, base_y, half_w, n, bs ^ 0x10, st, fade)
    import math
    _stamp_broken_arc_dots(hmap, cx, body_top, half_w * 0.88, n, bs ^ 0x20, st * 0.92, fade,
                           math.pi, math.tau, 0.22)
    if bh > n * 0.16:
        _stamp_dome_dots(hmap, cx, peak_y, half_w * 0.48, n, bs ^ 0x22, st * 0.60, fade)
    for tier in range(2):
        ty = base_y - (base_y - top_y) * (tier + 1) / 3.0
        _stamp_broken_dots_along(hmap, cx - half_w, ty, cx + half_w, ty, n,
                                 bs ^ (0x60 + tier), st * 0.34, 1.2, 0.38, fade, glitch=0.4)
    _stamp_broken_dots_along(hmap, cx - half_w * 1.05, base_y, cx + half_w * 1.05, base_y,
                             n, bs ^ 0x40, st * 0.45, 1.25, 0.32, fade, glitch=0.0)


def _draw_block_tower(hmap, b: dict, base_y: float, n: int) -> None:
    cx, bw, bh = b["cx"], b["w"], b["h"]
    half_w, top_y = bw * 0.5, base_y - bh
    roof_y = top_y + bh * 0.10
    fade, st, bs = b["fade"], 0.55 + b["fade"] * 0.42, b["seed"]
    _stamp_building_body(hmap, cx, roof_y, base_y, half_w, n, bs ^ 0x20, st, fade)
    _stamp_broken_dots_along(hmap, cx - half_w * 1.05, roof_y, cx + half_w * 1.05, roof_y, n,
                             bs ^ 0x30, st * 0.45, 1.15, 0.32, fade, glitch=0.36)
    if _hash_val(2, 2, bs) > 0.45:
        _stamp_dome_dots(hmap, cx, top_y + bh * 0.04, half_w * 0.42, n, bs ^ 0x31, st * 0.52, fade)


def _draw_mixed_tower(hmap, b: dict, base_y: float, n: int) -> None:
    cx, bw, bh = b["cx"], b["w"], b["h"]
    half_w, top_y = bw * 0.5, base_y - bh
    body_top = top_y + bh * 0.50
    peak_y = top_y + bh * 0.06
    fade, st, bs = b["fade"], 0.55 + b["fade"] * 0.42, b["seed"]
    _stamp_building_body(hmap, cx, body_top, base_y, half_w, n, bs ^ 0x20, st, fade)
    _stamp_gothic_arch_crown(hmap, cx, body_top, peak_y, half_w * 0.78, n,
                             bs ^ 0x50, st * 0.72, fade)
    _stamp_dome_dots(hmap, cx, peak_y, half_w * 0.38, n, bs ^ 0x51, st * 0.55, fade)


def _draw_twin_round_tower(hmap, b: dict, base_y: float, n: int) -> None:
    import math
    cx, bw, bh = b["cx"], b["w"], b["h"]
    half_w, top_y = bw * 0.5, base_y - bh
    body_top = top_y + bh * 0.52
    fade, st, bs = b["fade"], 0.55 + b["fade"] * 0.42, b["seed"]
    _stamp_building_body(hmap, cx, body_top, base_y, half_w, n, bs ^ 0x18, st * 0.9, fade)
    gap = half_w * 0.22
    for side, off in ((-1, 0x20), (1, 0x21)):
        tx = cx + side * gap
        tw = half_w * 0.40
        _stamp_broken_arc_dots(hmap, tx, body_top, tw, n, bs ^ off, st * 0.85, fade,
                               math.pi, math.tau, 0.24)
        _stamp_facade_openings(hmap, tx, body_top + (base_y - body_top) * 0.15, base_y,
                               tw * 0.85, n, bs ^ (off + 2), st * 0.5, fade)
    _stamp_rect_outline_dots(hmap, cx - half_w * 0.22, top_y + bh * 0.12,
                             cx + half_w * 0.22, body_top, n, bs ^ 0x23,
                             st * 0.36, fade, glitch=0.30)


def _draw_backdrop_block(hmap, b: dict, base_y: float, n: int) -> None:
    cx, bw, bh = b["cx"], b["w"], b["h"]
    half_w, top_y = bw * 0.5, base_y - bh
    layer = b.get("layer", 1)
    fade = b["fade"]
    st = (0.22 + fade * 0.28) if layer > 0 else (0.14 + fade * 0.18)
    bs = b["seed"]
    body_top = top_y + bh * 0.48
    peak_y = top_y + bh * 0.08
    _stamp_building_body(hmap, cx, body_top, base_y, half_w, n, bs, st, fade)
    if int(_hash_val(1, 1, bs) * 2) == 0:
        import math
        _stamp_broken_arc_dots(hmap, cx, body_top, half_w * 0.85, n, bs ^ 1, st * 0.8, fade,
                               math.pi, math.tau, 0.30)
    else:
        _stamp_gothic_arch_crown(hmap, cx, body_top, peak_y, half_w * 0.80, n,
                                 bs ^ 2, st * 0.75, fade)


def _draw_cathedral_building(hmap, b: dict, base_y: float, n: int, seed: int) -> None:
    if b["backdrop"]:
        _draw_backdrop_block(hmap, b, base_y, n)
        return
    style = b["style"] % 5
    if style == 0:
        _draw_gothic_tower(hmap, b, base_y, n)
    elif style == 1:
        _draw_round_tower(hmap, b, base_y, n)
    elif style == 2:
        _draw_block_tower(hmap, b, base_y, n)
    elif style == 3:
        _draw_mixed_tower(hmap, b, base_y, n)
    else:
        _draw_twin_round_tower(hmap, b, base_y, n)


def _stamp_cityscape_accents(hmap, seed: int, w: int, h: int, horizon: float,
                             base_y: float, inset_x: float, inset_y: float) -> None:
    n = h
    x0, x1 = inset_x + 6, w - inset_x - 6
    y0, y1 = inset_y + 6, horizon + (base_y - horizon) * 0.35
    star_count = int((20 + int(_hash_val(11, 11, seed) * 16)) * (w / h) * 0.72)
    for i in range(star_count):
        sx = x0 + _hash_val(i, 0, seed ^ 0x57A1) * (x1 - x0)
        sy = y0 + _hash_val(i, 1, seed ^ 0x57A2) * (y1 - y0)
        arm = 2.5 + _hash_val(i, 2, seed) * 5.0
        st = 0.20 + _hash_val(i, 3, seed) * 0.18
        _stamp_dotted_cross_star(hmap, sx, sy, n, seed ^ (i * 0x20), arm, st)

    accent_n = int((6 + int(_hash_val(13, 13, seed) * 4)) * (w / h) * 0.55)
    for i in range(accent_n):
        ax = inset_x + (w - 2 * inset_x) * (0.10 + _hash_val(i, 0, seed ^ 0xACC) * 0.80)
        ay = horizon + (base_y - horizon) * (0.12 + _hash_val(i, 1, seed) * 0.65)
        hw = 3.5 + _hash_val(i, 3, seed) * 5.5
        hh = hw * (0.65 + _hash_val(i, 4, seed) * 0.35)
        _stamp_rect_outline_dots(hmap, ax - hw, ay - hh, ax + hw, ay + hh, n,
                                 seed ^ (i * 0x60), 0.22, 1.0, glitch=0.28)


def _cityscape_profile(seed: int, w: int, h: int) -> list[dict]:
    inset_x, inset_y = _cityscape_inset(w, h)
    span = w - 2 * inset_x
    sc = _CITY_VIEW_SCALE
    hs = _CITY_HEIGHT_SCALE
    count = int((13 + int(_hash_val(0, 0, seed) * 5)) * (w / h) * _CITY_VIEW_DENSITY)
    slots = []
    for i in range(count):
        layer = int(_hash_val(i, 5, seed) * 3)
        bw = h * (0.075 + _hash_val(i, 2, seed) * 0.12) * sc
        cx = inset_x + span * (0.03 + (i + 0.18 + _hash_val(i, 1, seed) * 0.28) / count * 0.94)
        cx = max(inset_x + bw * 0.52, min(w - inset_x - bw * 0.52, cx))
        slots.append({
            "cx": cx,
            "w": bw,
            "h": h * (0.22 + _hash_val(i, 3, seed) * 0.40) * (0.77 + layer * 0.12) * sc * hs,
            "style": int(_hash_val(i, 4, seed) * 5),
            "fade": 0.30 + layer * 0.21 + _hash_val(i, 6, seed) * 0.10,
            "seed": seed ^ (i * 0xC17A),
            "backdrop": False,
            "layer": 2,
        })
    back_count = int((6 + int(_hash_val(10, 10, seed) * 3)) * (w / h) * _CITY_VIEW_DENSITY * 0.90)
    for i in range(back_count):
        bw = h * (0.09 + _hash_val(i, 7, seed) * 0.08) * sc
        cx = inset_x + span * (0.04 + (i + 0.45) / max(1, back_count) * 0.92)
        cx = max(inset_x + bw * 0.52, min(w - inset_x - bw * 0.52, cx))
        slots.append({
            "cx": cx,
            "w": bw,
            "h": h * (0.14 + _hash_val(i, 8, seed) * 0.16) * sc * hs,
            "style": int(_hash_val(i, 9, seed) * 2),
            "fade": 0.18 + _hash_val(i, 11, seed) * 0.11,
            "seed": seed ^ (i * 0xBA01),
            "backdrop": True,
            "layer": 1,
        })
    back2_count = int((5 + int(_hash_val(14, 14, seed) * 3)) * (w / h) * _CITY_VIEW_DENSITY * 0.85)
    for i in range(back2_count):
        bw = h * (0.10 + _hash_val(i, 12, seed) * 0.09) * sc
        cx = inset_x + span * (0.02 + (i + 0.28) / max(1, back2_count) * 0.96)
        cx = max(inset_x + bw * 0.52, min(w - inset_x - bw * 0.52, cx))
        slots.append({
            "cx": cx,
            "w": bw,
            "h": h * (0.10 + _hash_val(i, 13, seed) * 0.12) * sc * hs,
            "style": int(_hash_val(i, 14, seed) * 2),
            "fade": 0.09 + _hash_val(i, 15, seed) * 0.08,
            "seed": seed ^ (i * 0xDE01),
            "backdrop": True,
            "layer": 0,
        })
    slots.sort(key=lambda b: (b.get("layer", 2), b["cx"]))
    return slots


def _compose_faded_cityscape(hmap, seed: int) -> None:
    """Gothic cathedral skyline — broken dotted lines, horizontal glitch streaks."""
    h, w = _hmap_dims(hmap)
    cx = (w - 1) / 2.0
    cy = (h - 1) / 2.0
    inset_x, inset_y = _cityscape_inset(w, h)
    base_y = h - inset_y * 0.73
    horizon = inset_y + (base_y - inset_y) * 0.44

    for b in _cityscape_profile(seed, w, h):
        _draw_cathedral_building(hmap, b, base_y, h, seed)

    _stamp_cityscape_accents(hmap, seed, w, h, horizon, base_y, inset_x, inset_y)

    sky_dots = int(w * 0.55)
    for i in range(sky_dots):
        if _hash_val(i, 0, seed ^ 0x5E01) > 0.78:
            continue
        c = int(inset_x + 4 + _hash_val(i, 1, seed ^ 0x5E02) * (w - 2 * inset_x - 8))
        r = int(inset_y + 4 + _hash_val(i, 2, seed ^ 0x5E03) * (horizon - inset_y - 8))
        _darken_dot(hmap, c, r, h, 0.06 + _hash_val(i, 3, seed) * 0.10, 1.0)

    arm = max(3.5, h * 0.038)
    mark_in_x = inset_x + w * 0.02
    mark_in_y = inset_y + h * 0.04
    for i, (px, py) in enumerate([
        (cx, mark_in_y), (cx, h - mark_in_y),
        (mark_in_x, cy), (w - mark_in_x, cy),
    ]):
        _stamp_dotted_cross_star(hmap, px, py, h, seed ^ (i * 0x10), arm, 0.34)


def _compose_gothic_seal(hmap, seed: int, variant: str = "node") -> None:
    n = len(hmap)
    cx = (n - 1) / 2.0
    cy = (n - 1) / 2.0
    scale = n / 140.0
    apex = cy - n * 0.28
    base = cy + n * 0.30

    _draw_blueprint_construction(hmap, n, cx, cy, seed, scale, apex, base)
    _draw_blueprint_gothic_frame(hmap, n, cx, cy, seed, scale)

    if variant == "node":
        _stamp_ornate_lantern(hmap, cx, cy - n * 0.02, n, seed ^ 0x1A4E7E, scale)
    elif variant == "choice":
        _stamp_diamond(hmap, cx, cy - n * 0.01, 9.0 * scale, n, seed ^ 0xC401, strength=0.62)
        _stamp_diamond(hmap, cx, cy - n * 0.01, 5.0 * scale, n, seed ^ 0xC402, strength=0.44)
        _stamp_crosshair(hmap, cx, cy - n * 0.01, n, seed ^ 0xC403,
                         arm=4.5 * scale, strength=0.32)
    else:
        _stamp_circle_band(hmap, cx, cy, n * 0.13, n, seed ^ 0x1EEA01,
                           strength=0.50, band_half=0.95)
        _stamp_diamond(hmap, cx, cy, 5.5 * scale, n, seed ^ 0x1EEA02, strength=0.55)

    _apply_blueprint_anchor_marks(hmap, n, cx, cy, seed, scale)
    _apply_seal_grain(hmap, n, seed ^ 0x6BA1A1, strength=0.10)


def _dither_hmap(hmap) -> list[list[bool]]:
    rows, cols = _hmap_dims(hmap)
    grid = [[False] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            grid[r][c] = hmap[r][c] < _B4[r % 4][c % 4]
    return grid


def _dither_diffusion_hmap(
    hmap,
    paper_snap: float = _PAPER_SNAP,
    ink_snap: float = _INK_SNAP,
) -> list[list[bool]]:
    """Serpentine Floyd–Steinberg diffusion (Photoshop-style bitmap dither)."""
    rows, cols = _hmap_dims(hmap)
    buf = [[0.0] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            v = hmap[r][c]
            if v >= paper_snap:
                v = 1.0
            elif v <= ink_snap:
                v = 0.0
            buf[r][c] = v * 255.0

    grid = [[False] * cols for _ in range(rows)]
    for r in range(rows):
        reverse = r % 2 == 1
        col_range = range(cols - 1, -1, -1) if reverse else range(cols)
        for c in col_range:
            old = buf[r][c]
            new = 0.0 if old < 128.0 else 255.0
            grid[r][c] = new < 128.0
            err = old - new
            if reverse:
                if c > 0:
                    buf[r][c - 1] += err * 7 / 16
                if r + 1 < rows:
                    if c < cols - 1:
                        buf[r + 1][c + 1] += err * 3 / 16
                    buf[r + 1][c] += err * 5 / 16
                    if c > 0:
                        buf[r + 1][c - 1] += err * 1 / 16
            else:
                if c + 1 < cols:
                    buf[r][c + 1] += err * 7 / 16
                if r + 1 < rows:
                    if c > 0:
                        buf[r + 1][c - 1] += err * 3 / 16
                    buf[r + 1][c] += err * 5 / 16
                    if c + 1 < cols:
                        buf[r + 1][c + 1] += err * 1 / 16
    for r in range(rows):
        for c in range(cols):
            if hmap[r][c] >= paper_snap:
                grid[r][c] = False
    return grid


def _build_seal_hmap(seed_text: str, size: int, variant: str) -> list[list[float]]:
    seed = (hash(seed_text) ^ {"node": 0, "choice": 0xC401CE,
                               "item": 0x1EEA00}[variant]) & 0xFFFF_FFFF
    hmap = _new_hmap(size, 1.0)
    _compose_wavefunction_seal(hmap, seed, variant)
    _apply_contrast_on(hmap, 2.15)
    return hmap


def _apply_contrast_on(hmap, k: float) -> None:
    n = len(hmap)
    for r in range(n):
        for c in range(n):
            v = hmap[r][c]
            v = 0.5 + (v - 0.5) * k
            hmap[r][c] = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


# ===========================================================================
# Public API
# ===========================================================================

# ---------------------------------------------------------------------------
# Image caches (keyed by generation parameters — avoids re-rendering on
# revisiting the same node or choice label)
# ---------------------------------------------------------------------------
_scene_cache:  dict = {}
_choice_cache: dict = {}
_node_cache:   dict = {}
_node_pil_cache: dict = {}
_seal_cache:   dict = {}


def generate_node_pil_image(
    node_id: str,
    grid_w: int = 340,
    grid_h: int = 212,
) -> "Image":
    """Landscape cityscape as 1-bit PIL Image (1=paper, 0=ink)."""
    from PIL import Image as PILImage
    key = (node_id, grid_w, grid_h)
    if key in _node_pil_cache:
        return _node_pil_cache[key].copy()
    seed = (hash(node_id) ^ 0xD0DE_5CA1) & 0xFFFF_FFFF
    hmap = _new_hmap_rect(grid_h, grid_w, 1.0)
    _compose_faded_cityscape(hmap, seed)
    _apply_contrast_on(hmap, 1.08)
    img = _hmap_to_pil_image(hmap)
    _node_pil_cache[key] = img
    return img.copy()


def generate_node_image(
    node_id: str,
    grid_w: int = 544,
    grid_h: int = 272,
    zoom: int = 1,
    ink: str   = "#0f0f0c",
    paper: str = "#ffffff",
) -> "tk.PhotoImage":
    """Landscape cityscape for a scene node — one image per node id."""
    key = (node_id, grid_w, grid_h, zoom, ink, paper)
    if key in _node_cache:
        return _node_cache[key]
    seed = (hash(node_id) ^ 0xD0DE_5CA1) & 0xFFFF_FFFF
    img = _landscape_photoimage(seed, grid_w, grid_h, zoom, ink, paper)
    _node_cache[key] = img
    return img


def generate_scene_image(
    text: str,
    ink: str   = "#0f0f0c",
    paper: str = "#dcdcd0",
) -> "tk.PhotoImage":
    key = (text, ink, paper)
    if key in _scene_cache:
        return _scene_cache[key]
    seed = hash(text) & 0xFFFF_FFFF
    hmap = _layered_noise(seed)
    _draw_shapes(hmap, text, seed)
    _apply_organic_mask(hmap, seed)
    _apply_contrast(hmap, 1.45)
    grid = _dither(hmap)
    img = _to_photoimage(grid, ink, paper)
    _scene_cache[key] = img
    return img


def generate_choice_image(
    text: str,
    grid_w: int = 544,
    grid_h: int = 272,
    grid_size: int | None = None,
    zoom: int = 2,
    ink: str   = "#0f0f0c",
    paper: str = "#ffffff",
) -> "tk.PhotoImage":
    """Faded gothic cityscape on white — broken dotted lines, grayscale."""
    if grid_size is not None:
        grid_w = grid_h = grid_size
    key = (text, grid_w, grid_h, zoom, ink, paper)
    if key in _choice_cache:
        return _choice_cache[key]

    seed = (hash(text) ^ 0xC401_5E7D) & 0xFFFF_FFFF
    img = _landscape_photoimage(seed, grid_w, grid_h, zoom, ink, paper)
    _choice_cache[key] = img
    return img


def generate_scene_pil_image(text: str, zoom: int = 3) -> "Image":
    """Same procedural scene, returned as a 1-bit PIL Image.
    Pixel values: 1 = paper (white), 0 = ink (black).
    zoom: scale factor (3 → 300×300, 2 → 200×200, 1 → 100×100).
    Used by player_renderer.py for Pi Zero e-paper output."""
    from PIL import Image as _PILImage
    seed = hash(text) & 0xFFFF_FFFF
    hmap = _layered_noise(seed)
    _draw_shapes(hmap, text, seed)
    _apply_organic_mask(hmap, seed)
    grid = _dither(hmap)
    img = _PILImage.new("1", (COLS, ROWS), 1)
    for r in range(ROWS):
        for c in range(COLS):
            if grid[r][c]:
                img.putpixel((c, r), 0)
    if zoom != 1:
        w, h = img.size
        img = img.resize((w * zoom, h * zoom), _PILImage.NEAREST)
    return img


def generate_seal_image(
    seed_text: str,
    size: int = 140,
    variant: str = "node",
    zoom: int = 1,
    ink: str = "#0f0f0c",
    paper: str = "#dcdcd0",
) -> "tk.PhotoImage":
    """Procedural wavefunction seal — wavy lobe ring + interference dots."""
    key = (seed_text, size, variant, zoom, ink, paper)
    if key in _seal_cache:
        return _seal_cache[key]
    hmap = _build_seal_hmap(seed_text, size, variant)
    grid = _dither_hmap(hmap)
    img = _to_photoimage(grid, ink, paper)
    result = img if zoom == 1 else img.zoom(zoom)
    _seal_cache[key] = result
    return result


def generate_seal_pil_image(
    seed_text: str,
    size: int = 140,
    variant: str = "node",
    zoom: int = 2,
) -> "Image":
    """Gothic seal as 1-bit PIL Image (1=paper, 0=ink)."""
    from PIL import Image as _PILImage
    hmap = _build_seal_hmap(seed_text, size, variant)
    grid = _dither_hmap(hmap)
    img = _PILImage.new("1", (size, size), 1)
    for r in range(size):
        for c in range(size):
            if grid[r][c]:
                img.putpixel((c, r), 0)
    if zoom != 1:
        img = img.resize((size * zoom, size * zoom), _PILImage.NEAREST)
    return img
