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


def _dither(hmap):
    grid = [[False] * COLS for _ in range(ROWS)]
    for r in range(ROWS):
        for c in range(COLS):
            grid[r][c] = hmap[r][c] < _B4[r % 4][c % 4]
    return grid


def _to_photoimage(grid, ink, paper):
    rows_data = []
    for row in grid:
        row_colors = [ink if cell else paper for cell in row]
        rows_data.append("{" + " ".join(row_colors) + "}")
    img = tk.PhotoImage(width=COLS, height=ROWS)
    img.put(" ".join(rows_data))
    return img if ZOOM == 1 else img.zoom(ZOOM)


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
    _nw = noise_warp * _GS
    r1 = max(0,    cy - h - int(_nw) - 1)
    r2 = min(ROWS, cy + h + int(_nw) + 2)
    c1 = max(0,    cx - w - int(_nw) - 1)
    c2 = min(COLS, cx + w + int(_nw) + 2)

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
# Public API
# ===========================================================================

# ---------------------------------------------------------------------------
# Image caches (keyed by generation parameters — avoids re-rendering on
# revisiting the same node or choice label)
# ---------------------------------------------------------------------------
_scene_cache:  dict = {}
_choice_cache: dict = {}


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
    grid_size: int = 70,
    zoom: int = 2,
    ink: str   = "#0f0f0c",
    paper: str = "#dcdcd0",
) -> "tk.PhotoImage":
    """Noisy eight-spiked star for a choice button.

    Interior and exterior are paper.  The star band boundary is dense ink
    warped by noise and dithered with the Bayer matrix, so it reads like
    the scene noise map rather than a clean line.
    """
    import math

    key = (text, grid_size, zoom, ink, paper)
    if key in _choice_cache:
        return _choice_cache[key]

    seed = (hash(text) ^ 0xC401_5E7D) & 0xFFFF_FFFF
    n = grid_size
    ccx = (n - 1) / 2.0
    ccy = (n - 1) / 2.0

    SPIKES     = 8
    STAR_OUTER = 0.92    # spike-tip radius (normalised) — pushed out to edge
    STAR_INNER = 0.70    # valley radius — higher = ring closer to edge, big open centre
    BAND_HALF  = 0.08    # half-thickness of dithered band
    WARP       = 0.22    # low-freq boundary warp (less warp keeps star legible)
    CHAOS      = 0.28    # high-freq breaks
    BUBBLE     = 0.8    # threshold: noise > this punches a paper hole

    hmap = [[1.0] * n for _ in range(n)]   # start all paper
    for r in range(n):
        for c in range(n):
            dx = (c - ccx) / ccx
            dy = (r - ccy) / ccy

            # Warp the sample point with two noise layers → organic, chaotic
            wx = (_value_noise(c * 0.14, r * 0.14, seed)          - 0.5) * WARP
            wy = (_value_noise(c * 0.14, r * 0.14, seed ^ 0x9E37) - 0.5) * WARP
            wx += (_value_noise(c * 0.55, r * 0.55, seed ^ 0xFACE) - 0.5) * CHAOS
            wy += (_value_noise(c * 0.55, r * 0.55, seed ^ 0xCAFE) - 0.5) * CHAOS
            sx, sy = dx + wx, dy + wy

            dist  = (sx * sx + sy * sy) ** 0.5
            angle = math.atan2(sy, sx)

            # Star radius at this angle: triangle wave between outer & inner
            phase = (angle * SPIKES / (2 * math.pi)) % 1.0   # 0..1 per spike
            tri   = abs(phase * 2.0 - 1.0)                    # 1 at tip, 0 at valley
            star_r = STAR_INNER + (STAR_OUTER - STAR_INNER) * tri

            band_dist = abs(dist - star_r)
            if band_dist >= BAND_HALF:
                continue

            # Bubble holes punch random paper gaps in the band
            bubble_n = _value_noise(c * 0.38, r * 0.38, seed ^ 0xB0BB)
            if bubble_n > BUBBLE:
                continue

            # Inside the band: sample noise, darken toward the band centre
            v = _value_noise(c * 0.25, r * 0.25, seed ^ 0x1A2B)
            v = v * v * (3 - 2 * v)
            t = band_dist / BAND_HALF
            blend = 1.0 - t * t * (3 - 2 * t)
            hmap[r][c] = max(0.0, v - 0.30 * blend)

    rows_data = []
    for r in range(n):
        row_colors = [ink if hmap[r][c] < _B4[r % 4][c % 4] else paper
                      for c in range(n)]
        rows_data.append("{" + " ".join(row_colors) + "}")
    img = tk.PhotoImage(width=n, height=n)
    img.put(" ".join(rows_data))
    result = img if zoom == 1 else img.zoom(zoom)
    _choice_cache[key] = result
    return result


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
