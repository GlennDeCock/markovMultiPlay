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
COLS    = 100
ROWS    = 100
ZOOM    = 3
HORIZON = 60   # row index where ground meets sky

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
    octaves = [(0.07, 0.55, 0), (0.17, 0.30, 13337), (0.38, 0.15, 99991)]
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
    r1 = max(0,    cy - h - int(noise_warp) - 1)
    r2 = min(ROWS, cy + h + int(noise_warp) + 2)
    c1 = max(0,    cx - w - int(noise_warp) - 1)
    c2 = min(COLS, cx + w + int(noise_warp) + 2)

    ns = seed ^ noise_seed_off
    for r in range(r1, r2):
        for c in range(c1, c2):
            # warp the sample point with low-freq noise
            warp_r = (_value_noise(c * 0.18, r * 0.18, ns)          - 0.5) * noise_warp
            warp_c = (_value_noise(c * 0.18, r * 0.18, ns ^ 0x9E37) - 0.5) * noise_warp
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
    for r in range(max(0, cy - band_h), min(ROWS, cy + band_h + 1)):
        rel = abs(r - cy) / (band_h or 1)
        density = (1.0 - rel) ** 1.4
        for c in range(COLS):
            noise = _value_noise(c * 0.25, r * 0.25, seed) * 0.15
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
                                   w=14, h=20, strength=0.88, noise_warp=4.0),
    lambda hmap, seed: _draw_blob(hmap, COLS//2, HORIZON-6, seed,
                                   w=10, h=10, strength=0.80, noise_warp=5.0),
    lambda hmap, seed: _draw_wide_band(hmap, HORIZON, seed,
                                        band_h=8, strength=0.55),
    lambda hmap, seed: _draw_blob(hmap, COLS//3, HORIZON-4, seed,
                                   w=8, h=14, strength=0.85, noise_warp=4.5),
    lambda hmap, seed: _draw_blob(hmap, COLS*2//3, HORIZON-4, seed ^ 0xAB,
                                   w=6, h=18, strength=0.88, noise_warp=3.5),
    lambda hmap, seed: _draw_blob(hmap, COLS//2, HORIZON+6, seed,
                                   w=16, h=5, strength=0.60, noise_warp=6.0),
    lambda hmap, seed: _draw_blob(hmap, COLS//2, HORIZON-2, seed,
                                   w=20, h=8, strength=0.72, noise_warp=5.0),
    lambda hmap, seed: _draw_blob(hmap, COLS//2, ROWS*2//5, seed,
                                   w=12, h=22, strength=0.90, noise_warp=4.0),
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
    jx = int((_hash_val(slot, 0, seed ^ 0x1111) - 0.5) * 24)
    jy = int((_hash_val(0, slot, seed ^ 0x2222) - 0.5) * 10)

    if role == "bg":
        cx = COLS // 2 + jx // 2
        cy = ROWS * 2 // 5 + jy // 2
        scale = 1.3 + _hash_val(slot, slot, seed) * 0.3
    elif role == "mg":
        base_x = [COLS // 3, COLS * 2 // 3, COLS // 2]
        cx = base_x[slot % 3] + jx
        cy = HORIZON - 4 + jy // 2
        scale = 0.85 + _hash_val(slot, slot + 1, seed) * 0.25
    else:
        base_x = [COLS // 4, COLS * 3 // 4, COLS // 2]
        cx = base_x[slot % 3] + jx
        cy = HORIZON + 5 + abs(jy) // 2
        scale = 0.65 + _hash_val(slot, slot + 2, seed) * 0.2

    cx = max(12, min(COLS - 12, cx))
    cy = max(6,  min(ROWS - 8, cy))
    return cx, cy, scale


# ===========================================================================
# Public API
# ===========================================================================

def generate_scene_image(
    text: str,
    ink: str   = "#0f0f0c",
    paper: str = "#dcdcd0",
) -> "tk.PhotoImage":
    seed = hash(text) & 0xFFFF_FFFF
    hmap = _layered_noise(seed)
    _draw_shapes(hmap, text, seed)
    grid = _dither(hmap)
    return _to_photoimage(grid, ink, paper)
